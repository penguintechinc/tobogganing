"""Test AutoPerf tiered monitoring policies, cycle task, and API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.autoperf_manager import AutoPerfManager


@pytest_asyncio.fixture
async def autoperf_app(real_dal: AsyncDB, monkeypatch: pytest.MonkeyPatch):
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
    import hub_api.modules.perftest_cluster.api.autoperf as autoperf_api

    monkeypatch.setattr(autoperf_api, "get_db", lambda: real_dal)

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


async def _autoperf_token(app) -> str:
    """Issue a wildcard-scope token against the app's key provider."""
    from hub_api.auth.jwt import encode_access_token

    return await encode_access_token(
        {
            "sub": "autoperf-tester",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "tenant-autoperf",
            "scope": "*:*",
        },
        app.config["KEY_PROVIDER"],
    )


# ---------------------------------------------------------------------------
# HTTP-level API tests (routes, flag gating, tier gating)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policies_api_flag_off_returns_402(autoperf_app) -> None:
    """With the autoperf flag off, the policies API must 402 before touching the DB."""
    token = await _autoperf_token(autoperf_app)
    client = autoperf_app.test_client()
    resp = await client.get(
        "/api/v1/perftest_cluster/autoperf/policies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_policies_api_licensed_crud_roundtrip(autoperf_app, monkeypatch) -> None:
    """Licensed Professional tier: create, list, and delete a policy over HTTP."""
    autoperf_app._test_enabled_flags.add("tobogganing.perftest_cluster.autoperf")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _autoperf_token(autoperf_app)
    client = autoperf_app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    # Create a policy
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "high-load-monitor",
            "device_id": str(uuid4()),
            "target": "192.168.1.1",
            "t1_interval_seconds": 300,
            "t2_interval_seconds": 120,
            "t3_interval_seconds": 60,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    policy = await resp.get_json()
    assert policy["name"] == "high-load-monitor"
    policy_id = policy["id"]

    # List policies
    resp = await client.get(
        "/api/v1/perftest_cluster/autoperf/policies",
        headers=headers,
    )
    assert resp.status_code == 200
    listed = await resp.get_json()
    assert len(listed["policies"]) == 1
    assert listed["policies"][0]["id"] == policy_id

    # Get specific policy
    resp = await client.get(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    fetched = await resp.get_json()
    assert fetched["id"] == policy_id

    # Delete policy
    resp = await client.delete(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}",
        headers=headers,
    )
    assert resp.status_code == 204

    # Verify it's gone
    resp = await client.get(
        f"/api/v1/perftest_cluster/autoperf/policies/{policy_id}",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_policies_api_unlicensed_402_professional(autoperf_app) -> None:
    """Entitlement-key trap: autoperf flag ON but license unset -> 402 via
    the professional tier path. Fails if the entitlement key were prefixed
    (tier would fall back to community and the paid gate would silently pass).
    """
    autoperf_app._test_enabled_flags.add("tobogganing.perftest_cluster.autoperf")
    token = await _autoperf_token(autoperf_app)
    client = autoperf_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "test",
            "device_id": str(uuid4()),
            "target": "192.168.1.1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402
    body = await resp.get_json()
    assert body["tier"] == "professional"


@pytest.mark.asyncio
async def test_policies_api_licensed_201(autoperf_app, monkeypatch: pytest.MonkeyPatch) -> None:
    """Licensed Professional tier: policy create works."""
    autoperf_app._test_enabled_flags.add("tobogganing.perftest_cluster.autoperf")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _autoperf_token(autoperf_app)
    client = autoperf_app.test_client()
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "licensed-policy",
            "device_id": str(uuid4()),
            "target": "192.168.1.1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = await resp.get_json()
    assert body["name"] == "licensed-policy"


@pytest.mark.asyncio
async def test_policy_creation_validation(autoperf_app, monkeypatch) -> None:
    """Test policy creation validation: bad intervals."""
    autoperf_app._test_enabled_flags.add("tobogganing.perftest_cluster.autoperf")
    import hub_api.entitlements.gate as gate_module

    monkeypatch.setattr(gate_module, "_is_licensed_for_tier", lambda tier: True)
    token = await _autoperf_token(autoperf_app)
    client = autoperf_app.test_client()

    # Missing required field
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "bad-policy",
            # missing device_id
            "target": "192.168.1.1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400

    # Bad interval order
    resp = await client.post(
        "/api/v1/perftest_cluster/autoperf/policies",
        json={
            "name": "bad-interval",
            "device_id": str(uuid4()),
            "target": "192.168.1.1",
            "t1_interval_seconds": 60,  # Wrong: should be >= t2
            "t2_interval_seconds": 120,  # t2 > t1 violates t3 <= t2 <= t1
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


class TestAutoPerfCycleTask:
    """Test AutoPerf cycle task logic with real DAL."""

    @pytest.mark.asyncio
    async def test_autoperf_cycle_breach_escalates_and_retunes(
        self, real_dal: AsyncDB
    ) -> None:
        """Breach path: cycle detects alert_events, escalates tier, retunes interval."""
        from hub_api.modules.perftest_cluster.worker.tasks import _autoperf_cycle_async

        tenant = str(uuid4())
        device_id = str(uuid4())
        autoperf_mgr = AutoPerfManager(real_dal)

        # Create policy
        policy = await autoperf_mgr.create_policy(
            tenant=tenant,
            name="breach-test",
            device_id=device_id,
            target="192.168.1.1",
            t1_interval_seconds=300,
            t2_interval_seconds=120,
            t3_interval_seconds=60,
            deescalate_after_clean=2,
        )
        policy_id = policy["id"]

        # Get the job to see initial interval
        jobs_rowset = await real_dal(
            (real_dal.scheduled_jobs.tenant == tenant)
            & (real_dal.scheduled_jobs.job_type == "autoperf_cycle")
        ).select()
        assert len(jobs_rowset) == 1
        job_id = jobs_rowset.first()["id"]

        # Verify initial state: tier 1, interval 300
        initial_state = await autoperf_mgr.get_state(tenant, policy_id)
        assert initial_state["current_tier"] == 1
        jobs_rowset = await real_dal(real_dal.scheduled_jobs.id == job_id).select()
        assert jobs_rowset.first()["interval_seconds"] == 300

        # Insert an alert event after state's last_cycle_at (None = epoch)
        now = datetime.now(timezone.utc)
        await real_dal.alert_events.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            rule_id=str(uuid4()),
            device_id=device_id,
            observed_value=999.0,
            fired_at=now,
            notified=True,
        )

        # Fake engine factory that does nothing
        async def fake_engine(device):

            class FakeEngine:
                async def run_test(self, test_type, target):
                    return {"latency_ms": 10, "throughput": 100, "output": "ok"}

            return FakeEngine()

        # Run cycle
        await _autoperf_cycle_async(
            job_id="job1",
            tenant=tenant,
            module="perftest_cluster",
            job_type="autoperf_cycle",
            payload={"policy_id": policy_id},
            db=real_dal,
            engine_factory=fake_engine,
        )

        # Verify escalation: tier 1 + breach = tier 2, clean_cycles 0
        state = await autoperf_mgr.get_state(tenant, policy_id)
        assert state["current_tier"] == 2
        assert state["clean_cycles"] == 0

        # Verify interval retuned to t2 (120)
        jobs_rowset = await real_dal(real_dal.scheduled_jobs.id == job_id).select()
        assert jobs_rowset.first()["interval_seconds"] == 120

    @pytest.mark.asyncio
    async def test_autoperf_cycle_clean_path_counts_and_deescalates(
        self, real_dal: AsyncDB
    ) -> None:
        """Clean path: N clean cycles de-escalate one tier, reset counter."""
        from hub_api.modules.perftest_cluster.worker.tasks import _autoperf_cycle_async

        tenant = str(uuid4())
        device_id = str(uuid4())
        autoperf_mgr = AutoPerfManager(real_dal)

        # Create policy and manually escalate to tier 2
        policy = await autoperf_mgr.create_policy(
            tenant=tenant,
            name="clean-test",
            device_id=device_id,
            target="192.168.1.1",
            deescalate_after_clean=2,
        )
        policy_id = policy["id"]

        # Manually set state to tier 2
        now = datetime.now(timezone.utc)
        await real_dal(
            (real_dal.autoperf_state.tenant == tenant)
            & (real_dal.autoperf_state.policy_id == policy_id)
        ).update(
            current_tier=2,
            clean_cycles=0,
            last_cycle_at=now - timedelta(seconds=300),
            updated_at=now,
        )

        # Fake engine factory
        async def fake_engine(device):

            class FakeEngine:
                async def run_test(self, test_type, target):
                    return {"latency_ms": 10, "throughput": 100, "output": "ok"}

            return FakeEngine()

        # Run first clean cycle
        await _autoperf_cycle_async(
            job_id="job2",
            tenant=tenant,
            module="perftest_cluster",
            job_type="autoperf_cycle",
            payload={"policy_id": policy_id},
            db=real_dal,
            engine_factory=fake_engine,
        )

        # Should still be tier 2, clean_cycles=1 (< deescalate_after_clean)
        state = await autoperf_mgr.get_state(tenant, policy_id)
        assert state["current_tier"] == 2
        assert state["clean_cycles"] == 1

        # Run second clean cycle
        await _autoperf_cycle_async(
            job_id="job3",
            tenant=tenant,
            module="perftest_cluster",
            job_type="autoperf_cycle",
            payload={"policy_id": policy_id},
            db=real_dal,
            engine_factory=fake_engine,
        )

        # Should de-escalate to tier 1, reset clean_cycles to 0
        state = await autoperf_mgr.get_state(tenant, policy_id)
        assert state["current_tier"] == 1
        assert state["clean_cycles"] == 0

    @pytest.mark.asyncio
    async def test_autoperf_cycle_engine_failure_records_failed_and_continues(
        self, real_dal: AsyncDB
    ) -> None:
        """Engine failure: test result marked failed, cycle still calls record_cycle."""
        from hub_api.modules.perftest_cluster.worker.tasks import _autoperf_cycle_async
        from hub_api.modules.perftest_cluster.services.engine_client import EngineError

        tenant = str(uuid4())
        device_id = str(uuid4())
        autoperf_mgr = AutoPerfManager(real_dal)

        # Create policy
        policy = await autoperf_mgr.create_policy(
            tenant=tenant,
            name="engine-fail-test",
            device_id=device_id,
            target="192.168.1.1",
        )
        policy_id = policy["id"]

        # Fake engine factory that raises an error
        async def failing_engine(device):

            class FailingEngine:
                async def run_test(self, test_type, target):
                    raise EngineError("Network unreachable")

            return FailingEngine()

        # Run cycle
        await _autoperf_cycle_async(
            job_id="job4",
            tenant=tenant,
            module="perftest_cluster",
            job_type="autoperf_cycle",
            payload={"policy_id": policy_id},
            db=real_dal,
            engine_factory=failing_engine,
        )

        # Verify test results were recorded as failed
        tests_rowset = await real_dal(
            (real_dal.perf_test_results.tenant == tenant)
            & (real_dal.perf_test_results.device_id == device_id)
        ).select()
        assert len(tests_rowset) >= 1  # At least one test attempt
        for test in tests_rowset:
            assert test["status"] == "failed"

        # Verify cycle still called record_cycle (state was updated)
        state = await autoperf_mgr.get_state(tenant, policy_id)
        assert state is not None
        # First cycle, no breach (no alert_events), so clean -> tier stays 1
        assert state["current_tier"] == 1
