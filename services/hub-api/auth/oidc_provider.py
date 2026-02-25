"""
OIDC Provider endpoints for Tobogganing Hub API.

Implements hub-api as a built-in OIDC Identity Provider, exposing:
  - /.well-known/openid-configuration  (discovery document)
  - /oauth2/jwks                        (public key set)
  - /oauth2/token                       (token endpoint)
  - /oauth2/authorize                   (authorization endpoint — placeholder)
  - /oauth2/userinfo                    (userinfo endpoint)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import structlog
from py4web import action, request, response

from auth.scopes import (
    POLICIES_READ, POLICIES_WRITE, POLICIES_ADMIN, POLICIES_DELETE,
    HUBS_READ, HUBS_WRITE, HUBS_ADMIN, HUBS_DELETE,
    CLUSTERS_READ, CLUSTERS_WRITE, CLUSTERS_ADMIN, CLUSTERS_DELETE,
    CLIENTS_READ, CLIENTS_WRITE, CLIENTS_ADMIN, CLIENTS_DELETE,
    USERS_READ, USERS_WRITE, USERS_ADMIN, USERS_DELETE,
    TENANTS_READ, TENANTS_WRITE, TENANTS_ADMIN, TENANTS_DELETE,
    TEAMS_READ, TEAMS_WRITE, TEAMS_ADMIN, TEAMS_DELETE,
    IDENTITY_READ, IDENTITY_WRITE, IDENTITY_ADMIN, IDENTITY_DELETE,
    SPIFFE_READ, SPIFFE_WRITE, SPIFFE_ADMIN, SPIFFE_DELETE,
    CERTIFICATES_READ, CERTIFICATES_WRITE, CERTIFICATES_ADMIN, CERTIFICATES_DELETE,
    SETTINGS_READ, SETTINGS_WRITE, SETTINGS_ADMIN, SETTINGS_DELETE,
    AUDIT_READ, AUDIT_WRITE, AUDIT_ADMIN, AUDIT_DELETE,
)

logger = structlog.get_logger()

_ALL_SCOPES: list[str] = [
    s.scope_string for s in [
        POLICIES_READ, POLICIES_WRITE, POLICIES_ADMIN, POLICIES_DELETE,
        HUBS_READ, HUBS_WRITE, HUBS_ADMIN, HUBS_DELETE,
        CLUSTERS_READ, CLUSTERS_WRITE, CLUSTERS_ADMIN, CLUSTERS_DELETE,
        CLIENTS_READ, CLIENTS_WRITE, CLIENTS_ADMIN, CLIENTS_DELETE,
        USERS_READ, USERS_WRITE, USERS_ADMIN, USERS_DELETE,
        TENANTS_READ, TENANTS_WRITE, TENANTS_ADMIN, TENANTS_DELETE,
        TEAMS_READ, TEAMS_WRITE, TEAMS_ADMIN, TEAMS_DELETE,
        IDENTITY_READ, IDENTITY_WRITE, IDENTITY_ADMIN, IDENTITY_DELETE,
        SPIFFE_READ, SPIFFE_WRITE, SPIFFE_ADMIN, SPIFFE_DELETE,
        CERTIFICATES_READ, CERTIFICATES_WRITE, CERTIFICATES_ADMIN, CERTIFICATES_DELETE,
        SETTINGS_READ, SETTINGS_WRITE, SETTINGS_ADMIN, SETTINGS_DELETE,
        AUDIT_READ, AUDIT_WRITE, AUDIT_ADMIN, AUDIT_DELETE,
    ]
]


# ---------------------------------------------------------------------------
# Lazy JWTManager singleton
# ---------------------------------------------------------------------------

_jwt_manager = None


def _get_jwt_manager():
    global _jwt_manager
    if _jwt_manager is None:
        from auth.jwt_manager import JWTManager
        _jwt_manager = JWTManager()
    return _jwt_manager


# ---------------------------------------------------------------------------
# Async helper (mirrors middleware.py pattern)
# ---------------------------------------------------------------------------

def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
            asyncio.set_event_loop(None)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _json_response(body: dict, status: int = 200) -> str:
    response.status = status
    response.headers["Content-Type"] = "application/json"
    return json.dumps(body)


def _oauth_error(error: str, description: str, status: int = 400) -> str:
    return _json_response({"error": error, "error_description": description}, status)


# ---------------------------------------------------------------------------
# 1. OIDC Discovery document
# ---------------------------------------------------------------------------

@action(".well-known/openid-configuration", method=["GET"])
@action.uses("json")
def oidc_discovery():
    jwt_mgr = _get_jwt_manager()
    issuer = jwt_mgr.issuer_url

    doc: dict[str, Any] = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth2/authorize",
        "token_endpoint": f"{issuer}/oauth2/token",
        "userinfo_endpoint": f"{issuer}/oauth2/userinfo",
        "jwks_uri": f"{issuer}/oauth2/jwks",
        "response_types_supported": ["code", "token"],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials",
            "refresh_token",
        ],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": _ALL_SCOPES,
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "claims_supported": [
            "sub", "iss", "aud", "scope",
            "tenant", "teams", "roles",
            "iat", "exp", "jti",
        ],
    }

    logger.debug("oidc_discovery_served", issuer=issuer)
    return doc


# ---------------------------------------------------------------------------
# 2. JWKS endpoint
# ---------------------------------------------------------------------------

@action("oauth2/jwks", method=["GET"])
@action.uses("json")
def oauth2_jwks():
    jwks = _get_jwt_manager().get_jwks()
    logger.debug("jwks_served", key_count=len(jwks.get("keys", [])))
    return jwks


# ---------------------------------------------------------------------------
# 3. Token endpoint
# ---------------------------------------------------------------------------

@action("oauth2/token", method=["POST"])
def oauth2_token():
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    # Parse grant_type from form body or JSON
    content_type = request.environ.get("CONTENT_TYPE", "")
    if "application/json" in content_type:
        try:
            body: dict = request.json or {}
        except Exception:
            return _oauth_error("invalid_request", "Malformed JSON body")
    else:
        body = dict(request.vars)

    grant_type: Optional[str] = body.get("grant_type")
    if not grant_type:
        return _oauth_error("invalid_request", "grant_type is required")

    # ------------------------------------------------------------------
    # client_credentials grant
    # ------------------------------------------------------------------
    if grant_type == "client_credentials":
        client_id, client_secret = _extract_client_credentials(body)

        if not client_id or not client_secret:
            return _oauth_error(
                "invalid_client",
                "client_id and client_secret are required",
                status=401,
            )

        idp_row = _lookup_identity_provider(client_id, client_secret)
        if idp_row is None:
            logger.warning("client_credentials_auth_failed", client_id=client_id)
            return _oauth_error("invalid_client", "Invalid client credentials", status=401)

        # Resolve scopes: requested scope vs. configured allowed scopes
        requested_scope_str: str = body.get("scope", "")
        allowed_scopes: list[str] = _parse_allowed_scopes(idp_row)
        granted_scopes = _intersect_scopes(requested_scope_str, allowed_scopes)

        tenant = getattr(idp_row, "tenant_id", "") or ""
        teams: list[str] = _json_field_to_list(getattr(idp_row, "teams", None))
        roles: list[str] = _json_field_to_list(getattr(idp_row, "roles", None))

        try:
            token_pair = _run_async(
                _get_jwt_manager().generate_token(
                    subject=client_id,
                    tenant=tenant,
                    teams=teams,
                    roles=roles,
                    scopes=granted_scopes,
                )
            )
        except Exception as exc:
            logger.error("token_generation_failed", error=str(exc))
            return _oauth_error("server_error", "Token generation failed", status=500)

        expires_in = int(_get_jwt_manager().token_expiry.total_seconds())
        return _json_response({
            "access_token": token_pair["access_token"],
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": " ".join(granted_scopes),
        })

    # ------------------------------------------------------------------
    # refresh_token grant
    # ------------------------------------------------------------------
    if grant_type == "refresh_token":
        refresh_token_str: Optional[str] = body.get("refresh_token")
        if not refresh_token_str:
            return _oauth_error("invalid_request", "refresh_token is required")

        try:
            token_pair = _run_async(
                _get_jwt_manager().refresh_token(refresh_token_str)
            )
        except Exception as exc:
            logger.error("refresh_token_error", error=str(exc))
            return _oauth_error("server_error", "Token refresh failed", status=500)

        if token_pair is None:
            return _oauth_error("invalid_grant", "Invalid or expired refresh token", status=401)

        expires_in = int(_get_jwt_manager().token_expiry.total_seconds())
        return _json_response({
            "access_token": token_pair["access_token"],
            "refresh_token": token_pair["refresh_token"],
            "token_type": "Bearer",
            "expires_in": expires_in,
        })

    return _oauth_error("unsupported_grant_type", f"Unsupported grant_type: {grant_type}")


# ---------------------------------------------------------------------------
# 4. Authorization endpoint (placeholder)
# ---------------------------------------------------------------------------

_AUTHORIZE_FORM_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Tobogganing — Authorize</title></head>
<body>
<h2>Tobogganing Authorization</h2>
<p><em>Full authorization code flow is not yet implemented.</em></p>
<form method="post" action="/oauth2/token">
  <input type="hidden" name="grant_type" value="authorization_code">
  <input type="hidden" name="redirect_uri" value="{redirect_uri}">
  <input type="hidden" name="client_id" value="{client_id}">
  <input type="hidden" name="state" value="{state}">
  <label>Username: <input type="text" name="username"></label><br>
  <label>Password: <input type="password" name="password"></label><br>
  <button type="submit">Authorize</button>
</form>
</body>
</html>
"""


@action("oauth2/authorize", method=["GET"])
def oauth2_authorize():
    client_id = request.vars.get("client_id", "")
    redirect_uri = request.vars.get("redirect_uri", "")
    state = request.vars.get("state", "")
    response_type = request.vars.get("response_type", "")

    if not client_id:
        response.status = 400
        response.headers["Content-Type"] = "text/plain"
        return "client_id is required"

    if response_type not in ("code", "token"):
        response.status = 400
        response.headers["Content-Type"] = "text/plain"
        return "response_type must be 'code' or 'token'"

    logger.info(
        "oauth2_authorize_request",
        client_id=client_id,
        response_type=response_type,
    )

    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return _AUTHORIZE_FORM_HTML.format(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
    )


# ---------------------------------------------------------------------------
# 5. Userinfo endpoint
# ---------------------------------------------------------------------------

@action("oauth2/userinfo", method=["GET"])
@action.uses("json")
def oauth2_userinfo():
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        response.status = 401
        response.headers["WWW-Authenticate"] = 'Bearer realm="tobogganing"'
        return {"error": "unauthorized", "error_description": "Bearer token required"}

    token = auth_header[len("Bearer "):]
    if not token:
        response.status = 401
        response.headers["WWW-Authenticate"] = 'Bearer realm="tobogganing"'
        return {"error": "unauthorized", "error_description": "Bearer token is empty"}

    try:
        claims = _run_async(_get_jwt_manager().validate_token(token))
    except Exception as exc:
        logger.warning("userinfo_token_validation_error", error=str(exc))
        claims = None

    if claims is None:
        response.status = 401
        response.headers["WWW-Authenticate"] = (
            'Bearer realm="tobogganing", error="invalid_token"'
        )
        return {"error": "invalid_token", "error_description": "Token is invalid or expired"}

    # Normalise scope to list
    raw_scope = claims.get("scope", [])
    if isinstance(raw_scope, str):
        scope_list = [s for s in raw_scope.split(" ") if s]
    else:
        scope_list = list(raw_scope)

    profile: dict[str, Any] = {
        "sub": claims.get("sub", ""),
        "iss": claims.get("iss", ""),
        "tenant": claims.get("tenant", ""),
        "teams": claims.get("teams", []),
        "roles": claims.get("roles", []),
        "scope": scope_list,
    }

    # Enrich with user details from DB if the subject looks like a user ID
    subject: str = profile["sub"]
    if subject and not subject.startswith("spiffe://"):
        user_row = _lookup_user(subject)
        if user_row:
            profile["name"] = getattr(user_row, "full_name", "") or ""
            profile["email"] = getattr(user_row, "email", "") or ""
            profile["preferred_username"] = getattr(user_row, "username", "") or ""

    logger.debug("userinfo_served", sub=profile["sub"])
    return profile


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_client_credentials(body: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract client_id / client_secret from body or HTTP Basic auth header."""
    client_id: Optional[str] = body.get("client_id")
    client_secret: Optional[str] = body.get("client_secret")

    if not client_id or not client_secret:
        import base64
        auth_header: str = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                cid, _, csec = decoded.partition(":")
                if cid:
                    client_id = client_id or cid
                    client_secret = client_secret or csec
            except Exception:
                pass

    return client_id, client_secret


def _lookup_identity_provider(client_id: str, client_secret: str):
    """Look up a registered OIDC client in the identity_providers table.

    Returns the matching row or None if not found / secret mismatch.
    The identity_providers table is managed by Alembic migrations and
    queried via PyDAL (migrate=False, runtime-only).
    """
    import hashlib
    try:
        from database import get_read_db
        db = get_read_db()
        row = db(db.identity_providers.client_id == client_id).select().first()
        if row is None:
            return None

        stored_hash: str = getattr(row, "client_secret_hash", "") or ""
        if not stored_hash:
            return None

        provided_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        if provided_hash != stored_hash:
            return None

        is_active = getattr(row, "is_active", True)
        if not is_active:
            logger.warning("identity_provider_inactive", client_id=client_id)
            return None

        return row
    except Exception as exc:
        logger.error("identity_provider_lookup_error", error=str(exc))
        return None


def _parse_allowed_scopes(idp_row) -> list[str]:
    """Extract the allowed scopes list from an identity_providers row."""
    raw = getattr(idp_row, "allowed_scopes", None)
    if raw is None:
        return list(_ALL_SCOPES)
    if isinstance(raw, list):
        return [str(s) for s in raw if s]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(s) for s in parsed if s]
        except (json.JSONDecodeError, ValueError):
            return [s for s in raw.split(" ") if s]
    return list(_ALL_SCOPES)


def _intersect_scopes(requested: str, allowed: list[str]) -> list[str]:
    """Return the intersection of requested and allowed scopes.

    If no specific scopes are requested, return all allowed scopes.
    """
    if not requested or not requested.strip():
        return allowed

    requested_list = [s for s in requested.split(" ") if s]
    allowed_set = set(allowed)
    return [s for s in requested_list if s in allowed_set] or allowed


def _json_field_to_list(value) -> list[str]:
    """Coerce a PyDAL JSON field (list, JSON string, or None) to list[str]."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
        except (json.JSONDecodeError, ValueError):
            return [s for s in value.split(",") if s]
    return []


def _lookup_user(subject: str):
    """Look up a user row by username or user_id for userinfo enrichment."""
    try:
        from database import get_read_db
        db = get_read_db()
        row = db(
            (db.users.username == subject) | (db.users.id == subject)
        ).select(
            db.users.username,
            db.users.email,
            db.users.full_name,
        ).first()
        return row
    except Exception:
        return None
