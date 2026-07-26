"""WaddlePerf organizational units REST API blueprint."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_cluster.services.org_unit_manager import OrgUnitManager

logger = structlog.get_logger()

blueprint = Blueprint("wpc_org_units", __name__, url_prefix="/org-units")


@blueprint.route("", methods=["POST"])
@require_tenant
@require_scope("org_units:write")
@require_feature("perftest_cluster", "org_units")
async def create_org_unit() -> tuple[dict[str, Any], int]:
    """Create a new organizational unit.

    Required scope: org_units:write
    Required feature: perftest_cluster.org_units

    JSON body:
        name: OU name (required)
        parent_id: Parent OU ID (optional)
        description: OU description (optional)
        is_active: Active status (optional, default: true)

    Returns:
        JSON response with created OU and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data or "name" not in data:
            return {"error": "Missing required field: name"}, 400

        db = get_db()
        mgr = OrgUnitManager(db, tenant_id)
        await mgr.initialize()

        ou = await mgr.create_ou(
            {
                "name": data["name"],
                "parent_id": data.get("parent_id"),
                "description": data.get("description"),
                "is_active": data.get("is_active", True),
            }
        )

        logger.info(
            "org_unit_created",
            ou_id=ou.id,
            tenant=tenant_id,
        )

        return (
            {
                "id": ou.id,
                "tenant": ou.tenant,
                "name": ou.name,
                "parent_id": ou.parent_id,
                "description": ou.description,
                "is_active": ou.is_active,
                "created_at": ou.created_at.isoformat(),
                "updated_at": ou.updated_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        logger.error("create_org_unit_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("org_units:read")
@require_feature("perftest_cluster", "org_units")
async def list_org_units() -> tuple[dict[str, Any], int]:
    """List all organizational units for the tenant.

    Query parameters:
        parent_id: Filter by parent OU ID (optional)
        limit: Maximum number of results (default: 100)
        offset: Pagination offset (default: 0)

    Required scope: org_units:read
    Required feature: perftest_cluster.org_units

    Returns:
        JSON response with list of OUs and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        parent_id = request.args.get("parent_id", None, type=str)
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        db = get_db()
        mgr = OrgUnitManager(db, tenant_id)
        await mgr.initialize()

        ous = await mgr.list_ous(parent_id=parent_id, limit=limit, offset=offset)

        ou_list = [
            {
                "id": ou.id,
                "tenant": ou.tenant,
                "name": ou.name,
                "parent_id": ou.parent_id,
                "description": ou.description,
                "is_active": ou.is_active,
                "created_at": ou.created_at.isoformat(),
                "updated_at": ou.updated_at.isoformat(),
            }
            for ou in ous
        ]

        logger.info(
            "org_units_listed",
            count=len(ou_list),
            tenant=tenant_id,
            parent_id=parent_id,
        )

        return (
            {
                "org_units": ou_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_org_units_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<ou_id>", methods=["GET"])
@require_tenant
@require_scope("org_units:read")
@require_feature("perftest_cluster", "org_units")
async def get_org_unit(ou_id: str) -> tuple[dict[str, Any], int]:
    """Get organizational unit details.

    Args:
        ou_id: OU identifier

    Required scope: org_units:read
    Required feature: perftest_cluster.org_units

    Returns:
        JSON response with OU details and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        mgr = OrgUnitManager(db, tenant_id)
        await mgr.initialize()

        ou = await mgr.get_ou(ou_id)

        if not ou:
            return {"error": "Organizational unit not found"}, 404

        logger.info(
            "org_unit_retrieved",
            ou_id=ou_id,
            tenant=tenant_id,
        )

        return (
            {
                "id": ou.id,
                "tenant": ou.tenant,
                "name": ou.name,
                "parent_id": ou.parent_id,
                "description": ou.description,
                "is_active": ou.is_active,
                "created_at": ou.created_at.isoformat(),
                "updated_at": ou.updated_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_org_unit_failed", ou_id=ou_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<ou_id>", methods=["PUT"])
@require_tenant
@require_scope("org_units:write")
@require_feature("perftest_cluster", "org_units")
async def update_org_unit(ou_id: str) -> tuple[dict[str, Any], int]:
    """Update organizational unit.

    Args:
        ou_id: OU identifier

    JSON body:
        name: OU name (optional)
        parent_id: Parent OU ID (optional)
        description: OU description (optional)
        is_active: Active status (optional)

    Required scope: org_units:write
    Required feature: perftest_cluster.org_units

    Returns:
        JSON response with updated OU and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data:
            return {"error": "Request body is required"}, 400

        db = get_db()
        mgr = OrgUnitManager(db, tenant_id)
        await mgr.initialize()

        ou = await mgr.update_ou(ou_id, data)

        if not ou:
            return {"error": "Organizational unit not found"}, 404

        logger.info(
            "org_unit_updated",
            ou_id=ou_id,
            tenant=tenant_id,
        )

        return (
            {
                "id": ou.id,
                "tenant": ou.tenant,
                "name": ou.name,
                "parent_id": ou.parent_id,
                "description": ou.description,
                "is_active": ou.is_active,
                "created_at": ou.created_at.isoformat(),
                "updated_at": ou.updated_at.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("update_org_unit_failed", ou_id=ou_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<ou_id>", methods=["DELETE"])
@require_tenant
@require_scope("org_units:write")
@require_feature("perftest_cluster", "org_units")
async def delete_org_unit(ou_id: str) -> tuple[dict[str, Any], int]:
    """Delete organizational unit.

    Args:
        ou_id: OU identifier

    Required scope: org_units:write
    Required feature: perftest_cluster.org_units

    Returns:
        JSON response with status and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        mgr = OrgUnitManager(db, tenant_id)
        await mgr.initialize()

        success = await mgr.delete_ou(ou_id)

        if not success:
            return {"error": "Organizational unit not found"}, 404

        logger.info(
            "org_unit_deleted",
            ou_id=ou_id,
            tenant=tenant_id,
        )

        return (
            {
                "message": "Organizational unit deleted",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("delete_org_unit_failed", ou_id=ou_id, error=str(e))
        return {"error": "Internal server error"}, 500
