"""External Identity Provider manager — OIDC/SAML/SCIM token exchange.

Converts external IdP tokens into uniform Tobogganing JWTs by:
  1. Loading the provider record from the identity_providers table.
  2. Validating the external token via the appropriate adapter.
  3. Mapping external claims to tenant/team/role/scope using identity_mappings.
  4. Minting a fresh Tobogganing JWT via JWTManager.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import structlog
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.backends import default_backend
import base64

from database import get_db

logger = structlog.get_logger()

_DEFAULT_TENANT = "default"
_DEFAULT_ROLE = "viewer"
_DEFAULT_SCOPES: list[str] = ["read"]
_JWKS_TTL = 3600  # seconds


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ExternalIdentityClaims:
    """Unified representation of claims from any external IdP."""

    subject: str
    email: str
    name: str
    groups: list[str]
    raw_claims: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal JWKS cache entry
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _JWKSCacheEntry:
    keys: dict  # kid -> public key object
    fetched_at: float


# ---------------------------------------------------------------------------
# OIDC adapter
# ---------------------------------------------------------------------------

class OIDCAdapter:
    """Validates tokens from external OIDC providers using discovery + JWKS."""

    def __init__(self, provider_config: dict) -> None:
        self._issuer_url: str = provider_config["issuer_url"].rstrip("/")
        self._client_id: str = provider_config["client_id"]
        self._client_secret: str = provider_config.get("client_secret", "")
        self._audience: str = provider_config.get("audience", self._client_id)
        self._jwks_cache: _JWKSCacheEntry | None = None

    async def _fetch_discovery(self, client: httpx.AsyncClient) -> dict:
        url = f"{self._issuer_url}/.well-known/openid-configuration"
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()

    async def _get_jwks(self, client: httpx.AsyncClient) -> dict:
        now = time.monotonic()
        if (
            self._jwks_cache is not None
            and (now - self._jwks_cache.fetched_at) < _JWKS_TTL
        ):
            return self._jwks_cache.keys

        discovery = await self._fetch_discovery(client)
        jwks_uri: str = discovery["jwks_uri"]

        resp = await client.get(jwks_uri, timeout=10.0)
        resp.raise_for_status()
        raw_keys: list[dict] = resp.json().get("keys", [])

        keys: dict[str, Any] = {}
        for k in raw_keys:
            if k.get("kty") != "RSA":
                continue
            kid = k.get("kid", "default")
            try:
                n_int = int.from_bytes(
                    base64.urlsafe_b64decode(_pad_b64(k["n"])), "big"
                )
                e_int = int.from_bytes(
                    base64.urlsafe_b64decode(_pad_b64(k["e"])), "big"
                )
                pub_key = RSAPublicNumbers(e_int, n_int).public_key(default_backend())
                keys[kid] = pub_key
            except Exception as exc:
                logger.warning("oidc_jwks_key_parse_failed", kid=kid, error=str(exc))

        self._jwks_cache = _JWKSCacheEntry(keys=keys, fetched_at=now)
        logger.debug("oidc_jwks_refreshed", issuer=self._issuer_url, key_count=len(keys))
        return keys

    async def validate_token(self, token: str) -> ExternalIdentityClaims:
        """Validate an OIDC bearer token and return normalised claims.

        Raises:
            ValueError: On signature failure, expiry, issuer/audience mismatch,
                        or unreachable discovery endpoint.
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise ValueError(f"Malformed OIDC token: {exc}") from exc

        kid = header.get("kid", "default")
        alg = header.get("alg", "RS256")

        async with httpx.AsyncClient() as client:
            keys = await self._get_jwks(client)

        if not keys:
            raise ValueError(f"No JWKS keys available for issuer {self._issuer_url}")

        pub_key = keys.get(kid) or next(iter(keys.values()), None)
        if pub_key is None:
            raise ValueError(f"No matching JWKS key for kid={kid}")

        try:
            payload: dict = jwt.decode(
                token,
                pub_key,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer_url,
            )
        except jwt.ExpiredSignatureError as exc:
            raise ValueError("OIDC token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise ValueError(f"OIDC token invalid: {exc}") from exc

        subject = payload.get("sub", "")
        email = payload.get("email", "")
        name = payload.get("name", payload.get("preferred_username", ""))
        groups: list[str] = payload.get("groups", payload.get("roles", []))
        if isinstance(groups, str):
            groups = [groups]

        logger.info(
            "oidc_token_validated",
            subject=subject,
            issuer=self._issuer_url,
        )
        return ExternalIdentityClaims(
            subject=subject,
            email=email,
            name=name,
            groups=groups,
            raw_claims=payload,
        )


# ---------------------------------------------------------------------------
# SAML adapter (placeholder — premium)
# ---------------------------------------------------------------------------

class SAMLAdapter:
    """Placeholder for SAML assertion validation (premium feature)."""

    def __init__(self, provider_config: dict) -> None:
        self._metadata_url: str = provider_config.get("metadata_url", "")
        self._entity_id: str = provider_config.get("entity_id", "")
        self._certificate: str = provider_config.get("certificate", "")

    async def validate_assertion(self, saml_response: str) -> ExternalIdentityClaims:
        raise NotImplementedError("SAML support requires premium license")


# ---------------------------------------------------------------------------
# SCIM adapter (placeholder — premium)
# ---------------------------------------------------------------------------

class SCIMAdapter:
    """Placeholder for SCIM provisioning (premium feature)."""

    def __init__(self, provider_config: dict) -> None:
        self._base_url: str = provider_config.get("base_url", "")
        self._bearer_token: str = provider_config.get("bearer_token", "")

    async def sync_users(self) -> list[ExternalIdentityClaims]:
        raise NotImplementedError("SCIM support requires premium license")


# ---------------------------------------------------------------------------
# IdP Manager
# ---------------------------------------------------------------------------

class IdPManager:
    """Orchestrates external IdP token exchange → Tobogganing JWT."""

    def __init__(self) -> None:
        self._jwt_manager: Any = None  # lazy init

    def _get_jwt_manager(self) -> Any:
        if self._jwt_manager is None:
            from auth.jwt_manager import JWTManager  # noqa: PLC0415
            self._jwt_manager = JWTManager()
        return self._jwt_manager

    async def get_provider_adapter(
        self, provider_id: str
    ) -> OIDCAdapter | SAMLAdapter | SCIMAdapter:
        """Load an IdP record from DB and return the matching adapter.

        Args:
            provider_id: The ``id`` of the identity_providers row (as string).

        Raises:
            ValueError: If provider not found, disabled, or unknown type.
        """
        db = get_db()
        row = db(
            (db.identity_providers.id == int(provider_id))
            & (db.identity_providers.enabled == True)  # noqa: E712
        ).select(
            db.identity_providers.provider_type,
            db.identity_providers.config,
        ).first()

        if row is None:
            raise ValueError(f"Identity provider {provider_id!r} not found or disabled")

        provider_type: str = row.provider_type
        config: dict = row.config or {}

        if provider_type == "oidc":
            return OIDCAdapter(config)
        if provider_type == "saml":
            return SAMLAdapter(config)
        if provider_type == "scim":
            return SCIMAdapter(config)

        raise ValueError(f"Unknown provider_type: {provider_type!r}")

    async def map_external_claims(
        self,
        claims: ExternalIdentityClaims,
        provider_id: str,
    ) -> tuple[str, list[str], list[str], list[str]]:
        """Map external claims to (tenant, teams, roles, scopes).

        Lookup order:
          1. Exact match on (provider_type, subject) in identity_mappings.
          2. Group-based match for each group in claims.groups.
          3. Fall back to default tenant + viewer role.

        Returns:
            Tuple of (tenant_id, teams, roles, scopes).
        """
        db = get_db()

        prov_row = db(db.identity_providers.id == int(provider_id)).select(
            db.identity_providers.provider_type,
            db.identity_providers.tenant_id,
        ).first()

        provider_type = prov_row.provider_type if prov_row else "oidc"
        fallback_tenant = prov_row.tenant_id if prov_row else _DEFAULT_TENANT

        # 1. Subject-level mapping
        mapping = db(
            (db.identity_mappings.provider_type == provider_type)
            & (db.identity_mappings.external_id == claims.subject)
        ).select(
            db.identity_mappings.tenant_id,
            db.identity_mappings.team_id,
            db.identity_mappings.scopes,
        ).first()

        if mapping:
            return _extract_mapping(mapping, fallback_tenant)

        # 2. Group-based mappings — collect all matches, merge scopes
        if claims.groups:
            group_rows = db(
                (db.identity_mappings.provider_type == provider_type)
                & (db.identity_mappings.external_id.belongs(claims.groups))
            ).select(
                db.identity_mappings.tenant_id,
                db.identity_mappings.team_id,
                db.identity_mappings.scopes,
            )

            if group_rows:
                tenant = group_rows[0].tenant_id or fallback_tenant
                teams: list[str] = []
                scopes: list[str] = []
                for r in group_rows:
                    if r.team_id:
                        teams.append(r.team_id)
                    row_scopes = r.scopes or []
                    if isinstance(row_scopes, str):
                        row_scopes = [row_scopes]
                    scopes.extend(s for s in row_scopes if s not in scopes)
                roles = _roles_from_scopes(scopes)
                logger.info(
                    "idp_group_mapping_resolved",
                    subject=claims.subject,
                    group_count=len(claims.groups),
                    teams=teams,
                )
                return tenant, teams, roles, scopes

        # 3. Default fallback
        logger.info(
            "idp_mapping_fallback",
            subject=claims.subject,
            tenant=fallback_tenant,
        )
        return fallback_tenant, [], [_DEFAULT_ROLE], list(_DEFAULT_SCOPES)

    async def exchange_token(
        self, external_token: str, provider_id: str
    ) -> dict:
        """Validate an external IdP token and mint a Tobogganing JWT.

        Args:
            external_token: Raw bearer token from the external IdP.
            provider_id:    Identity provider row id.

        Returns:
            Dict with access_token, refresh_token, expires_at, token_type.

        Raises:
            ValueError:          On token validation failure.
            NotImplementedError: For SAML/SCIM premium stubs.
        """
        adapter = await self.get_provider_adapter(provider_id)

        if not isinstance(adapter, OIDCAdapter):
            raise NotImplementedError(
                f"Token exchange is only supported for OIDC providers; "
                f"got {type(adapter).__name__}"
            )

        claims = await adapter.validate_token(external_token)

        tenant, teams, roles, scopes = await self.map_external_claims(claims, provider_id)

        jwt_manager = self._get_jwt_manager()
        tokens = await jwt_manager.generate_token(
            subject=claims.subject,
            tenant=tenant,
            teams=teams,
            roles=roles,
            scopes=scopes,
        )

        logger.info(
            "idp_token_exchanged",
            subject=claims.subject,
            provider_id=provider_id,
            tenant=tenant,
            roles=roles,
        )
        return tokens


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _pad_b64(s: str) -> str:
    """Add Base64 padding so standard decoder does not choke."""
    return s + "=" * (-len(s) % 4)


def _extract_mapping(
    row: Any, fallback_tenant: str
) -> tuple[str, list[str], list[str], list[str]]:
    tenant = row.tenant_id or fallback_tenant
    teams: list[str] = [row.team_id] if row.team_id else []
    scopes: list[str] = row.scopes or list(_DEFAULT_SCOPES)
    if isinstance(scopes, str):
        scopes = [scopes]
    roles = _roles_from_scopes(scopes)
    return tenant, teams, roles, scopes


def _roles_from_scopes(scopes: list[str]) -> list[str]:
    """Derive a role list from scope grants (heuristic fallback)."""
    if "admin" in scopes or "write:admin" in scopes:
        return ["admin"]
    if any(s.startswith("write:") for s in scopes) or "write" in scopes:
        return ["maintainer"]
    return [_DEFAULT_ROLE]
