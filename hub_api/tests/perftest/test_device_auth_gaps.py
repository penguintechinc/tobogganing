"""Coverage backfill for perftest_cluster/services/device_auth.py.

This module (the global, tenant-blind device authentication helper used by
devices.py/client_config.py/tests.py) had no dedicated direct test file
before this: it was only exercised indirectly via API-level success paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from penguin_dal import AsyncDB

from hub_api.modules.perftest_cluster.services.device_auth import (
    authenticate_device_global,
)
from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager


@pytest.mark.asyncio
async def test_authenticate_device_global_empty_key(real_dal: AsyncDB) -> None:
    """A blank/whitespace API key is rejected before any query."""
    assert await authenticate_device_global(real_dal, "") is None
    assert await authenticate_device_global(real_dal, "   ") is None


@pytest.mark.asyncio
async def test_authenticate_device_global_unknown_key(real_dal: AsyncDB) -> None:
    """An unknown API key returns None."""
    assert await authenticate_device_global(real_dal, "not-a-real-key") is None


@pytest.mark.asyncio
async def test_authenticate_device_global_revoked_key(real_dal: AsyncDB) -> None:
    """A revoked API key fails global authentication."""
    from datetime import datetime, timezone

    tenant = "tenant-global-revoked"
    mgr = DeviceManager(real_dal, tenant)
    device, api_key = await mgr.register_device({"name": "d", "serial": "SN"})

    await real_dal(
        (real_dal.device_api_keys.device_id == device.id)
        & (real_dal.device_api_keys.tenant == tenant)
    ).update(revoked_at=datetime.now(timezone.utc))

    result = await authenticate_device_global(real_dal, api_key)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_device_global_success(real_dal: AsyncDB) -> None:
    """A valid, non-revoked key returns (device_row, tenant)."""
    tenant = "tenant-global-ok"
    mgr = DeviceManager(real_dal, tenant)
    device, api_key = await mgr.register_device({"name": "d", "serial": "SN"})

    result = await authenticate_device_global(real_dal, api_key)
    assert result is not None
    device_row, returned_tenant = result
    assert device_row.id == device.id
    assert returned_tenant == tenant


@pytest.mark.asyncio
async def test_authenticate_device_global_device_row_missing() -> None:
    """A valid key hash whose device row is missing (orphaned key) returns None."""
    key_row = MagicMock()
    key_row.revoked_at = None
    key_row.device_id = "orphan-device"
    key_row.tenant = "tenant-orphan"
    key_row.api_key_hash = None  # filled in below to match computed hash

    import hashlib

    api_key = "orphan-raw-key"
    key_row.api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    key_rowset = MagicMock()
    key_rowset.first.return_value = key_row

    device_rowset = MagicMock()
    device_rowset.first.return_value = None  # device missing

    db = MagicMock()

    async def _select(*args: object, **kwargs: object) -> MagicMock:
        # First select() call is for device_api_keys, second for devices.
        if not _select.called:  # type: ignore[attr-defined]
            _select.called = True  # type: ignore[attr-defined]
            return key_rowset
        return device_rowset

    _select.called = False  # type: ignore[attr-defined]
    query_proxy = MagicMock()
    query_proxy.select = _select
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    result = await authenticate_device_global(db, api_key)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_device_global_query_exception_fail_closed() -> None:
    """A query error during authentication fails closed (returns None)."""
    bad_db = MagicMock()
    bad_db.device_api_keys.api_key_hash = MagicMock()
    bad_db.device_api_keys.api_key_hash.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    result = await authenticate_device_global(bad_db, "some-key")
    assert result is None
