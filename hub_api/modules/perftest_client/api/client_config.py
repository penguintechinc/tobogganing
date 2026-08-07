"""Client configuration REST API blueprint for WaddlePerf client.

Device-facing endpoint that provides resolved schedules and client config
based on device API key authentication.
"""
from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, current_app, jsonify, request

from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.flags import feature_enabled
from hub_api.modules.perftest_cluster.services.device_auth import authenticate_device_global
from hub_api.modules.perftest_client.services.schedule_manager import ScheduleManager

logger = structlog.get_logger()

blueprint = Blueprint("wpcl_config", __name__, url_prefix="/config")


def _extract_bearer_token() -> str | None:
    """Extract API key from Authorization header.

    Returns:
        Token string if present, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]


@blueprint.route("", methods=["GET"])
async def get_client_config() -> tuple[dict[str, Any], int]:
    """Get client configuration and resolved schedules for a device.

    This is a device-facing endpoint. Authentication is via Bearer token
    containing an API key (not a JWT). The device's tenant is derived from
    the device record, not from the request.

    Returns:
        JSON response with resolved schedules and client config
    """
    try:
        # Extract and validate device API key
        api_key = _extract_bearer_token()
        if not api_key:
            logger.warning("client_config_missing_api_key")
            return {"error": "Missing or invalid Authorization header"}, 401

        # Authenticate device globally (no tenant trust)
        db = get_db()
        auth_result = await authenticate_device_global(db, api_key)

        if auth_result is None:
            logger.warning("client_config_auth_failed", key_prefix=api_key[:8] if len(api_key) > 8 else "")
            return {"error": "Invalid device credentials"}, 401

        device, tenant_id = auth_result

        # Check if the feature flag is enabled for this tenant
        is_enabled = feature_enabled("perftest.client", "config", distinct_id=tenant_id)

        if not is_enabled:
            logger.warning(
                "client_config_feature_disabled",
                device_id=device.id,
                tenant=tenant_id,
            )
            return (
                {
                    "error": "Feature not available",
                    "message": "perftest_client.config is not enabled",
                },
                402,
            )

        # Resolve schedules for this device
        mgr = ScheduleManager(db, tenant_id)
        await mgr.initialize()
        resolved_schedules = await mgr.resolve_for_device(device)

        # Fetch client configs for this device's org unit
        client_configs = []
        if device.org_unit_id:
            # Query client configs for the org unit
            try:
                configs = await asyncio.to_thread(
                    db.client_configs.select_list,
                    tenant=tenant_id,
                    org_unit_id=device.org_unit_id,
                )
                client_configs = [c.config or {} for c in configs] if configs else []
            except Exception as e:
                logger.error("client_config_fetch_failed", error=str(e))
                client_configs = []

        schedule_list = [
            {
                "id": s.id,
                "test_type": s.test_type,
                "target": s.target,
                "interval_seconds": s.interval_seconds,
                "enabled": s.enabled,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in resolved_schedules
        ]

        logger.info(
            "client_config_retrieved",
            device_id=device.id,
            tenant=tenant_id,
            schedule_count=len(schedule_list),
        )

        return (
            {
                "schedules": schedule_list,
                "config": client_configs[0] if client_configs else {},
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("client_config_error", error=str(e))
        return {"error": "Internal server error"}, 500
