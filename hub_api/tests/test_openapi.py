"""Tests for OpenAPI spec generation and routing."""

from __future__ import annotations

import pytest
import pytest_asyncio
from quart import Quart


@pytest.fixture
def app_with_key_provider(app: Quart) -> Quart:
    """Set up app with a real key provider for token generation in tests.

    Args:
        app: Base test app fixture.

    Returns:
        Quart app with KEY_PROVIDER configured.
    """
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    # Matches the "iss"/"aud" used by the valid_token fixture below, so
    # _validate_and_store_token's aud/iss enforcement accepts it.
    app.config["PRODUCT_NAME"] = "test-app"
    return app


@pytest_asyncio.fixture
async def valid_token(app_with_key_provider: Quart) -> str:
    """Generate a valid JWT token for testing authenticated endpoints.

    Args:
        app_with_key_provider: App with key provider configured.

    Returns:
        Encoded JWT token string.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_key_provider.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_public_docs_no_auth_required(app: Quart) -> None:
    """Test /docs/public is accessible without authentication.

    The public docs should expose only the login endpoint
    to allow unauthenticated clients to discover how to authenticate.

    Args:
        app: Quart application fixture.
    """
    client = app.test_client()
    resp = await client.get("/docs/public")
    assert resp.status_code == 200

    data = await resp.get_json()
    assert data["openapi"] == "3.1.0"
    assert data["info"]["title"]  # Should have a title
    assert "/api/v1/auth/login" in data["paths"]
    # Public docs should NOT expose other auth endpoints (require token)
    assert "/api/v1/auth/refresh-token" not in data["paths"]
    assert "/api/v1/auth/logout" not in data["paths"]


@pytest.mark.asyncio
async def test_openapi_json_no_token_returns_401(app: Quart) -> None:
    """Test /openapi.json returns 401 without authentication token.

    The full spec is sensitive and should require authentication
    to prevent unauthenticated enumeration of the API surface.

    Args:
        app: Quart application fixture.
    """
    client = app.test_client()
    resp = await client.get("/openapi.json")
    assert resp.status_code == 401

    data = await resp.get_json()
    assert "error" in data
    assert "Unauthorized" in data["error"]


@pytest.mark.asyncio
async def test_openapi_json_with_valid_token_returns_200(
    app_with_key_provider: Quart, valid_token: str
) -> None:
    """Test /openapi.json returns 200 with a valid JWT token.

    An authenticated request should receive the full OpenAPI spec,
    exposing all endpoints, schemas, and security requirements.

    Args:
        app_with_key_provider: App with key provider configured.
        valid_token: Valid JWT token from fixture.
    """
    client = app_with_key_provider.test_client()

    # Request with Bearer token
    headers = {"Authorization": f"Bearer {valid_token}"}
    resp = await client.get("/openapi.json", headers=headers)
    assert resp.status_code == 200

    data = await resp.get_json()
    assert data["openapi"] == "3.1.0"
    assert data["info"]["title"]  # Should have a title
    # Full spec should expose all endpoints
    assert "/api/v1/auth/login" in data["paths"]
    assert "/api/v1/auth/refresh-token" in data["paths"]
    assert "/api/v1/auth/logout" in data["paths"]
    assert "/health" in data["paths"]
    assert "/ready" in data["paths"]


@pytest.mark.asyncio
async def test_public_docs_includes_login_schema(app: Quart) -> None:
    """Test /docs/public includes complete schema for login endpoint.

    The public docs should provide enough information for a client
    to successfully call the login endpoint.

    Args:
        app: Quart application fixture.
    """
    client = app.test_client()
    resp = await client.get("/docs/public")
    assert resp.status_code == 200

    data = await resp.get_json()
    login_endpoint = data["paths"]["/api/v1/auth/login"]["post"]

    # Check request schema
    assert "requestBody" in login_endpoint
    schema = login_endpoint["requestBody"]["content"]["application/json"]["schema"]
    assert schema["type"] == "object"
    assert "email" in schema["properties"]
    assert "password" in schema["properties"]
    assert "email" in schema["required"]
    assert "password" in schema["required"]

    # Check response schemas
    assert "responses" in login_endpoint
    assert "200" in login_endpoint["responses"]
    assert "401" in login_endpoint["responses"]
