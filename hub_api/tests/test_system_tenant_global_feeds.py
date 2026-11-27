"""Global threat feeds live under the reserved ``system`` tenant (s174).

Covers: the scheduler writes only to SYSTEM_TENANT, customer-tenant writes
to SYSTEM_TENANT are refused, the scanner reads global feeds via the same
constant, and no nil-UUID tenant remains.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.sase.security.scanner import scans
from hub_api.modules.threatintel.feeds import FeedSource, SecurityFeedsManager
from hub_api.tenancy import (
    LEGACY_GLOBAL_TENANT,
    SYSTEM_TENANT,
    ReservedTenantWriteError,
    assert_not_system_tenant,
)


def _db() -> MagicMock:
    """Minimal mocked DAL; feed fetchers are patched out per test."""
    db = MagicMock()
    db.feed_updates.async_insert = AsyncMock(return_value="id")
    db.return_value.update = AsyncMock(return_value=None)
    return db


def test_system_tenant_is_reserved_name_not_nil_uuid() -> None:
    """The global feed tenant is the org-reserved ``system`` tenant."""
    assert SYSTEM_TENANT == "system"
    assert scans.GLOBAL_FEED_TENANT == SYSTEM_TENANT
    assert scans.GLOBAL_FEED_TENANT != LEGACY_GLOBAL_TENANT


def test_assert_not_system_tenant() -> None:
    """Customer tenants pass; the reserved tenant is refused."""
    assert_not_system_tenant("tenant-a")
    with pytest.raises(ReservedTenantWriteError):
        assert_not_system_tenant(SYSTEM_TENANT)


@pytest.mark.asyncio
async def test_tenant_cannot_write_global_feed() -> None:
    """Cross-tenant denial: update_feed() targeting the system tenant writes nothing."""
    db = _db()
    manager = SecurityFeedsManager(db)
    with pytest.raises(ReservedTenantWriteError):
        await manager.update_feed(SYSTEM_TENANT, FeedSource.BLACKWEB)
    db.feed_updates.async_insert.assert_not_called()


@pytest.mark.asyncio
async def test_update_global_feed_writes_under_system_tenant() -> None:
    """The global path stores feed bookkeeping with tenant_id=system."""
    db = _db()
    manager = SecurityFeedsManager(db)
    with patch.object(
        manager,
        "_update_blackweb_feed",
        AsyncMock(return_value={"added": 1, "updated": 0, "removed": 0, "errors": 0}),
    ) as fetch:
        await manager.update_global_feed(FeedSource.BLACKWEB)
    fetch.assert_awaited_once_with(SYSTEM_TENANT)
    assert db.feed_updates.async_insert.call_args.kwargs["tenant_id"] == SYSTEM_TENANT


@pytest.mark.asyncio
async def test_tenant_update_feed_stays_in_tenant() -> None:
    """A customer tenant's update writes only under its own tenant id."""
    db = _db()
    manager = SecurityFeedsManager(db)
    with patch.object(
        manager,
        "_update_spamhaus_feed",
        AsyncMock(return_value={"added": 0, "updated": 0, "removed": 0, "errors": 0}),
    ) as fetch:
        await manager.update_feed("tenant-a", FeedSource.SPAMHAUS)
    fetch.assert_awaited_once_with("tenant-a")
    assert db.feed_updates.async_insert.call_args.kwargs["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_scheduler_uses_global_path() -> None:
    """The scheduled loop refreshes via update_global_feed, never a tenant path."""
    manager = SecurityFeedsManager(_db())
    manager.update_global_feed = AsyncMock(side_effect=[None, asyncio.CancelledError()])  # type: ignore[method-assign]
    manager.update_feed = AsyncMock()  # type: ignore[method-assign]
    with patch("hub_api.modules.threatintel.feeds.manager.asyncio.sleep", new_callable=AsyncMock):
        await manager._schedule_feed_updates(FeedSource.BLACKWEB)
    manager.update_global_feed.assert_awaited_with(FeedSource.BLACKWEB)
    manager.update_feed.assert_not_called()
