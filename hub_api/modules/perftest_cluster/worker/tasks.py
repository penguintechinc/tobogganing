"""Celery tasks for WaddlePerf cluster scheduled server tests and AutoPerf.

Tasks execute scheduled server tests, record results, and run tiered AutoPerf cycles.
"""

from __future__ import annotations

import asyncio
import json
import random
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

import structlog
from penguin_dal import AsyncDB

from hub_api.config import Config, build_db_uri
from hub_api.modules.perftest_cluster.services.autoperf_manager import AutoPerfManager
from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.engine_client import EngineClient, EngineError
from hub_api.modules.perftest_cluster.services.test_manager import TestManager
from hub_api.scheduler.celery_app import celery_app

logger = structlog.get_logger()

# Type for the engine factory (can be injected in tests)
EngineFactory = Callable[[dict[str, Any]], EngineClient]


def _default_engine_factory(device: dict[str, Any]) -> EngineClient:
    """Create an EngineClient for a device.

    Args:
        device: Device dict (with device_metadata containing engine_url if available)

    Returns:
        EngineClient instance
    """
    # For scheduled tests, use the default engine URL from environment
    # Device-specific engine URLs may be added to metadata in the future
    return EngineClient()


def _test_types_for_tier(tier: int) -> list[str]:
    """Determine the AutoPerf test set to run for a monitoring tier.

    Tier 1 (continuous baseline) runs cheap path-localization probes --
    http_trace (HTTP/1.1 hop tracing), traceroute, udp, and http2 (an
    HTTP/2-specific reachability/latency ping run alongside http_trace,
    since h2 multiplexing/HOL and CDN/proxy handling can diverge from
    h1.1) -- distinguishing wifi vs ISP vs upstream vs whole-path issues,
    including issues specific to the HTTP/2 traffic most real sites use.
    On a threshold breach, the policy escalates to tier 2+ (see
    AutoPerfManager.record_cycle), which additionally runs the heavier
    "throughput" test (EngineClient's ThroughputBackend, currently the
    testserver's /speedtest endpoint) to confirm and quantify the
    degradation.

    Args:
        tier: Current AutoPerf tier. The escalation state machine caps at
            3, but there is currently only one heavy-diagnostic set, so
            tier 2 and tier 3 both run the same test types.

    Returns:
        Ordered list of test types to execute this cycle.
    """
    test_types = ["http_trace", "traceroute", "udp", "http2"]
    if tier >= 2:
        test_types.append("throughput")
    return test_types


def _jittered_interval_seconds(
    base_interval_seconds: int,
    jitter_pct: int,
    rng: Callable[[], float] = random.random,
) -> int:
    """Compute a jittered interval, +/- jitter_pct percent of the base.

    Args:
        base_interval_seconds: The check-in's configured interval in seconds.
        jitter_pct: 0-10, the maximum +/- percentage swing.
        rng: Random source returning a float in [0, 1) (default random.random;
            injectable for deterministic tests).

    Returns:
        Jittered interval in seconds, floored at 1 second.
    """
    if jitter_pct <= 0:
        return base_interval_seconds
    delta_fraction = (rng() * 2 - 1) * (jitter_pct / 100)
    jittered = base_interval_seconds * (1 + delta_fraction)
    return max(1, round(jittered))


async def _apply_jitter(
    db: Any,
    job_id: str,
    base_interval_seconds: int,
    jitter_pct: int,
    rng: Callable[[], float] = random.random,
) -> None:
    """Nudge a scheduled_jobs row's next_run_at by +/- jitter_pct percent.

    The generic sweep (hub_api/scheduler/tasks.py::_sweep_async) already
    advanced next_run_at to now + interval_seconds via JobManager.mark_ran()
    before this task's body ran (fire-and-forget dispatch). This is a second,
    targeted write that layers jitter on top -- JobManager's shared mark_ran
    signature (used by every job type) is intentionally left untouched.

    Args:
        db: AsyncDB instance.
        job_id: The auto_checkin's scheduled_jobs row id.
        base_interval_seconds: The check-in's configured interval in seconds.
        jitter_pct: 0-10.
        rng: Injectable random source (see _jittered_interval_seconds).
    """
    jittered_seconds = _jittered_interval_seconds(base_interval_seconds, jitter_pct, rng)
    next_run_at = datetime.now(timezone.utc) + timedelta(seconds=jittered_seconds)
    await db(db.scheduled_jobs.id == job_id).update(next_run_at=next_run_at)


def _compute_sample_stats(latencies: list[float]) -> tuple[float, float] | None:
    """Compute (mean, population stddev) across a cycle's collected latencies.

    Population stddev (not sample stddev) is used because the N samples
    collected this cycle ARE the entire population being measured for this
    cycle, not an estimate of a larger unknown population -- this also
    handles samples_per_run == 1 (stddev 0.0) without raising, unlike
    statistics.stdev which requires at least 2 data points.

    Args:
        latencies: Flat list of latency_ms values across all (test_type,
            sample) executions that returned a numeric result this cycle.

    Returns:
        (mean, stddev) tuple, or None if latencies is empty (no successful
        samples this cycle -- nothing to evaluate).
    """
    if not latencies:
        return None
    return (statistics.fmean(latencies), statistics.pstdev(latencies))


def _evaluate_threshold_breach(
    mean_latency_ms: float,
    stddev_latency_ms: float,
    threshold_stddev_min: float | None,
    threshold_stddev_max: float | None,
    threshold_mean: float | None,
) -> bool:
    """Evaluate a cycle's aggregate stats against the check-in's thresholds.

    Each of the three threshold fields is independently optional; breach is
    an OR across whichever are configured. All three None means the check-in
    has no failure condition configured (it only collects history).

    Args:
        mean_latency_ms: Cycle's aggregate mean latency.
        stddev_latency_ms: Cycle's aggregate population stddev.
        threshold_stddev_min: Optional min acceptable stddev.
        threshold_stddev_max: Optional max acceptable stddev.
        threshold_mean: Optional max acceptable mean latency.

    Returns:
        True if any configured threshold is violated.
    """
    if threshold_stddev_min is not None and stddev_latency_ms < threshold_stddev_min:
        return True
    if threshold_stddev_max is not None and stddev_latency_ms > threshold_stddev_max:
        return True
    if threshold_mean is not None and mean_latency_ms > threshold_mean:
        return True
    return False


async def _execute_auto_checkin_sample(
    db: Any,
    tenant: str,
    device_id: str,
    test_type: str,
    target: str,
    engine_factory: EngineFactory,
) -> float | None:
    """Execute one AutoCheckIn probe sample, store it, and return its latency.

    Mirrors _execute_and_store_test's device-lookup/engine-call/error-handling
    shape (same TestManager storage, same EngineError/generic-exception
    handling) but returns the sample's latency_ms instead of a bool, since
    AutoCheckIn's std-dev threshold evaluation needs the numeric samples, not
    just pass/fail. _execute_and_store_test keeps its existing bool-only
    contract untouched -- it is covered by baseline tests
    (run_server_test/autoperf_cycle) this task must not break.

    Args:
        db: AsyncDB instance.
        tenant: Tenant ID.
        device_id: Device to test.
        test_type: Type of test.
        target: Test target.
        engine_factory: Callable to create EngineClient for the device.

    Returns:
        The sample's latency_ms, or None on device-not-found/engine error/
        unexpected error (each still recorded as a failed PerfTestResult row).
    """
    device_mgr = DeviceManager(db, tenant)
    device_row = await device_mgr.get_device(device_id)
    test_mgr = TestManager(db, tenant)

    if not device_row:
        logger.warning(
            "device_not_found_for_auto_checkin_sample",
            device_id=device_id,
            tenant=tenant,
            test_type=test_type,
        )
        await test_mgr.create_test(
            {
                "device_id": device_id,
                "test_type": test_type,
                "target": target,
                "status": "failed",
                "latency_ms": None,
                "throughput": None,
                "test_output": "Device not found",
                "completed_at": datetime.now(timezone.utc),
            }
        )
        return None

    engine = engine_factory(device_row)
    try:
        result = await engine.run_test(test_type, target)
        latency = result.get("latency_ms")
        await test_mgr.create_test(
            {
                "device_id": device_id,
                "test_type": test_type,
                "target": target,
                "status": "completed",
                "latency_ms": latency,
                "throughput": result.get("throughput"),
                "test_output": result.get("output"),
                "completed_at": datetime.now(timezone.utc),
            }
        )
        return float(latency) if latency is not None else None
    except EngineError as e:
        logger.warning(
            "engine_error_during_auto_checkin_sample",
            device_id=device_id,
            test_type=test_type,
            error=str(e),
        )
        await test_mgr.create_test(
            {
                "device_id": device_id,
                "test_type": test_type,
                "target": target,
                "status": "failed",
                "latency_ms": None,
                "throughput": None,
                "test_output": f"Engine error: {str(e)}",
                "completed_at": datetime.now(timezone.utc),
            }
        )
        return None
    except Exception as e:
        logger.error(
            "unexpected_error_during_auto_checkin_sample",
            device_id=device_id,
            test_type=test_type,
            error=str(e),
        )
        await test_mgr.create_test(
            {
                "device_id": device_id,
                "test_type": test_type,
                "target": target,
                "status": "failed",
                "latency_ms": None,
                "throughput": None,
                "test_output": f"Error: {str(e)}",
                "completed_at": datetime.now(timezone.utc),
            }
        )
        return None


async def _run_auto_checkin_samples(
    db: Any,
    tenant: str,
    device_id: str,
    test_types: list[str],
    target: str,
    samples_per_run: int,
    engine_factory: EngineFactory,
) -> list[float]:
    """Run samples_per_run executions of each test_type and collect latencies.

    Args:
        db: AsyncDB instance.
        tenant: Tenant ID.
        device_id: Device to test.
        test_types: Probe types to run this cycle.
        target: Test target.
        samples_per_run: Executions per test_type (1-5).
        engine_factory: Callable to create EngineClient for the device.

    Returns:
        Flat list of latency_ms values across all (test_type, sample)
        executions that returned a numeric latency -- failed/None samples are
        skipped (already recorded as failed PerfTestResult rows).
    """
    latencies: list[float] = []
    for test_type in test_types:
        for _ in range(samples_per_run):
            latency = await _execute_auto_checkin_sample(
                db, tenant, device_id, test_type, target, engine_factory
            )
            if latency is not None:
                latencies.append(latency)
    return latencies


async def _auto_checkin_cycle_async(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
    *,
    db: Any | None = None,
    engine_factory: EngineFactory | None = None,
) -> None:
    """Execute an AutoCheckIn cycle: cascade-gate, run samples, evaluate breach, reschedule.

    Tier 1 always runs. Tier 2/3 only run their probes when the parent
    check-in's most recent cycle breached (auto_checkin_state.last_breached);
    otherwise the cycle is a no-op except for jitter rescheduling. Never
    raises -- errors are logged and swallowed, matching run_server_test/
    autoperf_cycle.

    Args:
        job_id: The scheduled_jobs row id (used for the jitter reschedule write).
        tenant: Tenant identifier.
        module: Module name (should be "perftest_cluster").
        job_type: Job type (should be "auto_checkin").
        payload: Job payload dict with checkin_id.
        db: penguin-dal AsyncDB instance (created fresh if None).
        engine_factory: Callable to create EngineClient (default: _default_engine_factory).
    """
    engine_factory = engine_factory or _default_engine_factory

    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error(
                "failed_to_create_dal_auto_checkin",
                job_id=job_id,
                tenant=tenant,
                error=str(e),
            )
            return

    try:
        checkin_id = payload.get("checkin_id")
        if not checkin_id:
            logger.warning(
                "invalid_auto_checkin_payload",
                job_id=job_id,
                tenant=tenant,
                payload=payload,
            )
            return

        checkin_rowset = await db(
            (db.auto_checkins.tenant == tenant) & (db.auto_checkins.id == checkin_id)
        ).select()
        checkin = checkin_rowset.first()
        if not checkin:
            logger.warning(
                "auto_checkin_not_found",
                job_id=job_id,
                checkin_id=checkin_id,
                tenant=tenant,
            )
            return

        if not checkin.enabled:
            return

        base_interval_seconds = checkin.interval_minutes * 60

        if checkin.tier > 1:
            if not checkin.parent_checkin_id:
                logger.error(
                    "auto_checkin_tier_missing_parent",
                    checkin_id=checkin_id,
                    tenant=tenant,
                )
                await _apply_jitter(db, job_id, base_interval_seconds, checkin.jitter_pct)
                return

            parent_state_rowset = await db(
                (db.auto_checkin_state.tenant == tenant)
                & (db.auto_checkin_state.checkin_id == checkin.parent_checkin_id)
            ).select()
            parent_state = parent_state_rowset.first()

            if not parent_state or not parent_state.last_breached:
                logger.info(
                    "auto_checkin_skipped_parent_not_breached",
                    checkin_id=checkin_id,
                    tenant=tenant,
                    tier=checkin.tier,
                )
                await _apply_jitter(db, job_id, base_interval_seconds, checkin.jitter_pct)
                return

        test_types = json.loads(checkin.test_types)
        latencies = await _run_auto_checkin_samples(
            db,
            tenant,
            checkin.device_id,
            test_types,
            checkin.target,
            checkin.samples_per_run,
            engine_factory,
        )

        stats = _compute_sample_stats(latencies)
        mean_latency_ms, stddev_latency_ms = stats if stats else (None, None)

        breached = False
        if stats is not None:
            breached = _evaluate_threshold_breach(
                mean_latency_ms,
                stddev_latency_ms,
                checkin.threshold_stddev_min,
                checkin.threshold_stddev_max,
                checkin.threshold_mean,
            )

        now = datetime.now(timezone.utc)
        state_rowset = await db(
            (db.auto_checkin_state.tenant == tenant)
            & (db.auto_checkin_state.checkin_id == checkin_id)
        ).select()
        if state_rowset.first():
            await db(
                (db.auto_checkin_state.tenant == tenant)
                & (db.auto_checkin_state.checkin_id == checkin_id)
            ).update(
                last_breached=breached,
                last_mean_latency_ms=mean_latency_ms,
                last_stddev_latency_ms=stddev_latency_ms,
                last_run_at=now,
                updated_at=now,
            )
        else:
            await db.auto_checkin_state.async_insert(
                id=str(uuid4()),
                tenant=tenant,
                checkin_id=checkin_id,
                last_breached=breached,
                last_mean_latency_ms=mean_latency_ms,
                last_stddev_latency_ms=stddev_latency_ms,
                last_run_at=now,
                updated_at=now,
            )

        if breached:
            stddev_breached = (
                checkin.threshold_stddev_max is not None
                and stddev_latency_ms > checkin.threshold_stddev_max
            ) or (
                checkin.threshold_stddev_min is not None
                and stddev_latency_ms < checkin.threshold_stddev_min
            )
            observed_value = stddev_latency_ms if stddev_breached else mean_latency_ms

            await db.alert_events.async_insert(
                id=str(uuid4()),
                tenant=tenant,
                rule_id=checkin_id,
                device_id=checkin.device_id,
                observed_value=observed_value,
                fired_at=now,
                notified=False,
            )
            try:
                from hub_api.notifications.service import NotificationService

                notifications = NotificationService(db)
                await notifications.notify(
                    tenant,
                    subject=f"AutoCheckIn breach: {checkin.name}",
                    body=(
                        f"AutoCheckIn '{checkin.name}' (tier {checkin.tier}) breached its "
                        f"threshold: mean={mean_latency_ms:.2f}ms stddev={stddev_latency_ms:.2f}ms "
                        f"target={checkin.target}"
                    ),
                )
            except Exception as e:
                logger.error(
                    "auto_checkin_notify_failed",
                    checkin_id=checkin_id,
                    tenant=tenant,
                    error=str(e),
                )

        logger.info(
            "auto_checkin_cycle_completed",
            job_id=job_id,
            checkin_id=checkin_id,
            tenant=tenant,
            tier=checkin.tier,
            breached=breached,
            sample_count=len(latencies),
        )

        await _apply_jitter(db, job_id, base_interval_seconds, checkin.jitter_pct)

    except Exception as e:
        logger.error("auto_checkin_cycle_failed", job_id=job_id, tenant=tenant, error=str(e))


@celery_app.task(name="hub_api.modules.perftest_cluster.worker.tasks.auto_checkin_cycle")
def auto_checkin_cycle(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
) -> None:
    """Celery task to run an AutoCheckIn cycle (cascade-gated probes + jitter reschedule).

    Args:
        job_id: Job ID.
        tenant: Tenant identifier.
        module: Module name.
        job_type: Job type.
        payload: Job payload dict with checkin_id.
    """
    asyncio.run(
        _auto_checkin_cycle_async(
            job_id=job_id,
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload=payload,
        )
    )


async def _execute_and_store_test(
    db: Any,
    tenant: str,
    device_id: str,
    test_type: str,
    target: str,
    engine_factory: EngineFactory,
) -> bool:
    """Execute a single test via engine and store result. Shared by server_test & autoperf.

    Executes test via engine, records result (pass or fail), and logs errors gracefully.

    Args:
        db: AsyncDB instance.
        tenant: Tenant ID.
        device_id: Device to test.
        test_type: Type of test (e.g., "icmp", "http").
        target: Test target (IP, hostname, etc.).
        engine_factory: Callable to create EngineClient for the device.

    Returns:
        True if test completed successfully, False on any error.
    """
    try:
        # Load device
        device_mgr = DeviceManager(db, tenant)
        device_row = await device_mgr.get_device(device_id)

        if not device_row:
            logger.warning(
                "device_not_found_for_test",
                device_id=device_id,
                tenant=tenant,
                test_type=test_type,
            )
            # Record failed test result
            test_mgr = TestManager(db, tenant)
            await test_mgr.create_test(
                {
                    "device_id": device_id,
                    "test_type": test_type,
                    "target": target,
                    "status": "failed",
                    "latency_ms": None,
                    "throughput": None,
                    "test_output": "Device not found",
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            return False

        # Execute test via engine
        engine = engine_factory(device_row)
        try:
            logger.info(
                "executing_test",
                device_id=device_id,
                test_type=test_type,
                target=target,
                tenant=tenant,
            )

            # Execute test via EngineClient.run_test
            result = await engine.run_test(test_type, target)

            # Record successful result
            test_mgr = TestManager(db, tenant)
            await test_mgr.create_test(
                {
                    "device_id": device_id,
                    "test_type": test_type,
                    "target": target,
                    "status": "completed",
                    "latency_ms": result.get("latency_ms"),
                    "throughput": result.get("throughput"),
                    "test_output": result.get("output"),
                    "completed_at": datetime.now(timezone.utc),
                }
            )

            logger.info(
                "test_completed",
                device_id=device_id,
                test_type=test_type,
                tenant=tenant,
                latency_ms=result.get("latency_ms"),
            )
            return True

        except EngineError as e:
            logger.warning(
                "engine_error_during_test",
                device_id=device_id,
                test_type=test_type,
                error=str(e),
            )
            # Record failed result
            test_mgr = TestManager(db, tenant)
            await test_mgr.create_test(
                {
                    "device_id": device_id,
                    "test_type": test_type,
                    "target": target,
                    "status": "failed",
                    "latency_ms": None,
                    "throughput": None,
                    "test_output": f"Engine error: {str(e)}",
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            return False

        except Exception as e:
            logger.error(
                "unexpected_error_during_test",
                device_id=device_id,
                test_type=test_type,
                error=str(e),
            )
            # Record failed result
            test_mgr = TestManager(db, tenant)
            await test_mgr.create_test(
                {
                    "device_id": device_id,
                    "test_type": test_type,
                    "target": target,
                    "status": "failed",
                    "latency_ms": None,
                    "throughput": None,
                    "test_output": f"Error: {str(e)}",
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            return False

    except Exception as e:
        logger.error(
            "execute_and_store_test_failed",
            device_id=device_id,
            tenant=tenant,
            error=str(e),
        )
        return False


async def _run_server_test_async(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
    *,
    db: Any | None = None,
    engine_factory: EngineFactory | None = None,
) -> None:
    """Execute a scheduled server test. Core logic (testable).

    Args:
        job_id: Job ID
        tenant: Tenant identifier
        module: Module name
        job_type: Job type (should be "server_test")
        payload: Job payload dict with device_id, test_type, target
        db: penguin-dal AsyncDB instance (created fresh if None)
        engine_factory: Callable to create EngineClient (default: _default_engine_factory)

    Note:
        This function records test results regardless of success/failure.
        Engine errors are logged but do not raise out of the task.
    """
    engine_factory = engine_factory or _default_engine_factory

    # Create fresh AsyncDB if not provided
    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error(
                "failed_to_create_dal",
                job_id=job_id,
                tenant=tenant,
                error=str(e),
            )
            return

    try:
        device_id = payload.get("device_id")
        test_type = payload.get("test_type")
        target = payload.get("target")

        if not device_id or not test_type or not target:
            logger.warning(
                "invalid_payload",
                job_id=job_id,
                tenant=tenant,
                payload=payload,
            )
            return

        await _execute_and_store_test(db, tenant, device_id, test_type, target, engine_factory)

    except Exception as e:
        logger.error(
            "run_server_test_failed",
            job_id=job_id,
            tenant=tenant,
            error=str(e),
        )


@celery_app.task(name="hub_api.modules.perftest_cluster.worker.tasks.run_server_test")
def run_server_test(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
) -> None:
    """Celery task to run a scheduled server test.

    Args:
        job_id: Job ID
        tenant: Tenant identifier
        module: Module name
        job_type: Job type (should be "server_test")
        payload: Job payload dict with device_id, test_type, target
    """
    asyncio.run(
        _run_server_test_async(
            job_id=job_id,
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload=payload,
        )
    )


async def _alert_sweep_async(db: Any | None = None) -> int:
    """Evaluate alert rules across all tenants. Core logic (testable).

    Args:
        db: penguin-dal AsyncDB instance (created fresh if None)

    Returns:
        Number of alert events fired
    """
    # Create fresh AsyncDB if not provided
    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error("failed_to_create_dal_alert_sweep", error=str(e))
            return 0

    try:
        from hub_api.modules.perftest_cluster.services.alert_evaluator import (
            AlertEvaluator,
        )
        from hub_api.notifications.service import NotificationService

        notifications = NotificationService(db)
        evaluator = AlertEvaluator(db, notifications)
        events_fired = await evaluator.sweep()

        logger.info("alert_sweep_complete", events_fired=events_fired)

        return events_fired

    except Exception as e:
        logger.error("alert_sweep_failed", error=str(e))
        return 0


@celery_app.task(name="hub_api.modules.perftest_cluster.worker.tasks.alert_sweep")
def alert_sweep() -> None:
    """Celery task to sweep and evaluate alert rules across all tenants."""
    asyncio.run(_alert_sweep_async())


async def _autoperf_cycle_async(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
    *,
    db: Any | None = None,
    engine_factory: EngineFactory | None = None,
) -> None:
    """Execute an AutoPerf tiered monitoring cycle. Core logic (testable).

    Loads the policy and state, executes the current tier's test set,
    checks for breaches via alert_events, and calls record_cycle to advance state.

    Args:
        job_id: Job ID
        tenant: Tenant identifier
        module: Module name (should be "perftest_cluster")
        job_type: Job type (should be "autoperf_cycle")
        payload: Job payload dict with policy_id
        db: penguin-dal AsyncDB instance (created fresh if None)
        engine_factory: Callable to create EngineClient (default: _default_engine_factory)

    Note:
        Never raises. Engine errors and failures are logged and cycle continues.
    """
    engine_factory = engine_factory or _default_engine_factory

    # Create fresh AsyncDB if not provided
    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error(
                "failed_to_create_dal_autoperf",
                job_id=job_id,
                tenant=tenant,
                error=str(e),
            )
            return

    try:
        policy_id = payload.get("policy_id")
        if not policy_id:
            logger.warning(
                "invalid_autoperf_payload",
                job_id=job_id,
                tenant=tenant,
                payload=payload,
            )
            return

        # Load policy and state
        autoperf_mgr = AutoPerfManager(db)
        policy_rowset = await db(
            (db.autoperf_policies.tenant == tenant) & (db.autoperf_policies.id == policy_id)
        ).select()
        policy = policy_rowset.first()

        if not policy:
            logger.warning(
                "autoperf_policy_not_found",
                job_id=job_id,
                policy_id=policy_id,
                tenant=tenant,
            )
            return

        state = await autoperf_mgr.get_state(tenant, policy_id)
        if not state:
            logger.warning(
                "autoperf_state_not_found",
                job_id=job_id,
                policy_id=policy_id,
                tenant=tenant,
            )
            return

        # Determine tests to run based on current tier
        current_tier = state["current_tier"]
        test_types = _test_types_for_tier(current_tier)

        logger.info(
            "autoperf_cycle_starting",
            job_id=job_id,
            policy_id=policy_id,
            tenant=tenant,
            tier=current_tier,
            test_count=len(test_types),
        )

        # Execute each test in the tier set
        for test_type in test_types:
            await _execute_and_store_test(
                db,
                tenant,
                policy["device_id"],
                test_type,
                policy["target"],
                engine_factory,
            )

        # Check for breaches since last_cycle_at
        last_cycle_at = state["last_cycle_at"]
        if last_cycle_at is None:
            # First cycle: use epoch
            last_cycle_at = datetime.fromtimestamp(0, tz=timezone.utc)

        events_rowset = await db(
            (db.alert_events.tenant == tenant)
            & (db.alert_events.device_id == policy["device_id"])
            & (db.alert_events.fired_at > last_cycle_at)
        ).select()

        breached = len(events_rowset) > 0

        logger.info(
            "autoperf_cycle_checking_breaches",
            job_id=job_id,
            policy_id=policy_id,
            tenant=tenant,
            breached=breached,
            event_count=len(events_rowset),
        )

        # Record cycle and advance state
        updated_state = await autoperf_mgr.record_cycle(tenant, policy_id, breached)

        logger.info(
            "autoperf_cycle_completed",
            job_id=job_id,
            policy_id=policy_id,
            tenant=tenant,
            new_tier=updated_state["current_tier"],
            breached=breached,
        )

    except Exception as e:
        logger.error(
            "autoperf_cycle_failed",
            job_id=job_id,
            tenant=tenant,
            error=str(e),
        )


@celery_app.task(name="hub_api.modules.perftest_cluster.worker.tasks.autoperf_cycle")
def autoperf_cycle(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
) -> None:
    """Celery task to run an AutoPerf tiered monitoring cycle.

    Args:
        job_id: Job ID
        tenant: Tenant identifier
        module: Module name
        job_type: Job type
        payload: Job payload dict with policy_id
    """
    asyncio.run(
        _autoperf_cycle_async(
            job_id=job_id,
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload=payload,
        )
    )
