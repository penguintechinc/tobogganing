"""Cluster-to-cluster matrix run management using penguin-dal."""
from __future__ import annotations

import itertools
import json
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

logger = structlog.get_logger()


@dataclass(slots=True)
class MatrixRunRecord:
    """C2C matrix run data structure."""

    id: str
    tenant: str
    status: str
    test_types: list[str]
    total_pairs: int
    completed_pairs: int
    failed_pairs: int
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RunManager:
    """Manages cluster-to-cluster matrix test runs using penguin-dal."""

    def __init__(self, db: object, tenant: str) -> None:
        """Initialize RunManager.

        Args:
            db: penguin-dal DAL instance
            tenant: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant = tenant

    def create_run(
        self,
        test_types: list[str],
        endpoint_ids: list[str] | None = None,
        created_by: str | None = None,
    ) -> tuple[dict[str, object], list[tuple[str, str, str]]]:
        """Create a new matrix run.

        Selects the tenant's enabled endpoints (optionally filtered to endpoint_ids),
        builds the ordered directed pair list (all source->dest combinations with
        source != dest, crossed with each test_type), creates a c2c_matrix_run row,
        and returns (run_dict, pairs).

        Args:
            test_types: List of test types to run
            endpoint_ids: Optional list of endpoint IDs to limit; if None, use all enabled endpoints
            created_by: User ID of the creator

        Returns:
            Tuple of (run_dict, pairs_list) where pairs_list is list of (source_id, dest_id, test_type)

        Raises:
            ValueError: If fewer than 2 enabled endpoints selected
        """
        # Get enabled endpoints
        endpoints = self.db.c2c_endpoints.select(
            tenant=self.tenant, enabled=True
        )

        if not endpoints:
            endpoints = []
        elif not isinstance(endpoints, list):
            endpoints = [endpoints]

        # Filter to endpoint_ids if provided
        if endpoint_ids:
            endpoint_ids_set = set(endpoint_ids)
            endpoints = [e for e in endpoints if e.id in endpoint_ids_set]

        # Verify we have at least 2 endpoints
        if len(endpoints) < 2:
            raise ValueError(
                f"Cannot create run with {len(endpoints)} enabled endpoints; need at least 2"
            )

        # Build ordered directed pairs: every (source_id, dest_id) with source != dest,
        # crossed with each test_type
        endpoint_ids_list = [e.id for e in endpoints]
        pairs: list[tuple[str, str, str]] = []

        for source_id, dest_id in itertools.permutations(endpoint_ids_list, 2):
            for test_type in test_types:
                pairs.append((source_id, dest_id, test_type))

        total_pairs = len(pairs)

        # Create run
        run = self.db.c2c_matrix_runs.create(
            tenant=self.tenant,
            status="pending",
            test_types=json.dumps(test_types),
            total_pairs=total_pairs,
            completed_pairs=0,
            failed_pairs=0,
            created_by=created_by,
        )

        logger.info(
            "run_created",
            run_id=run.id,
            total_pairs=total_pairs,
            test_types=test_types,
            tenant=self.tenant,
        )

        run_dict = {
            "id": run.id,
            "tenant": run.tenant,
            "status": run.status,
            "test_types": json.loads(run.test_types) if isinstance(run.test_types, str) else run.test_types,
            "total_pairs": run.total_pairs,
            "completed_pairs": run.completed_pairs,
            "failed_pairs": run.failed_pairs,
            "created_by": run.created_by,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

        return (run_dict, pairs)

    def get_run(self, run_id: str) -> dict[str, object] | None:
        """Get a run by ID.

        Args:
            run_id: Run ID

        Returns:
            Run dict or None if not found or belongs to different tenant
        """
        run = self.db.c2c_matrix_runs.select(id=run_id, tenant=self.tenant)

        if not run:
            return None

        return {
            "id": run.id,
            "tenant": run.tenant,
            "status": run.status,
            "test_types": json.loads(run.test_types) if isinstance(run.test_types, str) else run.test_types,
            "total_pairs": run.total_pairs,
            "completed_pairs": run.completed_pairs,
            "failed_pairs": run.failed_pairs,
            "created_by": run.created_by,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    def list_runs(self) -> list[dict[str, object]]:
        """List all runs for this tenant, newest first.

        Returns:
            List of run dicts
        """
        runs = self.db.c2c_matrix_runs.select(tenant=self.tenant)

        if not runs:
            return []

        run_list = runs if isinstance(runs, list) else [runs]

        return [
            {
                "id": r.id,
                "tenant": r.tenant,
                "status": r.status,
                "test_types": json.loads(r.test_types) if isinstance(r.test_types, str) else r.test_types,
                "total_pairs": r.total_pairs,
                "completed_pairs": r.completed_pairs,
                "failed_pairs": r.failed_pairs,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in run_list
        ]

    def mark_running(self, run_id: str) -> None:
        """Mark a run as running.

        Args:
            run_id: Run ID
        """
        self.db.c2c_matrix_runs.update(
            id=run_id,
            tenant=self.tenant,
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        logger.info(
            "run_marked_running",
            run_id=run_id,
            tenant=self.tenant,
        )

    def mark_complete(self, run_id: str) -> None:
        """Mark a run as completed.

        Args:
            run_id: Run ID
        """
        self.db.c2c_matrix_runs.update(
            id=run_id,
            tenant=self.tenant,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )

        logger.info(
            "run_marked_complete",
            run_id=run_id,
            tenant=self.tenant,
        )

    def mark_failed(self, run_id: str) -> None:
        """Mark a run as failed.

        Args:
            run_id: Run ID
        """
        self.db.c2c_matrix_runs.update(
            id=run_id,
            tenant=self.tenant,
            status="failed",
            completed_at=datetime.now(timezone.utc),
        )

        logger.info(
            "run_marked_failed",
            run_id=run_id,
            tenant=self.tenant,
        )

    def record_pair_result(
        self,
        run_id: str,
        source_id: str,
        dest_id: str,
        source_region: str,
        dest_region: str,
        test_type: str,
        status: str,
        latency_ms: float | None = None,
        throughput: float | None = None,
        loss_pct: float | None = None,
        test_output: str | None = None,
    ) -> dict[str, object]:
        """Record a pair test result. IDEMPOTENT.

        If a c2c_pair_results row already exists for (tenant, run_id, source_id,
        dest_id, test_type), return it WITHOUT incrementing counters.
        Otherwise insert the row, increment completed_pairs (and failed_pairs if
        status == "failed"), and flip run to "completed" when all pairs done.

        Args:
            run_id: Run ID
            source_id: Source endpoint ID
            dest_id: Destination endpoint ID
            source_region: Source region
            dest_region: Destination region
            test_type: Test type
            status: Result status (success, failed, etc.)
            latency_ms: Latency in milliseconds
            throughput: Throughput metric
            loss_pct: Packet loss percentage
            test_output: Test output/logs

        Returns:
            Pair result dict
        """
        # Check for existing result (idempotency)
        existing = self.db.c2c_pair_results.select(
            tenant=self.tenant,
            run_id=run_id,
            source_endpoint_id=source_id,
            dest_endpoint_id=dest_id,
            test_type=test_type,
        )

        if existing:
            return {
                "id": existing.id,
                "tenant": existing.tenant,
                "run_id": existing.run_id,
                "source_endpoint_id": existing.source_endpoint_id,
                "dest_endpoint_id": existing.dest_endpoint_id,
                "source_region": existing.source_region,
                "dest_region": existing.dest_region,
                "test_type": existing.test_type,
                "status": existing.status,
                "latency_ms": existing.latency_ms,
                "throughput": existing.throughput,
                "loss_pct": existing.loss_pct,
                "test_output": existing.test_output,
                "measured_at": existing.measured_at.isoformat() if existing.measured_at else None,
            }

        # Create new result
        pair_result = self.db.c2c_pair_results.create(
            tenant=self.tenant,
            run_id=run_id,
            source_endpoint_id=source_id,
            dest_endpoint_id=dest_id,
            source_region=source_region,
            dest_region=dest_region,
            test_type=test_type,
            status=status,
            latency_ms=latency_ms,
            throughput=throughput,
            loss_pct=loss_pct,
            test_output=test_output,
            measured_at=datetime.now(timezone.utc),
        )

        # Increment completed_pairs and failed_pairs
        run = self.db.c2c_matrix_runs.select(id=run_id, tenant=self.tenant)
        new_completed = run.completed_pairs + 1
        new_failed = run.failed_pairs + (1 if status == "failed" else 0)

        self.db.c2c_matrix_runs.update(
            id=run_id,
            tenant=self.tenant,
            completed_pairs=new_completed,
            failed_pairs=new_failed,
        )

        # If all pairs completed, mark run as completed
        if new_completed >= run.total_pairs:
            self.mark_complete(run_id)

        logger.info(
            "pair_result_recorded",
            run_id=run_id,
            source_id=source_id,
            dest_id=dest_id,
            test_type=test_type,
            status=status,
            tenant=self.tenant,
        )

        return {
            "id": pair_result.id,
            "tenant": pair_result.tenant,
            "run_id": pair_result.run_id,
            "source_endpoint_id": pair_result.source_endpoint_id,
            "dest_endpoint_id": pair_result.dest_endpoint_id,
            "source_region": pair_result.source_region,
            "dest_region": pair_result.dest_region,
            "test_type": pair_result.test_type,
            "status": pair_result.status,
            "latency_ms": pair_result.latency_ms,
            "throughput": pair_result.throughput,
            "loss_pct": pair_result.loss_pct,
            "test_output": pair_result.test_output,
            "measured_at": pair_result.measured_at.isoformat() if pair_result.measured_at else None,
        }

    def enqueue_run(
        self,
        run_id: str,
        pairs: list[tuple[str, str, str]],
        dispatch: Callable[[str, str, str, str, str], object] | None = None,
    ) -> int:
        """Enqueue a run's pairs for execution.

        For each pair, calls dispatch(run_id=run_id, tenant=self.tenant,
        source_id=..., dest_id=..., test_type=...).

        Args:
            run_id: Run ID
            pairs: List of (source_id, dest_id, test_type) tuples
            dispatch: Callable to dispatch tasks; defaults to Celery run_pair.delay

        Returns:
            Count of pairs dispatched
        """
        if dispatch is None:
            # Lazy import to avoid requiring Celery at module load
            try:
                from core.modules.waddleperf_c2c.worker.tasks import run_pair
                dispatch = lambda **kwargs: run_pair.delay(**kwargs)
            except ImportError:
                logger.error("Failed to import run_pair task; Celery may not be configured")
                raise

        count = 0
        for source_id, dest_id, test_type in pairs:
            dispatch(
                run_id=run_id,
                tenant=self.tenant,
                source_id=source_id,
                dest_id=dest_id,
                test_type=test_type,
            )
            count += 1

        logger.info(
            "run_enqueued",
            run_id=run_id,
            pairs_count=count,
            tenant=self.tenant,
        )

        return count
