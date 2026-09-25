"""Coverage backfill for perftest_cluster/worker/tasks.py.

Exercises the async core logic (_execute_and_store_test, _run_server_test_async,
_alert_sweep_async, _autoperf_cycle_async) directly with injected db/engine_factory,
plus the sync Celery task wrappers via asyncio.run patched to a no-op capturing shim.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.autoperf_manager import AutoPerfManager
from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.engine_client import EngineError
from hub_api.modules.perftest_cluster.worker import tasks as wpc_tasks


class _FakeEngineOK:
    """Engine stub that returns a canned successful result."""

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        """Return a fixed passing result."""
        return {"latency_ms": 12.5, "throughput": 99.0, "output": "ok"}


class _FakeEngineError:
    """Engine stub that raises EngineError."""

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        """Raise EngineError to simulate an engine-side failure."""
        raise EngineError("engine unreachable")


class _FakeEngineUnexpected:
    """Engine stub that raises a generic exception."""

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        """Raise a plain exception to simulate an unexpected failure."""
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# _execute_and_store_test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_and_store_device_not_found(real_dal: AsyncDB) -> None:
    """Missing device records a failed test result and returns False."""
    ok = await wpc_tasks._execute_and_store_test(
        real_dal,
        "tenant-x",
        "ghost-device",
        "icmp",
        "1.2.3.4",
        engine_factory=lambda d: _FakeEngineOK(),
    )
    assert ok is False

    results = await real_dal(real_dal.perf_test_results.tenant == "tenant-x").select()
    assert len(results) == 1
    assert results.first()["status"] == "failed"
    assert "not found" in results.first()["test_output"].lower()


@pytest.mark.asyncio
async def test_execute_and_store_success(real_dal: AsyncDB) -> None:
    """A successful engine run records a completed result and returns True."""
    tenant = "tenant-exec-ok"
    dev_mgr = DeviceManager(real_dal, tenant)
    device, _key = await dev_mgr.register_device({"name": "d", "serial": "SN"})

    ok = await wpc_tasks._execute_and_store_test(
        real_dal,
        tenant,
        device.id,
        "icmp",
        "1.2.3.4",
        engine_factory=lambda d: _FakeEngineOK(),
    )
    assert ok is True

    results = await real_dal(real_dal.perf_test_results.tenant == tenant).select()
    assert len(results) == 1
    assert results.first()["status"] == "completed"
    assert results.first()["latency_ms"] == 12.5


@pytest.mark.asyncio
async def test_execute_and_store_engine_error(real_dal: AsyncDB) -> None:
    """An EngineError during the run records a failed result, returns False."""
    tenant = "tenant-exec-engineerr"
    dev_mgr = DeviceManager(real_dal, tenant)
    device, _key = await dev_mgr.register_device({"name": "d2", "serial": "SN2"})

    ok = await wpc_tasks._execute_and_store_test(
        real_dal,
        tenant,
        device.id,
        "icmp",
        "1.2.3.4",
        engine_factory=lambda d: _FakeEngineError(),
    )
    assert ok is False

    results = await real_dal(real_dal.perf_test_results.tenant == tenant).select()
    assert results.first()["status"] == "failed"
    assert "engine error" in results.first()["test_output"].lower()


@pytest.mark.asyncio
async def test_execute_and_store_unexpected_error(real_dal: AsyncDB) -> None:
    """A generic exception during the run records a failed result, returns False."""
    tenant = "tenant-exec-unexpected"
    dev_mgr = DeviceManager(real_dal, tenant)
    device, _key = await dev_mgr.register_device({"name": "d3", "serial": "SN3"})

    ok = await wpc_tasks._execute_and_store_test(
        real_dal,
        tenant,
        device.id,
        "icmp",
        "1.2.3.4",
        engine_factory=lambda d: _FakeEngineUnexpected(),
    )
    assert ok is False

    results = await real_dal(real_dal.perf_test_results.tenant == tenant).select()
    assert results.first()["status"] == "failed"


@pytest.mark.asyncio
async def test_execute_and_store_outer_exception_returns_false(
    real_dal: AsyncDB, monkeypatch: Any
) -> None:
    """An exception raised outside the inner try (e.g. DeviceManager.get_device) is caught."""

    async def _boom(self: Any, device_id: str) -> None:
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(DeviceManager, "get_device", _boom)

    ok = await wpc_tasks._execute_and_store_test(
        real_dal,
        "tenant-outer-exc",
        "dev-1",
        "icmp",
        "1.2.3.4",
        engine_factory=lambda d: _FakeEngineOK(),
    )
    assert ok is False


# ---------------------------------------------------------------------------
# _run_server_test_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_server_test_async_invalid_payload(real_dal: AsyncDB) -> None:
    """A payload missing required keys logs a warning and returns without raising."""
    await wpc_tasks._run_server_test_async(
        job_id="job-1",
        tenant="tenant-payload",
        module="perftest_cluster",
        job_type="server_test",
        payload={"device_id": "d"},  # missing test_type/target
        db=real_dal,
    )
    # No result should have been recorded since payload validation short-circuits.
    results = await real_dal(real_dal.perf_test_results.tenant == "tenant-payload").select()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_run_server_test_async_success(real_dal: AsyncDB) -> None:
    """A valid payload executes and stores a test result via the injected engine."""
    tenant = "tenant-run-server"
    dev_mgr = DeviceManager(real_dal, tenant)
    device, _key = await dev_mgr.register_device({"name": "d", "serial": "SN"})

    await wpc_tasks._run_server_test_async(
        job_id="job-2",
        tenant=tenant,
        module="perftest_cluster",
        job_type="server_test",
        payload={"device_id": device.id, "test_type": "icmp", "target": "1.2.3.4"},
        db=real_dal,
        engine_factory=lambda d: _FakeEngineOK(),
    )
    results = await real_dal(real_dal.perf_test_results.tenant == tenant).select()
    assert len(results) == 1
    assert results.first()["status"] == "completed"


@pytest.mark.asyncio
async def test_run_server_test_async_outer_exception_swallowed(
    real_dal: AsyncDB, monkeypatch: Any
) -> None:
    """An unexpected exception in the outer try/except is logged, not raised."""

    async def _boom(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(wpc_tasks, "_execute_and_store_test", _boom)

    await wpc_tasks._run_server_test_async(
        job_id="job-3",
        tenant="tenant-outer",
        module="perftest_cluster",
        job_type="server_test",
        payload={"device_id": "d", "test_type": "icmp", "target": "1.2.3.4"},
        db=real_dal,
    )


def test_run_server_test_celery_wrapper_invokes_asyncio_run(monkeypatch: Any) -> None:
    """The sync Celery task wrapper delegates to asyncio.run(_run_server_test_async(...))."""
    captured: dict[str, Any] = {}

    def fake_run(coro: Any) -> None:
        captured["called"] = True
        coro.close()  # avoid "coroutine was never awaited" warning

    monkeypatch.setattr(wpc_tasks.asyncio, "run", fake_run)

    wpc_tasks.run_server_test(
        job_id="job-4",
        tenant="tenant-wrapper",
        module="perftest_cluster",
        job_type="server_test",
        payload={"device_id": "d", "test_type": "icmp", "target": "x"},
    )
    assert captured.get("called") is True


# ---------------------------------------------------------------------------
# _alert_sweep_async / alert_sweep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_sweep_async_runs_evaluator(real_dal: AsyncDB) -> None:
    """_alert_sweep_async delegates to AlertEvaluator.sweep() and returns its count."""
    fired = await wpc_tasks._alert_sweep_async(db=real_dal)
    assert fired == 0


def test_alert_sweep_celery_wrapper(monkeypatch: Any) -> None:
    """The sync alert_sweep task wrapper delegates to asyncio.run(_alert_sweep_async())."""
    captured: dict[str, Any] = {}

    def fake_run(coro: Any) -> None:
        captured["called"] = True
        coro.close()

    monkeypatch.setattr(wpc_tasks.asyncio, "run", fake_run)
    wpc_tasks.alert_sweep()
    assert captured.get("called") is True


# ---------------------------------------------------------------------------
# _autoperf_cycle_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autoperf_cycle_invalid_payload(real_dal: AsyncDB) -> None:
    """A payload missing policy_id logs a warning and returns without raising."""
    await wpc_tasks._autoperf_cycle_async(
        job_id="j",
        tenant="tenant-ap",
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={},
        db=real_dal,
    )


@pytest.mark.asyncio
async def test_autoperf_cycle_policy_not_found(real_dal: AsyncDB) -> None:
    """An unknown policy_id logs a warning and returns without raising."""
    await wpc_tasks._autoperf_cycle_async(
        job_id="j",
        tenant="tenant-ap2",
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={"policy_id": "ghost"},
        db=real_dal,
    )


@pytest.mark.asyncio
async def test_autoperf_cycle_state_not_found(real_dal: AsyncDB, monkeypatch: Any) -> None:
    """A policy that exists but has no state row logs a warning and returns."""
    tenant = "tenant-ap3"
    policy_id = str(uuid4())
    await real_dal.autoperf_policies.async_insert(
        id=policy_id,
        tenant=tenant,
        name="p",
        device_id="d",
        target="1.2.3.4",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )
    # No autoperf_state row inserted -> get_state returns None.
    await wpc_tasks._autoperf_cycle_async(
        job_id="j",
        tenant=tenant,
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={"policy_id": policy_id},
        db=real_dal,
    )


@pytest.mark.asyncio
async def test_autoperf_cycle_tier1_no_breach_runs_and_advances(
    real_dal: AsyncDB,
) -> None:
    """A tier-1 cycle with no breach executes the baseline path-localization
    probe set (http_trace/traceroute/udp) and records a clean cycle."""
    tenant = "tenant-ap4"
    dev_mgr = DeviceManager(real_dal, tenant)
    device, _key = await dev_mgr.register_device({"name": "d", "serial": "SN"})

    mgr = AutoPerfManager(real_dal)
    policy = await mgr.create_policy(
        tenant=tenant,
        name="p",
        device_id=device.id,
        target="1.2.3.4",
    )

    await wpc_tasks._autoperf_cycle_async(
        job_id="j",
        tenant=tenant,
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={"policy_id": policy["id"]},
        db=real_dal,
        engine_factory=lambda d: _FakeEngineOK(),
    )

    state = await mgr.get_state(tenant, policy["id"])
    assert state["last_cycle_at"] is not None

    results = await real_dal(real_dal.perf_test_results.tenant == tenant).select()
    # tier 1 -> http_trace + traceroute + udp + http2 = 4 tests executed
    assert len(results) == 4
    assert {r["test_type"] for r in results} == {
        "http_trace",
        "traceroute",
        "udp",
        "http2",
    }


@pytest.mark.asyncio
async def test_autoperf_cycle_tier3_breach_runs_full_suite(real_dal: AsyncDB) -> None:
    """A tier-3 policy runs the baseline set plus the heavy throughput test."""
    tenant = "tenant-ap5"
    dev_mgr = DeviceManager(real_dal, tenant)
    device, _key = await dev_mgr.register_device({"name": "d", "serial": "SN"})

    mgr = AutoPerfManager(real_dal)
    policy = await mgr.create_policy(
        tenant=tenant,
        name="p",
        device_id=device.id,
        target="1.2.3.4",
    )
    # Force tier to 3 directly.
    await real_dal(
        (real_dal.autoperf_state.tenant == tenant)
        & (real_dal.autoperf_state.policy_id == policy["id"])
    ).update(current_tier=3)

    await wpc_tasks._autoperf_cycle_async(
        job_id="j",
        tenant=tenant,
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={"policy_id": policy["id"]},
        db=real_dal,
        engine_factory=lambda d: _FakeEngineOK(),
    )

    results = await real_dal(real_dal.perf_test_results.tenant == tenant).select()
    # tier 3 -> http_trace, traceroute, udp, http2, throughput = 5 tests
    assert len(results) == 5
    assert {r["test_type"] for r in results} == {
        "http_trace",
        "traceroute",
        "udp",
        "http2",
        "throughput",
    }


@pytest.mark.asyncio
async def test_autoperf_cycle_detects_breach_from_alert_events(
    real_dal: AsyncDB,
) -> None:
    """A prior alert_event fired after last_cycle_at is detected as a breach."""
    tenant = "tenant-ap6"
    dev_mgr = DeviceManager(real_dal, tenant)
    device, _key = await dev_mgr.register_device({"name": "d", "serial": "SN"})

    mgr = AutoPerfManager(real_dal)
    policy = await mgr.create_policy(
        tenant=tenant,
        name="p",
        device_id=device.id,
        target="1.2.3.4",
    )

    # Seed an alert event fired "now" (after epoch last_cycle_at=None -> epoch).
    await real_dal.alert_events.async_insert(
        id=str(uuid4()),
        tenant=tenant,
        rule_id=str(uuid4()),
        device_id=device.id,
        observed_value=999.0,
        fired_at=datetime.now(timezone.utc),
        notified=False,
    )

    await wpc_tasks._autoperf_cycle_async(
        job_id="j",
        tenant=tenant,
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={"policy_id": policy["id"]},
        db=real_dal,
        engine_factory=lambda d: _FakeEngineOK(),
    )

    state = await mgr.get_state(tenant, policy["id"])
    # Breach detected -> escalated from tier 1 to tier 2.
    assert state["current_tier"] == 2


@pytest.mark.asyncio
async def test_autoperf_cycle_outer_exception_swallowed(
    real_dal: AsyncDB, monkeypatch: Any
) -> None:
    """An unexpected exception anywhere in the cycle is caught and logged, not raised."""

    async def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(AutoPerfManager, "get_state", _boom)

    tenant = "tenant-ap7"
    policy_id = str(uuid4())
    await real_dal.autoperf_policies.async_insert(
        id=policy_id,
        tenant=tenant,
        name="p",
        device_id="d",
        target="x",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )

    await wpc_tasks._autoperf_cycle_async(
        job_id="j",
        tenant=tenant,
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={"policy_id": policy_id},
        db=real_dal,
    )


def test_autoperf_cycle_celery_wrapper(monkeypatch: Any) -> None:
    """The sync autoperf_cycle task wrapper delegates to asyncio.run(...)."""
    captured: dict[str, Any] = {}

    def fake_run(coro: Any) -> None:
        captured["called"] = True
        coro.close()

    monkeypatch.setattr(wpc_tasks.asyncio, "run", fake_run)
    wpc_tasks.autoperf_cycle(
        job_id="j",
        tenant="t",
        module="perftest_cluster",
        job_type="autoperf_cycle",
        payload={"policy_id": "p"},
    )
    assert captured.get("called") is True


# ---------------------------------------------------------------------------
# db=None branch: fresh AsyncDB construction failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_server_test_async_db_creation_failure(monkeypatch: Any) -> None:
    """When db=None and AsyncDB construction fails, the function logs and returns."""

    def _boom_reflect(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("cannot connect")

    monkeypatch.setattr(wpc_tasks, "build_db_uri", lambda cfg: "sqlite:///:memory:")
    monkeypatch.setattr(
        wpc_tasks.AsyncDB,
        "__init__",
        lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("cannot connect")),
    )

    await wpc_tasks._run_server_test_async(
        job_id="j",
        tenant="t",
        module="perftest_cluster",
        job_type="server_test",
        payload={"device_id": "d", "test_type": "icmp", "target": "x"},
        db=None,
    )
