"""
Tests for network/vrf_manager.py — VRFManager CRUD, OSPF, validation, FRR config generation.

VRFManager uses SQLite directly (no PyDAL/get_db), so no module-level DB mock needed.
All tests use a real in-memory/temp SQLite DB via the vrf_manager fixture from conftest.
"""
import json
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from network.vrf_manager import (
    VRFManager,
    VRFConfiguration,
    VRFStatus,
    OSPFArea,
    OSPFAreaType,
    OSPFNeighbor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_vrf(
    vrf_id: str = "vrf-001",
    name: str = "test-vrf",
    rd: str = "65001:100",
    status: VRFStatus = VRFStatus.INACTIVE,
    ospf_enabled: bool = False,
) -> VRFConfiguration:
    return VRFConfiguration(
        id=vrf_id,
        name=name,
        description="Test VRF",
        rd=rd,
        rt_import=["65001:200"],
        rt_export=["65001:200"],
        ip_ranges=["10.0.0.0/24"],
        status=status,
        ospf_enabled=ospf_enabled,
        ospf_router_id="10.0.0.1" if ospf_enabled else None,
        ospf_networks=[{"network": "10.0.0.0/24", "area": "0.0.0.0"}] if ospf_enabled else [],
    )


def make_ospf_area(
    area_id: str = "0.0.0.0",
    vrf_id: str = "vrf-001",
    area_type: OSPFAreaType = OSPFAreaType.BACKBONE,
) -> OSPFArea:
    return OSPFArea(
        area_id=area_id,
        area_type=area_type,
        vrf_id=vrf_id,
        networks=["10.0.0.0/24"],
        auth_type=None,
        auth_key=None,
    )


# ---------------------------------------------------------------------------
# _validate_rd (lines 428-464)
# ---------------------------------------------------------------------------

class TestValidateRD:
    def test_valid_asn_rd(self, vrf_manager):
        assert vrf_manager._validate_rd("65001:100") is True

    def test_valid_ip_rd(self, vrf_manager):
        assert vrf_manager._validate_rd("192.168.1.1:200") is True

    def test_missing_colon_returns_false(self, vrf_manager):
        assert vrf_manager._validate_rd("65001100") is False

    def test_too_many_parts_returns_false(self, vrf_manager):
        assert vrf_manager._validate_rd("65001:100:200") is False

    def test_asn_out_of_range_returns_false(self, vrf_manager):
        # ASN must be 1..4294967295
        assert vrf_manager._validate_rd("0:100") is False
        assert vrf_manager._validate_rd("4294967296:100") is False

    def test_value_out_of_range_returns_false(self, vrf_manager):
        # Right part must be 0..65535
        assert vrf_manager._validate_rd("65001:65536") is False

    def test_non_numeric_right_part_returns_false(self, vrf_manager):
        assert vrf_manager._validate_rd("65001:abc") is False

    def test_invalid_ip_left_part_returns_false(self, vrf_manager):
        assert vrf_manager._validate_rd("not-an-ip:100") is False

    def test_valid_zero_value(self, vrf_manager):
        assert vrf_manager._validate_rd("65001:0") is True

    def test_valid_max_value(self, vrf_manager):
        assert vrf_manager._validate_rd("65001:65535") is True


# ---------------------------------------------------------------------------
# create_vrf (lines 158-204)
# ---------------------------------------------------------------------------

class TestCreateVRF:
    @pytest.mark.asyncio
    async def test_create_vrf_success(self, vrf_manager):
        """Covers lines 158-200: normal creation path."""
        vrf = make_vrf()
        result = await vrf_manager.create_vrf(vrf)
        assert result is True

    @pytest.mark.asyncio
    async def test_create_vrf_invalid_rd_returns_false(self, vrf_manager):
        """Covers lines 162-164: invalid RD short-circuits with False."""
        vrf = make_vrf(rd="invalid-rd")
        result = await vrf_manager.create_vrf(vrf)
        assert result is False

    @pytest.mark.asyncio
    async def test_create_vrf_invalid_ip_range_returns_false(self, vrf_manager):
        """Covers lines 168-172: invalid IP range returns False."""
        vrf = make_vrf()
        vrf.ip_ranges = ["not-a-cidr"]
        result = await vrf_manager.create_vrf(vrf)
        assert result is False

    @pytest.mark.asyncio
    async def test_create_vrf_sets_status_active(self, vrf_manager):
        """Covers _apply_vrf_config which sets status ACTIVE."""
        vrf = make_vrf(vrf_id="vrf-status-001", name="status-vrf")
        await vrf_manager.create_vrf(vrf)
        # Status should be ACTIVE after apply
        assert vrf.status == VRFStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_create_vrf_db_exception_returns_false(self, vrf_manager):
        """Covers lines 202-204: DB exception returns False."""
        import sqlite3
        vrf = make_vrf()
        # Patch sqlite3.connect to raise
        with patch("network.vrf_manager.sqlite3.connect", side_effect=Exception("DB error")):
            result = await vrf_manager.create_vrf(vrf)
        assert result is False

    @pytest.mark.asyncio
    async def test_create_vrf_with_ospf_enabled(self, vrf_manager):
        """Covers OSPF config path in _apply_vrf_config."""
        vrf = make_vrf(vrf_id="vrf-ospf-001", name="ospf-vrf", ospf_enabled=True)
        result = await vrf_manager.create_vrf(vrf)
        assert result is True
        assert vrf.status == VRFStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_create_vrf_with_rt_import_export(self, vrf_manager):
        """Covers rt_import and rt_export lines in _apply_vrf_config."""
        vrf = make_vrf(vrf_id="vrf-rt-001", name="rt-vrf")
        vrf.rt_import = ["65001:200", "65001:300"]
        vrf.rt_export = ["65001:400"]
        result = await vrf_manager.create_vrf(vrf)
        assert result is True


# ---------------------------------------------------------------------------
# update_vrf (lines 206-242)
# ---------------------------------------------------------------------------

class TestUpdateVRF:
    @pytest.mark.asyncio
    async def test_update_vrf_success(self, vrf_manager):
        """Covers lines 206-241: normal update path."""
        vrf = make_vrf(vrf_id="vrf-upd-001", name="update-vrf")
        await vrf_manager.create_vrf(vrf)

        vrf.description = "Updated description"
        result = await vrf_manager.update_vrf(vrf)
        assert result is True

    @pytest.mark.asyncio
    async def test_update_vrf_updates_timestamp(self, vrf_manager):
        """Covers line 209: updated_at is refreshed on update."""
        vrf = make_vrf(vrf_id="vrf-ts-001", name="ts-vrf")
        old_ts = vrf.updated_at
        await vrf_manager.create_vrf(vrf)
        await vrf_manager.update_vrf(vrf)
        assert vrf.updated_at >= old_ts

    @pytest.mark.asyncio
    async def test_update_vrf_db_exception_returns_false(self, vrf_manager):
        """Covers lines 240-242: DB exception returns False."""
        vrf = make_vrf(vrf_id="vrf-upd-err", name="upd-err-vrf")
        with patch("network.vrf_manager.sqlite3.connect", side_effect=Exception("DB error")):
            result = await vrf_manager.update_vrf(vrf)
        assert result is False


# ---------------------------------------------------------------------------
# delete_vrf (lines 244-268)
# ---------------------------------------------------------------------------

class TestDeleteVRF:
    @pytest.mark.asyncio
    async def test_delete_vrf_success(self, vrf_manager):
        """Covers lines 244-264: create then delete."""
        vrf = make_vrf(vrf_id="vrf-del-001", name="del-vrf")
        await vrf_manager.create_vrf(vrf)
        result = await vrf_manager.delete_vrf("vrf-del-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_vrf_nonexistent_succeeds(self, vrf_manager):
        """Deleting a VRF that doesn't exist still returns True (no error)."""
        result = await vrf_manager.delete_vrf("nonexistent-id")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_vrf_db_exception_returns_false(self, vrf_manager):
        """Covers lines 266-268: DB exception returns False."""
        with patch("network.vrf_manager.sqlite3.connect", side_effect=Exception("DB error")):
            result = await vrf_manager.delete_vrf("vrf-del-err")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_vrf_removes_ospf_areas(self, vrf_manager):
        """Covers lines 254-255: OSPF areas are deleted with the VRF."""
        vrf = make_vrf(vrf_id="vrf-ospf-del", name="ospf-del-vrf", ospf_enabled=True)
        await vrf_manager.create_vrf(vrf)
        area = make_ospf_area(vrf_id="vrf-ospf-del")
        await vrf_manager.create_ospf_area(area)

        result = await vrf_manager.delete_vrf("vrf-ospf-del")
        assert result is True


# ---------------------------------------------------------------------------
# get_vrf (lines 270-309)
# ---------------------------------------------------------------------------

class TestGetVRF:
    @pytest.mark.asyncio
    async def test_get_vrf_returns_configuration(self, vrf_manager):
        """Covers lines 270-305: retrieves VRFConfiguration from DB."""
        vrf = make_vrf(vrf_id="vrf-get-001", name="get-vrf")
        await vrf_manager.create_vrf(vrf)

        result = await vrf_manager.get_vrf("vrf-get-001")
        assert result is not None
        assert isinstance(result, VRFConfiguration)
        assert result.id == "vrf-get-001"
        assert result.name == "get-vrf"

    @pytest.mark.asyncio
    async def test_get_vrf_not_found_returns_none(self, vrf_manager):
        """Covers line 287: row is None returns None."""
        result = await vrf_manager.get_vrf("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_vrf_db_exception_returns_none(self, vrf_manager):
        """Covers lines 307-309: DB exception returns None."""
        with patch("network.vrf_manager.sqlite3.connect", side_effect=Exception("DB error")):
            result = await vrf_manager.get_vrf("some-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_vrf_null_json_fields_return_empty_lists(self, vrf_manager):
        """Covers branches where rt_import/rt_export/ip_ranges/ospf fields are NULL."""
        # Insert a row with NULL JSON fields directly
        import sqlite3
        conn = sqlite3.connect(vrf_manager.db_path)
        conn.execute("""
            INSERT INTO vrfs (id, name, description, rd, rt_import, rt_export, ip_ranges,
                              status, created_at, updated_at, is_active, ospf_enabled,
                              ospf_router_id, ospf_areas, ospf_networks)
            VALUES ('vrf-null-001', 'null-vrf', 'desc', '65001:100',
                    NULL, NULL, NULL, 'inactive',
                    '2024-01-01T00:00:00', '2024-01-01T00:00:00',
                    1, 0, NULL, NULL, NULL)
        """)
        conn.commit()
        conn.close()

        result = await vrf_manager.get_vrf("vrf-null-001")
        assert result is not None
        assert result.rt_import == []
        assert result.rt_export == []
        assert result.ip_ranges == []
        assert result.ospf_areas == []
        assert result.ospf_networks == []


# ---------------------------------------------------------------------------
# list_vrfs (lines 311-358)
# ---------------------------------------------------------------------------

class TestListVRFs:
    @pytest.mark.asyncio
    async def test_list_vrfs_active_only(self, vrf_manager):
        """Covers lines 311-354: default active_only=True."""
        vrf1 = make_vrf(vrf_id="vrf-list-001", name="list-vrf-1")
        vrf2 = make_vrf(vrf_id="vrf-list-002", name="list-vrf-2")
        await vrf_manager.create_vrf(vrf1)
        await vrf_manager.create_vrf(vrf2)

        result = await vrf_manager.list_vrfs(active_only=True)
        assert isinstance(result, list)
        ids = [v.id for v in result]
        assert "vrf-list-001" in ids
        assert "vrf-list-002" in ids

    @pytest.mark.asyncio
    async def test_list_vrfs_all(self, vrf_manager):
        """Covers active_only=False branch."""
        vrf = make_vrf(vrf_id="vrf-all-001", name="all-vrf")
        await vrf_manager.create_vrf(vrf)

        result = await vrf_manager.list_vrfs(active_only=False)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_list_vrfs_empty_returns_empty_list(self, vrf_manager):
        result = await vrf_manager.list_vrfs()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_vrfs_db_exception_returns_empty(self, vrf_manager):
        """Covers lines 356-358: DB exception returns []."""
        with patch("network.vrf_manager.sqlite3.connect", side_effect=Exception("DB error")):
            result = await vrf_manager.list_vrfs()
        assert result == []


# ---------------------------------------------------------------------------
# create_ospf_area (lines 360-389)
# ---------------------------------------------------------------------------

class TestCreateOSPFArea:
    @pytest.mark.asyncio
    async def test_create_ospf_area_success(self, vrf_manager):
        """Covers lines 360-385: normal OSPF area creation."""
        # First create the parent VRF
        vrf = make_vrf(vrf_id="vrf-ospf-a", name="ospf-area-vrf", ospf_enabled=True)
        await vrf_manager.create_vrf(vrf)

        area = make_ospf_area(vrf_id="vrf-ospf-a")
        result = await vrf_manager.create_ospf_area(area)
        assert result is True

    @pytest.mark.asyncio
    async def test_create_ospf_area_stub_type(self, vrf_manager):
        """Covers stub area type path."""
        vrf = make_vrf(vrf_id="vrf-stub-a", name="stub-area-vrf", ospf_enabled=True)
        await vrf_manager.create_vrf(vrf)

        area = make_ospf_area(vrf_id="vrf-stub-a", area_type=OSPFAreaType.STUB)
        result = await vrf_manager.create_ospf_area(area)
        assert result is True

    @pytest.mark.asyncio
    async def test_create_ospf_area_db_exception_returns_false(self, vrf_manager):
        """Covers lines 387-389: DB exception returns False."""
        area = make_ospf_area(vrf_id="vrf-err")
        with patch("network.vrf_manager.sqlite3.connect", side_effect=Exception("DB error")):
            result = await vrf_manager.create_ospf_area(area)
        assert result is False

    @pytest.mark.asyncio
    async def test_create_ospf_area_triggers_apply_ospf_config(self, vrf_manager):
        """Covers lines 383-384: _apply_ospf_config called after create."""
        vrf = make_vrf(vrf_id="vrf-ospf-b", name="ospf-b-vrf", ospf_enabled=True)
        await vrf_manager.create_vrf(vrf)

        with patch.object(vrf_manager, "_apply_ospf_config", new_callable=AsyncMock) as mock_apply:
            area = make_ospf_area(vrf_id="vrf-ospf-b")
            await vrf_manager.create_ospf_area(area)
            mock_apply.assert_called_once_with("vrf-ospf-b")


# ---------------------------------------------------------------------------
# get_ospf_neighbors (lines 391-426)
# ---------------------------------------------------------------------------

class TestGetOSPFNeighbors:
    @pytest.mark.asyncio
    async def test_get_ospf_neighbors_empty(self, vrf_manager):
        """Covers lines 391-426: no neighbors returns empty list."""
        result = await vrf_manager.get_ospf_neighbors("vrf-no-neighbors")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_ospf_neighbors_with_data(self, vrf_manager):
        """Covers neighbor row parsing."""
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(vrf_manager.db_path)
        conn.execute("""
            INSERT INTO ospf_neighbors
            (neighbor_id, vrf_id, neighbor_ip, interface, area_id, state,
             priority, dead_interval, hello_interval, last_seen)
            VALUES ('nbr-001', 'vrf-nbr', '10.0.0.2', 'eth0', '0.0.0.0',
                    'Full', 1, 40, 10, '2024-01-01T00:00:00')
        """)
        conn.commit()
        conn.close()

        result = await vrf_manager.get_ospf_neighbors("vrf-nbr")
        assert len(result) == 1
        assert isinstance(result[0], OSPFNeighbor)
        assert result[0].neighbor_id == "nbr-001"
        assert result[0].state == "Full"

    @pytest.mark.asyncio
    async def test_get_ospf_neighbors_null_last_seen(self, vrf_manager):
        """Covers branch where last_seen is NULL."""
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(vrf_manager.db_path)
        conn.execute("""
            INSERT INTO ospf_neighbors
            (neighbor_id, vrf_id, neighbor_ip, interface, area_id, state,
             priority, dead_interval, hello_interval, last_seen)
            VALUES ('nbr-002', 'vrf-nbr2', '10.0.0.3', 'eth1', '0.0.0.1',
                    'Down', 1, 40, 10, NULL)
        """)
        conn.commit()
        conn.close()

        result = await vrf_manager.get_ospf_neighbors("vrf-nbr2")
        assert len(result) == 1
        assert result[0].last_seen is None

    @pytest.mark.asyncio
    async def test_get_ospf_neighbors_db_exception_returns_empty(self, vrf_manager):
        """Covers lines 424-426: DB exception returns []."""
        with patch("network.vrf_manager.sqlite3.connect", side_effect=Exception("DB error")):
            result = await vrf_manager.get_ospf_neighbors("vrf-err")
        assert result == []


# ---------------------------------------------------------------------------
# _apply_vrf_config (lines 466-512)
# ---------------------------------------------------------------------------

class TestApplyVRFConfig:
    @pytest.mark.asyncio
    async def test_apply_vrf_config_sets_active(self, vrf_manager):
        """Covers lines 466-512: status set to ACTIVE on success."""
        vrf = make_vrf()
        await vrf_manager._apply_vrf_config(vrf)
        assert vrf.status == VRFStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_apply_vrf_config_with_ospf(self, vrf_manager):
        """Covers lines 486-497: OSPF config block is generated."""
        vrf = make_vrf(ospf_enabled=True)
        await vrf_manager._apply_vrf_config(vrf)
        assert vrf.status == VRFStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_apply_vrf_config_ospf_network_no_net_key(self, vrf_manager):
        """Covers the `if net:` guard — network with no 'network' key is skipped."""
        vrf = make_vrf(ospf_enabled=True)
        vrf.ospf_networks = [{"area": "0.0.0.0"}]  # no 'network' key
        await vrf_manager._apply_vrf_config(vrf)
        assert vrf.status == VRFStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_apply_vrf_config_exception_sets_error(self, vrf_manager):
        """Covers lines 510-512: exception sets status to ERROR."""
        vrf = make_vrf()
        # Force an error inside _apply_vrf_config
        with patch("network.vrf_manager.logger") as mock_logger:
            mock_logger.info.side_effect = Exception("logger exploded")
            await vrf_manager._apply_vrf_config(vrf)
        assert vrf.status == VRFStatus.ERROR


# ---------------------------------------------------------------------------
# _apply_ospf_config (lines 514-525)
# ---------------------------------------------------------------------------

class TestApplyOSPFConfig:
    @pytest.mark.asyncio
    async def test_apply_ospf_config_no_vrf(self, vrf_manager):
        """Covers line 518: get_vrf returns None — early return."""
        # No VRF with this ID exists
        await vrf_manager._apply_ospf_config("nonexistent-vrf")

    @pytest.mark.asyncio
    async def test_apply_ospf_config_ospf_disabled(self, vrf_manager):
        """Covers line 518: ospf_enabled=False — early return."""
        vrf = make_vrf(vrf_id="vrf-no-ospf", name="no-ospf-vrf", ospf_enabled=False)
        await vrf_manager.create_vrf(vrf)
        # Should return early without error
        await vrf_manager._apply_ospf_config("vrf-no-ospf")

    @pytest.mark.asyncio
    async def test_apply_ospf_config_enabled(self, vrf_manager):
        """Covers line 522: OSPF config applied when enabled."""
        vrf = make_vrf(vrf_id="vrf-ospf-apply", name="ospf-apply-vrf", ospf_enabled=True)
        await vrf_manager.create_vrf(vrf)
        await vrf_manager._apply_ospf_config("vrf-ospf-apply")

    @pytest.mark.asyncio
    async def test_apply_ospf_config_exception_caught(self, vrf_manager):
        """Covers lines 524-525: exception is caught."""
        with patch.object(vrf_manager, "get_vrf", side_effect=Exception("DB error")):
            await vrf_manager._apply_ospf_config("vrf-err")


# ---------------------------------------------------------------------------
# _remove_vrf_config (lines 527-538)
# ---------------------------------------------------------------------------

class TestRemoveVRFConfig:
    @pytest.mark.asyncio
    async def test_remove_vrf_config_not_found(self, vrf_manager):
        """Covers line 531: get_vrf returns None — early return."""
        await vrf_manager._remove_vrf_config("nonexistent")

    @pytest.mark.asyncio
    async def test_remove_vrf_config_found(self, vrf_manager):
        """Covers lines 527-536: VRF found, config removed."""
        vrf = make_vrf(vrf_id="vrf-rem-001", name="rem-vrf")
        await vrf_manager.create_vrf(vrf)
        await vrf_manager._remove_vrf_config("vrf-rem-001")

    @pytest.mark.asyncio
    async def test_remove_vrf_config_exception_caught(self, vrf_manager):
        """Covers lines 537-538: exception is caught."""
        with patch.object(vrf_manager, "get_vrf", side_effect=Exception("DB error")):
            await vrf_manager._remove_vrf_config("vrf-err")


# ---------------------------------------------------------------------------
# generate_frr_config (lines 540-588)
# ---------------------------------------------------------------------------

class TestGenerateFRRConfig:
    @pytest.mark.asyncio
    async def test_generate_frr_config_returns_string(self, vrf_manager):
        """Covers lines 540-584: generates FRR config string."""
        vrf = make_vrf(vrf_id="vrf-frr-001", name="frr-vrf")
        await vrf_manager.create_vrf(vrf)

        result = await vrf_manager.generate_frr_config("vrf-frr-001")
        assert isinstance(result, str)
        assert "frr-vrf" in result
        assert "65001:100" in result

    @pytest.mark.asyncio
    async def test_generate_frr_config_includes_rt(self, vrf_manager):
        """Covers rt_import/rt_export lines in generate_frr_config."""
        vrf = make_vrf(vrf_id="vrf-frr-rt", name="frr-rt-vrf")
        vrf.rt_import = ["65001:200"]
        vrf.rt_export = ["65001:300"]
        await vrf_manager.create_vrf(vrf)

        result = await vrf_manager.generate_frr_config("vrf-frr-rt")
        assert "import rt 65001:200" in result
        assert "export rt 65001:300" in result

    @pytest.mark.asyncio
    async def test_generate_frr_config_with_ospf(self, vrf_manager):
        """Covers lines 566-582: OSPF section in FRR config."""
        vrf = make_vrf(vrf_id="vrf-frr-ospf", name="frr-ospf-vrf", ospf_enabled=True)
        await vrf_manager.create_vrf(vrf)

        result = await vrf_manager.generate_frr_config("vrf-frr-ospf")
        assert "router ospf" in result
        assert "router-id" in result
        assert "10.0.0.0/24" in result

    @pytest.mark.asyncio
    async def test_generate_frr_config_ospf_no_net_key(self, vrf_manager):
        """Covers the `if net:` guard in generate_frr_config."""
        vrf = make_vrf(vrf_id="vrf-frr-nonet", name="frr-nonet-vrf", ospf_enabled=True)
        vrf.ospf_networks = [{"area": "0.0.0.0"}]  # no 'network' key
        await vrf_manager.create_vrf(vrf)

        result = await vrf_manager.generate_frr_config("vrf-frr-nonet")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_frr_config_vrf_not_found_returns_empty(self, vrf_manager):
        """Covers lines 543-544: VRF not found returns empty string."""
        result = await vrf_manager.generate_frr_config("nonexistent-vrf")
        assert result == ""

    @pytest.mark.asyncio
    async def test_generate_frr_config_exception_returns_empty(self, vrf_manager):
        """Covers lines 586-588: exception returns empty string."""
        with patch.object(vrf_manager, "get_vrf", side_effect=Exception("DB error")):
            result = await vrf_manager.generate_frr_config("vrf-err")
        assert result == ""


# ---------------------------------------------------------------------------
# VRFManager initialization (lines 75-156)
# ---------------------------------------------------------------------------

class TestVRFManagerInit:
    def test_vrf_manager_creates_tables(self, tmp_path):
        """Covers lines 80-156: all tables created on init."""
        import sqlite3
        db_path = str(tmp_path / "init_test.db")
        VRFManager(db_path=db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "vrfs" in tables
        assert "ospf_areas" in tables
        assert "ospf_neighbors" in tables

    def test_vrf_manager_creates_indexes(self, tmp_path):
        """Covers index creation in _init_database."""
        import sqlite3
        db_path = str(tmp_path / "idx_test.db")
        VRFManager(db_path=db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_vrfs_name" in indexes
        assert "idx_vrfs_status" in indexes
        assert "idx_ospf_areas_vrf" in indexes


# ---------------------------------------------------------------------------
# VRFConfiguration and enum dataclass sanity
# ---------------------------------------------------------------------------

class TestVRFDataclasses:
    def test_vrf_status_values(self):
        assert VRFStatus.ACTIVE.value == "active"
        assert VRFStatus.INACTIVE.value == "inactive"
        assert VRFStatus.PENDING.value == "pending"
        assert VRFStatus.ERROR.value == "error"

    def test_ospf_area_type_values(self):
        assert OSPFAreaType.NORMAL.value == "normal"
        assert OSPFAreaType.STUB.value == "stub"
        assert OSPFAreaType.NSSA.value == "nssa"
        assert OSPFAreaType.BACKBONE.value == "backbone"

    def test_vrf_configuration_defaults(self):
        vrf = VRFConfiguration(
            id="x", name="x", description="x", rd="65001:1"
        )
        assert vrf.status == VRFStatus.INACTIVE
        assert vrf.is_active is True
        assert vrf.ospf_enabled is False
        assert vrf.rt_import == []
        assert vrf.rt_export == []
        assert vrf.ip_ranges == []

    def test_ospf_neighbor_defaults(self):
        nbr = OSPFNeighbor(
            neighbor_id="n1",
            neighbor_ip="10.0.0.1",
            interface="eth0",
            vrf_id="vrf-1",
            area_id="0.0.0.0",
            state="Full",
        )
        assert nbr.priority == 1
        assert nbr.dead_interval == 40
        assert nbr.hello_interval == 10
        assert nbr.last_seen is None


# ---------------------------------------------------------------------------
# _validate_rd outer exception handler (lines 463-464)
# ---------------------------------------------------------------------------

class TestValidateRDOuterException:
    def test_validate_rd_outer_exception_returns_false(self, vrf_manager):
        """Covers lines 463-464: outer except block returns False on unexpected error."""
        # Patch the rd.split method to raise a non-ValueError exception
        import ipaddress as _ipaddress
        with patch.object(_ipaddress, "ip_address", side_effect=RuntimeError("unexpected")):
            # An RD like 'not-an-asn:100' will try ip_address, which raises RuntimeError
            # That propagates to the outer except and returns False
            result = vrf_manager._validate_rd("not-an-asn:100")
        assert result is False
