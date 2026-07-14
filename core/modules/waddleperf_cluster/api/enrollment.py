"""Enrollment REST API blueprint for WaddlePerf cluster."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request

from core.auth.middleware import current_claims, require_scope, require_tenant
from core.db import get_db
from core.entitlements.gate import require_feature, _is_licensed_for_tier, TIER_PROFESSIONAL
from core.modules.waddleperf_cluster.services.device_manager import DeviceManager
from core.modules.waddleperf_cluster.services.enrollment_manager import EnrollmentManager

logger = structlog.get_logger()

blueprint = Blueprint("wpc_enrollment", __name__, url_prefix="/enrollment")


@blueprint.route("/secrets", methods=["GET"])
@require_tenant
@require_scope("enrollment:read")
@require_feature("waddleperf_cluster", "enrollment")
async def list_secrets() -> tuple[dict[str, Any], int]:
    """List enrollment secrets for the tenant.

    Requires valid JWT with enrollment:read scope.

    Returns:
        JSON response with list of secrets.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        enrollment_manager = EnrollmentManager(db, tenant_id)
        await enrollment_manager.initialize()

        secrets_list = await enrollment_manager.list_secrets()

        secrets_data = [
            {
                "id": s.id,
                "org_unit_id": s.org_unit_id,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "created_at": s.created_at.isoformat(),
                "created_by": s.created_by,
            }
            for s in secrets_list
        ]

        logger.info(
            "secrets_listed",
            count=len(secrets_data),
            tenant=tenant_id,
        )

        return (
            {
                "secrets": secrets_data,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_secrets_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/secrets/<org_unit_id>", methods=["POST"])
@require_tenant
@require_scope("enrollment:write")
@require_feature("waddleperf_cluster", "enrollment")
async def create_secret(org_unit_id: str) -> tuple[dict[str, Any], int]:
    """Create an enrollment secret for an organizational unit.

    Requires valid JWT with enrollment:write scope.

    Args:
        org_unit_id: Organizational unit identifier.

    Returns:
        JSON response with created secret (including raw secret for one-time display).
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        user_id = claims.get("sub")
        db = get_db()

        enrollment_manager = EnrollmentManager(db, tenant_id)
        await enrollment_manager.initialize()

        # Parse optional expires_at from request
        data = await request.get_json() or {}
        expires_at = None
        if "expires_at" in data:
            try:
                expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return {"error": "Invalid expires_at format"}, 400

        secret, raw_secret = await enrollment_manager.create_secret(
            org_unit_id=org_unit_id,
            expires_at=expires_at,
            created_by=user_id,
        )

        logger.info(
            "enrollment_secret_created",
            secret_id=secret.id,
            org_unit_id=org_unit_id,
            tenant=tenant_id,
        )

        return (
            {
                "secret": {
                    "id": secret.id,
                    "raw": raw_secret,
                    "org_unit_id": secret.org_unit_id,
                    "expires_at": secret.expires_at.isoformat() if secret.expires_at else None,
                    "created_at": secret.created_at.isoformat(),
                },
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "note": "Store the 'raw' secret securely; it will not be displayed again",
                },
            },
            201,
        )

    except Exception as e:
        logger.error("create_secret_failed", org_unit_id=org_unit_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/secrets/<secret_id>", methods=["DELETE"])
@require_tenant
@require_scope("enrollment:write")
@require_feature("waddleperf_cluster", "enrollment")
async def delete_secret(secret_id: str) -> tuple[dict[str, Any], int]:
    """Delete an enrollment secret.

    Requires valid JWT with enrollment:write scope.

    Args:
        secret_id: Secret identifier.

    Returns:
        JSON response with status.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        enrollment_manager = EnrollmentManager(db, tenant_id)
        await enrollment_manager.initialize()

        success = await enrollment_manager.delete_secret(secret_id)

        if not success:
            return {"error": "Secret not found"}, 404

        logger.info(
            "enrollment_secret_deleted",
            secret_id=secret_id,
            tenant=tenant_id,
        )

        return (
            {
                "status": "deleted",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("delete_secret_failed", secret_id=secret_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/enroll", methods=["POST"])
@require_feature("waddleperf_cluster", "enrollment")
async def enroll_device() -> tuple[dict[str, Any], int]:
    """Enroll a device using a secret.

    Public endpoint — no JWT required. Validates enrollment secret and creates device.
    Enforces Professional tier gate for >5 active devices per tenant.

    Request body:
        secret: Enrollment secret (required)
        name: Device name (required)
        serial: Device serial (required)
        hostname: Device hostname
        os: Operating system
        device_metadata: Additional metadata JSON

    Returns:
        JSON response with enrolled device and API key.
    """
    try:
        data = await request.get_json()

        if not data:
            return {"error": "Request body is required"}, 400

        required_fields = ["secret", "name", "serial"]
        for field in required_fields:
            if field not in data:
                return {"error": f"Missing required field: {field}"}, 400

        raw_secret = data.get("secret")
        tenant_id = request.headers.get("X-Tenant-ID", "default")

        db = get_db()

        # Verify secret and get org_unit_id
        enrollment_manager = EnrollmentManager(db, tenant_id)
        await enrollment_manager.initialize()

        org_unit_id = await enrollment_manager.verify_secret(raw_secret)

        if org_unit_id is None:
            logger.warning(
                "enrollment_secret_verification_failed",
                tenant=tenant_id,
            )
            return {"error": "Invalid or expired enrollment secret"}, 401

        # Check Professional tier gate for >5 devices
        device_manager = DeviceManager(db, tenant_id)
        await device_manager.initialize()

        active_count = await device_manager.count_active_devices()

        if active_count >= 5:
            # Check if Professional license is available
            is_professional = _is_licensed_for_tier(TIER_PROFESSIONAL)

            if not is_professional:
                logger.warning(
                    "enrollment_device_limit_reached",
                    active_count=active_count,
                    tenant=tenant_id,
                )
                return (
                    {
                        "error": "Device limit reached",
                        "message": "Cannot enroll more than 5 devices without Professional license",
                    },
                    402,
                )

        # Register device
        device, api_key = await device_manager.register_device(
            {
                "name": data.get("name"),
                "serial": data.get("serial"),
                "hostname": data.get("hostname"),
                "os": data.get("os"),
                "org_unit_id": org_unit_id,
                "device_metadata": data.get("device_metadata", {}),
            }
        )

        logger.info(
            "device_enrolled",
            device_id=device.id,
            serial=device.serial,
            org_unit_id=org_unit_id,
            tenant=tenant_id,
        )

        return (
            {
                "device": {
                    "id": device.id,
                    "api_key": api_key,
                    "name": device.name,
                    "serial": device.serial,
                    "org_unit_id": device.org_unit_id,
                    "created_at": device.created_at.isoformat(),
                },
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "note": "Store the api_key securely; it will not be displayed again",
                },
            },
            201,
        )

    except Exception as e:
        logger.error("enroll_device_failed", error=str(e))
        return {"error": "Internal server error"}, 500
