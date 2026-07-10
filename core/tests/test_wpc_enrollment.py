"""Tests for WaddlePerf cluster enrollment management."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.modules.waddleperf_cluster.services.enrollment_manager import (
    EnrollmentManager,
    EnrollmentSecret,
)


@pytest.mark.asyncio
async def test_create_secret_success() -> None:
    """Test successful enrollment secret creation."""
    db = MagicMock()
    tenant_id = "test-tenant"
    ou_id = "ou-1"
    user_id = "user-1"

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = ou_id
    secret_obj.secret_hash = "hash12345"
    secret_obj.expires_at = None
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = user_id

    db.device_enrollment_secrets.create = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    secret, raw_secret = await manager.create_secret(
        org_unit_id=ou_id,
        expires_at=None,
        created_by=user_id,
    )

    assert secret.id == "secret-1"
    assert secret.org_unit_id == ou_id
    assert raw_secret is not None
    assert len(raw_secret) > 0


@pytest.mark.asyncio
async def test_create_secret_with_expiry() -> None:
    """Test creating secret with expiration."""
    db = MagicMock()
    tenant_id = "test-tenant"
    ou_id = "ou-1"

    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = ou_id
    secret_obj.secret_hash = "hash12345"
    secret_obj.expires_at = expires_at
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = None

    db.device_enrollment_secrets.create = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    secret, raw_secret = await manager.create_secret(
        org_unit_id=ou_id,
        expires_at=expires_at,
        created_by=None,
    )

    assert secret.expires_at == expires_at


@pytest.mark.asyncio
async def test_get_secret_success() -> None:
    """Test retrieving a secret."""
    db = MagicMock()
    tenant_id = "test-tenant"

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = "hash12345"
    secret_obj.expires_at = None
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = "user-1"

    db.device_enrollment_secrets.select = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    secret = await manager.get_secret("secret-1")

    assert secret is not None
    assert secret.id == "secret-1"
    assert secret.org_unit_id == "ou-1"


@pytest.mark.asyncio
async def test_get_secret_not_found() -> None:
    """Test retrieving non-existent secret."""
    db = MagicMock()
    tenant_id = "test-tenant"

    db.device_enrollment_secrets.select = MagicMock(return_value=None)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    secret = await manager.get_secret("nonexistent-secret")

    assert secret is None


@pytest.mark.asyncio
async def test_list_secrets() -> None:
    """Test listing secrets."""
    db = MagicMock()
    tenant_id = "test-tenant"

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = "hash12345"
    secret_obj.expires_at = None
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = "user-1"

    db.device_enrollment_secrets.select_list = MagicMock(return_value=[secret_obj])

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    secrets = await manager.list_secrets()

    assert len(secrets) == 1
    assert secrets[0].id == "secret-1"


@pytest.mark.asyncio
async def test_list_secrets_empty() -> None:
    """Test listing when no secrets exist."""
    db = MagicMock()
    tenant_id = "test-tenant"

    db.device_enrollment_secrets.select_list = MagicMock(return_value=None)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    secrets = await manager.list_secrets()

    assert len(secrets) == 0


@pytest.mark.asyncio
async def test_delete_secret_success() -> None:
    """Test deleting a secret."""
    db = MagicMock()
    tenant_id = "test-tenant"

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = "hash12345"
    secret_obj.expires_at = None
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = None

    db.device_enrollment_secrets.select = MagicMock(return_value=secret_obj)
    db.device_enrollment_secrets.delete = MagicMock(return_value=None)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    success = await manager.delete_secret("secret-1")

    assert success is True


@pytest.mark.asyncio
async def test_delete_secret_not_found() -> None:
    """Test deleting non-existent secret."""
    db = MagicMock()
    tenant_id = "test-tenant"

    db.device_enrollment_secrets.select = MagicMock(return_value=None)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    success = await manager.delete_secret("nonexistent-secret")

    assert success is False


@pytest.mark.asyncio
async def test_verify_secret_success() -> None:
    """Test successful secret verification."""
    db = MagicMock()
    tenant_id = "test-tenant"

    raw_secret = "test-secret-12345"
    secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = secret_hash
    secret_obj.expires_at = None
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = None

    db.device_enrollment_secrets.select = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    org_unit_id = await manager.verify_secret(raw_secret)

    assert org_unit_id == "ou-1"


@pytest.mark.asyncio
async def test_verify_secret_invalid() -> None:
    """Test verification fails with invalid secret."""
    db = MagicMock()
    tenant_id = "test-tenant"

    db.device_enrollment_secrets.select = MagicMock(return_value=None)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    org_unit_id = await manager.verify_secret("invalid-secret")

    assert org_unit_id is None


@pytest.mark.asyncio
async def test_verify_secret_expired() -> None:
    """Test verification fails for expired secret."""
    db = MagicMock()
    tenant_id = "test-tenant"

    raw_secret = "test-secret-12345"
    secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

    # Set expiry to 1 hour ago
    expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = secret_hash
    secret_obj.expires_at = expires_at
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = None

    db.device_enrollment_secrets.select = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    org_unit_id = await manager.verify_secret(raw_secret)

    assert org_unit_id is None


@pytest.mark.asyncio
async def test_verify_secret_hash_mismatch() -> None:
    """Test verification fails with hash mismatch."""
    db = MagicMock()
    tenant_id = "test-tenant"

    raw_secret = "test-secret-12345"
    wrong_hash = hashlib.sha256("wrong-secret".encode()).hexdigest()

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = wrong_hash
    secret_obj.expires_at = None
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = None

    db.device_enrollment_secrets.select = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    org_unit_id = await manager.verify_secret(raw_secret)

    assert org_unit_id is None


@pytest.mark.asyncio
async def test_verify_secret_no_expiry() -> None:
    """Test verification succeeds when secret has no expiry."""
    db = MagicMock()
    tenant_id = "test-tenant"

    raw_secret = "test-secret-12345"
    secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = secret_hash
    secret_obj.expires_at = None
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = None

    db.device_enrollment_secrets.select = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    org_unit_id = await manager.verify_secret(raw_secret)

    assert org_unit_id == "ou-1"


@pytest.mark.asyncio
async def test_verify_secret_valid_future_expiry() -> None:
    """Test verification succeeds with future expiry."""
    db = MagicMock()
    tenant_id = "test-tenant"

    raw_secret = "test-secret-12345"
    secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

    # Set expiry to 1 hour in the future
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    secret_obj = MagicMock()
    secret_obj.id = "secret-1"
    secret_obj.tenant = tenant_id
    secret_obj.org_unit_id = "ou-1"
    secret_obj.secret_hash = secret_hash
    secret_obj.expires_at = expires_at
    secret_obj.created_at = datetime.now(timezone.utc)
    secret_obj.created_by = None

    db.device_enrollment_secrets.select = MagicMock(return_value=secret_obj)

    manager = EnrollmentManager(db, tenant_id)
    await manager.initialize()

    org_unit_id = await manager.verify_secret(raw_secret)

    assert org_unit_id == "ou-1"
