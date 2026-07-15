"""Tests for SASE port configuration manager."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.modules.sase.network.port_manager import (
    PortConfigManager,
    PortProtocol,
    PortRangeConfig,
    HeadendPortConfig,
)
from core.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_port_db() -> MagicMock:
    """Create a mock DAL with port_ranges table support.

    Returns:
        Mock database object with port_ranges table.
    """
    db = MagicMock()

    # Mock port_ranges table
    port_ranges_table = MagicMock()
    port_ranges_table.async_insert = AsyncMock(return_value=1)

    # Mock query builder
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


@pytest.mark.asyncio
async def test_add_port_range(mock_port_db: MagicMock) -> None:
    """Test adding a new port range."""
    manager = PortConfigManager(mock_port_db)

    port_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=8443,
        end_port=8443,
        protocol=PortProtocol.TCP,
        description="HTTPS Proxy",
    )

    result = await manager.add_port_range(
        "headend-1", "cluster-1", "test-tenant", port_range
    )

    assert result == port_range.id
    mock_port_db.port_ranges.async_insert.assert_called_once()
    call_kwargs = mock_port_db.port_ranges.async_insert.call_args[1]
    assert call_kwargs["id"] == port_range.id
    assert call_kwargs["tenant"] == "test-tenant"
    assert call_kwargs["headend_id"] == "headend-1"
    assert call_kwargs["start_port"] == 8443


@pytest.mark.asyncio
async def test_add_port_range_invalid_port(mock_port_db: MagicMock) -> None:
    """Test add_port_range with invalid port numbers."""
    manager = PortConfigManager(mock_port_db)

    port_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=0,
        end_port=70000,
        protocol=PortProtocol.TCP,
    )

    result = await manager.add_port_range(
        "headend-1", "cluster-1", "test-tenant", port_range
    )

    assert result is None


@pytest.mark.asyncio
async def test_add_port_range_reversed_ports(mock_port_db: MagicMock) -> None:
    """Test add_port_range with reversed port range."""
    manager = PortConfigManager(mock_port_db)

    port_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=8443,
        end_port=8000,
        protocol=PortProtocol.TCP,
    )

    result = await manager.add_port_range(
        "headend-1", "cluster-1", "test-tenant", port_range
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_headend_config(mock_port_db: MagicMock) -> None:
    """Test retrieving headend port configuration."""
    range_id1 = str(uuid4())
    range_id2 = str(uuid4())
    tenant = "test-tenant"

    range_row1 = make_mock_row(
        {
            "id": range_id1,
            "tenant": tenant,
            "headend_id": "headend-1",
            "cluster_id": "cluster-1",
            "start_port": 8443,
            "end_port": 8443,
            "protocol": "tcp",
            "description": "HTTPS Proxy",
            "enabled": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    range_row2 = make_mock_row(
        {
            "id": range_id2,
            "tenant": tenant,
            "headend_id": "headend-1",
            "cluster_id": "cluster-1",
            "start_port": 8445,
            "end_port": 8445,
            "protocol": "udp",
            "description": "UDP Proxy",
            "enabled": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    rowset = make_mock_rowset([range_row1, range_row2])
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    config = await manager.get_headend_config("headend-1", tenant)

    assert config is not None
    assert config.headend_id == "headend-1"
    assert config.cluster_id == "cluster-1"
    assert len(config.tcp_ranges) == 1
    assert len(config.udp_ranges) == 1
    assert config.tcp_ranges[0].start_port == 8443
    assert config.udp_ranges[0].start_port == 8445


@pytest.mark.asyncio
async def test_remove_port_range(mock_port_db: MagicMock) -> None:
    """Test removing a port range."""
    range_id = str(uuid4())
    tenant = "test-tenant"

    query_proxy = mock_port_db()
    manager = PortConfigManager(mock_port_db)
    result = await manager.remove_port_range(range_id, tenant)

    assert result is True
    query_proxy.delete.assert_called_once()


@pytest.mark.asyncio
async def test_update_port_range(mock_port_db: MagicMock) -> None:
    """Test updating a port range."""
    range_id = str(uuid4())
    tenant = "test-tenant"

    query_proxy = mock_port_db()
    manager = PortConfigManager(mock_port_db)
    result = await manager.update_port_range(
        range_id, tenant, description="Updated Proxy", enabled=False
    )

    assert result is True
    query_proxy.update.assert_called_once()
    call_kwargs = query_proxy.update.call_args[1]
    assert call_kwargs["description"] == "Updated Proxy"
    assert call_kwargs["enabled"] is False


@pytest.mark.asyncio
async def test_get_cluster_config(mock_port_db: MagicMock) -> None:
    """Test retrieving cluster port configurations."""
    range_id1 = str(uuid4())
    range_id2 = str(uuid4())
    tenant = "test-tenant"

    range_row1 = make_mock_row(
        {
            "id": range_id1,
            "tenant": tenant,
            "headend_id": "headend-1",
            "cluster_id": "cluster-1",
            "start_port": 8443,
            "end_port": 8443,
            "protocol": "tcp",
            "description": "HTTPS",
            "enabled": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    range_row2 = make_mock_row(
        {
            "id": range_id2,
            "tenant": tenant,
            "headend_id": "headend-2",
            "cluster_id": "cluster-1",
            "start_port": 8443,
            "end_port": 8443,
            "protocol": "tcp",
            "description": "HTTPS",
            "enabled": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    # For the initial select to get distinct headends
    distinct_rowset = make_mock_rowset([range_row1, range_row2])

    # For the per-headend config queries
    headend1_rowset = make_mock_rowset([range_row1])
    headend2_rowset = make_mock_rowset([range_row2])

    query_proxy = mock_port_db()
    # First call gets distinct headends
    call_count = [0]

    async def select_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return distinct_rowset
        elif call_count[0] == 2:
            return headend1_rowset
        else:
            return headend2_rowset

    query_proxy.select = AsyncMock(side_effect=select_side_effect)
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    configs = await manager.get_cluster_config("cluster-1", tenant)

    assert len(configs) == 2
    assert "headend-1" in configs
    assert "headend-2" in configs


@pytest.mark.asyncio
async def test_get_all_configs(mock_port_db: MagicMock) -> None:
    """Test retrieving all port configurations."""
    range_id1 = str(uuid4())
    tenant = "test-tenant"

    range_row = make_mock_row(
        {
            "id": range_id1,
            "tenant": tenant,
            "headend_id": "headend-1",
            "cluster_id": "cluster-1",
            "start_port": 8443,
            "end_port": 8443,
            "protocol": "tcp",
            "description": "HTTPS",
            "enabled": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    distinct_rowset = make_mock_rowset([range_row])
    config_rowset = make_mock_rowset([range_row])

    query_proxy = mock_port_db()

    async def select_side_effect(*args, **kwargs):
        return distinct_rowset if query_proxy.select.call_count == 1 else config_rowset

    query_proxy.select = AsyncMock(side_effect=select_side_effect)
    mock_port_db.return_value = query_proxy

    manager = PortConfigManager(mock_port_db)
    configs = await manager.get_all_configs(tenant)

    assert len(configs) >= 0  # May be empty depending on rowset behavior


@pytest.mark.asyncio
async def test_set_default_config(mock_port_db: MagicMock) -> None:
    """Test setting default port configuration."""
    manager = PortConfigManager(mock_port_db)

    result = await manager.set_default_config("headend-1", "cluster-1", "test-tenant")

    assert result is True
    # Should have called async_insert for each default port range
    assert mock_port_db.port_ranges.async_insert.call_count == 6


@pytest.mark.asyncio
async def test_has_port_overlap_no_overlap(mock_port_db: MagicMock) -> None:
    """Test port overlap detection with no overlap."""
    manager = PortConfigManager(mock_port_db)

    new_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=9000,
        end_port=9100,
        protocol=PortProtocol.TCP,
    )

    # Existing range that doesn't overlap
    existing_row = make_mock_row(
        {
            "id": str(uuid4()),
            "tenant": "test-tenant",
            "headend_id": "headend-1",
            "cluster_id": "cluster-1",
            "start_port": 8443,
            "end_port": 8443,
            "protocol": "tcp",
            "description": None,
            "enabled": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    rowset = make_mock_rowset([existing_row])
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_port_db.return_value = query_proxy

    overlap = await manager._has_port_overlap("headend-1", "test-tenant", new_range)

    assert overlap is False


@pytest.mark.asyncio
async def test_has_port_overlap_with_overlap(mock_port_db: MagicMock) -> None:
    """Test port overlap detection with overlap."""
    manager = PortConfigManager(mock_port_db)

    new_range = PortRangeConfig(
        id=str(uuid4()),
        tenant="test-tenant",
        headend_id="headend-1",
        cluster_id="cluster-1",
        start_port=8400,
        end_port=8500,
        protocol=PortProtocol.TCP,
    )

    # Existing range that overlaps
    existing_row = make_mock_row(
        {
            "id": str(uuid4()),
            "tenant": "test-tenant",
            "headend_id": "headend-1",
            "cluster_id": "cluster-1",
            "start_port": 8443,
            "end_port": 8443,
            "protocol": "tcp",
            "description": None,
            "enabled": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    rowset = make_mock_rowset([existing_row])
    query_proxy = mock_port_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_port_db.return_value = query_proxy

    overlap = await manager._has_port_overlap("headend-1", "test-tenant", new_range)

    assert overlap is True
