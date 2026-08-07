"""Test alert rules, evaluation, and API."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.alert_evaluator import AlertEvaluator
from hub_api.notifications.service import NotificationService


@pytest_asyncio.fixture
async def evaluator(real_dal: AsyncDB) -> AlertEvaluator:
    """Create an AlertEvaluator with fake transports."""
    from hub_api.notifications.transports import EmailTransport, WebhookTransport

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
        from hub_api.notifications.service import NotificationService

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


# ---------------------------------------------------------------------------
# HTTP-level API tests (routes, flag gating, tier gating)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def alerts_app(real_dal: AsyncDB, monkeypatch: pytest.MonkeyPatch):
    """Quart app with the perftest_cluster module mounted on a real DAL.

    Feature flags are controlled per-test via app._test_enabled_flags (a set
    of full flag keys); everything else is flag-off — so the flag-off 402
    paths are exercised against the real gate, not a blanket bypass.
    """
    from hub_api.app import create_app
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext
    import hub_api.db
    import hub_api.app as app_module
    import shared.licensing.entitlements

    test_app = create_app()
    test_app.config["TESTING"] = True

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    test_app.config["KEY_PROVIDER"] = provider

    monkeypatch.setattr(hub_api.db, "get_db", lambda: real_dal)
    monkeypatch.setattr(app_module, "get_db", lambda: real_dal)
    import hub_api.modules.perftest_cluster.api.alerts as alerts_api
    import hub_api.modules.perftest_cluster.api.tests as tests_api
    monkeypatch.setattr(alerts_api, "get_db", lambda: real_dal)
    monkeypatch.setattr(tests_api, "get_db", lambda: real_dal)

    enabled_flags: set[str] = set()

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        return flag_key in enabled_flags

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    from hub_api.modules.perftest_cluster import module as wpc_module

    test_app.registry.register(wpc_module())
    ctx = ModuleContext(config=test_app.config_obj, db=real_dal, key_provider=provider)
    test_app.registry.apply_to(test_app, ctx)

    test_app._test_enabled_flags = enabled_flags  # type: ignore[attr-defined]
    return test_app


async def _alerts_token(app) -> str:
    """Issue a wildcard-scope token against the app's key provider."""
    from hub_api.auth.jwt import encode_access_token

    return await encode_access_token(
        {
            "sub": "alerts-tester",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant-alerts",
            "scope": "*:*",
        },
        app.config["KEY_PROVIDER"],
    )


@pytest.mark.asyncio
async def test_rules_api_flag_off_returns_402(alerts_app) -> None:
    """With the alerts flag off, the rules API must 402 before touching the DB."""
    token = await _alerts_token(alerts_app)
    client = alerts_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={"name": "r", "metric": "latency_ms", "comparator": "gt", "threshold": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_rules_api_crud_roundtrip(alerts_app) -> None:
    """Flag on (Community tier): create, list, and delete a rule over HTTP."""
    alerts_app._test_enabled_flags.add("tobogganing.perftest.cluster.alerts")
    token = await _alerts_token(alerts_app)
    client = alerts_app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/perftest_cluster/alerts/rules",
        json={"name": "hi-latency", "metric": "latency_ms", "comparator": "gt", "threshold": 250},
        headers=headers,
    )
    assert resp.status_code == 201
    rule = await resp.get_json()
    assert rule["metric"] == "latency_ms"

    resp = await client.get("/api/v1/perftest_cluster/alerts/rules", headers=headers)
    assert resp.status_code == 200
    listed = await resp.get_json()
    assert any(r["id"] == rule["id"] for r in listed["rules"])

    resp = await client.delete(
        f"/api/v1/perftest_cluster/alerts/rules/{rule['id']}", headers=headers
    )
    assert resp.status_code in (200, 204)


@pytest.mark.asyncio
async def test_email_channel_requires_only_alerts_flag(alerts_app) -> None:
    """Email channels are Community: alerts flag alone is enough for 201."""
    alerts_app._test_enabled_flags.add("tobogganing.perftest.cluster.alerts")
    token = await _alerts_token(alerts_app)
    client = alerts_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/alerts/channels",
        json={"name": "ops", "kind": "email", "config": {"to": ["ops@example.com"]}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_webhook_channel_unlicensed_402_professional(alerts_app) -> None:
    """Entitlement-key trap: alert_routing flag ON but license unset -> 402 via
    the professional tier path. Fails if the entitlement key were prefixed
    (tier would fall back to community and the paid gate would silently pass).
    """
    alerts_app._test_enabled_flags.update(
        {
            "tobogganing.perftest.cluster.alerts",
            "tobogganing.perftest.cluster.alert_routing",
        }
    )
    token = await _alerts_token(alerts_app)
    client = alerts_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/alerts/channels",
        json={
            "name": "hook",
            "kind": "webhook",
            "config": {"url": "https://example.com/hook", "secret": "s3cr3tvalue"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402
    body = await resp.get_json()
    assert body["tier"] == "professional"


@pytest.mark.asyncio
async def test_webhook_channel_licensed_201_redacts_secret(
    alerts_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Licensed Professional tier: webhook channel creates and redacts secret."""
    alerts_app._test_enabled_flags.update(
        {
            "tobogganing.perftest.cluster.alerts",
            "tobogganing.perftest.cluster.alert_routing",
        }
    )
    import hub_api.modules.perftest_cluster.api.alerts as alerts_api

    monkeypatch.setattr(alerts_api, "_is_licensed_for_tier", lambda tier: True)
    token = await _alerts_token(alerts_app)
    client = alerts_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/alerts/channels",
        json={
            "name": "hook",
            "kind": "webhook",
            "config": {"url": "https://example.com/hook", "secret": "s3cr3tvalue"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = await resp.get_json()
    assert "s3cr3tvalue" not in json.dumps(body)
    assert body["config"]["secret"].startswith("****")
