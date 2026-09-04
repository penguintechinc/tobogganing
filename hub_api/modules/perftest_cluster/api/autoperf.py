"""AutoPerf tiered monitoring policies REST API."""
from __future__ import annotations

from typing import Any

import structlog
from quart import Blueprint, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_cluster.services.autoperf_manager import AutoPerfManager

log = structlog.get_logger(__name__)

autoperf_bp = Blueprint("wpc_autoperf", __name__, url_prefix="/autoperf")


@autoperf_bp.route("/policies", methods=["POST"])
@require_tenant
@require_scope("autoperf:write")
@require_feature("perftest.cluster", "autoperf")
async def create_policy() -> tuple[dict[str, Any], int]:
    """Create an AutoPerf policy.

    Required scope: autoperf:write
    Required feature: perftest_cluster.autoperf

    JSON body:
        name: Policy name (required)
        device_id: Device to monitor (required)
        target: Test target IP/hostname (required)
        t1_interval_seconds: Tier 1 interval in seconds (default 300, min 30)
        t2_interval_seconds: Tier 2 interval in seconds (default 120, min 30)
        t3_interval_seconds: Tier 3 interval in seconds (default 60, min 30)
        deescalate_after_clean: Clean cycles to de-escalate (default 3)
        enabled: Policy enabled (default true)

    Returns:
        JSON response with created policy (201)
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
        if not data.get("name"):
            return {"error": "Missing required field: name"}, 400
        if not data.get("device_id"):
            return {"error": "Missing required field: device_id"}, 400
        if not data.get("target"):
            return {"error": "Missing required field: target"}, 400

        # Validate intervals
        t1_sec = data.get("t1_interval_seconds", 300)
        t2_sec = data.get("t2_interval_seconds", 120)
        t3_sec = data.get("t3_interval_seconds", 60)

        if t1_sec < 30 or t2_sec < 30 or t3_sec < 30:
            return {"error": "All intervals must be >= 30 seconds"}, 400

        if not (t3_sec <= t2_sec <= t1_sec):
            return {"error": "t3_interval <= t2_interval <= t1_interval required"}, 400

        db = get_db()
        autoperf_mgr = AutoPerfManager(db)

        policy = await autoperf_mgr.create_policy(
            tenant=tenant_id,
            name=data["name"],
            device_id=data["device_id"],
            target=data["target"],
            t1_interval_seconds=t1_sec,
            t2_interval_seconds=t2_sec,
            t3_interval_seconds=t3_sec,
            deescalate_after_clean=data.get("deescalate_after_clean", 3),
            enabled=data.get("enabled", True),
        )

        log.info(
            "autoperf_policy_created",
            policy_id=policy["id"],
            tenant=tenant_id,
            name=policy["name"],
        )

        return policy, 201

    except ValueError as e:
        log.warning(
            "autoperf_policy_validation_error",
            error=str(e),
        )
        return {"error": str(e)}, 400
    except Exception as e:
        log.error(
            "autoperf_policy_creation_failed",
            error=str(e),
        )
        return {"error": "Internal server error"}, 500


@autoperf_bp.route("/policies", methods=["GET"])
@require_tenant
@require_scope("autoperf:read")
@require_feature("perftest.cluster", "autoperf")
async def list_policies() -> tuple[dict[str, Any], int]:
    """List AutoPerf policies for the tenant.

    Required scope: autoperf:read
    Required feature: perftest_cluster.autoperf

    Returns:
        JSON response with policies list (200)
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        rowset = await db(db.autoperf_policies.tenant == tenant_id).select()
        policies = []

        for row in rowset:
            policies.append(
                {
                    "id": row.id,
                    "tenant": row.tenant,
                    "name": row.name,
                    "device_id": row.device_id,
                    "target": row.target,
                    "t1_interval_seconds": row.t1_interval_seconds,
                    "t2_interval_seconds": row.t2_interval_seconds,
                    "t3_interval_seconds": row.t3_interval_seconds,
                    "deescalate_after_clean": row.deescalate_after_clean,
                    "enabled": row.enabled,
                    "created_at": row.created_at,
                }
            )

        return {"policies": policies}, 200

    except Exception as e:
        log.error("autoperf_policy_list_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@autoperf_bp.route("/policies/<policy_id>", methods=["GET"])
@require_tenant
@require_scope("autoperf:read")
@require_feature("perftest.cluster", "autoperf")
async def get_policy(policy_id: str) -> tuple[dict[str, Any], int]:
    """Get a single AutoPerf policy.

    Required scope: autoperf:read
    Required feature: perftest_cluster.autoperf

    Returns:
        JSON response with policy (200) or 404 if not found
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        rowset = await db(
            (db.autoperf_policies.tenant == tenant_id)
            & (db.autoperf_policies.id == policy_id)
        ).select()

        row = rowset.first()
        if not row:
            return {"error": "Policy not found"}, 404

        return {
            "id": row.id,
            "tenant": row.tenant,
            "name": row.name,
            "device_id": row.device_id,
            "target": row.target,
            "t1_interval_seconds": row.t1_interval_seconds,
            "t2_interval_seconds": row.t2_interval_seconds,
            "t3_interval_seconds": row.t3_interval_seconds,
            "deescalate_after_clean": row.deescalate_after_clean,
            "enabled": row.enabled,
            "created_at": row.created_at,
        }, 200

    except Exception as e:
        log.error("autoperf_policy_get_failed", policy_id=policy_id, error=str(e))
        return {"error": "Internal server error"}, 500


@autoperf_bp.route("/policies/<policy_id>", methods=["DELETE"])
@require_tenant
@require_scope("autoperf:write")
@require_feature("perftest.cluster", "autoperf")
async def delete_policy(policy_id: str) -> tuple[dict[str, Any], int]:
    """Delete an AutoPerf policy.

    Required scope: autoperf:write
    Required feature: perftest_cluster.autoperf

    Returns:
        JSON response (204 on success, 404 if not found)
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        autoperf_mgr = AutoPerfManager(db)

        deleted = await autoperf_mgr.delete_policy(tenant_id, policy_id)

        if not deleted:
            return {"error": "Policy not found"}, 404

        log.info(
            "autoperf_policy_deleted",
            policy_id=policy_id,
            tenant=tenant_id,
        )

        return {}, 204

    except Exception as e:
        log.error("autoperf_policy_delete_failed", policy_id=policy_id, error=str(e))
        return {"error": "Internal server error"}, 500


@autoperf_bp.route("/policies/<policy_id>/state", methods=["GET"])
@require_tenant
@require_scope("autoperf:read")
@require_feature("perftest.cluster", "autoperf")
async def get_policy_state(policy_id: str) -> tuple[dict[str, Any], int]:
    """Get AutoPerf state for a policy.

    Required scope: autoperf:read
    Required feature: perftest_cluster.autoperf

    Returns:
        JSON response with state (200) or 404 if not found
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()
        autoperf_mgr = AutoPerfManager(db)

        state = await autoperf_mgr.get_state(tenant_id, policy_id)

        if not state:
            return {"error": "State not found"}, 404

        return state, 200

    except Exception as e:
        log.error("autoperf_state_get_failed", policy_id=policy_id, error=str(e))
        return {"error": "Internal server error"}, 500
