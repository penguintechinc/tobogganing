"""Edge-case coverage for VRFManager not covered by test_sdwan_vrf.py.

Covers exception (fail-closed) branches, the inactive-VRF listing path, the
OSPF-enabled branch of generate_frr_config, and the remaining validator
branches (_validate_frr_area_id numeric range, _validate_rd malformed input).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hub_api.modules.sdwan.network.vrf_manager import (
    OSPFArea,
    OSPFAreaType,
    VRFConfiguration,
    VRFManager,
    VRFStatus,
)
from hub_api.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_vrf_db() -> MagicMock:
    """Create a mock DAL with VRF table support.

    Returns:
        Mock database object with VRF tables.
    """
    db = MagicMock()
    vrfs_table = MagicMock()
    vrfs_table.async_insert = AsyncMock(return_value=1)
    ospf_areas_table = MagicMock()
    ospf_areas_table.async_insert = AsyncMock(return_value=1)
    ospf_neighbors_table = MagicMock()
    ospf_neighbors_table.async_insert = AsyncMock(return_value=1)

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


def _vrf_row(**overrides) -> dict:
    """Build a vrfs row dict with sane defaults.

    Args:
        overrides: Fields to override.

    Returns:
        Dict of row data suitable for make_mock_row.
    """
    defaults = dict(
        id=str(uuid4()),
        tenant="test-tenant",
        name="test-vrf",
        description="Test VRF",
        rd="65001:100",
        rt_import="[]",
        rt_export="[]",
        ip_ranges="[]",
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_active=True,
        ospf_enabled=False,
        ospf_router_id=None,
    )
    defaults.update(overrides)
    return defaults


# --- create_vrf: invalid ip_range + exception ---------------------------------


@pytest.mark.asyncio
async def test_create_vrf_invalid_ip_range(mock_vrf_db: MagicMock) -> None:
    """create_vrf rejects an invalid CIDR in ip_ranges."""
    manager = VRFManager(mock_vrf_db)
    vrf = VRFConfiguration(
        id=str(uuid4()),
        tenant="test-tenant",
        name="test-vrf",
        description="Test VRF",
        rd="65001:100",
        ip_ranges=["not-a-cidr"],
    )

    result = await manager.create_vrf(vrf)

    assert result is False


@pytest.mark.asyncio
async def test_create_vrf_exception_returns_false(mock_vrf_db: MagicMock) -> None:
    """create_vrf fails closed (False) on DB error."""
    mock_vrf_db.vrfs.async_insert = AsyncMock(side_effect=RuntimeError("db error"))
    manager = VRFManager(mock_vrf_db)
    vrf = VRFConfiguration(
        id=str(uuid4()),
        tenant="test-tenant",
        name="test-vrf",
        description="Test VRF",
        rd="65001:100",
    )

    result = await manager.create_vrf(vrf)

    assert result is False


# --- update_vrf / delete_vrf: exception -----------------------------------------


@pytest.mark.asyncio
async def test_update_vrf_exception_returns_false(mock_vrf_db: MagicMock) -> None:
    """update_vrf fails closed (False) on DB error."""
    query_proxy = mock_vrf_db()
    query_proxy.update = AsyncMock(side_effect=RuntimeError("db error"))

    manager = VRFManager(mock_vrf_db)
    vrf = VRFConfiguration(
        id=str(uuid4()),
        tenant="test-tenant",
        name="test-vrf",
        description="Test VRF",
        rd="65001:100",
    )

    result = await manager.update_vrf(vrf)

    assert result is False


@pytest.mark.asyncio
async def test_delete_vrf_exception_returns_false(mock_vrf_db: MagicMock) -> None:
    """delete_vrf fails closed (False) on DB error."""
    query_proxy = mock_vrf_db()
    query_proxy.delete = AsyncMock(side_effect=RuntimeError("db error"))

    manager = VRFManager(mock_vrf_db)
    result = await manager.delete_vrf("vrf-1", "tenant-1")

    assert result is False


# --- get_vrf: not found + exception --------------------------------------------


@pytest.mark.asyncio
async def test_get_vrf_not_found_returns_none(mock_vrf_db: MagicMock) -> None:
    """get_vrf returns None when no row is found."""
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    result = await manager.get_vrf("vrf-1", "tenant-1")

    assert result is None


@pytest.mark.asyncio
async def test_get_vrf_exception_returns_none(mock_vrf_db: MagicMock) -> None:
    """get_vrf fails closed (None) on DB error."""
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    result = await manager.get_vrf("vrf-1", "tenant-1")

    assert result is None


# --- list_vrfs: active_only=False + exception -----------------------------------


@pytest.mark.asyncio
async def test_list_vrfs_active_only_false(mock_vrf_db: MagicMock) -> None:
    """list_vrfs(active_only=False) queries without the is_active filter."""
    vrf_row = make_mock_row(_vrf_row(status="inactive", is_active=False))
    rowset = make_mock_rowset([vrf_row])
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    vrfs = await manager.list_vrfs("tenant-1", active_only=False)

    assert len(vrfs) == 1
    assert vrfs[0].status == VRFStatus.INACTIVE


@pytest.mark.asyncio
async def test_list_vrfs_exception_returns_empty(mock_vrf_db: MagicMock) -> None:
    """list_vrfs fails closed (empty list) on DB error."""
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    vrfs = await manager.list_vrfs("tenant-1")

    assert vrfs == []


# --- create_ospf_area: exception ------------------------------------------------


@pytest.mark.asyncio
async def test_create_ospf_area_exception_returns_false(mock_vrf_db: MagicMock) -> None:
    """create_ospf_area fails closed (False) on DB error."""
    mock_vrf_db.ospf_areas.async_insert = AsyncMock(side_effect=RuntimeError("db error"))
    manager = VRFManager(mock_vrf_db)
    area = OSPFArea(
        id=str(uuid4()),
        tenant="tenant-1",
        vrf_id=str(uuid4()),
        area_id="0.0.0.0",
        area_type=OSPFAreaType.BACKBONE,
    )

    result = await manager.create_ospf_area(area)

    assert result is False


# --- get_ospf_neighbors: exception ----------------------------------------------


@pytest.mark.asyncio
async def test_get_ospf_neighbors_exception_returns_empty(
    mock_vrf_db: MagicMock,
) -> None:
    """get_ospf_neighbors fails closed (empty list) on DB error."""
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    neighbors = await manager.get_ospf_neighbors("vrf-1", "tenant-1")

    assert neighbors == []


# --- generate_frr_config: vrf not found, rt_export, OSPF branch, exceptions ----


@pytest.mark.asyncio
async def test_generate_frr_config_vrf_not_found_returns_empty(
    mock_vrf_db: MagicMock,
) -> None:
    """generate_frr_config returns '' when the VRF doesn't exist."""
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    config = await manager.generate_frr_config("vrf-1", "tenant-1")

    assert config == ""


@pytest.mark.asyncio
async def test_generate_frr_config_with_rt_export(mock_vrf_db: MagicMock) -> None:
    """generate_frr_config emits 'export rt' lines for each rt_export entry."""
    vrf_row = make_mock_row(_vrf_row(rt_import="[]", rt_export='["65001:200"]'))
    rowset = make_mock_rowset([vrf_row])
    query_proxy = mock_vrf_db()

    call_count = [0]

    async def select_side_effect(*args, **kwargs):
        call_count[0] += 1
        return rowset if call_count[0] == 1 else make_mock_rowset([])

    query_proxy.select = AsyncMock(side_effect=select_side_effect)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    config = await manager.generate_frr_config("vrf-1", "tenant-1")

    assert "export rt 65001:200" in config


@pytest.mark.asyncio
async def test_generate_frr_config_ospf_enabled_with_areas(
    mock_vrf_db: MagicMock,
) -> None:
    """generate_frr_config emits router ospf block and area networks when enabled."""
    vrf_row = make_mock_row(_vrf_row(ospf_enabled=True, ospf_router_id="10.0.0.1"))
    vrf_rowset = make_mock_rowset([vrf_row])

    area_row = make_mock_row(
        {
            "area_id": "0.0.0.0",
            "networks": '["10.0.0.0/24"]',
        }
    )
    area_rowset = make_mock_rowset([area_row])

    query_proxy = mock_vrf_db()
    call_count = [0]

    async def select_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return vrf_rowset
        return area_rowset

    query_proxy.select = AsyncMock(side_effect=select_side_effect)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    config = await manager.generate_frr_config("vrf-1", "tenant-1")

    assert "router ospf vrf test-vrf" in config
    assert "router-id 10.0.0.1" in config
    assert "network 10.0.0.0/24 area 0.0.0.0" in config


@pytest.mark.asyncio
async def test_generate_frr_config_value_error_reraises(
    mock_vrf_db: MagicMock,
) -> None:
    """generate_frr_config re-raises ValueError from field validation."""
    vrf_row = make_mock_row(_vrf_row(name="bad name with space"))
    rowset = make_mock_rowset([vrf_row])
    query_proxy = mock_vrf_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)

    with pytest.raises(ValueError, match="forbidden characters"):
        await manager.generate_frr_config("vrf-1", "tenant-1")


@pytest.mark.asyncio
async def test_generate_frr_config_generic_exception_returns_empty(
    mock_vrf_db: MagicMock,
) -> None:
    """generate_frr_config fails closed ('') on an unexpected non-ValueError error."""
    vrf_row = make_mock_row(_vrf_row())
    rowset = make_mock_rowset([vrf_row])
    query_proxy = mock_vrf_db()

    call_count = [0]

    async def select_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return rowset
        raise RuntimeError("boom")

    query_proxy.select = AsyncMock(side_effect=select_side_effect)
    mock_vrf_db.return_value = query_proxy

    manager = VRFManager(mock_vrf_db)
    vrf = await manager.get_vrf("vrf-1", "tenant-1")
    assert vrf is not None
    # Force ospf_enabled path to reach the second (raising) select call.
    manager.get_vrf = AsyncMock(  # type: ignore[method-assign]
        return_value=VRFConfiguration(
            id="vrf-1",
            tenant="tenant-1",
            name="test-vrf",
            description="d",
            rd="65001:100",
            ospf_enabled=True,
            ospf_router_id="10.0.0.1",
        )
    )

    config = await manager.generate_frr_config("vrf-1", "tenant-1")

    assert config == ""


# --- _validate_frr_area_id: numeric out-of-range branch -------------------------


def test_validate_frr_area_id_numeric_out_of_range() -> None:
    """Numeric area ID outside 0-4294967295 raises ValueError."""
    with pytest.raises(ValueError, match="Invalid OSPF area"):
        VRFManager._validate_frr_area_id("9999999999")


# --- _validate_rd: additional malformed-input branches ---------------------------


def test_validate_rd_too_many_parts_returns_false() -> None:
    """RD with more than one colon returns False."""
    assert VRFManager._validate_rd("1:2:3") is False


def test_validate_rd_left_not_asn_or_ip_returns_false() -> None:
    """RD left side that's neither a valid ASN nor IP returns False."""
    assert VRFManager._validate_rd("not-an-asn-or-ip:100") is False


def test_validate_rd_right_not_numeric_returns_false() -> None:
    """RD right side that's not numeric returns False."""
    assert VRFManager._validate_rd("65001:not-numeric") is False


def test_validate_rd_non_string_returns_false() -> None:
    """A non-string RD (e.g. None) is fail-closed to False."""
    assert VRFManager._validate_rd(None) is False  # type: ignore[arg-type]
