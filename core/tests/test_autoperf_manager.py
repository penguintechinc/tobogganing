"""Tests for AutoPerf policy manager and state machine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_create_policy_round_trip(real_dal: Any) -> None:
    """Create policy with state and scheduler job, verify round-trip."""
    from core.modules.waddleperf_cluster.services.autoperf_manager import (
        AutoPerfManager,
    )
    from core.scheduler.job_manager import JobManager

    manager = AutoPerfManager(real_dal)
    jm = JobManager(real_dal)

    policy_data = {
        "name": "Test Policy",
        "device_id": "dev123",
        "target": "example.com",
        "t1_interval_seconds": 300,
        "t2_interval_seconds": 120,
        "t3_interval_seconds": 60,
        "deescalate_after_clean": 3,
    }

    created = await manager.create_policy("tenant1", **policy_data)

    assert created["id"]
    assert created["tenant"] == "tenant1"
    assert created["name"] == "Test Policy"
    assert created["device_id"] == "dev123"
    assert created["target"] == "example.com"
    assert created["t1_interval_seconds"] == 300
    assert created["t2_interval_seconds"] == 120
    assert created["t3_interval_seconds"] == 60
    assert created["deescalate_after_clean"] == 3
    assert created["enabled"] is True

    # Verify state row was created
    state = await manager.get_state("tenant1", created["id"])
    assert state is not None
    assert state["policy_id"] == created["id"]
    assert state["current_tier"] == 1
    assert state["clean_cycles"] == 0
    assert state["escalated_at"] is None

    # Verify scheduler job was created with t1 interval
    jobs = await jm.list_jobs("tenant1", "waddleperf_cluster")
    assert len(jobs) == 1
    assert jobs[0]["job_type"] == "autoperf_cycle"
    assert jobs[0]["payload"]["policy_id"] == created["id"]
    assert jobs[0]["interval_seconds"] == 300


@pytest.mark.asyncio
async def test_create_policy_interval_validation(real_dal: Any) -> None:
    """Interval validation: >=30, t3<=t2<=t1."""
    from core.modules.waddleperf_cluster.services.autoperf_manager import (
        AutoPerfManager,
    )

    manager = AutoPerfManager(real_dal)

    # Test t1 < 30
    with pytest.raises(ValueError, match="interval.*30"):
        await manager.create_policy(
            "tenant1",
            name="Bad",
            device_id="dev1",
            target="example.com",
            t1_interval_seconds=20,
            t2_interval_seconds=120,
            t3_interval_seconds=60,
            deescalate_after_clean=3,
        )

    # Test t1 < t2
    with pytest.raises(ValueError, match="t3.*t2.*t1"):
        await manager.create_policy(
            "tenant1",
            name="Bad",
            device_id="dev1",
            target="example.com",
            t1_interval_seconds=100,
            t2_interval_seconds=120,
            t3_interval_seconds=60,
            deescalate_after_clean=3,
        )

    # Test t2 < t3
    with pytest.raises(ValueError, match="t3.*t2.*t1"):
        await manager.create_policy(
            "tenant1",
            name="Bad",
            device_id="dev1",
            target="example.com",
            t1_interval_seconds=300,
            t2_interval_seconds=120,
            t3_interval_seconds=150,
            deescalate_after_clean=3,
        )


@pytest.mark.asyncio
async def test_create_policy_tenant_isolation(real_dal: Any) -> None:
    """Tenant A's policies not visible to tenant B."""
    from core.modules.waddleperf_cluster.services.autoperf_manager import (
        AutoPerfManager,
    )

    manager = AutoPerfManager(real_dal)

    policy1 = await manager.create_policy(
        "tenant1",
        name="T1 Policy",
        device_id="dev1",
        target="example.com",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
    )

    policy2 = await manager.create_policy(
        "tenant2",
        name="T2 Policy",
        device_id="dev2",
        target="example.org",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
    )

    # Tenant 1 cannot get tenant 2's state
    state = await manager.get_state("tenant1", policy2["id"])
    assert state is None

    # Tenant 2 cannot get tenant 1's state
    state = await manager.get_state("tenant2", policy1["id"])
    assert state is None


@pytest.mark.asyncio
async def test_record_cycle_breach_escalates(real_dal: Any) -> None:
    """Breach escalates tier T1->T2->T3, caps at 3."""
    from core.modules.waddleperf_cluster.services.autoperf_manager import (
        AutoPerfManager,
    )

    manager = AutoPerfManager(real_dal)
    now = datetime.now(timezone.utc)

    policy = await manager.create_policy(
        "tenant1",
        name="Escalate Test",
        device_id="dev1",
        target="example.com",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
    )

    # Initial state: tier 1
    state = await manager.get_state("tenant1", policy["id"])
    assert state["current_tier"] == 1
    assert state["clean_cycles"] == 0
    assert state["escalated_at"] is None

    # First breach: T1 -> T2
    result = await manager.record_cycle("tenant1", policy["id"], breached=True)
    assert result["current_tier"] == 2
    assert result["clean_cycles"] == 0
    assert result["escalated_at"] is not None

    # Second breach: T2 -> T3
    result = await manager.record_cycle("tenant1", policy["id"], breached=True)
    assert result["current_tier"] == 3
    assert result["clean_cycles"] == 0

    # Third breach: should cap at T3
    result = await manager.record_cycle("tenant1", policy["id"], breached=True)
    assert result["current_tier"] == 3
    assert result["clean_cycles"] == 0


@pytest.mark.asyncio
async def test_record_cycle_clean_counts_and_deescalates(real_dal: Any) -> None:
    """Clean cycle increments counter, deescalates after N clean cycles."""
    from core.modules.waddleperf_cluster.services.autoperf_manager import (
        AutoPerfManager,
    )

    manager = AutoPerfManager(real_dal)

    policy = await manager.create_policy(
        "tenant1",
        name="Deescalate Test",
        device_id="dev1",
        target="example.com",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
    )

    # Escalate to T3
    await manager.record_cycle("tenant1", policy["id"], breached=True)
    await manager.record_cycle("tenant1", policy["id"], breached=True)
    state = await manager.get_state("tenant1", policy["id"])
    assert state["current_tier"] == 3

    # First clean cycle: clean_cycles=1, tier stays 3
    result = await manager.record_cycle("tenant1", policy["id"], breached=False)
    assert result["current_tier"] == 3
    assert result["clean_cycles"] == 1

    # Second clean cycle: clean_cycles=2, tier stays 3
    result = await manager.record_cycle("tenant1", policy["id"], breached=False)
    assert result["current_tier"] == 3
    assert result["clean_cycles"] == 2

    # Third clean cycle (reaches deescalate_after_clean=3): T3->T2, clean_cycles=0
    result = await manager.record_cycle("tenant1", policy["id"], breached=False)
    assert result["current_tier"] == 2
    assert result["clean_cycles"] == 0

    # Three more clean cycles for T2->T1
    await manager.record_cycle("tenant1", policy["id"], breached=False)
    await manager.record_cycle("tenant1", policy["id"], breached=False)
    result = await manager.record_cycle("tenant1", policy["id"], breached=False)
    assert result["current_tier"] == 1
    assert result["clean_cycles"] == 0


@pytest.mark.asyncio
async def test_record_cycle_tier_retunes_interval(real_dal: Any) -> None:
    """Tier change updates scheduler job interval_seconds."""
    from core.modules.waddleperf_cluster.services.autoperf_manager import (
        AutoPerfManager,
    )
    from core.scheduler.job_manager import JobManager

    manager = AutoPerfManager(real_dal)
    jm = JobManager(real_dal)

    policy = await manager.create_policy(
        "tenant1",
        name="Retune Test",
        device_id="dev1",
        target="example.com",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
    )

    # Initial job interval is t1 (300)
    jobs = await jm.list_jobs("tenant1", "waddleperf_cluster")
    assert jobs[0]["interval_seconds"] == 300

    # Breach to T2: interval should become 120
    await manager.record_cycle("tenant1", policy["id"], breached=True)
    jobs = await jm.list_jobs("tenant1", "waddleperf_cluster")
    assert jobs[0]["interval_seconds"] == 120

    # Breach to T3: interval should become 60
    await manager.record_cycle("tenant1", policy["id"], breached=True)
    jobs = await jm.list_jobs("tenant1", "waddleperf_cluster")
    assert jobs[0]["interval_seconds"] == 60

    # Deescalate to T2: interval should become 120
    await manager.record_cycle("tenant1", policy["id"], breached=False)
    await manager.record_cycle("tenant1", policy["id"], breached=False)
    await manager.record_cycle("tenant1", policy["id"], breached=False)
    jobs = await jm.list_jobs("tenant1", "waddleperf_cluster")
    assert jobs[0]["interval_seconds"] == 120


@pytest.mark.asyncio
async def test_delete_policy_removes_all(real_dal: Any) -> None:
    """Delete policy removes policy + state + scheduler job."""
    from core.modules.waddleperf_cluster.services.autoperf_manager import (
        AutoPerfManager,
    )
    from core.scheduler.job_manager import JobManager

    manager = AutoPerfManager(real_dal)
    jm = JobManager(real_dal)

    policy = await manager.create_policy(
        "tenant1",
        name="Delete Test",
        device_id="dev1",
        target="example.com",
        t1_interval_seconds=300,
        t2_interval_seconds=120,
        t3_interval_seconds=60,
        deescalate_after_clean=3,
    )

    policy_id = policy["id"]

    # Verify all exist
    state = await manager.get_state("tenant1", policy_id)
    assert state is not None

    jobs = await jm.list_jobs("tenant1", "waddleperf_cluster")
    assert len(jobs) == 1
    job_id = jobs[0]["id"]

    # Delete policy
    await manager.delete_policy("tenant1", policy_id)

    # Verify all deleted
    state = await manager.get_state("tenant1", policy_id)
    assert state is None

    job = await jm.get_job("tenant1", job_id)
    assert job is None
