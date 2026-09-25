"""Tests for usage metering."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.entitlements.metering import Usage, UsageReporter
from hub_api.registry.contract import Entitlement


class MockQueryProxy:
    """Mock query proxy that properly handles async select."""

    def __init__(self, rowset):  # type: ignore[no-untyped-def]
        """Initialize with rowset to return."""
        self.rowset = rowset

    async def select(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        """Async select method."""
        return self.rowset


@pytest.mark.asyncio
async def test_usage_snapshot_counts_seats() -> None:
    """Test that snapshot counts seats from users table."""
    from hub_api.tests.conftest import make_mock_rowset

    # Create mock users rows
    user1 = MagicMock(id="user1", email="user1@example.com")
    user2 = MagicMock(id="user2", email="user2@example.com")
    user3 = MagicMock(id="user3", email="user3@example.com")

    # Create mock db with fresh setup
    mock_rowset = make_mock_rowset([user1, user2, user3])

    # Mock db.users.select() to return the rowset
    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    # Create reporter with patched app context
    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    # Mock the app context to avoid "Not within an app context" error
    with patch("hub_api.entitlements.metering.current_app", create=True):
        usage = await reporter.snapshot()

    # Verify seats count
    assert usage.seats == 3
    assert usage.nodes == 0
    assert isinstance(usage.features, frozenset)


@pytest.mark.asyncio
async def test_usage_snapshot_empty_users() -> None:
    """Test that snapshot returns 0 seats when no users."""
    from hub_api.tests.conftest import make_mock_rowset

    # Mock empty users table
    mock_rowset = make_mock_rowset([])
    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    with patch("hub_api.entitlements.metering.current_app", create=True):
        usage = await reporter.snapshot()

    assert usage.seats == 0
    assert usage.nodes == 0


@pytest.mark.asyncio
async def test_usage_snapshot_with_node_counter(mock_db: MagicMock) -> None:
    """Test that snapshot uses injected node_counter."""
    from unittest.mock import AsyncMock
    from hub_api.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=mock_rowset)
    mock_db.__call__ = MagicMock(return_value=query_proxy)

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
    from unittest.mock import AsyncMock
    from hub_api.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=mock_rowset)
    mock_db.__call__ = MagicMock(return_value=query_proxy)

    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    usage = await reporter.snapshot()

    # Should default to 0 (TODO for Phase 3)
    assert usage.nodes == 0


@pytest.mark.asyncio
async def test_usage_snapshot_handles_db_error(mock_db: MagicMock) -> None:
    """Test that snapshot handles database errors gracefully."""
    from unittest.mock import AsyncMock

    # Mock the query proxy to raise an exception
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(side_effect=Exception("DB connection error"))
    mock_db.__call__ = MagicMock(return_value=query_proxy)

    license_client = MagicMock()
    reporter = UsageReporter(mock_db, license_client)

    # Should not raise; should return 0 seats on error
    usage = await reporter.snapshot()

    assert usage.seats == 0
    assert usage.nodes == 0


@pytest.mark.asyncio
async def test_report_success() -> None:
    """Test that report sends usage successfully."""
    from hub_api.tests.conftest import make_mock_rowset

    user1 = MagicMock(id="user1")
    mock_rowset = make_mock_rowset([user1])
    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    license_client.keepalive = MagicMock()

    reporter = UsageReporter(mock_db, license_client)

    with patch("hub_api.entitlements.metering.current_app", create=True):
        result = await reporter.report()

    assert result is True
    license_client.keepalive.assert_called_once()
    call_args = license_client.keepalive.call_args[0][0]
    assert call_args["seats"] == 1
    assert call_args["nodes"] == 0


@pytest.mark.asyncio
async def test_report_license_client_error(mock_db: MagicMock) -> None:
    """Test that report swallows license client exceptions."""
    from unittest.mock import AsyncMock
    from hub_api.tests.conftest import make_mock_rowset

    user1 = MagicMock(id="user1")
    mock_rowset = make_mock_rowset([user1])
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=mock_rowset)
    mock_db.__call__ = MagicMock(return_value=query_proxy)

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
    from unittest.mock import AsyncMock
    from hub_api.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=mock_rowset)
    mock_db.__call__ = MagicMock(return_value=query_proxy)

    reporter = UsageReporter(mock_db, None)

    result = await reporter.report()

    assert result is False


@pytest.mark.asyncio
async def test_report_caches_snapshot_fallback() -> None:
    """Test that snapshot caches result for use as fallback on complete failure."""
    from hub_api.tests.conftest import make_mock_rowset

    user1 = MagicMock(id="user1")
    mock_rowset = make_mock_rowset([user1])
    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    license_client = MagicMock()
    license_client.keepalive = MagicMock()

    reporter = UsageReporter(mock_db, license_client)

    # First snapshot caches the result
    with patch("hub_api.entitlements.metering.current_app", create=True):
        usage1 = await reporter.snapshot()
    assert usage1.seats == 1
    assert reporter._last_snapshot is not None

    # Verify cache was stored
    assert reporter._last_snapshot.seats == 1


@pytest.mark.asyncio
async def test_seat_counter_from_users_table() -> None:
    """Test seat counter queries users table for distinct active identities."""
    from hub_api.entitlements.metering import count_active_seats
    from hub_api.tests.conftest import make_mock_rowset

    # Create mock user rows (distinct identities)
    user1 = MagicMock(id="uuid-1")
    user2 = MagicMock(id="uuid-2")
    user3 = MagicMock(id="uuid-3")

    mock_rowset = make_mock_rowset([user1, user2, user3])
    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.select = MagicMock(return_value=mock_rowset)

    # Call the seat counter
    seats = await count_active_seats(mock_db)

    assert seats == 3


@pytest.mark.asyncio
async def test_node_counter_from_clusters_table() -> None:
    """Test node counter queries clusters table for registered orchestrators."""
    from hub_api.entitlements.metering import count_registered_nodes
    from hub_api.tests.conftest import make_mock_rowset

    # Create mock cluster rows (registered nodes/orchestrators)
    cluster1 = MagicMock(id="cluster-1", name="hub-1")
    cluster2 = MagicMock(id="cluster-2", name="hub-2")

    mock_rowset = make_mock_rowset([cluster1, cluster2])
    mock_db = MagicMock()
    mock_db.clusters = MagicMock()
    mock_db.clusters.select = MagicMock(return_value=mock_rowset)

    # Call the node counter (sync version for backward compat with node_counter callable)
    nodes = count_registered_nodes(mock_db)

    assert nodes == 2


@pytest.mark.asyncio
async def test_node_counter_empty_clusters() -> None:
    """Test node counter returns 0 when no clusters registered."""
    from hub_api.entitlements.metering import count_registered_nodes
    from hub_api.tests.conftest import make_mock_rowset

    mock_rowset = make_mock_rowset([])
    mock_db = MagicMock()
    mock_db.clusters = MagicMock()
    mock_db.clusters.select = MagicMock(return_value=mock_rowset)

    nodes = count_registered_nodes(mock_db)

    assert nodes == 0
