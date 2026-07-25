"""Tests for the ping module."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.entitlements.gate import TIER_PROFESSIONAL, require_feature
from hub_api.registry import ModuleContext


@pytest.fixture
def app_with_ping(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with ping module registered and key provider configured.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with ping module and auth configured.
    """
    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Manually apply the registry to ensure routes are mounted
    # This is necessary because before_serving doesn't run in test contexts
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def valid_tenant_token(app_with_ping: Quart) -> str:
    """Generate a valid tenant JWT token for testing.

    Args:
        app_with_ping: App with key provider.

    Returns:
        Encoded JWT token with tenant claim.
    """
    provider = app_with_ping.config["KEY_PROVIDER"]

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
async def test_ping_module_declared_in_registry(app: Quart) -> None:
    """Test that the ping module is registered in the app registry.

    Args:
        app: Test app fixture.
    """
    # Check that ping module's flags are declared
    flags = app.registry.declared_flags()
    assert "tobogganing.ping.enabled" in flags
    assert "tobogganing.ping.pro" in flags


@pytest.mark.asyncio
async def test_ping_endpoint_flag_off(app_with_ping: Quart, valid_tenant_token: str) -> None:
    """Test that /api/v1/ping returns 402 when flag is off.

    Args:
        app_with_ping: App with auth configured.
        valid_tenant_token: Valid JWT token with tenant claim.
    """
    client = app_with_ping.test_client()

    # Mock the flag as disabled
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        response = await client.get(
            "/api/v1/ping",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 402
        data = await response.get_json()
        assert data["error"] == "Feature not available"


@pytest.mark.asyncio
async def test_ping_endpoint_flag_on(app_with_ping: Quart, valid_tenant_token: str) -> None:
    """Test that /api/v1/ping returns 200 with flag on.

    Args:
        app_with_ping: App with auth configured.
        valid_tenant_token: Valid JWT token with tenant claim.
    """
    client = app_with_ping.test_client()

    # Mock the flag as enabled
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get(
            "/api/v1/ping",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["pong"] is True
        assert data["meta"]["version"] == 1
        assert "timestamp" in data["meta"]


@pytest.mark.asyncio
async def test_ping_endpoint_no_token(app_with_ping: Quart) -> None:
    """Test that /api/v1/ping returns 403 without token.

    Args:
        app_with_ping: App with auth configured.
    """
    client = app_with_ping.test_client()

    # Mock the flag as enabled
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get("/api/v1/ping")

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_ping_pro_endpoint_flag_off(app_with_ping: Quart, valid_tenant_token: str) -> None:
    """Test that /api/v1/ping/pro returns 402 when flag is off.

    Args:
        app_with_ping: App with auth configured.
        valid_tenant_token: Valid JWT token with tenant claim.
    """
    client = app_with_ping.test_client()

    # Mock the flag as disabled
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        response = await client.get(
            "/api/v1/ping/pro",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 402
        data = await response.get_json()
        assert data["error"] == "Feature not available"


@pytest.mark.asyncio
async def test_ping_pro_endpoint_without_license(
    app_with_ping: Quart, valid_tenant_token: str
) -> None:
    """Test that /api/v1/ping/pro returns 402 without professional license.

    Args:
        app_with_ping: App with auth configured.
        valid_tenant_token: Valid JWT token with tenant claim.
    """
    client = app_with_ping.test_client()

    # Mock the flag as enabled but license check fails
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        with patch("hub_api.entitlements.gate._is_licensed_for_tier") as mock_licensed:
            mock_licensed.return_value = False

            response = await client.get(
                "/api/v1/ping/pro",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 402
            data = await response.get_json()
            assert data["error"] == "License required"
            assert data["tier"] == TIER_PROFESSIONAL


@pytest.mark.asyncio
async def test_ping_pro_endpoint_with_license(
    app_with_ping: Quart, valid_tenant_token: str
) -> None:
    """Test that /api/v1/ping/pro returns 200 with professional license.

    Args:
        app_with_ping: App with auth configured.
        valid_tenant_token: Valid JWT token with tenant claim.
    """
    client = app_with_ping.test_client()

    # Mock the flag as enabled and license check passes
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        with patch("hub_api.entitlements.gate._is_licensed_for_tier") as mock_licensed:
            mock_licensed.return_value = True

            response = await client.get(
                "/api/v1/ping/pro",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert data["pong"] == "pro"
            assert data["meta"]["version"] == 1
            assert "timestamp" in data["meta"]


@pytest.mark.asyncio
async def test_ping_pro_endpoint_no_token(app_with_ping: Quart) -> None:
    """Test that /api/v1/ping/pro returns 403 without token.

    Args:
        app_with_ping: App with auth configured.
    """
    client = app_with_ping.test_client()

    # Mock the flag as enabled
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        response = await client.get("/api/v1/ping/pro")

        assert response.status_code == 403
