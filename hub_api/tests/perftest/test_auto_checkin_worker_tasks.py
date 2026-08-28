"""Tests for the AutoCheckIn worker cycle: jitter, stats, cascade gate, breach."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.auto_checkin_manager import (
    AutoCheckInManager,
)
from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.engine_client import EngineError
from hub_api.modules.perftest_cluster.worker import tasks as wpc_tasks


class _FakeEngineFixedLatency:
    """Engine stub returning a fixed latency for every sample."""

    def __init__(self, latency_ms: float) -> None:
        self.latency_ms = latency_ms
        self.calls: list[str] = []

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(test_type)
        return {"latency_ms": self.latency_ms, "throughput": None, "output": "ok"}


class _FakeEngineSequence:
    """Engine stub returning successive latencies from a fixed list."""

    def __init__(self, latencies: list[float]) -> None:
        self._latencies = iter(latencies)

    async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
        return {"latency_ms": next(self._latencies), "throughput": None, "output": "ok"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_jittered_interval_zero_pct_returns_base() -> None:
    """jitter_pct=0 always returns the base interval, regardless of rng."""
    assert wpc_tasks._jittered_interval_seconds(300, 0, rng=lambda: 0.99) == 300


def test_jittered_interval_bounds() -> None:
    """rng=0.0 -> lower bound (base * (1 - pct/100)); rng=1.0 -> upper bound."""
    assert wpc_tasks._jittered_interval_seconds(300, 10, rng=lambda: 0.0) == 270
    assert wpc_tasks._jittered_interval_seconds(300, 10, rng=lambda: 1.0) == 330
    assert wpc_tasks._jittered_interval_seconds(300, 10, rng=lambda: 0.5) == 300


def test_compute_sample_stats_empty_returns_none() -> None:
    """No samples collected -> no stats to evaluate."""
    assert wpc_tasks._compute_sample_stats([]) is None


def test_compute_sample_stats_single_sample_zero_stddev() -> None:
    """A single sample has population stddev 0.0 (not a StatisticsError)."""
    mean, stddev = wpc_tasks._compute_sample_stats([42.0])
    assert mean == 42.0
    assert stddev == 0.0


def test_compute_sample_stats_mean_and_stddev() -> None:
    """Known population mean/stddev for [10, 20, 30]."""
    mean, stddev = wpc_tasks._compute_sample_stats([10.0, 20.0, 30.0])
    assert mean == pytest.approx(20.0)
    assert stddev == pytest.approx(8.16496580927726)


def test_evaluate_threshold_breach_no_thresholds_never_breaches() -> None:
    """All three thresholds None -> never breaches."""
    assert wpc_tasks._evaluate_threshold_breach(999.0, 999.0, None, None, None) is False


def test_evaluate_threshold_breach_max_exceeded() -> None:
    assert wpc_tasks._evaluate_threshold_breach(10.0, 60.0, None, 50.0, None) is True


def test_evaluate_threshold_breach_min_undershoot() -> None:
    assert wpc_tasks._evaluate_threshold_breach(10.0, 1.0, 5.0, None, None) is True


def test_evaluate_threshold_breach_mean_exceeded() -> None:
    assert wpc_tasks._evaluate_threshold_breach(500.0, 5.0, None, None, 200.0) is True


def test_evaluate_threshold_breach_within_bounds() -> None:
    assert wpc_tasks._evaluate_threshold_breach(50.0, 10.0, 5.0, 50.0, 100.0) is False


# ---------------------------------------------------------------------------
# _apply_jitter (DB-touching)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_jitter_updates_next_run_at(real_dal: AsyncDB) -> None:
    """_apply_jitter writes a new next_run_at within the jittered bound."""
    from hub_api.scheduler.job_manager import JobManager

    jm = JobManager(real_dal)
    job = await jm.create_job(
        tenant="t1",
        module="perftest_cluster",
        job_type="auto_checkin",
        payload={"checkin_id": "c1"},
        interval_seconds=300,
    )
    before = job["next_run_at"]

    await wpc_tasks._apply_jitter(real_dal, job["id"], 300, 10, rng=lambda: 1.0)

    updated = await jm.get_job("t1", job["id"])
    # SQLite round-trips datetimes as naive (see test_scheduler_sweep.py for the
    # same established .replace(tzinfo=None) pattern against this real_dal fixture).
    assert updated["next_run_at"].replace(tzinfo=None) > before.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# _auto_checkin_cycle_async (full cycle, real_dal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_checkin_cycle_tier1_runs_samples_and_records_state(
    real_dal: AsyncDB,
) -> None:
    """Tier-1 always runs; samples_per_run * len(test_types) probes executed."""
    device_mgr = DeviceManager(real_dal, "t1")
    device, _key = await device_mgr.register_device({"name": "d1", "serial": "SN1"})

    manager = AutoCheckInManager(real_dal)
    checkin = await manager.create_checkin(
        tenant="t1",
        name="baseline",
        device_id=device.id,
        target_kind="external",
        target="example.com",
        test_types=["icmp", "http"],
        samples_per_run=3,
        threshold_stddev_max=100.0,
    )

    engine = _FakeEngineFixedLatency(12.5)
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1",
        tenant="t1",
        module="perftest_cluster",
        job_type="auto_checkin",
        payload={"checkin_id": checkin["id"]},
        db=real_dal,
        engine_factory=lambda device: engine,
    )

    assert len(engine.calls) == 6  # 2 test_types * 3 samples

    state = await manager.get_state("t1", checkin["id"])
    assert state["last_breached"] is False
    assert state["last_mean_latency_ms"] == pytest.approx(12.5)
    assert state["last_stddev_latency_ms"] == pytest.approx(0.0)
    assert state["last_run_at"] is not None


@pytest.mark.asyncio
async def test_auto_checkin_cycle_breach_writes_alert_event(real_dal: AsyncDB) -> None:
    """A stddev-max breach writes an alert_events row keyed by the check-in id."""
    device_mgr = DeviceManager(real_dal, "t1")
    device, _key = await device_mgr.register_device({"name": "d2", "serial": "SN2"})

    manager = AutoCheckInManager(real_dal)
    checkin = await manager.create_checkin(
        tenant="t1",
        name="jittery",
        device_id=device.id,
        target_kind="external",
        target="example.com",
        test_types=["icmp"],
        samples_per_run=3,
        threshold_stddev_max=1.0,
    )

    engine = _FakeEngineSequence([1.0, 50.0, 100.0])
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1",
        tenant="t1",
        module="perftest_cluster",
        job_type="auto_checkin",
        payload={"checkin_id": checkin["id"]},
        db=real_dal,
        engine_factory=lambda device: engine,
    )

    state = await manager.get_state("t1", checkin["id"])
    assert state["last_breached"] is True

    events = await real_dal(
        (real_dal.alert_events.tenant == "t1") & (real_dal.alert_events.rule_id == checkin["id"])
    ).select()
    assert len(events) == 1
    assert events[0].device_id == device.id


@pytest.mark.asyncio
async def test_auto_checkin_cycle_tier2_skipped_when_parent_not_breached(
    real_dal: AsyncDB,
) -> None:
    """A tier-2 check-in whose parent hasn't breached runs no probes."""
    manager = AutoCheckInManager(real_dal)
    tier1 = await manager.create_checkin(
        tenant="t1",
        name="t1",
        device_id="dev1",
        target_kind="external",
        target="example.com",
        test_types=["icmp"],
        tier=1,
    )
    tier2 = await manager.create_checkin(
        tenant="t1",
        name="t2",
        device_id="dev1",
        target_kind="external",
        target="example.com",
        test_types=["throughput"],
        tier=2,
        parent_checkin_id=tier1["id"],
    )

    engine = _FakeEngineFixedLatency(5.0)
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job2",
        tenant="t1",
        module="perftest_cluster",
        job_type="auto_checkin",
        payload={"checkin_id": tier2["id"]},
        db=real_dal,
        engine_factory=lambda device: engine,
    )

    assert engine.calls == []
    state = await manager.get_state("t1", tier2["id"])
    assert state["last_run_at"] is None  # untouched: cycle was a no-op


@pytest.mark.asyncio
async def test_auto_checkin_cycle_tier2_runs_when_parent_breached(
    real_dal: AsyncDB,
) -> None:
    """A tier-2 check-in runs its probes once its parent's state is breached."""
    device_mgr = DeviceManager(real_dal, "t1")
    device, _key = await device_mgr.register_device({"name": "d3", "serial": "SN3"})

    manager = AutoCheckInManager(real_dal)
    tier1 = await manager.create_checkin(
        tenant="t1",
        name="t1",
        device_id=device.id,
        target_kind="external",
        target="example.com",
        test_types=["icmp"],
        tier=1,
    )
    tier2 = await manager.create_checkin(
        tenant="t1",
        name="t2",
        device_id=device.id,
        target_kind="external",
        target="example.com",
        test_types=["throughput"],
        tier=2,
        parent_checkin_id=tier1["id"],
    )

    now = datetime.now(timezone.utc)
    await real_dal(real_dal.auto_checkin_state.checkin_id == tier1["id"]).update(
        last_breached=True,
        last_run_at=now,
        updated_at=now,
    )

    engine = _FakeEngineFixedLatency(5.0)
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job2",
        tenant="t1",
        module="perftest_cluster",
        job_type="auto_checkin",
        payload={"checkin_id": tier2["id"]},
        db=real_dal,
        engine_factory=lambda device: engine,
    )

    assert engine.calls == ["throughput"]
    state = await manager.get_state("t1", tier2["id"])
    assert state["last_run_at"] is not None


@pytest.mark.asyncio
async def test_auto_checkin_cycle_missing_checkin_returns_early(real_dal: AsyncDB) -> None:
    """Unknown checkin_id logs a warning and returns without raising."""
    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1",
        tenant="t1",
        module="perftest_cluster",
        job_type="auto_checkin",
        payload={"checkin_id": "ghost"},
        db=real_dal,
    )  # must not raise


@pytest.mark.asyncio
async def test_auto_checkin_cycle_engine_error_recorded_as_failed_sample(
    real_dal: AsyncDB,
) -> None:
    """EngineError during a sample is recorded as a failed PerfTestResult, not raised."""
    manager = AutoCheckInManager(real_dal)
    checkin = await manager.create_checkin(
        tenant="t1",
        name="flaky",
        device_id="dev1",
        target_kind="external",
        target="example.com",
        test_types=["icmp"],
        samples_per_run=1,
    )

    class _FakeEngineError:
        async def run_test(self, test_type: str, target: str, **kwargs: Any) -> dict[str, Any]:
            raise EngineError("engine unreachable")

    await wpc_tasks._auto_checkin_cycle_async(
        job_id="job1",
        tenant="t1",
        module="perftest_cluster",
        job_type="auto_checkin",
        payload={"checkin_id": checkin["id"]},
        db=real_dal,
        engine_factory=lambda device: _FakeEngineError(),
    )  # must not raise

    state = await manager.get_state("t1", checkin["id"])
    assert state["last_mean_latency_ms"] is None  # no successful samples collected


def test_auto_checkin_cycle_celery_wrapper_invokes_asyncio_run(monkeypatch) -> None:
    """The sync Celery task wrapper delegates to asyncio.run with the async core."""
    called = {}

    def fake_run(coro: Any) -> None:
        called["coro"] = coro
        coro.close()

    monkeypatch.setattr(wpc_tasks.asyncio, "run", fake_run)
    wpc_tasks.auto_checkin_cycle(
        "job1", "t1", "perftest_cluster", "auto_checkin", {"checkin_id": "c1"}
    )
    assert "coro" in called
