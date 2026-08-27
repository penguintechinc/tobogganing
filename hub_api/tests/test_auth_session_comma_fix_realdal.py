"""Integration tests for session auth comma-syntax fix using real penguin-dal.

These tests verify the fix in _validate_and_store_session (line 243-247) where
the query was changed from comma-syntax `dal(a, b, c)` to `&`-syntax
`dal((users.id==...) & (users.tenant==...) & (users.is_active==True))`.

The comma-syntax raises TypeError: AsyncDB.__call__ takes 1 argument, which is
caught by the broad except clause and returns (None, None). The discriminating
test is the POSITIVE case: an ACTIVE user MUST authenticate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from quart import Quart

from hub_api.auth.middleware import _validate_and_store_session
from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def test_app(real_dal: Any) -> Quart:
    """Create a test Quart app with real_dal configured."""
    app = Quart(__name__)
    app.config["TESTING"] = True
    app.config["DAL"] = real_dal
    return app


@pytest.mark.asyncio
async def test_validate_session_authenticates_active_user_realdal(
    real_dal: Any, test_app: Quart
) -> None:
    """DISCRIMINATING TEST: Active user with valid session MUST authenticate.

    This test FAILS when the source code uses comma-syntax (TypeError caught
    by except clause returns None), and PASSES when using &-syntax (proper query).

    Verifies:
    - User with is_active=True is found via the tenant-scoped query
    - Session token matches and is not expired
    - Returns (user_dict, tenant) where user_dict is not None
    """
    tenant = "test-tenant-active"
    user_id = str(uuid4())
    username = "active_user"
    email = "active@example.com"
    now = datetime.now(timezone.utc)

    # Seed user with is_active=True
    await real_dal.users.async_insert(
        id=user_id,
        username=username,
        email=email,
        password_hash="hashed_password",
        is_active=True,
        mfa_enabled=False,
        tenant=tenant,
        role="reporter",
        created_at=now,
        updated_at=now,
    )

    # Seed session
    session_token = str(uuid4())
    session_id = str(uuid4())
    expires_at = now + timedelta(hours=1)

    await real_dal.sessions.async_insert(
        id=session_id,
        user_id=user_id,
        tenant=tenant,
        token=session_token,
        created_at=now,
        expires_at=expires_at,
    )

    # Test: _validate_and_store_session must return the user dict
    async with test_app.app_context():
        user_dict, returned_tenant = await _validate_and_store_session(session_token)

    assert user_dict is not None, "Active user authentication failed"
    assert returned_tenant == tenant
    assert user_dict["id"] == user_id
    assert user_dict["username"] == username
    assert user_dict["email"] == email
    assert user_dict["is_active"] is True


@pytest.mark.asyncio
async def test_validate_session_rejects_deactivated_user_realdal(
    real_dal: Any, test_app: Quart
) -> None:
    """Semantic guard: Deactivated user is denied even with valid session.

    Verifies:
    - User with is_active=False fails the is_active check in the query
    - Returns (None, None)
    """
    tenant = "test-tenant-inactive"
    user_id = str(uuid4())
    username = "inactive_user"
    email = "inactive@example.com"
    now = datetime.now(timezone.utc)

    # Seed user with is_active=False
    await real_dal.users.async_insert(
        id=user_id,
        username=username,
        email=email,
        password_hash="hashed_password",
        is_active=False,  # Deactivated
        mfa_enabled=False,
        tenant=tenant,
        role="reporter",
        created_at=now,
        updated_at=now,
    )

    # Seed session
    session_token = str(uuid4())
    session_id = str(uuid4())
    expires_at = now + timedelta(hours=1)

    await real_dal.sessions.async_insert(
        id=session_id,
        user_id=user_id,
        tenant=tenant,
        token=session_token,
        created_at=now,
        expires_at=expires_at,
    )

    # Test: _validate_and_store_session must return (None, None)
    async with test_app.app_context():
        user_dict, returned_tenant = await _validate_and_store_session(session_token)

    assert user_dict is None, "Deactivated user should be denied"
    assert returned_tenant is None


@pytest.mark.asyncio
async def test_count_active_devices_online_only_realdal(real_dal: Any) -> None:
    """Verify count_active_devices returns ONLY online devices.

    Tests the device_manager.py fix (line 375-378) where the query was changed
    from comma-syntax `db(a, b)` to `&`-syntax `db((devices.tenant==...) & (...))`.

    Verifies:
    - count_active_devices returns only devices with status="online"
    - Offline devices are excluded
    """
    tenant = "test-tenant-devices"
    now = datetime.now(timezone.utc)

    # Create DeviceManager
    manager = DeviceManager(real_dal, tenant)

    # Seed online devices
    for i in range(3):
        await real_dal.devices.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            org_unit_id=None,
            user_id=None,
            name=f"device-online-{i}",
            serial=f"SN-ONLINE-{i}",
            hostname=f"host-online-{i}",
            os="Linux",
            status="online",
            last_heartbeat=now,
            metadata=None,
            created_at=now,
            updated_at=now,
        )

    # Seed offline devices
    for i in range(2):
        await real_dal.devices.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            org_unit_id=None,
            user_id=None,
            name=f"device-offline-{i}",
            serial=f"SN-OFFLINE-{i}",
            hostname=f"host-offline-{i}",
            os="Linux",
            status="offline",
            last_heartbeat=now,
            metadata=None,
            created_at=now,
            updated_at=now,
        )

    # Test: count_active_devices must return only online count
    active_count = await manager.count_active_devices()
    assert active_count == 3, f"Expected 3 online devices, got {active_count}"
