from __future__ import annotations

from unittest.mock import patch

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_health_ok(app: Quart) -> None:
    """Test liveness probe returns 200 when process is up.

    Does not depend on database; returns 200 always (process-only check).

    Args:
        app: Quart application fixture.
    """
    client = app.test_client()
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_ok(app: Quart) -> None:
    """Test readiness probe returns 200 when database is reachable.

    Args:
        app: Mocked Quart application fixture (DB mocked to succeed).
    """
    client = app.test_client()
    resp = await client.get("/ready")
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_db_failure(app: Quart) -> None:
    """Test readiness probe returns 503 when database check fails.

    Args:
        app: Mocked Quart application fixture.
    """
    from unittest.mock import MagicMock

    client = app.test_client()
    # Mock get_db to return a db that will fail on query execution
    with patch("hub_api.app.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.connection.execute.side_effect = Exception("Database connection failed")
        mock_get_db.return_value = mock_db

        resp = await client.get("/ready")
        assert resp.status_code == 503
        data = await resp.get_json()
        assert data["status"] == "unhealthy"
        assert data["error"] == "database"
