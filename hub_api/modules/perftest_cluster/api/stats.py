"""WaddlePerf performance statistics REST API blueprint."""
from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from quart import Blueprint, request

from hub_api.auth.middleware import current_claims, require_scope, require_tenant
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from hub_api.modules.perftest_cluster.services.stats_manager import StatsManager

logger = structlog.get_logger()

blueprint = Blueprint("wpc_stats", __name__, url_prefix="/stats")


@blueprint.route("/summary", methods=["GET"])
@require_tenant
@require_scope("stats:read")
@require_feature("perftest_cluster", "stats")
async def get_summary() -> tuple[dict[str, Any], int]:
    """Get overall statistics summary.

    Query parameters:
        start_date: Filter by start date (ISO format, optional)
        end_date: Filter by end date (ISO format, optional)

    Required scope: stats:read
    Required feature: perftest_cluster.stats

    Returns:
        JSON response with overall statistics and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        start_date = request.args.get("start_date", None, type=str)
        end_date = request.args.get("end_date", None, type=str)

        db = get_db()
        mgr = StatsManager(db, tenant_id)
        await mgr.initialize()

        summary = await mgr.summary(start_date=start_date, end_date=end_date)

        logger.info(
            "stats_summary_retrieved",
            total_tests=summary.get("total_tests"),
            tenant=tenant_id,
        )

        return (
            {
                "summary": summary,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_summary_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/by-device", methods=["GET"])
@require_tenant
@require_scope("stats:read")
@require_feature("perftest_cluster", "stats")
async def get_by_device() -> tuple[dict[str, Any], int]:
    """Get statistics aggregated by device.

    Query parameters:
        start_date: Filter by start date (ISO format, optional)
        end_date: Filter by end date (ISO format, optional)
        limit: Maximum number of devices (default: 50)

    Required scope: stats:read
    Required feature: perftest_cluster.stats

    Returns:
        JSON response with per-device statistics and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        start_date = request.args.get("start_date", None, type=str)
        end_date = request.args.get("end_date", None, type=str)
        limit = request.args.get("limit", 50, type=int)

        db = get_db()
        mgr = StatsManager(db, tenant_id)
        await mgr.initialize()

        stats = await mgr.by_device(
            start_date=start_date, end_date=end_date, limit=limit
        )

        logger.info(
            "stats_by_device_retrieved",
            count=len(stats),
            tenant=tenant_id,
        )

        return (
            {
                "by_device": stats,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_by_device_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/by-type", methods=["GET"])
@require_tenant
@require_scope("stats:read")
@require_feature("perftest_cluster", "stats")
async def get_by_type() -> tuple[dict[str, Any], int]:
    """Get statistics aggregated by test type.

    Query parameters:
        start_date: Filter by start date (ISO format, optional)
        end_date: Filter by end date (ISO format, optional)
        limit: Maximum number of test types (default: 50)

    Required scope: stats:read
    Required feature: perftest_cluster.stats

    Returns:
        JSON response with per-test-type statistics and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        start_date = request.args.get("start_date", None, type=str)
        end_date = request.args.get("end_date", None, type=str)
        limit = request.args.get("limit", 50, type=int)

        db = get_db()
        mgr = StatsManager(db, tenant_id)
        await mgr.initialize()

        stats = await mgr.by_type(
            start_date=start_date, end_date=end_date, limit=limit
        )

        logger.info(
            "stats_by_type_retrieved",
            count=len(stats),
            tenant=tenant_id,
        )

        return (
            {
                "by_type": stats,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_by_type_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/trends", methods=["GET"])
@require_tenant
@require_scope("stats:read")
@require_feature("perftest_cluster", "stats")
async def get_trends() -> tuple[dict[str, Any], int]:
    """Get time-series data for trends analysis.

    Query parameters:
        start_date: Filter by start date (ISO format, optional)
        end_date: Filter by end date (ISO format, optional)
        interval: Time interval (hourly, daily, weekly) (default: daily)
        metric: Metric to trend (success_rate, avg_latency, count) (default: success_rate)

    Required scope: stats:read
    Required feature: perftest_cluster.stats

    Returns:
        JSON response with time-series data and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        start_date = request.args.get("start_date", None, type=str)
        end_date = request.args.get("end_date", None, type=str)
        interval = request.args.get("interval", "daily", type=str)
        metric = request.args.get("metric", "success_rate", type=str)

        db = get_db()
        mgr = StatsManager(db, tenant_id)
        await mgr.initialize()

        trends = await mgr.trends(
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            metric=metric,
        )

        logger.info(
            "stats_trends_retrieved",
            interval=interval,
            metric=metric,
            tenant=tenant_id,
        )

        return (
            {
                "trends": trends,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_trends_failed", error=str(e))
        return {"error": "Internal server error"}, 500


@blueprint.route("/recent", methods=["GET"])
@require_tenant
@require_scope("stats:read")
@require_feature("perftest_cluster", "stats")
async def get_recent() -> tuple[dict[str, Any], int]:
    """Get recent test results.

    Query parameters:
        device_id: Filter by device ID (optional)
        limit: Number of recent tests to return (default: 20, max: 100)

    Required scope: stats:read
    Required feature: perftest_cluster.stats

    Returns:
        JSON response with recent test results and meta
    """
    try:
        claims = current_claims()
        if not claims:
            return {"error": "Unauthorized"}, 403

        tenant_id = claims["tenant"]
        device_id = request.args.get("device_id", None, type=str)
        limit = request.args.get("limit", 20, type=int)

        # Cap at 100
        if limit > 100:
            limit = 100

        db = get_db()
        mgr = StatsManager(db, tenant_id)
        await mgr.initialize()

        recent = await mgr.recent(device_id=device_id, limit=limit)

        logger.info(
            "stats_recent_retrieved",
            count=len(recent),
            tenant=tenant_id,
        )

        return (
            {
                "recent": recent,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )

    except Exception as e:
        logger.error("get_recent_failed", error=str(e))
        return {"error": "Internal server error"}, 500
