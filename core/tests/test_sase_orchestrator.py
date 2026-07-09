"""Tests for SASE orchestrator module."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.modules.sase.orchestrator.cluster_manager import ClusterManager, Cluster
from core.modules.sase.orchestrator.client_registry import ClientRegistry, Client


# Fixtures


@pytest.fixture
def mock_cluster_obj():
    """Create a mock cluster object."""
    obj = MagicMock()
    obj.id = "cluster-1"
    obj.name = "Main"
    obj.region = "us-west"
    obj.datacenter = "dc1"
    obj.headend_url = "https://headend.local"
    obj.status = "active"
    obj.last_heartbeat = datetime.now(timezone.utc)
    obj.client_count = 0
    obj.tenant = "test-tenant"
    obj.metadata = {}
    return obj


@pytest.fixture
def mock_db():
    """Create a mock DAL instance with sync methods."""
    db = MagicMock()
    db.clusters = MagicMock()
    db.clients = MagicMock()
    return db


@pytest.fixture
def cluster_manager(mock_db):
    """Create a ClusterManager instance."""
    return ClusterManager(db=mock_db, tenant_id="test-tenant")


@pytest.fixture
def client_registry(mock_db):
    """Create a ClientRegistry instance."""
    return ClientRegistry(db=mock_db, tenant_id="test-tenant")


# ClusterManager Tests


@pytest.mark.asyncio
async def test_cluster_manager_initialize(cluster_manager):
    """Test ClusterManager initialization."""
    await cluster_manager.initialize()


@pytest.mark.asyncio
async def test_cluster_manager_register_cluster(cluster_manager, mock_db, mock_cluster_obj):
    """Test registering a cluster."""
    mock_db.clusters.create = lambda *a, **kw: mock_cluster_obj

    result = await cluster_manager.register_cluster(
        {
            "id": "cluster-1",
            "name": "Main",
            "region": "us-west",
            "datacenter": "dc1",
            "headend_url": "https://headend.local",
            "metadata": {},
        }
    )

    assert isinstance(result, Cluster)
    assert result.id == "cluster-1"
    assert result.name == "Main"


@pytest.mark.asyncio
async def test_cluster_manager_get_cluster(cluster_manager, mock_db, mock_cluster_obj):
    """Test getting a cluster."""
    mock_db.clusters.select = lambda *a, **kw: mock_cluster_obj

    result = await cluster_manager.get_cluster("cluster-1")

    assert isinstance(result, Cluster)
    assert result.id == "cluster-1"


@pytest.mark.asyncio
async def test_cluster_manager_get_cluster_not_found(cluster_manager, mock_db):
    """Test getting a non-existent cluster."""
    mock_db.clusters.select = lambda *a, **kw: None

    result = await cluster_manager.get_cluster("non-existent")

    assert result is None


@pytest.mark.asyncio
async def test_cluster_manager_get_all_clusters(cluster_manager, mock_db):
    """Test getting all clusters."""
    mock_c1 = MagicMock(id="c1", name="Main", region="us-west", datacenter="dc1",
                        headend_url="h1", status="active", last_heartbeat=datetime.now(timezone.utc),
                        client_count=2, tenant="test-tenant", metadata={})
    mock_c2 = MagicMock(id="c2", name="Secondary", region="us-east", datacenter="dc2",
                        headend_url="h2", status="active", last_heartbeat=datetime.now(timezone.utc),
                        client_count=1, tenant="test-tenant", metadata={})

    mock_db.clusters.select_list = lambda *a, **kw: [mock_c1, mock_c2]

    result = await cluster_manager.get_all_clusters()

    assert len(result) == 2
    assert result[0].id == "c1"


@pytest.mark.asyncio
async def test_cluster_manager_get_cluster_count(cluster_manager, mock_db):
    """Test getting cluster count."""
    mock_clusters = [MagicMock() for _ in range(3)]
    mock_db.clusters.select_list = lambda *a, **kw: mock_clusters

    result = await cluster_manager.get_cluster_count()

    assert result == 3


@pytest.mark.asyncio
async def test_cluster_manager_update_heartbeat(cluster_manager, mock_db):
    """Test updating cluster heartbeat."""
    mock_obj = MagicMock()
    mock_obj.client_count = 3
    mock_obj.update = lambda **kw: None
    mock_db.clusters.select = lambda *a, **kw: mock_obj

    result = await cluster_manager.update_heartbeat("cluster-1", client_count=5)

    assert result is True


@pytest.mark.asyncio
async def test_cluster_manager_remove_cluster(cluster_manager, mock_db):
    """Test removing a cluster."""
    mock_obj = MagicMock()
    mock_obj.delete = lambda: None
    mock_db.clusters.select = lambda *a, **kw: mock_obj

    result = await cluster_manager.remove_cluster("cluster-1")

    assert result is True


@pytest.mark.asyncio
async def test_cluster_manager_is_healthy(cluster_manager):
    """Test health check."""
    result = await cluster_manager.is_healthy()

    assert result is True


# ClientRegistry Tests


@pytest.mark.asyncio
async def test_client_registry_initialize(client_registry):
    """Test ClientRegistry initialization."""
    await client_registry.initialize()


@pytest.mark.asyncio
async def test_client_registry_register_client(client_registry, mock_db):
    """Test registering a client."""
    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash="hash123", public_key="pk1", ip_address="192.168.1.1",
        status="pending", created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_db.clients.create = lambda *a, **kw: mock_obj

    client, api_key = await client_registry.register_client(
        {
            "id": "client-1",
            "name": "Test",
            "type": "docker",
            "cluster_id": "c1",
            "public_key": "pk1",
            "ip_address": "192.168.1.1",
            "metadata": {},
        }
    )

    assert isinstance(client, Client)
    assert client.id == "client-1"
    assert len(api_key) > 30


@pytest.mark.asyncio
async def test_client_registry_authenticate_client(client_registry, mock_db):
    """Test authenticating a client."""
    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash="hash123", public_key="pk1", ip_address="192.168.1.1",
        status="pending", created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_obj.update = lambda **kw: None
    mock_db.clients.select = lambda *a, **kw: mock_obj

    result = await client_registry.authenticate_client("test-key")

    assert isinstance(result, Client)
    assert result.id == "client-1"


@pytest.mark.asyncio
async def test_client_registry_get_client(client_registry, mock_db):
    """Test getting a client."""
    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash="hash123", public_key="pk1", ip_address="192.168.1.1",
        status="active", created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_db.clients.select = lambda *a, **kw: mock_obj

    result = await client_registry.get_client("client-1")

    assert isinstance(result, Client)
    assert result.id == "client-1"


@pytest.mark.asyncio
async def test_client_registry_get_all_clients(client_registry, mock_db):
    """Test getting all clients."""
    mock_c1 = MagicMock(id="c1", name="C1", type="docker", cluster_id="cl1",
                        api_key_hash="h1", public_key="pk1", ip_address="192.168.1.1",
                        status="active", created_at=datetime.now(timezone.utc),
                        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={})
    mock_c2 = MagicMock(id="c2", name="C2", type="native", cluster_id="cl2",
                        api_key_hash="h2", public_key="pk2", ip_address="192.168.1.2",
                        status="active", created_at=datetime.now(timezone.utc),
                        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={})

    mock_db.clients.select_list = lambda *a, **kw: [mock_c1, mock_c2]

    result = await client_registry.get_all_clients()

    assert len(result) == 2


@pytest.mark.asyncio
async def test_client_registry_rotate_api_key(client_registry, mock_db):
    """Test rotating client API key."""
    mock_obj = MagicMock()
    mock_obj.update = lambda **kw: None
    mock_db.clients.select = lambda *a, **kw: mock_obj

    result = await client_registry.rotate_api_key("client-1")

    assert result is not None
    assert len(result) > 30


@pytest.mark.asyncio
async def test_client_registry_get_client_count(client_registry, mock_db):
    """Test getting client count."""
    mock_clients = [MagicMock() for _ in range(2)]
    mock_db.clients.select_list = lambda *a, **kw: mock_clients

    result = await client_registry.get_client_count()

    assert result == 2
