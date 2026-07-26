"""Cluster-to-cluster results matrix REST API blueprint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request

from hub_api.auth.middleware import (current_claims, require_scope,
                                     require_tenant)
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_c2c.services.matrix_service import \
    MatrixService
from hub_api.modules.perftest_c2c.services.run_manager import RunManager

logger = structlog.get_logger()

blueprint = Blueprint("c2c_matrix", __name__, url_prefix="/matrix")


@blueprint.route("/latest", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("perftest_c2c", "matrix")
async def get_latest_matrix() -> tuple[dict[str, Any], int]:
    """Get the latest NxN region matrix for a test type.

    Query params:
        test_type: Required test type (e.g., "http", "icmp")

    Returns:
        200 with matrix data, 400 if test_type missing.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        test_type = (request.args.get("test_type") or "").strip()

        if not test_type:
            return {
                "error": "Missing required parameter",
                "required": ["test_type"],
            }, 400

        service = MatrixService(db, tenant)
        matrix = await service.latest_matrix(test_type)

        regions: Any = matrix.get("regions", [])
        cells: Any = matrix.get("cells", [])
        logger.info(
            "matrix_latest_retrieved",
            test_type=test_type,
            regions_count=len(regions) if isinstance(regions, list) else 0,
            cells_count=len(cells) if isinstance(cells, list) else 0,
            tenant=tenant,
        )

        return (
            {
                **matrix,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_latest_matrix_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("/runs/<run_id>", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("perftest_c2c", "matrix")
async def get_run_matrix(run_id: str) -> tuple[dict[str, Any], int]:
    """Get the region matrix for a specific run.

    Args:
        run_id: Run identifier.

    Returns:
        200 with run matrix, 404 if run not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        # Verify run exists via RunManager (finding #5)
        run_manager = RunManager(db, tenant)
        run = await run_manager.get_run(run_id)

        if not run:
            logger.info(
                "run_matrix_not_found",
                run_id=run_id,
                tenant=tenant,
            )
            return {"error": "Run not found"}, 404

        service = MatrixService(db, tenant)
        matrix = await service.run_matrix(run_id)

        run_regions: Any = matrix.get("regions", [])
        run_cells: Any = matrix.get("cells", [])
        logger.info(
            "run_matrix_retrieved",
            run_id=run_id,
            regions_count=len(run_regions) if isinstance(run_regions, list) else 0,
            cells_count=len(run_cells) if isinstance(run_cells, list) else 0,
            tenant=tenant,
        )

        return (
            {
                **matrix,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_run_matrix_failed", run_id=run_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/trends", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("perftest_c2c", "matrix")
async def get_trends() -> tuple[dict[str, Any], int]:
    """Get trends for a region pair and test type.

    Query params:
        source: Required source region
        dest: Required destination region
        test_type: Required test type
        window: Optional window size (default 20)

    Returns:
        200 with trend data, 400 if required params missing.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        source = (request.args.get("source") or "").strip()
        dest = (request.args.get("dest") or "").strip()
        test_type = (request.args.get("test_type") or "").strip()

        # Validate required params
        if not source or not dest or not test_type:
            return {
                "error": "Missing required parameters",
                "required": ["source", "dest", "test_type"],
            }, 400

        # Optional window param
        try:
            window = int(request.args.get("window", 20))
        except ValueError:
            window = 20

        service = MatrixService(db, tenant)
        trends = await service.trends(
            source_region=source,
            dest_region=dest,
            test_type=test_type,
            window=window,
        )

        logger.info(
            "trends_retrieved",
            source_region=source,
            dest_region=dest,
            test_type=test_type,
            window=window,
            results_count=len(trends),
            tenant=tenant,
        )

        return (
            {
                "source": source,
                "dest": dest,
                "test_type": test_type,
                "trends": trends,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_trends_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500
