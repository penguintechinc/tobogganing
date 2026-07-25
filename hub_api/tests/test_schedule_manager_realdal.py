"""Integration tests for ScheduleManager with real penguin-dal AsyncDB."""
from __future__ import annotations

import pytest
from datetime import datetime

from hub_api.modules.waddleperf_client.services.schedule_manager import (
    ScheduleManager,
    TestScheduleDTO,
)


@pytest.mark.asyncio
async def test_schedule_manager_create_and_retrieve(real_dal) -> None:
    """Test creating a schedule and retrieving it."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    created = await manager.create_schedule({
        "org_unit_id": "ou-test-1",
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": True,
    })

    assert created.id is not None
    assert created.tenant == "test-tenant"
    assert created.test_type == "latency"
    assert created.target == "example.com"
    assert created.interval_seconds == 300
    assert created.enabled is True
    assert created.org_unit_id == "ou-test-1"

    # Retrieve it
    retrieved = await manager.get_schedule(created.id)
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.test_type == "latency"


@pytest.mark.asyncio
async def test_schedule_manager_tenant_isolation(real_dal) -> None:
    """Test that schedules are isolated by tenant."""
    manager1 = ScheduleManager(real_dal, "tenant-1")
    manager2 = ScheduleManager(real_dal, "tenant-2")

    await manager1.initialize()
    await manager2.initialize()

    # Create schedule in tenant-1
    sched1 = await manager1.create_schedule({
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": True,
    })

    # Try to access from tenant-2 (should not find it)
    result = await manager2.get_schedule(sched1.id)
    assert result is None

    # Should find it in tenant-1
    result = await manager1.get_schedule(sched1.id)
    assert result is not None
    assert result.id == sched1.id


@pytest.mark.asyncio
async def test_schedule_manager_update(real_dal) -> None:
    """Test updating a schedule."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    created = await manager.create_schedule({
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": True,
    })

    # Update it
    updated = await manager.update_schedule(created.id, {
        "interval_seconds": 600,
        "enabled": False,
    })

    assert updated is not None
    assert updated.id == created.id
    assert updated.interval_seconds == 600
    assert updated.enabled is False

    # Verify persistence
    retrieved = await manager.get_schedule(created.id)
    assert retrieved.interval_seconds == 600
    assert retrieved.enabled is False


@pytest.mark.asyncio
async def test_schedule_manager_delete(real_dal) -> None:
    """Test deleting a schedule."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    created = await manager.create_schedule({
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": True,
    })

    # Delete it
    success = await manager.delete_schedule(created.id)
    assert success is True

    # Should not be retrievable
    retrieved = await manager.get_schedule(created.id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_schedule_manager_delete_not_found(real_dal) -> None:
    """Test deleting a non-existent schedule."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    success = await manager.delete_schedule("nonexistent-id")
    assert success is False


@pytest.mark.asyncio
async def test_schedule_manager_list_schedules(real_dal) -> None:
    """Test listing schedules with pagination."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    # Create multiple schedules
    ids = []
    for i in range(3):
        sched = await manager.create_schedule({
            "test_type": f"test-{i}",
            "target": f"target-{i}.com",
            "interval_seconds": 300 + i * 100,
            "enabled": True,
        })
        ids.append(sched.id)

    # List all
    all_scheds = await manager.list_schedules()
    assert len(all_scheds) >= 3

    # List with limit
    limited = await manager.list_schedules(limit=2)
    assert len(limited) <= 2


@pytest.mark.asyncio
async def test_schedule_manager_list_schedules_by_org_unit(real_dal) -> None:
    """Test listing schedules filtered by org unit."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    # Create schedules for different org units
    ou1_sched = await manager.create_schedule({
        "org_unit_id": "ou-1",
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": True,
    })

    ou2_sched = await manager.create_schedule({
        "org_unit_id": "ou-2",
        "test_type": "throughput",
        "target": "example.com",
        "interval_seconds": 600,
        "enabled": True,
    })

    # List for ou-1
    ou1_list = await manager.list_schedules(org_unit_id="ou-1")
    ou1_ids = [s.id for s in ou1_list]

    assert ou1_sched.id in ou1_ids
    # ou2 should not be in this list
    ou2_in_list = any(s.id == ou2_sched.id for s in ou1_list)
    assert not ou2_in_list


@pytest.mark.asyncio
async def test_schedule_manager_resolve_for_device(real_dal) -> None:
    """Test resolving schedules for a device."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    # Create OU-specific schedule
    ou_sched = await manager.create_schedule({
        "org_unit_id": "ou-dev-1",
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": True,
    })

    # Create tenant-wide schedule
    tenant_sched = await manager.create_schedule({
        "org_unit_id": None,
        "test_type": "throughput",
        "target": "example.com",
        "interval_seconds": 600,
        "enabled": True,
    })

    # Create disabled schedule (should not be included)
    disabled_sched = await manager.create_schedule({
        "org_unit_id": "ou-dev-1",
        "test_type": "availability",
        "target": "example.com",
        "interval_seconds": 900,
        "enabled": False,
    })

    # Mock device object
    class MockDevice:
        def __init__(self, device_id: str, org_unit_id: str) -> None:
            self.id = device_id
            self.org_unit_id = org_unit_id

    device = MockDevice("device-1", "ou-dev-1")

    # Resolve schedules
    resolved = await manager.resolve_for_device(device)

    resolved_ids = [s.id for s in resolved]

    # Should include OU-specific and tenant-wide
    assert ou_sched.id in resolved_ids
    assert tenant_sched.id in resolved_ids

    # Should exclude disabled
    assert disabled_sched.id not in resolved_ids

    # All should be enabled
    for sched in resolved:
        assert sched.enabled is True


@pytest.mark.asyncio
async def test_schedule_manager_resolve_for_device_tenant_wide_only(real_dal) -> None:
    """Test resolving schedules when only tenant-wide schedules exist."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    # Create only tenant-wide schedule
    sched = await manager.create_schedule({
        "org_unit_id": None,
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": True,
    })

    class MockDevice:
        def __init__(self, device_id: str, org_unit_id: str) -> None:
            self.id = device_id
            self.org_unit_id = org_unit_id

    device = MockDevice("device-1", "ou-other")

    # Resolve schedules (OU has no specific schedules)
    resolved = await manager.resolve_for_device(device)

    resolved_ids = [s.id for s in resolved]
    assert sched.id in resolved_ids
    assert len([s for s in resolved if s.org_unit_id is None]) > 0


@pytest.mark.asyncio
async def test_schedule_manager_all_not_null_fields(real_dal) -> None:
    """Test that all NOT NULL fields are properly set on create."""
    manager = ScheduleManager(real_dal, "test-tenant")
    await manager.initialize()

    created = await manager.create_schedule({
        "org_unit_id": None,
        "test_type": "latency",
        "target": "example.com",
        "interval_seconds": 300,
        "enabled": False,
    })

    # Verify all fields are set
    assert created.id is not None
    assert isinstance(created.id, str)
    assert created.tenant == "test-tenant"
    assert created.test_type == "latency"
    assert created.target == "example.com"
    assert created.interval_seconds == 300
    assert created.enabled is False
    assert created.org_unit_id is None
    assert isinstance(created.created_at, datetime)
    assert isinstance(created.updated_at, datetime)

    # Retrieve and verify persistence
    retrieved = await manager.get_schedule(created.id)
    assert retrieved.id == created.id
    assert retrieved.tenant == "test-tenant"
    assert retrieved.test_type == "latency"
    assert retrieved.target == "example.com"
    assert retrieved.interval_seconds == 300
    assert retrieved.enabled is False
    assert retrieved.created_at is not None
    assert retrieved.updated_at is not None
