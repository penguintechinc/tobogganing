"""Headend policy endpoints (firewall rules, port config).

These endpoints are called by the Go hub-router headend service to fetch
firewall rules and port configurations. They are NOT part of the module system
and run at the app level to bypass tenant/module prefixing.

Auth: Bearer token validated against HEADEND_API_TOKEN environment variable.
"""

from __future__ import annotations

import asyncio
import hmac
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, current_app, request

from core.auth.jwt import decode_token, encode_access_token
from core.auth.middleware import current_claims, require_scope, require_tenant
from core.crypto.keys import KeyProvider
from core.db import get_db
from core.modules.sase.auth.user_manager import UserManager
from core.modules.sase.certs.certificate_manager import CertificateManager
from core.modules.sase.firewall.access_control import AccessControlManager
from core.modules.sase.network.port_manager import PortConfigManager
from core.modules.sase.orchestrator.cluster_manager import ClusterManager

logger = structlog.get_logger()

# App-level blueprint; registered with url_prefix='/api/v1' in app.py
# This keeps headend endpoints at EXACT flat paths
# (e.g., /api/v1/firewall/rules, NOT /api/v1/sase/firewall/rules)
headend_bp = Blueprint("headend", __name__, url_prefix="")


def _verify_headend_token(token: str | None) -> bool:
    """Verify headend API token using constant-time comparison.

    Args:
        token: The Bearer token to verify.

    Returns:
        True if token matches HEADEND_API_TOKEN, False otherwise.
    """
    expected = os.getenv("HEADEND_API_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


def _extract_bearer_token() -> str | None:
    """Extract Bearer token from Authorization header.

    Returns:
        Token string if present, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]


def _extract_bearer_token_from_header(auth_header: str) -> str | None:
    """Extract Bearer token from Authorization header string.

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


def get_access_control_manager(db: Any) -> AccessControlManager:
    """Get access control manager instance.

    Args:
        db: penguin-dal DAL instance.

    Returns:
        AccessControlManager bound to the database.
    """
    return AccessControlManager(db)


def get_user_manager(db: Any) -> UserManager:
    """Get user manager instance.

    Args:
        db: penguin-dal DAL instance.

    Returns:
        UserManager bound to the database.
    """
    return UserManager(db)


def get_port_config_manager(db: Any) -> PortConfigManager:
    """Get port config manager instance.

    Args:
        db: penguin-dal DAL instance.

    Returns:
        PortConfigManager bound to the database.
    """
    return PortConfigManager(db)


def get_certificate_manager(
    cert_mgr: CertificateManager | None,
) -> CertificateManager | None:
    """Get certificate manager instance from app config.

    Args:
        cert_mgr: CertificateManager from app config.

    Returns:
        CertificateManager or None if not configured.
    """
    return cert_mgr


@headend_bp.route("/firewall/rules", methods=["GET"])
async def get_firewall_rules() -> tuple[dict[str, Any], int]:
    """Get all firewall rules for headend consumption.

    Requires headend authentication via Bearer token (HEADEND_API_TOKEN).
    Returns rules for all active users across all tenants.

    Returns:
        - 200: {timestamp, rules_count, user_rules: {user_id: [rules]}}
        - 401: {error: "..."} if auth fails
        - 500: {error: "..."} on server error
    """
    try:
        # Authenticate headend
        token = _extract_bearer_token()
        if not _verify_headend_token(token):
            return {"error": "Unauthorized: invalid headend token"}, 401

        db = get_db()
        if db is None:
            return {"error": "Database unavailable"}, 500

        # Get managers
        acm = get_access_control_manager(db)
        um = get_user_manager(db)

        # Note: In a true multi-tenant setup, iterate all tenant configs
        # For now, use default tenant (headend clients can provide via env)
        tenant = "default"

        # Get all active users in the default tenant
        users = await um.list_users(tenant)
        all_rules: dict[str, Any] = {}

        # Export rules for each active user
        for user in users:
            if user.is_active:
                try:
                    user_rules = await acm.export_user_rules(user.id, tenant)
                    all_rules[user.id] = user_rules
                except Exception as e:
                    logger.warning(
                        "failed_to_export_user_rules",
                        user_id=user.id,
                        error=str(e),
                    )
                    # Continue with other users on partial failure

        response = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rules_count": len(all_rules),
            "user_rules": all_rules,
        }

        logger.info("firewall_rules_served", rules_count=len(all_rules))
        return response, 200

    except Exception as e:
        logger.error("firewall_rules_error", error=str(e))
        return {"error": "Failed to get firewall rules"}, 500


@headend_bp.route("/wireguard/peers", methods=["GET"])
async def get_wireguard_peers() -> tuple[dict[str, Any], int]:
    """Get all WireGuard peer configurations for headend consumption.

    Requires headend authentication via Bearer token (HEADEND_API_TOKEN).
    Returns peer configurations for the default tenant.

    Returns:
        - 200: {peers: [...], total: N, meta: {...}}
        - 401: {error: "..."} if auth fails
        - 500: {error: "..."} on server error
    """
    try:
        # Authenticate headend
        token = _extract_bearer_token()
        if not _verify_headend_token(token):
            return {"error": "Unauthorized: invalid headend token"}, 401

        # Get certificate manager from app config
        cert_manager: CertificateManager | None = current_app.config.get("CERT_MANAGER")
        if not cert_manager:
            logger.error("cert_manager_not_configured")
            return {"error": "Internal server error"}, 500

        # Get all WireGuard peers for default tenant
        # (headend operates at the cluster level, not tenant-scoped)
        tenant = "default"
        try:
            peers = await cert_manager.get_all_wireguard_peers(tenant_id=tenant)
        except Exception as e:
            logger.error(
                "wireguard_peers_fetch_failed",
                tenant_id=tenant,
                error=str(e),
            )
            return {"error": "Failed to fetch peers"}, 500

        logger.info(
            "wireguard_peers_fetched",
            peer_count=len(peers),
            tenant_id=tenant,
        )

        return (
            {
                "peers": peers,
                "total": len(peers),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("wireguard_peers_error", error=str(e))
        return {"error": "Internal server error"}, 500


@headend_bp.route("/auth/public-key", methods=["GET"])
async def get_auth_public_key() -> tuple[dict[str, Any], int]:
    """Get the public key for JWT verification.

    Used by headend servers and clients to verify JWTs issued by the auth service.
    Returns the key in PEM format with the key ID (kid).

    This endpoint is PUBLIC (no authentication required) because headends need
    the key before they can authenticate.

    Returns:
        - 200: {public_key: "...", kid: "...", algorithm: "RS256", ...}
        - 500: {error: "..."} on server error
    """
    try:
        key_provider: KeyProvider | None = current_app.config.get("KEY_PROVIDER")
        if not key_provider:
            logger.error("key_provider_not_configured")
            return {"error": "Internal server error"}, 500

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
        return {"error": "Internal server error"}, 500


@headend_bp.route("/auth/token", methods=["POST"])
async def issue_auth_token() -> tuple[dict[str, Any], int]:
    """Issue JWT token for an authenticated cluster/client node.

    This is the FLAT equivalent of `/api/v1/sase/jwt/token`.
    Used by Go hub-router to obtain initial JWT after registration.

    Requires node_id, node_type, and api_key in request body.
    Does NOT require a pre-existing JWT (caller has none yet).

    Request body:
    {
        "node_id": "cluster-1",
        "node_type": "kubernetes_node" | "raw_compute" | "client_docker" | "client_native",
        "api_key": "secret-api-key"
    }

    Returns:
        - 200: {access_token, refresh_token, expires_in, token_type, meta}
        - 400: {error: "..."} if validation fails
        - 401: {error: "..."} if authentication fails
        - 500: {error: "..."} on server error
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
        key_provider: KeyProvider | None = current_app.config.get("KEY_PROVIDER")

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
        tenant_id = "default"

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
                            "cluster_id": (
                                cluster.id if hasattr(cluster, "id") else str(cluster)
                            ),
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
                            "client_id": (
                                client.id if hasattr(client, "id") else str(client)
                            ),
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

        # Build JWT claims
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

        # Generate access token (1 hour)
        try:
            access_token = await encode_access_token(claims, key_provider, ttl_hours=1)
        except ValueError as e:
            logger.error("access_token_encoding_failed", error=str(e))
            return (
                {"error": "Failed to generate token"},
                500,
            )

        # Generate refresh token (24 hours)
        refresh_claims = claims.copy()
        refresh_claims["token_type"] = "refresh"
        try:
            refresh_token = await encode_access_token(
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
        logger.error("jwt_token_generation_error", error=str(e))
        return (
            {"error": "Internal server error"},
            500,
        )


@headend_bp.route("/auth/refresh", methods=["POST"])
async def refresh_auth_token() -> tuple[dict[str, Any], int]:
    """Refresh JWT access token using refresh token.

    This is the FLAT equivalent of `/api/v1/sase/jwt/refresh`.
    Does NOT require a pre-existing JWT (uses refresh_token for auth).

    Request body:
    {
        "refresh_token": "eyJhbGc..."
    }

    Returns:
        - 200: {access_token, expires_in, token_type, meta}
        - 400: {error: "..."} if validation fails
        - 401: {error: "..."} if token is invalid/expired
        - 500: {error: "..."} on server error
    """
    try:
        data = await request.get_json()

        refresh_token = data.get("refresh_token")
        if not refresh_token:
            return (
                {"error": "Missing refresh_token"},
                400,
            )

        key_provider: KeyProvider | None = current_app.config.get("KEY_PROVIDER")
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
        access_claims = {k: v for k, v in claims.items() if k != "token_type"}

        try:
            new_access_token = await encode_access_token(
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


@headend_bp.route("/clusters/", methods=["GET"])
@require_tenant
@require_scope("clusters:read")
async def list_clusters_flat() -> tuple[dict[str, Any], int]:
    """List all clusters for the tenant.

    This is the FLAT equivalent of `/api/v1/sase/clusters/` (GET).
    Used by Go hub-router to enumerate clusters for policy sync.

    Requires valid JWT with clusters:read scope.

    Returns:
        - 200: {clusters: [...], meta: {...}}
        - 403: {error: "..."} if auth fails
        - 500: {error: "..."} on server error
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        if db is None:
            return {"error": "Database unavailable"}, 500

        mgr = ClusterManager(db, tenant_id)
        await mgr.initialize()

        clusters = await mgr.get_all_clusters()

        cluster_list = [
            {
                "id": c.id,
                "name": c.name,
                "region": c.region,
                "datacenter": c.datacenter,
                "status": c.status,
                "client_count": c.client_count,
            }
            for c in clusters
        ]

        logger.info(
            "clusters_listed",
            count=len(cluster_list),
            tenant=tenant_id,
        )

        return (
            {
                "clusters": cluster_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_clusters_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@headend_bp.route("/auth/validate", methods=["POST"])
async def validate_auth_token() -> tuple[dict[str, Any], int]:
    """Validate a JWT token and return its payload.

    Used by headend servers to validate node JWTs issued by the auth service.
    Requires the JWT in the Authorization header (the token to validate).

    Request header:
        Authorization: Bearer <token>

    Returns:
        - 200: {valid: True, node_id: "...", tenant: "...", ...}
        - 401: {error: "..."} if token is invalid
        - 500: {error: "..."} on server error
    """
    try:
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        token = _extract_bearer_token_from_header(auth_header)

        if not token:
            logger.warning("auth_validate_no_token")
            return {"error": "Invalid authorization header"}, 401

        key_provider: KeyProvider | None = current_app.config.get("KEY_PROVIDER")
        if not key_provider:
            logger.error("key_provider_not_configured")
            return {"error": "Internal server error"}, 500

        # Validate token
        claims = decode_token(token, key_provider)

        if not claims:
            logger.warning("auth_validate_invalid_or_expired")
            return {"error": "Invalid or expired token"}, 401

        logger.info(
            "auth_validate_successful",
            node_id=claims.get("sub"),
        )

        return (
            {
                "valid": True,
                "node_id": claims.get("sub"),
                "node_type": claims.get("node_type"),
                "tenant": claims.get("tenant"),
                "permissions": (
                    claims.get("permissions", "").split()
                    if claims.get("permissions")
                    else []
                ),
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
        logger.error("auth_validate_error", error=str(e))
        return {"error": "Internal server error"}, 500


@headend_bp.route("/headend/<headend_id>/ports", methods=["GET"])
async def get_headend_ports(headend_id: str) -> tuple[dict[str, Any], int]:
    """Get port configuration for a specific headend.

    Requires headend authentication via Bearer token (HEADEND_API_TOKEN).
    Optional query param: cluster_id (defaults to "cluster-{headend_id}").

    Args:
        headend_id: ID of the headend.

    Returns:
        - 200: {headend_id, cluster_id, tcp_ranges, udp_ranges, ...}
        - 401: {error: "..."} if auth fails
        - 404: {error: "..."} if no config found
        - 500: {error: "..."} on server error
    """
    try:
        # Authenticate headend
        token = _extract_bearer_token()
        if not _verify_headend_token(token):
            return {"error": "Unauthorized: invalid headend token"}, 401

        db = get_db()
        if db is None:
            return {"error": "Database unavailable"}, 500

        # Get tenant and cluster from query params
        # Note: tenant should be derived from headend config in multi-tenant
        # For now, use default tenant
        tenant = request.args.get("tenant", "default")
        cluster_id = request.args.get("cluster_id", f"cluster-{headend_id}")

        pcm = get_port_config_manager(db)
        config = await pcm.get_headend_config(headend_id, tenant)

        if not config:
            logger.warning(
                "headend_config_not_found",
                headend_id=headend_id,
                cluster_id=cluster_id,
                tenant=tenant,
            )
            return {"error": "No port configuration found"}, 404

        # Build response matching py4web contract
        tcp_ranges_str = _get_tcp_ranges_string(config.tcp_ranges)
        udp_ranges_str = _get_udp_ranges_string(config.udp_ranges)
        tcp_detail = [_port_range_to_dict(pr) for pr in config.tcp_ranges]
        udp_detail = [_port_range_to_dict(pr) for pr in config.udp_ranges]
        updated_at = config.updated_at.isoformat() if config.updated_at else None

        response = {
            "headend_id": config.headend_id,
            "cluster_id": config.cluster_id,
            "tcp_ranges": tcp_ranges_str,
            "udp_ranges": udp_ranges_str,
            "tcp_ranges_detail": tcp_detail,
            "udp_ranges_detail": udp_detail,
            "updated_at": updated_at,
        }

        logger.info(
            "headend_ports_served",
            headend_id=headend_id,
            cluster_id=cluster_id,
            tcp_count=len(config.tcp_ranges),
            udp_count=len(config.udp_ranges),
        )
        return response, 200

    except Exception as e:
        logger.error(
            "headend_ports_error",
            headend_id=headend_id,
            error=str(e),
        )
        return {"error": "Failed to get port configuration"}, 500


def _get_tcp_ranges_string(ranges: list[Any]) -> str:
    """Convert TCP port ranges to comma-separated string.

    Args:
        ranges: List of PortRangeConfig objects.

    Returns:
        Comma-separated string like "80,443-8000,8443" or empty string.
    """
    if not ranges:
        return ""
    parts = []
    for r in ranges:
        if r.start_port == r.end_port:
            parts.append(str(r.start_port))
        else:
            parts.append(f"{r.start_port}-{r.end_port}")
    return ",".join(parts)


def _get_udp_ranges_string(ranges: list[Any]) -> str:
    """Convert UDP port ranges to comma-separated string.

    Args:
        ranges: List of PortRangeConfig objects.

    Returns:
        Comma-separated string like "53,5353-5400" or empty string.
    """
    if not ranges:
        return ""
    parts = []
    for r in ranges:
        if r.start_port == r.end_port:
            parts.append(str(r.start_port))
        else:
            parts.append(f"{r.start_port}-{r.end_port}")
    return ",".join(parts)


def _port_range_to_dict(port_range: Any) -> dict[str, Any]:
    """Convert PortRangeConfig to dictionary.

    Args:
        port_range: PortRangeConfig object.

    Returns:
        Dictionary representation of the port range.
    """
    return {
        "id": port_range.id,
        "start_port": port_range.start_port,
        "end_port": port_range.end_port,
        "protocol": port_range.protocol.value,
        "description": port_range.description,
        "enabled": port_range.enabled,
        "created_at": port_range.created_at.isoformat(),
        "updated_at": port_range.updated_at.isoformat(),
    }
