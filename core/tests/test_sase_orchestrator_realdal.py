"""Integration tests for SASE orchestrator managers using real_dal."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from core.modules.sase.orchestrator.cluster_manager import Cluster, ClusterManager
from core.modules.sase.orchestrator.client_registry import Client, ClientRegistry


@pytest.mark.asyncio
async def test_cluster_manager_register_and_get(real_dal) -> None:
    """Test cluster registration and retrieval with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    cluster_data = {
        "id": str(uuid4()),
        "name": "test-cluster",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
        "metadata": {"key": "value"},
    }

    # Register cluster
    cluster, api_key = await mgr.register_cluster(cluster_data)
    assert cluster.id == cluster_data["id"]
    assert cluster.name == cluster_data["name"]
    assert cluster.region == cluster_data["region"]
    assert cluster.status == "active"
    assert cluster.tenant == tenant
    assert api_key is not None
    assert len(api_key) > 0

    # Retrieve cluster
    retrieved = await mgr.get_cluster(cluster.id)
    assert retrieved is not None
    assert retrieved.id == cluster.id
    assert retrieved.name == cluster.name


@pytest.mark.asyncio
async def test_cluster_manager_tenant_isolation(real_dal) -> None:
    """Test that cluster queries are tenant-isolated with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant1 = "test-tenant-1"
    tenant2 = "test-tenant-2"
    cluster_id = str(uuid4())

    # Register cluster in tenant 1
    mgr1 = ClusterManager(real_dal, tenant1)
    cluster_data = {
        "id": cluster_id,
        "name": "cluster-t1",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
    }
    await mgr1.register_cluster(cluster_data)

    # Verify tenant 1 can see it
    result1 = await mgr1.get_cluster(cluster_id)
    assert result1 is not None
    assert result1.id == cluster_id

    # Verify tenant 2 cannot see it
    mgr2 = ClusterManager(real_dal, tenant2)
    result2 = await mgr2.get_cluster(cluster_id)
    assert result2 is None


@pytest.mark.asyncio
async def test_cluster_manager_authenticate(real_dal) -> None:
    """Test cluster authentication via API key with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    cluster_data = {
        "id": str(uuid4()),
        "name": "test-cluster",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
    }

    # Register and get API key
    cluster, api_key = await mgr.register_cluster(cluster_data)

    # Authenticate with correct key
    authenticated = await mgr.authenticate_cluster(api_key)
    assert authenticated is not None
    assert authenticated.id == cluster.id

    # Authenticate with invalid key
    invalid_auth = await mgr.authenticate_cluster("invalid-key")
    assert invalid_auth is None


@pytest.mark.asyncio
async def test_cluster_manager_update_heartbeat(real_dal) -> None:
    """Test cluster heartbeat update with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    cluster_data = {
        "id": str(uuid4()),
        "name": "test-cluster",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
    }

    cluster, _ = await mgr.register_cluster(cluster_data)

    # Update heartbeat
    success = await mgr.update_heartbeat(cluster.id, client_count=10)
    assert success is True

    # Verify update
    updated = await mgr.get_cluster(cluster.id)
    assert updated is not None
    assert updated.client_count == 10

    # Non-existent cluster
    success = await mgr.update_heartbeat("nonexistent", client_count=5)
    assert success is False


@pytest.mark.asyncio
async def test_cluster_manager_get_all_clusters(real_dal) -> None:
    """Test listing all clusters with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    # Create multiple clusters
    cluster_ids = []
    for i in range(3):
        cluster_data = {
            "id": str(uuid4()),
            "name": f"cluster-{i}",
            "region": "us-east-1",
            "datacenter": "dc1",
            "headend_url": f"https://headend-{i}.example.com",
        }
        cluster, _ = await mgr.register_cluster(cluster_data)
        cluster_ids.append(cluster.id)

    # List all clusters
    clusters = await mgr.get_all_clusters()
    assert len(clusters) >= 3
    retrieved_ids = {c.id for c in clusters}
    for cid in cluster_ids:
        assert cid in retrieved_ids


@pytest.mark.asyncio
async def test_cluster_manager_get_by_region(real_dal) -> None:
    """Test filtering clusters by region with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    # Create clusters in different regions
    cluster_data_east = {
        "id": str(uuid4()),
        "name": "cluster-east",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend-east.example.com",
    }
    cluster_data_west = {
        "id": str(uuid4()),
        "name": "cluster-west",
        "region": "us-west-2",
        "datacenter": "dc2",
        "headend_url": "https://headend-west.example.com",
    }

    east_cluster, _ = await mgr.register_cluster(cluster_data_east)
    west_cluster, _ = await mgr.register_cluster(cluster_data_west)

    # Filter by region
    east_clusters = await mgr.get_clusters_by_region("us-east-1")
    east_ids = {c.id for c in east_clusters}
    assert east_cluster.id in east_ids
    assert west_cluster.id not in east_ids


@pytest.mark.asyncio
async def test_cluster_manager_remove(real_dal) -> None:
    """Test cluster removal with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    cluster_data = {
        "id": str(uuid4()),
        "name": "test-cluster",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
    }

    cluster, _ = await mgr.register_cluster(cluster_data)

    # Remove cluster
    success = await mgr.remove_cluster(cluster.id)
    assert success is True

    # Verify removal
    retrieved = await mgr.get_cluster(cluster.id)
    assert retrieved is None

    # Try to remove non-existent
    success = await mgr.remove_cluster("nonexistent")
    assert success is False


@pytest.mark.asyncio
async def test_client_registry_register_and_get(real_dal) -> None:
    """Test client registration and retrieval with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    registry = ClientRegistry(real_dal, tenant)

    client_data = {
        "id": str(uuid4()),
        "name": "test-client",
        "type": "docker",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.1",
        "metadata": {"region": "us-east"},
    }

    # Register client
    client, api_key = await registry.register_client(client_data)
    assert client.id == client_data["id"]
    assert client.name == client_data["name"]
    assert client.type == client_data["type"]
    assert client.status == "pending"
    assert client.tenant == tenant
    assert api_key is not None

    # Retrieve client
    retrieved = await registry.get_client(client.id)
    assert retrieved is not None
    assert retrieved.id == client.id
    assert retrieved.name == client.name


@pytest.mark.asyncio
async def test_client_registry_tenant_isolation(real_dal) -> None:
    """Test that client queries are tenant-isolated with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant1 = "test-tenant-1"
    tenant2 = "test-tenant-2"
    client_id = str(uuid4())

    # Register client in tenant 1
    registry1 = ClientRegistry(real_dal, tenant1)
    client_data = {
        "id": client_id,
        "name": "client-t1",
        "type": "docker",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.1",
    }
    await registry1.register_client(client_data)

    # Verify tenant 1 can see it
    result1 = await registry1.get_client(client_id)
    assert result1 is not None
    assert result1.id == client_id

    # Verify tenant 2 cannot see it
    registry2 = ClientRegistry(real_dal, tenant2)
    result2 = await registry2.get_client(client_id)
    assert result2 is None


@pytest.mark.asyncio
async def test_client_registry_authenticate(real_dal) -> None:
    """Test client authentication via API key with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    registry = ClientRegistry(real_dal, tenant)

    client_data = {
        "id": str(uuid4()),
        "name": "test-client",
        "type": "docker",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.1",
    }

    # Register and get API key
    client, api_key = await registry.register_client(client_data)

    # Status is pending, so auth should fail
    authenticated = await registry.authenticate_client(api_key)
    assert authenticated is None

    # Activate client
    await registry.update_client_status(client.id, "active")

    # Now auth should succeed
    authenticated = await registry.authenticate_client(api_key)
    assert authenticated is not None
    assert authenticated.id == client.id

    # Auth with invalid key should fail
    invalid_auth = await registry.authenticate_client("invalid-key")
    assert invalid_auth is None


@pytest.mark.asyncio
async def test_client_registry_update_status(real_dal) -> None:
    """Test client status update with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    registry = ClientRegistry(real_dal, tenant)

    client_data = {
        "id": str(uuid4()),
        "name": "test-client",
        "type": "docker",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.1",
    }

    client, _ = await registry.register_client(client_data)
    assert client.status == "pending"

    # Update status
    success = await registry.update_client_status(client.id, "active")
    assert success is True

    # Verify status changed
    updated = await registry.get_client(client.id)
    assert updated is not None
    assert updated.status == "active"

    # Non-existent client
    success = await registry.update_client_status("nonexistent", "active")
    assert success is False


@pytest.mark.asyncio
async def test_client_registry_get_by_cluster(real_dal) -> None:
    """Test filtering clients by cluster with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    registry = ClientRegistry(real_dal, tenant)

    # Register clients in different clusters
    client_data_c1 = {
        "id": str(uuid4()),
        "name": "client-c1",
        "type": "docker",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.1",
    }
    client_data_c2 = {
        "id": str(uuid4()),
        "name": "client-c2",
        "type": "docker",
        "cluster_id": "cluster-2",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.2",
    }

    c1, _ = await registry.register_client(client_data_c1)
    c2, _ = await registry.register_client(client_data_c2)

    # Filter by cluster
    c1_clients = await registry.get_clients_by_cluster("cluster-1")
    c1_ids = {c.id for c in c1_clients}
    assert c1.id in c1_ids
    assert c2.id not in c1_ids


@pytest.mark.asyncio
async def test_client_registry_get_by_type(real_dal) -> None:
    """Test filtering clients by type with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    registry = ClientRegistry(real_dal, tenant)

    # Register clients of different types
    client_data_docker = {
        "id": str(uuid4()),
        "name": "client-docker",
        "type": "docker",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.1",
    }
    client_data_native = {
        "id": str(uuid4()),
        "name": "client-native",
        "type": "native",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.2",
    }

    docker, _ = await registry.register_client(client_data_docker)
    native, _ = await registry.register_client(client_data_native)

    # Filter by type
    docker_clients = await registry.get_clients_by_type("docker")
    docker_ids = {c.id for c in docker_clients}
    assert docker.id in docker_ids
    assert native.id not in docker_ids


@pytest.mark.asyncio
async def test_client_registry_rotate_api_key(real_dal) -> None:
    """Test API key rotation with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    registry = ClientRegistry(real_dal, tenant)

    client_data = {
        "id": str(uuid4()),
        "name": "test-client",
        "type": "docker",
        "cluster_id": "cluster-1",
        "public_key": "ssh-rsa AAAAB3...",
        "ip_address": "192.168.1.1",
    }

    client, old_api_key = await registry.register_client(client_data)

    # Activate client first
    await registry.update_client_status(client.id, "active")

    # Rotate API key
    new_api_key = await registry.rotate_api_key(client.id)
    assert new_api_key is not None
    assert new_api_key != old_api_key

    # Old key should not work
    old_auth = await registry.authenticate_client(old_api_key)
    assert old_auth is None

    # New key should work
    new_auth = await registry.authenticate_client(new_api_key)
    assert new_auth is not None
    assert new_auth.id == client.id

    # Non-existent client
    result = await registry.rotate_api_key("nonexistent")
    assert result is None
