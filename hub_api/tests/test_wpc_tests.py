"""Tests for WaddlePerf Cluster performance test API endpoints."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.modules.perftest_cluster.services.test_manager import PerfTestResult


# Use canonical fixtures from conftest.py (flags auto-enabled there)

@pytest.fixture
def app_with_wpc_tests(app_with_wpc: Quart) -> Quart:
    """Alias to canonical app_with_wpc fixture.

    Args:
        app_with_wpc: Canonical fixture with real auth and flags enabled.

    Returns:
        Quart app with WaddlePerf cluster module.
    """
    return app_with_wpc


@pytest.fixture
def tests_read_token(wpc_readonly_token: str) -> str:
    """Alias to canonical read-only token fixture.

    Args:
        wpc_readonly_token: Read-only token from canonical fixture.

    Returns:
        JWT token with read scope.
    """
    return wpc_readonly_token


@pytest.fixture
def tests_write_token(wpc_write_token: str) -> str:
    """Alias to canonical write token fixture.

    Args:
        wpc_write_token: Write token from canonical fixture.

    Returns:
        JWT token with write scope.
    """
    return wpc_write_token


@pytest_asyncio.fixture
async def app_with_wpc_realdb(
    real_dal: Any, monkeypatch: Any
) -> Quart:
    """Create a test app with WaddlePerf Cluster module and real async database.

    This fixture patches get_db to return the real AsyncDB from real_dal,
    allowing end-to-end tests against a migrated SQLite database.

    Args:
        real_dal: Real AsyncDB fixture from conftest.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        Quart app with WaddlePerf Cluster module and real database.
    """
    from hub_api.auth.jwt import encode_access_token
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext
    from hub_api.app import create_app
    import hub_api.db

    # Create a fresh app without mocking db.init_dal
    test_app = create_app()
    test_app.config["TESTING"] = True

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    test_app.config["KEY_PROVIDER"] = provider

    # Patch get_db to return the real AsyncDB
    monkeypatch.setattr(hub_api.db, "get_db", lambda: real_dal)
    import hub_api.app as app_module
    monkeypatch.setattr(app_module, "get_db", lambda: real_dal)

    # Patch the tests API module to use real DAL too
    import hub_api.modules.perftest_cluster.api.tests as tests_api
    monkeypatch.setattr(tests_api, "get_db", lambda: real_dal)

    # Enable all wpc feature flags for tests (bypass flag server)
    import shared.licensing.entitlements
    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith(
            "tobogganing.perftest_cluster."
        ) or flag_key.startswith("tobogganing.perftest_client."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    # Register WaddlePerf Cluster module via registry
    from hub_api.modules.perftest_cluster import module as wpc_module
    from hub_api.modules.perftest_client import module as wpcl_module

    wpc_contract = wpc_module()
    wpcl_contract = wpcl_module()
    test_app.registry.register(wpc_contract)
    test_app.registry.register(wpcl_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=test_app.config_obj, db=real_dal, key_provider=provider)
    test_app.registry.apply_to(test_app, ctx)

    return test_app


@pytest_asyncio.fixture
async def wpc_write_token_realdb(app_with_wpc_realdb: Quart) -> str:
    """Generate a JWT token with full write scopes for real-DAL tests.

    Args:
        app_with_wpc_realdb: App with real database and key provider.

    Returns:
        Encoded JWT token with write scopes.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_wpc_realdb.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_create_test_success(
    app_with_wpc_tests: Quart,
    tests_write_token: str,
    mock_test_result: PerfTestResult,
) -> None:
    """Test successful test creation with JWT auth."""
    client = app_with_wpc_tests.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.tests.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.create_test = AsyncMock(return_value=mock_test_result)

        response = await client.post(
            "/api/v1/perftest_cluster/tests",
            json={
                "device_id": "device-1",
                "test_type": "latency",
                "target": "https://example.com",
            },
            headers={"Authorization": f"Bearer {tests_write_token}"},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == "test-1"
        assert data["device_id"] == "device-1"
        assert data["test_type"] == "latency"
        assert data["status"] == "pending"
        assert "meta" in data


@pytest.mark.asyncio
async def test_list_tests_success(
    app_with_wpc_tests: Quart, tests_read_token: str, mock_test_result: PerfTestResult
) -> None:
    """Test listing tests with JWT auth."""
    client = app_with_wpc_tests.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.tests.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.list_results = AsyncMock(return_value=[mock_test_result])

        response = await client.get(
            "/api/v1/perftest_cluster/tests",
            headers={"Authorization": f"Bearer {tests_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "tests" in data
        assert len(data["tests"]) == 1
        assert data["tests"][0]["id"] == "test-1"
        assert "meta" in data


@pytest.mark.asyncio
async def test_get_test_success(
    app_with_wpc_tests: Quart,
    tests_read_token: str,
    mock_completed_result: PerfTestResult,
) -> None:
    """Test retrieving a single test with JWT auth."""
    client = app_with_wpc_tests.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.tests.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_test = AsyncMock(return_value=mock_completed_result)

        response = await client.get(
            "/api/v1/perftest_cluster/tests/test-2",
            headers={"Authorization": f"Bearer {tests_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "test-2"
        assert data["status"] == "completed"
        assert data["latency_ms"] == 45.5
        assert "meta" in data


@pytest.mark.asyncio
async def test_record_result_no_token(app_with_wpc_tests: Quart) -> None:
    """Test result recording fails without API key."""
    client = app_with_wpc_tests.test_client()

    response = await client.post(
        "/api/v1/perftest_cluster/tests/test-1/results",
        json={"device_id": "device-1", "status": "completed"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_record_result_invalid_token(app_with_wpc_tests: Quart) -> None:
    """Test result recording fails with invalid API key."""
    client = app_with_wpc_tests.test_client()
    mock_db = MagicMock()

    with patch(
        "hub_api.modules.perftest_cluster.api.tests.get_db", return_value=mock_db
    ):
        # Mock invalid key lookup
        mock_db.device_api_keys.select = MagicMock(return_value=None)

        response = await client.post(
            "/api/v1/perftest_cluster/tests/test-1/results",
            headers={"Authorization": "Bearer invalid-key"},
            json={"device_id": "device-1", "status": "completed"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_record_result_revoked_token(app_with_wpc_tests: Quart) -> None:
    """Test result recording fails with revoked API key."""
    client = app_with_wpc_tests.test_client()
    mock_db = MagicMock()

    api_key = "test-api-key"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    with patch(
        "hub_api.modules.perftest_cluster.api.tests.get_db", return_value=mock_db
    ):
        # Mock revoked key
        mock_key = MagicMock()
        mock_key.api_key_hash = api_key_hash
        mock_key.device_id = "device-1"
        mock_key.tenant = "tenant1"
        mock_key.revoked_at = datetime.now(timezone.utc)  # Revoked

        mock_db.device_api_keys.select = MagicMock(return_value=mock_key)

        response = await client.post(
            "/api/v1/perftest_cluster/tests/test-1/results",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"device_id": "device-1", "status": "completed"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_record_result_success(
    app_with_wpc_realdb: Quart, real_dal: Any
) -> None:
    """Test successful result recording with device API key authentication (real DAL).

    regression: Ensures device API key authentication works end-to-end with
    real database, capturing device ownership and tenant isolation.
    """
    from uuid import uuid4

    client = app_with_wpc_realdb.test_client()

    # Create device and API key in real database
    device_id = str(uuid4())
    tenant = "test-tenant"
    api_key = "test-api-key-success"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    # Insert device
    await real_dal.devices.async_insert(
        id=device_id,
        tenant=tenant,
        name="Test Device",
        serial="SN-TEST-001",
        hostname="test.local",
        os="Linux",
        status="online",
        last_heartbeat=None,
        metadata=None,
        created_at=now,
        updated_at=now,
    )

    # Insert API key
    api_key_id = str(uuid4())
    await real_dal.device_api_keys.async_insert(
        id=api_key_id,
        device_id=device_id,
        api_key_hash=api_key_hash,
        tenant=tenant,
        revoked_at=None,
        created_at=now,
    )

    # Create test record
    test_id = str(uuid4())
    await real_dal.perf_test_results.async_insert(
        id=test_id,
        tenant=tenant,
        device_id=device_id,
        test_type="latency",
        status="pending",
        target="https://example.com",
        started_at=None,
        completed_at=None,
        latency_ms=None,
        throughput=None,
        test_output=None,
        created_at=now,
    )

    # Record result with device API key
    response = await client.post(
        f"/api/v1/perftest_cluster/tests/{test_id}/results",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "device_id": device_id,
            "status": "completed",
            "latency_ms": 45.5,
            "throughput": 1000.0,
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["id"] == test_id
    assert data["status"] == "completed"
    assert data["latency_ms"] == 45.5
    assert data["throughput"] == 1000.0
    assert "meta" in data


@pytest.mark.asyncio
async def test_record_result_idor_device_cross_access(
    app_with_wpc_realdb: Quart, real_dal: Any
) -> None:
    """Regression: test device B cannot upload results to device A's test (real DAL).

    This test verifies that even with valid device authentication, a device
    cannot modify another device's test records (cross-device IDOR). Proves
    that the IDOR check in record_result route compares authenticated device
    against test's device_id and rejects with 403.

    regression: gh-xyz device ownership verification in test result upload.
    """
    from uuid import uuid4

    client = app_with_wpc_realdb.test_client()

    # Create two devices in real database (same tenant)
    device_a_id = str(uuid4())
    device_b_id = str(uuid4())
    tenant = "test-tenant"
    now = datetime.now(timezone.utc)

    # Device A
    await real_dal.devices.async_insert(
        id=device_a_id,
        tenant=tenant,
        name="Device A",
        serial="SN-DEVICE-A",
        hostname="device-a.local",
        os="Linux",
        status="online",
        last_heartbeat=None,
        metadata=None,
        created_at=now,
        updated_at=now,
    )

    # Device B
    await real_dal.devices.async_insert(
        id=device_b_id,
        tenant=tenant,
        name="Device B",
        serial="SN-DEVICE-B",
        hostname="device-b.local",
        os="Linux",
        status="online",
        last_heartbeat=None,
        metadata=None,
        created_at=now,
        updated_at=now,
    )

    # Device B's API key
    device_b_key = "device-b-key-idor"
    device_b_hash = hashlib.sha256(device_b_key.encode()).hexdigest()
    api_key_b_id = str(uuid4())

    await real_dal.device_api_keys.async_insert(
        id=api_key_b_id,
        device_id=device_b_id,
        api_key_hash=device_b_hash,
        tenant=tenant,
        revoked_at=None,
        created_at=now,
    )

    # Create test owned by Device A
    test_id = str(uuid4())
    await real_dal.perf_test_results.async_insert(
        id=test_id,
        tenant=tenant,
        device_id=device_a_id,  # Belongs to Device A!
        test_type="latency",
        status="pending",
        target="https://example.com",
        started_at=None,
        completed_at=None,
        latency_ms=None,
        throughput=None,
        test_output=None,
        created_at=now,
    )

    # Device B tries to upload results to Device A's test
    response = await client.post(
        f"/api/v1/perftest_cluster/tests/{test_id}/results",
        headers={"Authorization": f"Bearer {device_b_key}"},
        json={
            "device_id": device_b_id,
            "status": "completed",
            "latency_ms": 50.0,
        },
    )

    # Should be rejected with 403 Forbidden (IDOR protection)
    assert response.status_code == 403
    data = await response.get_json()
    assert "Forbidden" in data["error"]

    # Verify test was not modified (check in DB)
    rows = await real_dal(real_dal.perf_test_results.id == test_id).select()
    test_record = rows.first() if hasattr(rows, 'first') else rows[0] if rows else None
    assert test_record is not None
    assert test_record.status == "pending"  # Still pending, not modified
    assert test_record.device_id == device_a_id  # Still belongs to A


# Fixtures for test results
@pytest.fixture
def mock_test_result() -> PerfTestResult:
    """Create a mock test result for testing."""
    return PerfTestResult(
        id="test-1",
        tenant="tenant1",
        device_id="device-1",
        test_type="latency",
        status="pending",
        target="https://example.com",
        started_at=None,
        completed_at=None,
        latency_ms=None,
        throughput=None,
        test_output=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_completed_result() -> PerfTestResult:
    """Create a completed mock test result."""
    now = datetime.now(timezone.utc)
    return PerfTestResult(
        id="test-2",
        tenant="tenant1",
        device_id="device-1",
        test_type="throughput",
        status="completed",
        target="https://example.com",
        started_at=now,
        completed_at=now,
        latency_ms=45.5,
        throughput=1000.0,
        test_output="Test output data",
        created_at=now,
    )
