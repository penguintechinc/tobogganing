"""Schedules REST API blueprint for WaddlePerf client."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, current_app, jsonify, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_client.services.schedule_manager import ScheduleManager

logger = structlog.get_logger()

blueprint = Blueprint("wpcl_schedules", __name__, url_prefix="/schedules")


@blueprint.route("", methods=["POST"])
@require_tenant
@require_scope("schedules:write")
@require_feature("perftest_client", "schedules")
async def create_schedule() -> tuple[dict[str, Any], int]:
    """Create a new test schedule.

    Required scope: schedules:write
    Required feature: perftest_client.schedules

    JSON body:
        test_type: Test type (required)
        target: Test target (required)
        interval_seconds: Test interval in seconds (required)
        org_unit_id: Organization unit ID (optional)
        enabled: Whether schedule is enabled (optional, default: true)

    Returns:
        JSON response with created schedule and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data or "test_type" not in data or "target" not in data or "interval_seconds" not in data:
            return {"error": "Missing required fields: test_type, target, interval_seconds"}, 400

        db = get_db()
        mgr = ScheduleManager(db, tenant_id)
        await mgr.initialize()

        schedule_dto = await mgr.create_schedule(
            {
                "test_type": data["test_type"],
                "target": data["target"],
                "interval_seconds": data["interval_seconds"],
                "org_unit_id": data.get("org_unit_id"),
                "enabled": data.get("enabled", True),
            }
        )

        logger.info(
            "schedule_created",
            schedule_id=schedule_dto.id,
            tenant=tenant_id,
        )

        return (
            {
                "id": schedule_dto.id,
                "tenant": schedule_dto.tenant,
                "org_unit_id": schedule_dto.org_unit_id,
                "test_type": schedule_dto.test_type,
                "target": schedule_dto.target,
                "interval_seconds": schedule_dto.interval_seconds,
                "enabled": schedule_dto.enabled,
                "created_at": schedule_dto.created_at.isoformat(),
                "updated_at": schedule_dto.updated_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        logger.error("create_schedule_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("schedules:read")
@require_feature("perftest_client", "schedules")
async def list_schedules() -> tuple[dict[str, Any], int]:
    """List test schedules for the tenant.

    Query parameters:
        org_unit_id: Filter by organization unit ID (optional)

    Returns:
        JSON response with list of schedules and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        org_unit_id = request.args.get("org_unit_id")

        db = get_db()
        mgr = ScheduleManager(db, tenant_id)
        await mgr.initialize()

        schedules = await mgr.list_schedules(org_unit_id=org_unit_id)

        schedule_list = [
            {
                "id": s.id,
                "tenant": s.tenant,
                "org_unit_id": s.org_unit_id,
                "test_type": s.test_type,
                "target": s.target,
                "interval_seconds": s.interval_seconds,
                "enabled": s.enabled,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in schedules
        ]

        logger.info(
            "schedules_listed",
            count=len(schedule_list),
            tenant=tenant_id,
            org_unit_id=org_unit_id,
        )

        return (
            {
                "schedules": schedule_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_schedules_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<schedule_id>", methods=["GET"])
@require_tenant
@require_scope("schedules:read")
@require_feature("perftest_client", "schedules")
async def get_schedule(schedule_id: str) -> tuple[dict[str, Any], int]:
    """Get a test schedule by ID.

    Args:
        schedule_id: Schedule identifier

    Returns:
        JSON response with schedule details
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        mgr = ScheduleManager(db, tenant_id)
        await mgr.initialize()

        schedule_dto = await mgr.get_schedule(schedule_id)

        if not schedule_dto:
            return {"error": "Schedule not found"}, 404

        logger.info(
            "schedule_retrieved",
            schedule_id=schedule_id,
            tenant=tenant_id,
        )

        return (
            {
                "id": schedule_dto.id,
                "tenant": schedule_dto.tenant,
                "org_unit_id": schedule_dto.org_unit_id,
                "test_type": schedule_dto.test_type,
                "target": schedule_dto.target,
                "interval_seconds": schedule_dto.interval_seconds,
                "enabled": schedule_dto.enabled,
                "created_at": schedule_dto.created_at.isoformat(),
                "updated_at": schedule_dto.updated_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_schedule_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<schedule_id>", methods=["PUT"])
@require_tenant
@require_scope("schedules:write")
@require_feature("perftest_client", "schedules")
async def update_schedule(schedule_id: str) -> tuple[dict[str, Any], int]:
    """Update a test schedule.

    Args:
        schedule_id: Schedule identifier

    JSON body:
        test_type: Test type (optional)
        target: Test target (optional)
        interval_seconds: Test interval in seconds (optional)
        enabled: Whether schedule is enabled (optional)

    Returns:
        JSON response with updated schedule
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data:
            return {"error": "Request body required"}, 400

        db = get_db()
        mgr = ScheduleManager(db, tenant_id)
        await mgr.initialize()

        schedule_dto = await mgr.update_schedule(schedule_id, data)

        if not schedule_dto:
            return {"error": "Schedule not found"}, 404

        logger.info(
            "schedule_updated",
            schedule_id=schedule_id,
            tenant=tenant_id,
        )

        return (
            {
                "id": schedule_dto.id,
                "tenant": schedule_dto.tenant,
                "org_unit_id": schedule_dto.org_unit_id,
                "test_type": schedule_dto.test_type,
                "target": schedule_dto.target,
                "interval_seconds": schedule_dto.interval_seconds,
                "enabled": schedule_dto.enabled,
                "created_at": schedule_dto.created_at.isoformat(),
                "updated_at": schedule_dto.updated_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("update_schedule_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<schedule_id>", methods=["DELETE"])
@require_tenant
@require_scope("schedules:write")
@require_feature("perftest_client", "schedules")
async def delete_schedule(schedule_id: str) -> tuple[dict[str, Any], int]:
    """Delete a test schedule.

    Args:
        schedule_id: Schedule identifier

    Returns:
        JSON response with deletion status
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        mgr = ScheduleManager(db, tenant_id)
        await mgr.initialize()

        success = await mgr.delete_schedule(schedule_id)

        if not success:
            return {"error": "Schedule not found"}, 404

        logger.info(
            "schedule_deleted",
            schedule_id=schedule_id,
            tenant=tenant_id,
        )

        return (
            {
                "message": "Schedule deleted successfully",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("delete_schedule_failed", error=str(e))
        return {"error": "Internal server error"}, 500
