"""Tests for C2C matrix API."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_get_latest_matrix_success(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting the latest matrix for a test type."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        matrix_data = {
            "test_type": "latency",
            "regions": ["us-west-2", "us-east-1"],
            "cells": [
                {
                    "source": "us-west-2",
                    "dest": "us-east-1",
                    "status": "success",
                    "latency_ms": 45.5,
                    "throughput": None,
                    "loss_pct": 0.0,
                    "measured_at": "2026-07-10T00:00:00Z",
                },
                {
                    "source": "us-east-1",
                    "dest": "us-west-2",
                    "status": "success",
                    "latency_ms": 48.2,
                    "throughput": None,
                    "loss_pct": 0.0,
                    "measured_at": "2026-07-10T00:00:00Z",
                },
            ],
        }
        mock_service.latest_matrix = MagicMock(return_value=matrix_data)

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/latest?test_type=latency",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["test_type"] == "latency"
        assert len(data["regions"]) == 2
        assert len(data["cells"]) == 2
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_get_latest_matrix_missing_test_type(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test latest matrix fails without test_type parameter."""
    client = app_with_c2c.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/matrix/latest",
        headers={"Authorization": f"Bearer {c2c_readonly_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_run_matrix_success(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting matrix for a specific run."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        matrix_data = {
            "run_id": "run-1",
            "test_types": ["latency", "throughput"],
            "regions": ["us-west-2", "us-east-1"],
            "cells": [
                {
                    "source": "us-west-2",
                    "dest": "us-east-1",
                    "test_type": "latency",
                    "status": "success",
                    "latency_ms": 45.5,
                    "throughput": None,
                    "loss_pct": 0.0,
                    "measured_at": "2026-07-10T00:00:00Z",
                },
            ],
        }
        mock_service.run_matrix = MagicMock(return_value=matrix_data)

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/runs/run-1",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["run_id"] == "run-1"
        assert len(data["test_types"]) == 2
        assert len(data["regions"]) == 2


@pytest.mark.asyncio
async def test_get_run_matrix_not_found(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting matrix for non-existent run."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        # Empty matrix indicates no run found
        matrix_data = {
            "run_id": "run-invalid",
            "test_types": [],
            "regions": [],
            "cells": [],
        }
        mock_service.run_matrix = MagicMock(return_value=matrix_data)

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/runs/run-invalid",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_trends_success(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting trends for a region pair and test type."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        trends = [
            {
                "measured_at": "2026-07-10T00:00:00Z",
                "latency_ms": 45.0,
                "throughput": 100.0,
                "loss_pct": 0.0,
                "status": "success",
            },
            {
                "measured_at": "2026-07-10T00:01:00Z",
                "latency_ms": 47.5,
                "throughput": 98.0,
                "loss_pct": 0.0,
                "status": "success",
            },
        ]
        mock_service.trends = MagicMock(return_value=trends)

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/trends?source=us-west-2&dest=us-east-1&test_type=latency",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["source"] == "us-west-2"
        assert data["dest"] == "us-east-1"
        assert data["test_type"] == "latency"
        assert len(data["trends"]) == 2
        assert data["trends"][0]["latency_ms"] == 45.0


@pytest.mark.asyncio
async def test_get_trends_missing_source(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test trends fails without source parameter."""
    client = app_with_c2c.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/matrix/trends?dest=us-east-1&test_type=latency",
        headers={"Authorization": f"Bearer {c2c_readonly_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_trends_missing_dest(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test trends fails without dest parameter."""
    client = app_with_c2c.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/matrix/trends?source=us-west-2&test_type=latency",
        headers={"Authorization": f"Bearer {c2c_readonly_token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_trends_missing_test_type(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test trends fails without test_type parameter."""
    client = app_with_c2c.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/matrix/trends?source=us-west-2&dest=us-east-1",
        headers={"Authorization": f"Bearer {c2c_readonly_token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_trends_with_window(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test trends with custom window size."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.trends = MagicMock(return_value=[])

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/trends?source=us-west-2&dest=us-east-1&test_type=latency&window=50",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        # Verify window was passed correctly
        call_args = mock_service.trends.call_args
        assert call_args[1]["window"] == 50


@pytest.mark.asyncio
async def test_get_latest_matrix_write_token_fails(
    app_with_c2c: Quart, c2c_write_token: str
) -> None:
    """Test that only read scope is needed, write token also works."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.latest_matrix = MagicMock(
            return_value={
                "test_type": "latency",
                "regions": [],
                "cells": [],
            }
        )

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/latest?test_type=latency",
            headers={"Authorization": f"Bearer {c2c_write_token}"},
        )

        # Write token should also work since it includes read access
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_latest_matrix_empty(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting latest matrix when no data exists."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.latest_matrix = MagicMock(
            return_value={
                "test_type": "latency",
                "regions": [],
                "cells": [],
            }
        )

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/latest?test_type=latency",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["test_type"] == "latency"
        assert len(data["regions"]) == 0
        assert len(data["cells"]) == 0


@pytest.mark.asyncio
async def test_get_run_matrix_empty(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting run matrix when run has no results."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        matrix_data = {
            "run_id": "run-1",
            "test_types": [],
            "regions": [],
            "cells": [],
        }
        mock_service.run_matrix = MagicMock(return_value=matrix_data)

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/runs/run-1",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        # Empty matrix with test_types should return 200, not 404
        # (run exists, just no results yet)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_trends_empty(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test getting trends when no data exists."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.trends = MagicMock(return_value=[])

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/trends?source=us-west-2&dest=us-east-1&test_type=latency",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["trends"]) == 0


@pytest.mark.asyncio
async def test_get_trends_invalid_window(
    app_with_c2c: Quart, c2c_readonly_token: str
) -> None:
    """Test trends with invalid window parameter defaults to 20."""
    client = app_with_c2c.test_client()

    with patch(
        "core.modules.waddleperf_c2c.api.matrix.MatrixService"
    ) as mock_service_class:
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.trends = MagicMock(return_value=[])

        response = await client.get(
            "/api/v1/waddleperf_c2c/matrix/trends?source=us-west-2&dest=us-east-1&test_type=latency&window=invalid",
            headers={"Authorization": f"Bearer {c2c_readonly_token}"},
        )

        assert response.status_code == 200
        # Verify window defaulted to 20
        call_args = mock_service.trends.call_args
        assert call_args[1]["window"] == 20
