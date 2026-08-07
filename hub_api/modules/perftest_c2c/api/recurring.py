"""Recurring matrix runs REST API blueprint."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.flags import feature_enabled
from hub_api.scheduler.job_manager import JobManager

logger = structlog.get_logger()

blueprint = Blueprint("c2c_recurring", __name__, url_prefix="/recurring")


@blueprint.route("", methods=["POST"])
@require_tenant
@require_scope("c2c:write")
@require_feature("perftest.c2c", "recurring_runs")
async def create_recurring() -> tuple[dict[str, Any], int]:
    """Create a new recurring matrix run or node health job.

    Request body:
        {
            "endpoint_ids": ["ep-1", "ep-2"] or null,
            # null = all enabled endpoints (matrix_run only)
            "interval_seconds": 300,
            "job_type": "matrix_run" or "node_health"  # default: "matrix_run"
        }

    Returns:
        201 with job_id and scheduled details.
        400 on invalid input or job_type.
        402 if node_health requires regions feature but not enabled.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        data = await request.get_json()
        endpoint_ids = data.get("endpoint_ids")
        interval_seconds = data.get("interval_seconds")
        job_type = data.get("job_type", "matrix_run")  # Default to matrix_run

        # Validate job_type
        if job_type not in ("matrix_run", "node_health"):
            return {
                "error": "Invalid job_type",
                "message": "job_type must be 'matrix_run' or 'node_health'",
            }, 400

        # node_health requires the regions feature
        if job_type == "node_health":
            is_regions_enabled = feature_enabled("perftest.c2c", "regions")
            if not is_regions_enabled:
                return {
                    "error": "Feature not available",
                    "message": "node_health requires the 'regions' feature to be enabled",
                }, 402

        # Validate interval_seconds
        if interval_seconds is None or not isinstance(interval_seconds, int):
            return {
                "error": "Invalid interval_seconds",
                "message": "interval_seconds must be an integer",
            }, 400

        if interval_seconds < 30:
            return {
                "error": "Invalid interval_seconds",
                "message": "interval_seconds must be >= 30",
            }, 400

        # Validate endpoint_ids: must be null or non-empty list of strings
        if endpoint_ids is not None:
            if not isinstance(endpoint_ids, list):
                return {
                    "error": "Invalid endpoint_ids",
                    "message": "endpoint_ids must be a list or null",
                }, 400
            if len(endpoint_ids) == 0:
                return {
                    "error": "Invalid endpoint_ids",
                    "message": "endpoint_ids must be null or non-empty list",
                }, 400
            # Validate all elements are strings
            if not all(isinstance(eid, str) for eid in endpoint_ids):
                return {
                    "error": "Invalid endpoint_ids",
                    "message": "all endpoint_ids must be strings",
                }, 400

        # Create the job via JobManager
        manager = JobManager(db)
        payload = {
            "endpoint_ids": endpoint_ids,
            "interval_seconds": interval_seconds,
        }

        try:
            job = await manager.create_job(
                tenant=tenant,
                module="perftest_c2c",
                job_type=job_type,
                payload=payload,
                interval_seconds=interval_seconds,
                enabled=True,
            )
        except ValueError as e:
            logger.warning(
                "recurring_create_failed", error=str(e), tenant=tenant
            )
            return {"error": str(e)}, 400

        logger.info(
            "recurring_job_created",
            job_id=job["id"][:8],
            interval_seconds=interval_seconds,
            job_type=job_type,
            tenant=tenant,
        )

        return (
            {
                "job_id": job["id"],
                "interval_seconds": interval_seconds,
                "job_type": job_type,
                "next_run_at": job["next_run_at"].isoformat()
                if job["next_run_at"]
                else None,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        logger.error("create_recurring_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("perftest.c2c", "recurring_runs")
async def list_recurring() -> tuple[dict[str, Any], int]:
    """List recurring jobs (matrix_run and node_health) for the tenant.

    Returns:
        200 with list of jobs.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        manager = JobManager(db)
        jobs = await manager.list_jobs(tenant, module="perftest_c2c")

        # Filter to recurring job types (matrix_run and node_health)
        recurring_jobs = [
            j for j in jobs if j["job_type"] in ("matrix_run", "node_health")
        ]

        logger.info(
            "recurring_jobs_listed",
            count=len(recurring_jobs),
            tenant=tenant,
        )

        return (
            {
                "jobs": recurring_jobs,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_recurring_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("/<job_id>", methods=["DELETE"])
@require_tenant
@require_scope("c2c:write")
@require_feature("perftest.c2c", "recurring_runs")
async def delete_recurring(job_id: str) -> tuple[dict[str, Any], int]:
    """Delete a recurring job.

    Args:
        job_id: Job identifier.

    Returns:
        204 if deleted, 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        manager = JobManager(db)
        deleted = await manager.delete_job(tenant, job_id)

        if not deleted:
            logger.info(
                "recurring_not_found",
                job_id=job_id[:8],
                tenant=tenant,
            )
            return {"error": "Job not found"}, 404

        logger.info(
            "recurring_deleted",
            job_id=job_id[:8],
            tenant=tenant,
        )

        return {}, 204

    except Exception as e:
        logger.error("delete_recurring_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("/<job_id>", methods=["PATCH"])
@require_tenant
@require_scope("c2c:write")
@require_feature("perftest.c2c", "recurring_runs")
async def patch_recurring(job_id: str) -> tuple[dict[str, Any], int]:
    """Toggle enabled status of a recurring job.

    Request body:
        {"enabled": bool}

    Args:
        job_id: Job identifier.

    Returns:
        200 if updated, 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        data = await request.get_json()
        enabled = data.get("enabled")

        if not isinstance(enabled, bool):
            return {
                "error": "Invalid enabled",
                "message": "enabled must be a boolean",
            }, 400

        manager = JobManager(db)
        updated = await manager.set_enabled(tenant, job_id, enabled)

        if not updated:
            logger.info(
                "recurring_not_found_patch",
                job_id=job_id[:8],
                tenant=tenant,
            )
            return {"error": "Job not found"}, 404

        logger.info(
            "recurring_enabled_updated",
            job_id=job_id[:8],
            enabled=enabled,
            tenant=tenant,
        )

        return (
            {
                "enabled": enabled,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("patch_recurring_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500
