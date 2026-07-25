"""Version information REST API blueprint for WaddlePerf client."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, current_app, jsonify, request

from hub_api.auth.middleware import current_claims, require_tenant
from hub_api.entitlements.gate import require_feature

logger = structlog.get_logger()

blueprint = Blueprint("wpcl_version", __name__, url_prefix="/version")


@blueprint.route("", methods=["GET"])
@require_tenant
@require_feature("waddleperf_client", "version")
async def get_version() -> tuple[dict[str, Any], int]:
    """Get the latest WaddlePerf client version information.

    Required feature: waddleperf_client.version
    No specific scope required (tenant access is sufficient).

    Returns:
        JSON response with version details and metadata
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        # Default version info
        latest_version = current_app.config.get("WPCL_LATEST_VERSION", "1.0.0")
        min_version = current_app.config.get("WPCL_MIN_VERSION", "0.1.0")
        download_url = current_app.config.get(
            "WPCL_DOWNLOAD_URL",
            "https://downloads.tobogganing.app/waddleperf-client/latest",
        )

        logger.info(
            "version_retrieved",
            latest_version=latest_version,
            tenant=claims["tenant"],
        )

        return (
            {
                "latest_version": latest_version,
                "min_version": min_version,
                "download_url": download_url,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("version_retrieval_failed", error=str(e))
        return {"error": "Internal server error"}, 500
