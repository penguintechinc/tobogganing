"""Tests for machine-JWT issuance with tenant + identity binding (regression C3/C4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

import pytest
import jwt as pyjwt
from quart import Quart

from hub_api.auth.jwt import decode_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster


@pytest.fixture
def app_with_headend(app: Quart) -> Quart:
    """Create a test app with headend routes and AsyncMock for cluster manager.

    The app fixture from conftest.py already registers all blueprints via create_app().
    We just need to configure the managers with AsyncMocks.

    Args:
        app: Base test app fixture (already has headend_bp registered).

    Returns:
        Quart app with KEY_PROVIDER and managers configured with AsyncMocks.
    """
    # Set up key provider for token generation
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Mock cluster manager with AsyncMock for authenticate_cluster
    cluster_manager = MagicMock()
    cluster_manager.authenticate_cluster = AsyncMock()
    client_registry = MagicMock()
    client_registry.authenticate_client = AsyncMock()
    app.config["CLUSTER_MANAGER"] = cluster_manager
    app.config["CLIENT_REGISTRY"] = client_registry

    return app


@pytest.fixture
def cluster_stub() -> Cluster:
    """Provide a test cluster with real tenant field (not tenant_id).

    Returns:
        Cluster stub with id="c1", tenant="acme", status="active".
    """
    now = datetime.now(timezone.utc)
    return Cluster(
        id="c1",
        name="test-cluster",
        region="us-west-2",
        datacenter="dc1",
        headend_url="https://headend.example.com",
        status="active",
        last_heartbeat=now,
        client_count=0,
        tenant="acme",  # The real field is .tenant, not .tenant_id
    )


@pytest.mark.asyncio
async def test_auth_token_cluster_uses_real_tenant(
    app_with_headend: Quart, cluster_stub: Cluster
) -> None:
    """Test /auth/token returns access token with real tenant (regression C3).

    The bug: code reads getattr(cluster, "tenant_id", "default") but field is .tenant
    → machine JWTs always get tenant="default"

    Fix: read cluster.tenant instead.

    Args:
        app_with_headend: Test app with key provider and cluster manager.
        cluster_stub: Cluster fixture with tenant="acme".
    """
    client = app_with_headend.test_client()

    # Mock authenticate_cluster to return cluster_stub
    cluster_manager = app_with_headend.config["CLUSTER_MANAGER"]
    cluster_manager.authenticate_cluster.return_value = cluster_stub

    response = await client.post(
        "/api/v1/auth/token",
        json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "test-key"},
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = await response.get_json()
    assert "access_token" in data

    # Decode the access token and check claims
    key_provider = app_with_headend.config["KEY_PROVIDER"]
    claims = decode_token(data["access_token"], key_provider)
    assert claims is not None, "Failed to decode access token"

    # Regression C3: tenant should be "acme", not "default"
    assert claims["tenant"] == "acme", f"Expected tenant='acme', got {claims['tenant']}"
    # Machine JWT sub is prefixed: cluster:c1 for cluster nodes
    assert claims["sub"] == "cluster:c1", f"Expected sub='cluster:c1', got {claims['sub']}"
    assert "jti" in claims, "Missing jti claim"
    assert "scope" in claims, "Missing scope claim"


@pytest.mark.asyncio
async def test_auth_token_binds_identity_matching_node_id(
    app_with_headend: Quart, cluster_stub: Cluster
) -> None:
    """Test /auth/token succeeds when node_id matches cluster.id (regression C4).

    The bug: code does `await asyncio.to_thread(authenticate_cluster, api_key)`
    but authenticate_cluster is async def, so to_thread() runs it in thread returning
    an un-awaited coroutine → cluster is None → identity check fails

    Fix: `await authenticate_cluster(api_key)` (drop to_thread wrapper).

    Args:
        app_with_headend: Test app with key provider and cluster manager.
        cluster_stub: Cluster fixture with id="c1".
    """
    client = app_with_headend.test_client()

    # Mock authenticate_cluster to return cluster_stub
    cluster_manager = app_with_headend.config["CLUSTER_MANAGER"]
    cluster_manager.authenticate_cluster.return_value = cluster_stub

    # Matching node_id → 200
    response = await client.post(
        "/api/v1/auth/token",
        json={"node_id": "c1", "node_type": "kubernetes_node", "api_key": "test-key"},
    )

    assert (
        response.status_code == 200
    ), f"Matching node_id failed: {response.status_code}"


@pytest.mark.asyncio
async def test_auth_token_rejects_mismatched_node_id(
    app_with_headend: Quart, cluster_stub: Cluster
) -> None:
    """Test /auth/token fails when node_id doesn't match cluster.id.

    This ensures the identity binding actually works (regression C4).

    Args:
        app_with_headend: Test app with key provider and cluster manager.
        cluster_stub: Cluster fixture with id="c1".
    """
    client = app_with_headend.test_client()

    # Mock authenticate_cluster to return cluster_stub
    cluster_manager = app_with_headend.config["CLUSTER_MANAGER"]
    cluster_manager.authenticate_cluster.return_value = cluster_stub

    # Mismatched node_id → 401
    response = await client.post(
        "/api/v1/auth/token",
        json={"node_id": "other-id", "node_type": "kubernetes_node", "api_key": "test-key"},
    )

    assert (
        response.status_code == 401
    ), f"Mismatched node_id should fail with 401, got {response.status_code}"
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_revoke_cross_tenant_guard_same_tenant(
    app_with_headend: Quart, cluster_stub: Cluster
) -> None:
    """Test revoke endpoint allows revocation within same tenant (regression C3/C4).

    The bug: node_tenant was always "default" due to C3/C4 (no real tenant lookup).
    Result: cross-tenant guard never worked; could revoke other tenants' nodes.

    Fix: read cluster.tenant (C3) + await async get_cluster (C4) properly.
    Now revoke within same tenant is allowed.

    Args:
        app_with_headend: Test app with key provider and managers.
        cluster_stub: Cluster stub with tenant="acme".
    """
    from unittest.mock import patch

    from hub_api.auth.jwt import encode_access_token

    client = app_with_headend.test_client()

    # Mock get_cluster to return cluster_stub with tenant="acme"
    cluster_manager = app_with_headend.config["CLUSTER_MANAGER"]
    cluster_manager.get_cluster = AsyncMock(return_value=cluster_stub)

    # Create a valid JWT token with tenant="acme" (same as cluster_stub)
    key_provider = app_with_headend.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "acme",
        "scope": "jwt:revoke",
    }
    token = await encode_access_token(claims, key_provider, ttl_hours=1)

    # Mock feature flag to allow jwt feature
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # POST /api/v1/jwt/revoke with matching tenant → 200
        response = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "c1"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, f"Revoke same tenant failed: {response.status_code}"
    data = await response.get_json()
    assert data["revoked"] is True


@pytest.mark.asyncio
async def test_revoke_cross_tenant_guard_different_tenant(
    app_with_headend: Quart, cluster_stub: Cluster
) -> None:
    """Test revoke endpoint blocks cross-tenant revocation (regression C3/C4).

    Caller has tenant="other"; target cluster has tenant="acme".
    Should be rejected with 403 (cross-tenant guard working correctly).

    Args:
        app_with_headend: Test app with key provider and managers.
        cluster_stub: Cluster stub with tenant="acme".
    """
    from unittest.mock import patch

    from hub_api.auth.jwt import encode_access_token

    client = app_with_headend.test_client()

    # Mock get_cluster to return cluster_stub with tenant="acme"
    cluster_manager = app_with_headend.config["CLUSTER_MANAGER"]
    cluster_manager.get_cluster = AsyncMock(return_value=cluster_stub)

    # Create a valid JWT token with tenant="other" (different from cluster_stub)
    key_provider = app_with_headend.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-2",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "other",
        "scope": "jwt:revoke",
    }
    token = await encode_access_token(claims, key_provider, ttl_hours=1)

    # Mock feature flag to allow jwt feature
    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = True

        # POST /api/v1/jwt/revoke with mismatched tenant → 403
        response = await client.post(
            "/api/v1/jwt/revoke",
            json={"node_id": "c1"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert (
        response.status_code == 403
    ), f"Cross-tenant revoke should be 403, got {response.status_code}"
    data = await response.get_json()
    assert "Forbidden" in data["error"]
