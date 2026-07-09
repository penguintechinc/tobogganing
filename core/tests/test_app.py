from __future__ import annotations

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_health_ok(app: Quart) -> None:
    """Test health endpoint returns success with mocked database.

    Args:
        app: Mocked Quart application fixture.
    """
    client = app.test_client()
    resp = await client.get("/health")
    assert resp.status_code == 200
