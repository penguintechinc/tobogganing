"""Cluster-to-cluster regions and node catalog REST API blueprint."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, jsonify, request

from core.auth.middleware import current_claims, require_scope, require_tenant
from core.db import get_db
from core.entitlements.gate import require_feature
from core.modules.waddleperf_c2c.services.endpoint_manager import EndpointManager

logger = structlog.get_logger()

blueprint = Blueprint("c2c_regions", __name__, url_prefix="/regions")


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("waddleperf_c2c", "regions")
async def list_regions() -> tuple[dict[str, Any], int]:
    """List region aggregates with node counts and health summaries.

    Returns:
        200 with list of regions: {region, node_count, healthy_count, providers}
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        manager = EndpointManager(db, tenant)
        regions = await manager.list_regions(tenant)

        logger.info(
            "regions_listed",
            count=len(regions),
            tenant=tenant,
        )

        return (
            {
                "regions": regions,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_regions_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("/nodes", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("waddleperf_c2c", "regions")
async def list_nodes() -> tuple[dict[str, Any], int]:
    """List visible endpoints (own + foreign public, optionally filtered by region).

    Query params:
        region: Optional region filter

    Returns:
        200 with list of visible endpoints (foreign public nodes redacted).
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        region_param = request.args.get("region", "").strip() or None

        manager = EndpointManager(db, tenant)
        nodes = await manager.visible_endpoints(tenant, region=region_param)

        logger.info(
            "regions_nodes_listed",
            count=len(nodes),
            region=region_param,
            tenant=tenant,
        )

        return (
            {
                "nodes": nodes,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_nodes_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500
