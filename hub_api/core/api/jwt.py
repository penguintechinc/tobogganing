"""JWT authentication blueprint for core module."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, current_app, request

from hub_api.auth.jwt import decode_token, encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.auth.refresh import is_jti_revoked
from hub_api.cache.client import CacheClient, CacheUnavailable
from hub_api.crypto.keys import KeyProvider
from hub_api.entitlements.gate import require_feature

logger = structlog.get_logger()

blueprint = Blueprint("core_jwt", __name__, url_prefix="/api/v1/jwt")

# Expected issuer/audience for the node/cluster JWTs issued by this blueprint
# (see generate_jwt_token). decode_token() intentionally skips aud verification
# (pyjwt verify_aud=False) because other machine-JWT flows in this app use a
# different audience (e.g. aud="headend", checked separately by
# auth/middleware.py's _extract_machine_identity). Tokens presented to this
# blueprint's /validate and /refresh endpoints are explicitly checked against
# these values so a token minted for a different issuer/audience is rejected.
EXPECTED_ISS = "tobogganing"
EXPECTED_AUD = "tobogganing"

# TTL ceiling for cache-backed revocation entries (2 days > max refresh TTL).
_REVOCATION_TTL_SECONDS = 60 * 60 * 24 * 2


def _extract_bearer_token(auth_header: str | None) -> str | None:
    """Extract bearer token from Authorization header.

    Args:
        auth_header: Authorization header value.

    Returns:
        Token string if valid Bearer header found, else None.
    """
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def _decode_and_verify(token: str, key_provider: KeyProvider) -> dict[str, Any] | None:
    """Decode a JWT and enforce aud/iss match this blueprint's expected values.

    Args:
        token: Encoded JWT string.
        key_provider: KeyProvider for signature verification.

    Returns:
        Decoded claims dict if the signature/expiry are valid and aud/iss
        both match EXPECTED_AUD/EXPECTED_ISS, else None.
    """
    claims = decode_token(token, key_provider)
    if not claims:
        return None
    if claims.get("iss") != EXPECTED_ISS or claims.get("aud") != EXPECTED_AUD:
        logger.warning(
            "jwt_aud_iss_mismatch",
            iss=claims.get("iss"),
            aud=claims.get("aud"),
        )
        return None
    return claims


async def _is_revoked(claims: dict[str, Any], cache: CacheClient | None) -> bool:
    """Check whether a token's jti or subject has been revoked via the shared cache.

    Fails open (returns False) if no cache is configured or the cache backend
    is unavailable, matching the fail-open policy of auth.refresh.is_jti_revoked
    (a cache blip must never hard-block valid tokens).

    Args:
        claims: Decoded JWT claims.
        cache: Shared cache client, or None if not configured.

    Returns:
        True if the token's jti was individually revoked, or its subject was
        revoked (via /jwt/revoke) after this token was issued.
    """
    if cache is None:
        return False

    jti = claims.get("jti")
    if jti and await is_jti_revoked(jti, cache):
        return True

    sub = claims.get("sub") or ""
    node_id = sub.split(":", 1)[1] if ":" in sub else sub
    if not node_id:
        return False

    try:
        revoked_at = await cache.get("auth", "revoked_subject", node_id)
    except Exception as e:
        logger.warning("subject_revocation_check_error", error=str(e))
        return False

    if not revoked_at:
        return False

    try:
        # <=: a token issued in the same wall-clock second as the revocation
        # is treated as revoked too (fail closed on second-granularity ties)
        # rather than risking a just-issued token slipping through.
        return int(claims.get("iat", 0)) <= int(revoked_at)
    except (TypeError, ValueError):
        return False


async def _revoke_jti(jti: str | None, cache: CacheClient | None, exp: int | None = None) -> None:
    """Durably revoke a single JWT by jti in the shared cache.

    Best-effort: logs and swallows cache errors so a cache blip never blocks
    a refresh-rotation flow. Replaces the old in-process ``_REVOKED_TOKENS``
    set, which was useless across pods/restarts.

    Args:
        jti: JWT ID to revoke; no-op if falsy.
        cache: Shared cache client, or None if not configured (no-op).
        exp: Original token's exp claim, used to bound the denylist entry's
            TTL to the token's remaining natural lifetime.
    """
    if cache is None or not jti:
        return
    now = int(time.time())
    ttl = max(int(exp) - now, 60) if exp else _REVOCATION_TTL_SECONDS
    try:
        await cache.set("auth", "revoked_jti", jti, value="1", ttl_seconds=ttl)
    except CacheUnavailable as e:
        logger.error("jti_revocation_cache_unavailable", jti=jti, error=str(e))


async def _revoke_subject(node_id: str, cache: CacheClient | None) -> None:
    """Mark all tokens for a node/subject issued before now as revoked.

    Stores a revocation timestamp keyed by node_id in the shared cache;
    ``_is_revoked`` rejects any presented token whose ``iat`` predates this
    timestamp. Best-effort: logs and swallows cache errors rather than
    failing the revoke request (durable revocation degrades gracefully to
    "not currently enforceable" rather than a 5xx).

    Args:
        node_id: Node ID to revoke (matches the id portion of the sub claim).
        cache: Shared cache client, or None if not configured — logged as a
            revocation-store limitation since nothing durable is recorded.
    """
    if not node_id:
        return
    if cache is None:
        logger.warning(
            "subject_revocation_cache_not_configured",
            node_id=node_id,
            detail="CACHE not configured; revocation could not be persisted",
        )
        return
    now = int(time.time())
    try:
        await cache.set(
            "auth",
            "revoked_subject",
            node_id,
            value=str(now),
            ttl_seconds=_REVOCATION_TTL_SECONDS,
        )
    except CacheUnavailable as e:
        logger.error("subject_revocation_cache_unavailable", node_id=node_id, error=str(e))


@blueprint.route("/token", methods=["POST"])
@require_feature("sase", "auth")
async def generate_jwt_token() -> tuple[dict[str, Any], int]:
    """Generate JWT token for an authenticated node.

    Requires node_id, node_type, and api_key. Authenticates via
    cluster_manager (for headend nodes) or client_registry (for clients).

    Request body:
    {
        "node_id": "cluster-1",
        "node_type": "kubernetes_node" | "raw_compute" | "client_docker" | "client_native",
        "api_key": "secret-api-key"
    }

    Returns:
        JSON response with access_token, refresh_token, expires_in.
    """
    try:
        data = await request.get_json()

        # Validate required fields
        required_fields = {"node_id", "node_type", "api_key"}
        missing = required_fields - set(data.keys())
        if missing:
            return (
                {"error": f"Missing required fields: {', '.join(missing)}"},
                400,
            )

        node_id = data["node_id"]
        node_type = data["node_type"]
        api_key = data["api_key"]

        # Get managers from app config
        cluster_manager = current_app.config.get("CLUSTER_MANAGER")
        client_registry = current_app.config.get("CLIENT_REGISTRY")
        key_provider: KeyProvider = current_app.config.get("KEY_PROVIDER")

        if not key_provider:
            logger.error("key_provider_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        # Authenticate based on node type
        authenticated = False
        permissions = []
        metadata: dict[str, Any] = {}
        tenant_id = "default"  # Phase-2 default; will use node metadata in Phase-3
        authenticated_principal: Any = None  # Track authenticated principal for sub claim

        if node_type in ("kubernetes_node", "raw_compute"):
            # Authenticate cluster/headend nodes
            if cluster_manager:
                try:
                    cluster = await cluster_manager.authenticate_cluster(api_key)
                    if cluster and getattr(cluster, "id", None) == node_id:
                        authenticated = True
                        authenticated_principal = cluster
                        permissions = ["headend", "proxy", "wireguard"]
                        metadata = {
                            "cluster_id": (cluster.id if hasattr(cluster, "id") else str(cluster)),
                            "region": getattr(cluster, "region", "unknown"),
                            "datacenter": getattr(cluster, "datacenter", "unknown"),
                        }
                        tenant_id = cluster.tenant
                except Exception as e:
                    logger.error(
                        "cluster_authentication_failed",
                        node_id=node_id,
                        error=str(e),
                    )
            else:
                logger.warning("cluster_manager_not_configured")

        elif node_type in ("client_docker", "client_native"):
            # Authenticate client nodes
            if client_registry:
                try:
                    client = await client_registry.authenticate_client(api_key)
                    if client and getattr(client, "id", None) == node_id:
                        authenticated = True
                        authenticated_principal = client
                        permissions = ["connect", "tunnel", "route"]
                        metadata = {
                            "client_id": (client.id if hasattr(client, "id") else str(client)),
                            "client_type": getattr(client, "type", "unknown"),
                            "cluster_id": getattr(client, "cluster_id", "unknown"),
                        }
                        tenant_id = client.tenant
                except Exception as e:
                    logger.error(
                        "client_authentication_failed",
                        node_id=node_id,
                        error=str(e),
                    )
            else:
                logger.warning("client_registry_not_configured")

        if not authenticated:
            logger.warning(
                "jwt_generation_unauthorized",
                node_id=node_id,
                node_type=node_type,
            )
            return (
                {"error": "Authentication failed"},
                401,
            )

        # Build JWT claims — use authenticated principal's id, not request body
        # (defense in depth: don't trust client-supplied node_id)
        principal_id = getattr(
            authenticated_principal, "id", node_id
        )  # Fall back to node_id if no id attr

        # Build machine JWT claims (includes jti, scope, tenant)
        claims = build_machine_claims(  # nosec B106 - token_type is a JWT claim discriminator, not a credential
            sub_id=principal_id,
            node_type=node_type,
            tenant=tenant_id,
            iss="tobogganing",
            aud="tobogganing",
            token_type="access",
        )
        # Add node metadata (not part of standard machine-JWT)
        claims["node_type"] = node_type
        claims["permissions"] = " ".join(permissions)
        claims["metadata"] = metadata

        # Generate access token (1 hour default)
        try:
            access_token = await encode_access_token(claims, key_provider, ttl_hours=1)
        except ValueError as e:
            logger.error("access_token_encoding_failed", error=str(e))
            return (
                {"error": "Failed to generate token"},
                500,
            )

        # Generate refresh token (24 hours) — rebuild from machine_claims with refresh type
        refresh_claims = build_machine_claims(  # nosec B106 - token_type is a JWT claim discriminator, not a credential
            sub_id=principal_id,
            node_type=node_type,
            tenant=tenant_id,
            iss="tobogganing",
            aud="tobogganing",
            token_type="refresh",
        )
        # Add node metadata
        refresh_claims["node_type"] = node_type
        refresh_claims["permissions"] = " ".join(permissions)
        refresh_claims["metadata"] = metadata
        try:
            refresh_token = await encode_access_token(refresh_claims, key_provider, ttl_hours=24)
        except ValueError as e:
            logger.error("refresh_token_encoding_failed", error=str(e))
            return (
                {"error": "Failed to generate token"},
                500,
            )

        logger.info(
            "jwt_token_generated",
            node_id=node_id,
            node_type=node_type,
        )

        return (
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": 3600,  # 1 hour in seconds
                "token_type": "Bearer",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except ValueError as e:
        logger.error("jwt_request_validation_failed", error=str(e))
        return (
            {"error": f"Invalid request: {str(e)}"},
            400,
        )
    except Exception as e:
        logger.error("jwt_token_generation_error", error=str(e))
        return (
            {"error": "Internal server error"},
            500,
        )


@blueprint.route("/refresh", methods=["POST"])
@require_feature("sase", "auth")
async def refresh_jwt_token() -> tuple[dict[str, Any], int]:
    """Refresh JWT access token using refresh token.

    Request body:
    {
        "refresh_token": "eyJhbGc..."
    }

    Returns:
        JSON response with new access_token and expires_in.
    """
    try:
        data = await request.get_json()

        refresh_token = data.get("refresh_token")
        if not refresh_token:
            return (
                {"error": "Missing refresh_token"},
                400,
            )

        key_provider: KeyProvider = current_app.config.get("KEY_PROVIDER")
        if not key_provider:
            logger.error("key_provider_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        # Decode and validate refresh token (aud/iss must match this
        # blueprint's issuer/audience — see _decode_and_verify)
        claims = _decode_and_verify(refresh_token, key_provider)
        if not claims:
            logger.warning("refresh_token_invalid_or_expired")
            return (
                {"error": "Invalid or expired refresh token"},
                401,
            )

        # Verify this is actually a refresh token
        if claims.get("token_type") != "refresh":
            logger.warning("refresh_token_wrong_type")
            return (
                {"error": "Invalid token type"},
                401,
            )

        cache = current_app.config.get("CACHE")

        # Reject if this jti was already rotated/revoked, or the subject was
        # revoked (via /jwt/revoke) after this token was issued.
        if await _is_revoked(claims, cache):
            logger.warning("refresh_token_revoked", node_id=claims.get("sub"))
            return (
                {"error": "Invalid or expired refresh token"},
                401,
            )

        # Rotate: mint a brand-new access token AND a brand-new refresh
        # token, each with a fresh jti — never reuse the presented
        # refresh token's jti (single-use rotation).
        base_claims = {
            k: v for k, v in claims.items() if k not in ("token_type", "jti", "iat", "exp")
        }
        new_access_claims = {**base_claims, "jti": uuid.uuid4().hex}
        new_refresh_claims = {
            **base_claims,
            "jti": uuid.uuid4().hex,
            "token_type": "refresh",
        }

        try:
            new_access_token = await encode_access_token(
                new_access_claims, key_provider, ttl_hours=1
            )
            new_refresh_token = await encode_access_token(
                new_refresh_claims, key_provider, ttl_hours=24
            )
        except ValueError as e:
            logger.error("access_token_encoding_failed", error=str(e))
            return (
                {"error": "Failed to generate token"},
                500,
            )

        # Durably revoke the presented (now-superseded) refresh token's jti
        # so it cannot be replayed, even across pods/restarts.
        await _revoke_jti(claims.get("jti"), cache, exp=claims.get("exp"))

        logger.info(
            "jwt_token_refreshed",
            node_id=claims.get("sub"),
        )

        return (
            {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": 3600,
                "token_type": "Bearer",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except ValueError as e:
        logger.error("jwt_request_validation_failed", error=str(e))
        return (
            {"error": f"Invalid request: {str(e)}"},
            400,
        )
    except Exception as e:
        logger.error("jwt_refresh_error", error=str(e))
        return (
            {"error": "Internal server error"},
            500,
        )


@blueprint.route("/validate", methods=["POST"])
@require_feature("sase", "auth")
async def validate_jwt_token() -> tuple[dict[str, Any], int]:
    """Validate a JWT token and return its payload.

    Used by headend servers to validate node JWTs.

    Request header:
        Authorization: Bearer <token>

    Returns:
        JSON response with validation result and claims.
    """
    try:
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        token = _extract_bearer_token(auth_header)

        if not token:
            return (
                {"error": "Invalid authorization header"},
                401,
            )

        key_provider: KeyProvider = current_app.config.get("KEY_PROVIDER")
        if not key_provider:
            logger.error("key_provider_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        # Validate token (aud/iss must match this blueprint's issuer/audience)
        claims = _decode_and_verify(token, key_provider)

        if not claims:
            logger.warning("jwt_validation_failed_invalid_or_expired")
            return (
                {"error": "Invalid or expired token"},
                401,
            )

        # Check if token has been revoked — durable, cache-backed check
        # (shared across pods/restarts; replaces the old in-process set).
        cache = current_app.config.get("CACHE")
        if await _is_revoked(claims, cache):
            logger.warning("jwt_validation_failed_revoked", jti=claims.get("jti"))
            return (
                {"error": "Token has been revoked"},
                401,
            )

        logger.info(
            "jwt_validation_successful",
            node_id=claims.get("sub"),
        )

        return (
            {
                "valid": True,
                "node_id": claims.get("sub"),
                "node_type": claims.get("node_type"),
                "tenant": claims.get("tenant"),
                "permissions": claims.get("permissions", "").split(),
                "metadata": claims.get("metadata", {}),
                "expires_at": claims.get("exp"),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("jwt_validation_error", error=str(e))
        return (
            {"error": "Internal server error"},
            500,
        )


@blueprint.route("/revoke", methods=["POST"])
@require_tenant
@require_scope("jwt:revoke")
@require_feature("sase", "auth")
async def revoke_jwt_token() -> tuple[dict[str, Any], int]:
    """Revoke JWT token(s) for a node in the caller's tenant.

    Requires tenant claim and jwt:revoke scope.
    Only node_id-based revocation is supported; revocation of tokens
    from other tenants is rejected with 403.

    Request body:
    {
        "node_id": "cluster-1"  (revoke all tokens for node)
    }

    Returns:
        JSON response with revocation result.
    """
    try:
        claims = current_claims()
        caller_tenant = claims.get("tenant")
        if not caller_tenant:
            return (
                {"error": "Unauthorized: missing tenant claim"},
                403,
            )

        data = await request.get_json()

        if "node_id" not in data:
            return (
                {"error": "Missing node_id"},
                400,
            )

        node_id = data["node_id"]

        # Verify the node belongs to the caller's tenant
        # (lookup via cluster_manager or client_registry)
        cluster_manager = current_app.config.get("CLUSTER_MANAGER")
        client_registry = current_app.config.get("CLIENT_REGISTRY")

        node_tenant = None
        if cluster_manager:
            try:
                cluster = await cluster_manager.get_cluster(node_id)
                if cluster:
                    node_tenant = cluster.tenant
            except Exception:
                logger.debug("node_tenant_lookup_failed", node_id=node_id, exc_info=True)

        if not node_tenant and client_registry:
            try:
                client = await client_registry.get_client(node_id)
                if client:
                    node_tenant = client.tenant
            except Exception:
                logger.debug("node_tenant_lookup_failed", node_id=node_id, exc_info=True)

        # Cross-tenant revoke attempt → 403
        if node_tenant and node_tenant != caller_tenant:
            logger.warning(
                "jwt_revocation_denied_cross_tenant",
                node_id=node_id,
                caller_tenant=caller_tenant,
                node_tenant=node_tenant,
            )
            return (
                {"error": "Forbidden: cannot revoke tokens outside your tenant"},
                403,
            )

        # Durably persist the revocation via the shared cache so it is
        # enforced by _is_revoked() across pods/restarts, not just this
        # process. Best-effort: never fails the request on a cache blip.
        cache = current_app.config.get("CACHE")
        await _revoke_subject(node_id, cache)

        logger.info(
            "jwt_tokens_revoked_for_node",
            node_id=node_id,
            tenant_id=caller_tenant,
        )

        return (
            {
                "revoked": True,
                "node_id": node_id,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except ValueError as e:
        logger.error("jwt_request_validation_failed", error=str(e))
        return (
            {"error": f"Invalid request: {str(e)}"},
            400,
        )
    except Exception as e:
        logger.error("jwt_revocation_error", error=str(e), exc_info=True)
        return (
            {"error": "Internal server error"},
            500,
        )


@blueprint.route("/public-key", methods=["GET"])
@require_feature("sase", "auth")
async def get_jwt_public_key() -> tuple[dict[str, Any], int]:
    """Get the public key for JWT verification.

    Used by headend servers and clients to verify JWTs issued by the
    auth service. Returns the key in PEM format with the key ID (kid).

    Returns:
        JSON response with public_key, kid, algorithm, and use.
    """
    try:
        key_provider: KeyProvider = current_app.config.get("KEY_PROVIDER")
        if not key_provider:
            logger.error("key_provider_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        logger.info("jwt_public_key_requested")

        return (
            {
                "public_key": key_provider.public_pem,
                "kid": key_provider.kid,
                "algorithm": "RS256",
                "use": "sig",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("jwt_public_key_error", error=str(e))
        return (
            {"error": "Internal server error"},
            500,
        )
