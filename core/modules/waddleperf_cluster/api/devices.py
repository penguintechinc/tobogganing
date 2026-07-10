"""Devices REST API blueprint for WaddlePerf cluster."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, current_app, jsonify, request

from core.auth.middleware import current_claims, require_scope, require_tenant
from core.db import get_db
from core.entitlements.gate import require_feature
from core.modules.waddleperf_cluster.services.device_auth import authenticate_device_global
from core.modules.waddleperf_cluster.services.device_manager import DeviceManager

logger = structlog.get_logger()

blueprint = Blueprint("wpc_devices", __name__, url_prefix="/devices")


def _extract_bearer_token() -> str | None:
    """Extract JWT or API key from Authorization header.

    Returns:
        Token string if present, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("devices:read")
@require_feature("waddleperf_cluster", "devices")
async def list_devices() -> tuple[dict[str, Any], int]:
    """List devices for the tenant.

    Requires valid JWT with devices:read scope.

    Returns:
        JSON response with list of devices.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        device_manager = DeviceManager(db, tenant_id)
        await device_manager.initialize()

        devices = await device_manager.list_devices()

        device_list = [
            {
                "id": d.id,
                "name": d.name,
                "serial": d.serial,
                "hostname": d.hostname,
                "os": d.os,
                "org_unit_id": d.org_unit_id,
                "status": d.status,
                "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None,
                "created_at": d.created_at.isoformat(),
            }
            for d in devices
        ]

        logger.info(
            "devices_listed",
            count=len(device_list),
            tenant=tenant_id,
        )

        return (
            {
                "devices": device_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_devices_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<device_id>", methods=["GET"])
@require_tenant
@require_scope("devices:read")
@require_feature("waddleperf_cluster", "devices")
async def get_device(device_id: str) -> tuple[dict[str, Any], int]:
    """Get device details.

    Requires valid JWT with devices:read scope.

    Args:
        device_id: Device identifier.

    Returns:
        JSON response with device details.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        device_manager = DeviceManager(db, tenant_id)
        await device_manager.initialize()

        device = await device_manager.get_device(device_id)

        if not device:
            return {"error": "Device not found"}, 404

        logger.info(
            "device_retrieved",
            device_id=device_id,
            tenant=tenant_id,
        )

        return (
            {
                "device": {
                    "id": device.id,
                    "name": device.name,
                    "serial": device.serial,
                    "hostname": device.hostname,
                    "os": device.os,
                    "org_unit_id": device.org_unit_id,
                    "status": device.status,
                    "last_heartbeat": device.last_heartbeat.isoformat() if device.last_heartbeat else None,
                    "created_at": device.created_at.isoformat(),
                    "updated_at": device.updated_at.isoformat(),
                    "metadata": device.device_metadata or {},
                },
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_device_failed", device_id=device_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<device_id>/heartbeat", methods=["POST"])
@require_feature("waddleperf_cluster", "devices")
async def device_heartbeat(device_id: str) -> tuple[dict[str, Any], int]:
    """Record device heartbeat.

    Requires valid API key for the device.

    Args:
        device_id: Device identifier.

    Returns:
        JSON response with status.
    """
    try:
        # Authenticate using API key (globally, no tenant trust)
        api_key = _extract_bearer_token()
        if not api_key:
            return {"error": "Invalid authorization header"}, 401

        db = get_db()

        # Authenticate device globally; get back device record and its tenant
        auth_result = await authenticate_device_global(db, api_key)
        if not auth_result:
            return {"error": "Unauthorized"}, 401

        device, tenant_id = auth_result

        # Verify device_id matches authenticated device (IDOR protection)
        if device.id != device_id:
            logger.warning(
                "heartbeat_id_mismatch",
                expected_device_id=device_id,
                authenticated_device_id=device.id,
                tenant=tenant_id,
            )
            return {"error": "Forbidden"}, 403

        # Record heartbeat
        device_manager = DeviceManager(db, tenant_id)
        await device_manager.initialize()
        updated = await device_manager.heartbeat(device_id)

        if not updated:
            return {"error": "Device not found"}, 404

        logger.info(
            "device_heartbeat_recorded",
            device_id=device_id,
            tenant=tenant_id,
        )

        return (
            {
                "status": "heartbeat_recorded",
                "device_id": device_id,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("device_heartbeat_failed", device_id=device_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<device_id>/config", methods=["GET"])
@require_feature("waddleperf_cluster", "devices")
async def get_device_config(device_id: str) -> tuple[dict[str, Any], int]:
    """Get device configuration.

    Requires valid API key for the device.

    Args:
        device_id: Device identifier.

    Returns:
        JSON response with device configuration.
    """
    try:
        # Authenticate using API key (globally, no tenant trust)
        api_key = _extract_bearer_token()
        if not api_key:
            return {"error": "Invalid authorization header"}, 401

        db = get_db()

        # Authenticate device globally; get back device record and its tenant
        auth_result = await authenticate_device_global(db, api_key)
        if not auth_result:
            return {"error": "Unauthorized"}, 401

        device, tenant_id = auth_result

        # Verify device_id matches authenticated device (IDOR protection)
        if device.id != device_id:
            logger.warning(
                "config_id_mismatch",
                expected_device_id=device_id,
                authenticated_device_id=device.id,
                tenant=tenant_id,
            )
            return {"error": "Forbidden"}, 403

        logger.info(
            "device_config_retrieved",
            device_id=device_id,
            tenant=tenant_id,
        )

        return (
            {
                "device_id": device_id,
                "config": {
                    "check_interval_seconds": 300,
                    "tests": ["latency", "throughput"],
                    "enabled": True,
                },
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_device_config_failed", device_id=device_id, error=str(e))
        return {"error": "Internal server error"}, 500
