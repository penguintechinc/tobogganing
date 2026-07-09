"""Tests for SASE VRF manager."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.modules.sase.network.vrf_manager import (
    VRFConfiguration,
    VRFManager,
    VRFStatus,
    OSPFArea,
    OSPFAreaType,
    OSPFNeighbor,
)
from core.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_vrf_db() -> MagicMock:
    """Create a mock DAL with VRF table support.

    Returns:
        Mock database object with VRF tables.
    """
    db = MagicMock()

    # Mock VRF table
    vrfs_table = MagicMock()
    vrfs_table.async_insert = AsyncMock(return_value=1)

    # Mock OSPF areas table
    ospf_areas_table = MagicMock()
    ospf_areas_table.async_insert = AsyncMock(return_value=1)

    # Mock OSPF neighbors table
    ospf_neighbors_table = MagicMock()
    ospf_neighbors_table.async_insert = AsyncMock(return_value=1)

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
    db.vrfs = vrfs_table
    db.ospf_areas = ospf_areas_table
    db.ospf_neighbors = ospf_neighbors_table

    return db


@pytest.mark.asyncio
async def test_create_vrf(mock_vrf_db: MagicMock) -> None:
    """Test creating a new VRF."""
    manager = VRFManager(mock_vrf_db)

    vrf = VRFConfiguration(
        id=str(uuid4()),
        tenant="test-tenant",
        name="test-vrf",
        description="Test VRF",
        rd="65001:100",
        rt_import=["65001:100"],
        rt_export=["65001:100"],
        ip_ranges=["10.0.0.0/8"],
    )

    result = await manager.create_vrf(vrf)

    assert result is True
    mock_vrf_db.vrfs.async_insert.assert_called_once()
    call_kwargs = mock_vrf_db.vrfs.async_insert.call_args[1]
    assert call_kwargs["id"] == vrf.id
    assert call_kwargs["tenant"] == vrf.tenant
    assert call_kwargs["name"] == vrf.name
    assert call_kwargs["rd"] == "65001:100"


@pytest.mark.asyncio
async def test_create_vrf_invalid_rd(mock_vrf_db: MagicMock) -> None:
    """Test create_vrf with invalid Route Distinguisher."""
    manager = VRFManager(mock_vrf_db)

    vrf = VRFConfiguration(
        id=str(uuid4()),
        tenant="test-tenant",
        name="test-vrf",
        description="Test VRF",
        rd="invalid-rd",
    )

    result = await manager.create_vrf(vrf)

    assert result is False


@pytest.mark.asyncio
async def test_get_vrf(mock_vrf_db: MagicMock) -> None:
    """Test retrieving a VRF by ID."""
    vrf_id = str(uuid4())
    tenant = "test-tenant"

    vrf_row = make_mock_row(
        {
            "id": vrf_id,
            "tenant": tenant,
            "name": "test-vrf",
            "description": "Test VRF",
            "rd": "65001:100",
            "rt_import": '["65001:100"]',
            "rt_export": '["65001:100"]',
            "ip_ranges": '["10.0.0.0/8"]',
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "ospf_enabled": False,
            "ospf_router_id": None,
        }
    )

    rowset = make_mock_rowset([vrf_row])
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    vrf = await manager.get_vrf(vrf_id, tenant)

    assert vrf is not None
    assert vrf.id == vrf_id
    assert vrf.tenant == tenant
    assert vrf.name == "test-vrf"
    assert vrf.rd == "65001:100"


@pytest.mark.asyncio
async def test_update_vrf(mock_vrf_db: MagicMock) -> None:
    """Test updating a VRF."""
    vrf_id = str(uuid4())
    tenant = "test-tenant"

    vrf = VRFConfiguration(
        id=vrf_id,
        tenant=tenant,
        name="updated-vrf",
        description="Updated VRF",
        rd="65002:200",
    )

    query_proxy = mock_vrf_db()
    manager = VRFManager(mock_vrf_db)
    result = await manager.update_vrf(vrf)

    assert result is True
    query_proxy.update.assert_called_once()


@pytest.mark.asyncio
async def test_list_vrfs(mock_vrf_db: MagicMock) -> None:
    """Test listing VRFs with tenant scoping."""
    vrf_id1 = str(uuid4())
    vrf_id2 = str(uuid4())
    tenant = "test-tenant"

    vrf_row1 = make_mock_row(
        {
            "id": vrf_id1,
            "tenant": tenant,
            "name": "vrf-1",
            "description": "VRF 1",
            "rd": "65001:100",
            "rt_import": "[]",
            "rt_export": "[]",
            "ip_ranges": "[]",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "ospf_enabled": False,
            "ospf_router_id": None,
        }
    )

    vrf_row2 = make_mock_row(
        {
            "id": vrf_id2,
            "tenant": tenant,
            "name": "vrf-2",
            "description": "VRF 2",
            "rd": "65002:200",
            "rt_import": "[]",
            "rt_export": "[]",
            "ip_ranges": "[]",
            "status": "inactive",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "ospf_enabled": False,
            "ospf_router_id": None,
        }
    )

    rowset = make_mock_rowset([vrf_row1, vrf_row2])
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    vrfs = await manager.list_vrfs(tenant)

    assert len(vrfs) == 2
    assert vrfs[0].name == "vrf-1"
    assert vrfs[1].name == "vrf-2"


@pytest.mark.asyncio
async def test_delete_vrf(mock_vrf_db: MagicMock) -> None:
    """Test deleting a VRF."""
    vrf_id = str(uuid4())
    tenant = "test-tenant"

    query_proxy = mock_vrf_db()
    manager = VRFManager(mock_vrf_db)
    result = await manager.delete_vrf(vrf_id, tenant)

    assert result is True
    # Should have called delete on ospf_neighbors, ospf_areas, and vrfs
    assert query_proxy.delete.call_count == 3


@pytest.mark.asyncio
async def test_create_ospf_area(mock_vrf_db: MagicMock) -> None:
    """Test creating an OSPF area."""
    area_id = str(uuid4())
    vrf_id = str(uuid4())
    tenant = "test-tenant"

    area = OSPFArea(
        id=area_id,
        tenant=tenant,
        vrf_id=vrf_id,
        area_id="0.0.0.0",
        area_type=OSPFAreaType.BACKBONE,
        networks=["10.0.0.0/8"],
    )

    manager = VRFManager(mock_vrf_db)
    result = await manager.create_ospf_area(area)

    assert result is True
    mock_vrf_db.ospf_areas.async_insert.assert_called_once()


@pytest.mark.asyncio
async def test_get_ospf_neighbors(mock_vrf_db: MagicMock) -> None:
    """Test retrieving OSPF neighbors."""
    neighbor_id = str(uuid4())
    vrf_id = str(uuid4())
    tenant = "test-tenant"

    neighbor_row = make_mock_row(
        {
            "id": neighbor_id,
            "tenant": tenant,
            "vrf_id": vrf_id,
            "neighbor_id": "1.1.1.1",
            "neighbor_ip": "10.0.0.1",
            "interface": "eth0",
            "area_id": "0.0.0.0",
            "state": "Full",
            "priority": 1,
            "dead_interval": 40,
            "hello_interval": 10,
            "last_seen": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    rowset = make_mock_rowset([neighbor_row])
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    neighbors = await manager.get_ospf_neighbors(vrf_id, tenant)

    assert len(neighbors) == 1
    assert neighbors[0].neighbor_ip == "10.0.0.1"


@pytest.mark.asyncio
async def test_generate_frr_config(mock_vrf_db: MagicMock) -> None:
    """Test FRR configuration generation."""
    vrf_id = str(uuid4())
    tenant = "test-tenant"

    vrf_row = make_mock_row(
        {
            "id": vrf_id,
            "tenant": tenant,
            "name": "test-vrf",
            "description": "Test VRF",
            "rd": "65001:100",
            "rt_import": '["65001:100"]',
            "rt_export": '[]',
            "ip_ranges": "[]",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "ospf_enabled": False,
            "ospf_router_id": None,
        }
    )

    rowset = make_mock_rowset([vrf_row])
    query_proxy = mock_vrf_db()

    # Setup the mock to return the VRF row on first select, empty on second
    select_call_count = [0]

    async def select_side_effect(*args, **kwargs):
        select_call_count[0] += 1
        if select_call_count[0] == 1:
            return rowset
        return make_mock_rowset([])

    query_proxy.select = AsyncMock(side_effect=select_side_effect)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    config = await manager.generate_frr_config(vrf_id, tenant)

    assert "vrf test-vrf" in config
    assert "rd 65001:100" in config


def test_validate_rd_valid_asn_format() -> None:
    """Test RD validation with ASN format."""
    assert VRFManager._validate_rd("65001:100") is True
    assert VRFManager._validate_rd("4200000000:1") is True


def test_validate_rd_valid_ip_format() -> None:
    """Test RD validation with IP format."""
    assert VRFManager._validate_rd("192.168.1.1:100") is True
    assert VRFManager._validate_rd("10.0.0.1:65535") is True


def test_validate_rd_invalid_format() -> None:
    """Test RD validation with invalid format."""
    assert VRFManager._validate_rd("invalid") is False
    assert VRFManager._validate_rd("65001:99999") is False
    assert VRFManager._validate_rd("999999999999:100") is False


def test_validate_frr_name_valid() -> None:
    """Test FRR name validation with valid names."""
    VRFManager._validate_frr_name("test-vrf")
    VRFManager._validate_frr_name("vrf_123")
    VRFManager._validate_frr_name("PROD")


def test_validate_frr_name_invalid_newline() -> None:
    """Test FRR name validation rejects newlines (config injection)."""
    import pytest

    with pytest.raises(ValueError, match="forbidden characters"):
        VRFManager._validate_frr_name("test\nvrf")


def test_validate_frr_name_invalid_space() -> None:
    """Test FRR name validation rejects spaces (config injection)."""
    import pytest

    with pytest.raises(ValueError, match="forbidden characters"):
        VRFManager._validate_frr_name("test vrf")


def test_validate_frr_text_valid() -> None:
    """Test FRR text validation with valid text."""
    VRFManager._validate_frr_text("This is a description")
    VRFManager._validate_frr_text("192.168.1.1")


def test_validate_frr_text_invalid_newline() -> None:
    """Test FRR text validation rejects newlines (config injection)."""
    import pytest

    with pytest.raises(ValueError, match="forbidden characters"):
        VRFManager._validate_frr_text("description\nrouter ospf")


def test_validate_frr_text_invalid_control_char() -> None:
    """Test FRR text validation rejects control characters."""
    import pytest

    with pytest.raises(ValueError, match="forbidden characters"):
        VRFManager._validate_frr_text("text\x00with\x01control")


def test_validate_frr_route_target_valid() -> None:
    """Test FRR route target validation with valid formats."""
    VRFManager._validate_frr_route_target("65001:100")
    VRFManager._validate_frr_route_target("192.168.1.1:100")


def test_validate_frr_route_target_invalid() -> None:
    """Test FRR route target validation with invalid formats."""
    import pytest

    with pytest.raises(ValueError, match="Invalid route target"):
        VRFManager._validate_frr_route_target("invalid")
    
    with pytest.raises(ValueError, match="Invalid route target"):
        VRFManager._validate_frr_route_target("65001:100:extra")


def test_validate_frr_area_id_valid() -> None:
    """Test OSPF area ID validation with valid formats."""
    VRFManager._validate_frr_area_id("0")
    VRFManager._validate_frr_area_id("0.0.0.0")
    VRFManager._validate_frr_area_id("1.2.3.4")


def test_validate_frr_area_id_invalid() -> None:
    """Test OSPF area ID validation with invalid formats."""
    import pytest

    with pytest.raises(ValueError, match="Invalid OSPF area"):
        VRFManager._validate_frr_area_id("256.1.1.1")
    
    with pytest.raises(ValueError, match="Invalid OSPF area"):
        VRFManager._validate_frr_area_id("invalid")


def test_validate_frr_network_valid() -> None:
    """Test network CIDR validation with valid networks."""
    VRFManager._validate_frr_network("10.0.0.0/8")
    VRFManager._validate_frr_network("192.168.0.0/16")


def test_validate_frr_network_invalid_newline() -> None:
    """Test network CIDR validation rejects newlines (config injection)."""
    import pytest

    with pytest.raises(ValueError, match="forbidden characters"):
        VRFManager._validate_frr_network("10.0.0.0/8\nrouter ospf")


def test_validate_frr_network_invalid_cidr() -> None:
    """Test network CIDR validation rejects invalid CIDR."""
    import pytest

    with pytest.raises(ValueError, match="Invalid network CIDR"):
        VRFManager._validate_frr_network("256.1.1.1/8")
