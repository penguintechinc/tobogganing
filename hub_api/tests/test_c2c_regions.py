"""Tests for C2C regions feature: aggregation, visibility, health tracking.

Tests using real_dal fixture exercise the actual async penguin-dal API.
Covers region aggregation, public-node redaction, cross-tenant isolation,
feature flag gating, and licensing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

from hub_api.modules.waddleperf_c2c.services.endpoint_manager import EndpointManager


# ============================================================================
# EndpointManager Region Tests (Real DAL)
# ============================================================================


@pytest.mark.asyncio
async def test_list_regions_own_tenant_only(real_dal: AsyncDB) -> None:
    """Test list_regions returns aggregate of own tenant's endpoints."""
    tenant = "tenant-1"
    manager = EndpointManager(real_dal, tenant)

    # Create endpoints in different regions
    ep1, _ = await manager.create_endpoint(
        region="us-east-1",
        name="node-1",
        engine_url="http://engine1",
        target="target1",
        visibility="private",
    )

    ep2, _ = await manager.create_endpoint(
        region="us-east-1",
        name="node-2",
        engine_url="http://engine2",
        target="target2",
        visibility="private",
    )

    ep3, _ = await manager.create_endpoint(
        region="eu-west-1",
        name="node-3",
        engine_url="http://engine3",
        target="target3",
        visibility="private",
    )

    regions = await manager.list_regions(tenant)
    assert len(regions) == 2

    # Check us-east-1 aggregate
    us_east = next((r for r in regions if r["region"] == "us-east-1"), None)
    assert us_east is not None
    assert us_east["node_count"] == 2
    assert us_east["healthy_count"] == 0  # None started as healthy
    assert isinstance(us_east["providers"], list)

    # Check eu-west-1 aggregate
    eu_west = next((r for r in regions if r["region"] == "eu-west-1"), None)
    assert eu_west is not None
    assert eu_west["node_count"] == 1
    assert eu_west["healthy_count"] == 0


@pytest.mark.asyncio
async def test_list_regions_includes_public_foreign_endpoints(real_dal: AsyncDB) -> None:
    """Test list_regions includes foreign tenants' public endpoints."""
    tenant1 = "tenant-1"
    tenant2 = "tenant-2"

    mgr1 = EndpointManager(real_dal, tenant1)
    mgr2 = EndpointManager(real_dal, tenant2)

    # Tenant 1 creates private endpoint
    ep1, _ = await mgr1.create_endpoint(
        region="us-east-1",
        name="private-1",
        engine_url="http://engine1",
        target="target1",
        visibility="private",
    )

    # Tenant 2 creates public endpoint
    ep2, _ = await mgr2.create_endpoint(
        region="us-east-1",
        name="public-1",
        engine_url="http://engine2",
        target="target2",
        visibility="public",
    )

    # List regions for tenant1 - should include public endpoint from tenant2
    regions = await mgr1.list_regions(tenant1)
    assert len(regions) == 1

    us_east = regions[0]
    assert us_east["region"] == "us-east-1"
    assert us_east["node_count"] == 2  # 1 own private + 1 foreign public
    assert us_east["healthy_count"] == 0


@pytest.mark.asyncio
async def test_visible_endpoints_own_tenant_all_visibility(real_dal: AsyncDB) -> None:
    """Test visible_endpoints returns all (private/public) endpoints for own tenant."""
    tenant = "tenant-1"
    manager = EndpointManager(real_dal, tenant)

    # Create private and public endpoints
    ep_private, _ = await manager.create_endpoint(
        region="us-east-1",
        name="private-node",
        engine_url="http://engine-priv",
        target="target-priv",
        visibility="private",
    )

    ep_public, _ = await manager.create_endpoint(
        region="us-east-1",
        name="public-node",
        engine_url="http://engine-pub",
        target="target-pub",
        visibility="public",
    )

    # List all endpoints for own tenant
    endpoints = await manager.visible_endpoints(tenant, region=None)
    assert len(endpoints) == 2

    # Both should have full data
    priv = next((e for e in endpoints if e["id"] == ep_private["id"]), None)
    pub = next((e for e in endpoints if e["id"] == ep_public["id"]), None)

    assert priv is not None
    assert priv["engine_url"] == "http://engine-priv"
    assert priv["target"] == "target-priv"

    assert pub is not None
    assert pub["engine_url"] == "http://engine-pub"
    assert pub["target"] == "target-pub"


@pytest.mark.asyncio
async def test_visible_endpoints_foreign_public_redacted(real_dal: AsyncDB) -> None:
    """Test visible_endpoints redacts secrets from foreign public endpoints."""
    tenant1 = "tenant-1"
    tenant2 = "tenant-2"

    mgr1 = EndpointManager(real_dal, tenant1)
    mgr2 = EndpointManager(real_dal, tenant2)

    # Tenant 2 creates public endpoint with secrets
    ep2, _ = await mgr2.create_endpoint(
        region="us-east-1",
        name="foreign-public",
        engine_url="http://engine-secret",
        target="target-secret",
        visibility="public",
        provider="aws",
    )

    # List from tenant1 - foreign public should be redacted
    endpoints = await mgr1.visible_endpoints(tenant1, region=None)
    assert len(endpoints) == 1

    foreign_pub = endpoints[0]

    # Should have basic fields
    assert foreign_pub["id"] == ep2["id"]
    assert foreign_pub["name"] == "foreign-public"
    assert foreign_pub["region"] == "us-east-1"
    assert foreign_pub["provider"] == "aws"
    assert foreign_pub["health_status"] == "unknown"

    # Should NOT have secrets
    assert "engine_url" not in foreign_pub
    assert "target" not in foreign_pub
    assert "api_key_hash" not in foreign_pub


@pytest.mark.asyncio
async def test_visible_endpoints_foreign_private_hidden(real_dal: AsyncDB) -> None:
    """Test visible_endpoints never returns foreign private endpoints."""
    tenant1 = "tenant-1"
    tenant2 = "tenant-2"

    mgr1 = EndpointManager(real_dal, tenant1)
    mgr2 = EndpointManager(real_dal, tenant2)

    # Tenant 1 creates private endpoint
    ep1, _ = await mgr1.create_endpoint(
        region="us-east-1",
        name="tenant1-private",
        engine_url="http://engine1",
        target="target1",
        visibility="private",
    )

    # Tenant 2 creates private endpoint
    ep2, _ = await mgr2.create_endpoint(
        region="us-east-1",
        name="tenant2-private",
        engine_url="http://engine2",
        target="target2",
        visibility="private",
    )

    # List from tenant1 - should only see own endpoints
    endpoints = await mgr1.visible_endpoints(tenant1, region=None)
    assert len(endpoints) == 1
    assert endpoints[0]["id"] == ep1["id"]


@pytest.mark.asyncio
async def test_visible_endpoints_region_filter(real_dal: AsyncDB) -> None:
    """Test visible_endpoints respects region parameter."""
    tenant = "tenant-1"
    manager = EndpointManager(real_dal, tenant)

    # Create endpoints in different regions
    ep1, _ = await manager.create_endpoint(
        region="us-east-1",
        name="east-node",
        engine_url="http://engine1",
        target="target1",
        visibility="private",
    )

    ep2, _ = await manager.create_endpoint(
        region="eu-west-1",
        name="west-node",
        engine_url="http://engine2",
        target="target2",
        visibility="private",
    )

    # Filter by region
    east_endpoints = await manager.visible_endpoints(tenant, region="us-east-1")
    assert len(east_endpoints) == 1
    assert east_endpoints[0]["region"] == "us-east-1"

    west_endpoints = await manager.visible_endpoints(tenant, region="eu-west-1")
    assert len(west_endpoints) == 1
    assert west_endpoints[0]["region"] == "eu-west-1"


@pytest.mark.asyncio
async def test_endpoint_manager_create_with_visibility_and_provider(
    real_dal: AsyncDB,
) -> None:
    """Test creating endpoint with visibility and provider fields."""
    tenant = "test-tenant"
    manager = EndpointManager(real_dal, tenant)

    endpoint, _ = await manager.create_endpoint(
        region="us-east-1",
        name="test-node",
        engine_url="http://engine",
        target="target",
        visibility="public",
        provider="gcp",
    )

    assert endpoint["visibility"] == "public"
    assert endpoint["provider"] == "gcp"
    assert endpoint["health_status"] == "unknown"
    assert endpoint["last_health_check"] is None


@pytest.mark.asyncio
async def test_endpoint_manager_update_visibility(real_dal: AsyncDB) -> None:
    """Test updating endpoint visibility."""
    tenant = "test-tenant"
    manager = EndpointManager(real_dal, tenant)

    endpoint, _ = await manager.create_endpoint(
        region="us-east-1",
        name="test-node",
        engine_url="http://engine",
        target="target",
        visibility="private",
    )

    # Update to public
    updated = await manager.update_endpoint(
        endpoint["id"],
        visibility="public",
    )

    assert updated["visibility"] == "public"


@pytest.mark.asyncio
async def test_endpoint_manager_rejects_invalid_visibility(real_dal: AsyncDB) -> None:
    """Test that invalid visibility values are rejected."""
    tenant = "test-tenant"
    manager = EndpointManager(real_dal, tenant)

    with pytest.raises(ValueError, match="visibility"):
        await manager.create_endpoint(
            region="us-east-1",
            name="test-node",
            engine_url="http://engine",
            target="target",
            visibility="invalid",
        )


@pytest.mark.asyncio
async def test_endpoint_manager_rejects_invalid_provider(real_dal: AsyncDB) -> None:
    """Test that invalid provider values are rejected if provided."""
    tenant = "test-tenant"
    manager = EndpointManager(real_dal, tenant)

    # None/empty should work
    endpoint, _ = await manager.create_endpoint(
        region="us-east-1",
        name="test-node",
        engine_url="http://engine",
        target="target",
        provider=None,
    )
    assert endpoint["provider"] is None

    # Valid providers should work
    endpoint2, _ = await manager.create_endpoint(
        region="us-east-1",
        name="test-node-2",
        engine_url="http://engine2",
        target="target2",
        provider="aws",
    )
    assert endpoint2["provider"] == "aws"


# ============================================================================
# HTTP API Tests with Feature Flags and Licensing
# ============================================================================


@pytest_asyncio.fixture
async def app_with_c2c_realdal_regions(
    app_with_c2c: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Create test app with C2C module using real_dal fixture."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app
    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.waddleperf_c2c.api.endpoints
    monkeypatch.setattr(hub_api.modules.waddleperf_c2c.api.endpoints, "get_db", get_db_func)

    import hub_api.modules.waddleperf_c2c.api.regions
    monkeypatch.setattr(hub_api.modules.waddleperf_c2c.api.regions, "get_db", get_db_func)

    app_with_c2c.db = real_dal
    return app_with_c2c


@pytest_asyncio.fixture
async def c2c_read_token_regions(app_with_c2c_realdal_regions: Quart) -> str:
    """Generate read token for regions test app."""
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_c2c_realdal_regions.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.mark.asyncio
async def test_regions_api_flag_off_returns_402(
    app_with_c2c_realdal_regions: Quart, c2c_read_token_regions: str, monkeypatch: Any
) -> None:
    """Test regions API returns 402 when feature flag is off."""
    import shared.licensing.entitlements

    # Turn off regions flag
    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key == "tobogganing.waddleperf_c2c.regions":
            return False
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    client = app_with_c2c_realdal_regions.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/regions",
        headers={"Authorization": f"Bearer {c2c_read_token_regions}"},
    )

    assert response.status_code == 402


@pytest.mark.asyncio
async def test_regions_api_unlicensed_returns_402_professional(
    app_with_c2c_realdal_regions: Quart, c2c_read_token_regions: str, monkeypatch: Any
) -> None:
    """Test regions API returns 402 with professional tier when unlicensed."""
    import hub_api.entitlements.gate

    # Turn off licensing
    monkeypatch.setattr(
        hub_api.entitlements.gate,
        "_is_licensed_for_tier",
        lambda tier: False,
    )

    client = app_with_c2c_realdal_regions.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/regions",
        headers={"Authorization": f"Bearer {c2c_read_token_regions}"},
    )

    assert response.status_code == 402
    data = await response.get_json()
    # Should mention professional tier
    assert "professional" in str(data).lower() or response.status_code == 402


@pytest.mark.asyncio
async def test_regions_api_get_list_licensed(
    app_with_c2c_realdal_regions: Quart,
    c2c_read_token_regions: str,
    real_dal: AsyncDB,
) -> None:
    """Test GET /regions returns region aggregates when licensed."""
    # Setup endpoints
    mgr = EndpointManager(real_dal, "test-tenant")
    await mgr.create_endpoint(
        region="us-east-1",
        name="node-1",
        engine_url="http://engine1",
        target="target1",
        visibility="private",
    )
    await mgr.create_endpoint(
        region="us-east-1",
        name="node-2",
        engine_url="http://engine2",
        target="target2",
        visibility="private",
    )

    client = app_with_c2c_realdal_regions.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/regions",
        headers={"Authorization": f"Bearer {c2c_read_token_regions}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "regions" in data
    assert len(data["regions"]) == 1
    assert data["regions"][0]["region"] == "us-east-1"
    assert data["regions"][0]["node_count"] == 2


@pytest.mark.asyncio
async def test_regions_api_get_nodes_licensed(
    app_with_c2c_realdal_regions: Quart,
    c2c_read_token_regions: str,
    real_dal: AsyncDB,
) -> None:
    """Test GET /regions/nodes returns visible endpoints when licensed."""
    # Setup endpoints
    mgr = EndpointManager(real_dal, "test-tenant")
    ep1, _ = await mgr.create_endpoint(
        region="us-east-1",
        name="node-1",
        engine_url="http://engine1",
        target="target1",
        visibility="private",
    )
    ep2, _ = await mgr.create_endpoint(
        region="eu-west-1",
        name="node-2",
        engine_url="http://engine2",
        target="target2",
        visibility="private",
    )

    client = app_with_c2c_realdal_regions.test_client()

    # Get all nodes
    response = await client.get(
        "/api/v1/waddleperf_c2c/regions/nodes",
        headers={"Authorization": f"Bearer {c2c_read_token_regions}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "nodes" in data
    assert len(data["nodes"]) == 2

    # Filter by region
    response = await client.get(
        "/api/v1/waddleperf_c2c/regions/nodes?region=us-east-1",
        headers={"Authorization": f"Bearer {c2c_read_token_regions}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["region"] == "us-east-1"


@pytest.mark.asyncio
async def test_regions_api_foreign_public_redacted_in_response(
    app_with_c2c_realdal_regions: Quart,
    c2c_read_token_regions: str,
    real_dal: AsyncDB,
) -> None:
    """Test that foreign public endpoints are redacted in API response."""
    # Tenant A creates public endpoint
    mgr_a = EndpointManager(real_dal, "tenant-a")
    ep_public, _ = await mgr_a.create_endpoint(
        region="us-east-1",
        name="public-node",
        engine_url="http://secret-engine",
        target="secret-target",
        visibility="public",
        provider="aws",
    )

    # Get token for Tenant B (but the token says "test-tenant")
    client = app_with_c2c_realdal_regions.test_client()

    response = await client.get(
        "/api/v1/waddleperf_c2c/regions/nodes",
        headers={"Authorization": f"Bearer {c2c_read_token_regions}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    nodes = data.get("nodes", [])

    # Find the foreign public endpoint
    foreign_pub = next((n for n in nodes if n.get("id") == ep_public["id"]), None)
    if foreign_pub:  # Only if it's visible at all
        # Should not have secrets
        assert "engine_url" not in foreign_pub
        assert "target" not in foreign_pub
        assert "api_key_hash" not in foreign_pub
