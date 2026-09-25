"""Ziti API blueprints."""
from __future__ import annotations

from quart import Blueprint, jsonify

# Create a minimal health blueprint for the ziti module
_health_bp = Blueprint("ziti_health", __name__, url_prefix="/api/v1/ziti")


@_health_bp.route("/health", methods=["GET"])
async def health() -> tuple[dict, int]:
    """Return ziti module scaffold status.

    Returns:
        Tuple of (response dict, HTTP status code).
    """
    return jsonify({"status": "scaffold", "module": "ziti"}), 200


blueprints = (_health_bp,)
