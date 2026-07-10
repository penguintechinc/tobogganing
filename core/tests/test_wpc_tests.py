"""Tests for WaddlePerf Cluster performance test API endpoints."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from core.modules.waddleperf_cluster.services.test_manager import PerfTestResult


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


@pytest.mark.asyncio
async def test_create_test_success(
    app_with_wpc_tests: Quart,
    tests_write_token: str,
    mock_test_result: PerfTestResult,
) -> None:
    """Test successful test creation with JWT auth."""
    client = app_with_wpc_tests.test_client()

    with patch(
        "core.modules.waddleperf_cluster.api.tests.get_db"
    ) as mock_get_db, patch(
        "core.modules.waddleperf_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.create_test = AsyncMock(return_value=mock_test_result)

        response = await client.post(
            "/api/v1/waddleperf_cluster/tests",
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
        "core.modules.waddleperf_cluster.api.tests.get_db"
    ) as mock_get_db, patch(
        "core.modules.waddleperf_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.list_results = AsyncMock(return_value=[mock_test_result])

        response = await client.get(
            "/api/v1/waddleperf_cluster/tests",
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
        "core.modules.waddleperf_cluster.api.tests.get_db"
    ) as mock_get_db, patch(
        "core.modules.waddleperf_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_test = AsyncMock(return_value=mock_completed_result)

        response = await client.get(
            "/api/v1/waddleperf_cluster/tests/test-2",
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
        "/api/v1/waddleperf_cluster/tests/test-1/results",
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
        "core.modules.waddleperf_cluster.api.tests.get_db", return_value=mock_db
    ):
        # Mock invalid key lookup
        mock_db.device_api_keys.select = MagicMock(return_value=None)

        response = await client.post(
            "/api/v1/waddleperf_cluster/tests/test-1/results",
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
        "core.modules.waddleperf_cluster.api.tests.get_db", return_value=mock_db
    ):
        # Mock revoked key
        mock_key = MagicMock()
        mock_key.api_key_hash = api_key_hash
        mock_key.device_id = "device-1"
        mock_key.tenant = "tenant1"
        mock_key.revoked_at = datetime.now(timezone.utc)  # Revoked

        mock_db.device_api_keys.select = MagicMock(return_value=mock_key)

        response = await client.post(
            "/api/v1/waddleperf_cluster/tests/test-1/results",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"device_id": "device-1", "status": "completed"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_record_result_success(
    app_with_wpc_tests: Quart, mock_completed_result: PerfTestResult
) -> None:
    """Test successful result recording with device API key authentication."""
    client = app_with_wpc_tests.test_client()
    mock_db = MagicMock()

    api_key = "test-api-key"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    with patch(
        "core.modules.waddleperf_cluster.api.tests.get_db", return_value=mock_db
    ), patch(
        "core.modules.waddleperf_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        # Mock valid key
        mock_key = MagicMock()
        mock_key.api_key_hash = api_key_hash
        mock_key.device_id = "device-1"
        mock_key.tenant = "tenant1"
        mock_key.revoked_at = None

        # Mock device record
        mock_device = MagicMock()
        mock_device.id = "device-1"
        mock_device.tenant = "tenant1"

        mock_db.device_api_keys.select = MagicMock(return_value=mock_key)
        mock_db.devices.select = MagicMock(return_value=mock_device)

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_test = AsyncMock(return_value=mock_completed_result)
        mock_mgr.record_result = AsyncMock(return_value=mock_completed_result)

        response = await client.post(
            "/api/v1/waddleperf_cluster/tests/test-2/results",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "device_id": "device-1",
                "status": "completed",
                "latency_ms": 45.5,
                "throughput": 1000.0,
            },
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "test-2"
        assert data["status"] == "completed"
        assert "meta" in data


@pytest.mark.asyncio
async def test_record_result_idor_device_cross_access(
    app_with_wpc_tests: Quart,
) -> None:
    """Regression test for IDOR: device B cannot upload results to device A's test.

    This test verifies that even with valid device authentication, a device
    cannot modify another device's test records (cross-device IDOR).
    """
    client = app_with_wpc_tests.test_client()
    mock_db = MagicMock()

    # Device B's API key
    device_b_key = "device-b-key"
    device_b_hash = hashlib.sha256(device_b_key.encode()).hexdigest()

    with patch(
        "core.modules.waddleperf_cluster.api.tests.get_db", return_value=mock_db
    ), patch(
        "core.modules.waddleperf_cluster.api.tests.TestManager"
    ) as mock_manager_class:
        # Mock Device B (attacker trying to write to A's test)
        device_b = MagicMock()
        device_b.id = "device-b"
        device_b.tenant = "tenant1"

        # Mock the test record (belongs to device A)
        test_record = PerfTestResult(
            id="test-1",
            tenant="tenant1",
            device_id="device-a",  # Belongs to device A!
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

        # Mock API key lookup - Device B's key resolves to Device B
        mock_key_b = MagicMock()
        mock_key_b.api_key_hash = device_b_hash
        mock_key_b.device_id = "device-b"
        mock_key_b.tenant = "tenant1"
        mock_key_b.revoked_at = None

        # Setup mocks
        mock_db.device_api_keys.select = MagicMock(return_value=mock_key_b)
        mock_db.devices.select = MagicMock(return_value=device_b)

        # Setup TestManager
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_test = AsyncMock(return_value=test_record)

        # Device B tries to upload results to Device A's test
        response = await client.post(
            "/api/v1/waddleperf_cluster/tests/test-1/results",
            headers={"Authorization": f"Bearer {device_b_key}"},
            json={
                "device_id": "device-b",
                "status": "completed",
                "latency_ms": 50.0,
            },
        )

        # Should be rejected with 403 Forbidden
        assert response.status_code == 403
        data = await response.get_json()
        assert "Forbidden" in data["error"]
        # Verify record_result was NOT called (IDOR was caught)
        mock_mgr.record_result.assert_not_called()


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
