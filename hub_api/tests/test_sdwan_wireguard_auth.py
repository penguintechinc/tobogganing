"""Regression tests for WireGuard identity spoofing security fix.

Tests that the POST /keys endpoint properly validates both node_id and tenant_id
against the authenticated identity's claims, preventing cross-tenant and cross-node
key generation.

regression: security-review wireguard identity spoofing
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from quart import Quart


@pytest.fixture
def app_with_sdwan(app_with_sase: Quart, monkeypatch: Any) -> Quart:
    """Create app with SASE and SDWAN managers configured.

    Args:
        app_with_sase: Base SASE app fixture.
        monkeypatch: Pytest monkeypatch for enabling feature flags.

    Returns:
        App with SDWAN managers (cluster_manager, client_registry, etc.) mocked.
    """
    # Enable sase/wireguard feature flags for tests
    import shared.licensing.entitlements

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.sase."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    # Mock cluster manager that returns stub identity objects
    cluster_manager = MagicMock()

    def mock_authenticate_cluster(api_key: str) -> MagicMock | None:
        """Mock cluster authentication (sync for asyncio.to_thread) returning stub with id and tenant."""
        if api_key == "valid-cluster-key":
            stub = MagicMock()
            stub.id = "cluster-node-1"
            stub.tenant = "test-tenant"
            return stub
        elif api_key == "cluster-key-wrong-node":
            stub = MagicMock()
            stub.id = "cluster-node-2"  # mismatched node_id
            stub.tenant = "test-tenant"
            return stub
        elif api_key == "cluster-key-wrong-tenant":
            stub = MagicMock()
            stub.id = "cluster-node-1"
            stub.tenant = "other-tenant"  # mismatched tenant
            return stub
        return None

    cluster_manager.authenticate_cluster = mock_authenticate_cluster

    # Mock client registry
    client_registry = MagicMock()

    def mock_authenticate_client(api_key: str) -> MagicMock | None:
        """Mock client authentication (sync for asyncio.to_thread) returning stub with id and tenant."""
        if api_key == "valid-client-key":
            stub = MagicMock()
            stub.id = "client-node-1"
            stub.tenant = "test-tenant"
            return stub
        elif api_key == "client-key-wrong-node":
            stub = MagicMock()
            stub.id = "client-node-2"  # mismatched node_id
            stub.tenant = "test-tenant"
            return stub
        elif api_key == "client-key-wrong-tenant":
            stub = MagicMock()
            stub.id = "client-node-1"
            stub.tenant = "other-tenant"  # mismatched tenant
            return stub
        return None

    client_registry.authenticate_client = mock_authenticate_client

    # Mock WireGuard manager (async methods since they're awaited in the handler)
    from unittest.mock import AsyncMock

    wg_manager = MagicMock()
    wg_manager.generate_wireguard_keys = AsyncMock(
        return_value={
            "private_key": "private-key",
            "public_key": "public-key",
            "ip_address": "10.200.0.1",
        }
    )

    # Mock Certificate manager (async methods since they're awaited in the handler)
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(return_value=("key", "cert", "ca"))
    cert_manager.generate_client_certificate = AsyncMock(return_value=("key", "cert", "ca"))

    # Wire managers into app config
    app_with_sase.config["CLUSTER_MANAGER"] = cluster_manager
    app_with_sase.config["CLIENT_REGISTRY"] = client_registry
    app_with_sase.config["WIREGUARD_MANAGER"] = wg_manager
    app_with_sase.config["CERT_MANAGER"] = cert_manager

    return app_with_sase


@pytest.mark.asyncio
async def test_cluster_valid_node_and_tenant(
    app_with_sdwan: Quart, valid_tenant_token: str
) -> None:
    """Cluster with valid node_id and tenant_id should succeed.

    regression: security-review wireguard identity spoofing
    """
    client = app_with_sdwan.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "cluster-node-1",
            "node_type": "kubernetes_node",
            "api_key": "valid-cluster-key",
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["node_id"] == "cluster-node-1"
    assert "wireguard" in data
    assert "certificates" in data


@pytest.mark.asyncio
async def test_cluster_mismatched_node_id_returns_401(
    app_with_sdwan: Quart, valid_tenant_token: str
) -> None:
    """Cluster authenticates but node_id doesn't match should return 401.

    regression: security-review wireguard identity spoofing
    """
    client = app_with_sdwan.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "cluster-node-1",  # request wants this node
            "node_type": "kubernetes_node",
            "api_key": "cluster-key-wrong-node",  # but authenticates as cluster-node-2
        },
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_cluster_mismatched_tenant_returns_401(
    app_with_sdwan: Quart, valid_tenant_token: str
) -> None:
    """Cluster authenticates but tenant doesn't match should return 401.

    regression: security-review wireguard identity spoofing
    """
    client = app_with_sdwan.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "cluster-node-1",
            "node_type": "headend",
            "api_key": "cluster-key-wrong-tenant",  # authenticates with other-tenant
        },
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_client_valid_node_and_tenant(
    app_with_sdwan: Quart, valid_tenant_token: str
) -> None:
    """Client with valid node_id and tenant_id should succeed.

    regression: security-review wireguard identity spoofing
    """
    client = app_with_sdwan.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "client-node-1",
            "node_type": "client_docker",
            "api_key": "valid-client-key",
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["node_id"] == "client-node-1"
    assert "wireguard" in data


@pytest.mark.asyncio
async def test_client_mismatched_node_id_returns_401(
    app_with_sdwan: Quart, valid_tenant_token: str
) -> None:
    """Client authenticates but node_id doesn't match should return 401.

    regression: security-review wireguard identity spoofing
    """
    client = app_with_sdwan.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "client-node-1",  # request wants this node
            "node_type": "client_docker",
            "api_key": "client-key-wrong-node",  # but authenticates as client-node-2
        },
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_client_mismatched_tenant_returns_401(
    app_with_sdwan: Quart, valid_tenant_token: str
) -> None:
    """Client authenticates but tenant doesn't match should return 401.

    regression: security-review wireguard identity spoofing
    """
    client = app_with_sdwan.test_client()

    response = await client.post(
        "/api/v1/sdwan/wireguard/keys",
        headers={"Authorization": f"Bearer {valid_tenant_token}"},
        json={
            "node_id": "client-node-1",
            "node_type": "client_native",
            "api_key": "client-key-wrong-tenant",  # authenticates with other-tenant
        },
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert "error" in data
