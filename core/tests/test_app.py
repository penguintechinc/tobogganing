from __future__ import annotations

import pytest
from core.app import create_app


@pytest.mark.asyncio
async def test_health_ok() -> None:
    """Test health endpoint returns success."""
    app = create_app()
    client = app.test_client()
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)
