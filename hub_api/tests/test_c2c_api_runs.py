"""Tests for C2C runs API using real penguin-dal."""
from __future__ import annotations

import pytest
import pytest_asyncio
from quart import Quart
from typing import Any

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from penguin_dal import AsyncDB


@pytest_asyncio.fixture
async def app_with_c2c_runs_realdal(
    app_with_c2c: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Create test app with C2C module using real_dal."""
    # Patch get_db everywhere it's imported
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    # Patch in all the modules that imported it
    import hub_api.app
    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.perftest_c2c.api.runs
    monkeypatch.setattr(hub_api.modules.perftest_c2c.api.runs, "get_db", get_db_func)

    app_with_c2c.db = real_dal
    return app_with_c2c


@pytest_asyncio.fixture
async def c2c_readonly_token_runs(app_with_c2c_runs_realdal: Quart) -> str:
    """Generate read-only token for runs tests."""
    provider = app_with_c2c_runs_realdal.config["KEY_PROVIDER"]
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
async def c2c_write_token_runs(app_with_c2c_runs_realdal: Quart) -> str:
    """Generate write token for runs tests."""
    provider = app_with_c2c_runs_realdal.config["KEY_PROVIDER"]
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
# Run Creation Tests
# ============================================================================




@pytest.mark.asyncio
async def test_create_run_missing_test_types(
    app_with_c2c_runs_realdal: Quart, c2c_write_token_runs: str
) -> None:
    """Test run creation fails with missing test_types."""
    client = app_with_c2c_runs_realdal.test_client()

    response = await client.post(
        "/api/v1/perftest_c2c/runs",
        json={
            "endpoint_ids": ["ep-1", "ep-2"],
        },
        headers={"Authorization": f"Bearer {c2c_write_token_runs}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_run_missing_endpoint_ids(
    app_with_c2c_runs_realdal: Quart, c2c_write_token_runs: str
) -> None:
    """Test run creation fails with missing endpoint_ids."""
    client = app_with_c2c_runs_realdal.test_client()

    response = await client.post(
        "/api/v1/perftest_c2c/runs",
        json={
            "test_types": ["latency"],
        },
        headers={"Authorization": f"Bearer {c2c_write_token_runs}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_run_readonly_forbidden(
    app_with_c2c_runs_realdal: Quart, c2c_readonly_token_runs: str
) -> None:
    """Test that read-only token cannot create run."""
    client = app_with_c2c_runs_realdal.test_client()

    response = await client.post(
        "/api/v1/perftest_c2c/runs",
        json={
            "test_types": ["latency"],
            "endpoint_ids": ["ep-1", "ep-2"],
        },
        headers={"Authorization": f"Bearer {c2c_readonly_token_runs}"},
    )

    assert response.status_code == 403


# ============================================================================
# Run List Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_run_invalid_test_types(
    app_with_c2c_runs_realdal: Quart, c2c_write_token_runs: str
) -> None:
    """Test run creation fails with invalid test_types."""
    client = app_with_c2c_runs_realdal.test_client()

    response = await client.post(
        "/api/v1/perftest_c2c/runs",
        json={
            "test_types": ["latency", "throughput"],  # Invalid, not in ALLOWED_TEST_TYPES
            "endpoint_ids": ["ep-1", "ep-2"],
        },
        headers={"Authorization": f"Bearer {c2c_write_token_runs}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data
    assert "invalid" in data.get("error", "").lower() or "invalid" in data.get("message", "").lower()


@pytest.mark.asyncio
async def test_create_run_valid_test_types_passes_validation(
    app_with_c2c_runs_realdal: Quart, c2c_write_token_runs: str
) -> None:
    """Test that valid test_types pass validation (may fail for other reasons)."""
    client = app_with_c2c_runs_realdal.test_client()

    response = await client.post(
        "/api/v1/perftest_c2c/runs",
        json={
            "test_types": ["http", "icmp"],  # Valid test types
            "endpoint_ids": ["ep-1", "ep-2"],
        },
        headers={"Authorization": f"Bearer {c2c_write_token_runs}"},
    )

    # Response may be 400 due to missing endpoints, but should NOT be due to invalid test_types
    data = await response.get_json()
    error_msg = data.get("error", "").lower() + data.get("message", "").lower()
    assert "invalid test" not in error_msg, f"Valid test_types should not be rejected: {data}"


@pytest.mark.asyncio
async def test_list_runs_success(
    app_with_c2c_runs_realdal: Quart,
    c2c_readonly_token_runs: str,
    c2c_write_token_runs: str,
) -> None:
    """Test listing runs."""
    client = app_with_c2c_runs_realdal.test_client()

    response = await client.get(
        "/api/v1/perftest_c2c/runs",
        headers={"Authorization": f"Bearer {c2c_readonly_token_runs}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "runs" in data
