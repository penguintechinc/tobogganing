"""Celery tasks for WaddlePerf cluster scheduled server tests.

Tasks execute scheduled server tests, recording results in the database.
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

        # Load device
        device_mgr = DeviceManager(db, tenant)
        device_row = await device_mgr.get_device(device_id)

        if not device_row:
            logger.warning(
                "device_not_found",
                job_id=job_id,
                device_id=device_id,
                tenant=tenant,
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
            return

        # Execute test via engine
        engine = engine_factory(device_row)
        try:
            logger.info(
                "executing_scheduled_test",
                job_id=job_id,
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
                "scheduled_test_completed",
                job_id=job_id,
                device_id=device_id,
                test_type=test_type,
                tenant=tenant,
                latency_ms=result.get("latency_ms"),
            )

        except EngineError as e:
            logger.warning(
                "engine_error_during_test",
                job_id=job_id,
                device_id=device_id,
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

        except Exception as e:
            logger.error(
                "unexpected_error_during_test",
                job_id=job_id,
                device_id=device_id,
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
