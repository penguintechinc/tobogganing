"""Tests for hub_api/telemetry.py -- Prometheus /metrics + OTLP wiring.

Covers the two release-blocker assertions: the Prometheus endpoint exposes
the exact metric names/labels the shipped Grafana dashboard depends on, and
app startup never crashes regardless of OTEL_EXPORTER_OTLP_ENDPOINT state.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from quart import Quart

from hub_api.telemetry import (
    SERVICE_LABEL,
    http_request_duration_seconds,
    http_requests_total,
)


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_required_names_and_service_label(
    app: Quart,
) -> None:
    """/metrics must expose http_requests_total + http_request_duration_seconds
    labeled service="hub-api" after a request -- the exact names/labels
    k8s/helm/tobogganing/templates/monitoring/grafana.yaml's PromQL panels
    match on. A dashboard referencing metrics that don't exist is the bug
    this test guards against.
    """
    client = app.test_client()

    # Generate at least one sample before scraping.
    health_resp = await client.get("/health")
    assert health_resp.status_code == 200

    resp = await client.get("/metrics")
    assert resp.status_code == 200
    raw_body = await resp.get_data()
    body = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body

    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert f'service="{SERVICE_LABEL}"' in body
    # The /health request itself must have been counted with its matched
    # route rule, not the raw path.
    assert 'route="/health"' in body


@pytest.mark.asyncio
async def test_metrics_route_uses_matched_route_rule_not_raw_path(app: Quart) -> None:
    """A request to a path with no matching rule (404) must not blow up
    metric cardinality with the raw, attacker-controlled path -- it must be
    labeled "unmatched" instead.
    """
    client = app.test_client()

    resp = await client.get("/this-route-does-not-exist")
    assert resp.status_code == 404

    metrics_resp = await client.get("/metrics")
    raw_body = await metrics_resp.get_data()
    body = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body

    assert 'route="/this-route-does-not-exist"' not in body
    assert 'route="unmatched"' in body


def test_app_startup_with_otlp_endpoint_unset_does_not_crash(mock_db: MagicMock) -> None:
    """create_app() must never raise when OTEL_EXPORTER_OTLP_ENDPOINT is
    unset (the dev/test default) -- OTel wiring is skipped entirely, but
    the app (and its Prometheus /metrics route) still comes up.

    Config's fields read os.getenv() at class-definition time (module
    import), so an explicit Config(otel_exporter_otlp_endpoint="") is used
    rather than monkeypatching the env var post-import.
    """
    from hub_api.config import Config

    config = Config(otel_exporter_otlp_endpoint="")

    import hub_api.db
    from hub_api.app import create_app

    with (
        patch("hub_api.db.init_dal"),
        patch.object(hub_api.db, "get_db", return_value=mock_db),
    ):
        test_app = create_app(config=config)

    assert test_app.config["OTEL_ENABLED"] is False
    assert any(rule.rule == "/metrics" for rule in test_app.url_map.iter_rules())


def test_app_startup_with_otlp_endpoint_set_does_not_crash(mock_db: MagicMock) -> None:
    """create_app() must never raise even when OTEL_EXPORTER_OTLP_ENDPOINT
    points at an unreachable collector -- OTel setup wraps construction in
    a try/except, and any actual export retries happen asynchronously in a
    background thread with a bounded timeout, never blocking app startup.
    """
    from hub_api.config import Config

    config = Config(otel_exporter_otlp_endpoint="http://localhost:4317")

    import hub_api.db
    from hub_api.app import create_app

    with (
        patch("hub_api.db.init_dal"),
        patch.object(hub_api.db, "get_db", return_value=mock_db),
    ):
        test_app = create_app(config=config)

    assert test_app.config["OTEL_ENABLED"] is True
    assert any(rule.rule == "/metrics" for rule in test_app.url_map.iter_rules())


def test_prometheus_counter_and_histogram_have_expected_label_names() -> None:
    """Guard the exact label set (service/method/route/status) against
    accidental drift -- the dashboard's PromQL filters on `service` alone,
    but the full label set must stay stable for other panels/alerts.
    """
    assert http_requests_total._labelnames == ("service", "method", "route", "status")
    assert http_request_duration_seconds._labelnames == (
        "service",
        "method",
        "route",
        "status",
    )
