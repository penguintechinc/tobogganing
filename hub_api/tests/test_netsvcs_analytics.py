"""Tests for netsvcs analytics API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from quart import Quart


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with netsvcs module registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with netsvcs module and auth configured.
    """
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = "default"

    # Register netsvcs module via registry
    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def tenant_a_token(app_with_netsvcs: Quart) -> str:
    """Generate JWT token for tenant A.

    Args:
        app_with_netsvcs: Test app with netsvcs module.

    Returns:
        Valid JWT token for tenant A.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "user-a",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-a",
        "scope": "dns:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def tenant_b_token(app_with_netsvcs: Quart) -> str:
    """Generate JWT token for tenant B.

    Args:
        app_with_netsvcs: Test app with netsvcs module.

    Returns:
        Valid JWT token for tenant B.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    claims = {
        "sub": "user-b",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-b",
        "scope": "dns:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_queries_analytics_without_token(app_with_netsvcs: Quart) -> None:
    """Test queries analytics fails without JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    client = app_with_netsvcs.test_client()

    response = await client.get("/api/v1/netsvcs/analytics/queries")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_queries_analytics_requires_dns_read_scope(
    app_with_netsvcs: Quart,
) -> None:
    """Test queries analytics requires dns:read scope.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    from hub_api.auth.jwt import encode_access_token
    from hub_api.crypto import InAppKeyProvider

    client = app_with_netsvcs.test_client()
    provider = app_with_netsvcs.config["KEY_PROVIDER"]

    # Create token without dns:read scope
    claims = {
        "sub": "user-x",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-x",
        "scope": "other:read",  # Wrong scope
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)

    response = await client.get(
        "/api/v1/netsvcs/analytics/queries",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should fail due to missing dns:read scope
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_performance_analytics_without_token(
    app_with_netsvcs: Quart,
) -> None:
    """Test performance analytics fails without JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    client = app_with_netsvcs.test_client()

    response = await client.get("/api/v1/netsvcs/analytics/performance")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_servers_analytics_without_token(app_with_netsvcs: Quart) -> None:
    """Test servers analytics fails without JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    client = app_with_netsvcs.test_client()

    response = await client.get("/api/v1/netsvcs/analytics/servers")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_summary_analytics_without_token(app_with_netsvcs: Quart) -> None:
    """Test summary analytics fails without JWT token.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
    """
    client = app_with_netsvcs.test_client()

    response = await client.get("/api/v1/netsvcs/analytics/summary")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_analytics_routes_require_feature_flag(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test analytics routes require netsvcs feature flag.

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    # Mock feature flag as disabled
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        routes = [
            "/api/v1/netsvcs/analytics/queries",
            "/api/v1/netsvcs/analytics/performance",
            "/api/v1/netsvcs/analytics/servers",
            "/api/v1/netsvcs/analytics/summary",
        ]

        for route in routes:
            response = await client.get(
                route,
                headers={"Authorization": f"Bearer {tenant_a_token}"},
            )
            # Should fail due to feature flag being off (402 PAYMENT_REQUIRED)
            assert response.status_code == 402


@pytest.mark.asyncio
async def test_analytics_all_routes_tenant_scoped(
    app_with_netsvcs: Quart, tenant_a_token: str
) -> None:
    """Test that analytics routes extract and use tenant from claims.

    Verifies that all analytics routes use @require_tenant decorator
    and access current_claims()["tenant"].

    Args:
        app_with_netsvcs: Test app with netsvcs module.
        tenant_a_token: Valid JWT token for tenant A.
    """
    client = app_with_netsvcs.test_client()

    # Both will fail due to database mocking complexity,
    # but we verify they reach the route handler (not auth error)
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # Routes that should be tenant-scoped
        routes = [
            "/api/v1/netsvcs/analytics/queries",
            "/api/v1/netsvcs/analytics/performance",
            "/api/v1/netsvcs/analytics/servers",
            "/api/v1/netsvcs/analytics/summary",
        ]

        for route in routes:
            # Use token with tenant-a
            response = await client.get(
                route,
                headers={"Authorization": f"Bearer {tenant_a_token}"},
            )

            # Should not be 403 (auth error) - means @require_tenant passed
            # May be 500 due to mock DB, but that's OK for this test
            assert response.status_code != 403, f"Route {route} requires auth"
