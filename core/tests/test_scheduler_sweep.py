"""Tests for scheduler sweep task.

Real integration tests using a migrated sqlite database and real AsyncDB.
Tests handler registry, dispatch resilience, idempotency, and tenant isolation.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio

from core.scheduler.job_manager import JobManager
from core.scheduler.registry import clear_handlers, register_job_handler
from core.scheduler.tasks import _sweep_async
from penguin_dal import AsyncDB


@pytest.fixture
def cleanup_handlers() -> Any:
    """Fixture to clear handlers before and after each test.

    Isolates handler state between test cases.
    """
    clear_handlers()
    yield
    clear_handlers()


@pytest_asyncio.fixture
async def test_db(real_dal: AsyncDB) -> Any:
    """Provide the real_dal fixture as an async fixture."""
    return real_dal


class TestSweepDispatch:
    """Tests for job dispatch via sweep."""

    @pytest.mark.asyncio
    async def test_due_job_dispatched_once_with_parsed_payload(
        self,
        test_db: AsyncDB,
        cleanup_handlers: Any,
    ) -> None:
        """Due job is dispatched exactly once with parsed payload and advanced.

        Job is marked due, handler registered, dispatched, and next_run_at
        advanced by interval_seconds.
        """
        # Setup
        tenant = "tenant-a"
        module = "test_module"
        job_type = "test_job"
        payload_dict = {"key": "value", "count": 42}
        interval = 60

        job_mgr = JobManager(test_db)
        now = datetime.now(timezone.utc)

        # Create a job with next_run_at in the past (due)
        job = await job_mgr.create_job(
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload=payload_dict,
            interval_seconds=interval,
            enabled=True,
        )
        job_id = job["id"]

        # Manually set next_run_at to the past to make it due
        await test_db(test_db.scheduled_jobs.id == job_id).update(
            next_run_at=now - timedelta(seconds=10),
        )

        # Register handler
        task_name = "test.tasks.run_job"
        register_job_handler(module, job_type, task_name)

        # Capture dispatch calls
        dispatched: list[tuple[str, dict[str, Any]]] = []

        def fake_dispatch(task: str, kwargs: dict[str, Any]) -> None:
            """Capture dispatch calls."""
            dispatched.append((task, kwargs))

        # Run sweep
        count = await _sweep_async(db=test_db, dispatch=fake_dispatch, now=now)

        # Verify dispatch was called once with correct task name and payload
        assert count == 1
        assert len(dispatched) == 1
        task, kwargs = dispatched[0]
        assert task == task_name
        assert kwargs["job_id"] == job_id
        assert kwargs["tenant"] == tenant
        assert kwargs["module"] == module
        assert kwargs["job_type"] == job_type
        assert kwargs["payload"] == payload_dict

        # Verify job was advanced
        updated_job = await job_mgr.get_job(tenant, job_id)
        assert updated_job is not None
        expected_next_run = now + timedelta(seconds=interval)
        # SQLite returns naive datetime; compare by removing timezone
        assert updated_job["next_run_at"].replace(tzinfo=None) == expected_next_run.replace(
            tzinfo=None
        )
        assert updated_job["last_run_at"].replace(tzinfo=None) == now.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_not_due_and_disabled_skipped(
        self,
        test_db: AsyncDB,
        cleanup_handlers: Any,
    ) -> None:
        """Not-due and disabled jobs are skipped by sweep."""
        tenant = "tenant-a"
        module = "test_module"
        job_type = "test_job"

        job_mgr = JobManager(test_db)
        now = datetime.now(timezone.utc)

        # Create a not-due job (next_run_at in the future)
        future_job = await job_mgr.create_job(
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload={"test": "future"},
            interval_seconds=60,
            enabled=True,
        )
        # future_job was created with next_run_at = now + interval, so it's not due

        # Create a disabled job (due but disabled)
        disabled_job = await job_mgr.create_job(
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload={"test": "disabled"},
            interval_seconds=60,
            enabled=False,
        )
        # Manually set next_run_at to past to make it due
        await test_db(test_db.scheduled_jobs.id == disabled_job["id"]).update(
            next_run_at=now - timedelta(seconds=10),
        )

        # Register handler
        register_job_handler(module, job_type, "test.tasks.run_job")

        # Capture dispatch calls
        dispatched: list[tuple[str, dict[str, Any]]] = []

        def fake_dispatch(task: str, kwargs: dict[str, Any]) -> None:
            """Capture dispatch calls."""
            dispatched.append((task, kwargs))

        # Run sweep
        count = await _sweep_async(db=test_db, dispatch=fake_dispatch, now=now)

        # Neither job should be dispatched
        assert count == 0
        assert len(dispatched) == 0

    @pytest.mark.asyncio
    async def test_unknown_handler_advanced_and_warned(
        self,
        test_db: AsyncDB,
        cleanup_handlers: Any,
    ) -> None:
        """Unknown handler: job is advanced, warning logged, not counted as dispatched."""
        tenant = "tenant-a"
        module = "test_module"
        job_type = "unknown_job_type"

        job_mgr = JobManager(test_db)
        now = datetime.now(timezone.utc)

        # Create a due job
        job = await job_mgr.create_job(
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload={"test": "unknown"},
            interval_seconds=60,
            enabled=True,
        )
        job_id = job["id"]

        # Manually set next_run_at to past to make it due
        await test_db(test_db.scheduled_jobs.id == job_id).update(
            next_run_at=now - timedelta(seconds=10),
        )

        # Do NOT register a handler for this (module, job_type)

        # Capture dispatch calls
        dispatched: list[tuple[str, dict[str, Any]]] = []

        def fake_dispatch(task: str, kwargs: dict[str, Any]) -> None:
            """Capture dispatch calls."""
            dispatched.append((task, kwargs))

        # Run sweep
        count = await _sweep_async(db=test_db, dispatch=fake_dispatch, now=now)

        # Job should NOT be counted as dispatched
        assert count == 0
        assert len(dispatched) == 0

        # Job should still be advanced (warning is logged via structlog)
        updated_job = await job_mgr.get_job(tenant, job_id)
        assert updated_job is not None
        expected_next_run = now + timedelta(seconds=60)
        assert updated_job["next_run_at"].replace(tzinfo=None) == expected_next_run.replace(
            tzinfo=None
        )

    @pytest.mark.asyncio
    async def test_dispatch_failure_does_not_prevent_next_job(
        self,
        test_db: AsyncDB,
        cleanup_handlers: Any,
    ) -> None:
        """Dispatch raising on job 1 does not prevent job 2 from being processed."""
        tenant = "tenant-a"

        job_mgr = JobManager(test_db)
        now = datetime.now(timezone.utc)

        # Create job 1 (will fail on dispatch)
        job1 = await job_mgr.create_job(
            tenant=tenant,
            module="module_a",
            job_type="job_type_a",
            payload={"job": 1},
            interval_seconds=60,
            enabled=True,
        )
        await test_db(test_db.scheduled_jobs.id == job1["id"]).update(
            next_run_at=now - timedelta(seconds=10),
        )

        # Create job 2 (will succeed)
        job2 = await job_mgr.create_job(
            tenant=tenant,
            module="module_b",
            job_type="job_type_b",
            payload={"job": 2},
            interval_seconds=60,
            enabled=True,
        )
        await test_db(test_db.scheduled_jobs.id == job2["id"]).update(
            next_run_at=now - timedelta(seconds=10),
        )

        # Register handlers
        register_job_handler("module_a", "job_type_a", "test.tasks.fail_job")
        register_job_handler("module_b", "job_type_b", "test.tasks.run_job")

        # Capture dispatch calls and simulate failure for job 1
        dispatched: list[tuple[str, dict[str, Any]]] = []

        def fake_dispatch(task: str, kwargs: dict[str, Any]) -> None:
            """Capture dispatch calls and fail for job 1."""
            dispatched.append((task, kwargs))
            if task == "test.tasks.fail_job":
                raise RuntimeError("Intentional dispatch failure")

        # Run sweep
        count = await _sweep_async(db=test_db, dispatch=fake_dispatch, now=now)

        # Both jobs should be attempted and marked as run
        # Only job 2 is counted as dispatched (job 1's dispatch failed)
        assert count == 1
        assert len(dispatched) == 2

        # Both jobs should be advanced
        updated_job1 = await job_mgr.get_job(tenant, job1["id"])
        updated_job2 = await job_mgr.get_job(tenant, job2["id"])
        assert updated_job1 is not None
        assert updated_job2 is not None
        expected_next = now + timedelta(seconds=60)
        assert updated_job1["next_run_at"].replace(tzinfo=None) == expected_next.replace(
            tzinfo=None
        )
        assert updated_job2["next_run_at"].replace(tzinfo=None) == expected_next.replace(
            tzinfo=None
        )

    @pytest.mark.asyncio
    async def test_idempotency_second_sweep_at_same_now_dispatches_nothing(
        self,
        test_db: AsyncDB,
        cleanup_handlers: Any,
    ) -> None:
        """Second sweep at same `now` dispatches nothing (idempotent via next_run_at).

        After the first sweep, next_run_at is advanced to now + interval_seconds.
        At the same `now` timestamp, the job is no longer due.
        """
        tenant = "tenant-a"
        module = "test_module"
        job_type = "test_job"
        interval = 60

        job_mgr = JobManager(test_db)
        now = datetime.now(timezone.utc)

        # Create a due job
        job = await job_mgr.create_job(
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload={"test": "idempotent"},
            interval_seconds=interval,
            enabled=True,
        )
        job_id = job["id"]

        # Manually set next_run_at to past
        await test_db(test_db.scheduled_jobs.id == job_id).update(
            next_run_at=now - timedelta(seconds=10),
        )

        # Register handler
        register_job_handler(module, job_type, "test.tasks.run_job")

        # Capture dispatch calls
        dispatched: list[tuple[str, dict[str, Any]]] = []

        def fake_dispatch(task: str, kwargs: dict[str, Any]) -> None:
            """Capture dispatch calls."""
            dispatched.append((task, kwargs))

        # First sweep
        count1 = await _sweep_async(db=test_db, dispatch=fake_dispatch, now=now)
        assert count1 == 1
        assert len(dispatched) == 1

        # Clear dispatch list
        dispatched.clear()

        # Second sweep at SAME `now` timestamp
        count2 = await _sweep_async(db=test_db, dispatch=fake_dispatch, now=now)
        assert count2 == 0
        assert len(dispatched) == 0

        # Job should have next_run_at = now + interval
        updated_job = await job_mgr.get_job(tenant, job_id)
        assert updated_job is not None
        expected_next = now + timedelta(seconds=interval)
        assert updated_job["next_run_at"].replace(tzinfo=None) == expected_next.replace(
            tzinfo=None
        )
