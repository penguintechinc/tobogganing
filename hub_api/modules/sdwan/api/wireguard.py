"""WireGuard key management blueprint for SASE module."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, current_app, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.core import CertificateManager
from hub_api.entitlements.gate import require_feature
from hub_api.modules.sdwan.certs import WireGuardKeyManager

logger = structlog.get_logger()

blueprint = Blueprint("sase_wireguard", __name__, url_prefix="/wireguard")


@dataclass(slots=True)
class WireGuardKeysRequest:
    """Request to generate WireGuard keys."""

    node_id: str
    node_type: str
    api_key: str


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


@blueprint.route("/keys", methods=["POST"])
@require_tenant
@require_scope("wireguard:write")
@require_feature("sase", "wireguard")
async def generate_wireguard_keys() -> tuple[dict[str, Any], int]:
    """Generate WireGuard keys and certificates for authenticated nodes.

    Requires tenant claim (for authorization) and node authentication via
    cluster_manager (for headend/cluster nodes) or client_registry (for clients).

    Request body:
    {
        "node_id": "cluster-1",
        "node_type": "kubernetes_node" | "raw_compute" | "headend" | "client_docker" | "client_native",
        "api_key": "secret-api-key"
    }

    Returns:
        JSON response with WireGuard keys, IP address, and X.509 certificate.
    """
    try:
        claims = current_claims()
        if not claims or "tenant" not in claims:
            logger.warning("wireguard_keys_generation_no_tenant")
            return (
                {"error": "Unauthorized: missing tenant claim"},
                403,
            )

        tenant_id = claims["tenant"]

        # Parse request body
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
        wg_manager: WireGuardKeyManager = current_app.config.get("WIREGUARD_MANAGER")
        pki_manager: CertificateManager = current_app.config.get("CERT_MANAGER")

        if not wg_manager or not pki_manager:
            logger.error("wg_manager_or_pki_manager_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        # Authenticate based on node type
        authenticated = False

        if node_type in ("kubernetes_node", "raw_compute", "headend"):
            # Authenticate cluster/headend nodes
            if cluster_manager:
                try:
                    cluster = await asyncio.to_thread(cluster_manager.authenticate_cluster, api_key)
                    authenticated = (
                        cluster is not None
                        and getattr(cluster, "id", None) == node_id
                        and getattr(cluster, "tenant", None) == tenant_id
                    )
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
                    client = await asyncio.to_thread(client_registry.authenticate_client, api_key)
                    authenticated = (
                        client is not None
                        and getattr(client, "id", None) == node_id
                        and getattr(client, "tenant", None) == tenant_id
                    )
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
                "wireguard_keys_generation_unauthorized",
                node_id=node_id,
                node_type=node_type,
                tenant_id=tenant_id,
            )
            return (
                {"error": "Authentication failed"},
                401,
            )

        # Generate WireGuard keys
        try:
            wg_config = await wg_manager.generate_wireguard_keys(
                node_id, node_type, tenant_id=tenant_id
            )
        except Exception as e:
            logger.error(
                "wireguard_keys_generation_failed",
                node_id=node_id,
                error=str(e),
            )
            return (
                {"error": "Failed to generate WireGuard keys"},
                500,
            )

        # Generate X.509 certificate for WireGuard authentication
        try:
            if node_type in ("headend", "kubernetes_node", "raw_compute"):
                cert_key, cert_pem, ca_cert = await pki_manager.generate_headend_certificate(
                    node_id,
                    f"{node_type}-{node_id}",
                    [wg_config["ip_address"]],
                )
            else:
                cert_key, cert_pem, ca_cert = await pki_manager.generate_client_certificate(
                    node_id,
                    f"{node_type}-{node_id}",
                    node_type,
                )
        except Exception as e:
            logger.error(
                "certificate_generation_failed",
                node_id=node_id,
                error=str(e),
            )
            return (
                {"error": "Failed to generate certificate"},
                500,
            )

        logger.info(
            "wireguard_keys_generated",
            node_id=node_id,
            node_type=node_type,
            tenant_id=tenant_id,
        )

        return (
            {
                "node_id": node_id,
                "wireguard": {
                    "private_key": wg_config["private_key"],
                    "public_key": wg_config["public_key"],
                    "ip_address": wg_config["ip_address"],
                },
                "certificates": {
                    "private_key": cert_key,
                    "certificate": cert_pem,
                    "ca_certificate": ca_cert,
                },
                "authentication_note": "WireGuard requires both certificate AND JWT/SSO authentication",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except ValueError as e:
        logger.error("wireguard_request_validation_failed", error=str(e))
        return (
            {"error": f"Invalid request: {str(e)}"},
            400,
        )
    except Exception as e:
        logger.error("wireguard_keys_generation_error", error=str(e))
        return (
            {"error": "Internal server error"},
            500,
        )


@blueprint.route("/peers", methods=["GET"])
@require_tenant
@require_scope("wireguard:read")
@require_feature("sase", "wireguard")
async def get_wireguard_peers() -> tuple[dict[str, Any], int]:
    """Get all WireGuard peer configurations.

    Used by headend servers to fetch the current peer list for
    configuring WireGuard interfaces.

    Requires tenant claim and valid Bearer token.

    Returns:
        JSON response with list of peers (node_id, public_key, ip_address).
    """
    try:
        claims = current_claims()
        if not claims or "tenant" not in claims:
            logger.warning("wireguard_peers_request_no_tenant")
            return (
                {"error": "Unauthorized: missing tenant claim"},
                403,
            )

        tenant_id = claims["tenant"]

        # Get WireGuard manager
        wg_manager: WireGuardKeyManager = current_app.config.get("WIREGUARD_MANAGER")
        if not wg_manager:
            logger.error("wg_manager_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        # Get all WireGuard peers for this tenant
        try:
            peers = await wg_manager.get_all_wireguard_peers(tenant_id=tenant_id)
        except Exception as e:
            logger.error(
                "wireguard_peers_fetch_failed",
                tenant_id=tenant_id,
                error=str(e),
            )
            return (
                {"error": "Failed to fetch peers"},
                500,
            )

        logger.info(
            "wireguard_peers_fetched",
            peer_count=len(peers),
            tenant_id=tenant_id,
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
        return (
            {"error": "Internal server error"},
            500,
        )


@blueprint.route("/keys/<node_id>", methods=["DELETE"])
@require_tenant
@require_scope("wireguard:write")
@require_feature("sase", "wireguard")
async def revoke_wireguard_keys(node_id: str) -> tuple[dict[str, Any], int]:
    """Revoke WireGuard keys for a specific node.

    Requires tenant claim and valid Bearer token.

    Path parameter:
        node_id: Node identifier to revoke.

    Returns:
        JSON response indicating success or failure.
    """
    try:
        claims = current_claims()
        if not claims or "tenant" not in claims:
            logger.warning("wireguard_keys_revocation_no_tenant")
            return (
                {"error": "Unauthorized: missing tenant claim"},
                403,
            )

        tenant_id = claims["tenant"]

        # Get WireGuard manager
        wg_manager: WireGuardKeyManager = current_app.config.get("WIREGUARD_MANAGER")
        if not wg_manager:
            logger.error("wg_manager_not_configured")
            return (
                {"error": "Internal server error"},
                500,
            )

        # Revoke WireGuard keys (tenant-scoped)
        try:
            success = await wg_manager.revoke_wireguard_keys(node_id, tenant_id=tenant_id)
        except Exception as e:
            logger.error(
                "wireguard_keys_revocation_failed",
                node_id=node_id,
                tenant_id=tenant_id,
                error=str(e),
            )
            return (
                {"error": "Failed to revoke keys"},
                500,
            )

        if success:
            logger.info(
                "wireguard_keys_revoked",
                node_id=node_id,
                tenant_id=tenant_id,
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
        else:
            logger.warning(
                "wireguard_keys_revocation_not_found",
                node_id=node_id,
                tenant_id=tenant_id,
            )
            return (
                {"error": "Node not found"},
                404,
            )

    except Exception as e:
        logger.error("wireguard_keys_revocation_error", error=str(e))
        return (
            {"error": "Internal server error"},
            500,
        )
