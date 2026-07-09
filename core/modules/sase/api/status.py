"""SASE status REST API blueprint."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, jsonify

from core.db import get_db
from core.modules.sase.orchestrator.cluster_manager import ClusterManager
from core.modules.sase.orchestrator.client_registry import ClientRegistry

logger = structlog.get_logger()

blueprint = Blueprint("sase_status", __name__, url_prefix="/status")


@blueprint.route("", methods=["GET"])
async def get_status() -> tuple[dict[str, Any], int]:
    """Get overall SASE service status.

    Returns aggregate metrics for clusters and clients.

    Returns:
        JSON response with service status and metrics.
    """
    try:
        db = get_db()
        tenant_id = "default"  # Phase-0 uses default tenant

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
