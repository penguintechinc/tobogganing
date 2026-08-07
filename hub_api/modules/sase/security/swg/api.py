"""API endpoints for SASE SWG domain categorization and lookup."""
from __future__ import annotations

from dataclasses import dataclass

from quart import Blueprint, jsonify, request

from hub_api.auth.middleware import (
    require_scope,
    require_tenant,
    require_machine_jwt,
    current_claims,
)
from hub_api.entitlements.gate import require_feature

from hub_api.modules.sase.security.enforcement import EnforcementAction
from hub_api.modules.sase.security.swg.lookup import SwgLookup, build_radix
from hub_api.modules.sase.security.swg.policy import CategoryPolicyManager
from hub_api.modules.sase.security.swg.ingest import CategoryIngestManager

blueprint = Blueprint("sase_swg", __name__, url_prefix="/swg")


@dataclass(slots=True)
class LookupResultDTO:
    """Response DTO for domain lookup.

    Contains the domain, its categories, resolved enforcement action,
    matched policy scope, and whether it was uncategorized.
    """

    domain: str
    categories: list[str] | None
    action: str
    matched_scope: str
    uncategorized: bool


@blueprint.route("/lookup", methods=["GET"])
@require_tenant
@require_scope("sase:read")
@require_feature("sase", "swg")
async def lookup_domain() -> tuple[dict, int]:
    """Look up a domain and return its enforcement action.

    Query parameters:
        domain: Domain to look up (required).

    Derives tenant, user_id, and group_ids from authenticated JWT claims only.
    X-* headers are not trusted for authorization context.

    Returns:
        200 with LookupResultDTO if successful
        400 if domain parameter missing or invalid
        402 if feature disabled
        403 if unauthorized
    """
    domain = request.args.get("domain", "").strip()

    if not domain:
        return jsonify({"error": "Missing required query parameter: domain"}), 400

    if not domain or len(domain) > 255:
        return jsonify({"error": "Invalid domain: must be 1-255 characters"}), 400

    try:
        from quart import current_app

        # Get lookup engine from app config
        lookup_engine: SwgLookup | None = current_app.config.get("SWG_LOOKUP")
        if not lookup_engine:
            return jsonify({"error": "SWG lookup not configured"}), 500

        # Get authenticated claims (tenant already validated by @require_tenant)
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized: no valid JWT"}), 403

        tenant = claims.get("tenant")
        user_id = claims.get("sub")  # subject from JWT
        # Extract group_ids from claims if present
        group_ids_from_claims = claims.get("groups")
        group_ids = tuple(group_ids_from_claims) if isinstance(group_ids_from_claims, (list, tuple)) else None

        result = await lookup_engine.lookup(
            domain, tenant=tenant, user_id=user_id, group_ids=group_ids
        )

        # Return DTO
        dto = {
            "domain": result.domain,
            "categories": list(result.categories) if result.categories else None,
            "action": result.action.value,
            "matched_scope": result.matched_scope,
            "uncategorized": result.uncategorized,
        }

        return jsonify(dto), 200

    except Exception as e:
        return jsonify({"error": f"Lookup failed: {str(e)}"}), 500


@blueprint.route("/radix", methods=["GET"])
@require_machine_jwt("swg:read")
async def get_radix_artifact() -> tuple[dict, int]:
    """Get the serialized radix tree artifact for data-plane consumption.

    Returns the compiled domain category radix tree as a JSON artifact,
    which the data plane pulls daily for inline lookup.

    Returns:
        200 with radix artifact and version
        403 if unauthorized (machine JWT missing swg:read scope)
        500 if radix not available
    """
    try:
        from quart import current_app

        radix = current_app.config.get("SWG_RADIX")
        if not radix:
            return jsonify({"error": "SWG radix not available"}), 500

        # Serialize the radix tree
        artifact = radix.serialize()

        # Return as base64 (for easy JSON transmission)
        import base64

        encoded = base64.b64encode(artifact).decode("utf-8")

        return (
            jsonify({
                "artifact": encoded,
                "version": "1.0",
                "encoding": "base64",
            }),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Failed to generate radix artifact: {str(e)}"}), 500


@blueprint.route("/categories", methods=["POST"])
@require_tenant
@require_scope("sase:write")
async def upsert_category() -> tuple[dict, int]:
    """Upsert a custom category for a domain (authenticated tenant only).

    Request body:
        {
            "domain": "example.com",
            "category": "blocked-shopping"
        }

    Tenant is derived from authenticated JWT claims. Request body tenant
    field (if present) must match the authenticated tenant or is rejected.

    Returns:
        200 if successful
        400 if invalid input
        403 if tenant mismatch or unauthorized
    """
    try:
        data = await request.get_json()

        domain = data.get("domain", "").strip()
        category = data.get("category", "").strip()
        request_tenant = data.get("tenant", "").strip()

        if not domain or not category:
            return (
                jsonify({
                    "error": "Missing required fields: domain, category"
                }),
                400,
            )

        # Get authenticated tenant (already validated by @require_tenant)
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized: no valid JWT"}), 403

        tenant = claims.get("tenant")

        # If request includes a tenant field, it must match the authenticated tenant
        if request_tenant and request_tenant != tenant:
            return (
                jsonify({"error": "Tenant mismatch: cannot write to other tenant"}),
                403,
            )

        from quart import current_app

        ingest_mgr = current_app.config.get("SWG_INGEST_MANAGER")
        if not ingest_mgr:
            return jsonify({"error": "SWG ingest not configured"}), 500

        # Upsert the custom category under the authenticated tenant
        await ingest_mgr.upsert_custom(domain, category, tenant=tenant)

        return jsonify({"status": "success", "domain": domain, "category": category}), 200

    except Exception as e:
        return jsonify({"error": f"Upsert failed: {str(e)}"}), 500


@blueprint.route("/policy", methods=["GET"])
@require_tenant
@require_scope("sase:read")
async def get_policies() -> tuple[dict, int]:
    """Get all category policies for authenticated tenant.

    Returns only policies for the authenticated tenant (derived from JWT claims).

    Returns:
        200 with list of policies scoped to authenticated tenant
        403 if unauthorized
    """
    try:
        # Get authenticated tenant (already validated by @require_tenant)
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized: no valid JWT"}), 403

        tenant = claims.get("tenant")

        from quart import current_app

        policy_mgr = current_app.config.get("SWG_POLICY_MANAGER")
        if not policy_mgr:
            return jsonify({"error": "SWG policy manager not configured"}), 500

        policies = await policy_mgr.get_policies(tenant)

        policies_list = [
            {
                "id": p.id,
                "scope": p.scope,
                "scope_id": p.scope_id,
                "category": p.category,
                "action": p.action,
            }
            for p in policies
        ]

        return jsonify({"policies": policies_list}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to fetch policies: {str(e)}"}), 500


@blueprint.route("/policy", methods=["PUT"])
@require_tenant
@require_scope("sase:write")
async def set_policy() -> tuple[dict, int]:
    """Set a category policy for authenticated tenant.

    Request body:
        {
            "scope": "user|group|tenant",
            "scope_id": "user123" (optional),
            "category": "gambling",
            "action": "block"
        }

    Tenant is derived from authenticated JWT claims. Any tenant field in
    the request body must match the authenticated tenant or is rejected.

    Returns:
        200 if successful
        400 if invalid input
        403 if tenant mismatch or unauthorized
    """
    try:
        data = await request.get_json()

        request_tenant = data.get("tenant", "").strip()
        scope = data.get("scope", "").strip()
        scope_id = data.get("scope_id", "").strip() or None
        category = data.get("category", "").strip()
        action = data.get("action", "").strip()

        if not scope or not category or not action:
            return (
                jsonify({
                    "error": "Missing required fields: scope, category, action"
                }),
                400,
            )

        # Get authenticated tenant (already validated by @require_tenant)
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized: no valid JWT"}), 403

        tenant = claims.get("tenant")

        # If request includes a tenant field, it must match the authenticated tenant
        if request_tenant and request_tenant != tenant:
            return (
                jsonify({"error": "Tenant mismatch: cannot write to other tenant"}),
                403,
            )

        from quart import current_app

        policy_mgr = current_app.config.get("SWG_POLICY_MANAGER")
        if not policy_mgr:
            return jsonify({"error": "SWG policy manager not configured"}), 500

        # Set the policy under the authenticated tenant
        await policy_mgr.set_policy(tenant, scope, scope_id, category, action)

        return (
            jsonify({
                "status": "success",
                "tenant": tenant,
                "scope": scope,
                "category": category,
                "action": action,
            }),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Set policy failed: {str(e)}"}), 500
