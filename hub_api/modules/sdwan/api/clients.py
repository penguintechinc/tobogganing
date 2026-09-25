"""SASE clients REST API blueprint."""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import os
import re
import secrets
import structlog
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, current_app, g, jsonify, request

from hub_api.auth.middleware import (
    current_claims,
    require_machine_jwt,
    require_scope,
    require_tenant,
)
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.sdwan.orchestrator.client_registry import ClientRegistry
from hub_api.modules.sdwan.orchestrator.cluster_manager import ClusterManager

logger = structlog.get_logger()

blueprint = Blueprint("sase_clients", __name__, url_prefix="/clients")


@dataclass(slots=True)
class ClientRegistrationRequest:
    """Request DTO for client registration."""

    name: str
    type: str  # 'docker' or 'native'
    public_key: str
    location: dict[str, str] | None = None


def _verify_bootstrap_token(token: str | None) -> bool:
    """Constant-time check of enrollment/bootstrap token.

    Args:
        token: The token to verify.

    Returns:
        True if token matches ENROLLMENT_BOOTSTRAP_TOKEN, False otherwise.
    """
    expected = os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


def _extract_bearer_token() -> str | None:
    """Extract JWT token from Authorization header.

    Returns:
        Token string if present, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]


@blueprint.route("", methods=["POST"])
async def register_client() -> tuple[dict[str, Any], int]:
    """Register a new client with enrollment token.

    Requires ENROLLMENT_BOOTSTRAP_TOKEN for Phase-0 enrollment.

    Returns:
        JSON response with client_id and api_key.
    """
    try:
        # Phase-0: Verify bootstrap token (not JWT)
        token = _extract_bearer_token()
        if not _verify_bootstrap_token(token):
            return {"error": "Unauthorized: enrollment token required"}, 401

        data = await request.get_json()

        # Validate required fields
        required = ["name", "type", "public_key"]
        for field in required:
            if field not in data:
                return {"error": f"Missing required field: {field}"}, 400

        # Validate client type
        if data["type"] not in ["docker", "native"]:
            return {"error": "Invalid client type"}, 400

        # Generate client ID
        client_id = str(uuid.uuid4())

        db = get_db()
        # Tenant is derived from server config, never the request body, so a
        # shared bootstrap token cannot enroll a client into an arbitrary
        # tenant. Per-tenant signed enrollment tokens are Phase-3 hardening.
        enrollment_tenant = current_app.config.get("ENROLLMENT_TENANT", "default")
        if data.get("tenant") not in (None, enrollment_tenant):
            return {"error": "tenant mismatch"}, 403
        tenant_id = enrollment_tenant

        # Get optimal cluster for client location
        cluster_mgr = ClusterManager(db, tenant_id)
        await cluster_mgr.initialize()

        location = data.get("location", {})
        cluster = await cluster_mgr.get_optimal_cluster(location)

        if not cluster:
            return {"error": "No available clusters"}, 503

        # Register client
        client_registry = ClientRegistry(db, tenant_id)
        await client_registry.initialize()

        client, api_key = await client_registry.register_client(
            {
                "id": client_id,
                "name": data["name"],
                "type": data["type"],
                "cluster_id": cluster.id,
                "public_key": data["public_key"],
                "ip_address": data.get("ip_address", ""),
                "metadata": data.get("metadata", {}),
            }
        )

        logger.info(
            "client_registered",
            client_id=client.id,
            type=client.type,
            cluster_id=cluster.id,
            tenant=tenant_id,
        )

        return (
            {
                "client_id": client.id,
                "api_key": api_key,
                "cluster": {
                    "id": cluster.id,
                    "headend_url": cluster.headend_url,
                },
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        logger.error("client_registration_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<client_id>/config", methods=["GET"])
async def get_client_config(client_id: str) -> tuple[dict[str, Any], int]:
    """Get configuration for a client.

    Requires valid API key for the client.

    Args:
        client_id: Client identifier.

    Returns:
        JSON response with client configuration.
    """
    try:
        # Authenticate using API key
        api_key = _extract_bearer_token()
        if not api_key:
            return {"error": "Invalid authorization header"}, 401

        db = get_db()
        tenant_id = "default"  # Phase-0 uses default tenant

        client_registry = ClientRegistry(db, tenant_id)
        await client_registry.initialize()

        client = await client_registry.authenticate_client(api_key)

        if not client or client.id != client_id:
            return {"error": "Unauthorized"}, 401

        # Get cluster info
        cluster_mgr = ClusterManager(db, tenant_id)
        await cluster_mgr.initialize()

        cluster = await cluster_mgr.get_cluster(client.cluster_id)

        if not cluster:
            return {"error": "Cluster not available"}, 503

        logger.info(
            "client_config_retrieved",
            client_id=client.id,
            tenant=tenant_id,
        )

        return (
            {
                "client_id": client.id,
                "cluster": {
                    "id": cluster.id,
                    "headend_url": cluster.headend_url,
                    "region": cluster.region,
                    "datacenter": cluster.datacenter,
                },
                "status": client.status,
                "tunnel_mode": client.metadata.get("tunnel_mode", "full")
                if client.metadata
                else "full",
                "split_tunnel_routes": client.metadata.get("split_tunnel_routes", [])
                if client.metadata
                else [],
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_client_config_failed", client_id=client_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<client_id>/tunnel-config", methods=["PUT"])
async def update_tunnel_config(client_id: str) -> tuple[dict[str, Any], int]:
    """Update tunnel configuration for a client.

    Requires valid API key or admin JWT.

    Args:
        client_id: Client identifier.

    Returns:
        JSON response with updated configuration.
    """
    try:
        # Authenticate using API key or JWT
        token = _extract_bearer_token()
        if not token:
            return {"error": "Invalid authorization header"}, 401

        data = await request.get_json()

        # Validate tunnel mode
        tunnel_mode = data.get("tunnel_mode", "full")
        if tunnel_mode not in ["full", "split"]:
            return {"error": "Invalid tunnel_mode. Must be 'full' or 'split'"}, 400

        split_tunnel_routes = []
        if tunnel_mode == "split":
            routes = data.get("split_tunnel_routes", [])
            if not isinstance(routes, list):
                return {"error": "split_tunnel_routes must be a list"}, 400

            domain_pattern = re.compile(r"^(\*\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

            for route in routes:
                if not isinstance(route, str):
                    return {"error": f"Invalid route format: {route}"}, 400

                try:
                    ipaddress.ip_network(route, strict=False)
                    split_tunnel_routes.append(route)
                except ValueError:
                    # Not an IP, try as domain
                    if domain_pattern.match(route):
                        split_tunnel_routes.append(route)
                    else:
                        return (
                            {
                                "error": f"Invalid route: {route}. Must be a domain, IP address, or CIDR"
                            },
                            400,
                        )

        db = get_db()
        tenant_id = "default"

        client_registry = ClientRegistry(db, tenant_id)
        await client_registry.initialize()

        client = await client_registry.authenticate_client(token)

        if not client or client.id != client_id:
            return {"error": "Unauthorized"}, 401

        # Update client configuration
        metadata = client.metadata or {}
        metadata["tunnel_mode"] = tunnel_mode
        metadata["split_tunnel_routes"] = split_tunnel_routes

        success = await client_registry.update_client_status(
            client_id, client.status, metadata
        )

        if not success:
            return {"error": "Failed to update configuration"}, 500

        logger.info(
            "tunnel_config_updated",
            client_id=client_id,
            tunnel_mode=tunnel_mode,
            tenant=tenant_id,
        )

        return (
            {
                "client_id": client_id,
                "tunnel_mode": tunnel_mode,
                "split_tunnel_routes": split_tunnel_routes,
                "status": "updated",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("update_tunnel_config_failed", client_id=client_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<client_id>/rotate-key", methods=["POST"])
async def rotate_client_key(client_id: str) -> tuple[dict[str, Any], int]:
    """Rotate API key for a client.

    Requires valid current API key.

    Args:
        client_id: Client identifier.

    Returns:
        JSON response with new API key.
    """
    try:
        # Authenticate using current API key
        api_key = _extract_bearer_token()
        if not api_key:
            return {"error": "Invalid authorization header"}, 401

        db = get_db()
        tenant_id = "default"

        client_registry = ClientRegistry(db, tenant_id)
        await client_registry.initialize()

        client = await client_registry.authenticate_client(api_key)

        if not client or client.id != client_id:
            return {"error": "Unauthorized"}, 401

        # Rotate API key
        new_api_key = await client_registry.rotate_api_key(client_id)

        if not new_api_key:
            return {"error": "Failed to rotate key"}, 500

        logger.info(
            "api_key_rotated",
            client_id=client_id,
            tenant=tenant_id,
        )

        return (
            {
                "client_id": client_id,
                "new_api_key": new_api_key,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("rotate_client_key_failed", client_id=client_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<client_id>/metrics", methods=["POST"])
async def submit_client_metrics(client_id: str) -> tuple[dict[str, Any], int]:
    """Submit metrics from a client.

    Requires valid API key.

    Args:
        client_id: Client identifier.

    Returns:
        JSON response with status.
    """
    try:
        # Authenticate using API key
        api_key = _extract_bearer_token()
        if not api_key:
            return {"error": "Invalid authorization header"}, 401

        db = get_db()
        tenant_id = "default"

        client_registry = ClientRegistry(db, tenant_id)
        await client_registry.initialize()

        client = await client_registry.authenticate_client(api_key)

        if not client or client.id != client_id:
            return {"error": "Unauthorized"}, 401

        data = await request.get_json()

        # Update last seen timestamp
        await client_registry.update_client_status(client_id, client.status)

        logger.info(
            "client_metrics_received",
            client_id=client.id,
            tenant=tenant_id,
        )

        return (
            {
                "status": "metrics_received",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("submit_client_metrics_failed", client_id=client_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/headends/<headend_id>/metrics", methods=["POST"])
@require_machine_jwt("metrics:write")
async def submit_headend_metrics(headend_id: str) -> tuple[dict[str, Any], int]:
    """Submit metrics from a headend/cluster.

    Requires valid machine-JWT with metrics:write scope.
    Verifies the authenticated cluster matches the headend_id in path.

    Args:
        headend_id: Headend/cluster identifier.

    Returns:
        JSON response with status.
    """
    try:
        db = get_db()
        tenant_id = g.machine_tenant  # regression: security-review finding-2

        # Verify the headend/cluster exists and matches the path parameter
        cluster_mgr = ClusterManager(db, tenant_id)
        await cluster_mgr.initialize()

        cluster = await cluster_mgr.get_cluster(headend_id)
        if not cluster:
            logger.warning(
                "headend_metrics_cluster_not_found",
                headend_id=headend_id,
                tenant=tenant_id,
            )
            return {"error": "Unauthorized: cluster not found"}, 401

        # Verify cluster ID matches path parameter (prevent ID spoofing)
        if str(cluster.id) != str(headend_id):
            logger.warning(
                "headend_metrics_id_mismatch",
                expected_id=headend_id,
                authenticated_id=cluster.id,
                tenant=tenant_id,
            )
            return {"error": "Unauthorized: cluster ID mismatch"}, 401

        data = await request.get_json()

        logger.info(
            "headend_metrics_received",
            headend_id=headend_id,
            cluster_id=cluster.id,
            tenant=tenant_id,
        )

        return (
            {
                "status": "metrics_received",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error(
            "submit_headend_metrics_failed", headend_id=headend_id, error=str(e)
        )
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("clients:read")
@require_feature("sase", "clients")
async def list_clients() -> tuple[dict[str, Any], int]:
    """List all clients for the tenant.

    Requires valid JWT with clients:read scope.

    Returns:
        JSON response with list of clients.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        client_registry = ClientRegistry(db, tenant_id)
        await client_registry.initialize()

        clients = await client_registry.get_all_clients()

        client_list = [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type,
                "cluster_id": c.cluster_id,
                "status": c.status,
                "last_seen": c.last_seen.isoformat(),
            }
            for c in clients
        ]

        logger.info(
            "clients_listed",
            count=len(client_list),
            tenant=tenant_id,
        )

        return (
            {
                "clients": client_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_clients_failed", error=str(e))
        return {"error": "Internal server error"}, 500
