"""Tests for WaddlePerf client schedules API endpoints."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from quart import Quart
from typing import Any

from hub_api.modules.perftest_client.services.schedule_manager import TestScheduleDTO


def make_mock_schedule(
    schedule_id: str = "test-sched-1",
    tenant: str = "test-tenant",
    test_type: str = "ping",
    target: str = "example.com",
    interval_seconds: int = 60,
    org_unit_id: str | None = None,
    enabled: bool = True,
) -> TestScheduleDTO:
    """Create a mock TestScheduleDTO."""
    return TestScheduleDTO(
        id=schedule_id,
        tenant=tenant,
        org_unit_id=org_unit_id,
        test_type=test_type,
        target=target,
        interval_seconds=interval_seconds,
        enabled=enabled,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# Use fixtures from conftest: app_with_wpc, wpc_write_token, wpc_readonly_token


@pytest.mark.asyncio
async def test_create_schedule_success(
    app_with_wpc: Quart, wpc_write_token: str
) -> None:
    """Test successful schedule creation.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        schedule = make_mock_schedule(
            schedule_id="sched-123",
            test_type="ping",
            target="10.0.0.1",
            interval_seconds=30,
        )
        mock_mgr.create_schedule = AsyncMock(return_value=schedule)

        response = await client.post(
            "/api/v1/perftest_client/schedules",
            json={
                "test_type": "ping",
                "target": "10.0.0.1",
                "interval_seconds": 30,
            },
            headers={"Authorization": f"Bearer {wpc_write_token}"},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == "sched-123"
        assert data["test_type"] == "ping"
        assert data["target"] == "10.0.0.1"
        assert data["interval_seconds"] == 30
        assert data["enabled"] is True
        assert data["tenant"] == "test-tenant"
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_create_schedule_missing_fields(
    app_with_wpc: Quart, wpc_write_token: str
) -> None:
    """Test schedule creation fails without required fields.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    response = await client.post(
        "/api/v1/perftest_client/schedules",
        json={"test_type": "ping"},
        headers={"Authorization": f"Bearer {wpc_write_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Missing required fields" in data["error"]


@pytest.mark.asyncio
async def test_create_schedule_requires_write_scope(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test schedule creation fails without write scope.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Token with read-only scope.
    """
    client = app_with_wpc.test_client()

    response = await client.post(
        "/api/v1/perftest_client/schedules",
        json={
            "test_type": "ping",
            "target": "10.0.0.1",
            "interval_seconds": 30,
        },
        headers={"Authorization": f"Bearer {wpc_readonly_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_schedules_success(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test successful schedule listing.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        schedules = [
            make_mock_schedule(schedule_id="sched-1", test_type="ping"),
            make_mock_schedule(schedule_id="sched-2", test_type="iperf"),
        ]
        mock_mgr.list_schedules = AsyncMock(return_value=schedules)

        response = await client.get(
            "/api/v1/perftest_client/schedules",
            headers={"Authorization": f"Bearer {wpc_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["schedules"]) == 2
        assert data["schedules"][0]["id"] == "sched-1"
        assert data["schedules"][1]["id"] == "sched-2"
        assert "meta" in data


@pytest.mark.asyncio
async def test_list_schedules_with_filter(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test schedule listing with org_unit_id filter.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        schedules = [
            make_mock_schedule(schedule_id="sched-1", org_unit_id="ou-1"),
        ]
        mock_mgr.list_schedules = AsyncMock(return_value=schedules)

        response = await client.get(
            "/api/v1/perftest_client/schedules?org_unit_id=ou-1",
            headers={"Authorization": f"Bearer {wpc_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["schedules"]) == 1
        assert data["schedules"][0]["org_unit_id"] == "ou-1"

        # Verify the manager was called with the filter
        mock_mgr.list_schedules.assert_called_once_with(org_unit_id="ou-1")


@pytest.mark.asyncio
async def test_get_schedule_success(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test successful schedule retrieval.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        schedule = make_mock_schedule(schedule_id="sched-456")
        mock_mgr.get_schedule = AsyncMock(return_value=schedule)

        response = await client.get(
            "/api/v1/perftest_client/schedules/sched-456",
            headers={"Authorization": f"Bearer {wpc_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "sched-456"
        assert "meta" in data


@pytest.mark.asyncio
async def test_get_schedule_not_found(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test schedule retrieval when not found.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_schedule = AsyncMock(return_value=None)

        response = await client.get(
            "/api/v1/perftest_client/schedules/nonexistent",
            headers={"Authorization": f"Bearer {wpc_readonly_token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_schedule_success(
    app_with_wpc: Quart, wpc_write_token: str
) -> None:
    """Test successful schedule update.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        updated_schedule = make_mock_schedule(
            schedule_id="sched-789",
            interval_seconds=120,
        )
        mock_mgr.update_schedule = AsyncMock(return_value=updated_schedule)

        response = await client.put(
            "/api/v1/perftest_client/schedules/sched-789",
            json={"interval_seconds": 120},
            headers={"Authorization": f"Bearer {wpc_write_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "sched-789"
        assert data["interval_seconds"] == 120


@pytest.mark.asyncio
async def test_delete_schedule_success(
    app_with_wpc: Quart, wpc_write_token: str
) -> None:
    """Test successful schedule deletion.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.delete_schedule = AsyncMock(return_value=True)

        response = await client.delete(
            "/api/v1/perftest_client/schedules/sched-999",
            headers={"Authorization": f"Bearer {wpc_write_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "deleted successfully" in data["message"]


@pytest.mark.asyncio
async def test_delete_schedule_not_found(
    app_with_wpc: Quart, wpc_write_token: str
) -> None:
    """Test schedule deletion when not found.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.delete_schedule = AsyncMock(return_value=False)

        response = await client.delete(
            "/api/v1/perftest_client/schedules/nonexistent",
            headers={"Authorization": f"Bearer {wpc_write_token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_schedules_tenant_isolation(
    app_with_wpc: Quart, wpc_write_token: str
) -> None:
    """Test that schedules are scoped to tenant claim.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_write_token: Valid JWT token with write scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.perftest_client.api.schedules.ScheduleManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        schedule = make_mock_schedule(schedule_id="sched-123")
        mock_mgr.create_schedule = AsyncMock(return_value=schedule)

        response = await client.post(
            "/api/v1/perftest_client/schedules",
            json={
                "test_type": "ping",
                "target": "10.0.0.1",
                "interval_seconds": 30,
            },
            headers={"Authorization": f"Bearer {wpc_write_token}"},
        )

        assert response.status_code == 201

        # Verify ScheduleManager was instantiated with test-tenant
        # Check that the second argument is "test-tenant"
        call_args = mock_manager_class.call_args
        assert call_args[0][1] == "test-tenant"


@pytest.mark.asyncio
async def test_create_schedule_missing_auth(app_with_wpc: Quart) -> None:
    """Test schedule creation without authorization.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    response = await client.post(
        "/api/v1/perftest_client/schedules",
        json={
            "test_type": "ping",
            "target": "10.0.0.1",
            "interval_seconds": 30,
        },
    )

    assert response.status_code == 403
