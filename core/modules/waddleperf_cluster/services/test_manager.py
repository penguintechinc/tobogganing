"""Performance test result management using penguin-dal."""
from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

logger = structlog.get_logger()


@dataclass(slots=True)
class PerfTestResult:
    """Performance test result data structure."""

    id: str
    tenant: str
    device_id: str
    test_type: str
    status: str
    target: str | None
    started_at: datetime | None
    completed_at: datetime | None
    latency_ms: float | None
    throughput: float | None
    test_output: str | None
    created_at: datetime


class TestManager:
    """Manages performance test results using penguin-dal."""

    def __init__(self, db: object, tenant: str) -> None:
        """Initialize TestManager.

        Args:
            db: penguin-dal DAL instance
            tenant: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant = tenant

    async def initialize(self) -> None:
        """Initialize the TestManager."""
        try:
            logger.info("TestManager initialized", tenant=self.tenant)
        except Exception as e:
            logger.error("Failed to initialize TestManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the TestManager."""
        logger.info("TestManager shutdown complete")

    async def create_test(self, data: dict) -> PerfTestResult:
        """Create a new performance test result.

        Args:
            data: Test result data dictionary (device_id, test_type, target, status, etc.)

        Returns:
            PerfTestResult object
        """
        test_id = str(uuid4())
        now = datetime.now()

        await self.db.perf_test_results.async_insert(
            id=test_id,
            tenant=self.tenant,
            device_id=data.get("device_id"),
            test_type=data.get("test_type"),
            status=data.get("status", "pending"),
            target=data.get("target"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            latency_ms=data.get("latency_ms"),
            throughput=data.get("throughput"),
            test_output=data.get("test_output"),
            created_at=now,
        )

        logger.info(
            "created_test",
            test_id=test_id,
            device_id=data.get("device_id"),
            test_type=data.get("test_type"),
            tenant=self.tenant,
        )

        return PerfTestResult(
            id=test_id,
            tenant=self.tenant,
            device_id=data.get("device_id"),
            test_type=data.get("test_type"),
            status=data.get("status", "pending"),
            target=data.get("target"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            latency_ms=data.get("latency_ms"),
            throughput=data.get("throughput"),
            test_output=data.get("test_output"),
            created_at=now,
        )

    async def record_result(self, test_id: str, data: dict) -> PerfTestResult | None:
        """Record test result details (latency, throughput, output).

        Args:
            test_id: Test result ID
            data: Result data (status, latency_ms, throughput, test_output, completed_at)

        Returns:
            Updated PerfTestResult or None if not found
        """
        existing = await self.get_test(test_id)
        if not existing:
            return None

        update_data = {
            k: v
            for k, v in data.items()
            if k in ["status", "latency_ms", "throughput", "test_output", "completed_at"]
        }

        await self.db(
            (self.db.perf_test_results.id == test_id) & (self.db.perf_test_results.tenant == self.tenant)
        ).update(**update_data)

        logger.info(
            "recorded_result",
            test_id=test_id,
            status=update_data.get("status"),
            tenant=self.tenant,
        )

        return await self.get_test(test_id)

    async def get_test(self, test_id: str) -> PerfTestResult | None:
        """Get a test result by ID.

        Args:
            test_id: Test result ID

        Returns:
            PerfTestResult or None if not found
        """
        test_rowset = await self.db(
            (self.db.perf_test_results.id == test_id) & (self.db.perf_test_results.tenant == self.tenant)
        ).select()
        test_obj = test_rowset.first()

        if not test_obj:
            return None

        return PerfTestResult(
            id=test_obj.id,
            tenant=test_obj.tenant,
            device_id=test_obj.device_id,
            test_type=test_obj.test_type,
            status=test_obj.status,
            target=test_obj.target,
            started_at=test_obj.started_at,
            completed_at=test_obj.completed_at,
            latency_ms=test_obj.latency_ms,
            throughput=test_obj.throughput,
            test_output=test_obj.test_output,
            created_at=test_obj.created_at,
        )

    async def list_results(
        self,
        device_id: str | None = None,
        test_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PerfTestResult]:
        """List test results with optional filtering.

        Args:
            device_id: Filter by device ID
            test_type: Filter by test type
            status: Filter by status (pending, running, completed, failed)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of PerfTestResult objects
        """
        conditions = [self.db.perf_test_results.tenant == self.tenant]

        if device_id:
            conditions.append(self.db.perf_test_results.device_id == device_id)
        if test_type:
            conditions.append(self.db.perf_test_results.test_type == test_type)
        if status:
            conditions.append(self.db.perf_test_results.status == status)

        query = conditions[0]
        for cond in conditions[1:]:
            query = query & cond

        results_rowset = await self.db(query).select(limitby=(offset, offset + limit))

        return [
            PerfTestResult(
                id=r.id,
                tenant=r.tenant,
                device_id=r.device_id,
                test_type=r.test_type,
                status=r.status,
                target=r.target,
                started_at=r.started_at,
                completed_at=r.completed_at,
                latency_ms=r.latency_ms,
                throughput=r.throughput,
                test_output=r.test_output,
                created_at=r.created_at,
            )
            for r in results_rowset
        ]

    async def list_tests(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PerfTestResult]:
        """List all test results for the tenant.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of PerfTestResult objects
        """
        results_rowset = await self.db(
            self.db.perf_test_results.tenant == self.tenant,
        ).select(limitby=(offset, offset + limit))

        return [
            PerfTestResult(
                id=r.id,
                tenant=r.tenant,
                device_id=r.device_id,
                test_type=r.test_type,
                status=r.status,
                target=r.target,
                started_at=r.started_at,
                completed_at=r.completed_at,
                latency_ms=r.latency_ms,
                throughput=r.throughput,
                test_output=r.test_output,
                created_at=r.created_at,
            )
            for r in results_rowset
        ]

    async def delete_test(self, test_id: str) -> bool:
        """Delete a test result.

        Args:
            test_id: Test result ID

        Returns:
            True if successful, False if not found
        """
        existing = await self.get_test(test_id)
        if not existing:
            return False

        await self.db(
            (self.db.perf_test_results.id == test_id) & (self.db.perf_test_results.tenant == self.tenant)
        ).delete()

        logger.info(
            "deleted_test",
            test_id=test_id,
            tenant=self.tenant,
        )

        return True
