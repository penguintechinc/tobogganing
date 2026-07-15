"""Celery tasks for WaddlePerf cluster scheduled server tests and AutoPerf.

Tasks execute scheduled server tests, record results, and run tiered AutoPerf cycles.
"""
from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any, Callable

from core.config import Config, build_db_uri
from core.modules.waddleperf_cluster.services.device_manager import DeviceManager
from core.modules.waddleperf_cluster.services.engine_client import EngineClient, EngineError
from core.modules.waddleperf_cluster.services.test_manager import TestManager
from core.modules.waddleperf_cluster.services.autoperf_manager import AutoPerfManager
from core.scheduler.celery_app import celery_app
from penguin_dal import AsyncDB

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

        await _execute_and_store_test(
            db, tenant, device_id, test_type, target, engine_factory
        )

    except Exception as e:
        logger.error(
            "run_server_test_failed",
            job_id=job_id,
            tenant=tenant,
            error=str(e),
        )


@celery_app.task(name="core.modules.waddleperf_cluster.worker.tasks.run_server_test")
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
        from core.modules.waddleperf_cluster.services.alert_evaluator import (
            AlertEvaluator,
        )
        from core.notifications.service import NotificationService

        notifications = NotificationService(db)
        evaluator = AlertEvaluator(db, notifications)
        events_fired = await evaluator.sweep()

        logger.info("alert_sweep_complete", events_fired=events_fired)

        return events_fired

    except Exception as e:
        logger.error("alert_sweep_failed", error=str(e))
        return 0


@celery_app.task(name="core.modules.waddleperf_cluster.worker.tasks.alert_sweep")
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
        module: Module name (should be "waddleperf_cluster")
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
            (db.autoperf_policies.tenant == tenant)
            & (db.autoperf_policies.id == policy_id)
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
        test_types: list[str] = []

        if current_tier >= 1:
            test_types.extend(["icmp", "http"])
        if current_tier >= 2:
            test_types.extend(["tcp", "udp", "http_trace"])
        if current_tier >= 3:
            test_types.extend(["speedtest", "traceroute"])

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


@celery_app.task(name="core.modules.waddleperf_cluster.worker.tasks.autoperf_cycle")
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
