"""Headend policy endpoints (firewall rules, port config).

These endpoints are called by the Go hub-router headend service to fetch
firewall rules and port configurations. They are NOT part of the module system
and run at the app level to bypass tenant/module prefixing.

Auth: Bearer token validated against HEADEND_API_TOKEN environment variable.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from quart import Blueprint, request

from core.db import get_db
from core.modules.sase.auth.user_manager import UserManager
from core.modules.sase.firewall.access_control import AccessControlManager
from core.modules.sase.network.port_manager import PortConfigManager

logger = structlog.get_logger()

# App-level blueprint; registered with url_prefix='/api/v1' in app.py
# This keeps headend endpoints at EXACT flat paths
# (e.g., /api/v1/firewall/rules, NOT /api/v1/sase/firewall/rules)
headend_bp = Blueprint("headend", __name__, url_prefix="")


def _verify_headend_token(token: str | None) -> bool:
    """Verify headend API token using constant-time comparison.

    Args:
        token: The Bearer token to verify.

    Returns:
        True if token matches HEADEND_API_TOKEN, False otherwise.
    """
    expected = os.getenv("HEADEND_API_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


def _extract_bearer_token() -> str | None:
    """Extract Bearer token from Authorization header.

    Returns:
        Token string if present, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]


def get_access_control_manager(db: Any) -> AccessControlManager:
    """Get access control manager instance.

    Args:
        db: penguin-dal DAL instance.

    Returns:
        AccessControlManager bound to the database.
    """
    return AccessControlManager(db)


def get_user_manager(db: Any) -> UserManager:
    """Get user manager instance.

    Args:
        db: penguin-dal DAL instance.

    Returns:
        UserManager bound to the database.
    """
    return UserManager(db)


def get_port_config_manager(db: Any) -> PortConfigManager:
    """Get port config manager instance.

    Args:
        db: penguin-dal DAL instance.

    Returns:
        PortConfigManager bound to the database.
    """
    return PortConfigManager(db)


@headend_bp.route("/firewall/rules", methods=["GET"])
async def get_firewall_rules() -> tuple[dict[str, Any], int]:
    """Get all firewall rules for headend consumption.

    Requires headend authentication via Bearer token (HEADEND_API_TOKEN).
    Returns rules for all active users across all tenants.

    Returns:
        - 200: {timestamp, rules_count, user_rules: {user_id: [rules]}}
        - 401: {error: "..."} if auth fails
        - 500: {error: "..."} on server error
    """
    try:
        # Authenticate headend
        token = _extract_bearer_token()
        if not _verify_headend_token(token):
            return {"error": "Unauthorized: invalid headend token"}, 401

        db = get_db()
        if db is None:
            return {"error": "Database unavailable"}, 500

        # Get managers
        acm = get_access_control_manager(db)
        um = get_user_manager(db)

        # Note: In a true multi-tenant setup, iterate all tenant configs
        # For now, use default tenant (headend clients can provide via env)
        tenant = "default"

        # Get all active users in the default tenant
        users = await um.list_users(tenant)
        all_rules: dict[str, Any] = {}

        # Export rules for each active user
        for user in users:
            if user.is_active:
                try:
                    user_rules = await acm.export_user_rules(user.id, tenant)
                    all_rules[user.id] = user_rules
                except Exception as e:
                    logger.warning(
                        "failed_to_export_user_rules",
                        user_id=user.id,
                        error=str(e),
                    )
                    # Continue with other users on partial failure

        response = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rules_count": len(all_rules),
            "user_rules": all_rules,
        }

        logger.info("firewall_rules_served", rules_count=len(all_rules))
        return response, 200

    except Exception as e:
        logger.error("firewall_rules_error", error=str(e))
        return {"error": "Failed to get firewall rules"}, 500


@headend_bp.route("/headend/<headend_id>/ports", methods=["GET"])
async def get_headend_ports(headend_id: str) -> tuple[dict[str, Any], int]:
    """Get port configuration for a specific headend.

    Requires headend authentication via Bearer token (HEADEND_API_TOKEN).
    Optional query param: cluster_id (defaults to "cluster-{headend_id}").

    Args:
        headend_id: ID of the headend.

    Returns:
        - 200: {headend_id, cluster_id, tcp_ranges, udp_ranges, ...}
        - 401: {error: "..."} if auth fails
        - 404: {error: "..."} if no config found
        - 500: {error: "..."} on server error
    """
    try:
        # Authenticate headend
        token = _extract_bearer_token()
        if not _verify_headend_token(token):
            return {"error": "Unauthorized: invalid headend token"}, 401

        db = get_db()
        if db is None:
            return {"error": "Database unavailable"}, 500

        # Get tenant and cluster from query params
        # Note: tenant should be derived from headend config in multi-tenant
        # For now, use default tenant
        tenant = request.args.get("tenant", "default")
        cluster_id = request.args.get("cluster_id", f"cluster-{headend_id}")

        pcm = get_port_config_manager(db)
        config = await pcm.get_headend_config(headend_id, tenant)

        if not config:
            logger.warning(
                "headend_config_not_found",
                headend_id=headend_id,
                cluster_id=cluster_id,
                tenant=tenant,
            )
            return {"error": "No port configuration found"}, 404

        # Build response matching py4web contract
        tcp_ranges_str = _get_tcp_ranges_string(config.tcp_ranges)
        udp_ranges_str = _get_udp_ranges_string(config.udp_ranges)
        tcp_detail = [_port_range_to_dict(pr) for pr in config.tcp_ranges]
        udp_detail = [_port_range_to_dict(pr) for pr in config.udp_ranges]
        updated_at = config.updated_at.isoformat() if config.updated_at else None

        response = {
            "headend_id": config.headend_id,
            "cluster_id": config.cluster_id,
            "tcp_ranges": tcp_ranges_str,
            "udp_ranges": udp_ranges_str,
            "tcp_ranges_detail": tcp_detail,
            "udp_ranges_detail": udp_detail,
            "updated_at": updated_at,
        }

        logger.info(
            "headend_ports_served",
            headend_id=headend_id,
            cluster_id=cluster_id,
            tcp_count=len(config.tcp_ranges),
            udp_count=len(config.udp_ranges),
        )
        return response, 200

    except Exception as e:
        logger.error(
            "headend_ports_error",
            headend_id=headend_id,
            error=str(e),
        )
        return {"error": "Failed to get port configuration"}, 500


def _get_tcp_ranges_string(ranges: list[Any]) -> str:
    """Convert TCP port ranges to comma-separated string.

    Args:
        ranges: List of PortRangeConfig objects.

    Returns:
        Comma-separated string like "80,443-8000,8443" or empty string.
    """
    if not ranges:
        return ""
    parts = []
    for r in ranges:
        if r.start_port == r.end_port:
            parts.append(str(r.start_port))
        else:
            parts.append(f"{r.start_port}-{r.end_port}")
    return ",".join(parts)


def _get_udp_ranges_string(ranges: list[Any]) -> str:
    """Convert UDP port ranges to comma-separated string.

    Args:
        ranges: List of PortRangeConfig objects.

    Returns:
        Comma-separated string like "53,5353-5400" or empty string.
    """
    if not ranges:
        return ""
    parts = []
    for r in ranges:
        if r.start_port == r.end_port:
            parts.append(str(r.start_port))
        else:
            parts.append(f"{r.start_port}-{r.end_port}")
    return ",".join(parts)


def _port_range_to_dict(port_range: Any) -> dict[str, Any]:
    """Convert PortRangeConfig to dictionary.

    Args:
        port_range: PortRangeConfig object.

    Returns:
        Dictionary representation of the port range.
    """
    return {
        "id": port_range.id,
        "start_port": port_range.start_port,
        "end_port": port_range.end_port,
        "protocol": port_range.protocol.value,
        "description": port_range.description,
        "enabled": port_range.enabled,
        "created_at": port_range.created_at.isoformat(),
        "updated_at": port_range.updated_at.isoformat(),
    }
