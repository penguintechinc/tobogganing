"""DNS zones and records blueprint for netsvcs module."""
from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, current_app, jsonify, request

from hub_api.auth.middleware import (
    current_claims,
    require_scope,
    require_tenant,
)
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.netsvcs.managers.config_service import ConfigService
from hub_api.modules.netsvcs.managers.zone_manager import ZoneManager
from quart_schema import validate_request, validate_response, tag

logger = structlog.get_logger()

zones_bp = Blueprint("netsvcs_zones", __name__, url_prefix="/zones")


# Request DTOs
@dataclass(slots=True)
class CreateZoneRequest:
    """Create zone request DTO."""

    name: str
    visibility: str = "public"
    description: str | None = None


@dataclass(slots=True)
class UpdateZoneRequest:
    """Update zone request DTO."""

    name: str | None = None
    visibility: str | None = None
    description: str | None = None


@dataclass(slots=True)
class CreateRecordRequest:
    """Create record request DTO."""

    name: str
    type: str
    value: str
    ttl: int = 300
    priority: int | None = None
    weight: int | None = None
    port: int | None = None


@dataclass(slots=True)
class UpdateRecordRequest:
    """Update record request DTO."""

    name: str | None = None
    type: str | None = None
    value: str | None = None
    ttl: int | None = None
    priority: int | None = None
    weight: int | None = None
    port: int | None = None


# Response DTOs
@dataclass(slots=True)
class ZoneResponse:
    """Zone response DTO."""

    id: str
    name: str
    visibility: str
    description: str | None
    created_at: str


@dataclass(slots=True)
class ZonesListResponse:
    """List zones response."""

    zones: list[ZoneResponse]
    meta: dict[str, Any]


@dataclass(slots=True)
class RecordResponse:
    """Record response DTO."""

    id: str
    name: str
    type: str
    value: str
    ttl: int
    created_at: str
    priority: int | None = None
    weight: int | None = None
    port: int | None = None


@dataclass(slots=True)
class RecordsListResponse:
    """List records response."""

    records: list[RecordResponse]
    meta: dict[str, Any]


@dataclass(slots=True)
class MessageResponse:
    """Generic message response DTO."""

    message: str
    meta: dict[str, Any]


# Zone routes


@zones_bp.route("", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "zones")
@validate_response(ZonesListResponse)
async def list_zones() -> tuple[dict[str, Any], int]:
    """List all zones for the tenant.

    Returns:
        JSON response with list of zones and meta.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        zones = await manager.list_zones()

        zone_dtos = [
            ZoneResponse(
                id=z.id,
                name=z.name,
                visibility=z.visibility,
                description=z.description,
                created_at=z.created_at.isoformat(),
            )
            for z in zones
        ]

        return (
            {
                "zones": zone_dtos,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("list_zones_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@zones_bp.route("", methods=["POST"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "zones")
@validate_request(CreateZoneRequest)
@validate_response(ZoneResponse)
async def create_zone(data: CreateZoneRequest) -> tuple[dict[str, Any], int]:
    """Create a new zone.

    Request body:
    {
        "name": "example.com",
        "visibility": "public",
        "description": "Example zone"
    }

    Returns:
        JSON response with created zone (201) or error (400/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        zone = await manager.create_zone(
            name=data.name,
            visibility=data.visibility,
            description=data.description,
        )

        if not zone:
            # Duplicate name in tenant
            return jsonify({"error": "Zone name already exists in this tenant"}), 400

        # Bump config version after zone creation
        config_service = ConfigService(db, tenant_id)
        await config_service.bump_version()

        return (
            {
                "id": zone.id,
                "name": zone.name,
                "visibility": zone.visibility,
                "description": zone.description,
                "created_at": zone.created_at.isoformat(),
            },
            201,
        )
    except Exception as e:
        logger.error("create_zone_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@zones_bp.route("/<zone_id>", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "zones")
@validate_response(ZoneResponse)
async def get_zone(zone_id: str) -> tuple[dict[str, Any] | Any, int]:
    """Get a single zone by ID.

    Args:
        zone_id: Zone ID to retrieve

    Returns:
        JSON response with zone details (200) or error (404/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        zone = await manager.get_zone(zone_id)

        if not zone:
            return jsonify({"error": "Zone not found"}), 404

        return (
            {
                "id": zone.id,
                "name": zone.name,
                "visibility": zone.visibility,
                "description": zone.description,
                "created_at": zone.created_at.isoformat(),
            },
            200,
        )
    except Exception as e:
        logger.error("get_zone_error", error=str(e), zone_id=zone_id)
        return jsonify({"error": "Internal server error"}), 500


@zones_bp.route("/<zone_id>", methods=["PUT"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "zones")
@validate_request(UpdateZoneRequest)
@validate_response(ZoneResponse)
async def update_zone(
    zone_id: str, data: UpdateZoneRequest
) -> tuple[dict[str, Any] | Any, int]:
    """Update an existing zone.

    Args:
        zone_id: Zone ID to update
        data: Update request data

    Returns:
        JSON response with updated zone (200) or error (400/404/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        zone = await manager.update_zone(
            zone_id=zone_id,
            name=data.name,
            visibility=data.visibility,
            description=data.description,
        )

        if not zone:
            return jsonify({"error": "Zone not found or duplicate name"}), 404

        # Bump config version after zone update
        config_service = ConfigService(db, tenant_id)
        await config_service.bump_version()

        return (
            {
                "id": zone.id,
                "name": zone.name,
                "visibility": zone.visibility,
                "description": zone.description,
                "created_at": zone.created_at.isoformat(),
            },
            200,
        )
    except Exception as e:
        logger.error("update_zone_error", error=str(e), zone_id=zone_id)
        return jsonify({"error": "Internal server error"}), 500


@zones_bp.route("/<zone_id>", methods=["DELETE"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "zones")
@validate_response(MessageResponse)
async def delete_zone(zone_id: str) -> tuple[dict[str, Any], int]:
    """Delete a zone and cascade records.

    Args:
        zone_id: Zone ID to delete

    Returns:
        JSON response with deletion status.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        deleted = await manager.delete_zone(zone_id)

        if not deleted:
            return jsonify({"error": "Zone not found"}), 404

        # Bump config version after zone deletion
        config_service = ConfigService(db, tenant_id)
        await config_service.bump_version()

        return (
            {
                "message": "Zone deleted successfully",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("delete_zone_error", error=str(e), zone_id=zone_id)
        return jsonify({"error": "Internal server error"}), 500


# Record routes


@zones_bp.route("/<zone_id>/records", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "zones")
@validate_response(RecordsListResponse)
async def list_records(zone_id: str) -> tuple[dict[str, Any], int]:
    """List all records for a zone.

    Args:
        zone_id: Zone ID to list records for

    Returns:
        JSON response with list of records and meta.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)

        # Verify zone exists and belongs to tenant
        zone = await manager.get_zone(zone_id)
        if not zone:
            return jsonify({"error": "Zone not found"}), 404

        records = await manager.list_records(zone_id)

        record_dtos = [
            RecordResponse(
                id=r.id,
                name=r.name,
                type=r.type,
                value=r.value,
                ttl=r.ttl,
                priority=r.priority,
                weight=r.weight,
                port=r.port,
                created_at=r.created_at.isoformat(),
            )
            for r in records
        ]

        return (
            {
                "records": record_dtos,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("list_records_error", error=str(e), zone_id=zone_id)
        return jsonify({"error": "Internal server error"}), 500


@zones_bp.route("/<zone_id>/records", methods=["POST"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "zones")
@validate_request(CreateRecordRequest)
@validate_response(RecordResponse)
async def create_record(
    zone_id: str, data: CreateRecordRequest
) -> tuple[dict[str, Any], int]:
    """Create a new record in a zone.

    Args:
        zone_id: Zone ID
        data: Create record request data

    Returns:
        JSON response with created record (201) or error (400/404/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        record = await manager.create_record(
            zone_id=zone_id,
            name=data.name,
            type=data.type,
            value=data.value,
            ttl=data.ttl,
            priority=data.priority,
            weight=data.weight,
            port=data.port,
        )

        if not record:
            return (
                jsonify({"error": "Zone not found or invalid record type"}),
                400,
            )

        # Bump config version after record creation
        config_service = ConfigService(db, tenant_id)
        await config_service.bump_version()

        return (
            {
                "id": record.id,
                "name": record.name,
                "type": record.type,
                "value": record.value,
                "ttl": record.ttl,
                "priority": record.priority,
                "weight": record.weight,
                "port": record.port,
                "created_at": record.created_at.isoformat(),
            },
            201,
        )
    except Exception as e:
        logger.error("create_record_error", error=str(e), zone_id=zone_id)
        return jsonify({"error": "Internal server error"}), 500


@zones_bp.route("/<zone_id>/records/<record_id>", methods=["PUT"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "zones")
@validate_request(UpdateRecordRequest)
@validate_response(RecordResponse)
async def update_record(
    zone_id: str, record_id: str, data: UpdateRecordRequest
) -> tuple[dict[str, Any] | Any, int]:
    """Update an existing record.

    Args:
        zone_id: Zone ID
        record_id: Record ID to update
        data: Update record request data

    Returns:
        JSON response with updated record (200) or error (400/404/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        record = await manager.update_record(
            zone_id=zone_id,
            record_id=record_id,
            name=data.name,
            type=data.type,
            value=data.value,
            ttl=data.ttl,
            priority=data.priority,
            weight=data.weight,
            port=data.port,
        )

        if not record:
            return jsonify({"error": "Record not found or invalid type"}), 404

        # Bump config version after record update
        config_service = ConfigService(db, tenant_id)
        await config_service.bump_version()

        return (
            {
                "id": record.id,
                "name": record.name,
                "type": record.type,
                "value": record.value,
                "ttl": record.ttl,
                "priority": record.priority,
                "weight": record.weight,
                "port": record.port,
                "created_at": record.created_at.isoformat(),
            },
            200,
        )
    except Exception as e:
        logger.error(
            "update_record_error",
            error=str(e),
            zone_id=zone_id,
            record_id=record_id,
        )
        return jsonify({"error": "Internal server error"}), 500


@zones_bp.route("/<zone_id>/records/<record_id>", methods=["DELETE"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "zones")
@validate_response(MessageResponse)
async def delete_record(zone_id: str, record_id: str) -> tuple[dict[str, Any], int]:
    """Delete a record.

    Args:
        zone_id: Zone ID
        record_id: Record ID to delete

    Returns:
        JSON response with deletion status.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ZoneManager(db, tenant_id)
        deleted = await manager.delete_record(zone_id, record_id)

        if not deleted:
            return jsonify({"error": "Record not found"}), 404

        # Bump config version after record deletion
        config_service = ConfigService(db, tenant_id)
        await config_service.bump_version()

        return (
            {
                "message": "Record deleted successfully",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error(
            "delete_record_error",
            error=str(e),
            zone_id=zone_id,
            record_id=record_id,
        )
        return jsonify({"error": "Internal server error"}), 500
