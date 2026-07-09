"""Tests for SASE API orchestration endpoints."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from core.auth.jwt import encode_access_token
from core.crypto import InAppKeyProvider, generate_rsa_key_pair
from core.modules.sase.orchestrator.client_registry import Client
from core.modules.sase.orchestrator.cluster_manager import Cluster
from core.registry import ModuleContext


@pytest.fixture
def app_with_sase(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with SASE module registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with SASE module and auth configured.
    """
    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Register SASE module via registry (combines module prefix + blueprint prefix)
    from core.modules.sase import module as sase_module

    sase_contract = sase_module()
    app.registry.register(sase_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest.fixture
def valid_tenant_token(app_with_sase: Quart) -> str:
    """Generate a valid tenant JWT token.

    Args:
        app_with_sase: App with key provider.

    Returns:
        Encoded JWT token with tenant claim.
    """
    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "clusters:read clients:read",
    }

    token = encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.fixture
def valid_write_token(app_with_sase: Quart) -> str:
    """Generate a valid JWT token with write scopes.

    Args:
        app_with_sase: App with key provider.

    Returns:
        Encoded JWT token with write scopes.
    """
    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }

    token = encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest.fixture
def bootstrap_token() -> str:
    """Get bootstrap/enrollment token.

    Returns:
        Bootstrap token matching env var.
    """
    return os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "test-bootstrap-token")


# Cluster API Tests


@pytest.mark.asyncio
async def test_register_cluster_without_token(app_with_sase: Quart) -> None:
    """Test cluster registration fails without bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sase/clusters",
        json={
            "name": "test-cluster",
            "region": "us-east-1",
            "datacenter": "dc1",
            "headend_url": "https://headend.example.com",
        },
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Unauthorized: enrollment token required"


@pytest.mark.asyncio
async def test_register_cluster_with_token(
    app_with_sase: Quart, bootstrap_token: str
) -> None:
    """Test cluster registration with valid bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
        bootstrap_token: Bootstrap token.
    """
    # Set the bootstrap token in environment
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token

    client = app_with_sase.test_client()
    mock_db = app_with_sase.db

    # Mock the cluster manager
    with patch(
        "core.modules.sase.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        # Mock initialize
        mock_mgr.initialize = AsyncMock()

        # Mock get_cluster_count
        mock_mgr.get_cluster_count = AsyncMock(return_value=0)

        # Mock register_cluster
        cluster = Cluster(
            id="test-cluster-id",
            name="test-cluster",
            region="us-east-1",
            datacenter="dc1",
            headend_url="https://headend.example.com",
            status="active",
            last_heartbeat=datetime.now(timezone.utc),
            client_count=0,
            tenant="default",
        )
        mock_mgr.register_cluster = AsyncMock(return_value=cluster)

        response = await client.post(
            "/api/v1/sase/clusters",
            json={
                "name": "test-cluster",
                "region": "us-east-1",
                "datacenter": "dc1",
                "headend_url": "https://headend.example.com",
            },
            headers={"Authorization": f"Bearer {bootstrap_token}"},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["cluster_id"] == "test-cluster-id"
        assert data["status"] == "registered"
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_list_clusters_without_token(app_with_sase: Quart) -> None:
    """Test list clusters fails without JWT token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/sase/clusters")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_clusters_with_token(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test list clusters with valid JWT token and enabled flag.

    Args:
        app_with_sase: Test app with SASE module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_sase.test_client()

    with patch("core.modules.sase.api.clusters.ClusterManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        mock_mgr.initialize = AsyncMock()
        cluster = Cluster(
            id="cluster-1",
            name="cluster-1",
            region="us-east-1",
            datacenter="dc1",
            headend_url="https://headend.example.com",
            status="active",
            last_heartbeat=datetime.now(timezone.utc),
            client_count=5,
            tenant="test-tenant",
        )
        mock_mgr.get_all_clusters = AsyncMock(return_value=[cluster])

        with patch("core.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sase/clusters",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert len(data["clusters"]) == 1
            assert data["clusters"][0]["id"] == "cluster-1"
            assert "meta" in data


@pytest.mark.asyncio
async def test_list_clusters_flag_disabled(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test list clusters returns 402 when flag disabled.

    Args:
        app_with_sase: Test app with SASE module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_sase.test_client()

    with patch("core.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        response = await client.get(
            "/api/v1/sase/clusters",
            headers={"Authorization": f"Bearer {valid_tenant_token}"},
        )

        assert response.status_code == 402
        data = await response.get_json()
        assert data["error"] == "Feature not available"


@pytest.mark.asyncio
async def test_list_clusters_tenant_isolation(
    app_with_sase: Quart, valid_tenant_token: str
) -> None:
    """Test that list_clusters respects tenant claim from JWT.

    Args:
        app_with_sase: Test app with SASE module.
        valid_tenant_token: Valid JWT token.
    """
    client = app_with_sase.test_client()

    with patch("core.modules.sase.api.clusters.ClusterManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_all_clusters = AsyncMock(return_value=[])

        with patch("core.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sase/clusters",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            # Verify ClusterManager was initialized with the tenant from JWT
            calls = mock_manager_class.call_args_list
            assert len(calls) >= 1
            # The first positional arg to ClusterManager is db, second is tenant_id
            assert calls[0][0][1] == "test-tenant"


# Client API Tests


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
        "core.modules.sase.api.clients.ClusterManager"
    ) as mock_cluster_class:
        with patch(
            "core.modules.sase.api.clients.ClientRegistry"
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
        "core.modules.sase.api.clients.ClientRegistry"
    ) as mock_client_class:
        with patch(
            "core.modules.sase.api.clients.ClusterManager"
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
        "core.modules.sase.api.clients.ClientRegistry"
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
        "core.modules.sase.api.clients.ClientRegistry"
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

        with patch("core.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sase/clients",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 200
            data = await response.get_json()
            assert len(data["clients"]) == 1
            assert data["clients"][0]["id"] == "client-1"


# Status API Tests


@pytest.mark.asyncio
async def test_cluster_heartbeat_without_token(app_with_sase: Quart) -> None:
    """Test cluster heartbeat fails without bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sase/clusters/cluster-1/heartbeat",
        json={"client_count": 5},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Unauthorized: enrollment token required"


@pytest.mark.asyncio
async def test_cluster_heartbeat_with_token(
    app_with_sase: Quart, bootstrap_token: str
) -> None:
    """Test cluster heartbeat with valid bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
        bootstrap_token: Bootstrap token.
    """
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token

    client = app_with_sase.test_client()

    with patch(
        "core.modules.sase.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.update_heartbeat = AsyncMock(return_value=True)

        response = await client.post(
            "/api/v1/sase/clusters/cluster-1/heartbeat",
            json={"client_count": 5},
            headers={"Authorization": f"Bearer {bootstrap_token}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_update_tunnel_config(app_with_sase: Quart) -> None:
    """Test updating client tunnel configuration.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "test-api-key"

    with patch(
        "core.modules.sase.api.clients.ClientRegistry"
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
        "core.modules.sase.api.clients.ClientRegistry"
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


@pytest.mark.asyncio
async def test_get_status(app_with_sase: Quart) -> None:
    """Test getting service status.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    with patch(
        "core.modules.sase.api.status.ClusterManager"
    ) as mock_cluster_class:
        with patch(
            "core.modules.sase.api.status.ClientRegistry"
        ) as mock_client_class:
            # Mock cluster manager
            mock_cluster_mgr = AsyncMock()
            mock_cluster_class.return_value = mock_cluster_mgr
            mock_cluster_mgr.initialize = AsyncMock()
            mock_cluster_mgr.get_cluster_count = AsyncMock(return_value=2)

            cluster1 = Cluster(
                id="cluster-1",
                name="cluster-1",
                region="us-east-1",
                datacenter="dc1",
                headend_url="https://headend.example.com",
                status="active",
                last_heartbeat=datetime.now(timezone.utc),
                client_count=5,
                tenant="default",
            )
            cluster2 = Cluster(
                id="cluster-2",
                name="cluster-2",
                region="us-west-1",
                datacenter="dc2",
                headend_url="https://headend2.example.com",
                status="stale",
                last_heartbeat=datetime.now(timezone.utc),
                client_count=3,
                tenant="default",
            )
            mock_cluster_mgr.get_all_clusters = AsyncMock(
                return_value=[cluster1, cluster2]
            )

            # Mock client registry
            mock_client_registry = AsyncMock()
            mock_client_class.return_value = mock_client_registry
            mock_client_registry.initialize = AsyncMock()
            mock_client_registry.get_client_count = AsyncMock(return_value=8)

            test_client1 = Client(
                id="client-1",
                name="test-client-1",
                type="docker",
                cluster_id="cluster-1",
                api_key_hash="hash1",
                public_key="-----BEGIN PUBLIC KEY-----",
                ip_address="10.0.0.1",
                status="active",
                created_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                tenant="default",
            )
            test_client2 = Client(
                id="client-2",
                name="test-client-2",
                type="native",
                cluster_id="cluster-1",
                api_key_hash="hash2",
                public_key="-----BEGIN PUBLIC KEY-----",
                ip_address="10.0.0.2",
                status="pending",
                created_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                tenant="default",
            )
            mock_client_registry.get_all_clients = AsyncMock(
                return_value=[test_client1, test_client2]
            )

            response = await client.get("/api/v1/sase/status")

            assert response.status_code == 200
            data = await response.get_json()
            assert data["service"] == "SASE Orchestrator API"
            assert data["status"] == "healthy"
            assert data["clusters"]["total"] == 2
            assert data["clusters"]["active"] == 1
            assert data["clients"]["total"] == 8
            assert data["clients"]["active"] == 1
            assert "meta" in data
