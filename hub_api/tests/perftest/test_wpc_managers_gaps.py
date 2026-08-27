"""Coverage backfill for perftest_cluster services: device_manager.py,
org_unit_manager.py, enrollment_manager.py.

Targets initialize/shutdown lifecycle logs, not-found branches, the
revoked-key auth rejection, remove_device/count_active_devices, and the
verify_secret fail-closed exception path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.enrollment_manager import (
    EnrollmentManager,
)
from hub_api.modules.perftest_cluster.services.org_unit_manager import OrgUnitManager

# ---------------------------------------------------------------------------
# DeviceManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_device_manager_initialize_and_shutdown(real_dal: AsyncDB) -> None:
    """initialize()/shutdown() succeed without raising."""
    mgr = DeviceManager(real_dal, "tenant-lifecycle")
    await mgr.initialize()
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_authenticate_device_revoked_key_rejected(real_dal: AsyncDB) -> None:
    """A revoked API key fails authentication."""
    tenant = "tenant-revoked"
    mgr = DeviceManager(real_dal, tenant)
    device, api_key = await mgr.register_device({"name": "d", "serial": "SN"})

    # Revoke the key directly.
    await real_dal(
        (real_dal.device_api_keys.device_id == device.id)
        & (real_dal.device_api_keys.tenant == tenant)
    ).update(revoked_at=datetime.now(timezone.utc))

    result = await mgr.authenticate_device(api_key)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_device_empty_key_rejected(real_dal: AsyncDB) -> None:
    """An empty/blank API key is rejected before any query."""
    mgr = DeviceManager(real_dal, "tenant-empty-key")
    assert await mgr.authenticate_device("") is None
    assert await mgr.authenticate_device("   ") is None


@pytest.mark.asyncio
async def test_authenticate_device_unknown_key(real_dal: AsyncDB) -> None:
    """An unknown API key returns None."""
    mgr = DeviceManager(real_dal, "tenant-unknown-key")
    assert await mgr.authenticate_device("not-a-real-key") is None


@pytest.mark.asyncio
async def test_authenticate_device_query_error_fail_closed() -> None:
    """A query error during authentication fails closed (returns None)."""
    bad_db = MagicMock()
    bad_db.device_api_keys.api_key_hash = MagicMock()
    bad_db.device_api_keys.api_key_hash.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    mgr = DeviceManager(bad_db, "tenant-err")
    result = await mgr.authenticate_device("some-key")
    assert result is None


@pytest.mark.asyncio
async def test_update_status_not_found(real_dal: AsyncDB) -> None:
    """update_status returns None for an unknown device_id."""
    mgr = DeviceManager(real_dal, "tenant-status-nf")
    assert await mgr.update_status("ghost", "offline") is None


@pytest.mark.asyncio
async def test_heartbeat_not_found(real_dal: AsyncDB) -> None:
    """heartbeat returns None for an unknown device_id."""
    mgr = DeviceManager(real_dal, "tenant-hb-nf")
    assert await mgr.heartbeat("ghost") is None


@pytest.mark.asyncio
async def test_remove_device_not_found_and_success(real_dal: AsyncDB) -> None:
    """remove_device returns False for unknown id, True + removes on success."""
    mgr = DeviceManager(real_dal, "tenant-remove")
    assert await mgr.remove_device("ghost") is False

    device, _key = await mgr.register_device({"name": "d", "serial": "SN"})
    assert await mgr.remove_device(device.id) is True
    assert await mgr.get_device(device.id) is None


@pytest.mark.asyncio
async def test_count_active_devices(real_dal: AsyncDB) -> None:
    """count_active_devices only counts devices with status='online'."""
    tenant = "tenant-count"
    mgr = DeviceManager(real_dal, tenant)
    d1, _ = await mgr.register_device({"name": "d1", "serial": "SN1"})  # online by default
    await mgr.register_device({"name": "d2", "serial": "SN2"})
    await mgr.update_status(d1.id, "offline")

    count = await mgr.count_active_devices()
    assert count == 1


@pytest.mark.asyncio
async def test_list_devices_with_org_unit_filter(real_dal: AsyncDB) -> None:
    """list_devices filters by org_unit_id when provided."""
    tenant = "tenant-list-ou"
    mgr = DeviceManager(real_dal, tenant)
    await mgr.register_device({"name": "ou1-dev", "serial": "S1", "org_unit_id": "ou-1"})
    await mgr.register_device({"name": "ou2-dev", "serial": "S2", "org_unit_id": "ou-2"})

    ou1_only = await mgr.list_devices(org_unit_id="ou-1")
    assert len(ou1_only) == 1
    assert ou1_only[0].name == "ou1-dev"


# ---------------------------------------------------------------------------
# OrgUnitManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_unit_manager_initialize_and_shutdown(real_dal: AsyncDB) -> None:
    """initialize()/shutdown() succeed without raising."""
    mgr = OrgUnitManager(real_dal, "tenant-ou-lifecycle")
    await mgr.initialize()
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_get_ou_not_found(real_dal: AsyncDB) -> None:
    """get_ou returns None for an unknown id."""
    mgr = OrgUnitManager(real_dal, "tenant-ou-nf")
    assert await mgr.get_ou("ghost") is None


@pytest.mark.asyncio
async def test_update_ou_not_found(real_dal: AsyncDB) -> None:
    """update_ou returns None for an unknown id."""
    mgr = OrgUnitManager(real_dal, "tenant-ou-upd-nf")
    assert await mgr.update_ou("ghost", {"name": "x"}) is None


@pytest.mark.asyncio
async def test_delete_ou_not_found_and_success(real_dal: AsyncDB) -> None:
    """delete_ou returns False for unknown id, True + removes on success."""
    mgr = OrgUnitManager(real_dal, "tenant-ou-del")
    assert await mgr.delete_ou("ghost") is False

    ou = await mgr.create_ou({"name": "to-delete"})
    assert await mgr.delete_ou(ou.id) is True
    assert await mgr.get_ou(ou.id) is None


@pytest.mark.asyncio
async def test_list_ous_with_parent_filter(real_dal: AsyncDB) -> None:
    """list_ous filters by parent_id when provided."""
    tenant = "tenant-ou-list"
    mgr = OrgUnitManager(real_dal, tenant)
    parent = await mgr.create_ou({"name": "parent"})
    await mgr.create_ou({"name": "child", "parent_id": parent.id})
    await mgr.create_ou({"name": "unrelated"})

    children = await mgr.list_ous(parent_id=parent.id)
    assert len(children) == 1
    assert children[0].name == "child"


# ---------------------------------------------------------------------------
# EnrollmentManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrollment_manager_initialize_and_shutdown(real_dal: AsyncDB) -> None:
    """initialize()/shutdown() succeed without raising."""
    mgr = EnrollmentManager(real_dal, "tenant-em-lifecycle")
    await mgr.initialize()
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_get_secret_not_found(real_dal: AsyncDB) -> None:
    """get_secret returns None for an unknown id."""
    mgr = EnrollmentManager(real_dal, "tenant-em-nf")
    assert await mgr.get_secret("ghost") is None


@pytest.mark.asyncio
async def test_verify_secret_unknown_returns_none(real_dal: AsyncDB) -> None:
    """verify_secret returns None for an unknown raw secret."""
    mgr = EnrollmentManager(real_dal, "tenant-em-verify")
    assert await mgr.verify_secret("not-a-real-secret") is None


@pytest.mark.asyncio
async def test_verify_secret_expired_returns_none(real_dal: AsyncDB) -> None:
    """verify_secret returns None for an expired secret."""
    tenant = "tenant-em-expired"
    mgr = EnrollmentManager(real_dal, tenant)
    _secret, raw = await mgr.create_secret(
        org_unit_id=None,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        created_by=None,
    )
    assert await mgr.verify_secret(raw) is None


@pytest.mark.asyncio
async def test_verify_secret_exception_fail_closed() -> None:
    """A query error during verify_secret fails closed (returns None)."""
    bad_db = MagicMock()
    bad_db.device_enrollment_secrets.tenant = MagicMock()
    bad_db.device_enrollment_secrets.tenant.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    mgr = EnrollmentManager(bad_db, "tenant-em-err")
    result = await mgr.verify_secret("whatever")
    assert result is None
