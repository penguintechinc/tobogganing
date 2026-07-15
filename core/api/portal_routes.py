"""Portal manifest endpoint exposing registered modules and flags."""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from quart import Blueprint, current_app, jsonify

from core.auth.middleware import current_claims, require_tenant
from core.flags import feature_enabled

logger = structlog.get_logger()

portal_bp = Blueprint("portal", __name__, url_prefix="/api/v1/portal")


@portal_bp.route("/manifest", methods=["GET"])
@require_tenant
async def get_manifest() -> tuple[dict, int]:
    """Get portal manifest with modules, nav entries, and evaluated flags.

    Returns:
    - 200 {modules: [...], role: "...", meta: {...}}
    - 403 without valid Bearer token (enforced by @require_tenant)
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized: invalid token"}, 403

        # Real tokens carry roles: [..] (see AuthService); accept singular
        # "role" for compatibility, default to "viewer".
        roles = claims.get("roles")
        if isinstance(roles, list) and roles:
            role = roles[0]
        else:
            role = claims.get("role", "viewer")
        if isinstance(role, list) and role:
            role = role[0]

        # Build modules manifest
        registry = current_app.registry
        modules_dict = registry.modules()

        modules_list = []
        for module_name, contract in modules_dict.items():
            # Build nav entries for this module
            nav_entries = []
            for nav_entry in contract.nav:
                nav_entries.append({
                    "label": nav_entry.label,
                    "path": nav_entry.path,
                    "icon": nav_entry.icon,
                })

            # Evaluate flags for this module
            flags_dict = {}
            for flag_key in contract.flags:
                # Strip "tobogganing.{module}." prefix to get feature name for logging
                # Flag key format: "tobogganing.{module}.{feature}"
                # Extract just the feature part for feature_enabled call
                parts = flag_key.split(".")
                if len(parts) >= 3 and parts[0] == "tobogganing" and parts[1] == module_name:
                    # feature_enabled expects module name and full flag key
                    is_enabled = feature_enabled(module_name, flag_key)
                else:
                    # Fallback: use the full flag key as-is
                    is_enabled = feature_enabled(module_name, flag_key)

                flags_dict[flag_key] = is_enabled

            modules_list.append({
                "name": module_name,
                "nav": nav_entries,
                "flags": flags_dict,
            })

        logger.info(
            "manifest_requested",
            role=role,
            module_count=len(modules_list),
            tenant=claims.get("tenant"),
        )

        return {
            "modules": modules_list,
            "role": role,
            "meta": {
                "version": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }, 200
    except Exception as e:
        logger.error("manifest_error", error=str(e))
        return {"error": "Unauthorized: invalid token"}, 403
