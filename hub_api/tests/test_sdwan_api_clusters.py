"""Tests for SASE API cluster endpoints."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster


@pytest.mark.asyncio
async def test_register_cluster_without_token(app_with_sase: Quart) -> None:
    """Test cluster registration fails without bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sdwan/clusters",
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
        "hub_api.modules.sdwan.api.clusters.ClusterManager"
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
        mock_mgr.register_cluster = AsyncMock(return_value=(cluster, "test-api-key"))

        response = await client.post(
            "/api/v1/sdwan/clusters",
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
        assert "api_key" in data
        assert data["api_key"] == "test-api-key"
        assert "meta" in data
        assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_list_clusters_without_token(app_with_sase: Quart) -> None:
    """Test list clusters fails without JWT token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/sdwan/clusters")

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

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
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

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sdwan/clusters",
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

    with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
        mock_flag.return_value = False

        response = await client.get(
            "/api/v1/sdwan/clusters",
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

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr

        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_all_clusters = AsyncMock(return_value=[])

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sdwan/clusters",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            # Verify ClusterManager was initialized with the tenant from JWT
            calls = mock_manager_class.call_args_list
            assert len(calls) >= 1
            # The first positional arg to ClusterManager is db, second is tenant_id
            assert calls[0][0][1] == "test-tenant"


@pytest.mark.asyncio
async def test_cluster_heartbeat_without_token(app_with_sase: Quart) -> None:
    """Test cluster heartbeat fails without API key.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sdwan/clusters/cluster-1/heartbeat",
        json={"client_count": 5},
    )

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Unauthorized: API key required"


@pytest.mark.asyncio
async def test_cluster_heartbeat_with_token(
    app_with_sase: Quart
) -> None:
    """Test cluster heartbeat with valid per-cluster API key.

    Regression test: heartbeat must use per-cluster key, not shared bootstrap token.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "test-cluster-api-key"

    with patch(
        "hub_api.modules.sdwan.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        # Mock authenticate_cluster to return authenticated cluster
        cluster = Cluster(
            id="cluster-1",
            name="test-cluster",
            region="us-east-1",
            datacenter="dc1",
            headend_url="https://headend.example.com",
            status="active",
            last_heartbeat=datetime.now(timezone.utc),
            client_count=0,
            tenant="test-tenant",
        )
        mock_mgr.authenticate_cluster = AsyncMock(return_value=cluster)
        mock_mgr.update_heartbeat = AsyncMock(return_value=True)

        response = await client.post(
            "/api/v1/sdwan/clusters/cluster-1/heartbeat",
            json={"client_count": 5},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        # Verify authenticate_cluster was called (per-cluster auth, not bootstrap)
        mock_mgr.authenticate_cluster.assert_called_once_with(api_key)


@pytest.mark.asyncio
async def test_cluster_heartbeat_with_invalid_key(app_with_sase: Quart) -> None:
    """Regression test: cluster heartbeat with invalid key → 401.

    Regression: gh-HIGH-AUTH-FINDING-1 (heartbeat spoofing via shared bootstrap token)

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "invalid-key"

    with patch(
        "hub_api.modules.sdwan.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        # authenticate_cluster returns None for invalid key
        mock_mgr.authenticate_cluster = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/sdwan/clusters/cluster-1/heartbeat",
            json={"client_count": 5},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Authentication failed"


@pytest.mark.asyncio
async def test_cluster_heartbeat_cluster_id_mismatch(app_with_sase: Quart) -> None:
    """Regression test: heartbeat with key from cluster A to cluster B → 403.

    Regression: gh-HIGH-AUTH-FINDING-1 (heartbeat spoofing / cross-cluster access)

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "cluster-a-key"

    with patch(
        "hub_api.modules.sdwan.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        # authenticate_cluster returns cluster-a, but heartbeat is for cluster-b
        cluster_a = Cluster(
            id="cluster-a",
            name="cluster-a",
            region="us-east-1",
            datacenter="dc1",
            headend_url="https://headend.example.com",
            status="active",
            last_heartbeat=datetime.now(timezone.utc),
            client_count=0,
            tenant="test-tenant",
        )
        mock_mgr.authenticate_cluster = AsyncMock(return_value=cluster_a)

        response = await client.post(
            "/api/v1/sdwan/clusters/cluster-b/heartbeat",
            json={"client_count": 5},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 403
        data = await response.get_json()
        assert data["error"] == "Cluster ID mismatch"


@pytest.mark.asyncio
async def test_get_headend_config_with_invalid_key(app_with_sase: Quart) -> None:
    """Regression test: get_headend_config with invalid key → 401.

    Regression: gh-HIGH-AUTH-FINDING-2 (cross-tenant access via shared bootstrap token)

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "invalid-key"

    with patch(
        "hub_api.modules.sdwan.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        # authenticate_cluster returns None for invalid key
        mock_mgr.authenticate_cluster = AsyncMock(return_value=None)

        response = await client.get(
            "/api/v1/sdwan/clusters/cluster-1/headend-config",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "Authentication failed"


@pytest.mark.asyncio
async def test_get_headend_config_cluster_id_mismatch(app_with_sase: Quart) -> None:
    """Regression test: get_headend_config with mismatched cluster ID → 403.

    Regression: gh-HIGH-AUTH-FINDING-2 (cross-tenant access via shared bootstrap token)

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "tenant-a-cluster-key"

    with patch(
        "hub_api.modules.sdwan.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        # authenticate_cluster returns cluster from tenant-a, access request for tenant-b cluster
        cluster_a = Cluster(
            id="tenant-a-cluster",
            name="cluster-a",
            region="us-east-1",
            datacenter="dc1",
            headend_url="https://headend-a.example.com",
            status="active",
            last_heartbeat=datetime.now(timezone.utc),
            client_count=0,
            tenant="tenant-a",
        )
        mock_mgr.authenticate_cluster = AsyncMock(return_value=cluster_a)

        response = await client.get(
            "/api/v1/sdwan/clusters/tenant-b-cluster/headend-config",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 403
        data = await response.get_json()
        assert data["error"] == "Cluster ID mismatch"


@pytest.mark.asyncio
async def test_get_headend_config_with_valid_key(app_with_sase: Quart) -> None:
    """Test getting headend config with valid per-cluster API key.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()
    api_key = "test-cluster-key"

    with patch(
        "hub_api.modules.sdwan.api.clusters.ClusterManager"
    ) as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()

        cluster = Cluster(
            id="cluster-1",
            name="test-cluster",
            region="us-east-1",
            datacenter="dc1",
            headend_url="https://headend.example.com",
            status="active",
            last_heartbeat=datetime.now(timezone.utc),
            client_count=0,
            tenant="test-tenant",
        )
        mock_mgr.authenticate_cluster = AsyncMock(return_value=cluster)

        response = await client.get(
            "/api/v1/sdwan/clusters/cluster-1/headend-config",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["config"]["cluster_id"] == "cluster-1"
        assert "auth" in data["config"]
        assert "wireguard" in data["config"]
        # Verify authenticate_cluster was called (per-cluster auth)
        mock_mgr.authenticate_cluster.assert_called_once_with(api_key)
