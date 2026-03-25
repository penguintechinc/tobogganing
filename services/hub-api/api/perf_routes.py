"""Performance metrics API routes for the WaddlePerf fabric telemetry system."""

from datetime import datetime

import structlog
from py4web import action, request, response
from pydantic import ValidationError as PydanticValidationError

from api.schemas.perf import PerfMetricQuery, PerfMetricSubmission
from auth.middleware import require_scope

logger = structlog.get_logger()


def setup_perf_routes(app, db):
    """Register WaddlePerf performance metric routes on the py4web app."""

    @action("api/v1/perf/metrics", method=["POST"])
    @action.uses("json")
    @require_scope("metrics:write")
    async def submit_perf_metrics():
        """Submit a batch of fabric performance metrics from a hub-router or client."""
        try:
            data = await request.json()
        except Exception:
            response.status = 400
            return {"error": "Invalid JSON body"}

        metrics_data = data.get("metrics", [])
        if not metrics_data:
            response.status = 422
            return {"error": "No metrics provided"}

        inserted = 0
        errors = []
        for i, metric in enumerate(metrics_data):
            try:
                validated = PerfMetricSubmission.model_validate(metric)
                db.perf_metrics.insert(
                    source_id=validated.source_id,
                    source_type=validated.source_type,
                    target_id=validated.target_id,
                    protocol=validated.protocol,
                    latency_ms=validated.latency_ms,
                    jitter_ms=validated.jitter_ms,
                    packet_loss_pct=validated.packet_loss_pct,
                    throughput_mbps=validated.throughput_mbps,
                    timestamp=validated.timestamp or datetime.now(),
                )
                inserted += 1
            except PydanticValidationError as exc:
                errors.append({"index": i, "errors": exc.errors()})
            except Exception as exc:  # noqa: BLE001
                errors.append({"index": i, "errors": str(exc)})

        db.commit()

        return {
            "status": "success",
            "data": {"inserted": inserted, "errors": errors},
        }

    @action("api/v1/perf/metrics", method=["GET"])
    @action.uses("json")
    @require_scope("metrics:read")
    async def query_perf_metrics():
        """Query stored fabric performance metrics with optional filters."""
        try:
            params = dict(request.params)
            query_filter = PerfMetricQuery.model_validate(params)
        except PydanticValidationError as exc:
            response.status = 422
            return {"error": "Validation failed", "details": exc.errors()}

        query = db.perf_metrics.id > 0

        if query_filter.cluster_id:
            query &= (db.perf_metrics.source_id == query_filter.cluster_id) | (
                db.perf_metrics.target_id == query_filter.cluster_id
            )
        if query_filter.protocol:
            query &= db.perf_metrics.protocol == query_filter.protocol
        if query_filter.time_range_start:
            query &= db.perf_metrics.timestamp >= query_filter.time_range_start
        if query_filter.time_range_end:
            query &= db.perf_metrics.timestamp <= query_filter.time_range_end

        rows = db(query).select(
            orderby=~db.perf_metrics.timestamp,
            limitby=(0, query_filter.limit),
        )

        metrics = [
            {
                "id": row.id,
                "source_id": row.source_id,
                "source_type": row.source_type,
                "target_id": row.target_id,
                "protocol": row.protocol,
                "latency_ms": row.latency_ms,
                "jitter_ms": row.jitter_ms,
                "packet_loss_pct": row.packet_loss_pct,
                "throughput_mbps": row.throughput_mbps,
                "timestamp": str(row.timestamp) if row.timestamp else None,
            }
            for row in rows
        ]

        return {
            "status": "success",
            "data": {"metrics": metrics},
            "meta": {"count": len(metrics), "limit": query_filter.limit},
        }

    @action("api/v1/perf/summary", method=["GET"])
    @action.uses("json")
    @require_scope("metrics:read")
    async def perf_summary():
        """Return aggregated fabric health summary: latest metrics per source-target pair."""
        rows = db(db.perf_metrics.id > 0).select(
            orderby=~db.perf_metrics.timestamp,
            limitby=(0, 1000),
        )

        summary: dict = {}
        for row in rows:
            key = f"{row.source_id}->{row.target_id}"
            if key not in summary:
                summary[key] = {
                    "source_id": row.source_id,
                    "target_id": row.target_id,
                    "protocols": {},
                }
            if row.protocol not in summary[key]["protocols"]:
                summary[key]["protocols"][row.protocol] = {
                    "latest_latency_ms": row.latency_ms,
                    "latest_jitter_ms": row.jitter_ms,
                    "latest_packet_loss_pct": row.packet_loss_pct,
                    "latest_throughput_mbps": row.throughput_mbps,
                    "last_measured": str(row.timestamp) if row.timestamp else None,
                }

        return {
            "status": "success",
            "data": {"pairs": list(summary.values())},
            "meta": {"pair_count": len(summary)},
        }
