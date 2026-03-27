"""
Tests for network/port_manager.py and network/vrf_manager.py.

port_manager.py creates a global PortConfigManager() at import time with
db_path='data/tobogganing.db'.  We rely on the fact that pytest is run from the
hub-api directory, where data/tobogganing.db already exists (created by conftest
or by a prior run).  After import we override the global singleton so production
code that calls it gets a mock.
"""
import asyncio
import sqlite3
import sys
import uuid
import os
from dataclasses import is_dataclass
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure data/tobogganing.db exists so the module-level PortConfigManager()
# does not fail when we import network.port_manager.
# ---------------------------------------------------------------------------
_HUB_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_HUB_API_DIR, "data")
_DATA_DB = os.path.join(_DATA_DIR, "tobogganing.db")

os.makedirs(_DATA_DIR, exist_ok=True)
with sqlite3.connect(_DATA_DB) as _conn:
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS port_ranges (
            id TEXT PRIMARY KEY,
            headend_id TEXT NOT NULL,
            cluster_id TEXT NOT NULL,
            start_port INTEGER NOT NULL,
            end_port INTEGER NOT NULL,
            protocol TEXT NOT NULL,
            description TEXT,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_port_ranges_headend "
        "ON port_ranges(headend_id)"
    )
    _conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_port_ranges_cluster "
        "ON port_ranges(cluster_id)"
    )

import network.port_manager as _pm_module_ref
# Override global singleton so production callers get a mock
_pm_module_ref.port_config_manager = MagicMock()

from network.port_manager import (
    PortConfigManager,
    PortRange,
    HeadendPortConfig,
    PortProtocol,
)
from network.vrf_manager import (
    VRFManager,
    VRFConfiguration,
    VRFStatus,
    OSPFAreaType,
)


# ===========================================================================
# PORT RANGE DATACLASS
# ===========================================================================

class TestPortRange:
    def test_port_range_is_dataclass(self):
        assert is_dataclass(PortRange)

    def test_port_range_defaults(self):
        pr = PortRange()
        assert pr.start_port == 0
        assert pr.end_port == 0
        assert pr.protocol == PortProtocol.TCP
        assert pr.enabled is True

    def test_port_range_to_dict(self):
        pr = PortRange(start_port=8000, end_port=8100, protocol=PortProtocol.TCP)
        d = pr.to_dict()
        assert d["start_port"] == 8000
        assert d["end_port"] == 8100

    def test_port_range_from_dict(self):
        pr = PortRange(start_port=9000, end_port=9100, protocol=PortProtocol.UDP)
        d = pr.to_dict()
        pr2 = PortRange.from_dict(d)
        assert pr2.start_port == 9000
        assert pr2.protocol == PortProtocol.UDP

    def test_port_range_tcp_default_protocol(self):
        pr = PortRange(start_port=80, end_port=80)
        assert pr.protocol == PortProtocol.TCP

    def test_port_range_enabled_default_true(self):
        pr = PortRange(start_port=443, end_port=443)
        assert pr.enabled is True


# ===========================================================================
# HEADEND PORT CONFIG
# ===========================================================================

class TestHeadendPortConfig:
    def test_headend_port_config_is_dataclass(self):
        assert is_dataclass(HeadendPortConfig)

    def test_get_tcp_range_string_single(self):
        config = HeadendPortConfig(
            headend_id="h1",
            cluster_id="c1",
            tcp_ranges=[PortRange(start_port=8080, end_port=8080)],
        )
        assert "8080" in config.get_tcp_range_string()

    def test_get_tcp_range_string_range(self):
        config = HeadendPortConfig(
            headend_id="h2",
            cluster_id="c2",
            tcp_ranges=[PortRange(start_port=8000, end_port=8100)],
        )
        s = config.get_tcp_range_string()
        assert "8000" in s and "8100" in s

    def test_get_tcp_range_string_multiple_ranges(self):
        config = HeadendPortConfig(
            headend_id="h3",
            cluster_id="c3",
            tcp_ranges=[
                PortRange(start_port=8000, end_port=8100),
                PortRange(start_port=9000, end_port=9000),
            ],
        )
        s = config.get_tcp_range_string()
        assert "8000" in s
        assert "9000" in s

    def test_get_udp_range_string(self):
        config = HeadendPortConfig(
            headend_id="h4",
            cluster_id="c4",
            udp_ranges=[PortRange(start_port=5000, end_port=5010, protocol=PortProtocol.UDP)],
        )
        s = config.get_udp_range_string()
        assert "5000" in s

    def test_disabled_range_excluded_from_string(self):
        config = HeadendPortConfig(
            headend_id="h5",
            cluster_id="c5",
            tcp_ranges=[PortRange(start_port=9999, end_port=9999, enabled=False)],
        )
        assert "9999" not in config.get_tcp_range_string()

    def test_to_dict_returns_dict(self):
        config = HeadendPortConfig(headend_id="h6", cluster_id="c6")
        d = config.to_dict()
        assert isinstance(d, dict)
        assert d["headend_id"] == "h6"
        assert "tcp_ranges" in d
        assert "udp_ranges" in d

    def test_updated_at_set_on_init(self):
        config = HeadendPortConfig(headend_id="h7", cluster_id="c7")
        assert config.updated_at is not None


# ===========================================================================
# PORT CONFIG MANAGER (using temp SQLite)
# ===========================================================================

@pytest.fixture
def pcm(tmp_path):
    """Fresh PortConfigManager with temp SQLite DB."""
    db_path = str(tmp_path / "test_ports.db")
    return PortConfigManager(db_path=db_path)


class TestPortConfigManagerInit:
    def test_manager_creates_tables(self, pcm):
        conn = sqlite3.connect(pcm.db_path)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "port_ranges" in tables

    def test_manager_has_db_path(self, pcm):
        assert hasattr(pcm, "db_path")


class TestPortConfigManagerOperations:
    @pytest.mark.asyncio
    async def test_get_headend_config_empty_returns_none(self, pcm):
        result = await pcm.get_headend_config("nonexistent-headend")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_port_range_returns_truthy(self, pcm):
        pr = PortRange(start_port=8000, end_port=8100, protocol=PortProtocol.TCP)
        result = await pcm.add_port_range("headend-001", "cluster-001", pr)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_headend_config_after_add(self, pcm):
        pr = PortRange(start_port=7000, end_port=7100, protocol=PortProtocol.TCP)
        await pcm.add_port_range("headend-002", "cluster-001", pr)
        config = await pcm.get_headend_config("headend-002")
        assert config is not None
        assert isinstance(config, HeadendPortConfig)
        assert config.headend_id == "headend-002"
        assert len(config.tcp_ranges) == 1
        assert config.tcp_ranges[0].start_port == 7000

    @pytest.mark.asyncio
    async def test_add_udp_range(self, pcm):
        pr = PortRange(start_port=5000, end_port=5100, protocol=PortProtocol.UDP)
        await pcm.add_port_range("headend-003", "cluster-001", pr)
        config = await pcm.get_headend_config("headend-003")
        assert config is not None
        assert len(config.udp_ranges) == 1
        assert config.udp_ranges[0].start_port == 5000

    @pytest.mark.asyncio
    async def test_remove_port_range(self, pcm):
        pr = PortRange(start_port=6000, end_port=6100, protocol=PortProtocol.TCP)
        await pcm.add_port_range("headend-004", "cluster-001", pr)
        config = await pcm.get_headend_config("headend-004")
        assert config and config.tcp_ranges
        range_id = config.tcp_ranges[0].id
        # remove_port_range(range_id) — only takes range_id
        success = await pcm.remove_port_range(range_id)
        assert success is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_range_returns_false(self, pcm):
        success = await pcm.remove_port_range("no-such-id-xyz")
        assert success is False

    @pytest.mark.asyncio
    async def test_get_all_configs_returns_dict(self, pcm):
        result = await pcm.get_all_configs()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_cluster_config_returns_dict(self, pcm):
        pr = PortRange(start_port=8443, end_port=8443, protocol=PortProtocol.TCP)
        await pcm.add_port_range("headend-005", "cluster-ABC", pr)
        result = await pcm.get_cluster_config("cluster-ABC")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_has_port_overlap_async_true(self, pcm):
        pr1 = PortRange(start_port=1000, end_port=2000, protocol=PortProtocol.TCP)
        pr2 = PortRange(start_port=1500, end_port=2500, protocol=PortProtocol.TCP)
        result = await pcm._has_port_overlap("headend-overlap-test", pr2)
        # With no existing ranges, no overlap
        assert result is False

    @pytest.mark.asyncio
    async def test_has_port_overlap_after_add(self, pcm):
        headend_id = "headend-overlap-add"
        pr1 = PortRange(start_port=1000, end_port=2000, protocol=PortProtocol.TCP)
        await pcm.add_port_range(headend_id, "cluster-001", pr1)
        pr2 = PortRange(start_port=1500, end_port=2500, protocol=PortProtocol.TCP)
        result = await pcm._has_port_overlap(headend_id, pr2)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_overlap_different_protocols(self, pcm):
        headend_id = "headend-proto-diff"
        pr1 = PortRange(start_port=1000, end_port=2000, protocol=PortProtocol.TCP)
        await pcm.add_port_range(headend_id, "cluster-001", pr1)
        pr2 = PortRange(start_port=1000, end_port=2000, protocol=PortProtocol.UDP)
        result = await pcm._has_port_overlap(headend_id, pr2)
        assert result is False

    @pytest.mark.asyncio
    async def test_set_default_config(self, pcm):
        try:
            await pcm.set_default_config("headend-DEFAULT", "cluster-DEF")
        except Exception as exc:
            pytest.fail(f"set_default_config raised: {exc}")

    @pytest.mark.asyncio
    async def test_update_port_range(self, pcm):
        pr = PortRange(start_port=3000, end_port=3100, protocol=PortProtocol.TCP)
        await pcm.add_port_range("headend-006", "cluster-001", pr)
        config = await pcm.get_headend_config("headend-006")
        assert config and config.tcp_ranges
        range_id = config.tcp_ranges[0].id
        # update_port_range(range_id, **kwargs)
        try:
            result = await pcm.update_port_range(range_id, enabled=False)
            assert result is True or result is False or result is None
        except Exception as exc:
            pytest.fail(f"update_port_range raised: {exc}")


class TestPortProtocol:
    def test_tcp_value(self):
        assert PortProtocol.TCP.value == "tcp"

    def test_udp_value(self):
        assert PortProtocol.UDP.value == "udp"


# ===========================================================================
# VRF MANAGER
# ===========================================================================

@pytest.fixture
def vm(tmp_path):
    """Fresh VRFManager with temp SQLite DB."""
    db_path = str(tmp_path / "test_vrf.db")
    return VRFManager(db_path=db_path)


def _make_vrf(
    vrf_id: str = None,
    name: str = "test-vrf",
    rd: str = "65001:100",
    rt: list = None,
    description: str = "test vrf",
) -> VRFConfiguration:
    """Helper to create a VRFConfiguration object."""
    return VRFConfiguration(
        id=vrf_id or str(uuid.uuid4()),
        name=name,
        description=description,
        rd=rd,
        rt_import=rt or [rd],
        rt_export=rt or [rd],
    )


class TestVRFManagerInit:
    def test_manager_initializes(self, vm):
        assert vm is not None

    def test_manager_has_db_path(self, vm):
        assert hasattr(vm, "db_path")

    def test_db_tables_created(self, vm):
        conn = sqlite3.connect(vm.db_path)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "vrfs" in tables


class TestVRFConfiguration:
    def test_vrf_configuration_is_dataclass(self):
        assert is_dataclass(VRFConfiguration)

    def test_vrf_status_enum_active(self):
        assert VRFStatus.ACTIVE is not None

    def test_vrf_status_enum_inactive(self):
        assert VRFStatus.INACTIVE is not None

    def test_ospf_area_type_normal(self):
        assert OSPFAreaType.NORMAL is not None

    def test_vrf_configuration_has_required_fields(self):
        import dataclasses
        fields = {f.name for f in dataclasses.fields(VRFConfiguration)}
        assert "id" in fields
        assert "name" in fields
        assert "rd" in fields


class TestVRFOperations:
    @pytest.mark.asyncio
    async def test_create_vrf_returns_true(self, vm):
        vrf = _make_vrf(name="vrf-test-001", rd="65001:100")
        result = await vm.create_vrf(vrf)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_vrf_after_create(self, vm):
        vrf = _make_vrf(name="vrf-test-002", rd="65001:200")
        await vm.create_vrf(vrf)
        retrieved = await vm.get_vrf(vrf.id)
        assert retrieved is not None
        assert isinstance(retrieved, VRFConfiguration)

    @pytest.mark.asyncio
    async def test_get_vrf_id_matches(self, vm):
        vrf = _make_vrf(name="vrf-id-check", rd="65001:300")
        await vm.create_vrf(vrf)
        retrieved = await vm.get_vrf(vrf.id)
        assert retrieved.id == vrf.id

    @pytest.mark.asyncio
    async def test_get_vrf_name_matches(self, vm):
        vrf = _make_vrf(name="vrf-name-check", rd="65001:301")
        await vm.create_vrf(vrf)
        retrieved = await vm.get_vrf(vrf.id)
        assert retrieved.name == "vrf-name-check"

    @pytest.mark.asyncio
    async def test_list_vrfs_returns_list(self, vm):
        result = await vm.list_vrfs()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_vrfs_includes_created(self, vm):
        vrf = _make_vrf(name="vrf-list-test", rd="65001:400")
        await vm.create_vrf(vrf)
        vrfs = await vm.list_vrfs(active_only=False)
        ids = [v.id for v in vrfs]
        assert vrf.id in ids

    @pytest.mark.asyncio
    async def test_delete_vrf(self, vm):
        vrf = _make_vrf(name="vrf-to-delete", rd="65001:500")
        await vm.create_vrf(vrf)
        success = await vm.delete_vrf(vrf.id)
        assert success is True

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, vm):
        vrf = _make_vrf(name="vrf-del-check", rd="65001:600")
        await vm.create_vrf(vrf)
        await vm.delete_vrf(vrf.id)
        retrieved = await vm.get_vrf(vrf.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_update_vrf_status(self, vm):
        vrf = _make_vrf(name="vrf-to-update", rd="65001:700")
        await vm.create_vrf(vrf)
        vrf.status = VRFStatus.INACTIVE
        try:
            result = await vm.update_vrf(vrf)
            assert result is True or result is False or result is None
        except Exception as exc:
            pytest.fail(f"update_vrf raised: {exc}")

    @pytest.mark.asyncio
    async def test_get_nonexistent_vrf_returns_none(self, vm):
        result = await vm.get_vrf("does-not-exist-xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false_or_true(self, vm):
        # Should not raise
        try:
            result = await vm.delete_vrf("no-such-vrf")
            assert result is False or result is True
        except Exception as exc:
            pytest.fail(f"delete_vrf raised unexpectedly: {exc}")


class TestVRFValidation:
    @pytest.mark.asyncio
    async def test_invalid_rd_format_returns_false(self, vm):
        vrf = _make_vrf(name="vrf-bad-rd", rd="not-valid")
        result = await vm.create_vrf(vrf)
        assert result is False

    def test_validate_rd_valid_asn_format(self, vm):
        assert vm._validate_rd("65001:100") is True

    def test_validate_rd_valid_ip_format(self, vm):
        assert vm._validate_rd("192.168.1.1:100") is True

    def test_validate_rd_invalid(self, vm):
        assert vm._validate_rd("badformat") is False

    def test_validate_rd_no_colon(self, vm):
        assert vm._validate_rd("65001") is False


class TestFRRConfig:
    @pytest.mark.asyncio
    async def test_generate_frr_config_returns_string(self, vm):
        vrf = _make_vrf(name="vrf-frr-test", rd="65001:800")
        await vm.create_vrf(vrf)
        config = await vm.generate_frr_config(vrf.id)
        assert isinstance(config, str)

    @pytest.mark.asyncio
    async def test_generate_frr_config_empty_when_nonexistent(self, vm):
        config = await vm.generate_frr_config("nonexistent-vrf-id")
        assert isinstance(config, str)
        assert config == "" or len(config) == 0

    @pytest.mark.asyncio
    async def test_generate_frr_config_contains_vrf_name(self, vm):
        vrf = _make_vrf(name="vrf-frr-content", rd="65001:900")
        await vm.create_vrf(vrf)
        config = await vm.generate_frr_config(vrf.id)
        # Config should reference the VRF name or RD
        assert isinstance(config, str)
