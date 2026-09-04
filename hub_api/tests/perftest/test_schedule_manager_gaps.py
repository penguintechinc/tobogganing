"""Coverage backfill for perftest_client/services/schedule_manager.py.

test_wpcl_schedule_manager.py covers create_schedule; this file targets the
remaining lifecycle/list/update/delete/resolve_for_device gaps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_client.services.schedule_manager import ScheduleManager


@dataclass(slots=True)
class _FakeDevice:
    """Minimal device stand-in with the attributes resolve_for_device() reads."""

    id: str
    org_unit_id: str | None


@pytest.mark.asyncio
async def test_initialize_and_shutdown(real_dal: AsyncDB) -> None:
    """initialize()/shutdown() succeed without raising."""
    mgr = ScheduleManager(real_dal, "tenant-lifecycle")
    await mgr.initialize()
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_get_schedule_not_found(real_dal: AsyncDB) -> None:
    """get_schedule() returns None for an unknown id."""
    mgr = ScheduleManager(real_dal, "tenant-x")
    result = await mgr.get_schedule("ghost")
    assert result is None


@pytest.mark.asyncio
async def test_list_schedules_with_org_unit_filter(real_dal: AsyncDB) -> None:
    """list_schedules() filters by org_unit_id when provided."""
    tenant = "tenant-list"
    mgr = ScheduleManager(real_dal, tenant)

    await mgr.create_schedule(
        {"org_unit_id": "ou-1", "test_type": "http", "target": "a", "interval_seconds": 60}
    )
    await mgr.create_schedule(
        {"org_unit_id": "ou-2", "test_type": "tcp", "target": "b", "interval_seconds": 60}
    )
    await mgr.create_schedule(
        {"org_unit_id": None, "test_type": "icmp", "target": "c", "interval_seconds": 60}
    )

    all_schedules = await mgr.list_schedules()
    assert len(all_schedules) == 3

    ou1_only = await mgr.list_schedules(org_unit_id="ou-1")
    assert len(ou1_only) == 1
    assert ou1_only[0].target == "a"


@pytest.mark.asyncio
async def test_update_schedule_not_found(real_dal: AsyncDB) -> None:
    """update_schedule() returns None for an unknown id."""
    mgr = ScheduleManager(real_dal, "tenant-x")
    result = await mgr.update_schedule("ghost", {"enabled": False})
    assert result is None


@pytest.mark.asyncio
async def test_update_schedule_success(real_dal: AsyncDB) -> None:
    """update_schedule() applies allowed fields and refreshes updated_at."""
    tenant = "tenant-update"
    mgr = ScheduleManager(real_dal, tenant)
    created = await mgr.create_schedule(
        {"test_type": "http", "target": "orig", "interval_seconds": 60}
    )

    updated = await mgr.update_schedule(
        created.id, {"target": "changed", "interval_seconds": 120, "enabled": False}
    )
    assert updated is not None
    assert updated.target == "changed"
    assert updated.interval_seconds == 120
    assert updated.enabled is False


@pytest.mark.asyncio
async def test_delete_schedule_not_found_and_success(real_dal: AsyncDB) -> None:
    """delete_schedule() returns False for unknown id, True + removes on success."""
    tenant = "tenant-delete"
    mgr = ScheduleManager(real_dal, tenant)

    assert await mgr.delete_schedule("ghost") is False

    created = await mgr.create_schedule(
        {"test_type": "http", "target": "x", "interval_seconds": 60}
    )
    assert await mgr.delete_schedule(created.id) is True
    assert await mgr.get_schedule(created.id) is None


@pytest.mark.asyncio
async def test_resolve_for_device_dedup_and_scope(real_dal: AsyncDB) -> None:
    """resolve_for_device() merges org-unit-specific and tenant-wide schedules, deduped."""
    tenant = "tenant-resolve"
    mgr = ScheduleManager(real_dal, tenant)

    # OU-specific schedule for ou-1.
    ou_schedule = await mgr.create_schedule(
        {"org_unit_id": "ou-1", "test_type": "http", "target": "ou-target", "interval_seconds": 60}
    )
    # Tenant-wide schedule (applies to all devices).
    wide_schedule = await mgr.create_schedule(
        {"org_unit_id": None, "test_type": "icmp", "target": "wide-target", "interval_seconds": 60}
    )
    # Disabled schedule for ou-1 (must be excluded).
    disabled = await mgr.create_schedule(
        {
            "org_unit_id": "ou-1",
            "test_type": "tcp",
            "target": "disabled",
            "interval_seconds": 60,
            "enabled": False,
        }
    )
    # Schedule for a different OU (must be excluded for our device).
    await mgr.create_schedule(
        {"org_unit_id": "ou-2", "test_type": "udp", "target": "other-ou", "interval_seconds": 60}
    )

    device = _FakeDevice(id="dev-1", org_unit_id="ou-1")
    resolved = await mgr.resolve_for_device(device)

    resolved_ids = {s.id for s in resolved}
    assert ou_schedule.id in resolved_ids
    assert wide_schedule.id in resolved_ids
    assert disabled.id not in resolved_ids
    assert len(resolved) == 2  # deduped, no double count


@pytest.mark.asyncio
async def test_resolve_for_device_no_org_unit(real_dal: AsyncDB) -> None:
    """A device with no org_unit_id only picks up tenant-wide schedules."""
    tenant = "tenant-resolve-none"
    mgr = ScheduleManager(real_dal, tenant)

    wide = await mgr.create_schedule(
        {"org_unit_id": None, "test_type": "icmp", "target": "wide", "interval_seconds": 60}
    )
    await mgr.create_schedule(
        {"org_unit_id": "ou-1", "test_type": "http", "target": "scoped", "interval_seconds": 60}
    )

    device = _FakeDevice(id="dev-2", org_unit_id=None)
    resolved = await mgr.resolve_for_device(device)
    assert len(resolved) == 1
    assert resolved[0].id == wide.id
