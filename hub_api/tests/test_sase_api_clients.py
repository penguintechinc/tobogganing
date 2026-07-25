"""Tests for SASE API client endpoints."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.modules.sase.orchestrator.client_registry import Client
from hub_api.modules.sase.orchestrator.cluster_manager import Cluster


@pytest.mark.asyncio
async def test_register_client_without_token(app_with_sase: Quart) -> None:
    """Test client registration fails without bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sase/clients",
        json={
            "name": "test-client",
            "type": "docker",
            "public_key": "-----BEGIN PUBLIC KEY-----",
        },
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Unauthorized: enrollment token required"


@pytest.mark.asyncio
async def test_register_client_with_token(
    app_with_sase: Quart, bootstrap_token: str
) -> None:
    """Test client registration with valid bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
        bootstrap_token: Bootstrap token.
    """
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token

    client = app_with_sase.test_client()

    with patch(
        "hub_api.modules.sase.api.clients.ClusterManager"
    ) as mock_cluster_class:
        with patch(
            "hub_api.modules.sase.api.clients.ClientRegistry"
        ) as mock_client_class:
            # Mock cluster manager
            mock_cluster_mgr = AsyncMock()
            mock_cluster_class.return_value = mock_cluster_mgr
            mock_cluster_mgr.initialize = AsyncMock()

            cluster = Cluster(
                id="cluster-1",
                name="cluster-1",
                region="us-east-1",
                datacenter="dc1",
                headend_url="https://headend.example.com",
                status="active",
                last_heartbeat=datetime.now(timezone.utc),
                client_count=0,
                tenant="default",
            )
            mock_cluster_mgr.get_optimal_cluster = AsyncMock(return_value=cluster)

            # Mock client registry
            mock_client_registry = AsyncMock()
            mock_client_class.return_value = mock_client_registry
            mock_client_registry.initialize = AsyncMock()

            test_client_obj = Client(
                id="client-1",
                name="test-client",
                type="docker",
                cluster_id="cluster-1",
                api_key_hash="hash",
                public_key="-----BEGIN PUBLIC KEY-----",
                ip_address="10.0.0.1",
                status="pending",
                created_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                tenant="default",
            )
            mock_client_registry.register_client = AsyncMock(
                return_value=(test_client_obj, "test-api-key")
            )

            response = await client.post(
                "/api/v1/sase/clients",
                json={
                    "name": "test-client",
                    "type": "docker",
                    "public_key": "-----BEGIN PUBLIC KEY-----",
                },
                headers={"Authorization": f"Bearer {bootstrap_token}"},
            )

            assert response.status_code == 201
            data = await response.get_json()
            assert data["client_id"] == "client-1"
            assert "api_key" in data
            assert data["cluster"]["id"] == "cluster-1"


@pytest.mark.asyncio
async def test_get_client_config_with_api_key(app_with_sase: Quart) -> None:
    """Test getting client config with valid API key.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "test-api-key"

    with patch(
        "hub_api.modules.sase.api.clients.ClientRegistry"
    ) as mock_client_class:
        with patch(
            "hub_api.modules.sase.api.clients.ClusterManager"
        ) as mock_cluster_class:
            # Mock client registry
            mock_client_registry = AsyncMock()
            mock_client_class.return_value = mock_client_registry
            mock_client_registry.initialize = AsyncMock()

            test_client_obj = Client(
                id="client-1",
                name="test-client",
                type="docker",
                cluster_id="cluster-1",
                api_key_hash="hash",
                public_key="-----BEGIN PUBLIC KEY-----",
                ip_address="10.0.0.1",
                status="active",
                created_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                tenant="default",
                metadata={"tunnel_mode": "full"},
            )
            mock_client_registry.authenticate_client = AsyncMock(
                return_value=test_client_obj
            )

            # Mock cluster manager
            mock_cluster_mgr = AsyncMock()
            mock_cluster_class.return_value = mock_cluster_mgr
            mock_cluster_mgr.initialize = AsyncMock()

            cluster = Cluster(
                id="cluster-1",
                name="cluster-1",
                region="us-east-1",
                datacenter="dc1",
                headend_url="https://headend.example.com",
                status="active",
                last_heartbeat=datetime.now(timezone.utc),
                client_count=1,
                tenant="default",
            )
            mock_cluster_mgr.get_cluster = AsyncMock(return_value=cluster)

            response = await client.get(
                "/api/v1/sase/clients/client-1/config",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert data["client_id"] == "client-1"
            assert data["cluster"]["id"] == "cluster-1"
            assert data["status"] == "active"


@pytest.mark.asyncio
async def test_rotate_client_key(app_with_sase: Quart) -> None:
    """Test rotating client API key.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "test-api-key"

    with patch(
        "hub_api.modules.sase.api.clients.ClientRegistry"
    ) as mock_client_class:
        # Mock client registry
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()

        test_client_obj = Client(
            id="client-1",
            name="test-client",
            type="docker",
            cluster_id="cluster-1",
            api_key_hash="hash",
            public_key="-----BEGIN PUBLIC KEY-----",
            ip_address="10.0.0.1",
            status="active",
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            tenant="default",
        )
        mock_client_registry.authenticate_client = AsyncMock(return_value=test_client_obj)
        mock_client_registry.rotate_api_key = AsyncMock(return_value="new-api-key")

        response = await client.post(
            "/api/v1/sase/clients/client-1/rotate-key",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["client_id"] == "client-1"
        assert data["new_api_key"] == "new-api-key"


@pytest.mark.asyncio
async def test_list_clients_with_token(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test listing clients with valid JWT token.

    Args:
        app_with_sase: Test app with SASE module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_sase.test_client()

    with patch(
        "hub_api.modules.sase.api.clients.ClientRegistry"
    ) as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()

        test_client_obj = Client(
            id="client-1",
            name="test-client",
            type="docker",
            cluster_id="cluster-1",
            api_key_hash="hash",
            public_key="-----BEGIN PUBLIC KEY-----",
            ip_address="10.0.0.1",
            status="active",
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            tenant="test-tenant",
        )
        mock_client_registry.get_all_clients = AsyncMock(return_value=[test_client_obj])

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sase/clients",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert len(data["clients"]) == 1
            assert data["clients"][0]["id"] == "client-1"


@pytest.mark.asyncio
async def test_update_tunnel_config(app_with_sase: Quart) -> None:
    """Test updating client tunnel configuration.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "test-api-key"

    with patch(
        "hub_api.modules.sase.api.clients.ClientRegistry"
    ) as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()

        test_client_obj = Client(
            id="client-1",
            name="test-client",
            type="docker",
            cluster_id="cluster-1",
            api_key_hash="hash",
            public_key="-----BEGIN PUBLIC KEY-----",
            ip_address="10.0.0.1",
            status="active",
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            tenant="default",
            metadata={},
        )
        mock_client_registry.authenticate_client = AsyncMock(
            return_value=test_client_obj
        )
        mock_client_registry.update_client_status = AsyncMock(return_value=True)

        response = await client.put(
            "/api/v1/sase/clients/client-1/tunnel-config",
            json={
                "tunnel_mode": "split",
                "split_tunnel_routes": ["10.0.0.0/8", "example.com"],
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["tunnel_mode"] == "split"
        assert len(data["split_tunnel_routes"]) == 2


@pytest.mark.asyncio
async def test_submit_client_metrics(app_with_sase: Quart) -> None:
    """Test submitting client metrics.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "test-api-key"

    with patch(
        "hub_api.modules.sase.api.clients.ClientRegistry"
    ) as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()

        test_client_obj = Client(
            id="client-1",
            name="test-client",
            type="docker",
            cluster_id="cluster-1",
            api_key_hash="hash",
            public_key="-----BEGIN PUBLIC KEY-----",
            ip_address="10.0.0.1",
            status="active",
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            tenant="default",
        )
        mock_client_registry.authenticate_client = AsyncMock(
            return_value=test_client_obj
        )
        mock_client_registry.update_client_status = AsyncMock(return_value=True)

        response = await client.post(
            "/api/v1/sase/clients/client-1/metrics",
            json={"metrics": {"cpu": 50, "memory": 1024}},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "metrics_received"
