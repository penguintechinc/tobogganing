"""Tests for C2C matrix API using real penguin-dal."""
from __future__ import annotations

import pytest
import pytest_asyncio
from quart import Quart
from typing import Any

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from penguin_dal import AsyncDB


@pytest_asyncio.fixture
async def app_with_c2c_matrix_realdal(
    app_with_c2c: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Create test app with C2C module using real_dal."""
    # Patch get_db everywhere it's imported
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app
    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.waddleperf_c2c.api.matrix
    monkeypatch.setattr(hub_api.modules.waddleperf_c2c.api.matrix, "get_db", get_db_func)

    app_with_c2c.db = real_dal
    return app_with_c2c


@pytest_asyncio.fixture
async def c2c_readonly_token_matrix(app_with_c2c_matrix_realdal: Quart) -> str:
    """Generate read-only token for matrix tests."""
    provider = app_with_c2c_matrix_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def c2c_write_token_matrix(app_with_c2c_matrix_realdal: Quart) -> str:
    """Generate write token for matrix tests."""
    provider = app_with_c2c_matrix_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read c2c:write",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


# ============================================================================
# Latest Matrix Tests
# ============================================================================




@pytest.mark.asyncio
async def test_get_latest_matrix_missing_test_type(
    app_with_c2c_matrix_realdal: Quart, c2c_readonly_token_matrix: str
) -> None:
    """Test latest matrix fails without test_type parameter."""
    client = app_with_c2c_matrix_realdal.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/matrix/latest",
        headers={"Authorization": f"Bearer {c2c_readonly_token_matrix}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_latest_matrix_readonly(
    app_with_c2c_matrix_realdal: Quart, c2c_readonly_token_matrix: str
) -> None:
    """Test that read-only token can access matrix."""
    client = app_with_c2c_matrix_realdal.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/matrix/latest?test_type=latency",
        headers={"Authorization": f"Bearer {c2c_readonly_token_matrix}"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_latest_matrix_no_token(
    app_with_c2c_matrix_realdal: Quart,
) -> None:
    """Test that missing token returns 403."""
    client = app_with_c2c_matrix_realdal.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/matrix/latest?test_type=latency",
    )

    assert response.status_code == 403


# ============================================================================
# Run Matrix Tests
# ============================================================================


