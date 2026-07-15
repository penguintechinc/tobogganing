"""Celery tasks for WaddlePerf cluster-to-cluster test execution.

Tasks execute source->destination endpoint tests via the engine client,
recording results in the database.
"""
from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any, Callable

from core.config import Config, build_db_uri
from core.modules.waddleperf_c2c.services.endpoint_manager import EndpointManager
from core.modules.waddleperf_c2c.services.run_manager import RunManager
from core.modules.waddleperf_cluster.services.engine_client import EngineClient, EngineError
from penguin_dal import AsyncDB

logger = structlog.get_logger()

# Type for the engine factory (can be injected in tests)
EngineFactory = Callable[[dict[str, Any]], EngineClient]


def _default_engine_factory(source: dict[str, Any]) -> EngineClient:
    """Create an EngineClient for a source endpoint.

    Args:
        source: Source endpoint dict (with engine_url, api_key_hash, etc.)

    Returns:
        EngineClient instance

    Note:
        The endpoint only stores api_key_hash (the raw key is hashed and cannot
        be recovered). We call the engine without an api_key, relying on
        engine-to-engine trust within the cluster. If per-endpoint auth is needed,
        it should be implemented via SPIFFE or another secure channel outside this task.
    """
    return EngineClient(
        base_url=source.get("engine_url"),
        api_key=None,  # No recoverable raw key; cluster-internal trust
        timeout=30.0,
    )


async def _execute_pair(
    run_id: str,
    tenant: str,
    source_id: str,
    dest_id: str,
    test_type: str,
    *,
    db: Any | None = None,
    engine_factory: EngineFactory | None = None,
) -> dict[str, Any]:
    """Execute a single pair test and record the result. Core logic (testable).

    Args:
        run_id: Matrix run ID
        tenant: Tenant identifier
        source_id: Source endpoint ID
        dest_id: Destination endpoint ID
        test_type: Test type (e.g., "http", "tcp", "icmp")
        db: penguin-dal AsyncDB instance (created fresh if None)
        engine_factory: Callable to create EngineClient (default: _default_engine_factory)

    Returns:
        Pair result dict with keys: id, run_id, source_id, dest_id, status, etc.
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
                run_id=run_id,
                tenant=tenant,
                error=str(e),
            )
            raise

    try:
        # Load source and destination endpoints
        endpoint_mgr = EndpointManager(db, tenant)
        source = await endpoint_mgr.get_endpoint(source_id)
        dest = await endpoint_mgr.get_endpoint(dest_id)

        # If either endpoint is missing, record failed result
        if not source:
            logger.warning(
                "source_endpoint_not_found",
                run_id=run_id,
                source_id=source_id,
                tenant=tenant,
            )
            run_mgr = RunManager(db, tenant)
            result = await run_mgr.record_pair_result(
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                source_region="unknown",
                dest_region="unknown",
                test_type=test_type,
                status="failed",
                latency_ms=None,
                throughput=None,
                loss_pct=None,
                test_output="Source endpoint not found",
            )
            return result

        if not dest:
            logger.warning(
                "dest_endpoint_not_found",
                run_id=run_id,
                dest_id=dest_id,
                tenant=tenant,
            )
            run_mgr = RunManager(db, tenant)
            source_region = str(source.get("region", "unknown"))
            result = await run_mgr.record_pair_result(
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                source_region=source_region,
                dest_region="unknown",
                test_type=test_type,
                status="failed",
                latency_ms=None,
                throughput=None,
                loss_pct=None,
                test_output="Destination endpoint not found",
            )
            return result

        # Create engine client for source endpoint
        try:
            engine = engine_factory(source)
        except Exception as e:
            logger.error(
                "failed_to_create_engine_client",
                run_id=run_id,
                source_id=source_id,
                error=str(e),
            )
            run_mgr = RunManager(db, tenant)
            source_region = str(source.get("region", "unknown"))
            dest_region = str(dest.get("region", "unknown"))
            result = await run_mgr.record_pair_result(
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                source_region=source_region,
                dest_region=dest_region,
                test_type=test_type,
                status="failed",
                latency_ms=None,
                throughput=None,
                loss_pct=None,
                test_output=f"Failed to create engine client: {str(e)}",
            )
            return result

        # Run the test against the destination target
        try:
            dest_target = str(dest.get("target"))
            result_data = await engine.run_test(test_type, target=dest_target)

            # Extract metrics from engine result
            latency_ms = result_data.get("latency_ms")
            throughput = result_data.get("throughput")
            loss_pct = result_data.get("loss_pct")
            test_output = result_data.get("output") or ""

            # Record successful result
            run_mgr = RunManager(db, tenant)
            source_region = str(source.get("region", "unknown"))
            dest_region = str(dest.get("region", "unknown"))
            result = await run_mgr.record_pair_result(
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                source_region=source_region,
                dest_region=dest_region,
                test_type=test_type,
                status="success",
                latency_ms=latency_ms,
                throughput=throughput,
                loss_pct=loss_pct,
                test_output=test_output,
            )

            logger.info(
                "pair_test_completed",
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                test_type=test_type,
                status="success",
                tenant=tenant,
            )

            return result

        except EngineError as e:
            logger.warning(
                "engine_test_failed",
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                error=str(e),
                tenant=tenant,
            )
            run_mgr = RunManager(db, tenant)
            source_region = str(source.get("region", "unknown"))
            dest_region = str(dest.get("region", "unknown"))
            result = await run_mgr.record_pair_result(
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                source_region=source_region,
                dest_region=dest_region,
                test_type=test_type,
                status="failed",
                latency_ms=None,
                throughput=None,
                loss_pct=None,
                test_output=f"Engine error: {str(e)}",
            )
            return result

        except Exception as e:
            logger.error(
                "unexpected_error_during_test",
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                error=str(e),
                exc_info=True,
                tenant=tenant,
            )
            run_mgr = RunManager(db, tenant)
            source_region = str(source.get("region", "unknown"))
            dest_region = str(dest.get("region", "unknown"))
            result = await run_mgr.record_pair_result(
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                source_region=source_region,
                dest_region=dest_region,
                test_type=test_type,
                status="failed",
                latency_ms=None,
                throughput=None,
                loss_pct=None,
                test_output=f"Unexpected error: {str(e)}",
            )
            return result

    except Exception as e:
        logger.error(
            "unhandled_pair_execution_error",
            run_id=run_id,
            tenant=tenant,
            source_id=source_id,
            dest_id=dest_id,
            error=str(e),
            exc_info=True,
        )
        # Record FAILED pair result for finding #3 (worker fail-stuck)
        try:
            run_mgr = RunManager(db, tenant)
            await run_mgr.record_pair_result(
                run_id=run_id,
                source_id=source_id,
                dest_id=dest_id,
                source_region="unknown",
                dest_region="unknown",
                test_type=test_type,
                status="failed",
                latency_ms=None,
                throughput=None,
                loss_pct=None,
                test_output=f"Unhandled error: {str(e)}",
            )
        except Exception as record_err:
            logger.error(
                "failed_to_record_pair_result",
                run_id=run_id,
                error=str(record_err),
            )
        raise


# Import Celery app and define task
try:
    from core.modules.waddleperf_c2c.worker.celery_app import celery_app

    @celery_app.task(  # type: ignore[untyped-decorator]
        bind=True,
        name="waddleperf_c2c.run_pair",
        max_retries=0,
    )
    def run_pair(
        self: Any,
        run_id: str,
        tenant: str,
        source_id: str,
        dest_id: str,
        test_type: str,
    ) -> dict[str, Any]:
        """Celery task to execute a single pair test.

        Builds a fresh AsyncDB per task and runs the async _execute_pair logic
        via asyncio.run() inside the sync Celery task context.

        Args:
            self: Task self (bound task)
            run_id: Matrix run ID
            tenant: Tenant identifier
            source_id: Source endpoint ID
            dest_id: Destination endpoint ID
            test_type: Test type

        Returns:
            Pair result dict
        """
        return asyncio.run(
            _execute_pair(
                run_id=run_id,
                tenant=tenant,
                source_id=source_id,
                dest_id=dest_id,
                test_type=test_type,
            )
        )

except ImportError:
    # If Celery import fails, create a dummy task
    logger.warning("Failed to import celery_app; run_pair task unavailable")

    def run_pair(
        run_id: str,
        tenant: str,
        source_id: str,
        dest_id: str,
        test_type: str,
    ) -> dict[str, Any]:
        """Dummy run_pair when Celery unavailable."""
        raise RuntimeError("Celery not available; cannot enqueue run_pair task")


async def _start_recurring_run(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
    *,
    db: Any | None = None,
    dispatch: Any | None = None,
) -> dict[str, Any] | None:
    """Start a recurring matrix run triggered by the scheduler.

    Creates a new matrix run via RunManager.create_run and enqueues it.
    Reuses the existing pair fanout logic (RunManager.enqueue_run).

    Args:
        job_id: Scheduled job ID (for logging).
        tenant: Tenant identifier.
        module: Module name (waddleperf_c2c).
        job_type: Job type (matrix_run).
        payload: Job payload dict with endpoint_ids and interval_seconds.
        db: penguin-dal AsyncDB instance (created fresh if None).
        dispatch: Callable to dispatch pair tasks (default: celery run_pair.delay).

    Returns:
        Dict with run_id and status, or None if creation failed.
    """
    # Create fresh AsyncDB if not provided
    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error(
                "failed_to_create_dal_recurring",
                job_id=job_id[:8],
                tenant=tenant,
                error=str(e),
            )
            return None

    try:
        # Extract payload fields
        endpoint_ids = payload.get("endpoint_ids")

        # Create run
        run_mgr = RunManager(db, tenant)
        try:
            run, pairs = await run_mgr.create_run(
                test_types=["latency", "throughput"],  # Default test types for recurring
                endpoint_ids=endpoint_ids,
                created_by=None,  # Scheduled job, no user
            )
        except ValueError as e:
            logger.warning(
                "recurring_run_creation_failed",
                job_id=job_id[:8],
                tenant=tenant,
                error=str(e),
            )
            return None

        run_id: str = run["id"]  # type: ignore[assignment]

        # Mark as running
        await run_mgr.mark_running(run_id)

        # Enqueue pairs
        try:
            pairs_count = await run_mgr.enqueue_run(run_id, pairs, dispatch=dispatch)
        except Exception as e:
            logger.error(
                "recurring_run_enqueue_failed",
                job_id=job_id[:8],
                run_id=run_id[:8],
                error=str(e),
                exc_info=True,
            )
            return None

        logger.info(
            "recurring_run_created",
            job_id=job_id[:8],
            run_id=run_id[:8],
            pairs_count=pairs_count,
            tenant=tenant,
        )

        return {
            "run_id": run_id,
            "status": "running",
            "pairs_count": pairs_count,
        }

    except Exception as e:
        logger.error(
            "start_recurring_run_failed",
            job_id=job_id[:8],
            tenant=tenant,
            error=str(e),
            exc_info=True,
        )
        return None


# Import Celery app and define task
try:
    from core.modules.waddleperf_c2c.worker.celery_app import celery_app

    @celery_app.task(  # type: ignore[untyped-decorator]
        bind=True,
        name="waddleperf_c2c.start_recurring_run",
        max_retries=0,
    )
    def start_recurring_run(
        self: Any,
        job_id: str,
        tenant: str,
        module: str,
        job_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Celery task to start a recurring matrix run.

        Triggered by the core scheduler sweep for recurring_runs jobs.
        Builds a fresh AsyncDB per task and runs the async _start_recurring_run
        logic via asyncio.run() inside the sync Celery task context.

        Args:
            self: Task self (bound task).
            job_id: Scheduled job ID.
            tenant: Tenant identifier.
            module: Module name.
            job_type: Job type.
            payload: Job-specific payload.

        Returns:
            Dict with run_id and status, or None if failed.
        """
        return asyncio.run(
            _start_recurring_run(
                job_id=job_id,
                tenant=tenant,
                module=module,
                job_type=job_type,
                payload=payload,
            )
        )

except ImportError:
    logger.warning(
        "Failed to import celery_app; start_recurring_run task unavailable"
    )

    def start_recurring_run(
        job_id: str,
        tenant: str,
        module: str,
        job_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Dummy start_recurring_run when Celery unavailable."""
        raise RuntimeError(
            "Celery not available; cannot enqueue start_recurring_run task"
        )


async def _node_health(
    job_id: str,
    tenant: str,
    module: str,
    job_type: str,
    payload: dict[str, Any],
    *,
    db: Any | None = None,
    engine_factory: EngineFactory | None = None,
) -> None:
    """Sweep tenant's endpoints and update their health status.

    Checks each of the tenant's enabled endpoints via GET {engine_url}/health
    with 5s timeout. Updates health_status and last_health_check in the database.
    Per-endpoint try/except ensures one failing endpoint doesn't stop the sweep.
    Only scans the owning tenant's endpoints (fail-closed).

    Args:
        job_id: Scheduled job ID (for logging).
        tenant: Tenant identifier.
        module: Module name (waddleperf_c2c).
        job_type: Job type (node_health).
        payload: Job payload (unused for health sweep).
        db: penguin-dal AsyncDB instance (created fresh if None).
        engine_factory: Callable to create EngineClient (default: custom health factory).

    Returns:
        None. Never raises; all errors caught and logged.
    """
    # Create fresh AsyncDB if not provided
    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error(
                "failed_to_create_dal_node_health",
                job_id=job_id[:8],
                tenant=tenant,
                error=str(e),
            )
            return

    # Default engine factory: 5s timeout for health checks
    if engine_factory is None:
        def engine_factory(endpoint: dict[str, Any]) -> EngineClient:
            return EngineClient(
                base_url=endpoint.get("engine_url"),
                api_key=None,
                timeout=5.0,
            )

    try:
        # Get all enabled endpoints for this tenant
        endpoint_mgr = EndpointManager(db, tenant)
        endpoints = await endpoint_mgr.list_endpoints(enabled_only=True)

        for endpoint in endpoints:
            endpoint_id = endpoint.get("id")
            engine_url = endpoint.get("engine_url")

            try:
                # Create engine client and check health
                engine = engine_factory(endpoint)
                is_healthy = await engine.health()
                health_status = "healthy" if is_healthy else "unhealthy"

                # Update endpoint health status and timestamp
                await db(
                    (db.c2c_endpoints.id == endpoint_id)
                    & (db.c2c_endpoints.tenant == tenant)
                ).update(
                    health_status=health_status,
                    last_health_check=datetime.now(timezone.utc),
                )

                logger.info(
                    "endpoint_health_checked",
                    endpoint_id=endpoint_id[:8],
                    engine_url=engine_url,
                    health_status=health_status,
                    tenant=tenant,
                )

            except EngineError as e:
                # Engine error (timeout, connection refused, etc.) → unhealthy
                logger.warning(
                    "endpoint_health_error",
                    endpoint_id=endpoint_id[:8],
                    engine_url=engine_url,
                    error=str(e),
                    tenant=tenant,
                )
                try:
                    await db(
                        (db.c2c_endpoints.id == endpoint_id)
                        & (db.c2c_endpoints.tenant == tenant)
                    ).update(
                        health_status="unhealthy",
                        last_health_check=datetime.now(timezone.utc),
                    )
                except Exception as update_err:
                    logger.error(
                        "failed_to_update_endpoint_health",
                        endpoint_id=endpoint_id[:8],
                        error=str(update_err),
                        tenant=tenant,
                    )

            except Exception as e:
                # Unexpected error → log and mark unhealthy, continue
                logger.error(
                    "unexpected_error_health_check",
                    endpoint_id=endpoint_id[:8],
                    error=str(e),
                    exc_info=True,
                    tenant=tenant,
                )
                try:
                    await db(
                        (db.c2c_endpoints.id == endpoint_id)
                        & (db.c2c_endpoints.tenant == tenant)
                    ).update(
                        health_status="unhealthy",
                        last_health_check=datetime.now(timezone.utc),
                    )
                except Exception as update_err:
                    logger.error(
                        "failed_to_update_endpoint_health",
                        endpoint_id=endpoint_id[:8],
                        error=str(update_err),
                        tenant=tenant,
                    )

        logger.info(
            "node_health_sweep_completed",
            job_id=job_id[:8],
            tenant=tenant,
            endpoint_count=len(endpoints),
        )

    except Exception as e:
        logger.error(
            "node_health_sweep_failed",
            job_id=job_id[:8],
            tenant=tenant,
            error=str(e),
            exc_info=True,
        )


# Import Celery app and define task
try:
    from core.modules.waddleperf_c2c.worker.celery_app import celery_app

    @celery_app.task(  # type: ignore[untyped-decorator]
        bind=True,
        name="waddleperf_c2c.node_health",
        max_retries=0,
    )
    def node_health(
        self: Any,
        job_id: str,
        tenant: str,
        module: str,
        job_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Celery task to perform a node health sweep.

        Triggered by the core scheduler sweep for node_health jobs.
        Builds a fresh AsyncDB per task and runs the async _node_health
        logic via asyncio.run() inside the sync Celery task context.

        Args:
            self: Task self (bound task).
            job_id: Scheduled job ID.
            tenant: Tenant identifier.
            module: Module name.
            job_type: Job type.
            payload: Job-specific payload (unused).

        Returns:
            None.
        """
        return asyncio.run(
            _node_health(
                job_id=job_id,
                tenant=tenant,
                module=module,
                job_type=job_type,
                payload=payload,
            )
        )

except ImportError:
    logger.warning("Failed to import celery_app; node_health task unavailable")

    def node_health(
        job_id: str,
        tenant: str,
        module: str,
        job_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Dummy node_health when Celery unavailable."""
        raise RuntimeError("Celery not available; cannot enqueue node_health task")


__all__ = [
    "run_pair",
    "_execute_pair",
    "start_recurring_run",
    "_start_recurring_run",
    "node_health",
    "_node_health",
]
