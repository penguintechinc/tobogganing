"""Tests for WaddlePerf Cluster statistics API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart


# Use canonical fixtures from conftest.py (flags auto-enabled there)

@pytest.fixture
def app_with_wpc_stats(app_with_wpc: Quart) -> Quart:
    """Alias to canonical app_with_wpc fixture.

    Args:
        app_with_wpc: Canonical fixture with real auth and flags enabled.

    Returns:
        Quart app with WaddlePerf cluster module.
    """
    return app_with_wpc


@pytest.fixture
def stats_read_token(wpc_readonly_token: str) -> str:
    """Alias to canonical read-only token fixture.

    Args:
        wpc_readonly_token: Read-only token from canonical fixture.

    Returns:
        JWT token with read scope.
    """
    return wpc_readonly_token


@pytest.mark.asyncio
async def test_get_summary_success(
    app_with_wpc_stats: Quart, stats_read_token: str
) -> None:
    """Test retrieving overall statistics summary."""
    client = app_with_wpc_stats.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.stats.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.stats.StatsManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_summary = {
            "total_tests": 100,
            "completed_count": 80,
            "success_rate": 80.0,
            "avg_latency_ms": 45.5,
        }

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.summary = AsyncMock(return_value=mock_summary)

        response = await client.get(
            "/api/v1/perftest_cluster/stats/summary",
            headers={"Authorization": f"Bearer {stats_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "summary" in data
        assert data["summary"]["total_tests"] == 100
        assert data["summary"]["success_rate"] == 80.0
        assert "meta" in data


@pytest.mark.asyncio
async def test_get_by_device_success(
    app_with_wpc_stats: Quart, stats_read_token: str
) -> None:
    """Test retrieving device-aggregated statistics."""
    client = app_with_wpc_stats.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.stats.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.stats.StatsManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_by_device = [
            {
                "device_id": "device-1",
                "total_tests": 50,
                "success_rate": 90.0,
                "avg_latency_ms": 40.0,
            }
        ]

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.by_device = AsyncMock(return_value=mock_by_device)

        response = await client.get(
            "/api/v1/perftest_cluster/stats/by-device",
            headers={"Authorization": f"Bearer {stats_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "by_device" in data
        assert len(data["by_device"]) == 1
        assert data["by_device"][0]["device_id"] == "device-1"
        assert "meta" in data


@pytest.mark.asyncio
async def test_get_by_type_success(
    app_with_wpc_stats: Quart, stats_read_token: str
) -> None:
    """Test retrieving test-type aggregated statistics."""
    client = app_with_wpc_stats.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.stats.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.stats.StatsManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_by_type = [
            {
                "test_type": "latency",
                "total_tests": 60,
                "success_rate": 83.33,
                "avg_latency_ms": 42.0,
            }
        ]

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.by_type = AsyncMock(return_value=mock_by_type)

        response = await client.get(
            "/api/v1/perftest_cluster/stats/by-type",
            headers={"Authorization": f"Bearer {stats_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "by_type" in data
        assert len(data["by_type"]) == 1
        assert data["by_type"][0]["test_type"] == "latency"
        assert "meta" in data


@pytest.mark.asyncio
async def test_get_trends_success(
    app_with_wpc_stats: Quart, stats_read_token: str
) -> None:
    """Test retrieving time-series trends data."""
    client = app_with_wpc_stats.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.stats.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.stats.StatsManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_trends = {
            "timestamps": ["2026-07-06T00:00:00", "2026-07-07T00:00:00"],
            "values": [75.0, 80.0],
            "metric": "success_rate",
            "interval": "daily",
        }

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.trends = AsyncMock(return_value=mock_trends)

        response = await client.get(
            "/api/v1/perftest_cluster/stats/trends?interval=daily&metric=success_rate",
            headers={"Authorization": f"Bearer {stats_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "trends" in data
        assert data["trends"]["metric"] == "success_rate"
        assert "meta" in data


@pytest.mark.asyncio
async def test_get_recent_success(
    app_with_wpc_stats: Quart, stats_read_token: str
) -> None:
    """Test retrieving recent test results."""
    client = app_with_wpc_stats.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.stats.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.stats.StatsManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        now = datetime.now(timezone.utc).isoformat()
        mock_recent = [
            {
                "id": "test-1",
                "device_id": "device-1",
                "test_type": "latency",
                "status": "completed",
                "latency_ms": 45.5,
                "created_at": now,
            }
        ]

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.recent = AsyncMock(return_value=mock_recent)

        response = await client.get(
            "/api/v1/perftest_cluster/stats/recent",
            headers={"Authorization": f"Bearer {stats_read_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "recent" in data
        assert len(data["recent"]) == 1
        assert data["recent"][0]["id"] == "test-1"
        assert "meta" in data


@pytest.mark.asyncio
async def test_get_recent_with_limit_cap(
    app_with_wpc_stats: Quart, stats_read_token: str
) -> None:
    """Test that limit is capped at 100."""
    client = app_with_wpc_stats.test_client()

    with patch(
        "hub_api.modules.perftest_cluster.api.stats.get_db"
    ) as mock_get_db, patch(
        "hub_api.modules.perftest_cluster.api.stats.StatsManager"
    ) as mock_manager_class:
        mock_get_db.return_value = MagicMock()

        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.recent = AsyncMock(return_value=[])

        # Request with limit > 100
        response = await client.get(
            "/api/v1/perftest_cluster/stats/recent?limit=200",
            headers={"Authorization": f"Bearer {stats_read_token}"},
        )

        assert response.status_code == 200
        # Verify StatsManager.recent was called with limit=100 (capped)
        mock_mgr.recent.assert_called_once()
        call_kwargs = mock_mgr.recent.call_args[1]
        assert call_kwargs["limit"] == 100
