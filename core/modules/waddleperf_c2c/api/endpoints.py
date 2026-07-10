"""Cluster-to-cluster endpoints REST API blueprint."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, jsonify, request

from core.auth.middleware import current_claims, require_scope, require_tenant
from core.db import get_db
from core.entitlements.gate import require_feature
from core.modules.waddleperf_c2c.services.endpoint_manager import EndpointManager

logger = structlog.get_logger()

blueprint = Blueprint("c2c_endpoints", __name__, url_prefix="/endpoints")


@blueprint.route("", methods=["POST"])
@require_tenant
@require_scope("c2c:write")
@require_feature("waddleperf_c2c", "endpoints")
async def create_endpoint() -> tuple[dict[str, Any], int]:
    """Create a new C2C endpoint.

    Request body:
        {
            "region": "us-west-2",
            "name": "primary-node",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
            "api_key": "optional-key"
        }

    Returns:
        201 with endpoint and raw api_key (if generated).
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        data = await request.get_json()
        region = (data.get("region") or "").strip()
        name = (data.get("name") or "").strip()
        engine_url = (data.get("engine_url") or "").strip()
        target = (data.get("target") or "").strip()
        api_key = data.get("api_key")

        # Validate required fields
        if not region or not name or not engine_url or not target:
            return {
                "error": "Missing required fields",
                "required": ["region", "name", "engine_url", "target"],
            }, 400

        manager = EndpointManager(db, tenant)

        try:
            endpoint, raw_key = manager.create_endpoint(
                region=region,
                name=name,
                engine_url=engine_url,
                target=target,
                api_key=api_key,
            )
        except ValueError as e:
            logger.warning("endpoint_create_duplicate", error=str(e), tenant=tenant)
            return {"error": str(e)}, 409

        # Include raw key only once if generated
        response_data = endpoint.copy()
        if raw_key:
            response_data["api_key"] = raw_key

        logger.info(
            "endpoint_created_api",
            endpoint_id=endpoint["id"],
            region=region,
            tenant=tenant,
        )

        return (
            {
                **response_data,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        logger.error("create_endpoint_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("waddleperf_c2c", "endpoints")
async def list_endpoints() -> tuple[dict[str, Any], int]:
    """List C2C endpoints for the tenant.

    Query params:
        enabled: Optional bool filter (true/false)

    Returns:
        200 with list of endpoints.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        enabled_param = request.args.get("enabled", "").lower()
        enabled_only = enabled_param == "true"

        manager = EndpointManager(db, tenant)
        endpoints = manager.list_endpoints(enabled_only=enabled_only)

        logger.info(
            "endpoints_listed",
            count=len(endpoints),
            enabled_only=enabled_only,
            tenant=tenant,
        )

        return (
            {
                "endpoints": endpoints,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_endpoints_failed", error=str(e), exc_info=True)
        return {"error": "Internal server error"}, 500


@blueprint.route("/<endpoint_id>", methods=["GET"])
@require_tenant
@require_scope("c2c:read")
@require_feature("waddleperf_c2c", "endpoints")
async def get_endpoint(endpoint_id: str) -> tuple[dict[str, Any], int]:
    """Get a C2C endpoint by ID.

    Args:
        endpoint_id: Endpoint identifier.

    Returns:
        200 with endpoint, 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        manager = EndpointManager(db, tenant)
        endpoint = manager.get_endpoint(endpoint_id)

        if not endpoint:
            logger.info(
                "endpoint_not_found",
                endpoint_id=endpoint_id,
                tenant=tenant,
            )
            return {"error": "Endpoint not found"}, 404

        logger.info(
            "endpoint_retrieved",
            endpoint_id=endpoint_id,
            tenant=tenant,
        )

        return (
            {
                **endpoint,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_endpoint_failed", endpoint_id=endpoint_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<endpoint_id>", methods=["PATCH"])
@require_tenant
@require_scope("c2c:write")
@require_feature("waddleperf_c2c", "endpoints")
async def update_endpoint(endpoint_id: str) -> tuple[dict[str, Any], int]:
    """Update a C2C endpoint.

    Request body: any of {name, region, engine_url, target, enabled}

    Returns:
        200 with updated endpoint, 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        data = await request.get_json()
        manager = EndpointManager(db, tenant)

        # Filter to allowed fields
        allowed_fields = {"name", "region", "engine_url", "target", "enabled"}
        update_data = {k: v for k, v in data.items() if k in allowed_fields}

        if not update_data:
            # No valid fields to update; just return current state
            endpoint = manager.get_endpoint(endpoint_id)
            if not endpoint:
                return {"error": "Endpoint not found"}, 404
        else:
            endpoint = manager.update_endpoint(endpoint_id, **update_data)

        if not endpoint:
            logger.info(
                "endpoint_not_found_update",
                endpoint_id=endpoint_id,
                tenant=tenant,
            )
            return {"error": "Endpoint not found"}, 404

        logger.info(
            "endpoint_updated_api",
            endpoint_id=endpoint_id,
            tenant=tenant,
        )

        return (
            {
                **endpoint,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("update_endpoint_failed", endpoint_id=endpoint_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<endpoint_id>", methods=["DELETE"])
@require_tenant
@require_scope("c2c:write")
@require_feature("waddleperf_c2c", "endpoints")
async def delete_endpoint(endpoint_id: str) -> tuple[dict[str, Any] | str, int]:
    """Delete a C2C endpoint.

    Args:
        endpoint_id: Endpoint identifier.

    Returns:
        204 on success, 404 if not found.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant = claims["tenant"]
        db = get_db()

        manager = EndpointManager(db, tenant)
        deleted = manager.delete_endpoint(endpoint_id)

        if not deleted:
            logger.info(
                "endpoint_not_found_delete",
                endpoint_id=endpoint_id,
                tenant=tenant,
            )
            return {"error": "Endpoint not found"}, 404

        logger.info(
            "endpoint_deleted_api",
            endpoint_id=endpoint_id,
            tenant=tenant,
        )

        return "", 204

    except Exception as e:
        logger.error("delete_endpoint_failed", endpoint_id=endpoint_id, error=str(e))
        return {"error": "Internal server error"}, 500
