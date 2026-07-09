"""SASE clusters REST API blueprint."""
from __future__ import annotations

import asyncio
import hmac
import os
import secrets
import structlog
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, current_app, jsonify, request

from core.auth.middleware import current_claims, require_scope, require_tenant
from core.db import get_db
from core.entitlements.gate import require_feature
from core.modules.sase.orchestrator.cluster_manager import ClusterManager

logger = structlog.get_logger()

blueprint = Blueprint("sase_clusters", __name__, url_prefix="/clusters")


@dataclass(slots=True)
class ClusterRegistrationRequest:
    """Request DTO for cluster registration."""

    name: str
    region: str
    datacenter: str
    headend_url: str


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
async def register_cluster() -> tuple[dict[str, Any], int]:
    """Register a new cluster with enrollment token.

    Requires ENROLLMENT_BOOTSTRAP_TOKEN for Phase-0 enrollment.
    Enforces Professional tier for >5 node clusters.

    Returns:
        JSON response with cluster_id and status.
    """
    try:
        # Phase-0: Verify bootstrap token (not JWT)
        token = _extract_bearer_token()
        if not _verify_bootstrap_token(token):
            return {"error": "Unauthorized: enrollment token required"}, 401

        data = await request.get_json()

        # Validate required fields
        required = ["name", "region", "datacenter", "headend_url"]
        for field in required:
            if field not in data:
                return {"error": f"Missing required field: {field}"}, 400

        # Generate cluster ID
        cluster_id = str(uuid.uuid4())

        # Get DAL and tenant from bootstrap context
        db = get_db()
        # Tenant is derived from server config, never the request body, so a
        # shared bootstrap token cannot enroll into an arbitrary tenant.
        # Per-tenant signed enrollment tokens are Phase-3 hardening.
        enrollment_tenant = current_app.config.get("ENROLLMENT_TENANT", "default")
        if data.get("tenant") not in (None, enrollment_tenant):
            return {"error": "tenant mismatch"}, 403
        tenant_id = enrollment_tenant

        # Initialize cluster manager with tenant
        mgr = ClusterManager(db, tenant_id)
        await mgr.initialize()

        # Check >5 node gate (Professional tier)
        active_count = await mgr.get_cluster_count()
        if active_count >= 5:
            # Would require Professional entitlement; for now return 402
            return (
                {
                    "error": "License required",
                    "message": "Cluster requires Professional license for >5 nodes",
                    "tier": "professional",
                },
                402,
            )

        # Register cluster
        cluster_obj = await mgr.register_cluster(
            {
                "id": cluster_id,
                "name": data["name"],
                "region": data["region"],
                "datacenter": data["datacenter"],
                "headend_url": data["headend_url"],
                "metadata": data.get("metadata", {}),
            }
        )

        logger.info(
            "cluster_registered",
            cluster_id=cluster_obj.id,
            region=cluster_obj.region,
            datacenter=cluster_obj.datacenter,
            tenant=tenant_id,
        )

        return (
            {
                "cluster_id": cluster_obj.id,
                "status": "registered",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        logger.error("cluster_registration_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<cluster_id>/heartbeat", methods=["POST"])
async def cluster_heartbeat(cluster_id: str) -> tuple[dict[str, Any], int]:
    """Update cluster heartbeat with client count.

    Requires ENROLLMENT_BOOTSTRAP_TOKEN for Phase-0 enrollment.

    Args:
        cluster_id: Cluster identifier.

    Returns:
        JSON response with status.
    """
    try:
        # Phase-0: Verify bootstrap token
        token = _extract_bearer_token()
        if not _verify_bootstrap_token(token):
            return {"error": "Unauthorized: enrollment token required"}, 401

        data = await request.get_json()
        client_count = data.get("client_count", 0)

        db = get_db()
        # Tenant from server config, never the request body (see register_cluster).
        enrollment_tenant = current_app.config.get("ENROLLMENT_TENANT", "default")
        if data.get("tenant") not in (None, enrollment_tenant):
            return {"error": "tenant mismatch"}, 403
        tenant_id = enrollment_tenant

        mgr = ClusterManager(db, tenant_id)
        await mgr.initialize()

        success = await mgr.update_heartbeat(cluster_id, client_count)

        if not success:
            return {"error": "Cluster not found"}, 404

        logger.info(
            "cluster_heartbeat_updated",
            cluster_id=cluster_id,
            client_count=client_count,
            tenant=tenant_id,
        )

        return (
            {
                "status": "ok",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("cluster_heartbeat_failed", cluster_id=cluster_id, error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("", methods=["GET"])
@require_tenant
@require_scope("clusters:read")
@require_feature("sase", "clusters")
async def list_clusters() -> tuple[dict[str, Any], int]:
    """List all clusters for the tenant.

    Requires valid JWT with clusters:read scope.

    Returns:
        JSON response with list of clusters.
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        mgr = ClusterManager(db, tenant_id)
        await mgr.initialize()

        clusters = await mgr.get_all_clusters()

        cluster_list = [
            {
                "id": c.id,
                "name": c.name,
                "region": c.region,
                "datacenter": c.datacenter,
                "status": c.status,
                "client_count": c.client_count,
            }
            for c in clusters
        ]

        logger.info(
            "clusters_listed",
            count=len(cluster_list),
            tenant=tenant_id,
        )

        return (
            {
                "clusters": cluster_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("list_clusters_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/<cluster_id>/headend-config", methods=["GET"])
async def get_headend_config(cluster_id: str) -> tuple[dict[str, Any], int]:
    """Get complete headend configuration for a cluster.

    Requires cluster API key authentication.

    Args:
        cluster_id: Cluster identifier.

    Returns:
        JSON response with headend configuration.
    """
    try:
        # Authenticate using API key (cluster bootstrap token)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return {"error": "Invalid authorization header"}, 401

        api_key = auth_header[7:]

        # For Phase-0, we verify bootstrap token again
        if not _verify_bootstrap_token(api_key):
            return {"error": "Authentication failed"}, 401

        db = get_db()
        tenant_id = "default"  # Phase-0 uses default tenant

        mgr = ClusterManager(db, tenant_id)
        await mgr.initialize()

        cluster = await mgr.get_cluster(cluster_id)
        if not cluster or cluster.id != cluster_id:
            return {"error": "Cluster not found"}, 404

        # Build headend configuration
        config = {
            "cluster_id": cluster.id,
            "http_port": "8443",
            "tcp_port": "8444",
            "udp_port": "8445",
            "metrics_port": "9090",
            "cert_file": "/certs/headend.crt",
            "key_file": "/certs/headend.key",
            "auth": {
                "type": "jwt",
                "manager_url": request.url_root.rstrip("/"),
            },
            "wireguard": {
                "interface": "wg0",
                "listen_port": 51820,
                "network": "10.200.0.0/16",
                "ip_address": "10.200.0.1",
            },
            "mirror": {
                "enabled": False,
                "destinations": [],
                "protocol": "VXLAN",
                "buffer_size": 1000,
                "sample_rate": 100,
                "filter": "",
            },
            "proxy": {
                "skip_tls_verify": False,
                "timeout_seconds": 30,
                "max_idle_conns": 100,
            },
        }

        logger.info(
            "headend_config_provided",
            cluster_id=cluster_id,
            tenant=tenant_id,
        )

        return (
            {
                "config": config,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_headend_config_failed", cluster_id=cluster_id, error=str(e))
        return {"error": "Internal server error"}, 500
