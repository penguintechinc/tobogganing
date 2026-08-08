"""Read-only API for SASE blocklist verdict lookups."""
from __future__ import annotations

from dataclasses import dataclass

from quart import Blueprint, jsonify, request

from hub_api.auth.middleware import require_scope, require_tenant
from hub_api.entitlements.gate import require_feature

from .models import Verdict, IOC_TYPES
from .store import BlocklistStore

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
                {
                    "error": f"Invalid IOC type: {ioc_type}. Must be one of: {', '.join(IOC_TYPES)}"
                }
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
