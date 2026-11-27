"""Per-tenant DNS resolver settings (cache + behaviour) REST endpoints.

Edits the tenant's dns_resolver_settings row (migration 0029) through
ConfigService, which validates values and bumps the config version so
enrolled resolvers pick up the change. The tenant always comes from the
validated JWT, never the request.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import structlog
from opentelemetry import metrics, trace
from quart import Blueprint, jsonify
from quart_schema import tag, validate_request, validate_response

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.netsvcs.managers.config_service import ConfigService

logger = structlog.get_logger()
_tracer = trace.get_tracer(__name__)
_updates = metrics.get_meter(__name__).create_counter(
    "netsvcs_resolver_settings_updates_total",
    description="Resolver settings update attempts by outcome",
)

resolver_settings_bp = Blueprint(
    "netsvcs_resolver_settings", __name__, url_prefix="/resolver-settings"
)


@dataclass(slots=True)
class ResolverSettingsResponse:
    """Effective resolver settings for the caller's tenant."""

    cache_enabled: bool
    cache_ttl: int
    cache_max_entries: int
    log_queries: bool
    enable_dnssec: bool
    ioc_filtering: bool


@dataclass(slots=True)
class UpdateResolverSettingsRequest:
    """Partial update; omitted (null) fields keep their current value."""

    cache_enabled: bool | None = None
    cache_ttl: int | None = None
    cache_max_entries: int | None = None
    log_queries: bool | None = None
    enable_dnssec: bool | None = None
    ioc_filtering: bool | None = None


@resolver_settings_bp.route("", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "resolver_settings")
@validate_response(ResolverSettingsResponse)
async def get_resolver_settings() -> tuple[Any, int]:
    """Return the caller tenant's effective resolver settings (defaults if unset)."""
    tenant_id = current_claims()["tenant"]
    with _tracer.start_as_current_span("netsvcs.resolver_settings.get"):
        try:
            settings = await ConfigService(get_db(), tenant_id).get_resolver_settings()
        except Exception as e:
            logger.error("get_resolver_settings_error", error=str(e))
            return jsonify({"error": "Internal server error"}), 500
    return ResolverSettingsResponse(**settings), 200


@resolver_settings_bp.route("", methods=["PUT"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "resolver_settings")
@validate_request(UpdateResolverSettingsRequest)
@validate_response(ResolverSettingsResponse)
async def put_resolver_settings(data: UpdateResolverSettingsRequest) -> tuple[Any, int]:
    """Update the caller tenant's resolver settings and bump the config version.

    Returns 400 on an empty body or an out-of-range/mistyped value.
    """
    tenant_id = current_claims()["tenant"]
    changes = {k: v for k, v in asdict(data).items() if v is not None}
    if not changes:
        _updates.add(1, {"outcome": "invalid"})
        return jsonify({"error": "no settings supplied"}), 400
    with _tracer.start_as_current_span("netsvcs.resolver_settings.put"):
        try:
            merged = await ConfigService(get_db(), tenant_id).update_resolver_settings(**changes)
        except ValueError as e:
            _updates.add(1, {"outcome": "invalid"})
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            _updates.add(1, {"outcome": "error"})
            logger.error("put_resolver_settings_error", error=str(e))
            return jsonify({"error": "Internal server error"}), 500
    _updates.add(1, {"outcome": "ok"})
    return ResolverSettingsResponse(**merged), 200
