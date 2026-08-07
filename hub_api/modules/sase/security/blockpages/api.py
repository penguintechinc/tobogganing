"""API endpoints for SASE block pages and routing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from quart import Blueprint, jsonify, request, current_app
import structlog

from hub_api.auth.middleware import require_scope, require_tenant, current_claims
from hub_api.entitlements.gate import require_feature

from .models import BlockPage, BlockRoute, PageStatus, RouteDest
from .pages import BlockPageManager
from .routes import BlockRouteManager
from .render import render_block_page

logger = structlog.get_logger()

blueprint = Blueprint("sase_blockpages", __name__, url_prefix="/blockpages")


# Response DTOs (exact fields, no raw model passthrough)


@dataclass(slots=True)
class BlockPageDTO:
    """Response DTO for block page."""

    id: str
    tenant: str
    name: str
    markdown: str
    status: str
    version: int
    created_by: str
    updated_by: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class BlockRouteDTO:
    """Response DTO for block route."""

    id: str
    tenant: str
    source_type: str
    destination_kind: str
    page_id: str | None
    external_url: str | None
    created_at: str
    created_by: str | None
    updated_by: str | None
    ticket: str | None
    notes: str | None
    expiry: str | None
    review_date: str | None
    scope: str | None
    risk: str | None


@dataclass(slots=True)
class BlockPagePreviewDTO:
    """Response DTO for block page preview rendering."""

    html: str
    variables: dict[str, str]


@dataclass(slots=True)
class ExternalRedirectDTO:
    """Response DTO for external redirect with block headers."""

    redirect_url: str
    headers: dict[str, str]


# API Endpoints


@blueprint.route("/pages", methods=["GET"])
@require_tenant
@require_scope("sase:read")
@require_feature("sase", "blockpages")
async def list_pages() -> tuple[dict, int]:
    """List all block pages for the authenticated tenant.

    Returns:
        200 with list of BlockPageDTO
        402 if feature disabled
        403 if unauthorized
    """
    try:
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized"}), 403

        tenant = claims.get("tenant")
        if not tenant:
            return jsonify({"error": "No tenant in claims"}), 403

        db = current_app.config.get("DAL")
        if not db:
            return jsonify({"error": "Database not configured"}), 500

        manager = BlockPageManager(db)
        pages = await manager.list_pages(tenant=tenant)

        pages_dto = [
            {
                "id": p.id,
                "tenant": p.tenant,
                "name": p.name,
                "markdown": p.markdown,
                "status": p.status.value,
                "version": p.version,
                "created_by": p.created_by,
                "updated_by": p.updated_by,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in pages
        ]

        return jsonify({"pages": pages_dto}), 200

    except Exception as e:
        logger.error("failed_to_list_pages", error=str(e))
        return jsonify({"error": "Failed to list pages"}), 500


@blueprint.route("/pages", methods=["POST"])
@require_tenant
@require_scope("sase:write")
@require_feature("sase", "blockpages")
async def create_page() -> tuple[dict, int]:
    """Create a new draft block page.

    Request body:
        name: str - display name
        markdown: str - markdown content

    Returns:
        201 with BlockPageDTO
        400 if invalid input
        402 if feature disabled
        403 if unauthorized
    """
    try:
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized"}), 403

        tenant = claims.get("tenant")
        body_tenant = request.json.get("tenant") if request.json else None

        # Cross-tenant check: body tenant must match or be absent
        if body_tenant and body_tenant != tenant:
            return jsonify({"error": "Tenant mismatch"}), 403

        data = await request.get_json()
        name = data.get("name", "").strip()
        markdown = data.get("markdown", "").strip()

        if not name or not markdown:
            return jsonify({"error": "Missing required fields: name, markdown"}), 400

        db = current_app.config.get("DAL")
        if not db:
            return jsonify({"error": "Database not configured"}), 500

        manager = BlockPageManager(db)
        user_id = claims.get("sub")

        page = await manager.create(
            tenant=tenant,
            name=name,
            markdown=markdown,
            created_by=user_id,
        )

        page_dto = {
            "id": page.id,
            "tenant": page.tenant,
            "name": page.name,
            "markdown": page.markdown,
            "status": page.status.value,
            "version": page.version,
            "created_by": page.created_by,
            "updated_by": page.updated_by,
            "created_at": page.created_at.isoformat(),
            "updated_at": page.updated_at.isoformat(),
        }

        return jsonify(page_dto), 201

    except Exception as e:
        logger.error("failed_to_create_page", error=str(e))
        return jsonify({"error": "Failed to create page"}), 500


@blueprint.route("/pages/<page_id>", methods=["PUT"])
@require_tenant
@require_scope("sase:write")
@require_feature("sase", "blockpages")
async def update_page(page_id: str) -> tuple[dict, int]:
    """Update a block page's markdown.

    Request body:
        markdown: str - new markdown content

    Returns:
        200 with updated BlockPageDTO
        400 if invalid input
        402 if feature disabled
        403 if unauthorized or not found
    """
    try:
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized"}), 403

        tenant = claims.get("tenant")
        data = await request.get_json()
        markdown = data.get("markdown", "").strip()

        if not markdown:
            return jsonify({"error": "Missing markdown"}), 400

        db = current_app.config.get("DAL")
        if not db:
            return jsonify({"error": "Database not configured"}), 500

        manager = BlockPageManager(db)
        user_id = claims.get("sub")

        page = await manager.update(
            tenant=tenant,
            page_id=page_id,
            markdown=markdown,
            updated_by=user_id,
        )

        if not page:
            return jsonify({"error": "Page not found"}), 403

        page_dto = {
            "id": page.id,
            "tenant": page.tenant,
            "name": page.name,
            "markdown": page.markdown,
            "status": page.status.value,
            "version": page.version,
            "created_by": page.created_by,
            "updated_by": page.updated_by,
            "created_at": page.created_at.isoformat(),
            "updated_at": page.updated_at.isoformat(),
        }

        return jsonify(page_dto), 200

    except Exception as e:
        logger.error("failed_to_update_page", page_id=page_id, error=str(e))
        return jsonify({"error": "Failed to update page"}), 500


@blueprint.route("/pages/<page_id>/publish", methods=["POST"])
@require_tenant
@require_scope("sase:write")
@require_feature("sase", "blockpages")
async def publish_page(page_id: str) -> tuple[dict, int]:
    """Publish a draft page to live (bumps version).

    Returns:
        200 with published BlockPageDTO
        402 if feature disabled
        403 if unauthorized or not found
    """
    try:
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized"}), 403

        tenant = claims.get("tenant")

        db = current_app.config.get("DAL")
        if not db:
            return jsonify({"error": "Database not configured"}), 500

        manager = BlockPageManager(db)
        page = await manager.publish(tenant=tenant, page_id=page_id)

        if not page:
            return jsonify({"error": "Page not found"}), 403

        page_dto = {
            "id": page.id,
            "tenant": page.tenant,
            "name": page.name,
            "markdown": page.markdown,
            "status": page.status.value,
            "version": page.version,
            "created_by": page.created_by,
            "updated_by": page.updated_by,
            "created_at": page.created_at.isoformat(),
            "updated_at": page.updated_at.isoformat(),
        }

        return jsonify(page_dto), 200

    except Exception as e:
        logger.error("failed_to_publish_page", page_id=page_id, error=str(e))
        return jsonify({"error": "Failed to publish page"}), 500


@blueprint.route("/pages/<page_id>/preview", methods=["POST"])
@require_tenant
@require_scope("sase:read")
@require_feature("sase", "blockpages")
async def preview_page(page_id: str) -> tuple[dict, int]:
    """Preview a block page with sample variable rendering.

    Request body (optional):
        variables: dict - sample variables for rendering

    Returns:
        200 with BlockPagePreviewDTO (html + variables used)
        403 if unauthorized or not found
    """
    try:
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized"}), 403

        tenant = claims.get("tenant")

        db = current_app.config.get("DAL")
        if not db:
            return jsonify({"error": "Database not configured"}), 500

        manager = BlockPageManager(db)
        page = await manager.get_by_id(tenant=tenant, page_id=page_id)

        if not page:
            return jsonify({"error": "Page not found"}), 403

        # Get variables from request or use defaults
        data = await request.get_json() or {}
        variables = data.get("variables", {}) or {}

        # Fill in missing variables with defaults
        default_vars = {
            "blocked_url": "example.com",
            "category": "Uncategorized",
            "reason": "Content Policy Violation",
            "user": "User",
            "org": "Organization",
            "support_link": "https://example.com/support",
            "appeal_link": "https://example.com/appeal",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        for key, default_value in default_vars.items():
            if key not in variables:
                variables[key] = default_value

        # Render the page
        html = render_block_page(page.markdown, variables)

        preview_dto = {
            "html": html,
            "variables": variables,
        }

        return jsonify(preview_dto), 200

    except Exception as e:
        logger.error("failed_to_preview_page", page_id=page_id, error=str(e))
        return jsonify({"error": "Failed to preview page"}), 500


@blueprint.route("/routes", methods=["GET"])
@require_tenant
@require_scope("sase:read")
@require_feature("sase", "blockpages")
async def get_routes() -> tuple[dict, int]:
    """Get all block routes for the authenticated tenant.

    Returns:
        200 with list of BlockRouteDTO
        402 if feature disabled
        403 if unauthorized
    """
    try:
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized"}), 403

        tenant = claims.get("tenant")

        db = current_app.config.get("DAL")
        if not db:
            return jsonify({"error": "Database not configured"}), 500

        manager = BlockRouteManager(db)
        routes = await manager.get_routes(tenant=tenant)

        routes_dto = [
            {
                "id": r.id,
                "tenant": r.tenant,
                "source_type": r.source_type,
                "destination_kind": r.destination_kind.value,
                "page_id": r.page_id,
                "external_url": r.external_url,
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
                "updated_by": r.updated_by,
                "ticket": r.ticket,
                "notes": r.notes,
                "expiry": r.expiry.isoformat() if r.expiry else None,
                "review_date": r.review_date.isoformat() if r.review_date else None,
                "scope": r.scope,
                "risk": r.risk,
            }
            for r in routes
        ]

        return jsonify({"routes": routes_dto}), 200

    except Exception as e:
        logger.error("failed_to_get_routes", error=str(e))
        return jsonify({"error": "Failed to get routes"}), 500


@blueprint.route("/routes", methods=["PUT"])
@require_tenant
@require_scope("sase:write")
@require_feature("sase", "blockpages")
async def upsert_routes() -> tuple[dict, int]:
    """Set or update block routes (full upsert).

    Request body:
        routes: list of route dicts with source_type, destination_kind, page_id/external_url, metadata

    Returns:
        200 with list of updated BlockRouteDTO
        400 if invalid input
        402 if feature disabled
        403 if unauthorized
    """
    try:
        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized"}), 403

        tenant = claims.get("tenant")
        data = await request.get_json()
        routes_data = data.get("routes", []) if data else []

        if not isinstance(routes_data, list):
            return jsonify({"error": "routes must be a list"}), 400

        db = current_app.config.get("DAL")
        if not db:
            return jsonify({"error": "Database not configured"}), 500

        manager = BlockRouteManager(db)
        user_id = claims.get("sub")
        updated_routes = []

        for route_data in routes_data:
            source_type = route_data.get("source_type")
            destination_kind = route_data.get("destination_kind")
            page_id = route_data.get("page_id")
            external_url = route_data.get("external_url")
            metadata = route_data.get("metadata") or {}

            if not source_type or not destination_kind:
                return jsonify({"error": "Missing source_type or destination_kind"}), 400

            # Validate destination_kind
            try:
                dest_kind = RouteDest(destination_kind)
            except ValueError:
                return jsonify({"error": f"Invalid destination_kind: {destination_kind}"}), 400

            # Add user to metadata
            metadata["created_by"] = metadata.get("created_by", user_id)
            metadata["updated_by"] = user_id

            route = await manager.set_route(
                tenant=tenant,
                source_type=source_type,
                destination_kind=dest_kind,
                page_id=page_id,
                external_url=external_url,
                metadata=metadata,
            )

            route_dto = {
                "id": route.id,
                "tenant": route.tenant,
                "source_type": route.source_type,
                "destination_kind": route.destination_kind.value,
                "page_id": route.page_id,
                "external_url": route.external_url,
                "created_at": route.created_at.isoformat(),
                "created_by": route.created_by,
                "updated_by": route.updated_by,
                "ticket": route.ticket,
                "notes": route.notes,
                "expiry": route.expiry.isoformat() if route.expiry else None,
                "review_date": route.review_date.isoformat() if route.review_date else None,
                "scope": route.scope,
                "risk": route.risk,
            }
            updated_routes.append(route_dto)

        return jsonify({"routes": updated_routes}), 200

    except Exception as e:
        logger.error("failed_to_upsert_routes", error=str(e))
        return jsonify({"error": "Failed to upsert routes"}), 500
