"""WaddlePerf cluster scheduled test API blueprint."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.scheduler.job_manager import JobManager

logger = structlog.get_logger()

blueprint = Blueprint("wpc_scheduled_tests", __name__, url_prefix="/scheduled-tests")


@blueprint.route("", methods=["POST"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "scheduled_tests")
async def create_scheduled_test() -> tuple[dict[str, Any], int]:
    """Create a scheduled server test.

    Required scope: tests:write
    Required feature: perftest_cluster.scheduled_tests

    JSON body:
        device_id: Device identifier (required, non-empty string)
        test_type: Test type (required, non-empty string)
        target: Target URL or endpoint (required, non-empty string)
        interval_seconds: Interval in seconds (required, int >= 30)

    Returns:
        JSON response with created job and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data:
            return {"error": "Request body is required"}, 400

        # Validate required fields
        required = ["device_id", "test_type", "target", "interval_seconds"]
        missing = [f for f in required if f not in data]
        if missing:
            return {"error": f"Missing required fields: {', '.join(missing)}"}, 400

        # Validate device_id, test_type, target are non-empty strings
        device_id = data.get("device_id")
        test_type = data.get("test_type")
        target = data.get("target")

        if not isinstance(device_id, str) or not device_id.strip():
            return {"error": "device_id must be a non-empty string"}, 400
        if not isinstance(test_type, str) or not test_type.strip():
            return {"error": "test_type must be a non-empty string"}, 400
        if not isinstance(target, str) or not target.strip():
            return {"error": "target must be a non-empty string"}, 400

        # Validate interval_seconds
        interval_seconds = data.get("interval_seconds")
        if not isinstance(interval_seconds, int):
            return {"error": "interval_seconds must be an integer"}, 400
        if interval_seconds < 30:
            return {"error": "interval_seconds must be at least 30"}, 400

        # Create scheduled job
        db = get_db()
        manager = JobManager(db)

        payload = {
            "device_id": device_id.strip(),
            "test_type": test_type.strip(),
            "target": target.strip(),
        }

        job = await manager.create_job(
            tenant=tenant_id,
            module="perftest_cluster",
            job_type="server_test",
            payload=payload,
            interval_seconds=interval_seconds,
            enabled=True,
        )

        logger.info(
            "scheduled_test_created",
            job_id=job["id"][:8],
            device_id=device_id,
            test_type=test_type,
            tenant=tenant_id,
        )

        return (
            {
                "id": job["id"],
                "device_id": job["payload"]["device_id"],
                "test_type": job["payload"]["test_type"],
                "target": job["payload"]["target"],
                "interval_seconds": job["interval_seconds"],
                "enabled": job["enabled"],
                "next_run_at": job["next_run_at"].isoformat(),
                "created_at": job["created_at"].isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except ValueError as e:
        logger.warning("validation_error", error=str(e))
        return {"error": str(e)}, 400
    except Exception as e:
        logger.error("create_scheduled_test_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("perftest.cluster", "scheduled_tests")
async def list_scheduled_tests() -> tuple[dict[str, Any], int]:
    """List scheduled tests for the tenant.

    Required scope: tests:read
    Required feature: perftest_cluster.scheduled_tests

    Returns:
        JSON response with list of scheduled tests and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = JobManager(db)

        jobs = await manager.list_jobs(tenant_id, module="perftest_cluster")

        # Filter to server_test jobs only
        jobs = [j for j in jobs if j["job_type"] == "server_test"]

        return (
            {
                "jobs": [
                    {
                        "id": j["id"],
                        "device_id": j["payload"]["device_id"],
                        "test_type": j["payload"]["test_type"],
                        "target": j["payload"]["target"],
                        "interval_seconds": j["interval_seconds"],
                        "enabled": j["enabled"],
                        "next_run_at": j["next_run_at"].isoformat(),
                        "last_run_at": (
                            j["last_run_at"].isoformat() if j["last_run_at"] else None
                        ),
                        "created_at": j["created_at"].isoformat(),
                    }
                    for j in jobs
                ],
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_scheduled_tests_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<job_id>", methods=["DELETE"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "scheduled_tests")
async def delete_scheduled_test(job_id: str) -> tuple[dict[str, Any], int]:
    """Delete a scheduled test.

    Required scope: tests:write
    Required feature: perftest_cluster.scheduled_tests

    Path parameters:
        job_id: Job identifier

    Returns:
        Empty response (204) or not found (404)
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = JobManager(db)

        # Verify job exists and belongs to tenant
        job = await manager.get_job(tenant_id, job_id)
        if not job:
            return {"error": "Job not found"}, 404

        # Delete the job
        deleted = await manager.delete_job(tenant_id, job_id)
        if not deleted:
            return {"error": "Job not found"}, 404

        logger.info(
            "scheduled_test_deleted",
            job_id=job_id[:8],
            tenant=tenant_id,
        )

        return "", 204

    except Exception as e:
        logger.error("delete_scheduled_test_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<job_id>", methods=["PATCH"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "scheduled_tests")
async def update_scheduled_test(job_id: str) -> tuple[dict[str, Any], int]:
    """Update a scheduled test (enable/disable).

    Required scope: tests:write
    Required feature: perftest_cluster.scheduled_tests

    Path parameters:
        job_id: Job identifier

    JSON body:
        enabled: Boolean to enable or disable the job

    Returns:
        JSON response with updated job
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data or "enabled" not in data:
            return {"error": "Request body with 'enabled' field is required"}, 400

        db = get_db()
        manager = JobManager(db)

        # Verify job exists and belongs to tenant
        job = await manager.get_job(tenant_id, job_id)
        if not job:
            return {"error": "Job not found"}, 404

        # Update enabled status
        updated = await manager.set_enabled(tenant_id, job_id, data["enabled"])
        if not updated:
            return {"error": "Failed to update job"}, 500

        # Fetch updated job
        job = await manager.get_job(tenant_id, job_id)
        if not job:
            return {"error": "Job not found after update"}, 500

        logger.info(
            "scheduled_test_updated",
            job_id=job_id[:8],
            enabled=job["enabled"],
            tenant=tenant_id,
        )

        return (
            {
                "id": job["id"],
                "device_id": job["payload"]["device_id"],
                "test_type": job["payload"]["test_type"],
                "target": job["payload"]["target"],
                "interval_seconds": job["interval_seconds"],
                "enabled": job["enabled"],
                "next_run_at": job["next_run_at"].isoformat(),
                "last_run_at": (
                    job["last_run_at"].isoformat() if job["last_run_at"] else None
                ),
                "created_at": job["created_at"].isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("update_scheduled_test_failed", error=str(e))
        return {"error": "Internal server error"}, 500
