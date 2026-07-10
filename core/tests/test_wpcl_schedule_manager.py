"""Test ScheduleManager CRUD and tenant scoping."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from core.modules.waddleperf_client.services.schedule_manager import (
    ScheduleManager,
    TestScheduleDTO,
)


def make_mock_schedule(data: dict) -> MagicMock:
    """Create a mock schedule object."""
    schedule = MagicMock()
    for key, value in data.items():
        setattr(schedule, key, value)
    schedule.as_dict.return_value = data
    return schedule


@pytest.mark.asyncio
async def test_schedule_manager_create_schedule() -> None:
    """Test creating a schedule."""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    mock_schedule = make_mock_schedule(
        {
            "id": "sched-123",
            "tenant": "tenant-1",
            "org_unit_id": "ou-456",
            "test_type": "latency",
            "target": "example.com",
            "interval_seconds": 300,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    db.test_schedules.create = MagicMock(return_value=mock_schedule)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.create_schedule(
        {
            "org_unit_id": "ou-456",
            "test_type": "latency",
            "target": "example.com",
            "interval_seconds": 300,
            "enabled": True,
        }
    )

    assert result.id == "sched-123"
    assert result.tenant == "tenant-1"
    assert result.test_type == "latency"
    assert result.target == "example.com"
    assert result.interval_seconds == 300
    assert result.enabled is True

    # Verify tenant was passed
    db.test_schedules.create.assert_called_once()
    call_kwargs = db.test_schedules.create.call_args[1]
    assert call_kwargs["tenant"] == "tenant-1"


@pytest.mark.asyncio
async def test_schedule_manager_get_schedule() -> None:
    """Test getting a schedule by ID."""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    mock_schedule = make_mock_schedule(
        {
            "id": "sched-123",
            "tenant": "tenant-1",
            "org_unit_id": "ou-456",
            "test_type": "latency",
            "target": "example.com",
            "interval_seconds": 300,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    db.test_schedules.select = MagicMock(return_value=mock_schedule)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.get_schedule("sched-123")

    assert result is not None
    assert result.id == "sched-123"
    assert result.tenant == "tenant-1"

    # Verify tenant scoping
    db.test_schedules.select.assert_called_once_with(
        id="sched-123", tenant="tenant-1"
    )


@pytest.mark.asyncio
async def test_schedule_manager_get_schedule_not_found() -> None:
    """Test getting a non-existent schedule."""
    db = MagicMock()
    db.test_schedules.select = MagicMock(return_value=None)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.get_schedule("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_schedule_manager_list_schedules() -> None:
    """Test listing schedules."""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    mock_schedules = [
        make_mock_schedule(
            {
                "id": "sched-1",
                "tenant": "tenant-1",
                "org_unit_id": "ou-456",
                "test_type": "latency",
                "target": "example.com",
                "interval_seconds": 300,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ),
        make_mock_schedule(
            {
                "id": "sched-2",
                "tenant": "tenant-1",
                "org_unit_id": "ou-456",
                "test_type": "throughput",
                "target": "example.com",
                "interval_seconds": 600,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ),
    ]
    db.test_schedules.select_list = MagicMock(return_value=mock_schedules)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.list_schedules(org_unit_id="ou-456")

    assert len(result) == 2
    assert result[0].id == "sched-1"
    assert result[1].id == "sched-2"

    # Verify tenant and org_unit_id scoping
    db.test_schedules.select_list.assert_called_once()
    call_kwargs = db.test_schedules.select_list.call_args[1]
    assert call_kwargs["tenant"] == "tenant-1"
    assert call_kwargs["org_unit_id"] == "ou-456"


@pytest.mark.asyncio
async def test_schedule_manager_list_schedules_tenant_wide() -> None:
    """Test listing tenant-wide schedules."""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    mock_schedules = [
        make_mock_schedule(
            {
                "id": "sched-1",
                "tenant": "tenant-1",
                "org_unit_id": None,
                "test_type": "latency",
                "target": "example.com",
                "interval_seconds": 300,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ),
    ]
    db.test_schedules.select_list = MagicMock(return_value=mock_schedules)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.list_schedules()

    assert len(result) == 1
    assert result[0].org_unit_id is None

    # Verify tenant scoping but no org_unit_id filter
    call_kwargs = db.test_schedules.select_list.call_args[1]
    assert call_kwargs["tenant"] == "tenant-1"


@pytest.mark.asyncio
async def test_schedule_manager_update_schedule() -> None:
    """Test updating a schedule."""
    db = MagicMock()
    now = datetime.now(timezone.utc)

    # Mock for get_schedule calls
    original = make_mock_schedule(
        {
            "id": "sched-123",
            "tenant": "tenant-1",
            "org_unit_id": "ou-456",
            "test_type": "latency",
            "target": "example.com",
            "interval_seconds": 300,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    updated = make_mock_schedule(
        {
            "id": "sched-123",
            "tenant": "tenant-1",
            "org_unit_id": "ou-456",
            "test_type": "latency",
            "target": "example.com",
            "interval_seconds": 600,  # Changed
            "enabled": False,  # Changed
            "created_at": now,
            "updated_at": now,
        }
    )

    db.test_schedules.select = MagicMock(side_effect=[original, updated])
    db.test_schedules.update = MagicMock()

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.update_schedule(
        "sched-123",
        {"interval_seconds": 600, "enabled": False},
    )

    assert result is not None
    assert result.interval_seconds == 600
    assert result.enabled is False

    # Verify tenant scoping on update
    db.test_schedules.update.assert_called_once()
    call_kwargs = db.test_schedules.update.call_args[1]
    assert call_kwargs["tenant"] == "tenant-1"
    assert call_kwargs["id"] == "sched-123"


@pytest.mark.asyncio
async def test_schedule_manager_update_schedule_not_found() -> None:
    """Test updating a non-existent schedule."""
    db = MagicMock()
    db.test_schedules.select = MagicMock(return_value=None)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.update_schedule("nonexistent", {"enabled": False})

    assert result is None
    db.test_schedules.update.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_manager_delete_schedule() -> None:
    """Test deleting a schedule."""
    db = MagicMock()
    now = datetime.now(timezone.utc)
    mock_schedule = make_mock_schedule(
        {
            "id": "sched-123",
            "tenant": "tenant-1",
            "org_unit_id": "ou-456",
            "test_type": "latency",
            "target": "example.com",
            "interval_seconds": 300,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    db.test_schedules.select = MagicMock(return_value=mock_schedule)
    db.test_schedules.delete = MagicMock()

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.delete_schedule("sched-123")

    assert result is True

    # Verify tenant scoping
    db.test_schedules.delete.assert_called_once_with(
        id="sched-123", tenant="tenant-1"
    )


@pytest.mark.asyncio
async def test_schedule_manager_delete_schedule_not_found() -> None:
    """Test deleting a non-existent schedule."""
    db = MagicMock()
    db.test_schedules.select = MagicMock(return_value=None)

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    result = await manager.delete_schedule("nonexistent")

    assert result is False
    db.test_schedules.delete.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_manager_resolve_for_device_ou_specific() -> None:
    """Test resolving schedules for a device with OU-specific schedules."""
    db = MagicMock()
    now = datetime.now(timezone.utc)

    # OU-specific schedules
    ou_schedules = [
        make_mock_schedule(
            {
                "id": "sched-1",
                "tenant": "tenant-1",
                "org_unit_id": "ou-456",
                "test_type": "latency",
                "target": "example.com",
                "interval_seconds": 300,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ),
    ]

    # Tenant-wide schedules
    tenant_wide = [
        make_mock_schedule(
            {
                "id": "sched-2",
                "tenant": "tenant-1",
                "org_unit_id": None,
                "test_type": "throughput",
                "target": "example.com",
                "interval_seconds": 600,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ),
    ]

    db.test_schedules.select_list = MagicMock(side_effect=[ou_schedules, tenant_wide])

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    # Create mock device
    device = MagicMock()
    device.id = "device-1"
    device.org_unit_id = "ou-456"

    result = await manager.resolve_for_device(device)

    assert len(result) == 2
    assert result[0].id == "sched-1"
    assert result[0].org_unit_id == "ou-456"
    assert result[1].id == "sched-2"
    assert result[1].org_unit_id is None

    # Verify both queries were tenant-scoped and enabled
    calls = db.test_schedules.select_list.call_args_list
    assert len(calls) == 2

    # First call: OU-specific
    assert calls[0][1]["tenant"] == "tenant-1"
    assert calls[0][1]["org_unit_id"] == "ou-456"
    assert calls[0][1]["enabled"] is True

    # Second call: tenant-wide
    assert calls[1][1]["tenant"] == "tenant-1"
    assert calls[1][1]["org_unit_id"] is None
    assert calls[1][1]["enabled"] is True


@pytest.mark.asyncio
async def test_schedule_manager_resolve_for_device_excludes_disabled() -> None:
    """Test that resolve_for_device excludes disabled schedules."""
    db = MagicMock()
    now = datetime.now(timezone.utc)

    # Only returns enabled schedules
    db.test_schedules.select_list = MagicMock(return_value=[])

    manager = ScheduleManager(db, "tenant-1")
    await manager.initialize()

    device = MagicMock()
    device.id = "device-1"
    device.org_unit_id = "ou-456"

    result = await manager.resolve_for_device(device)

    assert len(result) == 0

    # Verify enabled=True was passed
    calls = db.test_schedules.select_list.call_args_list
    for call in calls:
        assert call[1]["enabled"] is True


@pytest.mark.asyncio
async def test_schedule_manager_tenant_isolation() -> None:
    """Test that schedules from different tenants are isolated."""
    db = MagicMock()
    now = datetime.now(timezone.utc)

    # Manager for tenant-1
    db.test_schedules.select = MagicMock(return_value=None)
    manager1 = ScheduleManager(db, "tenant-1")
    await manager1.initialize()

    # Try to get schedule
    result = await manager1.get_schedule("sched-123")

    assert result is None

    # Verify tenant-1 was used
    call_kwargs = db.test_schedules.select.call_args[1]
    assert call_kwargs["tenant"] == "tenant-1"

    # Reset mock
    db.test_schedules.select.reset_mock()

    # Manager for tenant-2
    manager2 = ScheduleManager(db, "tenant-2")
    await manager2.initialize()

    # Try to get schedule
    result = await manager2.get_schedule("sched-123")

    assert result is None

    # Verify tenant-2 was used (different from tenant-1)
    call_kwargs = db.test_schedules.select.call_args[1]
    assert call_kwargs["tenant"] == "tenant-2"
