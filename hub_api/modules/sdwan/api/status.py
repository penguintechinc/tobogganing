"""SASE status REST API blueprint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.modules.sdwan.orchestrator.client_registry import ClientRegistry
from hub_api.modules.sdwan.orchestrator.cluster_manager import ClusterManager

logger = structlog.get_logger()

blueprint = Blueprint("sase_status", __name__, url_prefix="/status")


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("status:read")
async def get_status() -> tuple[dict[str, Any], int]:
    """Get overall SASE service status.

    Returns aggregate metrics for clusters and clients, scoped to the
    caller's tenant. Requires a valid JWT with status:read scope — this
    endpoint previously had no auth at all and hard-coded a "default"
    tenant (security-review finding HIGH-B), leaking cross-tenant cluster
    and client counts to unauthenticated callers.

    Returns:
        JSON response with service status and metrics.
    """
    try:
        claims = current_claims()
        tenant_id = claims["tenant"]

        db = get_db()

        cluster_mgr = ClusterManager(db, tenant_id)
        await cluster_mgr.initialize()

        client_registry = ClientRegistry(db, tenant_id)
        await client_registry.initialize()

        # Get aggregate metrics
        cluster_count = await cluster_mgr.get_cluster_count()
        all_clusters = await cluster_mgr.get_all_clusters()
        active_clusters = len([c for c in all_clusters if c.status == "active"])

        client_count = await client_registry.get_client_count()
        all_clients = await client_registry.get_all_clients()
        active_clients = len([c for c in all_clients if c.status == "active"])

        logger.info(
            "status_retrieved",
            clusters_total=cluster_count,
            clusters_active=active_clusters,
            clients_total=client_count,
            clients_active=active_clients,
            tenant=tenant_id,
        )

        return (
            {
                "service": "SASE Orchestrator API",
                "status": "healthy",
                "clusters": {
                    "total": cluster_count,
                    "active": active_clusters,
                },
                "clients": {
                    "total": client_count,
                    "active": active_clients,
                },
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("status_check_failed", error=str(e))
        return (
            {
                "service": "SASE Orchestrator API",
                "status": "error",
                "error": "Internal server error",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            500,
        )
