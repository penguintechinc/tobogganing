"""Edge-case tests for SecurityFeedsManager orchestration paths.

Complements tests/test_sase_feeds.py::TestFeedUpdate with the untested
start/stop lifecycle, the update_feed() dispatcher + failure recording,
the Spamhaus/IPVoid/DNSBL feed updaters, and _store_indicator()'s error
path.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.threatintel.feeds import (
    FeedSource,
    SecurityFeedsManager,
    ThreatType,
    build_threat_indicator,
)


@pytest.fixture
def mock_db() -> MagicMock:
    """Mocked penguin-dal instance (mirrors tests/test_sase_feeds.py::mock_db)."""
    db = MagicMock()

    db.threat_indicators = MagicMock()
    db.feed_updates = MagicMock()
    db.threat_detections = MagicMock()

    async def mock_insert(*_args: object, **_kwargs: object) -> str:
        return "id-123"

    async def mock_update(*_args: object, **_kwargs: object) -> None:
        return None

    db.threat_indicators.async_insert = AsyncMock(side_effect=mock_insert)
    db.feed_updates.async_insert = AsyncMock(side_effect=mock_insert)
    db.threat_detections.async_insert = AsyncMock(side_effect=mock_insert)

    def query_mock(*_args: object, **_kwargs: object) -> MagicMock:
        query_obj = MagicMock()
        query_obj.select = AsyncMock(return_value=[])
        query_obj.count = AsyncMock(return_value=0)
        query_obj.update = AsyncMock(side_effect=mock_update)
        return query_obj

    db.side_effect = query_mock
    db.return_value.select = AsyncMock(return_value=[])
    db.return_value.count = AsyncMock(return_value=0)
    db.return_value.update = AsyncMock(side_effect=mock_update)

    return db


@pytest.mark.asyncio
async def test_start_feed_updates_schedules_every_source(mock_db: MagicMock) -> None:
    """start_feed_updates() creates a scheduling task per FeedSource and gathers them."""
    manager = SecurityFeedsManager(mock_db)
    manager._schedule_feed_updates = AsyncMock()

    await manager.start_feed_updates()

    assert manager._schedule_feed_updates.call_count == len(FeedSource)
    await manager.stop_feed_updates()


@pytest.mark.asyncio
async def test_stop_feed_updates_closes_open_session(mock_db: MagicMock) -> None:
    """stop_feed_updates() closes the aiohttp session and clears the reference."""
    manager = SecurityFeedsManager(mock_db)
    mock_session = AsyncMock()
    manager.session = mock_session

    await manager.stop_feed_updates()

    mock_session.close.assert_called_once()
    assert manager.session is None


@pytest.mark.asyncio
async def test_stop_feed_updates_noop_when_no_session(mock_db: MagicMock) -> None:
    """stop_feed_updates() is a no-op when no session was ever created."""
    manager = SecurityFeedsManager(mock_db)
    assert manager.session is None

    await manager.stop_feed_updates()  # Must not raise

    assert manager.session is None


@pytest.mark.asyncio
async def test_schedule_feed_updates_returns_immediately_for_unconfigured_source(
    mock_db: MagicMock,
) -> None:
    """_schedule_feed_updates() returns immediately if the source has no feed_configs entry."""
    manager = SecurityFeedsManager(mock_db)

    # FeedSource.MISP is a valid enum member but has no entry in feed_configs
    # (only used for user-configured FeedSourceManager ingestion).
    result = await manager._schedule_feed_updates(FeedSource.MISP)

    assert result is None


@pytest.mark.asyncio
async def test_schedule_feed_updates_loop_success_then_error_then_cancelled(
    mock_db: MagicMock,
) -> None:
    """_schedule_feed_updates() sleeps after success, retries after error, breaks on cancel."""
    manager = SecurityFeedsManager(mock_db)
    manager.update_feed = AsyncMock(
        side_effect=[None, RuntimeError("transient failure"), asyncio.CancelledError()]
    )

    with patch(
        "hub_api.modules.threatintel.feeds.manager.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:
        await manager._schedule_feed_updates(FeedSource.BLACKWEB)

    assert manager.update_feed.call_count == 3
    # Normal interval sleep after success, then error-path sleep(300)
    mock_sleep.assert_any_call(300)


@pytest.mark.asyncio
async def test_update_feed_dispatches_to_blackweb_and_completes(mock_db: MagicMock) -> None:
    """update_feed() dispatches to _update_blackweb_feed and marks the run completed."""
    manager = SecurityFeedsManager(mock_db)
    manager._update_blackweb_feed = AsyncMock(
        return_value={"added": 2, "updated": 0, "removed": 0, "errors": 0}
    )

    stats = await manager.update_feed("tenant-1", FeedSource.BLACKWEB)

    assert stats["added"] == 2
    mock_db.feed_updates.async_insert.assert_called_once()


@pytest.mark.asyncio
async def test_update_feed_dispatches_to_spamhaus(mock_db: MagicMock) -> None:
    """update_feed() dispatches FeedSource.SPAMHAUS to _update_spamhaus_feed."""
    manager = SecurityFeedsManager(mock_db)
    manager._update_spamhaus_feed = AsyncMock(
        return_value={"added": 1, "updated": 0, "removed": 0, "errors": 0}
    )

    stats = await manager.update_feed("tenant-1", FeedSource.SPAMHAUS)

    assert stats["added"] == 1


@pytest.mark.asyncio
async def test_update_feed_dispatches_to_ipvoid_and_dnsbl(mock_db: MagicMock) -> None:
    """update_feed() dispatches IPVOID and DNSBL to their real-time-only handlers."""
    manager = SecurityFeedsManager(mock_db)

    ipvoid_stats = await manager.update_feed("tenant-1", FeedSource.IPVOID)
    dnsbl_stats = await manager.update_feed("tenant-1", FeedSource.DNSBL)

    assert ipvoid_stats == {"added": 0, "updated": 0, "removed": 0, "errors": 0}
    assert dnsbl_stats == {"added": 0, "updated": 0, "removed": 0, "errors": 0}


@pytest.mark.asyncio
async def test_update_feed_exception_records_failed_status(mock_db: MagicMock) -> None:
    """update_feed() catches errors from the dispatched updater and records status=failed."""
    manager = SecurityFeedsManager(mock_db)
    manager._update_blackweb_feed = AsyncMock(side_effect=RuntimeError("boom"))

    stats = await manager.update_feed("tenant-1", FeedSource.BLACKWEB)

    assert stats["errors"] == 1


@pytest.mark.asyncio
async def test_update_feed_exception_swallows_secondary_update_failure(
    mock_db: MagicMock,
) -> None:
    """update_feed()'s failure-recording update is itself best-effort (nested except: pass)."""
    manager = SecurityFeedsManager(mock_db)
    manager._update_blackweb_feed = AsyncMock(side_effect=RuntimeError("boom"))
    mock_db.return_value.update = AsyncMock(side_effect=RuntimeError("update also failed"))

    stats = await manager.update_feed("tenant-1", FeedSource.BLACKWEB)  # Must not raise

    assert stats["errors"] == 1


@pytest.mark.asyncio
async def test_update_blackweb_feed_success_adds_domains_and_ips(
    mock_db: MagicMock,
) -> None:
    """_update_blackweb_feed() stores every fetched domain and IP as an indicator."""
    manager = SecurityFeedsManager(mock_db)

    with (
        patch(
            "hub_api.modules.threatintel.feeds.manager.fetch_blackweb_domains",
            new_callable=AsyncMock,
            return_value=["evil.example.com"],
        ),
        patch(
            "hub_api.modules.threatintel.feeds.manager.fetch_blackweb_ips",
            new_callable=AsyncMock,
            return_value=["198.51.100.7"],
        ),
    ):
        stats = await manager._update_blackweb_feed("tenant-1")

    await manager.stop_feed_updates()  # Close the real aiohttp session opened above

    assert stats["added"] == 2
    assert stats["errors"] == 0


@pytest.mark.asyncio
async def test_update_spamhaus_feed_success_adds_both_lists(mock_db: MagicMock) -> None:
    """_update_spamhaus_feed() processes both DROP and EDROP lists on success."""
    manager = SecurityFeedsManager(mock_db)

    with patch(
        "hub_api.modules.threatintel.feeds.manager.fetch_spamhaus_drop",
        new_callable=AsyncMock,
        return_value=["2.4.6.0/24"],
    ):
        stats = await manager._update_spamhaus_feed("tenant-1")

    await manager.stop_feed_updates()  # Close the real aiohttp session opened above

    assert stats["added"] == 2  # one network from DROP, one from EDROP
    assert stats["errors"] == 0


@pytest.mark.asyncio
async def test_update_spamhaus_feed_failure_increments_errors_per_list(
    mock_db: MagicMock,
) -> None:
    """_update_spamhaus_feed() preserves existing indicators and counts errors on fetch failure."""
    manager = SecurityFeedsManager(mock_db)

    with patch(
        "hub_api.modules.threatintel.feeds.manager.fetch_spamhaus_drop",
        new_callable=AsyncMock,
        side_effect=RuntimeError("timeout"),
    ):
        stats = await manager._update_spamhaus_feed("tenant-1")

    await manager.stop_feed_updates()  # Close the real aiohttp session opened above

    assert stats["errors"] == 2  # DROP and EDROP both failed
    assert stats["added"] == 0


@pytest.mark.asyncio
async def test_store_indicator_exception_returns_false(mock_db: MagicMock) -> None:
    """_store_indicator() returns False (not raise) when the DAL call errors."""
    manager = SecurityFeedsManager(mock_db)
    mock_db.side_effect = RuntimeError("db unavailable")

    indicator = build_threat_indicator(
        indicator_type="domain",
        value="err.example.com",
        threat_types=[ThreatType.MALWARE_DOMAIN],
        source=FeedSource.BLACKWEB,
        confidence=80,
        ttl=3600,
    )

    result = await manager._store_indicator("tenant-1", indicator)

    assert result is False


@pytest.mark.asyncio
async def test_store_indicator_updates_existing(mock_db: MagicMock) -> None:
    """_store_indicator() returns False and updates when the indicator already exists."""
    manager = SecurityFeedsManager(mock_db)

    update_mock = AsyncMock()

    def existing_query_mock(*_args: object, **_kwargs: object) -> MagicMock:
        query_obj = MagicMock()
        query_obj.select = AsyncMock(return_value=[{"value": "seen.example.com"}])
        query_obj.update = update_mock
        return query_obj

    mock_db.side_effect = existing_query_mock

    indicator = build_threat_indicator(
        indicator_type="domain",
        value="seen.example.com",
        threat_types=[ThreatType.MALWARE_DOMAIN],
        source=FeedSource.BLACKWEB,
        confidence=80,
        ttl=3600,
    )

    result = await manager._store_indicator("tenant-1", indicator)

    assert result is False
    update_mock.assert_called_once()
