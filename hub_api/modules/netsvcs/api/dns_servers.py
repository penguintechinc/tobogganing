"""DNS servers blueprint for netsvcs module."""
from __future__ import annotations

import asyncio
import hmac
import os
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, current_app, g, jsonify, request

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.auth.middleware import (
    current_claims,
    require_machine_jwt,
    require_scope,
    require_tenant,
)
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.netsvcs.managers.config_service import ConfigService
from hub_api.modules.netsvcs.managers.server_manager import ServerManager
from quart_schema import validate_request, validate_response

logger = structlog.get_logger()

dns_servers_bp = Blueprint("netsvcs_dns_servers", __name__, url_prefix="/dns-servers")


# Response DTOs
@dataclass(slots=True)
class DNSServerResponse:
    """DNS server response DTO."""

    id: str
    name: str
    status: str
    version: str | None
    region: str | None
    hostname: str | None
    last_heartbeat: str | None
    created_at: str


@dataclass(slots=True)
class DNSServersListResponse:
    """List of DNS servers response."""

    servers: list[DNSServerResponse]
    meta: dict[str, Any]


@dataclass(slots=True)
class DNSServerMetricsResponse:
    """DNS server metrics response."""

    server_id: str
    timestamp: str
    queries_total: int
    cache_hits: int
    errors: int
    avg_response_ms: float


@dataclass(slots=True)
class DNSServerMetricsListResponse:
    """List of metrics response."""

    metrics: list[DNSServerMetricsResponse]
    meta: dict[str, Any]


@dataclass(slots=True)
class DNSConfigRecord:
    """DNS config record DTO."""

    name: str
    type: str
    value: str
    ttl: int
    priority: int | None = None
    weight: int | None = None
    port: int | None = None


@dataclass(slots=True)
class DNSConfigZone:
    """DNS config zone DTO."""

    name: str
    visibility: str
    records: list[DNSConfigRecord]


@dataclass(slots=True)
class DNSServerConfigResponse:
    """Server configuration response."""

    zones: list[DNSConfigZone]
    cache_settings: dict[str, Any]
    settings: dict[str, Any]
    version: int


@dataclass(slots=True)
class DNSEnrollmentResponse:
    """Server enrollment response (machine-JWT + config)."""

    server_id: str
    jwt: str
    refresh_token: str
    config: DNSServerConfigResponse


@dataclass(slots=True)
class DNSHeartbeatResponse:
    """Heartbeat response."""

    config_version: int
    should_sync: bool
    timestamp: str
    meta: dict[str, Any]


@dataclass(slots=True)
class DNSRefreshTokenResponse:
    """Refresh token response."""

    access_token: str
    refresh_token: str
    meta: dict[str, Any]


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


@dns_servers_bp.route("", methods=["GET"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "dns_servers")
@validate_response(DNSServersListResponse)
async def list_dns_servers() -> tuple[dict[str, Any], int]:
    """List all DNS servers for the tenant.

    Returns:
        JSON response with list of servers and meta.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ServerManager(db, tenant_id)
        servers = await manager.get_all_servers()

        server_dtos = [
            DNSServerResponse(
                id=s.id,
                name=s.name,
                status=s.status,
                version=s.version,
                region=s.region,
                hostname=s.hostname,
                last_heartbeat=s.last_heartbeat.isoformat() if s.last_heartbeat else None,
                created_at=s.created_at.isoformat(),
            )
            for s in servers
        ]

        return (
            {
                "servers": server_dtos,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("list_dns_servers_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@dns_servers_bp.route("/<server_id>", methods=["GET"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "dns_servers")
@validate_response(DNSServerResponse)
async def get_dns_server(server_id: str) -> tuple[dict[str, Any] | Any, int]:
    """Get details of a specific DNS server.

    Args:
        server_id: Server ID to retrieve

    Returns:
        JSON response with server details.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ServerManager(db, tenant_id)
        server = await manager.get_server(server_id)

        if not server:
            return jsonify({"error": "DNS server not found"}), 404

        return (
            {
                "id": server.id,
                "name": server.name,
                "status": server.status,
                "version": server.version,
                "region": server.region,
                "hostname": server.hostname,
                "last_heartbeat": server.last_heartbeat.isoformat()
                if server.last_heartbeat
                else None,
                "created_at": server.created_at.isoformat(),
            },
            200,
        )
    except Exception as e:
        logger.error("get_dns_server_error", error=str(e), server_id=server_id)
        return jsonify({"error": "Internal server error"}), 500


@dns_servers_bp.route("/<server_id>", methods=["DELETE"])
@require_tenant
@require_scope("dns:write")
@require_feature("netsvcs", "dns_servers")
async def delete_dns_server(server_id: str) -> tuple[dict[str, Any], int]:
    """Delete a DNS server and its metrics.

    Args:
        server_id: Server ID to delete

    Returns:
        JSON response with deletion status.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        manager = ServerManager(db, tenant_id)
        deleted = await manager.delete_server(server_id)

        if not deleted:
            return jsonify({"error": "DNS server not found"}), 404

        return (
            {
                "message": "DNS server deleted successfully",
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("delete_dns_server_error", error=str(e), server_id=server_id)
        return jsonify({"error": "Internal server error"}), 500


@dns_servers_bp.route("/<server_id>/metrics", methods=["GET"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "dns_servers")
@validate_response(DNSServerMetricsListResponse)
async def get_dns_server_metrics(server_id: str) -> tuple[dict[str, Any], int]:
    """Get metrics for a DNS server.

    Query parameters:
        hours: Number of hours to look back (default 24)

    Args:
        server_id: Server ID

    Returns:
        JSON response with metrics list.
    """
    try:
        db = get_db()
        tenant_id = current_claims()["tenant"]

        # Get hours from query param
        hours_str = request.args.get("hours", "24")
        try:
            hours = int(hours_str)
        except (ValueError, TypeError):
            hours = 24

        manager = ServerManager(db, tenant_id)
        metrics = await manager.get_metrics(server_id, hours)

        metric_dtos = [
            DNSServerMetricsResponse(
                server_id=m.server_id,
                timestamp=m.timestamp.isoformat(),
                queries_total=m.queries_total,
                cache_hits=m.cache_hits,
                errors=m.errors,
                avg_response_ms=m.avg_response_ms,
            )
            for m in metrics
        ]

        return (
            {
                "metrics": metric_dtos,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("get_dns_server_metrics_error", error=str(e), server_id=server_id)
        return jsonify({"error": "Internal server error"}), 500


# Node plane routes (machine-JWT auth)


@dns_servers_bp.route("/register", methods=["POST"])
@validate_response(DNSEnrollmentResponse)
async def register_server() -> tuple[dict[str, Any], int]:
    """Register a new DNS resolver server with bootstrap token.

    Requires ENROLLMENT_BOOTSTRAP_TOKEN for enrollment.
    Returns machine-JWT + refresh token for subsequent API calls.

    Returns:
        JSON response with server_id, jwt, refresh_token, and config.
    """
    try:
        # Verify bootstrap token (not JWT)
        token = _extract_bearer_token()
        if not _verify_bootstrap_token(token):
            return jsonify({"error": "Unauthorized: enrollment token required"}), 401

        data = await request.get_json()

        # Validate required fields
        required = ["name", "hostname", "version", "region"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Get DAL and enrollment tenant
        db = get_db()
        enrollment_tenant = current_app.config.get("ENROLLMENT_TENANT", "default")

        # Initialize manager with enrollment tenant
        manager = ServerManager(db, enrollment_tenant)
        await manager.initialize()

        # Register server
        server = await manager.register_server(
            name=data["name"],
            hostname=data["hostname"],
            version=data["version"],
            region=data["region"],
        )

        # Mint machine-JWT
        key_provider = current_app.config.get("KEY_PROVIDER")
        if not key_provider:
            logger.error("key_provider_not_configured")
            return jsonify({"error": "Internal server error"}), 500

        # Build claims (use default aud="headend" required by machine-JWT middleware)
        machine_claims = build_machine_claims(
            sub_id=server.id,
            node_type="dns_resolver",
            tenant=enrollment_tenant,
            iss="tobogganing",
            token_type="access",
        )

        # Encode access token (1 hour)
        access_token = await encode_access_token(
            machine_claims, key_provider, ttl_hours=1
        )

        # Build refresh token claims
        refresh_claims = build_machine_claims(
            sub_id=server.id,
            node_type="dns_resolver",
            tenant=enrollment_tenant,
            iss="tobogganing",
            token_type="refresh",
        )

        # Encode refresh token (24 hours)
        refresh_token = await encode_access_token(
            refresh_claims, key_provider, ttl_hours=24
        )

        # Get initial config
        config_service = ConfigService(db, enrollment_tenant)
        server_config = await config_service.get_server_config()

        logger.info(
            "dns_server_enrolled",
            server_id=server.id,
            name=server.name,
            region=server.region,
            tenant=enrollment_tenant,
        )

        return (
            {
                "server_id": server.id,
                "jwt": access_token,
                "refresh_token": refresh_token,
                "config": {
                    "zones": [
                        {
                            "name": z.name,
                            "visibility": z.visibility,
                            "records": [
                                {
                                    "name": r.name,
                                    "type": r.type,
                                    "value": r.value,
                                    "ttl": r.ttl,
                                    "priority": r.priority,
                                    "weight": r.weight,
                                    "port": r.port,
                                }
                                for r in z.records
                            ],
                        }
                        for z in server_config.zones
                    ],
                    "cache_settings": server_config.cache_settings,
                    "settings": server_config.settings,
                    "version": server_config.version,
                },
            },
            201,
        )

    except Exception as e:
        logger.error("register_server_error", error=str(e))
        return jsonify({"error": "Internal server error"}), 500


@dns_servers_bp.route("/<server_id>/config", methods=["GET"])
@require_machine_jwt("dns:config:read")
@validate_response(DNSServerConfigResponse)
async def get_server_config(server_id: str) -> tuple[dict[str, Any], int]:
    """Get configuration for a DNS resolver server.

    Requires machine-JWT with dns:config:read scope.
    Verifies the machine subject matches the server ID.

    Args:
        server_id: Server ID

    Returns:
        JSON response with zones, records, and config version.
    """
    try:
        # Verify machine identity
        machine_sub = g.machine_sub
        expected_sub = f"resolver:{server_id}"

        if machine_sub != expected_sub:
            logger.warning(
                "config_pull_subject_mismatch",
                expected=expected_sub,
                actual=machine_sub,
            )
            return jsonify({"error": "Forbidden: subject mismatch"}), 403

        tenant_id = g.machine_tenant

        db = get_db()
        config_service = ConfigService(db, tenant_id)

        server_config = await config_service.get_server_config()

        return (
            {
                "zones": [
                    {
                        "name": z.name,
                        "visibility": z.visibility,
                        "records": [
                            {
                                "name": r.name,
                                "type": r.type,
                                "value": r.value,
                                "ttl": r.ttl,
                                "priority": r.priority,
                                "weight": r.weight,
                                "port": r.port,
                            }
                            for r in z.records
                        ],
                    }
                    for z in server_config.zones
                ],
                "cache_settings": server_config.cache_settings,
                "settings": server_config.settings,
                "version": server_config.version,
            },
            200,
        )

    except Exception as e:
        logger.error("get_server_config_error", error=str(e), server_id=server_id)
        return jsonify({"error": "Internal server error"}), 500


@dns_servers_bp.route("/<server_id>/heartbeat", methods=["POST"])
@require_machine_jwt("metrics:write")
@validate_response(DNSHeartbeatResponse)
async def server_heartbeat(server_id: str) -> tuple[dict[str, Any], int]:
    """Record a server heartbeat and ingest metrics.

    Requires machine-JWT with metrics:write scope.
    Verifies the machine subject matches the server ID.

    Request body:
    {
        "queries_total": 1000,
        "cache_hits": 800,
        "errors": 5,
        "avg_response_ms": 12.5
    }

    Args:
        server_id: Server ID

    Returns:
        JSON response with config_version and should_sync flag.
    """
    try:
        # Verify machine identity
        machine_sub = g.machine_sub
        expected_sub = f"resolver:{server_id}"

        if machine_sub != expected_sub:
            logger.warning(
                "heartbeat_subject_mismatch",
                expected=expected_sub,
                actual=machine_sub,
            )
            return jsonify({"error": "Forbidden: subject mismatch"}), 403

        tenant_id = g.machine_tenant

        data = await request.get_json()

        db = get_db()
        manager = ServerManager(db, tenant_id)

        # Record heartbeat
        recorded = await manager.record_heartbeat(server_id, data)

        if not recorded:
            return jsonify({"error": "Server not found"}), 404

        # Get current config version
        config_service = ConfigService(db, tenant_id)
        current_version = await config_service.get_config_version()

        # Determine if server should sync config
        # (server's version is in the request; if they differ, should_sync=True)
        client_version = data.get("config_version", 0)
        should_sync = client_version < current_version

        logger.info(
            "server_heartbeat_received",
            server_id=server_id,
            config_version=current_version,
            should_sync=should_sync,
        )

        return (
            {
                "config_version": current_version,
                "should_sync": should_sync,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("server_heartbeat_error", error=str(e), server_id=server_id)
        return jsonify({"error": "Internal server error"}), 500


@dns_servers_bp.route("/<server_id>/refresh-token", methods=["POST"])
@validate_response(DNSRefreshTokenResponse)
async def refresh_server_token(server_id: str) -> tuple[dict[str, Any], int]:
    """Rotate DNS resolver server tokens with replay protection.

    Requires a machine-JWT with token_type="refresh" and subject="resolver:{server_id}".
    Uses jti-based single-use replay protection.

    Returns:
        JSON response with new access and refresh tokens.
    """
    try:
        # Extract and validate refresh token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized: missing refresh token"}), 401

        refresh_token_str = auth_header[7:].strip()
        if not refresh_token_str:
            return jsonify({"error": "Unauthorized: missing refresh token"}), 401

        key_provider = current_app.config.get("KEY_PROVIDER")
        cache_client = current_app.config.get("CACHE")
        if not key_provider or not cache_client:
            logger.error("key_provider_or_cache_not_configured")
            return jsonify({"error": "Internal server error"}), 500

        # Decode and validate refresh token
        from hub_api.auth.jwt import decode_token

        claims = decode_token(refresh_token_str, key_provider)
        if not claims:
            return jsonify({"error": "Unauthorized: invalid refresh token"}), 401

        # Verify token type is 'refresh'
        if claims.get("token_type") != "refresh":
            return jsonify({"error": "Unauthorized: invalid token type"}), 401

        # Verify subject matches resolver:{server_id}
        subject = claims.get("sub")
        expected_sub = f"resolver:{server_id}"
        if subject != expected_sub:
            logger.warning(
                "refresh_token_subject_mismatch",
                expected=expected_sub,
                actual=subject,
            )
            return jsonify({"error": "Forbidden: subject mismatch"}), 403

        tenant_id = claims.get("tenant")
        if not tenant_id:
            return jsonify({"error": "Unauthorized: missing tenant"}), 401

        # Verify server still exists and is active
        db = get_db()
        manager = ServerManager(db, tenant_id)
        server = await manager.get_server(server_id)
        if not server or server.status != "online":
            logger.warning(
                "refresh_server_not_active",
                server_id=server_id,
                status=server.status if server else "not_found",
            )
            return jsonify({"error": "Server not active"}), 403

        # Check for replay: get current jti from cache
        try:
            cached_jti = await cache_client.get("auth", "refresh", subject, fail_closed=True)
        except Exception as e:
            logger.error("refresh_cache_read_error", error=str(e))
            return jsonify({"error": "Cache unavailable", "retry_with_credentials": True}), 503

        # Verify single-use: current jti must match cached jti
        current_jti = claims.get("jti")
        if cached_jti and cached_jti != current_jti:
            # JTI mismatch: token is stale or replayed
            logger.warning(
                "refresh_replay_detected",
                subject=subject,
                current_jti=current_jti,
                cached_jti=cached_jti,
            )
            # Revoke this subject's refresh tokens
            try:
                await cache_client.delete("auth", "refresh", subject)
            except Exception:
                pass
            return jsonify({"error": "Unauthorized: refresh token superseded"}), 401

        # Mint new access token
        access_claims = build_machine_claims(
            sub_id=server_id,
            node_type="dns_resolver",
            tenant=tenant_id,
            iss=claims.get("iss", "tobogganing"),
            token_type="access",
        )

        new_access_token = await encode_access_token(
            access_claims, key_provider, ttl_hours=1
        )

        # Mint new refresh token
        refresh_claims = build_machine_claims(
            sub_id=server_id,
            node_type="dns_resolver",
            tenant=tenant_id,
            iss=claims.get("iss", "tobogganing"),
            token_type="refresh",
        )

        new_refresh_token = await encode_access_token(
            refresh_claims, key_provider, ttl_hours=24
        )

        # Cache new refresh jti (24 hour TTL)
        new_jti = refresh_claims.get("jti")
        try:
            await cache_client.set("auth", "refresh", subject, value=new_jti, ttl_seconds=86400, fail_closed=True)
        except Exception as e:
            logger.warning("refresh_cache_set_error", error=str(e))
            # Non-fatal: still return new tokens even if cache write fails

        logger.info(
            "server_token_refreshed",
            server_id=server_id,
            tenant=tenant_id,
        )

        return (
            {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("refresh_server_token_error", error=str(e), server_id=server_id)
        return jsonify({"error": "Internal server error"}), 500
