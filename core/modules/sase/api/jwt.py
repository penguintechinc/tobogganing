"""JWT authentication blueprint for SASE module."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request, current_app

from core.auth.jwt import decode_token, encode_access_token
from core.auth.middleware import current_claims, require_scope, require_tenant
from core.crypto.keys import KeyProvider
from core.entitlements.gate import require_feature

logger = structlog.get_logger()

blueprint = Blueprint("sase_jwt", __name__, url_prefix="/jwt")

# In-memory revocation list (Phase-2 placeholder; will move to DB in Phase-3)
_REVOKED_TOKENS: set[str] = set()


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

        if node_type in ("kubernetes_node", "raw_compute"):
            # Authenticate cluster/headend nodes
            if cluster_manager:
                try:
                    cluster = await asyncio.to_thread(
                        cluster_manager.authenticate_cluster, api_key
                    )
                    if cluster:
                        authenticated = True
                        permissions = ["headend", "proxy", "wireguard"]
                        metadata = {
                            "cluster_id": cluster.id if hasattr(cluster, "id") else str(cluster),
                            "region": getattr(cluster, "region", "unknown"),
                            "datacenter": getattr(cluster, "datacenter", "unknown"),
                        }
                        tenant_id = getattr(cluster, "tenant_id", "default")
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
                    client = await asyncio.to_thread(
                        client_registry.authenticate_client, api_key
                    )
                    if client and getattr(client, "id", None) == node_id:
                        authenticated = True
                        permissions = ["connect", "tunnel", "route"]
                        metadata = {
                            "client_id": client.id if hasattr(client, "id") else str(client),
                            "client_type": getattr(client, "type", "unknown"),
                            "cluster_id": getattr(client, "cluster_id", "unknown"),
                        }
                        tenant_id = getattr(client, "tenant_id", "default")
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

        # Build JWT claims with tenant-first
        claims = {
            "sub": node_id,
            "iss": "tobogganing",
            "aud": "tobogganing",
            "tenant": tenant_id,
            "node_type": node_type,
            "permissions": " ".join(permissions),
            "scope": " ".join(permissions),
            "metadata": metadata,
        }

        # Generate access token (1 hour default)
        try:
            access_token = encode_access_token(
                claims, key_provider, ttl_hours=1
            )
        except ValueError as e:
            logger.error("access_token_encoding_failed", error=str(e))
            return (
                {"error": "Failed to generate token"},
                500,
            )

        # Generate refresh token (24 hours; Phase-2 uses JWT; Phase-3 will use DB)
        refresh_claims = claims.copy()
        refresh_claims["token_type"] = "refresh"
        try:
            refresh_token = encode_access_token(
                refresh_claims, key_provider, ttl_hours=24
            )
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

        # Decode and validate refresh token
        claims = decode_token(refresh_token, key_provider)
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

        # Generate new access token with same claims
        access_claims = {
            k: v
            for k, v in claims.items()
            if k != "token_type"
        }

        try:
            new_access_token = encode_access_token(
                access_claims, key_provider, ttl_hours=1
            )
        except ValueError as e:
            logger.error("access_token_encoding_failed", error=str(e))
            return (
                {"error": "Failed to generate token"},
                500,
            )

        logger.info(
            "jwt_token_refreshed",
            node_id=claims.get("sub"),
        )

        return (
            {
                "access_token": new_access_token,
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

        # Validate token
        claims = decode_token(token, key_provider)

        if not claims:
            logger.warning("jwt_validation_failed_invalid_or_expired")
            return (
                {"error": "Invalid or expired token"},
                401,
            )

        # Check if token has been revoked (Phase-2 in-memory check)
        token_jti = claims.get("jti", token[:32])
        if token_jti in _REVOKED_TOKENS:
            logger.warning("jwt_validation_failed_revoked", jti=token_jti)
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
                cluster = await asyncio.to_thread(
                    cluster_manager.get_cluster, node_id
                )
                if cluster:
                    node_tenant = getattr(cluster, "tenant_id", "default")
            except Exception:
                pass

        if not node_tenant and client_registry:
            try:
                client = await asyncio.to_thread(
                    client_registry.get_client, node_id
                )
                if client:
                    node_tenant = getattr(client, "tenant_id", "default")
            except Exception:
                pass

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
