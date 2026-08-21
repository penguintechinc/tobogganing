"""Feed source management blueprint for threatintel module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp
import structlog
from quart import Blueprint, jsonify
from quart_schema import tag, validate_request, validate_response

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature

from .ingestor import ingest_feed_source
from .source_manager import VALID_SOURCE_TYPES, FeedSourceManager, FeedSourceRecord

logger = structlog.get_logger()

feeds_bp = Blueprint("threatintel_feeds", __name__, url_prefix="/feeds")


# Request DTOs
@dataclass(slots=True)
class CreateFeedSourceRequest:
    """Create feed source request DTO."""

    name: str
    source_type: str
    url: str
    enabled: bool = True


# Response DTOs
@dataclass(slots=True)
class FeedSourceResponse:
    """Feed source response DTO."""

    id: str
    name: str
    source_type: str
    url: str
    enabled: bool
    last_refresh_at: str | None
    last_refresh_status: str | None
    last_refresh_error: str | None
    created_at: str


@dataclass(slots=True)
class FeedSourcesListResponse:
    """List feed sources response."""

    sources: list[FeedSourceResponse]
    meta: dict[str, Any]


@dataclass(slots=True)
class RefreshResultResponse:
    """Feed source refresh result response DTO."""

    id: str
    status: str
    added: int
    updated: int
    errors: int
    meta: dict[str, Any]


@dataclass(slots=True)
class MessageResponse:
    """Generic message response DTO."""

    message: str
    meta: dict[str, Any]


def _meta() -> dict[str, Any]:
    """Build the standard response meta block."""
    return {"version": 1, "timestamp": datetime.now(timezone.utc).isoformat()}


def _to_dto(source: FeedSourceRecord) -> dict[str, Any]:
    """Convert a FeedSourceRecord into the exact FeedSourceResponse field set."""
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "url": source.url,
        "enabled": source.enabled,
        "last_refresh_at": (source.last_refresh_at.isoformat() if source.last_refresh_at else None),
        "last_refresh_status": source.last_refresh_status,
        "last_refresh_error": source.last_refresh_error,
        "created_at": source.created_at.isoformat(),
    }


@feeds_bp.route("", methods=["GET"])
@tag(["threatintel"])
@require_tenant
@require_scope("threatintel:read")
@require_feature("threatintel", "feeds")
@validate_response(FeedSourcesListResponse)
async def list_feed_sources() -> tuple[dict[str, Any], int]:
    """List all threat-intel feed sources for the tenant.

    Returns:
        JSON response with list of feed sources and meta.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = FeedSourceManager(db, tenant_id)
        sources = await manager.list_sources()

        return (
            {
                "sources": [_to_dto(s) for s in sources],
                "meta": _meta(),
            },
            200,
        )
    except Exception as e:
        logger.error("list_feed_sources_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@feeds_bp.route("", methods=["POST"])
@tag(["threatintel"])
@require_tenant
@require_scope("threatintel:write")
@require_feature("threatintel", "feeds")
@validate_request(CreateFeedSourceRequest)
@validate_response(FeedSourceResponse)
async def create_feed_source(data: CreateFeedSourceRequest) -> tuple[dict[str, Any], int]:
    """Create a new threat-intel feed source.

    Request body:
    {
        "name": "my-misp",
        "source_type": "misp",
        "url": "https://misp.example.com/export.json",
        "enabled": true
    }

    Returns:
        JSON response with created feed source (201) or error (400/500).
    """
    try:
        if data.source_type not in VALID_SOURCE_TYPES:
            return (
                jsonify(
                    {
                        "error": (
                            f"Invalid source_type: {data.source_type}. "
                            f"Must be one of: {', '.join(sorted(VALID_SOURCE_TYPES))}"
                        )
                    }
                ),
                400,
            )

        if not data.url.startswith(("http://", "https://")):
            return jsonify({"error": "url must be http:// or https://"}), 400

        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = FeedSourceManager(db, tenant_id)
        source = await manager.create_source(
            name=data.name,
            source_type=data.source_type,
            url=data.url,
            enabled=data.enabled,
        )

        if not source:
            return (
                jsonify({"error": "Feed source name already exists in this tenant"}),
                400,
            )

        return _to_dto(source), 201
    except Exception as e:
        logger.error("create_feed_source_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@feeds_bp.route("/<source_id>", methods=["DELETE"])
@tag(["threatintel"])
@require_tenant
@require_scope("threatintel:write")
@require_feature("threatintel", "feeds")
@validate_response(MessageResponse)
async def delete_feed_source(source_id: str) -> tuple[dict[str, Any], int]:
    """Delete a threat-intel feed source.

    Args:
        source_id: Feed source ID to delete.

    Returns:
        JSON response with deletion status (200) or error (404/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = FeedSourceManager(db, tenant_id)
        deleted = await manager.delete_source(source_id)

        if not deleted:
            return jsonify({"error": "Feed source not found"}), 404

        return (
            {"message": "Feed source deleted successfully", "meta": _meta()},
            200,
        )
    except Exception as e:
        logger.error("delete_feed_source_error", error=str(e), source_id=source_id)
        return jsonify({"error": "Internal server error"}), 500


@feeds_bp.route("/<source_id>/refresh", methods=["POST"])
@tag(["threatintel"])
@require_tenant
@require_scope("threatintel:write")
@require_feature("threatintel", "feeds")
@validate_response(RefreshResultResponse)
async def refresh_feed_source(source_id: str) -> tuple[dict[str, Any], int]:
    """Trigger an immediate ingest for a threat-intel feed source.

    Fetches the source URL, parses it per source_type, and stores every
    indicator into threat_indicators for the tenant. Fetch/parse failures
    are recorded on the source (last_refresh_status="failed") rather than
    raised, so a bad feed never 500s the caller.

    Args:
        source_id: Feed source ID to refresh.

    Returns:
        JSON response with refresh stats (200) or error (404/500).
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = FeedSourceManager(db, tenant_id)
        source = await manager.get_source(source_id)

        if not source:
            return jsonify({"error": "Feed source not found"}), 404

        async with aiohttp.ClientSession() as session:
            try:
                stats = await ingest_feed_source(
                    db, tenant_id, source.source_type, source.url, session
                )
                await manager.mark_refresh_result(source_id, status="completed")
                return (
                    {
                        "id": source_id,
                        "status": "completed",
                        "added": stats["added"],
                        "updated": stats["updated"],
                        "errors": stats["errors"],
                        "meta": _meta(),
                    },
                    200,
                )
            except Exception as e:
                await manager.mark_refresh_result(source_id, status="failed", error=str(e))
                logger.warning("feed_source_refresh_failed", source_id=source_id, error=str(e))
                return (
                    {
                        "id": source_id,
                        "status": "failed",
                        "added": 0,
                        "updated": 0,
                        "errors": 1,
                        "meta": _meta(),
                    },
                    200,
                )
    except Exception as e:
        logger.error("refresh_feed_source_error", error=str(e), source_id=source_id)
        return jsonify({"error": "Internal server error"}), 500
