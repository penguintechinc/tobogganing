"""Edge-case coverage for PortConfigManager not covered by test_sdwan_ports.py.

Covers falsy/empty rowset branches, overlap rejection through add_port_range,
and every except-block (fail-closed) path.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hub_api.modules.sdwan.network.port_manager import (
    HeadendPortConfig,
    PortConfigManager,
    PortProtocol,
    PortRangeConfig,
)
from hub_api.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_port_db() -> MagicMock:
    """Create a mock DAL with port_ranges table support.

    Returns:
        Mock database object with port_ranges table.
    """
    db = MagicMock()
    port_ranges_table = MagicMock()
    port_ranges_table.async_insert = AsyncMock(return_value=1)

    def make_query_proxy() -> MagicMock:
        query_proxy = MagicMock()
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
        query_proxy.count = AsyncMock(return_value=0)
        query_proxy.update = AsyncMock(return_value=None)
        query_proxy.delete = AsyncMock(return_value=None)
        query_proxy.__and__ = MagicMock(return_value=query_proxy)
        query_proxy.__or__ = MagicMock(return_value=query_proxy)
        return query_proxy

    query_proxy = make_query_proxy()
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy
    db.port_ranges = port_ranges_table

    return db


def _falsy_rowset() -> MagicMock:
    """Build a MagicMock rowset that is falsy (bool() is False).

    Returns:
        A MagicMock configured so `not rowset` evaluates True.
    """
    rowset = MagicMock()
    rowset.__bool__ = MagicMock(return_value=False)
    rowset.__len__ = MagicMock(return_value=0)
    rowset.__iter__ = MagicMock(side_effect=lambda: iter([]))
    return rowset


# --- get_headend_config -------------------------------------------------------


@pytest.mark.asyncio
async def test_get_headend_config_falsy_rowset_returns_none(
    mock_port_db: MagicMock,
) -> None:
    """A genuinely falsy rowset short-circuits to None."""
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(return_value=_falsy_rowset())
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    config = await manager.get_headend_config("headend-1", "tenant-1")

    assert config is None


@pytest.mark.asyncio
async def test_get_headend_config_truthy_empty_rowset_returns_none(
    mock_port_db: MagicMock,
) -> None:
    """A truthy-but-empty rowset iterates zero times, leaving cluster_id None."""
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    config = await manager.get_headend_config("headend-1", "tenant-1")

    assert config is None


@pytest.mark.asyncio
async def test_get_headend_config_exception_returns_none(
    mock_port_db: MagicMock,
) -> None:
    """get_headend_config fails closed (None) on DB error."""
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    config = await manager.get_headend_config("headend-1", "tenant-1")

    assert config is None


# --- get_cluster_config -------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cluster_config_exception_returns_empty(
    mock_port_db: MagicMock,
) -> None:
    """get_cluster_config fails closed (empty dict) on DB error."""
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    configs = await manager.get_cluster_config("cluster-1", "tenant-1")

    assert configs == {}


# --- add_port_range: overlap rejection + exception ---------------------------


@pytest.mark.asyncio
async def test_add_port_range_overlap_rejected(mock_port_db: MagicMock) -> None:
    """add_port_range returns None when _has_port_overlap reports a conflict."""
    manager = PortConfigManager(mock_port_db)
    manager._has_port_overlap = AsyncMock(return_value=True)  # type: ignore[method-assign]

    port_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=8443,
        end_port=8443,
        protocol=PortProtocol.TCP,
    )

    result = await manager.add_port_range("headend-1", "cluster-1", "test-tenant", port_range)

    assert result is None
    mock_port_db.port_ranges.async_insert.assert_not_called()


@pytest.mark.asyncio
async def test_add_port_range_exception_returns_none(mock_port_db: MagicMock) -> None:
    """add_port_range fails closed (None) if the insert raises."""
    mock_port_db.port_ranges.async_insert = AsyncMock(side_effect=RuntimeError("db error"))
    manager = PortConfigManager(mock_port_db)

    port_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=8443,
        end_port=8443,
        protocol=PortProtocol.TCP,
    )

    result = await manager.add_port_range("headend-1", "cluster-1", "test-tenant", port_range)

    assert result is None


# --- remove_port_range: exception ---------------------------------------------


@pytest.mark.asyncio
async def test_remove_port_range_exception_returns_false(
    mock_port_db: MagicMock,
) -> None:
    """remove_port_range fails closed (False) on DB error."""
    query_proxy = mock_port_db()
    query_proxy.delete = AsyncMock(side_effect=RuntimeError("db error"))

    manager = PortConfigManager(mock_port_db)
    result = await manager.remove_port_range("range-1", "tenant-1")

    assert result is False


# --- update_port_range: no valid fields + exception ---------------------------


@pytest.mark.asyncio
async def test_update_port_range_no_valid_fields_returns_false(
    mock_port_db: MagicMock,
) -> None:
    """update_port_range returns False when no recognized fields are passed."""
    manager = PortConfigManager(mock_port_db)

    result = await manager.update_port_range("range-1", "tenant-1", unrelated_field="ignored")

    assert result is False


@pytest.mark.asyncio
async def test_update_port_range_exception_returns_false(
    mock_port_db: MagicMock,
) -> None:
    """update_port_range fails closed (False) on DB error."""
    query_proxy = mock_port_db()
    query_proxy.update = AsyncMock(side_effect=RuntimeError("db error"))

    manager = PortConfigManager(mock_port_db)
    result = await manager.update_port_range("range-1", "tenant-1", enabled=False)

    assert result is False


# --- get_all_configs: exception -----------------------------------------------


@pytest.mark.asyncio
async def test_get_all_configs_exception_returns_empty(
    mock_port_db: MagicMock,
) -> None:
    """get_all_configs fails closed (empty dict) on DB error."""
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    configs = await manager.get_all_configs("tenant-1")

    assert configs == {}


# --- set_default_config: partial failure warning + exception -----------------


@pytest.mark.asyncio
async def test_set_default_config_logs_warning_on_partial_failure(
    mock_port_db: MagicMock,
) -> None:
    """set_default_config still returns True even if individual ranges fail to add."""
    manager = PortConfigManager(mock_port_db)
    manager.add_port_range = AsyncMock(return_value=None)  # type: ignore[method-assign]

    result = await manager.set_default_config("headend-1", "cluster-1", "test-tenant")

    assert result is True
    assert manager.add_port_range.await_count == 6


@pytest.mark.asyncio
async def test_set_default_config_exception_returns_false(
    mock_port_db: MagicMock,
) -> None:
    """set_default_config fails closed (False) if an unexpected error occurs."""
    manager = PortConfigManager(mock_port_db)
    manager.add_port_range = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    result = await manager.set_default_config("headend-1", "cluster-1", "test-tenant")

    assert result is False


# --- _has_port_overlap: exception ---------------------------------------------


@pytest.mark.asyncio
async def test_has_port_overlap_exception_returns_false(
    mock_port_db: MagicMock,
) -> None:
    """_has_port_overlap fails closed (False) on DB error."""
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    mock_port_db.return_value = query_proxy

    new_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=9000,
        end_port=9100,
        protocol=PortProtocol.TCP,
    )

    manager = PortConfigManager(mock_port_db)
    overlap = await manager._has_port_overlap("headend-1", "test-tenant", new_range)

    assert overlap is False
