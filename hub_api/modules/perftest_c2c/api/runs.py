"""Cluster-to-cluster matrix runs REST API blueprint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request

from hub_api.auth.middleware import (current_claims, require_scope,
                                     require_tenant)
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_c2c.services.run_manager import RunManager
from hub_api.modules.perftest_cluster.services.engine_client import \
    ALLOWED_TEST_TYPES

logger = structlog.get_logger()

blueprint = Blueprint("c2c_runs", __name__, url_prefix="/runs")


@blueprint.route("", methods=["POST"])
@require_tenant
@require_scope("c2c:write")
@require_feature("perftest.c2c", "runs")
async def create_run() -> tuple[dict[str, Any], int]:
    """Create and enqueue a new matrix run.

    Request body:
        {
            "test_types": ["http", "icmp"],
            "endpoint_ids": ["ep-1", "ep-2"]  # optional; defaults to all enabled
        }

    Returns:
        202 with run_id and total_pairs enqueued.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        user_id = claims.get("sub")
        db = get_db()

        data = await request.get_json()
        test_types = data.get("test_types", [])
        endpoint_ids = data.get("endpoint_ids")

        # Validate test_types
        if not test_types or not isinstance(test_types, list) or len(test_types) == 0:
            return {
                "error": "Invalid test_types",
                "message": "test_types must be a non-empty list",
            }, 400

        # Validate that all test_types are allowed by the engine
        invalid_types = [t for t in test_types if t not in ALLOWED_TEST_TYPES]
        if invalid_types:
            allowed = sorted(ALLOWED_TEST_TYPES)
            return {
                "error": "Invalid test_types",
                "message": (
                    f"Invalid test types: {invalid_types}. " f"Allowed types: {allowed}"
                ),
            }, 400

        manager = RunManager(db, tenant)

        try:
            run, pairs = await manager.create_run(
                test_types=test_types,
                endpoint_ids=endpoint_ids,
                created_by=user_id,
            )
        except ValueError as e:
            logger.warning("run_create_failed", error=str(e), tenant=tenant)
            return {"error": str(e)}, 400

        # Mark as running and enqueue
        run_id: str = run["id"]  # type: ignore[assignment]
        await manager.mark_running(run_id)

        try:
            pairs_count = await manager.enqueue_run(run_id, pairs)
        except Exception as e:
            logger.error(
                "run_enqueue_failed",
                run_id=run["id"],
                error=str(e),
                exc_info=True,
            )
            return {
                "error": "Failed to enqueue run",
                "message": str(e),
            }, 500

        logger.info(
            "run_created_api",
            run_id=run["id"],
            pairs_count=pairs_count,
            tenant=tenant,
        )

        return (
            {
                "run_id": run["id"],
                "total_pairs": pairs_count,
                "status": "running",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            202,
        )

    except Exception as e:
        logger.error("create_run_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("perftest.c2c", "runs")
async def list_runs() -> tuple[dict[str, Any], int]:
    """List matrix runs for the tenant.

    Returns:
        200 with list of runs.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        manager = RunManager(db, tenant)
        runs = await manager.list_runs()

        logger.info(
            "runs_listed",
            count=len(runs),
            tenant=tenant,
        )

        return (
            {
                "runs": runs,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_runs_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("/<run_id>", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("perftest.c2c", "runs")
async def get_run(run_id: str) -> tuple[dict[str, Any], int]:
    """Get run status and progress.

    Args:
        run_id: Run identifier.

    Returns:
        200 with run status/progress, 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        manager = RunManager(db, tenant)
        run = await manager.get_run(run_id)

        if not run:
            logger.info(
                "run_not_found",
                run_id=run_id,
                tenant=tenant,
            )
            return {"error": "Run not found"}, 404

        logger.info(
            "run_retrieved",
            run_id=run_id,
            tenant=tenant,
        )

        return (
            {
                **run,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_run_failed", run_id=run_id, error=str(e))
        return {"error": "Internal server error"}, 500
