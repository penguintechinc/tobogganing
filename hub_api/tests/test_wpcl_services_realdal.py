"""Real DAL integration tests for WaddlePerf cluster service managers.

Tests use the real_dal fixture to exercise actual async penguin-dal API
against a migrated SQLite database. This is the anti-mock validation that
catches schema mismatches, wrong API usage, and tenant isolation bugs.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from hub_api.modules.perftest_cluster.services.device_manager import DeviceManager
from hub_api.modules.perftest_cluster.services.org_unit_manager import OrgUnitManager
from hub_api.modules.perftest_cluster.services.enrollment_manager import EnrollmentManager
from hub_api.modules.perftest_cluster.services.test_manager import TestManager
from hub_api.modules.perftest_cluster.services.device_auth import authenticate_device_global


@pytest.mark.asyncio
async def test_device_manager_create_and_get(real_dal) -> None:
    """Test DeviceManager create and get operations with real DAL."""
    mgr = DeviceManager(real_dal, tenant_id="tenant1")

    device_info = {
        "name": "Device1",
        "serial": "SN123456",
        "hostname": "device1.local",
        "os": "Linux",
        "device_metadata": {"version": "1.0"},
    }

    device, api_key = await mgr.register_device(device_info)
    assert device.id is not None
    assert device.tenant == "tenant1"
    assert device.name == "Device1"
    assert device.serial == "SN123456"
    assert len(api_key) > 0

    # Fetch the device
    fetched = await mgr.get_device(device.id)
    assert fetched is not None
    assert fetched.id == device.id
    assert fetched.name == "Device1"


@pytest.mark.asyncio
async def test_device_manager_tenant_isolation(real_dal) -> None:
    """Test that devices are isolated per tenant."""
    mgr_t1 = DeviceManager(real_dal, tenant_id="tenant1")
    mgr_t2 = DeviceManager(real_dal, tenant_id="tenant2")

    device_info = {
        "name": "Device1",
        "serial": "SN789012",
        "hostname": "device1.local",
        "os": "Linux",
    }

    device_t1, _ = await mgr_t1.register_device(device_info)

    # Tenant2 should not see tenant1's device
    fetched_in_t2 = await mgr_t2.get_device(device_t1.id)
    assert fetched_in_t2 is None

    # But tenant1 should see it
    fetched_in_t1 = await mgr_t1.get_device(device_t1.id)
    assert fetched_in_t1 is not None


@pytest.mark.asyncio
async def test_device_manager_authenticate(real_dal) -> None:
    """Test device authentication via API key."""
    mgr = DeviceManager(real_dal, tenant_id="tenant1")

    device_info = {
        "name": "AuthDevice",
        "serial": "SNAUTH001",
        "hostname": "auth.local",
        "os": "Linux",
    }

    device, api_key = await mgr.register_device(device_info)

    # Authenticate with correct key
    authenticated = await mgr.authenticate_device(api_key)
    assert authenticated is not None
    assert authenticated.id == device.id
    assert authenticated.serial == "SNAUTH001"

    # Authenticate with incorrect key
    bad_auth = await mgr.authenticate_device("bad-key-12345")
    assert bad_auth is None

    # Authenticate with empty key
    empty_auth = await mgr.authenticate_device("")
    assert empty_auth is None


@pytest.mark.asyncio
async def test_device_manager_list_and_update(real_dal) -> None:
    """Test device listing and status updates."""
    mgr = DeviceManager(real_dal, tenant_id="tenant1")

    # Create 3 devices
    for i in range(3):
        device_info = {
            "name": f"Device{i}",
            "serial": f"SN{i}",
            "hostname": f"device{i}.local",
            "os": "Linux",
        }
        await mgr.register_device(device_info)

    # List all devices
    devices = await mgr.list_devices(limit=10, offset=0)
    assert len(devices) == 3

    # Update status
    if devices:
        device = devices[0]
        updated = await mgr.update_status(device.id, "offline")
        assert updated is not None
        assert updated.status == "offline"


@pytest.mark.asyncio
async def test_device_manager_heartbeat(real_dal) -> None:
    """Test device heartbeat recording."""
    mgr = DeviceManager(real_dal, tenant_id="tenant1")

    device_info = {
        "name": "HBDevice",
        "serial": "SNHB001",
        "hostname": "hb.local",
        "os": "Linux",
    }

    device, _ = await mgr.register_device(device_info)

    # Record heartbeat
    updated = await mgr.heartbeat(device.id)
    assert updated is not None
    assert updated.status == "online"
    assert updated.last_heartbeat is not None


@pytest.mark.asyncio
async def test_device_manager_delete(real_dal) -> None:
    """Test device deletion."""
    mgr = DeviceManager(real_dal, tenant_id="tenant1")

    device_info = {
        "name": "DeleteMe",
        "serial": "SNDEL001",
        "hostname": "del.local",
        "os": "Linux",
    }

    device, _ = await mgr.register_device(device_info)

    # Delete device
    success = await mgr.remove_device(device.id)
    assert success is True

    # Verify it's gone
    fetched = await mgr.get_device(device.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_org_unit_manager_crud(real_dal) -> None:
    """Test OrgUnitManager create, read, update, delete."""
    mgr = OrgUnitManager(real_dal, tenant_id="tenant1")

    # Create OU
    ou_data = {
        "name": "Sales",
        "description": "Sales department",
        "is_active": True,
    }
    ou = await mgr.create_ou(ou_data)
    assert ou.id is not None
    assert ou.name == "Sales"
    assert ou.tenant == "tenant1"

    # Get OU
    fetched = await mgr.get_ou(ou.id)
    assert fetched is not None
    assert fetched.id == ou.id

    # Update OU
    update_data = {"name": "Sales & Marketing"}
    updated = await mgr.update_ou(ou.id, update_data)
    assert updated is not None
    assert updated.name == "Sales & Marketing"

    # Delete OU
    success = await mgr.delete_ou(ou.id)
    assert success is True

    # Verify deleted
    deleted_fetch = await mgr.get_ou(ou.id)
    assert deleted_fetch is None


@pytest.mark.asyncio
async def test_org_unit_manager_hierarchy(real_dal) -> None:
    """Test OU hierarchy with parent IDs."""
    mgr = OrgUnitManager(real_dal, tenant_id="tenant1")

    # Create parent OU
    parent_ou = await mgr.create_ou({"name": "Engineering"})

    # Create child OU
    child_data = {
        "name": "Backend",
        "parent_id": parent_ou.id,
    }
    child_ou = await mgr.create_ou(child_data)
    assert child_ou.parent_id == parent_ou.id

    # List children
    children = await mgr.list_ous(parent_id=parent_ou.id)
    assert len(children) == 1
    assert children[0].name == "Backend"


@pytest.mark.asyncio
async def test_enrollment_manager_secret_lifecycle(real_dal) -> None:
    """Test enrollment secret creation and verification."""
    mgr = EnrollmentManager(real_dal, tenant_id="tenant1")

    # Create secret
    expires_at = datetime.now(timezone.utc)
    secret, raw_secret = await mgr.create_secret(
        org_unit_id=None,
        expires_at=expires_at,
        created_by=None,
    )
    assert secret.id is not None
    assert len(raw_secret) > 0

    # Get secret
    fetched = await mgr.get_secret(secret.id)
    assert fetched is not None
    assert fetched.secret_hash == secret.secret_hash

    # Verify secret
    org_unit_id = await mgr.verify_secret(raw_secret)
    assert org_unit_id is None  # No org unit was associated

    # Verify with wrong secret
    bad_verify = await mgr.verify_secret("wrong-secret")
    assert bad_verify is None


@pytest.mark.asyncio
async def test_enrollment_manager_tenant_isolation(real_dal) -> None:
    """Test that enrollment secrets are isolated per tenant."""
    mgr_t1 = EnrollmentManager(real_dal, tenant_id="tenant1")
    mgr_t2 = EnrollmentManager(real_dal, tenant_id="tenant2")

    secret_t1, raw_t1 = await mgr_t1.create_secret(None, None, None)

    # Tenant2 should not see tenant1's secret
    fetched_in_t2 = await mgr_t2.get_secret(secret_t1.id)
    assert fetched_in_t2 is None

    # But tenant1 should see it
    fetched_in_t1 = await mgr_t1.get_secret(secret_t1.id)
    assert fetched_in_t1 is not None


@pytest.mark.asyncio
async def test_test_manager_crud(real_dal) -> None:
    """Test TestManager create, read, update, delete."""
    mgr = TestManager(real_dal, tenant="tenant1")
    device_id = str(uuid4())

    # Create test
    test_data = {
        "device_id": device_id,
        "test_type": "latency",
        "target": "8.8.8.8",
        "status": "pending",
    }
    test = await mgr.create_test(test_data)
    assert test.id is not None
    assert test.device_id == device_id
    assert test.tenant == "tenant1"

    # Get test
    fetched = await mgr.get_test(test.id)
    assert fetched is not None
    assert fetched.id == test.id

    # Record result
    result_data = {
        "status": "completed",
        "latency_ms": 25.5,
        "throughput": 1000.0,
    }
    updated = await mgr.record_result(test.id, result_data)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.latency_ms == 25.5

    # Delete test
    success = await mgr.delete_test(test.id)
    assert success is True

    # Verify deleted
    deleted_fetch = await mgr.get_test(test.id)
    assert deleted_fetch is None


@pytest.mark.asyncio
async def test_test_manager_list_with_filters(real_dal) -> None:
    """Test TestManager list with various filters."""
    mgr = TestManager(real_dal, tenant="tenant1")
    device_id = str(uuid4())

    # Create tests with different types and statuses
    for i in range(3):
        test_data = {
            "device_id": device_id,
            "test_type": "latency" if i % 2 == 0 else "throughput",
            "target": f"target{i}",
            "status": "completed" if i % 2 == 0 else "pending",
        }
        await mgr.create_test(test_data)

    # List all
    all_tests = await mgr.list_tests(limit=10, offset=0)
    assert len(all_tests) == 3

    # Filter by device
    device_tests = await mgr.list_results(device_id=device_id, limit=10)
    assert len(device_tests) == 3

    # Filter by type
    latency_tests = await mgr.list_results(test_type="latency", limit=10)
    assert len(latency_tests) >= 1

    # Filter by status
    pending_tests = await mgr.list_results(status="pending", limit=10)
    assert len(pending_tests) >= 1


@pytest.mark.asyncio
async def test_authenticate_device_global(real_dal) -> None:
    """Test global device authentication across tenants."""
    # Create device in tenant1
    mgr_t1 = DeviceManager(real_dal, tenant_id="tenant1")
    device_info = {
        "name": "GlobalDevice",
        "serial": "SNGLOBAL001",
        "hostname": "global.local",
        "os": "Linux",
    }
    device, api_key = await mgr_t1.register_device(device_info)

    # Authenticate globally (should work without knowing tenant)
    result = await authenticate_device_global(real_dal, api_key)
    assert result is not None
    device_row, tenant = result
    assert tenant == "tenant1"
    assert device_row.id == device.id

    # Try with bad key
    bad_result = await authenticate_device_global(real_dal, "bad-key")
    assert bad_result is None

    # Try with empty key
    empty_result = await authenticate_device_global(real_dal, "")
    assert empty_result is None


@pytest.mark.asyncio
async def test_authenticate_device_global_revoked_key(real_dal) -> None:
    """Test that global auth rejects revoked keys."""
    mgr = DeviceManager(real_dal, tenant_id="tenant1")
    device_info = {
        "name": "RevokedDevice",
        "serial": "SNREVOKED001",
        "hostname": "revoked.local",
        "os": "Linux",
    }
    device, api_key = await mgr.register_device(device_info)

    # Revoke the key directly in DB
    api_key_hash = __import__("hashlib").sha256(api_key.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    await real_dal(
        real_dal.device_api_keys.api_key_hash == api_key_hash,
    ).update(revoked_at=now)

    # Try to authenticate with revoked key
    result = await authenticate_device_global(real_dal, api_key)
    assert result is None
