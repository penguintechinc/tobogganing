"""AutoCheckIn configuration REST API (CRUD + tier cascade state)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_cluster.services.auto_checkin_manager import AutoCheckInManager
from hub_api.modules.perftest_cluster.services.engine_client import ALLOWED_TEST_TYPES
from hub_api.modules.perftest_cluster.worker.tasks import _test_types_for_tier

log = structlog.get_logger(__name__)

auto_checkins_bp = Blueprint("wpc_auto_checkins", __name__, url_prefix="/auto-checkins")

_REQUIRED_FIELDS = ("name", "device_id", "target_kind", "target")


def _meta() -> dict[str, Any]:
    """Standard response metadata block."""
    return {"version": 1, "timestamp": datetime.now(timezone.utc).isoformat()}


@auto_checkins_bp.route("", methods=["POST"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "auto_checkins")
async def create_auto_checkin() -> tuple[dict[str, Any], int]:
    """Create an AutoCheckIn.

    Required scope: tests:write
    Required feature: perftest_cluster.auto_checkins

    JSON body:
        name, device_id, target_kind ("ours"|"external"), target: required strings
        test_types: optional list[str] subset of ALLOWED_TEST_TYPES (defaults to
            the tier's standard set via _test_types_for_tier)
        interval_minutes: int 1-60 (default 5)
        jitter_pct: int 0-10 (default 0)
        samples_per_run: int 1-5 (default 1)
        threshold_stddev_min/threshold_stddev_max/threshold_mean: optional floats
        tier: int 1-3 (default 1)
        parent_checkin_id: required if tier > 1, forbidden if tier == 1
        enabled: bool (default true)

    Returns:
        JSON response with created check-in (201).
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()
        if not data:
            return {"error": "Request body is required"}, 400

        missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
        if missing:
            return {"error": f"Missing required fields: {', '.join(missing)}"}, 400

        for f in _REQUIRED_FIELDS:
            if not isinstance(data[f], str) or not data[f].strip():
                return {"error": f"{f} must be a non-empty string"}, 400

        tier = data.get("tier", 1)
        if not isinstance(tier, int):
            return {"error": "tier must be an integer"}, 400

        test_types = data.get("test_types") or _test_types_for_tier(tier)
        if not isinstance(test_types, list) or not all(isinstance(t, str) for t in test_types):
            return {"error": "test_types must be a list of strings"}, 400

        db = get_db()
        manager = AutoCheckInManager(db)

        checkin = await manager.create_checkin(
            tenant=tenant_id,
            name=data["name"].strip(),
            device_id=data["device_id"].strip(),
            target_kind=data["target_kind"].strip(),
            target=data["target"].strip(),
            test_types=test_types,
            interval_minutes=data.get("interval_minutes", 5),
            jitter_pct=data.get("jitter_pct", 0),
            samples_per_run=data.get("samples_per_run", 1),
            threshold_stddev_min=data.get("threshold_stddev_min"),
            threshold_stddev_max=data.get("threshold_stddev_max"),
            threshold_mean=data.get("threshold_mean"),
            tier=tier,
            parent_checkin_id=data.get("parent_checkin_id"),
            enabled=data.get("enabled", True),
        )

        log.info(
            "auto_checkin_created",
            checkin_id=checkin["id"],
            tenant=tenant_id,
            name=checkin["name"],
            tier=tier,
        )

        return {**checkin, "meta": _meta()}, 201

    except ValueError as e:
        log.warning("auto_checkin_validation_error", error=str(e))
        return {"error": str(e)}, 400
    except Exception as e:
        log.error("auto_checkin_creation_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("perftest.cluster", "auto_checkins")
async def list_auto_checkins() -> tuple[dict[str, Any], int]:
    """List AutoCheckIns for the tenant.

    Required scope: tests:read
    Required feature: perftest_cluster.auto_checkins

    Returns:
        JSON response with checkins list (200).
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)
        checkins = await manager.list_checkins(tenant_id)

        return {"checkins": checkins, "meta": _meta()}, 200

    except Exception as e:
        log.error("auto_checkin_list_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("perftest.cluster", "auto_checkins")
async def get_auto_checkin(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Get a single AutoCheckIn.

    Required scope: tests:read
    Required feature: perftest_cluster.auto_checkins

    Returns:
        JSON response with check-in (200) or 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)
        checkin = await manager.get_checkin(tenant_id, checkin_id)

        if not checkin:
            return {"error": "Check-in not found"}, 404

        return {**checkin, "meta": _meta()}, 200

    except Exception as e:
        log.error("auto_checkin_get_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>/state", methods=["GET"])
@require_tenant
@require_scope("tests:read")
@require_feature("perftest.cluster", "auto_checkins")
async def get_auto_checkin_state(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Get cascade state (last_breached, last mean/stddev, last_run_at) for a check-in.

    Required scope: tests:read
    Required feature: perftest_cluster.auto_checkins

    Returns:
        JSON response with state (200) or 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)
        state = await manager.get_state(tenant_id, checkin_id)

        if not state:
            return {"error": "State not found"}, 404

        return state, 200

    except Exception as e:
        log.error("auto_checkin_state_get_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>", methods=["PATCH"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "auto_checkins")
async def update_auto_checkin(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Update mutable AutoCheckIn fields.

    Required scope: tests:write
    Required feature: perftest_cluster.auto_checkins

    JSON body (all optional): name, target, test_types, interval_minutes,
        jitter_pct, samples_per_run, threshold_stddev_min, threshold_stddev_max,
        threshold_mean, enabled. Structural fields (device_id, target_kind,
        tier, parent_checkin_id) are immutable -- create a new check-in instead.

    Returns:
        JSON response with updated check-in (200) or 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()
        if not data:
            return {"error": "Request body is required"}, 400

        if "test_types" in data:
            tt = data["test_types"]
            if not isinstance(tt, list) or not all(isinstance(t, str) for t in tt):
                return {"error": "test_types must be a list of strings"}, 400
            unsupported = set(tt) - ALLOWED_TEST_TYPES
            if unsupported:
                return {"error": f"Unsupported test_types: {sorted(unsupported)}"}, 400

        db = get_db()
        manager = AutoCheckInManager(db)

        existing = await manager.get_checkin(tenant_id, checkin_id)
        if not existing:
            return {"error": "Check-in not found"}, 404

        updated = await manager.update_checkin(tenant_id, checkin_id, **data)
        if not updated:
            return {"error": "Check-in not found"}, 404

        log.info("auto_checkin_updated", checkin_id=checkin_id, tenant=tenant_id)

        return {**updated, "meta": _meta()}, 200

    except ValueError as e:
        log.warning("auto_checkin_update_validation_error", checkin_id=checkin_id, error=str(e))
        return {"error": str(e)}, 400
    except Exception as e:
        log.error("auto_checkin_update_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500


@auto_checkins_bp.route("/<checkin_id>", methods=["DELETE"])
@require_tenant
@require_scope("tests:write")
@require_feature("perftest.cluster", "auto_checkins")
async def delete_auto_checkin(checkin_id: str) -> tuple[dict[str, Any], int]:
    """Delete an AutoCheckIn (must have no tier-dependent children).

    Required scope: tests:write
    Required feature: perftest_cluster.auto_checkins

    Returns:
        Empty response (204), 404 if not found, or 409 if it has dependents.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        manager = AutoCheckInManager(db)

        deleted = await manager.delete_checkin(tenant_id, checkin_id)
        if not deleted:
            return {"error": "Check-in not found"}, 404

        log.info("auto_checkin_deleted", checkin_id=checkin_id, tenant=tenant_id)

        return {}, 204

    except ValueError as e:
        log.warning("auto_checkin_delete_conflict", checkin_id=checkin_id, error=str(e))
        return {"error": str(e)}, 409
    except Exception as e:
        log.error("auto_checkin_delete_failed", checkin_id=checkin_id, error=str(e))
        return {"error": "Internal server error"}, 500
