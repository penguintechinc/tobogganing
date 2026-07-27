"""Alert rules and channel management REST API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog
from quart import Blueprint, current_app, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import _is_licensed_for_tier, require_feature, tier_of
from hub_api.flags import feature_enabled
from hub_api.notifications.channels import ChannelManager

log = structlog.get_logger(__name__)

alerts_bp = Blueprint("wpc_alerts", __name__, url_prefix="/alerts")


@alerts_bp.route("/rules", methods=["POST"])
@require_tenant
@require_scope("alerts:write")
@require_feature("perftest_cluster", "alerts")
async def create_rule() -> tuple[dict[str, Any], int]:
    """Create an alert rule.

    Required scope: alerts:write
    Required feature: perftest_cluster.alerts

    JSON body:
        name: Rule name (required)
        metric: Metric name (e.g., latency_ms, throughput) (required)
        comparator: gt, gte, lt, lte (required)
        threshold: Threshold value (required)
        window_seconds: Dedup window in seconds (default 300)
        device_id: Device filter (optional)
        test_type: Test type filter (optional)
        channel_id: Notification channel ID (optional)
        enabled: Rule enabled (default true)

    Returns:
        JSON response with created rule
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data:
            return {"error": "Request body is required"}, 400

        # Validate required fields
        if not data.get("name"):
            return {"error": "Missing required field: name"}, 400
        if not data.get("metric"):
            return {"error": "Missing required field: metric"}, 400
        if not data.get("comparator"):
            return {"error": "Missing required field: comparator"}, 400
        if data.get("threshold") is None:
            return {"error": "Missing required field: threshold"}, 400

        # Validate comparator
        if data["comparator"] not in ["gt", "gte", "lt", "lte"]:
            return {"error": "Invalid comparator. Must be one of: gt, gte, lt, lte"}, 400

        # Validate window_seconds
        window_seconds = data.get("window_seconds", 300)
        if window_seconds < 0:
            return {"error": "window_seconds must be non-negative"}, 400

        db = get_db()
        rule_id = str(uuid4())
        now = datetime.now(timezone.utc)

        await db.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant_id,
            name=data["name"],
            metric=data["metric"],
            comparator=data["comparator"],
            threshold=data["threshold"],
            window_seconds=window_seconds,
            device_id=data.get("device_id"),
            test_type=data.get("test_type"),
            channel_id=data.get("channel_id"),
            enabled=data.get("enabled", True),
            created_at=now,
        )

        log.info(
            "alert_rule_created",
            rule_id=rule_id,
            tenant=tenant_id,
            metric=data["metric"],
        )

        return (
            {
                "id": rule_id,
                "name": data["name"],
                "metric": data["metric"],
                "comparator": data["comparator"],
                "threshold": data["threshold"],
                "window_seconds": window_seconds,
                "device_id": data.get("device_id"),
                "test_type": data.get("test_type"),
                "channel_id": data.get("channel_id"),
                "enabled": data.get("enabled", True),
                "created_at": now.isoformat(),
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        log.error("create_rule_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@alerts_bp.route("/rules", methods=["GET"])
@require_tenant
@require_scope("alerts:read")
@require_feature("perftest_cluster", "alerts")
async def list_rules() -> tuple[dict[str, Any], int]:
    """List alert rules for the tenant.

    Returns:
        JSON response with list of rules
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        rules_rowset = await db(
            db.alert_rules.tenant == tenant_id
        ).select()

        rules = []
        for row in rules_rowset:
            rules.append({
                "id": row["id"],
                "name": row["name"],
                "metric": row["metric"],
                "comparator": row["comparator"],
                "threshold": row["threshold"],
                "window_seconds": row["window_seconds"],
                "device_id": row["device_id"],
                "test_type": row["test_type"],
                "channel_id": row["channel_id"],
                "enabled": row["enabled"],
                "created_at": row["created_at"].isoformat(),
            })

        return (
            {
                "rules": rules,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        log.error("list_rules_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@alerts_bp.route("/rules/<rule_id>", methods=["DELETE"])
@require_tenant
@require_scope("alerts:write")
@require_feature("perftest_cluster", "alerts")
async def delete_rule(rule_id: str) -> tuple[dict[str, Any], int]:
    """Delete an alert rule.

    Returns:
        204 No Content or 404
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        # Verify rule belongs to tenant
        rule_rowset = await db(
            (db.alert_rules.id == rule_id) & (db.alert_rules.tenant == tenant_id)
        ).select()

        if not rule_rowset.first():
            return {"error": "Not found"}, 404

        await db(
            (db.alert_rules.id == rule_id) & (db.alert_rules.tenant == tenant_id)
        ).delete()

        log.info("alert_rule_deleted", rule_id=rule_id, tenant=tenant_id)

        return "", 204

    except Exception as e:
        log.error("delete_rule_failed", rule_id=rule_id, error=str(e))
        return {"error": "Internal server error"}, 500


@alerts_bp.route("/events", methods=["GET"])
@require_tenant
@require_scope("alerts:read")
@require_feature("perftest_cluster", "alerts")
async def list_events() -> tuple[dict[str, Any], int]:
    """List recent alert events for the tenant.

    Returns:
        JSON response with list of events
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        events_rowset = await db(
            db.alert_events.tenant == tenant_id
        ).select()

        events = []
        for row in events_rowset:
            events.append({
                "id": row["id"],
                "rule_id": row["rule_id"],
                "device_id": row["device_id"],
                "observed_value": row["observed_value"],
                "fired_at": row["fired_at"].isoformat(),
                "notified": row["notified"],
            })

        return (
            {
                "events": events,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        log.error("list_events_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@alerts_bp.route("/channels", methods=["POST"])
@require_tenant
@require_scope("alerts:write")
async def create_channel() -> tuple[dict[str, Any], int]:
    """Create a notification channel (email or webhook).

    Email requires: perftest_cluster.alerts
    Webhook requires: perftest_cluster.alert_routing (Professional)

    JSON body:
        name: Channel name (required)
        kind: "email" or "webhook" (required)
        config: Config dict (required)
            email: {"to": ["addr1", "addr2"]}
            webhook: {"url": "https://...", "secret": "..."}
        enabled: Channel enabled (default true)

    Returns:
        JSON response with created channel
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        data = await request.get_json()

        if not data:
            return {"error": "Request body is required"}, 400

        kind = data.get("kind")
        if kind not in ["email", "webhook"]:
            return {"error": "Invalid kind. Must be 'email' or 'webhook'"}, 400

        # Email requires the alerts feature; webhook additionally requires
        # the Professional-tier alert_routing feature.
        if kind == "email":
            if not feature_enabled("perftest_cluster", "alerts"):
                return {"error": "Feature not enabled"}, 402
        elif kind == "webhook":
            if not feature_enabled("perftest_cluster", "alert_routing"):
                return {"error": "Feature not enabled"}, 402

            tier = tier_of("perftest_cluster.alert_routing", current_app.registry)
            if not _is_licensed_for_tier(tier):
                return (
                    {
                        "error": "License required",
                        "message": f"Feature requires {tier} license",
                        "tier": tier,
                    },
                    402,
                )

        # Delegate creation (and config validation) to the channel manager.
        channel_mgr = ChannelManager(get_db())
        try:
            channel = await channel_mgr.create_channel(
                tenant=tenant_id,
                name=data.get("name", ""),
                kind=kind,
                config=data.get("config", {}),
            )
        except ValueError as exc:
            return {"error": str(exc)}, 400

        return (
            {
                **channel,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            201,
        )

    except Exception as e:
        log.error("create_channel_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@alerts_bp.route("/channels", methods=["GET"])
@require_tenant
@require_scope("alerts:read")
async def list_channels() -> tuple[dict[str, Any], int]:
    """List notification channels for the tenant.

    Returns:
        JSON response with list of channels
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        channel_mgr = ChannelManager(db)
        channels = await channel_mgr.list_channels(tenant_id)

        # Channels already have secrets redacted from ChannelManager
        return (
            {
                "channels": channels,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        log.error("list_channels_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@alerts_bp.route("/channels/<channel_id>", methods=["DELETE"])
@require_tenant
@require_scope("alerts:write")
async def delete_channel(channel_id: str) -> tuple[dict[str, Any], int]:
    """Delete a notification channel.

    Returns:
        204 No Content or 404
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        db = get_db()

        channel_mgr = ChannelManager(db)
        success = await channel_mgr.delete_channel(tenant_id, channel_id)

        if not success:
            return {"error": "Not found"}, 404

        log.info("channel_deleted", channel_id=channel_id, tenant=tenant_id)

        return "", 204

    except Exception as e:
        log.error("delete_channel_failed", channel_id=channel_id, error=str(e))
        return {"error": "Internal server error"}, 500
