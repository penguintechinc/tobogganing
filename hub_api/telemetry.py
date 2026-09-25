"""OpenTelemetry + Prometheus telemetry bootstrap for hub_api.

Wires the mandatory logs+metrics+traces triad: a Prometheus text-exposition
``/metrics`` endpoint (so the existing hub-api ServiceMonitor and Grafana
dashboards resolve real data) plus OTLP-exported traces, metrics, and log
records. OTLP wiring is entirely env-gated -- an unset or unreachable
collector never breaks request handling (see ``init_otel``).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from quart import Quart, Response, g, request

if TYPE_CHECKING:
    from hub_api.config import Config

from penguintechinc_utils.logging import get_logger

logger = get_logger(__name__)

# Label value identifying this service in every emitted metric/span/log.
# `k8s/helm/tobogganing/templates/monitoring/grafana.yaml`'s PromQL panels
# filter on `service="hub-api"` -- keep this in sync with that value.
SERVICE_LABEL = "hub-api"

# Latency buckets tuned for a JSON API (sub-10ms to multi-second tail).
_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

# Prometheus metric names + label set are load-bearing: the existing
# hub-api Grafana dashboard's PromQL (`grafana.yaml`) matches on these exact
# names plus `service="hub-api"` -- never rename without updating both.
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests handled by hub-api, labeled by matched route rule.",
    labelnames=["service", "method", "route", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, labeled by matched route rule.",
    labelnames=["service", "method", "route", "status"],
    buckets=_DURATION_BUCKETS,
)


def init_metrics(app: Quart) -> None:
    """Register the per-request metric hooks and the ``/metrics`` route.

    Uses the matched route *rule* (e.g. ``/api/v1/devices/<id>``), never the
    raw request path, as a label value -- bounding cardinality against
    path-parameterized routes. Also updates the OTLP metric instruments
    stashed on ``app.config`` by :func:`init_otel`, when OTel is enabled.
    """

    @app.before_request
    async def _telemetry_start_timer() -> None:
        g.telemetry_start_time = time.perf_counter()

    @app.after_request
    async def _telemetry_record_request(response: Response) -> Response:
        route = request.url_rule.rule if request.url_rule is not None else "unmatched"
        started = getattr(g, "telemetry_start_time", None)
        elapsed = time.perf_counter() - started if started is not None else 0.0
        labels = {
            "service": SERVICE_LABEL,
            "method": request.method,
            "route": route,
            "status": str(response.status_code),
        }
        http_requests_total.labels(**labels).inc()
        http_request_duration_seconds.labels(**labels).observe(elapsed)

        otel_counter = app.config.get("OTEL_HTTP_REQUESTS_COUNTER")
        otel_histogram = app.config.get("OTEL_HTTP_DURATION_HISTOGRAM")
        if otel_counter is not None and otel_histogram is not None:
            otel_counter.add(1, attributes=labels)
            otel_histogram.record(elapsed, attributes=labels)

        return response

    @app.route("/metrics", methods=["GET"])
    async def metrics_endpoint() -> tuple[bytes, int, dict[str, str]]:
        """Prometheus text exposition, scraped by the hub-api ServiceMonitor."""
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


def _select_otlp_exporter_classes(protocol: str) -> tuple[type, type, type]:
    """Pick the OTLP exporter classes for the configured wire protocol.

    Returns:
        A ``(SpanExporter, MetricExporter, LogExporter)`` class tuple for
        either ``http/protobuf`` or grpc (the default). Both exporter
        families read ``OTEL_EXPORTER_OTLP_ENDPOINT``/``_HEADERS`` from the
        environment themselves when not passed explicit constructor args.
    """
    # Explicit `type[Any]` locals + uniquely-named imports per branch: mypy
    # --strict flags reusing one alias for two structurally-similar-but-
    # nominally-different classes across if/else branches as an
    # "incompatible import" redefinition otherwise.
    span_exporter_cls: type[Any]
    metric_exporter_cls: type[Any]
    log_exporter_cls: type[Any]

    if protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http._log_exporter import (
            OTLPLogExporter as _HttpLogExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter as _HttpMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as _HttpSpanExporter,
        )

        span_exporter_cls = _HttpSpanExporter
        metric_exporter_cls = _HttpMetricExporter
        log_exporter_cls = _HttpLogExporter
    else:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
            OTLPLogExporter as _GrpcLogExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter as _GrpcMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as _GrpcSpanExporter,
        )

        span_exporter_cls = _GrpcSpanExporter
        metric_exporter_cls = _GrpcMetricExporter
        log_exporter_cls = _GrpcLogExporter

    return span_exporter_cls, metric_exporter_cls, log_exporter_cls


def init_otel(app: Quart, config: Config) -> None:
    """Wire OTLP-exported traces, metrics, and logs -- fail-safe by design.

    No-ops entirely when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset (dev/test
    default): the Prometheus ``/metrics`` route from :func:`init_metrics`
    keeps working regardless. Any setup failure (bad protocol, import error,
    unreachable collector at construction time) is caught and logged as a
    warning, never raised -- a dead exporter must never break the app. Once
    configured, the SDK's batch processors export asynchronously and drop on
    failure rather than blocking request handling.
    """
    endpoint = config.otel_exporter_otlp_endpoint
    if not endpoint:
        logger.info("otel_disabled", reason="OTEL_EXPORTER_OTLP_ENDPOINT unset")
        app.config["OTEL_ENABLED"] = False
        return

    try:
        from opentelemetry import metrics as otel_metrics
        from opentelemetry import trace
        from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        span_exporter_cls, metric_exporter_cls, log_exporter_cls = _select_otlp_exporter_classes(
            config.otel_exporter_otlp_protocol
        )

        resource = Resource.create(
            {
                "service.name": config.otel_service_name,
                "service.namespace": "tobogganing",
            }
        )

        # Bound each export attempt's retry deadline (default SDK backoff
        # otherwise climbs 1s/2s/4s/8s/16s/32s per signal, which stalls
        # graceful shutdown for minutes when the collector is unreachable --
        # a dead exporter must never hold up the process, not just requests).
        _EXPORT_TIMEOUT_SECONDS = 5

        # Traces
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(span_exporter_cls(timeout=_EXPORT_TIMEOUT_SECONDS))
        )
        trace.set_tracer_provider(tracer_provider)

        # Metrics
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter_cls(timeout=_EXPORT_TIMEOUT_SECONDS)
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        otel_metrics.set_meter_provider(meter_provider)

        # Logs
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(log_exporter_cls(timeout=_EXPORT_TIMEOUT_SECONDS))
        )
        logging.getLogger().addHandler(
            LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
        )

        # ASGI instrumentation (request spans). OpenTelemetryMiddleware is a
        # structurally-compatible ASGI3 callable wrapper; Quart's `asgi_app`
        # stub type is narrower than asgiref's generic ASGI protocol it
        # implements against, hence the assignment mismatch below.
        app.asgi_app = OpenTelemetryMiddleware(  # type: ignore[assignment]
            app.asgi_app, tracer_provider=tracer_provider
        )

        # OTLP metric instruments mirroring the Prometheus counters above,
        # recorded together in init_metrics()'s after_request hook.
        meter = otel_metrics.get_meter("hub_api")
        app.config["OTEL_HTTP_REQUESTS_COUNTER"] = meter.create_counter(
            "http.server.requests", unit="1", description="Total HTTP requests handled"
        )
        app.config["OTEL_HTTP_DURATION_HISTOGRAM"] = meter.create_histogram(
            "http.server.duration", unit="s", description="HTTP request duration"
        )
        app.config["OTEL_TRACER_PROVIDER"] = tracer_provider
        app.config["OTEL_METER_PROVIDER"] = meter_provider
        app.config["OTEL_LOGGER_PROVIDER"] = logger_provider
        app.config["OTEL_ENABLED"] = True
        logger.info(
            "otel_configured",
            endpoint=endpoint,
            protocol=config.otel_exporter_otlp_protocol,
        )
    except Exception as exc:  # noqa: BLE001 - telemetry setup must never crash the app
        logger.warning("otel_setup_failed", error=str(exc))
        app.config["OTEL_ENABLED"] = False


def instrument_sqlalchemy_engine(app: Quart, engine: Any) -> None:
    """Instrument penguin-dal's SQLAlchemy engine for DB span emission.

    No-op when OTel wiring is disabled (see :func:`init_otel`) or when
    instrumentation itself fails -- DB spans are a bonus signal on top of
    the mandatory HTTP request spans, never a startup-blocking dependency.
    """
    if not app.config.get("OTEL_ENABLED"):
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        # AsyncEngine wraps a sync Engine that emits the actual SQLAlchemy
        # core events the instrumentor hooks into.
        sync_engine = getattr(engine, "sync_engine", engine)
        SQLAlchemyInstrumentor().instrument(engine=sync_engine)
        logger.info("otel_sqlalchemy_instrumented")
    except Exception as exc:  # noqa: BLE001 - never block startup on this
        logger.warning("otel_sqlalchemy_instrumentation_failed", error=str(exc))
