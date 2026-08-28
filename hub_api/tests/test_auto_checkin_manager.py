"""Tests for AutoCheckInManager: CRUD, tier/parent validation, scheduler wiring."""

from __future__ import annotations

from typing import Any

import pytest

from hub_api.modules.perftest_cluster.services.auto_checkin_manager import (
    AutoCheckInManager,
)
from hub_api.scheduler.job_manager import JobManager


@pytest.mark.asyncio
async def test_create_checkin_round_trip(real_dal: Any) -> None:
    """Create a tier-1 check-in; verify row, state, and scheduler job."""
    manager = AutoCheckInManager(real_dal)
    jm = JobManager(real_dal)

    created = await manager.create_checkin(
        tenant="tenant1",
        name="Edge Wifi Baseline",
        device_id="dev-1",
        target_kind="external",
        target="example.com",
        test_types=["http_trace", "traceroute", "udp", "http2"],
        interval_minutes=5,
        jitter_pct=10,
        samples_per_run=3,
        threshold_stddev_max=50.0,
        tier=1,
    )

    assert created["id"]
    assert created["tenant"] == "tenant1"
    assert created["test_types"] == ["http_trace", "traceroute", "udp", "http2"]
    assert created["interval_minutes"] == 5
    assert created["jitter_pct"] == 10
    assert created["samples_per_run"] == 3
    assert created["threshold_stddev_max"] == 50.0
    assert created["tier"] == 1
    assert created["parent_checkin_id"] is None
    assert created["enabled"] is True

    state = await manager.get_state("tenant1", created["id"])
    assert state is not None
    assert state["last_breached"] is False
    assert state["last_run_at"] is None

    jobs = await jm.list_jobs("tenant1", "perftest_cluster")
    assert len(jobs) == 1
    assert jobs[0]["job_type"] == "auto_checkin"
    assert jobs[0]["payload"]["checkin_id"] == created["id"]
    assert jobs[0]["interval_seconds"] == 300


@pytest.mark.asyncio
async def test_create_checkin_bound_validation(real_dal: Any) -> None:
    """interval_minutes/jitter_pct/samples_per_run/tier/target_kind/test_types bounds."""
    manager = AutoCheckInManager(real_dal)

    with pytest.raises(ValueError, match="interval_minutes"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "external",
            "example.com",
            ["icmp"],
            interval_minutes=61,
        )
    with pytest.raises(ValueError, match="jitter_pct"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "external",
            "example.com",
            ["icmp"],
            jitter_pct=11,
        )
    with pytest.raises(ValueError, match="samples_per_run"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "external",
            "example.com",
            ["icmp"],
            samples_per_run=6,
        )
    with pytest.raises(ValueError, match="target_kind"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "bogus",
            "example.com",
            ["icmp"],
        )
    with pytest.raises(ValueError, match="test_types"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "external",
            "example.com",
            ["not_a_real_type"],
        )


@pytest.mark.asyncio
async def test_create_checkin_tier2_requires_valid_parent(real_dal: Any) -> None:
    """tier=2 requires parent_checkin_id pointing at an existing tier-1 row."""
    manager = AutoCheckInManager(real_dal)

    with pytest.raises(ValueError, match="parent_checkin_id"):
        await manager.create_checkin(
            "t1",
            "orphan-tier2",
            "dev1",
            "external",
            "example.com",
            ["throughput"],
            tier=2,
        )

    tier1 = await manager.create_checkin(
        "t1",
        "tier1",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
        tier=1,
    )

    with pytest.raises(ValueError, match="tier 1"):
        await manager.create_checkin(
            "t1",
            "wrong-parent-tier",
            "dev1",
            "external",
            "example.com",
            ["throughput"],
            tier=3,
            parent_checkin_id=tier1["id"],
        )

    tier2 = await manager.create_checkin(
        "t1",
        "tier2",
        "dev1",
        "external",
        "example.com",
        ["throughput"],
        tier=2,
        parent_checkin_id=tier1["id"],
    )
    assert tier2["parent_checkin_id"] == tier1["id"]

    with pytest.raises(ValueError, match="must not set parent_checkin_id"):
        await manager.create_checkin(
            "t1",
            "tier1-with-parent",
            "dev1",
            "external",
            "example.com",
            ["icmp"],
            tier=1,
            parent_checkin_id=tier1["id"],
        )


@pytest.mark.asyncio
async def test_update_checkin_interval_retunes_job(real_dal: Any) -> None:
    """Updating interval_minutes updates the scheduled job's interval_seconds."""
    manager = AutoCheckInManager(real_dal)
    jm = JobManager(real_dal)

    created = await manager.create_checkin(
        "t1",
        "retune",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
        interval_minutes=5,
    )
    updated = await manager.update_checkin("t1", created["id"], interval_minutes=30)
    assert updated["interval_minutes"] == 30

    jobs = await jm.list_jobs("t1", "perftest_cluster")
    assert jobs[0]["interval_seconds"] == 1800


@pytest.mark.asyncio
async def test_delete_checkin_rejects_when_dependents_exist(real_dal: Any) -> None:
    """Deleting a check-in with tier-dependent children raises ValueError."""
    manager = AutoCheckInManager(real_dal)

    tier1 = await manager.create_checkin(
        "t1",
        "parent",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
        tier=1,
    )
    await manager.create_checkin(
        "t1",
        "child",
        "dev1",
        "external",
        "example.com",
        ["throughput"],
        tier=2,
        parent_checkin_id=tier1["id"],
    )

    with pytest.raises(ValueError, match="tier dependency"):
        await manager.delete_checkin("t1", tier1["id"])


@pytest.mark.asyncio
async def test_delete_checkin_removes_state_and_job(real_dal: Any) -> None:
    """Deleting a leaf check-in removes its row, state, and scheduler job."""
    manager = AutoCheckInManager(real_dal)
    jm = JobManager(real_dal)

    created = await manager.create_checkin(
        "t1",
        "leaf",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
        tier=1,
    )
    deleted = await manager.delete_checkin("t1", created["id"])
    assert deleted is True

    assert await manager.get_checkin("t1", created["id"]) is None
    assert await manager.get_state("t1", created["id"]) is None
    assert await jm.list_jobs("t1", "perftest_cluster") == []


@pytest.mark.asyncio
async def test_tenant_isolation(real_dal: Any) -> None:
    """Cross-tenant reads/deletes are invisible."""
    manager = AutoCheckInManager(real_dal)
    created = await manager.create_checkin(
        "tenant-a",
        "iso",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
    )
    assert await manager.get_checkin("tenant-b", created["id"]) is None
    assert await manager.delete_checkin("tenant-b", created["id"]) is False


@pytest.mark.asyncio
async def test_manager_rejects_none_db() -> None:
    """Constructing a manager with db=None raises ValueError immediately."""
    with pytest.raises(ValueError, match="Database instance cannot be None"):
        AutoCheckInManager(None)


@pytest.mark.asyncio
async def test_create_checkin_empty_test_types_rejected(real_dal: Any) -> None:
    """test_types=[] is rejected as non-empty-list, distinct from unsupported-type."""
    manager = AutoCheckInManager(real_dal)
    with pytest.raises(ValueError, match="test_types must be a non-empty list"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "external",
            "example.com",
            [],
        )


@pytest.mark.asyncio
async def test_create_checkin_invalid_tier_rejected(real_dal: Any) -> None:
    """tier outside {1,2,3} is rejected."""
    manager = AutoCheckInManager(real_dal)
    with pytest.raises(ValueError, match="tier must be one of"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "external",
            "example.com",
            ["icmp"],
            tier=5,
        )


@pytest.mark.asyncio
async def test_create_checkin_parent_not_found(real_dal: Any) -> None:
    """A tier>1 parent_checkin_id that doesn't exist is rejected."""
    manager = AutoCheckInManager(real_dal)
    with pytest.raises(ValueError, match="parent_checkin_id not found or cross-tenant"):
        await manager.create_checkin(
            "t1",
            "bad",
            "dev1",
            "external",
            "example.com",
            ["throughput"],
            tier=2,
            parent_checkin_id="does-not-exist",
        )


@pytest.mark.asyncio
async def test_update_checkin_not_found_returns_none(real_dal: Any) -> None:
    """Updating an unknown checkin_id returns None (no ValueError)."""
    manager = AutoCheckInManager(real_dal)
    result = await manager.update_checkin("t1", "ghost", name="x")
    assert result is None


@pytest.mark.asyncio
async def test_update_checkin_test_types_unsupported_rejected(real_dal: Any) -> None:
    """Updating test_types to an unsupported type raises ValueError."""
    manager = AutoCheckInManager(real_dal)
    created = await manager.create_checkin(
        "t1",
        "retest",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
    )
    with pytest.raises(ValueError, match="Unsupported test_types"):
        await manager.update_checkin("t1", created["id"], test_types=["not_a_real_type"])


@pytest.mark.asyncio
async def test_update_checkin_test_types_valid_round_trips(real_dal: Any) -> None:
    """Updating test_types to a valid list persists and JSON round-trips."""
    manager = AutoCheckInManager(real_dal)
    created = await manager.create_checkin(
        "t1",
        "retest2",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
    )
    updated = await manager.update_checkin(
        "t1", created["id"], test_types=["http_trace", "traceroute"]
    )
    assert updated["test_types"] == ["http_trace", "traceroute"]


@pytest.mark.asyncio
async def test_update_checkin_interval_out_of_bounds_rejected(real_dal: Any) -> None:
    manager = AutoCheckInManager(real_dal)
    created = await manager.create_checkin(
        "t1",
        "bounds1",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
    )
    with pytest.raises(ValueError, match="interval_minutes"):
        await manager.update_checkin("t1", created["id"], interval_minutes=999)


@pytest.mark.asyncio
async def test_update_checkin_jitter_out_of_bounds_rejected(real_dal: Any) -> None:
    manager = AutoCheckInManager(real_dal)
    created = await manager.create_checkin(
        "t1",
        "bounds2",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
    )
    with pytest.raises(ValueError, match="jitter_pct"):
        await manager.update_checkin("t1", created["id"], jitter_pct=99)


@pytest.mark.asyncio
async def test_update_checkin_samples_per_run_out_of_bounds_rejected(real_dal: Any) -> None:
    manager = AutoCheckInManager(real_dal)
    created = await manager.create_checkin(
        "t1",
        "bounds3",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
    )
    with pytest.raises(ValueError, match="samples_per_run"):
        await manager.update_checkin("t1", created["id"], samples_per_run=99)


@pytest.mark.asyncio
async def test_update_checkin_enabled_false_disables_job(real_dal: Any) -> None:
    """Setting enabled=False on update propagates to the scheduled job."""
    manager = AutoCheckInManager(real_dal)
    jm = JobManager(real_dal)
    created = await manager.create_checkin(
        "t1",
        "disable-me",
        "dev1",
        "external",
        "example.com",
        ["icmp"],
    )
    updated = await manager.update_checkin("t1", created["id"], enabled=False)
    assert updated["enabled"] is False

    jobs = await jm.list_jobs("t1", "perftest_cluster")
    assert jobs[0]["enabled"] is False


@pytest.mark.asyncio
async def test_find_job_returns_none_when_no_match(real_dal: Any) -> None:
    """_find_job scans and returns None when no scheduled job matches."""
    manager = AutoCheckInManager(real_dal)
    result = await manager._find_job("t1", "no-such-checkin-id")
    assert result is None
