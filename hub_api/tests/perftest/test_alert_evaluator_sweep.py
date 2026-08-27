"""Coverage backfill for AlertEvaluator.sweep() (services/alert_evaluator.py).

evaluate_result() is already covered by test_wpc_alerts.py; this file targets
the cross-tenant scheduler sweep() path: device-scoped vs tenant-wide rule
scanning, comparator evaluation, dedup, and notification failure handling.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.alert_evaluator import AlertEvaluator
from hub_api.notifications.service import NotificationService


class _FakeEmailTransport:
    """Email transport stub that records sends instead of dispatching."""

    def __init__(self) -> None:
        """Initialize with an empty sent list."""
        self.sent: list[dict[str, Any]] = []

    async def send(self, to: list[str], subject: str, body: str) -> None:
        """Record the send call."""
        self.sent.append({"to": to, "subject": subject, "body": body})


async def _insert_device(real_dal: AsyncDB, tenant: str, device_id: str) -> None:
    """Insert a minimal devices row for FK-style lookups in sweep()."""
    await real_dal.devices.async_insert(
        id=device_id,
        tenant=tenant,
        org_unit_id=None,
        name="dev",
        serial=f"SN-{device_id[:8]}",
        hostname=None,
        os=None,
        status="online",
        metadata=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


async def _insert_rule(
    real_dal: AsyncDB,
    tenant: str,
    *,
    metric: str,
    comparator: str,
    threshold: float,
    window_seconds: int = 300,
    device_id: str | None = None,
    test_type: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Insert an alert_rules row and return its id."""
    rule_id = str(uuid4())
    await real_dal.alert_rules.async_insert(
        id=rule_id,
        tenant=tenant,
        name="sweep-rule",
        metric=metric,
        comparator=comparator,
        threshold=threshold,
        window_seconds=window_seconds,
        device_id=device_id,
        test_type=test_type,
        channel_id=channel_id,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )
    return rule_id


async def _insert_perf_result(
    real_dal: AsyncDB,
    tenant: str,
    device_id: str,
    *,
    test_type: str,
    latency_ms: float | None,
    completed_at: datetime,
) -> None:
    """Insert a perf_test_results row for sweep() to scan."""
    await real_dal.perf_test_results.async_insert(
        id=str(uuid4()),
        tenant=tenant,
        device_id=device_id,
        test_type=test_type,
        status="completed",
        target="1.2.3.4",
        started_at=completed_at,
        completed_at=completed_at,
        latency_ms=latency_ms,
        throughput=None,
        test_output=None,
        created_at=completed_at,
    )


@pytest.mark.asyncio
async def test_sweep_no_rules_returns_zero(real_dal: AsyncDB) -> None:
    """sweep() with zero enabled rules across all tenants fires nothing."""
    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)
    fired = await evaluator.sweep()
    assert fired == 0


@pytest.mark.asyncio
async def test_sweep_device_scoped_rule_breach_fires_and_notifies(
    real_dal: AsyncDB,
) -> None:
    """A device-scoped rule breaches on the latest result and notifies its channel."""
    tenant = "sweep-tenant-1"
    device_id = str(uuid4())
    channel_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await _insert_device(real_dal, tenant, device_id)
    await real_dal.notification_channels.async_insert(
        id=channel_id,
        tenant=tenant,
        name="ops",
        kind="email",
        config='{"to": ["ops@example.com"]}',
        enabled=True,
        created_at=now,
    )
    await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gt",
        threshold=100.0,
        device_id=device_id,
        channel_id=channel_id,
    )
    await _insert_perf_result(
        real_dal, tenant, device_id, test_type="ping", latency_ms=150.0, completed_at=now
    )

    email_transport = _FakeEmailTransport()
    notifications = NotificationService(real_dal, email_transport=email_transport)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 1
    assert len(email_transport.sent) == 1

    events = await real_dal(real_dal.alert_events.tenant == tenant).select()
    assert len(events) == 1
    assert events.first()["notified"] is True


@pytest.mark.asyncio
async def test_sweep_tenant_wide_rule_scans_all_devices(real_dal: AsyncDB) -> None:
    """A rule with no device_id filter scans every device for the tenant."""
    tenant = "sweep-tenant-2"
    device_a = str(uuid4())
    device_b = str(uuid4())
    now = datetime.now(timezone.utc)

    await _insert_device(real_dal, tenant, device_a)
    await _insert_device(real_dal, tenant, device_b)
    await _insert_rule(real_dal, tenant, metric="latency_ms", comparator="gt", threshold=100.0)
    # Only device_b breaches.
    await _insert_perf_result(
        real_dal, tenant, device_a, test_type="ping", latency_ms=50.0, completed_at=now
    )
    await _insert_perf_result(
        real_dal, tenant, device_b, test_type="ping", latency_ms=200.0, completed_at=now
    )

    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 1


@pytest.mark.asyncio
async def test_sweep_test_type_filter_excludes_non_matching(real_dal: AsyncDB) -> None:
    """A rule with test_type_filter only evaluates matching-type results."""
    tenant = "sweep-tenant-3"
    device_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await _insert_device(real_dal, tenant, device_id)
    await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gt",
        threshold=100.0,
        test_type="ping",
    )
    # Result is for "http", filtered rule wants "ping" -> no window match.
    await _insert_perf_result(
        real_dal, tenant, device_id, test_type="http", latency_ms=999.0, completed_at=now
    )

    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 0


@pytest.mark.asyncio
async def test_sweep_no_breach_no_event(real_dal: AsyncDB) -> None:
    """A rule that isn't breached by the latest result fires nothing."""
    tenant = "sweep-tenant-4"
    device_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await _insert_device(real_dal, tenant, device_id)
    await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gt",
        threshold=1000.0,
        device_id=device_id,
    )
    await _insert_perf_result(
        real_dal, tenant, device_id, test_type="ping", latency_ms=10.0, completed_at=now
    )

    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 0


@pytest.mark.asyncio
async def test_sweep_dedup_within_window_skips(real_dal: AsyncDB) -> None:
    """An already-fired event within the window suppresses a duplicate."""
    tenant = "sweep-tenant-5"
    device_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await _insert_device(real_dal, tenant, device_id)
    rule_id = await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gt",
        threshold=100.0,
        device_id=device_id,
    )
    await _insert_perf_result(
        real_dal, tenant, device_id, test_type="ping", latency_ms=200.0, completed_at=now
    )
    # Pre-existing event within window.
    await real_dal.alert_events.async_insert(
        id=str(uuid4()),
        tenant=tenant,
        rule_id=rule_id,
        device_id=device_id,
        observed_value=200.0,
        fired_at=now,
        notified=True,
    )

    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 0


@pytest.mark.asyncio
async def test_sweep_no_matching_result_in_window_skips(real_dal: AsyncDB) -> None:
    """A device with no perf_test_results in the window contributes no events."""
    tenant = "sweep-tenant-6"
    device_id = str(uuid4())

    await _insert_device(real_dal, tenant, device_id)
    await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gt",
        threshold=1.0,
        device_id=device_id,
        window_seconds=60,
    )
    # No perf_test_results inserted at all.

    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 0


@pytest.mark.asyncio
async def test_sweep_metric_missing_from_result_skips(real_dal: AsyncDB) -> None:
    """A latest result whose metric value is None is skipped (no breach possible)."""
    tenant = "sweep-tenant-7"
    device_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await _insert_device(real_dal, tenant, device_id)
    await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gt",
        threshold=1.0,
        device_id=device_id,
    )
    # latency_ms is None on this result (e.g. failed test).
    await _insert_perf_result(
        real_dal, tenant, device_id, test_type="ping", latency_ms=None, completed_at=now
    )

    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 0


@pytest.mark.asyncio
async def test_sweep_all_comparators(real_dal: AsyncDB) -> None:
    """sweep() evaluates gte and lt/lte comparators as well as gt."""
    tenant = "sweep-tenant-8"
    now = datetime.now(timezone.utc)

    # gte: 100 >= 100 breaches.
    device_gte = str(uuid4())
    await _insert_device(real_dal, tenant, device_gte)
    await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gte",
        threshold=100.0,
        device_id=device_gte,
    )
    await _insert_perf_result(
        real_dal, tenant, device_gte, test_type="ping", latency_ms=100.0, completed_at=now
    )

    # lte: 50 <= 50 breaches (throughput metric).
    device_lte = str(uuid4())
    await _insert_device(real_dal, tenant, device_lte)
    await _insert_rule(
        real_dal,
        tenant,
        metric="throughput",
        comparator="lte",
        threshold=50.0,
        device_id=device_lte,
    )
    await real_dal.perf_test_results.async_insert(
        id=str(uuid4()),
        tenant=tenant,
        device_id=device_lte,
        test_type="ping",
        status="completed",
        target="1.2.3.4",
        started_at=now,
        completed_at=now,
        latency_ms=None,
        throughput=50.0,
        test_output=None,
        created_at=now,
    )

    notifications = NotificationService(real_dal)
    evaluator = AlertEvaluator(real_dal, notifications)

    fired = await evaluator.sweep()
    assert fired == 2


@pytest.mark.asyncio
async def test_sweep_notification_failure_does_not_raise(
    real_dal: AsyncDB, monkeypatch: Any
) -> None:
    """A notification delivery failure during sweep() is caught and logged."""
    tenant = "sweep-tenant-9"
    device_id = str(uuid4())
    channel_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await _insert_device(real_dal, tenant, device_id)
    await real_dal.notification_channels.async_insert(
        id=channel_id,
        tenant=tenant,
        name="broken",
        kind="email",
        config='{"to": ["ops@example.com"]}',
        enabled=True,
        created_at=now,
    )
    await _insert_rule(
        real_dal,
        tenant,
        metric="latency_ms",
        comparator="gt",
        threshold=1.0,
        device_id=device_id,
        channel_id=channel_id,
    )
    await _insert_perf_result(
        real_dal, tenant, device_id, test_type="ping", latency_ms=999.0, completed_at=now
    )

    notifications = NotificationService(real_dal)

    async def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notifications, "notify", _boom)

    evaluator = AlertEvaluator(real_dal, notifications)
    fired = await evaluator.sweep()
    # Event still counted as fired even though notification delivery failed.
    assert fired == 1
