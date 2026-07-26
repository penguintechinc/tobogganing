"""Tests for core scheduler JobManager."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_create_job_round_trip(real_dal: Any) -> None:
    """Create job with payload, retrieve it, verify JSON survives round-trip."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)
    now = datetime.now(timezone.utc)

    payload = {"device_id": "dev123", "test_type": "latency", "target": "example.com"}
    created = await manager.create_job(
        tenant="t1",
        module="perftest_cluster",
        job_type="server_test",
        payload=payload,
        interval_seconds=60,
        enabled=True,
    )

    assert created["id"]
    assert created["tenant"] == "t1"
    assert created["module"] == "perftest_cluster"
    assert created["job_type"] == "server_test"
    assert created["payload"] == payload  # Dict, not JSON string
    assert created["interval_seconds"] == 60
    assert created["enabled"] is True
    assert created["next_run_at"] > now

    # Retrieve and verify
    retrieved = await manager.get_job("t1", created["id"])
    assert retrieved is not None
    assert retrieved["payload"] == payload


@pytest.mark.asyncio
async def test_interval_seconds_validation(real_dal: Any) -> None:
    """interval_seconds < 30 must raise ValueError."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)

    with pytest.raises(ValueError, match="interval_seconds.*30"):
        await manager.create_job(
            tenant="t1",
            module="test",
            job_type="test",
            payload={},
            interval_seconds=29,
        )


@pytest.mark.asyncio
async def test_list_jobs_tenant_isolation(real_dal: Any) -> None:
    """Tenant A cannot list/get/delete tenant B's jobs."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)

    # Create jobs for two tenants
    job1 = await manager.create_job(
        tenant="t1",
        module="m1",
        job_type="j1",
        payload={"x": 1},
        interval_seconds=30,
    )
    job2 = await manager.create_job(
        tenant="t2",
        module="m1",
        job_type="j1",
        payload={"x": 2},
        interval_seconds=30,
    )

    # T1 should only see its own jobs
    t1_jobs = await manager.list_jobs("t1")
    assert len(t1_jobs) == 1
    assert t1_jobs[0]["id"] == job1["id"]

    # T2 should only see its own jobs
    t2_jobs = await manager.list_jobs("t2")
    assert len(t2_jobs) == 1
    assert t2_jobs[0]["id"] == job2["id"]

    # T1 cannot get T2's job
    retrieved = await manager.get_job("t1", job2["id"])
    assert retrieved is None

    # T1 cannot delete T2's job
    deleted = await manager.delete_job("t1", job2["id"])
    assert deleted is False

    # T2's job still exists
    retrieved = await manager.get_job("t2", job2["id"])
    assert retrieved is not None


@pytest.mark.asyncio
async def test_list_jobs_with_module_filter(real_dal: Any) -> None:
    """list_jobs with module filter returns only matching jobs."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)
    tenant = "t1"

    await manager.create_job(
        tenant=tenant,
        module="m1",
        job_type="j1",
        payload={},
        interval_seconds=30,
    )
    await manager.create_job(
        tenant=tenant,
        module="m2",
        job_type="j1",
        payload={},
        interval_seconds=30,
    )

    # Unfiltered
    all_jobs = await manager.list_jobs(tenant)
    assert len(all_jobs) == 2

    # Filtered to m1
    m1_jobs = await manager.list_jobs(tenant, module="m1")
    assert len(m1_jobs) == 1
    assert m1_jobs[0]["module"] == "m1"


@pytest.mark.asyncio
async def test_get_job_returns_none_for_missing(real_dal: Any) -> None:
    """get_job returns None for non-existent job."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)
    result = await manager.get_job("t1", "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_set_enabled(real_dal: Any) -> None:
    """set_enabled toggles the enabled flag."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)

    job = await manager.create_job(
        tenant="t1",
        module="m",
        job_type="j",
        payload={},
        interval_seconds=30,
        enabled=True,
    )
    assert job["enabled"] is True

    # Disable
    success = await manager.set_enabled("t1", job["id"], False)
    assert success is True

    retrieved = await manager.get_job("t1", job["id"])
    assert retrieved["enabled"] is False

    # Enable again
    success = await manager.set_enabled("t1", job["id"], True)
    assert success is True

    retrieved = await manager.get_job("t1", job["id"])
    assert retrieved["enabled"] is True


@pytest.mark.asyncio
async def test_set_enabled_cross_tenant_fails(real_dal: Any) -> None:
    """set_enabled scoped to tenant; cross-tenant fails."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)

    job = await manager.create_job(
        tenant="t1",
        module="m",
        job_type="j",
        payload={},
        interval_seconds=30,
        enabled=True,
    )

    # T2 cannot change T1's job
    success = await manager.set_enabled("t2", job["id"], False)
    assert success is False

    # T1's job unchanged
    retrieved = await manager.get_job("t1", job["id"])
    assert retrieved["enabled"] is True


@pytest.mark.asyncio
async def test_delete_job(real_dal: Any) -> None:
    """delete_job removes a job."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)

    job = await manager.create_job(
        tenant="t1",
        module="m",
        job_type="j",
        payload={},
        interval_seconds=30,
    )

    # Delete
    success = await manager.delete_job("t1", job["id"])
    assert success is True

    # Verify gone
    retrieved = await manager.get_job("t1", job["id"])
    assert retrieved is None


@pytest.mark.asyncio
async def test_delete_job_cross_tenant_fails(real_dal: Any) -> None:
    """delete_job scoped to tenant; cross-tenant fails."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)

    job = await manager.create_job(
        tenant="t1",
        module="m",
        job_type="j",
        payload={},
        interval_seconds=30,
    )

    # T2 cannot delete T1's job
    success = await manager.delete_job("t2", job["id"])
    assert success is False

    # T1's job still exists
    retrieved = await manager.get_job("t1", job["id"])
    assert retrieved is not None


@pytest.mark.asyncio
async def test_due_jobs_cross_tenant(real_dal: Any) -> None:
    """due_jobs returns only enabled+due jobs across all tenants by design."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)
    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=1)
    past = now - timedelta(seconds=10)

    # T1: enabled, due
    job1 = await manager.create_job(
        tenant="t1",
        module="m1",
        job_type="j1",
        payload={},
        interval_seconds=30,
        enabled=True,
    )
    # Manually set next_run_at to past for due_jobs query
    await real_dal(real_dal.scheduled_jobs.id == job1["id"]).update(next_run_at=past)

    # T2: enabled, due
    job2 = await manager.create_job(
        tenant="t2",
        module="m2",
        job_type="j2",
        payload={},
        interval_seconds=30,
        enabled=True,
    )
    await real_dal(real_dal.scheduled_jobs.id == job2["id"]).update(next_run_at=past)

    # T1: enabled, not due
    job3 = await manager.create_job(
        tenant="t1",
        module="m1",
        job_type="j3",
        payload={},
        interval_seconds=30,
        enabled=True,
    )
    await real_dal(real_dal.scheduled_jobs.id == job3["id"]).update(next_run_at=future)

    # T1: disabled, due (should not be returned)
    job4 = await manager.create_job(
        tenant="t1",
        module="m1",
        job_type="j4",
        payload={},
        interval_seconds=30,
        enabled=False,
    )
    await real_dal(real_dal.scheduled_jobs.id == job4["id"]).update(next_run_at=past)

    # due_jobs at `now` should return job1 and job2 only
    due = await manager.due_jobs(now=now, limit=100)
    assert len(due) == 2
    due_ids = {j["id"] for j in due}
    assert job1["id"] in due_ids
    assert job2["id"] in due_ids
    assert job3["id"] not in due_ids  # Not due
    assert job4["id"] not in due_ids  # Disabled


@pytest.mark.asyncio
async def test_due_jobs_limit(real_dal: Any) -> None:
    """due_jobs respects limit parameter."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)
    now = datetime.now(timezone.utc)
    past = now - timedelta(seconds=10)

    # Create 5 due jobs
    for i in range(5):
        job = await manager.create_job(
            tenant="t1",
            module="m",
            job_type=f"j{i}",
            payload={},
            interval_seconds=30,
        )
        await real_dal(real_dal.scheduled_jobs.id == job["id"]).update(
            next_run_at=past
        )

    # With limit=3, only 3 returned
    due = await manager.due_jobs(now=now, limit=3)
    assert len(due) == 3


@pytest.mark.asyncio
async def test_mark_ran_advances_next_run_at(real_dal: Any) -> None:
    """mark_ran sets last_run_at, advances next_run_at by interval_seconds."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)
    now = datetime.now(timezone.utc)
    past = now - timedelta(seconds=10)

    job = await manager.create_job(
        tenant="t1",
        module="m",
        job_type="j",
        payload={},
        interval_seconds=60,
    )
    original_next = job["next_run_at"]

    # Manually set next_run_at to past and last_run_at to None
    await real_dal(real_dal.scheduled_jobs.id == job["id"]).update(
        next_run_at=past, last_run_at=None
    )

    # Mark ran
    await manager.mark_ran(job_id=job["id"], now=now)

    # Fetch and verify
    updated = await manager.get_job("t1", job["id"])
    assert updated["last_run_at"] is not None
    # next_run_at should be now + 60 seconds
    expected_next = now + timedelta(seconds=60)
    # Allow small time delta due to execution time
    # Strip timezone for comparison since SQLite returns naive datetimes
    updated_next_tz = (
        updated["next_run_at"]
        if updated["next_run_at"].tzinfo is None
        else updated["next_run_at"].replace(tzinfo=None)
    )
    expected_next_naive = (
        expected_next
        if expected_next.tzinfo is None
        else expected_next.replace(tzinfo=None)
    )
    assert abs((updated_next_tz - expected_next_naive).total_seconds()) < 1
    assert updated["updated_at"] is not None


@pytest.mark.asyncio
async def test_mark_ran_idempotent_second_call(real_dal: Any) -> None:
    """Second call to mark_ran advances next_run_at again."""
    from hub_api.scheduler.job_manager import JobManager

    manager = JobManager(real_dal)
    now = datetime.now(timezone.utc)

    job = await manager.create_job(
        tenant="t1",
        module="m",
        job_type="j",
        payload={},
        interval_seconds=60,
    )

    # First mark ran
    await manager.mark_ran(job_id=job["id"], now=now)
    first_next = await manager.get_job("t1", job["id"])
    first_next_at = first_next["next_run_at"]

    # Second mark ran at now + 100 seconds
    second_now = now + timedelta(seconds=100)
    await manager.mark_ran(job_id=job["id"], now=second_now)
    second_next = await manager.get_job("t1", job["id"])
    second_next_at = second_next["next_run_at"]

    # Verify advanced again
    assert second_next_at > first_next_at
    expected = second_now + timedelta(seconds=60)
    # Strip timezone for comparison since SQLite returns naive datetimes
    second_next_tz = (
        second_next_at if second_next_at.tzinfo is None else second_next_at.replace(tzinfo=None)
    )
    expected_naive = expected if expected.tzinfo is None else expected.replace(tzinfo=None)
    assert abs((second_next_tz - expected_naive).total_seconds()) < 1
