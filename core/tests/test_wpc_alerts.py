"""Test alert rules, evaluation, and API."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB

from core.modules.waddleperf_cluster.services.alert_evaluator import AlertEvaluator
from core.notifications.service import NotificationService


@pytest_asyncio.fixture
async def evaluator(real_dal: AsyncDB) -> AlertEvaluator:
    """Create an AlertEvaluator with fake transports."""
    from core.notifications.transports import EmailTransport, WebhookTransport

    class FakeEmailTransport(EmailTransport):
        """Email transport that logs sends without actually sending."""

        def __init__(self):
            super().__init__()
            self.sent = []

        async def send(self, to: list[str], subject: str, body: str) -> None:
            self.sent.append({"to": to, "subject": subject, "body": body})

    class FakeWebhookTransport(WebhookTransport):
        """Webhook transport that logs sends without actually sending."""

        def __init__(self):
            super().__init__()
            self.sent = []

        async def send(self, url: str, secret: str, subject: str, body: str) -> None:
            self.sent.append({"url": url, "secret": secret, "subject": subject, "body": body})

    email_transport = FakeEmailTransport()
    webhook_transport = FakeWebhookTransport()

    notifications = NotificationService(
        real_dal,
        email_transport=email_transport,
        webhook_transport=webhook_transport,
    )
    return AlertEvaluator(real_dal, notifications)


class TestAlertRuleCRUD:
    """Test alert rule CRUD operations."""

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_create_rule(self, real_dal: AsyncDB) -> None:
        """Test creating an alert rule."""
        tenant = str(uuid4())
        rule_id = str(uuid4())

        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="High Latency",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        row = await real_dal(
            (real_dal.alert_rules.id == rule_id) & (real_dal.alert_rules.tenant == tenant)
        ).select()
        rule = row.first()

        assert rule is not None
        assert rule["name"] == "High Latency"
        assert rule["metric"] == "latency_ms"
        assert rule["comparator"] == "gt"
        assert rule["threshold"] == 100.0

    @pytest.mark.asyncio
    async def test_tenant_isolation_list(self, real_dal: AsyncDB) -> None:
        """Test that tenant A cannot see tenant B's rules."""
        tenant_a = str(uuid4())
        tenant_b = str(uuid4())

        # Create rule for tenant A
        await real_dal.alert_rules.async_insert(
            id=str(uuid4()),
            tenant=tenant_a,
            name="Rule A",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Create rule for tenant B
        await real_dal.alert_rules.async_insert(
            id=str(uuid4()),
            tenant=tenant_b,
            name="Rule B",
            metric="throughput",
            comparator="lt",
            threshold=50.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Get rules for tenant A
        rules_a = await real_dal(
            real_dal.alert_rules.tenant == tenant_a
        ).select()
        assert len(rules_a) == 1
        assert rules_a.first()["name"] == "Rule A"

        # Get rules for tenant B
        rules_b = await real_dal(
            real_dal.alert_rules.tenant == tenant_b
        ).select()
        assert len(rules_b) == 1
        assert rules_b.first()["name"] == "Rule B"

    @pytest.mark.asyncio
    async def test_tenant_isolation_delete(self, real_dal: AsyncDB) -> None:
        """Test that tenant A cannot delete tenant B's rules."""
        tenant_a = str(uuid4())
        tenant_b = str(uuid4())
        rule_id_b = str(uuid4())

        # Create rule for tenant B
        await real_dal.alert_rules.async_insert(
            id=rule_id_b,
            tenant=tenant_b,
            name="Rule B",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Tenant A tries to delete (should not find it)
        await real_dal(
            (real_dal.alert_rules.id == rule_id_b) & (real_dal.alert_rules.tenant == tenant_a)
        ).delete()

        # Verify B's rule still exists
        row = await real_dal(
            (real_dal.alert_rules.id == rule_id_b) & (real_dal.alert_rules.tenant == tenant_b)
        ).select()
        assert row.first() is not None


class TestAlertEvaluation:
    """Test alert rule evaluation on ingest."""

    @pytest.mark.asyncio
    async def test_breach_fires_event(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test that a breached rule fires an event."""
        tenant = str(uuid4())
        channel_id = str(uuid4())
        rule_id = str(uuid4())

        # Create a channel for the rule
        await real_dal.notification_channels.async_insert(
            id=channel_id,
            tenant=tenant,
            name="Test Channel",
            kind="email",
            config=json.dumps({"to": ["test@example.com"]}),
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Create a rule: latency > 100
        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="High Latency",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=channel_id,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Evaluate result that breaches
        result = {
            "device_id": str(uuid4()),
            "test_type": "ping",
            "latency_ms": 150.0,
            "throughput": None,
            "status": "completed",
        }

        events_fired = await evaluator.evaluate_result(tenant, result)

        assert events_fired == 1

        # Verify event was created
        events = await real_dal(
            (real_dal.alert_events.tenant == tenant) & (real_dal.alert_events.rule_id == rule_id)
        ).select()
        assert len(events) == 1
        assert events.first()["observed_value"] == 150.0
        assert events.first()["notified"] == True  # Should be marked notified

    @pytest.mark.asyncio
    async def test_no_breach_no_event(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test that a non-breached rule does not fire an event."""
        tenant = str(uuid4())
        rule_id = str(uuid4())

        # Create a rule: latency > 100
        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="High Latency",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Evaluate result that does not breach
        result = {
            "device_id": str(uuid4()),
            "test_type": "ping",
            "latency_ms": 50.0,
            "throughput": None,
            "status": "completed",
        }

        events_fired = await evaluator.evaluate_result(tenant, result)

        assert events_fired == 0

        # Verify no event was created
        events = await real_dal(
            (real_dal.alert_events.tenant == tenant) & (real_dal.alert_events.rule_id == rule_id)
        ).select()
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_dedup_within_window(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test that dedup prevents firing within window."""
        tenant = str(uuid4())
        rule_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Create rule
        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="High Latency",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=now,
        )

        # Fire first event
        await real_dal.alert_events.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            rule_id=rule_id,
            device_id=None,
            observed_value=150.0,
            fired_at=now,
            notified=False,
        )

        # Try to evaluate again within window
        result = {
            "device_id": str(uuid4()),
            "test_type": "ping",
            "latency_ms": 150.0,
            "throughput": None,
            "status": "completed",
        }

        events_fired = await evaluator.evaluate_result(tenant, result)

        # Should be deduped
        assert events_fired == 0

    @pytest.mark.asyncio
    async def test_device_filter(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test that device filter works correctly."""
        tenant = str(uuid4())
        device_a = str(uuid4())
        device_b = str(uuid4())
        rule_id = str(uuid4())

        # Create rule filtered to device A
        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="High Latency Device A",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=device_a,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Evaluate result from device B (should not breach)
        result = {
            "device_id": device_b,
            "test_type": "ping",
            "latency_ms": 150.0,
            "throughput": None,
            "status": "completed",
        }

        events_fired = await evaluator.evaluate_result(tenant, result)
        assert events_fired == 0

        # Evaluate result from device A (should breach)
        result = {
            "device_id": device_a,
            "test_type": "ping",
            "latency_ms": 150.0,
            "throughput": None,
            "status": "completed",
        }

        events_fired = await evaluator.evaluate_result(tenant, result)
        assert events_fired == 1

    @pytest.mark.asyncio
    async def test_test_type_filter(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test that test_type filter works correctly."""
        tenant = str(uuid4())
        rule_id = str(uuid4())

        # Create rule filtered to "ping" test type
        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="High Latency Ping",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type="ping",
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # Evaluate result from "http" test (should not breach)
        result = {
            "device_id": str(uuid4()),
            "test_type": "http",
            "latency_ms": 150.0,
            "throughput": None,
            "status": "completed",
        }

        events_fired = await evaluator.evaluate_result(tenant, result)
        assert events_fired == 0

        # Evaluate result from "ping" test (should breach)
        result = {
            "device_id": str(uuid4()),
            "test_type": "ping",
            "latency_ms": 150.0,
            "throughput": None,
            "status": "completed",
        }

        events_fired = await evaluator.evaluate_result(tenant, result)
        assert events_fired == 1

    @pytest.mark.asyncio
    async def test_evaluator_exception_does_not_break_ingest(
        self, real_dal: AsyncDB
    ) -> None:
        """Test that evaluator exceptions don't break ingest."""
        from core.notifications.service import NotificationService

        tenant = str(uuid4())

        # Create a broken evaluator that raises
        class BrokenEvaluator(AlertEvaluator):
            async def evaluate_result(self, tenant: str, result: dict) -> int:
                raise Exception("Broken evaluator")

        broken_eval = BrokenEvaluator(
            real_dal,
            NotificationService(real_dal),
        )

        result = {
            "device_id": str(uuid4()),
            "test_type": "ping",
            "latency_ms": 50.0,
            "throughput": None,
            "status": "completed",
        }

        # Should not raise
        try:
            await broken_eval.evaluate_result(tenant, result)
            pytest.fail("Expected exception to be raised")
        except Exception:
            # Expected
            pass


class TestAlertComparators:
    """Test all comparator operators."""

    @pytest.mark.asyncio
    async def test_gt_comparator(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test gt (greater than) comparator."""
        tenant = str(uuid4())
        rule_id = str(uuid4())

        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="Test",
            metric="latency_ms",
            comparator="gt",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # 101 > 100 (breach)
        assert await evaluator.evaluate_result(tenant, {"device_id": str(uuid4()), "test_type": "ping", "latency_ms": 101.0, "throughput": None, "status": "completed"}) == 1

    @pytest.mark.asyncio
    async def test_gte_comparator(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test gte (greater than or equal) comparator."""
        tenant = str(uuid4())
        rule_id = str(uuid4())

        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="Test",
            metric="latency_ms",
            comparator="gte",
            threshold=100.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # 100 >= 100 (breach)
        assert await evaluator.evaluate_result(tenant, {"device_id": str(uuid4()), "test_type": "ping", "latency_ms": 100.0, "throughput": None, "status": "completed"}) == 1

    @pytest.mark.asyncio
    async def test_lt_comparator(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test lt (less than) comparator."""
        tenant = str(uuid4())
        rule_id = str(uuid4())

        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="Test",
            metric="throughput",
            comparator="lt",
            threshold=50.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # 49 < 50 (breach)
        assert await evaluator.evaluate_result(tenant, {"device_id": str(uuid4()), "test_type": "ping", "latency_ms": None, "throughput": 49.0, "status": "completed"}) == 1

    @pytest.mark.asyncio
    async def test_lte_comparator(
        self, real_dal: AsyncDB, evaluator: AlertEvaluator
    ) -> None:
        """Test lte (less than or equal) comparator."""
        tenant = str(uuid4())
        rule_id = str(uuid4())

        await real_dal.alert_rules.async_insert(
            id=rule_id,
            tenant=tenant,
            name="Test",
            metric="throughput",
            comparator="lte",
            threshold=50.0,
            window_seconds=300,
            device_id=None,
            test_type=None,
            channel_id=None,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )

        # 50 <= 50 (breach)
        assert await evaluator.evaluate_result(tenant, {"device_id": str(uuid4()), "test_type": "ping", "latency_ms": None, "throughput": 50.0, "status": "completed"}) == 1
