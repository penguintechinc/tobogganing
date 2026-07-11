"""Celery tasks for WaddlePerf cluster-to-cluster test execution.

Tasks execute source->destination endpoint tests via the engine client,
recording results in the database.
"""
from __future__ import annotations

import asyncio
import structlog
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


__all__ = ["run_pair", "_execute_pair"]
