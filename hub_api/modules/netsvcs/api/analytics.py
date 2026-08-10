"""Analytics blueprint for netsvcs module."""
from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from quart import Blueprint, jsonify, request

from hub_api.auth.middleware import (
    current_claims,
    require_scope,
    require_tenant,
)
from hub_api.db import get_db
from hub_api.entitlements.gate import require_feature
from quart_schema import validate_response, tag

logger = structlog.get_logger()

analytics_bp = Blueprint("netsvcs_analytics", __name__, url_prefix="/analytics")


# Response DTOs
@dataclass(slots=True)
class QueryTimelineEntry:
    """Query timeline entry DTO."""

    timestamp: str
    queries: int


@dataclass(slots=True)
class QueriesAnalyticsResponse:
    """Queries analytics response."""

    total_queries: int
    total_cache_hits: int
    total_errors: int
    cache_hit_rate: float
    timeline: list[QueryTimelineEntry]
    meta: dict[str, Any]


@dataclass(slots=True)
class PerformanceMetric:
    """Performance metric DTO."""

    metric: str
    value: float


@dataclass(slots=True)
class PerformanceAnalyticsResponse:
    """Performance analytics response."""

    metrics: list[PerformanceMetric]
    meta: dict[str, Any]


@dataclass(slots=True)
class ServerSummaryEntry:
    """Server summary entry DTO."""

    server_id: str
    server_name: str
    queries: int
    cache_hits: int
    errors: int
    avg_response_ms: float


@dataclass(slots=True)
class ServersAnalyticsResponse:
    """Servers analytics response."""

    servers: list[ServerSummaryEntry]
    meta: dict[str, Any]


@dataclass(slots=True)
class SummaryMetric:
    """Summary metric DTO."""

    key: str
    value: int


@dataclass(slots=True)
class SummaryAnalyticsResponse:
    """Summary analytics response."""

    metrics: list[SummaryMetric]
    meta: dict[str, Any]


@analytics_bp.route("/queries", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "analytics")
@validate_response(QueriesAnalyticsResponse)
async def get_queries_analytics() -> tuple[dict[str, Any], int]:
    """Get query analytics for this tenant.

    Query parameters:
        hours: Number of hours to look back (default 24)

    Returns:
        JSON response with query totals and timeline.
    """
    db = get_db()
    tenant_id = current_claims()["tenant"]
    try:

        # Get hours from query param
        hours_str = request.args.get("hours", "24")
        try:
            hours = int(hours_str)
        except (ValueError, TypeError):
            hours = 24

        # Calculate time cutoff
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Fetch metrics for this tenant
        rowset = await db(
            (db.dns_server_metrics.tenant == tenant_id)
            & (db.dns_server_metrics.timestamp >= cutoff)
        ).select()

        total_queries = 0
        total_cache_hits = 0
        total_errors = 0

        # Aggregate metrics by hour for timeline
        timeline_dict: dict[str, dict[str, int]] = {}
        for row in rowset:
            total_queries += row.queries_total
            total_cache_hits += row.cache_hits
            total_errors += row.errors

            # Group by hour
            hour_key = row.timestamp.replace(minute=0, second=0, microsecond=0)
            hour_str = hour_key.isoformat()
            if hour_str not in timeline_dict:
                timeline_dict[hour_str] = {"queries": 0}
            timeline_dict[hour_str]["queries"] += row.queries_total

        # Convert to timeline list
        timeline = [
            QueryTimelineEntry(timestamp=k, queries=v["queries"])
            for k, v in sorted(timeline_dict.items())
        ]

        # Calculate cache hit rate
        cache_hit_rate = (
            (total_cache_hits / total_queries * 100)
            if total_queries > 0
            else 0.0
        )

        return (
            {
                "total_queries": total_queries,
                "total_cache_hits": total_cache_hits,
                "total_errors": total_errors,
                "cache_hit_rate": cache_hit_rate,
                "timeline": timeline,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("get_queries_analytics_error", error=str(e), tenant=tenant_id)
        return jsonify({"error": "Internal server error"}), 500


@analytics_bp.route("/performance", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "analytics")
@validate_response(PerformanceAnalyticsResponse)
async def get_performance_analytics() -> tuple[dict[str, Any], int]:
    """Get performance analytics for this tenant.

    Query parameters:
        hours: Number of hours to look back (default 24)

    Returns:
        JSON response with performance metrics (avg, min, max, percentiles).
    """
    db = get_db()
    tenant_id = current_claims()["tenant"]
    try:

        # Get hours from query param
        hours_str = request.args.get("hours", "24")
        try:
            hours = int(hours_str)
        except (ValueError, TypeError):
            hours = 24

        # Calculate time cutoff
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Fetch metrics for this tenant
        rowset = await db(
            (db.dns_server_metrics.tenant == tenant_id)
            & (db.dns_server_metrics.timestamp >= cutoff)
        ).select()

        response_times = [row.avg_response_ms for row in rowset]

        # Calculate metrics
        if response_times:
            avg_response = sum(response_times) / len(response_times)
            min_response = min(response_times)
            max_response = max(response_times)

            # Simple percentile calculation (sorted list)
            sorted_times = sorted(response_times)
            p50_idx = int(len(sorted_times) * 0.5)
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)

            p50 = sorted_times[p50_idx] if p50_idx < len(sorted_times) else 0.0
            p95 = sorted_times[p95_idx] if p95_idx < len(sorted_times) else 0.0
            p99 = sorted_times[p99_idx] if p99_idx < len(sorted_times) else 0.0
        else:
            avg_response = min_response = max_response = p50 = p95 = p99 = 0.0

        metrics = [
            PerformanceMetric(metric="avg_response_ms", value=avg_response),
            PerformanceMetric(metric="min_response_ms", value=min_response),
            PerformanceMetric(metric="max_response_ms", value=max_response),
            PerformanceMetric(metric="p50_response_ms", value=p50),
            PerformanceMetric(metric="p95_response_ms", value=p95),
            PerformanceMetric(metric="p99_response_ms", value=p99),
        ]

        return (
            {
                "metrics": metrics,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("get_performance_analytics_error", error=str(e), tenant=tenant_id)
        return jsonify({"error": "Internal server error"}), 500


@analytics_bp.route("/servers", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "analytics")
@validate_response(ServersAnalyticsResponse)
async def get_servers_analytics() -> tuple[dict[str, Any], int]:
    """Get per-server analytics for this tenant.

    Query parameters:
        hours: Number of hours to look back (default 24)

    Returns:
        JSON response with per-server metrics.
    """
    db = get_db()
    tenant_id = current_claims()["tenant"]
    try:

        # Get hours from query param
        hours_str = request.args.get("hours", "24")
        try:
            hours = int(hours_str)
        except (ValueError, TypeError):
            hours = 24

        # Calculate time cutoff
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Fetch servers for this tenant
        servers_rowset = await db(
            db.dns_servers.tenant == tenant_id,
        ).select()

        servers_by_id = {row.id: row for row in servers_rowset}

        # Fetch metrics for this tenant and time range
        metrics_rowset = await db(
            (db.dns_server_metrics.tenant == tenant_id)
            & (db.dns_server_metrics.timestamp >= cutoff)
        ).select()

        # Aggregate metrics by server
        server_stats: dict[str, dict[str, Any]] = {}
        for metric_row in metrics_rowset:
            server_id = metric_row.server_id
            if server_id not in server_stats:
                server_stats[server_id] = {
                    "queries": 0,
                    "cache_hits": 0,
                    "errors": 0,
                    "response_times": [],
                }

            server_stats[server_id]["queries"] += metric_row.queries_total
            server_stats[server_id]["cache_hits"] += metric_row.cache_hits
            server_stats[server_id]["errors"] += metric_row.errors
            server_stats[server_id]["response_times"].append(
                metric_row.avg_response_ms
            )

        # Build response
        servers_list = []
        for server_id, server in servers_by_id.items():
            stats = server_stats.get(server_id, {})
            avg_response = (
                sum(stats.get("response_times", [])) / len(stats.get("response_times", []))
                if stats.get("response_times")
                else 0.0
            )

            servers_list.append(
                ServerSummaryEntry(
                    server_id=server.id,
                    server_name=server.name,
                    queries=stats.get("queries", 0),
                    cache_hits=stats.get("cache_hits", 0),
                    errors=stats.get("errors", 0),
                    avg_response_ms=avg_response,
                )
            )

        return (
            {
                "servers": servers_list,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("get_servers_analytics_error", error=str(e), tenant=tenant_id)
        return jsonify({"error": "Internal server error"}), 500


@analytics_bp.route("/summary", methods=["GET"])
@tag(["netsvcs"])
@require_tenant
@require_scope("dns:read")
@require_feature("netsvcs", "analytics")
@validate_response(SummaryAnalyticsResponse)
async def get_summary_analytics() -> tuple[dict[str, Any], int]:
    """Get dashboard summary for this tenant.

    Returns:
        JSON response with zone/record/server/query counts for THIS TENANT ONLY.
    """
    db = get_db()
    tenant_id = current_claims()["tenant"]
    try:

        # Count zones for this tenant
        zones_rowset = await db(
            db.dns_zones.tenant == tenant_id,
        ).select()
        zone_count = len(zones_rowset)

        # Count records for this tenant
        records_rowset = await db(
            db.dns_records.tenant == tenant_id,
        ).select()
        record_count = len(records_rowset)

        # Count servers for this tenant
        servers_rowset = await db(
            db.dns_servers.tenant == tenant_id,
        ).select()
        server_count = len(servers_rowset)

        # Sum queries for this tenant (last 24 hours)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        metrics_rowset = await db(
            (db.dns_server_metrics.tenant == tenant_id)
            & (db.dns_server_metrics.timestamp >= cutoff)
        ).select()
        total_queries = sum(row.queries_total for row in metrics_rowset)

        metrics = [
            SummaryMetric(key="zones", value=zone_count),
            SummaryMetric(key="records", value=record_count),
            SummaryMetric(key="servers", value=server_count),
            SummaryMetric(key="queries_24h", value=total_queries),
        ]

        return (
            {
                "metrics": metrics,
                "meta": {
                    "version": 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            200,
        )
    except Exception as e:
        logger.error("get_summary_analytics_error", error=str(e), tenant=tenant_id)
        return jsonify({"error": "Internal server error"}), 500
