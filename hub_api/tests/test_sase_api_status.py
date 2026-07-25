"""Tests for SASE API status endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from quart import Quart

from hub_api.modules.sase.orchestrator.client_registry import Client
from hub_api.modules.sase.orchestrator.cluster_manager import Cluster


@pytest.mark.asyncio
async def test_get_status(app_with_sase: Quart) -> None:
    """Test getting service status.

    Args:
        app_with_sase: Test app with SASE module.
    """
    client = app_with_sase.test_client()

    with patch(
        "hub_api.modules.sase.api.status.ClusterManager"
    ) as mock_cluster_class:
        with patch(
            "hub_api.modules.sase.api.status.ClientRegistry"
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
