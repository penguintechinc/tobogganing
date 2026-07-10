"""Tests for C2C runs API."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_create_run_success(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test successful matrix run creation."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.runs.RunManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        run_dict = {
            "id": "run-1",
            "tenant": "test-tenant",
            "status": "pending",
            "test_types": ["latency", "throughput"],
            "total_pairs": 6,
            "completed_pairs": 0,
            "failed_pairs": 0,
            "created_by": "test-user",
            "created_at": "2026-07-10T00:00:00Z",
            "started_at": None,
            "completed_at": None,
        }

        pairs = [
            ("ep-1", "ep-2", "latency"),
            ("ep-1", "ep-2", "throughput"),
            ("ep-2", "ep-1", "latency"),
            ("ep-2", "ep-1", "throughput"),
        ]

        mock_mgr.create_run = MagicMock(return_value=(run_dict, pairs))
        mock_mgr.mark_running = MagicMock()
        mock_mgr.enqueue_run = MagicMock(return_value=len(pairs))

        response = await client.post(
            "/api/v1/waddleperf_c2c/runs",
            json={
                "test_types": ["latency", "throughput"],
                "endpoint_ids": ["ep-1", "ep-2"],
            },
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 202
        data = await response.get_json()
        assert data["run_id"] == "run-1"
        assert data["total_pairs"] == len(pairs)
        assert data["status"] == "running"
        assert "meta" in data
        assert data["meta"]["version"] == 1

        # Verify enqueue was called with the correct number of pairs
        mock_mgr.enqueue_run.assert_called_once()
        call_args = mock_mgr.enqueue_run.call_args
        assert call_args[0][0] == "run-1"  # run_id
        assert len(call_args[0][1]) == len(pairs)  # pairs list


@pytest.mark.asyncio
async def test_create_run_no_test_types(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test run creation fails with missing test_types."""
    client = app_with_c2c.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/runs",
        json={
            "endpoint_ids": ["ep-1", "ep-2"],
        },
        headers={"Authorization": f"Bearer {c2c_write_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_create_run_empty_test_types(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test run creation fails with empty test_types."""
    client = app_with_c2c.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/runs",
        json={
            "test_types": [],
            "endpoint_ids": ["ep-1", "ep-2"],
        },
        headers={"Authorization": f"Bearer {c2c_write_token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_run_insufficient_endpoints(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test run creation fails with fewer than 2 endpoints."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.runs.RunManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.create_run = MagicMock(
            side_effect=ValueError("Cannot create run with 1 enabled endpoints; need at least 2")
        )

        response = await client.post(
            "/api/v1/waddleperf_c2c/runs",
            json={
                "test_types": ["latency"],
                "endpoint_ids": ["ep-1"],
            },
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_runs_success(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test listing matrix runs."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.runs.RunManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        runs = [
            {
                "id": "run-1",
                "tenant": "test-tenant",
                "status": "completed",
                "test_types": ["latency"],
                "total_pairs": 2,
                "completed_pairs": 2,
                "failed_pairs": 0,
                "created_by": "test-user",
                "created_at": "2026-07-10T00:00:00Z",
                "started_at": "2026-07-10T00:00:01Z",
                "completed_at": "2026-07-10T00:05:00Z",
            }
        ]
        mock_mgr.list_runs = MagicMock(return_value=runs)

        response = await client.get(
            "/api/v1/waddleperf_c2c/runs",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["id"] == "run-1"


@pytest.mark.asyncio
async def test_get_run_success(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting run status."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.runs.RunManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        run = {
            "id": "run-1",
            "tenant": "test-tenant",
            "status": "running",
            "test_types": ["latency", "throughput"],
            "total_pairs": 6,
            "completed_pairs": 3,
            "failed_pairs": 0,
            "created_by": "test-user",
            "created_at": "2026-07-10T00:00:00Z",
            "started_at": "2026-07-10T00:00:01Z",
            "completed_at": None,
        }
        mock_mgr.get_run = MagicMock(return_value=run)

        response = await client.get(
            "/api/v1/waddleperf_c2c/runs/run-1",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == "run-1"
        assert data["status"] == "running"
        assert data["completed_pairs"] == 3
        assert data["total_pairs"] == 6


@pytest.mark.asyncio
async def test_get_run_not_found(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting non-existent run."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.runs.RunManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.get_run = MagicMock(return_value=None)

        response = await client.get(
            "/api/v1/waddleperf_c2c/runs/run-invalid",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_run_read_only_token_forbidden(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test that read-only token cannot create run."""
    client = app_with_c2c.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/runs",
        json={
            "test_types": ["latency"],
            "endpoint_ids": ["ep-1", "ep-2"],
        },
        headers={"Authorization": f"Bearer {c2c_readonly_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_run_enqueue_failure(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test handling enqueue failure during run creation."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.runs.RunManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr

        run_dict = {
            "id": "run-1",
            "tenant": "test-tenant",
            "status": "pending",
            "test_types": ["latency"],
            "total_pairs": 2,
            "completed_pairs": 0,
            "failed_pairs": 0,
            "created_by": "test-user",
            "created_at": "2026-07-10T00:00:00Z",
            "started_at": None,
            "completed_at": None,
        }

        pairs = [("ep-1", "ep-2", "latency"), ("ep-2", "ep-1", "latency")]

        mock_mgr.create_run = MagicMock(return_value=(run_dict, pairs))
        mock_mgr.mark_running = MagicMock()
        mock_mgr.enqueue_run = MagicMock(side_effect=Exception("Celery not available"))

        response = await client.post(
            "/api/v1/waddleperf_c2c/runs",
            json={
                "test_types": ["latency"],
                "endpoint_ids": ["ep-1", "ep-2"],
            },
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        assert response.status_code == 500
        data = await response.get_json()
        assert "error" in data


@pytest.mark.asyncio
async def test_list_runs_empty(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test listing runs when none exist."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.runs.RunManager"
    ) as mock_manager_class:
        mock_mgr = MagicMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.list_runs = MagicMock(return_value=[])

        response = await client.get(
            "/api/v1/waddleperf_c2c/runs",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["runs"]) == 0
