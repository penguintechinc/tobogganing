"""Integration tests for cluster API key rotation."""
from __future__ import annotations

from uuid import uuid4

import pytest

from hub_api.modules.sdwan.orchestrator.cluster_manager import ClusterManager


@pytest.mark.asyncio
async def test_rotate_api_key_success(real_dal) -> None:
    """Test successful API key rotation with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    # Register cluster
    cluster_data = {
        "id": str(uuid4()),
        "name": "test-cluster",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
    }
    cluster, old_api_key = await mgr.register_cluster(cluster_data)

    # Rotate the key
    new_api_key = await mgr.rotate_api_key(cluster.id)

    # Verify new key is returned and differs from old
    assert new_api_key is not None
    assert new_api_key != old_api_key
    assert len(new_api_key) > 0


@pytest.mark.asyncio
async def test_rotate_api_key_invalidates_old(real_dal) -> None:
    """Test that old API key is invalidated after rotation with real DAL.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    # Register cluster
    cluster_data = {
        "id": str(uuid4()),
        "name": "test-cluster",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
    }
    cluster, old_api_key = await mgr.register_cluster(cluster_data)

    # Verify old key works
    authenticated = await mgr.authenticate_cluster(old_api_key)
    assert authenticated is not None
    assert authenticated.id == cluster.id

    # Rotate the key
    new_api_key = await mgr.rotate_api_key(cluster.id)
    assert new_api_key is not None

    # Verify old key no longer works
    old_auth = await mgr.authenticate_cluster(old_api_key)
    assert old_auth is None

    # Verify new key works
    new_auth = await mgr.authenticate_cluster(new_api_key)
    assert new_auth is not None
    assert new_auth.id == cluster.id


@pytest.mark.asyncio
async def test_rotate_api_key_nonexistent_cluster(real_dal) -> None:
    """Test rotation of nonexistent cluster returns None.

    Args:
        real_dal: Real AsyncDB fixture.
    """
    tenant = "test-tenant-1"
    mgr = ClusterManager(real_dal, tenant)

    # Attempt to rotate key for nonexistent cluster
    result = await mgr.rotate_api_key("nonexistent-cluster")
    assert result is None


@pytest.mark.asyncio
async def test_rotate_api_key_tenant_isolation(real_dal) -> None:
    """Test that key rotation respects tenant isolation.

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
    cluster, api_key = await mgr1.register_cluster(cluster_data)

    # Attempt to rotate from tenant 2 (should fail)
    mgr2 = ClusterManager(real_dal, tenant2)
    result = await mgr2.rotate_api_key(cluster_id)
    assert result is None

    # Verify old key still works (tenant 1 only)
    auth = await mgr1.authenticate_cluster(api_key)
    assert auth is not None
    assert auth.id == cluster_id
