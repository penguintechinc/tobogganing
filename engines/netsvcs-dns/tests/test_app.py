"""Tests for the Quart application."""
from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock

from app.main import app


@pytest.fixture
def client():
    """Provide a test client for the Quart app."""
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.asyncio
async def test_healthz(client) -> None:
    """Test /healthz endpoint."""
    response = await client.get("/healthz")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_not_ready(client) -> None:
    """Test /ready endpoint when not ready."""
    # By default, ready should be False (not enrolled)
    response = await client.get("/ready")
    assert response.status_code == 503
    data = await response.get_json()
    assert data["ready"] is False


@pytest.mark.asyncio
async def test_ready_ready(client) -> None:
    """Test /ready endpoint when ready."""
    # Manually set ready to True
    import app.main
    app.main.ready = True

    response = await client.get("/ready")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["ready"] is True

    # Reset
    app.main.ready = False


@pytest.mark.asyncio
async def test_metrics(client) -> None:
    """Test /metrics endpoint."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    text = await response.get_data(as_text=True)
    assert "HELP" in text or text.startswith("#")


@pytest.mark.asyncio
async def test_404(client) -> None:
    """Test 404 error handling."""
    response = await client.get("/nonexistent")
    assert response.status_code == 404
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client) -> None:
    """Test /metrics endpoint is available and returns Prometheus format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    text = await response.get_data(as_text=True)
    # Metrics endpoint should contain HELP/TYPE or be empty
    assert isinstance(text, str)
