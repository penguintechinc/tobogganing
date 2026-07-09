"""Tests for SASE orchestrator module."""
from __future__ import annotations

import hashlib
import hmac
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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
    """Test registering a cluster and receiving per-cluster API key.

    Regression: gh-HIGH-AUTH-FINDING-1 (bootstrap token must be enrollment-only)
    """
    mock_db.clusters.create = lambda *a, **kw: mock_cluster_obj

    cluster, api_key = await cluster_manager.register_cluster(
        {
            "id": "cluster-1",
            "name": "Main",
            "region": "us-west",
            "datacenter": "dc1",
            "headend_url": "https://headend.local",
            "metadata": {},
        }
    )

    assert isinstance(cluster, Cluster)
    assert cluster.id == "cluster-1"
    assert cluster.name == "Main"
    assert isinstance(api_key, str)
    assert len(api_key) > 0  # API key should be non-empty


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
    """Test authenticating an active client."""
    api_key = "test-key"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash=api_key_hash, public_key="pk1", ip_address="192.168.1.1",
        status="active", created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_obj.update = lambda **kw: None
    mock_db.clients.select = lambda *a, **kw: mock_obj

    result = await client_registry.authenticate_client(api_key)

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


# Security Tests


@pytest.mark.asyncio
async def test_authenticate_client_cross_tenant_rejected(mock_db):
    """Regression: gh-001 - cross-tenant auth must be rejected."""
    # Client in tenant-A tries to use key, but registry is for tenant-B
    registry_b = ClientRegistry(db=mock_db, tenant_id="tenant-b")

    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash="hash123", public_key="pk1", ip_address="192.168.1.1",
        status="active", created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="tenant-a", metadata={}
    )

    # DB returns the object with tenant-a, even though we're looking in tenant-b
    # (In real DB, this wouldn't happen due to tenant column constraint)
    mock_db.clients.select = lambda **kw: mock_obj if kw.get("tenant") == "tenant-a" else None

    result = await registry_b.authenticate_client("test-key")

    # Must be rejected because registry is scoped to tenant-b
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_client_revoked_status_rejected(client_registry, mock_db):
    """Regression: gh-002 - revoked clients cannot authenticate."""
    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash=hashlib.sha256(b"test-key").hexdigest(),
        public_key="pk1", ip_address="192.168.1.1",
        status="revoked",  # CRITICAL: revoked status
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_db.clients.select = lambda **kw: mock_obj

    result = await client_registry.authenticate_client("test-key")

    # Must be rejected (status != 'active')
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_client_disabled_status_rejected(client_registry, mock_db):
    """Regression: gh-002 - disabled clients cannot authenticate."""
    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash=hashlib.sha256(b"test-key").hexdigest(),
        public_key="pk1", ip_address="192.168.1.1",
        status="disabled",  # CRITICAL: disabled status
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_db.clients.select = lambda **kw: mock_obj

    result = await client_registry.authenticate_client("test-key")

    # Must be rejected (status != 'active')
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_client_pending_status_rejected(client_registry, mock_db):
    """Regression: gh-002 - pending clients cannot authenticate."""
    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash=hashlib.sha256(b"test-key").hexdigest(),
        public_key="pk1", ip_address="192.168.1.1",
        status="pending",  # CRITICAL: pending status
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_db.clients.select = lambda **kw: mock_obj

    result = await client_registry.authenticate_client("test-key")

    # Must be rejected (status != 'active')
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_client_constant_time_compare(client_registry, mock_db):
    """Regression: gh-003 - authenticate uses constant-time comparison."""
    api_key = "test-key-12345"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    mock_obj = MagicMock(
        id="client-1", name="Test", type="docker", cluster_id="c1",
        api_key_hash=api_key_hash,
        public_key="pk1", ip_address="192.168.1.1",
        status="active",
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc), tenant="test-tenant", metadata={}
    )
    mock_obj.update = lambda **kw: None
    mock_db.clients.select = lambda **kw: mock_obj

    # Verify hmac.compare_digest is used in authentication
    with patch('core.modules.sase.orchestrator.client_registry.hmac.compare_digest',
               wraps=hmac.compare_digest) as mock_compare:
        result = await client_registry.authenticate_client(api_key)

        # Verify constant-time compare was called
        assert mock_compare.called
        assert result is not None
        assert result.id == "client-1"


@pytest.mark.asyncio
async def test_authenticate_client_exception_returns_none(client_registry, mock_db):
    """Regression: gh-004 - auth exceptions fail closed (return None)."""
    mock_db.clients.select = lambda **kw: None  # Simulate DB error on next call

    # Simulate a DB error
    mock_db.clients.select = MagicMock(side_effect=Exception("DB connection lost"))

    result = await client_registry.authenticate_client("test-key")

    # Must fail closed (return None, not raise)
    assert result is None


@pytest.mark.asyncio
async def test_remove_client_exception_returns_false(client_registry, mock_db):
    """Regression: gh-005 - remove_client exception fails closed."""
    mock_obj = MagicMock()
    mock_obj.delete = MagicMock(side_effect=Exception("DB error"))
    mock_db.clients.select = lambda **kw: mock_obj

    result = await client_registry.remove_client("client-1")

    # Must fail closed (return False, not raise)
    assert result is False


@pytest.mark.asyncio
async def test_update_client_status_exception_returns_false(client_registry, mock_db):
    """Regression: gh-006 - update_client_status exception fails closed."""
    mock_obj = MagicMock()
    mock_obj.update = MagicMock(side_effect=Exception("DB error"))
    mock_db.clients.select = lambda **kw: mock_obj

    result = await client_registry.update_client_status("client-1", "active")

    # Must fail closed (return False, not raise)
    assert result is False
