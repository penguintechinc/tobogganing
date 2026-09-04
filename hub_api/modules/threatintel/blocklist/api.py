"""API for SASE blocklist verdict lookups and threatintel blocklist management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, current_app, jsonify, request
from quart_schema import tag, validate_request, validate_response

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature

from .entry_manager import BlocklistEntryManager, BlocklistEntryRecord
from .models import IOC_TYPES
from .store import BlocklistStore

logger = structlog.get_logger()

blueprint = Blueprint("sase_blocklist", __name__, url_prefix="/blocklist")


@dataclass(slots=True)
class VerdictDTO:
    """Response DTO for blocklist verdict lookup.

    Contains only the fields exposed to callers, never raw Verdict internals.
    """

    ioc_type: str
    value: str
    severity: str
    source: str
    stix_id: str
    first_seen: int
    expiry: int | None


# Blocklist entry management DTOs (distinct from the /check verdict DTO above)
@dataclass(slots=True)
class CreateBlocklistEntryRequest:
    """Create blocklist entry request DTO."""

    indicator_type: str
    value: str
    source: str = "manual"
    confidence: int = 100
    ttl: int = 86400


@dataclass(slots=True)
class BlocklistEntryResponse:
    """Blocklist entry response DTO."""

    id: str
    indicator_type: str
    value: str
    source: str
    confidence: int
    active: bool
    created_at: str
    updated_at: str


@dataclass(slots=True)
class BlocklistEntriesListResponse:
    """List blocklist entries response."""

    entries: list[BlocklistEntryResponse]
    meta: dict[str, Any]


@dataclass(slots=True)
class BlocklistMessageResponse:
    """Generic message response DTO for blocklist management."""

    message: str
    meta: dict[str, Any]


def _entry_meta(**extra: Any) -> dict[str, Any]:
    """Build the standard response meta block, with optional pagination fields."""
    return {"version": 1, "timestamp": datetime.now(timezone.utc).isoformat(), **extra}


def _entry_to_dto(entry: BlocklistEntryRecord) -> dict[str, Any]:
    """Convert a BlocklistEntryRecord into the exact BlocklistEntryResponse field set."""
    return {
        "id": entry.id,
        "indicator_type": entry.indicator_type,
        "value": entry.value,
        "source": entry.source,
        "confidence": entry.confidence,
        "active": entry.active,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


@blueprint.route("/check", methods=["GET"])
@require_tenant
@require_scope("sase:read")
@require_feature("threatintel", "blocklist")
async def check_ioc() -> tuple[dict, int]:
    """Check if an IOC is in the SASE blocklist.

    Query parameters:
        type: IOC type (ip, domain, url, hash)
        value: IOC value to check

    Returns:
        200 with verdict DTO if found
        404 if not found or feature disabled
        400 if invalid IOC type
    """
    ioc_type = request.args.get("type")
    value = request.args.get("value")

    if not ioc_type or not value:
        return jsonify({"error": "Missing required query parameters: type, value"}), 400

    if ioc_type not in IOC_TYPES:
        return (
            jsonify(
                {"error": f"Invalid IOC type: {ioc_type}. Must be one of: {', '.join(IOC_TYPES)}"}
            ),
            400,
        )

    from quart import current_app

    cache = current_app.config.get("CACHE")
    if not cache:
        return jsonify({"error": "Cache not configured"}), 500

    store = BlocklistStore(cache)
    verdict = await store.check(ioc_type, value)

    if verdict is None:
        return jsonify({"error": "IOC not found in blocklist"}), 404

    # Return typed DTO, never raw Verdict
    dto = {
        "ioc_type": verdict.ioc_type,
        "value": verdict.value,
        "severity": verdict.severity,
        "source": verdict.source,
        "stix_id": verdict.stix_id,
        "first_seen": verdict.first_seen,
        "expiry": verdict.expiry,
    }
    return jsonify(dto), 200


# Blocklist entry management routes (list/add/remove).
#
# Entries are persisted in threat_indicators (tenant-scoped, filterable,
# paginated, deletable by id) and mirrored into BlocklistStore for immediate
# /check visibility, matching the BlocklistCurator write path.


@blueprint.route("", methods=["GET"])
@tag(["threatintel"])
@require_tenant
@require_scope("threatintel:read")
@require_feature("threatintel", "blocklist")
@validate_response(BlocklistEntriesListResponse)
async def list_blocklist_entries() -> tuple[dict[str, Any], int]:
    """List blocklist entries for the tenant, with optional filters and pagination.

    Query parameters:
        indicator_type: Optional filter (ip/domain/url/hash)
        source: Optional filter by source
        limit: Page size (default 50, max 200)
        offset: Pagination offset (default 0)

    Returns:
        JSON response with list of entries and meta (200).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        indicator_type = request.args.get("indicator_type")
        source = request.args.get("source")
        try:
            limit = min(int(request.args.get("limit", 50)), 200)
            offset = max(int(request.args.get("offset", 0)), 0)
        except (TypeError, ValueError):
            return jsonify({"error": "limit and offset must be integers"}), 400

        manager = BlocklistEntryManager(db, tenant_id)
        entries, total = await manager.list_entries(
            indicator_type=indicator_type, source=source, limit=limit, offset=offset
        )

        return (
            {
                "entries": [_entry_to_dto(e) for e in entries],
                "meta": _entry_meta(total=total, limit=limit, offset=offset),
            },
            200,
        )
    except Exception as e:
        logger.error("list_blocklist_entries_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@blueprint.route("", methods=["POST"])
@tag(["threatintel"])
@require_tenant
@require_scope("threatintel:write")
@require_feature("threatintel", "blocklist")
@validate_request(CreateBlocklistEntryRequest)
@validate_response(BlocklistEntryResponse)
async def add_blocklist_entry(
    data: CreateBlocklistEntryRequest,
) -> tuple[dict[str, Any], int]:
    """Add a manual blocklist entry for the tenant.

    Request body:
    {
        "indicator_type": "domain",
        "value": "malicious.example.com",
        "source": "manual",
        "confidence": 100,
        "ttl": 86400
    }

    Returns:
        JSON response with created entry (201) or error (400/500).
    """
    try:
        if data.indicator_type not in IOC_TYPES:
            return (
                jsonify(
                    {
                        "error": (
                            f"Invalid indicator_type: {data.indicator_type}. "
                            f"Must be one of: {', '.join(IOC_TYPES)}"
                        )
                    }
                ),
                400,
            )

        db = get_db()
        tenant_id = current_claims()["tenant"]

        cache = current_app.config.get("CACHE")
        store = BlocklistStore(cache) if cache else None

        manager = BlocklistEntryManager(db, tenant_id, store=store)
        entry = await manager.add_entry(
            indicator_type=data.indicator_type,
            value=data.value,
            source=data.source,
            confidence=data.confidence,
            ttl=data.ttl,
        )

        if not entry:
            return (
                jsonify({"error": "Entry already exists for this tenant/source"}),
                400,
            )

        return _entry_to_dto(entry), 201
    except Exception as e:
        logger.error("add_blocklist_entry_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@blueprint.route("/<entry_id>", methods=["DELETE"])
@tag(["threatintel"])
@require_tenant
@require_scope("threatintel:write")
@require_feature("threatintel", "blocklist")
@validate_response(BlocklistMessageResponse)
async def remove_blocklist_entry(entry_id: str) -> tuple[dict[str, Any], int]:
    """Remove a blocklist entry for the tenant.

    Args:
        entry_id: Entry ID to remove.

    Returns:
        JSON response with removal status (200) or error (404/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        cache = current_app.config.get("CACHE")
        store = BlocklistStore(cache) if cache else None

        manager = BlocklistEntryManager(db, tenant_id, store=store)
        removed = await manager.remove_entry(entry_id)

        if not removed:
            return jsonify({"error": "Entry not found"}), 404

        return (
            {"message": "Blocklist entry removed successfully", "meta": _entry_meta()},
            200,
        )
    except Exception as e:
        logger.error("remove_blocklist_entry_error", error=str(e), entry_id=entry_id)
        return jsonify({"error": "Internal server error"}), 500
