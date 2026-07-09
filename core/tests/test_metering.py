"""Tests for usage metering."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from core.entitlements.metering import Usage, UsageReporter
from core.registry.contract import Entitlement


@pytest.mark.asyncio
async def test_usage_snapshot_counts_seats(mock_db: MagicMock) -> None:
    """Test that snapshot counts seats from users table."""
    # Create mock users rows
    user1 = MagicMock(id="user1", email="user1@example.com")
    user2 = MagicMock(id="user2", email="user2@example.com")
    user3 = MagicMock(id="user3", email="user3@example.com")

    # Mock the users table select to return the users
    from core.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([user1, user2, user3])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    # Create reporter
    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    # Get snapshot
    usage = await reporter.snapshot()

    # Verify seats count
    assert usage.seats == 3
    assert usage.nodes == 0
    assert isinstance(usage.features, frozenset)


@pytest.mark.asyncio
async def test_usage_snapshot_empty_users(mock_db: MagicMock) -> None:
    """Test that snapshot returns 0 seats when no users."""
    # Mock empty users table
    from core.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    usage = await reporter.snapshot()

    assert usage.seats == 0
    assert usage.nodes == 0


@pytest.mark.asyncio
async def test_usage_snapshot_with_node_counter(mock_db: MagicMock) -> None:
    """Test that snapshot uses injected node_counter."""
    from core.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()

    # Provide a node counter that returns 5
    def node_counter() -> int:
        return 5

    reporter = UsageReporter(mock_db, license_client, node_counter=node_counter)

    usage = await reporter.snapshot()

    assert usage.nodes == 5


@pytest.mark.asyncio
async def test_usage_snapshot_default_node_counter(mock_db: MagicMock) -> None:
    """Test that snapshot defaults to 0 nodes without node_counter."""
    from core.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    usage = await reporter.snapshot()

    # Should default to 0 (TODO for Phase 3)
    assert usage.nodes == 0


@pytest.mark.asyncio
async def test_usage_snapshot_handles_db_error(mock_db: MagicMock) -> None:
    """Test that snapshot handles database errors gracefully."""
    # Mock the users table to raise an exception
    mock_db.users.select = MagicMock(side_effect=Exception("DB connection error"))

    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    # Should not raise; should return 0 seats on error
    usage = await reporter.snapshot()

    assert usage.seats == 0
    assert usage.nodes == 0


@pytest.mark.asyncio
async def test_report_success(mock_db: MagicMock) -> None:
    """Test that report sends usage successfully."""
    from core.tests.conftest import make_mock_rowset

    user1 = MagicMock(id="user1")
    mock_rowset = make_mock_rowset([user1])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    license_client.keepalive = MagicMock()

    reporter = UsageReporter(mock_db, license_client)

    result = await reporter.report()

    assert result is True
    license_client.keepalive.assert_called_once()
    call_args = license_client.keepalive.call_args[0][0]
    assert call_args["seats"] == 1
    assert call_args["nodes"] == 0


@pytest.mark.asyncio
async def test_report_license_client_error(mock_db: MagicMock) -> None:
    """Test that report swallows license client exceptions."""
    from core.tests.conftest import make_mock_rowset

    user1 = MagicMock(id="user1")
    mock_rowset = make_mock_rowset([user1])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    license_client.keepalive = MagicMock(
        side_effect=Exception("License server unreachable")
    )

    reporter = UsageReporter(mock_db, license_client)

    # Should not raise; should return False
    result = await reporter.report()

    assert result is False


@pytest.mark.asyncio
async def test_report_no_license_client(mock_db: MagicMock) -> None:
    """Test that report handles None license client."""
    from core.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    reporter = UsageReporter(mock_db, None)

    result = await reporter.report()

    assert result is False


@pytest.mark.asyncio
async def test_report_caches_snapshot_fallback(mock_db: MagicMock) -> None:
    """Test that snapshot caches result for use as fallback on complete failure."""
    from core.tests.conftest import make_mock_rowset

    user1 = MagicMock(id="user1")
    mock_rowset = make_mock_rowset([user1])
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    license_client.keepalive = MagicMock()

    reporter = UsageReporter(mock_db, license_client)

    # First snapshot caches the result
    usage1 = await reporter.snapshot()
    assert usage1.seats == 1
    assert reporter._last_snapshot is not None

    # Verify cache was stored
    assert reporter._last_snapshot.seats == 1
