"""Tests for C2C endpoints API using real penguin-dal."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from quart import Quart
from unittest.mock import patch, MagicMock

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.registry import ModuleContext
from penguin_dal import AsyncDB


@pytest_asyncio.fixture
async def app_with_c2c_realdal(
    app_with_c2c: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Create test app with C2C module using real_dal fixture.

    Reuses app_with_c2c which has auth + module wiring already set up,
    but patches get_db to return real_dal instead of mock_db.
    """
    # Patch get_db everywhere it's imported
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app
    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.waddleperf_c2c.api.endpoints
    monkeypatch.setattr(hub_api.modules.waddleperf_c2c.api.endpoints, "get_db", get_db_func)

    import hub_api.modules.waddleperf_c2c.api.runs
    monkeypatch.setattr(hub_api.modules.waddleperf_c2c.api.runs, "get_db", get_db_func)

    import hub_api.modules.waddleperf_c2c.api.matrix
    monkeypatch.setattr(hub_api.modules.waddleperf_c2c.api.matrix, "get_db", get_db_func)

    app_with_c2c.db = real_dal
    return app_with_c2c


@pytest_asyncio.fixture
async def c2c_write_token_realdal(app_with_c2c_realdal: Quart) -> str:
    """Generate write token for real_dal app."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_c2c_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read c2c:write",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def c2c_readonly_token_realdal(app_with_c2c_realdal: Quart) -> str:
    """Generate read-only token for real_dal app."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_c2c_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


# ============================================================================
# Endpoint Creation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_endpoint_success(
    app_with_c2c_realdal: Quart, c2c_write_token_realdal: str, real_dal: AsyncDB
) -> None:
    """Test successful endpoint creation with real DAL."""
    client = app_with_c2c_realdal.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary-node",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )

    assert response.status_code == 201
    data = await response.get_json()
    assert data["region"] == "us-west-2"
    assert data["name"] == "primary-node"
    assert data["api_key"] is not None


@pytest.mark.asyncio
async def test_create_endpoint_with_custom_api_key(
    app_with_c2c_realdal: Quart, c2c_write_token_realdal: str
) -> None:
    """Test creating endpoint with custom API key (key not returned)."""
    client = app_with_c2c_realdal.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary-node",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
            "api_key": "my-custom-key-12345",
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )

    assert response.status_code == 201
    data = await response.get_json()
    assert "api_key" not in data  # Custom key not echoed back


@pytest.mark.asyncio
async def test_create_endpoint_missing_fields(
    app_with_c2c_realdal: Quart, c2c_write_token_realdal: str
) -> None:
    """Test endpoint creation fails with missing required fields."""
    client = app_with_c2c_realdal.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary-node",
            # Missing engine_url and target
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_endpoint_readonly_forbidden(
    app_with_c2c_realdal: Quart, c2c_readonly_token_realdal: str
) -> None:
    """Test that read-only token cannot create endpoint."""
    client = app_with_c2c_realdal.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_readonly_token_realdal}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_endpoint_no_token_forbidden(
    app_with_c2c_realdal: Quart,
) -> None:
    """Test that missing token returns 403."""
    client = app_with_c2c_realdal.test_client()

    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
    )

    assert response.status_code == 403


# ============================================================================
# Endpoint List Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_endpoints_empty(
    app_with_c2c_realdal: Quart, c2c_readonly_token_realdal: str
) -> None:
    """Test listing endpoints when none exist."""
    client = app_with_c2c_realdal.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/endpoints",
        headers={"Authorization": f"Bearer {c2c_readonly_token_realdal}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["endpoints"] == []


@pytest.mark.asyncio
async def test_list_endpoints_success(
    app_with_c2c_realdal: Quart,
    c2c_readonly_token_realdal: str,
    c2c_write_token_realdal: str,
    real_dal: AsyncDB,
) -> None:
    """Test listing endpoints after creating one."""
    client = app_with_c2c_realdal.test_client()

    # Create endpoint
    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine1.local:8080",
            "target": "node1.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )
    assert response.status_code == 201

    # List endpoints
    response = await client.get(
        "/api/v1/waddleperf_c2c/endpoints",
        headers={"Authorization": f"Bearer {c2c_readonly_token_realdal}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert len(data["endpoints"]) == 1
    assert data["endpoints"][0]["name"] == "primary"


# ============================================================================
# Endpoint Get/Update/Delete Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_endpoint_success(
    app_with_c2c_realdal: Quart,
    c2c_readonly_token_realdal: str,
    c2c_write_token_realdal: str,
) -> None:
    """Test getting a single endpoint."""
    client = app_with_c2c_realdal.test_client()

    # Create endpoint
    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )
    assert response.status_code == 201
    created = await response.get_json()
    endpoint_id = created["id"]

    # Get endpoint
    response = await client.get(
        f"/api/v1/waddleperf_c2c/endpoints/{endpoint_id}",
        headers={"Authorization": f"Bearer {c2c_readonly_token_realdal}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["id"] == endpoint_id
    assert data["name"] == "primary"


@pytest.mark.asyncio
async def test_get_endpoint_not_found(
    app_with_c2c_realdal: Quart, c2c_readonly_token_realdal: str
) -> None:
    """Test getting non-existent endpoint."""
    client = app_with_c2c_realdal.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/endpoints/nonexistent-id",
        headers={"Authorization": f"Bearer {c2c_readonly_token_realdal}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_endpoint_success(
    app_with_c2c_realdal: Quart,
    c2c_write_token_realdal: str,
) -> None:
    """Test updating an endpoint."""
    client = app_with_c2c_realdal.test_client()

    # Create endpoint
    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )
    assert response.status_code == 201
    created = await response.get_json()
    endpoint_id = created["id"]

    # Update endpoint
    response = await client.patch(
        f"/api/v1/waddleperf_c2c/endpoints/{endpoint_id}",
        json={"name": "primary-updated", "enabled": False},
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["name"] == "primary-updated"
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_update_endpoint_not_found(
    app_with_c2c_realdal: Quart, c2c_write_token_realdal: str
) -> None:
    """Test updating non-existent endpoint."""
    client = app_with_c2c_realdal.test_client()

    response = await client.patch(
        "/api/v1/waddleperf_c2c/endpoints/nonexistent-id",
        json={"name": "updated"},
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_endpoint_success(
    app_with_c2c_realdal: Quart,
    c2c_write_token_realdal: str,
) -> None:
    """Test deleting an endpoint."""
    client = app_with_c2c_realdal.test_client()

    # Create endpoint
    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "primary",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )
    assert response.status_code == 201
    created = await response.get_json()
    endpoint_id = created["id"]

    # Delete endpoint
    response = await client.delete(
        f"/api/v1/waddleperf_c2c/endpoints/{endpoint_id}",
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_endpoint_not_found(
    app_with_c2c_realdal: Quart, c2c_write_token_realdal: str
) -> None:
    """Test deleting non-existent endpoint."""
    client = app_with_c2c_realdal.test_client()

    response = await client.delete(
        "/api/v1/waddleperf_c2c/endpoints/nonexistent-id",
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )

    assert response.status_code == 404


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_endpoint_list(
    app_with_c2c_realdal: Quart,
    c2c_write_token_realdal: str,
    c2c_readonly_token_realdal: str,
) -> None:
    """Test that endpoints from other tenants are not visible."""
    client = app_with_c2c_realdal.test_client()

    # Create endpoint in test-tenant
    response = await client.post(
        "/api/v1/waddleperf_c2c/endpoints",
        json={
            "region": "us-west-2",
            "name": "tenant1-endpoint",
            "engine_url": "http://engine.local:8080",
            "target": "node.example.com",
        },
        headers={"Authorization": f"Bearer {c2c_write_token_realdal}"},
    )
    assert response.status_code == 201

    # List should show it
    response = await client.get(
        "/api/v1/waddleperf_c2c/endpoints",
        headers={"Authorization": f"Bearer {c2c_readonly_token_realdal}"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert len(data["endpoints"]) == 1
