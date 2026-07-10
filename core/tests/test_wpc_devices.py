"""Tests for WaddlePerf cluster device management."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.modules.waddleperf_cluster.services.device_manager import Device, DeviceManager


@pytest.mark.asyncio
async def test_register_device_success() -> None:
    """Test successful device registration."""
    db = MagicMock()
    tenant_id = "test-tenant"

    device_obj = MagicMock()
    device_obj.id = "device-1"
    device_obj.tenant = tenant_id
    device_obj.org_unit_id = "ou-1"
    device_obj.name = "test-device"
    device_obj.serial = "SN-12345"
    device_obj.hostname = "test.example.com"
    device_obj.os = "Linux"
    device_obj.status = "online"
    device_obj.last_heartbeat = None
    device_obj.device_metadata = {}
    device_obj.created_at = datetime.now(timezone.utc)
    device_obj.updated_at = datetime.now(timezone.utc)

    db.devices.create = MagicMock(return_value=device_obj)
    db.device_api_keys.create = MagicMock(return_value=MagicMock())

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    device, api_key = await manager.register_device(
        {
            "name": "test-device",
            "serial": "SN-12345",
            "hostname": "test.example.com",
            "os": "Linux",
            "org_unit_id": "ou-1",
        }
    )

    assert device.id == "device-1"
    assert device.serial == "SN-12345"
    assert device.status == "online"
    assert api_key is not None
    assert len(api_key) > 0


@pytest.mark.asyncio
async def test_authenticate_device_success() -> None:
    """Test successful device authentication."""
    import hashlib

    db = MagicMock()
    tenant_id = "test-tenant"

    raw_api_key = "test-api-key-12345"
    api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()

    key_obj = MagicMock()
    key_obj.device_id = "device-1"
    key_obj.api_key_hash = api_key_hash
    key_obj.revoked_at = None

    device_obj = MagicMock()
    device_obj.id = "device-1"
    device_obj.tenant = tenant_id
    device_obj.org_unit_id = None
    device_obj.name = "test-device"
    device_obj.serial = "SN-12345"
    device_obj.hostname = "test.example.com"
    device_obj.os = "Linux"
    device_obj.status = "online"
    device_obj.last_heartbeat = None
    device_obj.device_metadata = {}
    device_obj.created_at = datetime.now(timezone.utc)
    device_obj.updated_at = datetime.now(timezone.utc)

    db.device_api_keys.select = MagicMock(return_value=key_obj)
    db.devices.select = MagicMock(return_value=device_obj)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    device = await manager.authenticate_device(raw_api_key)

    assert device is not None
    assert device.id == "device-1"
    assert device.serial == "SN-12345"


@pytest.mark.asyncio
async def test_authenticate_device_revoked() -> None:
    """Test authentication fails for revoked key."""
    import hashlib

    db = MagicMock()
    tenant_id = "test-tenant"

    raw_api_key = "test-api-key-12345"
    api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()

    key_obj = MagicMock()
    key_obj.device_id = "device-1"
    key_obj.api_key_hash = api_key_hash
    key_obj.revoked_at = datetime.now(timezone.utc)

    db.device_api_keys.select = MagicMock(return_value=key_obj)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    device = await manager.authenticate_device(raw_api_key)

    assert device is None


@pytest.mark.asyncio
async def test_authenticate_device_not_found() -> None:
    """Test authentication fails when key not found."""
    db = MagicMock()
    tenant_id = "test-tenant"

    db.device_api_keys.select = MagicMock(return_value=None)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    device = await manager.authenticate_device("invalid-key")

    assert device is None


@pytest.mark.asyncio
async def test_get_device_success() -> None:
    """Test retrieving a device."""
    db = MagicMock()
    tenant_id = "test-tenant"

    device_obj = MagicMock()
    device_obj.id = "device-1"
    device_obj.tenant = tenant_id
    device_obj.org_unit_id = None
    device_obj.name = "test-device"
    device_obj.serial = "SN-12345"
    device_obj.hostname = "test.example.com"
    device_obj.os = "Linux"
    device_obj.status = "online"
    device_obj.last_heartbeat = None
    device_obj.device_metadata = {}
    device_obj.created_at = datetime.now(timezone.utc)
    device_obj.updated_at = datetime.now(timezone.utc)

    db.devices.select = MagicMock(return_value=device_obj)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    device = await manager.get_device("device-1")

    assert device is not None
    assert device.id == "device-1"
    assert device.serial == "SN-12345"


@pytest.mark.asyncio
async def test_get_device_not_found() -> None:
    """Test retrieving non-existent device."""
    db = MagicMock()
    tenant_id = "test-tenant"

    db.devices.select = MagicMock(return_value=None)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    device = await manager.get_device("nonexistent-device")

    assert device is None


@pytest.mark.asyncio
async def test_list_devices() -> None:
    """Test listing devices."""
    db = MagicMock()
    tenant_id = "test-tenant"

    device_obj = MagicMock()
    device_obj.id = "device-1"
    device_obj.tenant = tenant_id
    device_obj.org_unit_id = None
    device_obj.name = "test-device"
    device_obj.serial = "SN-12345"
    device_obj.hostname = "test.example.com"
    device_obj.os = "Linux"
    device_obj.status = "online"
    device_obj.last_heartbeat = None
    device_obj.device_metadata = {}
    device_obj.created_at = datetime.now(timezone.utc)
    device_obj.updated_at = datetime.now(timezone.utc)

    db.devices.select_list = MagicMock(return_value=[device_obj])

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    devices = await manager.list_devices()

    assert len(devices) == 1
    assert devices[0].id == "device-1"


@pytest.mark.asyncio
async def test_update_status() -> None:
    """Test updating device status."""
    db = MagicMock()
    tenant_id = "test-tenant"

    device_obj = MagicMock()
    device_obj.id = "device-1"
    device_obj.tenant = tenant_id
    device_obj.org_unit_id = None
    device_obj.name = "test-device"
    device_obj.serial = "SN-12345"
    device_obj.hostname = "test.example.com"
    device_obj.os = "Linux"
    device_obj.status = "offline"
    device_obj.last_heartbeat = None
    device_obj.device_metadata = {}
    device_obj.created_at = datetime.now(timezone.utc)
    device_obj.updated_at = datetime.now(timezone.utc)

    db.devices.select = MagicMock(return_value=device_obj)
    db.devices.update = MagicMock(return_value=None)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    updated = await manager.update_status("device-1", "offline")

    assert updated is not None
    assert updated.id == "device-1"


@pytest.mark.asyncio
async def test_heartbeat() -> None:
    """Test device heartbeat."""
    db = MagicMock()
    tenant_id = "test-tenant"

    device_obj = MagicMock()
    device_obj.id = "device-1"
    device_obj.tenant = tenant_id
    device_obj.org_unit_id = None
    device_obj.name = "test-device"
    device_obj.serial = "SN-12345"
    device_obj.hostname = "test.example.com"
    device_obj.os = "Linux"
    device_obj.status = "online"
    device_obj.last_heartbeat = None
    device_obj.device_metadata = {}
    device_obj.created_at = datetime.now(timezone.utc)
    device_obj.updated_at = datetime.now(timezone.utc)

    db.devices.select = MagicMock(return_value=device_obj)
    db.devices.update = MagicMock(return_value=None)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    updated = await manager.heartbeat("device-1")

    assert updated is not None
    assert updated.id == "device-1"


@pytest.mark.asyncio
async def test_remove_device() -> None:
    """Test removing a device."""
    db = MagicMock()
    tenant_id = "test-tenant"

    device_obj = MagicMock()
    device_obj.id = "device-1"
    device_obj.tenant = tenant_id
    device_obj.org_unit_id = None
    device_obj.name = "test-device"
    device_obj.serial = "SN-12345"
    device_obj.hostname = "test.example.com"
    device_obj.os = "Linux"
    device_obj.status = "online"
    device_obj.last_heartbeat = None
    device_obj.device_metadata = {}
    device_obj.created_at = datetime.now(timezone.utc)
    device_obj.updated_at = datetime.now(timezone.utc)

    db.devices.select = MagicMock(return_value=device_obj)
    db.devices.delete = MagicMock(return_value=None)
    db.device_api_keys.delete = MagicMock(return_value=None)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    success = await manager.remove_device("device-1")

    assert success is True


@pytest.mark.asyncio
async def test_remove_device_not_found() -> None:
    """Test removing non-existent device."""
    db = MagicMock()
    tenant_id = "test-tenant"

    db.devices.select = MagicMock(return_value=None)

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    success = await manager.remove_device("nonexistent-device")

    assert success is False


@pytest.mark.asyncio
async def test_count_active_devices() -> None:
    """Test counting active devices."""
    db = MagicMock()
    tenant_id = "test-tenant"

    device_obj = MagicMock()
    device_obj.id = "device-1"

    db.devices.select_list = MagicMock(return_value=[device_obj, device_obj, device_obj])

    manager = DeviceManager(db, tenant_id)
    await manager.initialize()

    count = await manager.count_active_devices()

    assert count == 3
