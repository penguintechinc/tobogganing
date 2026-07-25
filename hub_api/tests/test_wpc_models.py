"""Test WaddlePerf cluster models."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from hub_api.db.base import Base
from hub_api.db.models import (
    OrgUnit,
    Device,
    DeviceApiKey,
    DeviceEnrollmentSecret,
    PerfTestResult,
    ClientConfig,
    ServerKey,
)


def test_wpc_models_create_on_sqlite() -> None:
    """Test that WaddlePerf models create tables on SQLite via Base.metadata."""
    tables_to_check = {
        "org_units",
        "devices",
        "device_api_keys",
        "device_enrollment_secrets",
        "perf_test_results",
        "client_configs",
        "server_keys",
    }

    # Verify all tables exist in Base.metadata
    base_tables = set(Base.metadata.tables.keys())
    missing = tables_to_check - base_tables

    assert (
        not missing
    ), f"WaddlePerf tables missing from Base.metadata: {missing}"


def test_org_unit_per_tenant_uniqueness(test_db_session: any) -> None:
    """Test that OrgUnit name is unique per tenant."""
    # Create two OrgUnits with same name in different tenants
    ou1 = OrgUnit(
        id=str(uuid4()),
        tenant="tenant-a",
        name="engineering",
        description="Engineering team",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    ou2 = OrgUnit(
        id=str(uuid4()),
        tenant="tenant-b",
        name="engineering",
        description="Engineering team for tenant B",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Both should be insertable (different tenants)
    test_db_session.add(ou1)
    test_db_session.commit()

    test_db_session.add(ou2)
    test_db_session.commit()

    # Verify both exist
    assert test_db_session.query(OrgUnit).filter_by(name="engineering").count() == 2


def test_device_per_tenant_serial_uniqueness(test_db_session: any) -> None:
    """Test that Device serial is unique per tenant."""
    # Create two devices with same serial in different tenants
    dev1 = Device(
        id=str(uuid4()),
        tenant="tenant-a",
        name="device-1",
        serial="SN-12345",
        hostname="host1.example.com",
        os="Linux",
        status="online",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    dev2 = Device(
        id=str(uuid4()),
        tenant="tenant-b",
        name="device-2",
        serial="SN-12345",
        hostname="host2.example.com",
        os="Linux",
        status="online",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Both should be insertable (different tenants)
    test_db_session.add(dev1)
    test_db_session.commit()

    test_db_session.add(dev2)
    test_db_session.commit()

    # Verify both exist
    assert test_db_session.query(Device).filter_by(serial="SN-12345").count() == 2


def test_device_metadata_column_accessible(test_db_session: any) -> None:
    """Test that device_metadata attribute maps to 'metadata' column."""
    device = Device(
        id=str(uuid4()),
        tenant="tenant-a",
        name="test-device",
        serial="SN-99999",
        hostname="test.example.com",
        os="Linux",
        status="offline",
        device_metadata={"cpu": "4", "memory": "8GB"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    test_db_session.add(device)
    test_db_session.commit()

    # Retrieve and verify metadata is accessible
    retrieved = test_db_session.query(Device).filter_by(serial="SN-99999").first()
    assert retrieved is not None
    assert retrieved.device_metadata == {"cpu": "4", "memory": "8GB"}


def test_device_api_key_creation(test_db_session: any) -> None:
    """Test DeviceApiKey creation with required fields."""
    api_key = DeviceApiKey(
        id=str(uuid4()),
        tenant="tenant-a",
        device_id=str(uuid4()),
        api_key_hash="sha256_hash_12345",
        created_at=datetime.utcnow(),
    )

    test_db_session.add(api_key)
    test_db_session.commit()

    # Retrieve and verify
    retrieved = (
        test_db_session.query(DeviceApiKey)
        .filter_by(tenant="tenant-a")
        .first()
    )
    assert retrieved is not None
    assert retrieved.api_key_hash == "sha256_hash_12345"
    assert retrieved.revoked_at is None


def test_device_enrollment_secret_creation(test_db_session: any) -> None:
    """Test DeviceEnrollmentSecret creation."""
    secret = DeviceEnrollmentSecret(
        id=str(uuid4()),
        tenant="tenant-a",
        org_unit_id=str(uuid4()),
        secret_hash="hash_enrollment_secret",
        expires_at=None,
        created_at=datetime.utcnow(),
        created_by=str(uuid4()),
    )

    test_db_session.add(secret)
    test_db_session.commit()

    # Retrieve and verify
    retrieved = (
        test_db_session.query(DeviceEnrollmentSecret)
        .filter_by(tenant="tenant-a")
        .first()
    )
    assert retrieved is not None
    assert retrieved.secret_hash == "hash_enrollment_secret"


def test_perf_test_result_creation(test_db_session: any) -> None:
    """Test PerfTestResult creation with metrics."""
    test_result = PerfTestResult(
        id=str(uuid4()),
        tenant="tenant-a",
        device_id=str(uuid4()),
        test_type="http",
        status="completed",
        target="https://example.com",
        latency_ms=125.5,
        throughput=1024.75,
        test_output="Test completed successfully",
        created_at=datetime.utcnow(),
    )

    test_db_session.add(test_result)
    test_db_session.commit()

    # Retrieve and verify
    retrieved = (
        test_db_session.query(PerfTestResult)
        .filter_by(tenant="tenant-a")
        .first()
    )
    assert retrieved is not None
    assert retrieved.test_type == "http"
    assert retrieved.latency_ms == 125.5
    assert retrieved.throughput == 1024.75


def test_client_config_with_json(test_db_session: any) -> None:
    """Test ClientConfig creation with JSON config."""
    config = ClientConfig(
        id=str(uuid4()),
        tenant="tenant-a",
        org_unit_id=str(uuid4()),
        config={
            "interval": 60,
            "tests": ["http", "tcp"],
            "enabled": True,
        },
        updated_at=datetime.utcnow(),
        updated_by=str(uuid4()),
    )

    test_db_session.add(config)
    test_db_session.commit()

    # Retrieve and verify
    retrieved = (
        test_db_session.query(ClientConfig)
        .filter_by(tenant="tenant-a")
        .first()
    )
    assert retrieved is not None
    assert retrieved.config["interval"] == 60
    assert "http" in retrieved.config["tests"]


def test_server_key_creation(test_db_session: any) -> None:
    """Test ServerKey creation."""
    key = ServerKey(
        id=str(uuid4()),
        tenant="tenant-a",
        key_id="key-2026-001",
        public_key="-----BEGIN PUBLIC KEY-----\nMIIBIjANBg...",
        created_at=datetime.utcnow(),
    )

    test_db_session.add(key)
    test_db_session.commit()

    # Retrieve and verify
    retrieved = (
        test_db_session.query(ServerKey)
        .filter_by(tenant="tenant-a")
        .first()
    )
    assert retrieved is not None
    assert retrieved.key_id == "key-2026-001"
    assert "PUBLIC KEY" in retrieved.public_key
