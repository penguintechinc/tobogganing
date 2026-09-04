"""Tests for WaddlePerf client config API endpoints."""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from quart import Quart
from typing import Any

from hub_api.modules.perftest_client.services.schedule_manager import TestScheduleDTO


def make_mock_schedule(
    schedule_id: str = "test-sched-1",
    test_type: str = "ping",
    target: str = "example.com",
    interval_seconds: int = 60,
) -> TestScheduleDTO:
    """Create a mock TestScheduleDTO."""
    return TestScheduleDTO(
        id=schedule_id,
        tenant="test-tenant",
        org_unit_id="ou-1",
        test_type=test_type,
        target=target,
        interval_seconds=interval_seconds,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def make_mock_device(
    device_id: str = "dev-123",
    org_unit_id: str = "ou-1",
) -> MagicMock:
    """Create a mock device object."""
    device = MagicMock()
    device.id = device_id
    device.org_unit_id = org_unit_id
    device.tenant = "test-tenant"
    device.name = "test-device"
    device.serial = "ABC123"
    return device


# Use fixtures from conftest: app_with_wpc


@pytest.mark.asyncio
async def test_get_client_config_success(app_with_wpc: Quart) -> None:
    """Test successful client config retrieval with valid device key.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()
    test_api_key = "test-device-key-12345"

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global",
        new_callable=AsyncMock
    ) as mock_auth, patch(
        "hub_api.modules.perftest_client.api.client_config.ScheduleManager"
    ) as mock_mgr_class, patch(
        "hub_api.modules.perftest_client.api.client_config.get_db"
    ) as mock_get_db:

        device = make_mock_device()
        mock_auth.return_value = (device, "test-tenant")

        mock_mgr = AsyncMock()
        mock_mgr_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        schedules = [make_mock_schedule(schedule_id="sched-1")]
        mock_mgr.resolve_for_device = AsyncMock(return_value=schedules)

        mock_db = MagicMock()
        mock_db.client_configs = MagicMock()
        mock_db.client_configs.select_list = MagicMock(return_value=None)
        mock_get_db.return_value = mock_db

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["schedules"]) == 1
        assert data["schedules"][0]["id"] == "sched-1"
        assert "config" in data
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_get_client_config_returns_resolved_schedules(
    app_with_wpc: Quart,
) -> None:
    """Test that client config returns schedules resolved for device's org unit.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()
    test_api_key = "test-device-key-12345"

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global"
    ) as mock_auth, patch(
        "hub_api.modules.perftest_client.api.client_config.ScheduleManager"
    ) as mock_mgr_class, patch(
        "hub_api.modules.perftest_client.api.client_config.get_db"
    ) as mock_get_db:

        device = make_mock_device(device_id="dev-456", org_unit_id="ou-2")
        mock_auth.return_value = (device, "test-tenant")

        mock_mgr = AsyncMock()
        mock_mgr_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        schedules = [
            make_mock_schedule(schedule_id="sched-ou2-1"),
            make_mock_schedule(schedule_id="sched-ou2-2"),
        ]
        mock_mgr.resolve_for_device = AsyncMock(return_value=schedules)

        mock_db = MagicMock()
        mock_db.client_configs = MagicMock()
        mock_db.client_configs.select_list = MagicMock(return_value=None)
        mock_get_db.return_value = mock_db

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["schedules"]) == 2

        # Verify resolve_for_device was called with the device
        mock_mgr.resolve_for_device.assert_called_once_with(device)


@pytest.mark.asyncio
async def test_get_client_config_includes_client_config(
    app_with_wpc: Quart,
) -> None:
    """Test that client config includes fetched config from DB.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()
    test_api_key = "test-device-key-12345"

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global"
    ) as mock_auth, patch(
        "hub_api.modules.perftest_client.api.client_config.ScheduleManager"
    ) as mock_mgr_class, patch(
        "hub_api.modules.perftest_client.api.client_config.get_db"
    ) as mock_get_db:

        device = make_mock_device()
        mock_auth.return_value = (device, "test-tenant")

        mock_mgr = AsyncMock()
        mock_mgr_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.resolve_for_device = AsyncMock(return_value=[])

        mock_db = MagicMock()
        config_obj = MagicMock()
        config_obj.config = {"test_mode": True, "verbose": False}
        mock_db.client_configs.select_list = MagicMock(return_value=[config_obj])
        mock_get_db.return_value = mock_db

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["config"] == {"test_mode": True, "verbose": False}


@pytest.mark.asyncio
async def test_get_client_config_missing_auth_header(app_with_wpc: Quart) -> None:
    """Test config retrieval fails without Authorization header.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    response = await client.get("/api/v1/perftest_client/config")

    assert response.status_code == 401
    data = await response.get_json()
    assert "Missing or invalid Authorization header" in data["error"]


@pytest.mark.asyncio
async def test_get_client_config_invalid_device_key(app_with_wpc: Quart) -> None:
    """Test config retrieval fails with invalid device key.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global"
    ) as mock_auth:
        mock_auth.return_value = None

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": "Bearer invalid-key"},
        )

        assert response.status_code == 401
        data = await response.get_json()
        assert "Invalid device credentials" in data["error"]


@pytest.mark.asyncio
async def test_get_client_config_feature_disabled(app_with_wpc: Quart) -> None:
    """Test config retrieval returns 402 when feature flag is disabled.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()
    test_api_key = "test-device-key-12345"

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global"
    ) as mock_auth, patch(
        "hub_api.modules.perftest_client.api.client_config.feature_enabled"
    ) as mock_feature:

        device = make_mock_device()
        mock_auth.return_value = (device, "test-tenant")
        mock_feature.return_value = False

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )

        assert response.status_code == 402
        data = await response.get_json()
        assert "Feature not available" in data["error"]


@pytest.mark.asyncio
async def test_get_client_config_tenant_derived_from_device(
    app_with_wpc: Quart,
) -> None:
    """Test that tenant is derived from device record, not header.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()
    test_api_key = "test-device-key-12345"

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global"
    ) as mock_auth, patch(
        "hub_api.modules.perftest_client.api.client_config.ScheduleManager"
    ) as mock_mgr_class, patch(
        "hub_api.modules.perftest_client.api.client_config.get_db"
    ) as mock_get_db:

        device = make_mock_device()
        # Device's tenant is "test-tenant"
        mock_auth.return_value = (device, "test-tenant")

        mock_mgr = AsyncMock()
        mock_mgr_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.resolve_for_device = AsyncMock(return_value=[])

        mock_db = MagicMock()
        mock_db.client_configs.select_list = MagicMock(return_value=None)
        mock_get_db.return_value = mock_db

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )

        assert response.status_code == 200

        # Verify ScheduleManager was created with tenant from device, not header
        mock_mgr_class.assert_called_once_with(mock_db, "test-tenant")


@pytest.mark.asyncio
async def test_get_client_config_revoked_key(app_with_wpc: Quart) -> None:
    """Test config retrieval fails with revoked device key.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global"
    ) as mock_auth:
        # authenticate_device_global returns None for revoked keys
        mock_auth.return_value = None

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": "Bearer revoked-key"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_client_config_empty_schedules(app_with_wpc: Quart) -> None:
    """Test config retrieval with no schedules resolved.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()
    test_api_key = "test-device-key-12345"

    with patch(
        "hub_api.modules.perftest_client.api.client_config.authenticate_device_global"
    ) as mock_auth, patch(
        "hub_api.modules.perftest_client.api.client_config.ScheduleManager"
    ) as mock_mgr_class, patch(
        "hub_api.modules.perftest_client.api.client_config.get_db"
    ) as mock_get_db:

        device = make_mock_device()
        mock_auth.return_value = (device, "test-tenant")

        mock_mgr = AsyncMock()
        mock_mgr_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.resolve_for_device = AsyncMock(return_value=[])

        mock_db = MagicMock()
        mock_db.client_configs.select_list = MagicMock(return_value=None)
        mock_get_db.return_value = mock_db

        response = await client.get(
            "/api/v1/perftest_client/config",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["schedules"] == []
        assert data["config"] == {}


@pytest.mark.asyncio
async def test_get_client_config_no_bearer_prefix(app_with_wpc: Quart) -> None:
    """Test config retrieval fails with malformed Authorization header.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    response = await client.get(
        "/api/v1/perftest_client/config",
        headers={"Authorization": "Basic dGVzdDp0ZXN0"},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "Missing or invalid Authorization header" in data["error"]
