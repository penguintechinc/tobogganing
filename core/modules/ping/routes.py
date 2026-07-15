"""Routes for the ping module."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, jsonify

from core.auth.middleware import require_tenant
from core.entitlements.gate import require_feature

blueprint = Blueprint("ping", __name__)


@blueprint.route("", methods=["GET"])
@require_tenant
@require_feature("ping", "enabled")
async def ping_enabled() -> tuple[dict[str, Any], int]:
    """Ping endpoint gated by the tobogganing.ping.enabled flag.

    Requires a valid tenant claim.

    Returns:
        JSON response with status and metadata.
    """
    return (
        {
            "pong": True,
            "meta": {
                "version": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        },
        200,
    )


@blueprint.route("/pro", methods=["GET"])
@require_tenant
@require_feature("ping", "pro")
async def ping_pro() -> tuple[dict[str, Any], int]:
    """Professional ping endpoint gated by the tobogganing.ping.pro feature.

    Requires a valid tenant claim and Professional license.

    Returns:
        JSON response with professional status and metadata.
    """
    return (
        {
            "pong": "pro",
            "meta": {
                "version": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        },
        200,
    )
