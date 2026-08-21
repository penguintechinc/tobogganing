"""Additional coverage for ClusterManager and ClientRegistry.

Covers initialize/shutdown, rotate_api_key, count/health checks,
get_optimal_cluster branches, background monitor loops, and fail-closed
exception paths not exercised by tests/test_sdwan_orchestrator_realdal.py.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hub_api.modules.sdwan.orchestrator import client_registry as client_registry_module
from hub_api.modules.sdwan.orchestrator import cluster_manager as cluster_manager_module
from hub_api.modules.sdwan.orchestrator.client_registry import ClientRegistry
from hub_api.modules.sdwan.orchestrator.cluster_manager import ClusterManager

# --- ClusterManager: initialize/shutdown ------------------------------------


@pytest.mark.asyncio
async def test_cluster_manager_initialize_success(real_dal) -> None:
    """initialize() logs and returns without error."""
    mgr = ClusterManager(real_dal, "tenant-init")
    await mgr.initialize()  # should not raise


@pytest.mark.asyncio
async def test_cluster_manager_initialize_error_reraises(
    real_dal, monkeypatch: pytest.MonkeyPatch
) -> None:
    """initialize() re-raises after logging when logger.info fails."""
    mgr = ClusterManager(real_dal, "tenant-init-err")
    monkeypatch.setattr(
        cluster_manager_module.logger, "info", MagicMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError, match="boom"):
        await mgr.initialize()


@pytest.mark.asyncio
async def test_cluster_manager_shutdown(real_dal) -> None:
    """shutdown() completes without raising."""
    mgr = ClusterManager(real_dal, "tenant-shutdown")
    await mgr.shutdown()


# --- ClusterManager: authenticate_cluster fail-closed / hash mismatch -------


@pytest.mark.asyncio
async def test_cluster_manager_authenticate_none_api_key_fails_closed(real_dal) -> None:
    """A non-string api_key raises inside the try block and is fail-closed to None."""
    mgr = ClusterManager(real_dal, "tenant-auth-err")

    result = await mgr.authenticate_cluster(None)  # type: ignore[arg-type]

    assert result is None


@pytest.mark.asyncio
async def test_cluster_manager_authenticate_hash_mismatch() -> None:
    """Stored hash mismatch (defense-in-depth check) returns None."""
    db = MagicMock()
    row = MagicMock()
    row.id = "cluster-1"
    row.tenant = "tenant-a"
    row.api_key_hash = "different-hash-than-queried"

    rowset = MagicMock()
    rowset.first.return_value = row

    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=rowset)
    query_proxy.update = AsyncMock(return_value=None)
    query_proxy.__and__ = MagicMock(return_value=query_proxy)

    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy
    db.clusters = MagicMock()

    mgr = ClusterManager(db, "tenant-a")
    result = await mgr.authenticate_cluster("some-api-key")

    assert result is None


# --- ClusterManager: rotate_api_key ------------------------------------------


@pytest.mark.asyncio
async def test_cluster_manager_rotate_api_key(real_dal) -> None:
    """rotate_api_key issues a new key that authenticates; old key stops working."""
    tenant = "tenant-rotate"
    mgr = ClusterManager(real_dal, tenant)

    cluster_data = {
        "id": str(uuid4()),
        "name": "rotate-cluster",
        "region": "us-east-1",
        "datacenter": "dc1",
        "headend_url": "https://headend.example.com",
    }
    cluster, old_key = await mgr.register_cluster(cluster_data)

    new_key = await mgr.rotate_api_key(cluster.id)
    assert new_key is not None
    assert new_key != old_key

    old_auth = await mgr.authenticate_cluster(old_key)
    assert old_auth is None

    new_auth = await mgr.authenticate_cluster(new_key)
    assert new_auth is not None
    assert new_auth.id == cluster.id


@pytest.mark.asyncio
async def test_cluster_manager_rotate_api_key_not_found(real_dal) -> None:
    """rotate_api_key for an unknown cluster returns None."""
    mgr = ClusterManager(real_dal, "tenant-rotate-2")

    result = await mgr.rotate_api_key("nonexistent-cluster")

    assert result is None


# --- ClusterManager: get_clusters_by_datacenter ------------------------------


@pytest.mark.asyncio
async def test_cluster_manager_get_by_datacenter(real_dal) -> None:
    """get_clusters_by_datacenter filters correctly."""
    tenant = "tenant-dc"
    mgr = ClusterManager(real_dal, tenant)

    await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "dc1-cluster",
            "region": "us-east-1",
            "datacenter": "dc-alpha",
            "headend_url": "https://headend-a.example.com",
        }
    )
    dc2_cluster, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "dc2-cluster",
            "region": "us-east-1",
            "datacenter": "dc-beta",
            "headend_url": "https://headend-b.example.com",
        }
    )

    dc_beta_clusters = await mgr.get_clusters_by_datacenter("dc-beta")
    ids = {c.id for c in dc_beta_clusters}
    assert dc2_cluster.id in ids


# --- ClusterManager: count / health ------------------------------------------


@pytest.mark.asyncio
async def test_cluster_manager_get_cluster_count(real_dal) -> None:
    """get_cluster_count reflects registered clusters for the tenant."""
    tenant = "tenant-count"
    mgr = ClusterManager(real_dal, tenant)

    await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "count-cluster",
            "region": "us-east-1",
            "datacenter": "dc1",
            "headend_url": "https://headend.example.com",
        }
    )

    count = await mgr.get_cluster_count()
    assert count >= 1


@pytest.mark.asyncio
async def test_cluster_manager_is_healthy_true(real_dal) -> None:
    """is_healthy returns True when get_cluster_count succeeds."""
    mgr = ClusterManager(real_dal, "tenant-health")
    assert await mgr.is_healthy() is True


@pytest.mark.asyncio
async def test_cluster_manager_is_healthy_false_on_error() -> None:
    """is_healthy returns False when the underlying query raises."""
    db = MagicMock()
    query_proxy = MagicMock()
    query_proxy.count = AsyncMock(side_effect=RuntimeError("db down"))
    query_proxy.__and__ = MagicMock(return_value=query_proxy)
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    mgr = ClusterManager(db, "tenant-unhealthy")
    assert await mgr.is_healthy() is False


# --- ClusterManager: get_optimal_cluster -------------------------------------


@pytest.mark.asyncio
async def test_cluster_manager_get_optimal_cluster_by_datacenter(real_dal) -> None:
    """get_optimal_cluster prefers datacenter match."""
    tenant = "tenant-optimal-dc"
    mgr = ClusterManager(real_dal, tenant)

    target, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "target",
            "region": "us-east-1",
            "datacenter": "dc-target",
            "headend_url": "https://headend.example.com",
        }
    )

    optimal = await mgr.get_optimal_cluster({"datacenter": "dc-target"})
    assert optimal is not None
    assert optimal.id == target.id


@pytest.mark.asyncio
async def test_cluster_manager_get_optimal_cluster_by_region_fallback(real_dal) -> None:
    """get_optimal_cluster falls back to region when datacenter has no match."""
    tenant = "tenant-optimal-region"
    mgr = ClusterManager(real_dal, tenant)

    target, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "region-target",
            "region": "region-target",
            "datacenter": "dc-other",
            "headend_url": "https://headend.example.com",
        }
    )

    optimal = await mgr.get_optimal_cluster(
        {"datacenter": "dc-does-not-exist", "region": "region-target"}
    )
    assert optimal is not None
    assert optimal.id == target.id


@pytest.mark.asyncio
async def test_cluster_manager_get_optimal_cluster_all_fallback(real_dal) -> None:
    """get_optimal_cluster falls back to all clusters when no location given."""
    tenant = "tenant-optimal-all"
    mgr = ClusterManager(real_dal, tenant)

    target, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "any-cluster",
            "region": "any-region",
            "datacenter": "any-dc",
            "headend_url": "https://headend.example.com",
        }
    )

    optimal = await mgr.get_optimal_cluster({})
    assert optimal is not None
    assert optimal.id == target.id


@pytest.mark.asyncio
async def test_cluster_manager_get_optimal_cluster_no_active_returns_none(
    real_dal,
) -> None:
    """get_optimal_cluster returns None when candidates exist but none are active."""
    tenant = "tenant-optimal-none"
    mgr = ClusterManager(real_dal, tenant)

    cluster, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "inactive-cluster",
            "region": "us-east-1",
            "datacenter": "dc1",
            "headend_url": "https://headend.example.com",
        }
    )
    await real_dal(real_dal.clusters.id == cluster.id).update(status="stale")

    optimal = await mgr.get_optimal_cluster({})
    assert optimal is None


@pytest.mark.asyncio
async def test_cluster_manager_get_optimal_cluster_picks_least_loaded(
    real_dal,
) -> None:
    """get_optimal_cluster picks the active candidate with the lowest client_count."""
    tenant = "tenant-optimal-load"
    mgr = ClusterManager(real_dal, tenant)

    busy, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "busy",
            "region": "region-load",
            "datacenter": "dc-busy",
            "headend_url": "https://headend-busy.example.com",
        }
    )
    quiet, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "quiet",
            "region": "region-load",
            "datacenter": "dc-quiet",
            "headend_url": "https://headend-quiet.example.com",
        }
    )
    await mgr.update_heartbeat(busy.id, client_count=50)
    await mgr.update_heartbeat(quiet.id, client_count=1)

    optimal = await mgr.get_optimal_cluster({"region": "region-load"})
    assert optimal is not None
    assert optimal.id == quiet.id


# --- ClusterManager: monitor_health / _check_cluster_health ------------------


@pytest.mark.asyncio
async def test_check_cluster_health_marks_stale(real_dal) -> None:
    """_check_cluster_health marks clusters with an old heartbeat as stale."""
    tenant = "tenant-stale"
    mgr = ClusterManager(real_dal, tenant)

    cluster, _ = await mgr.register_cluster(
        {
            "id": str(uuid4()),
            "name": "stale-candidate",
            "region": "us-east-1",
            "datacenter": "dc1",
            "headend_url": "https://headend.example.com",
        }
    )
    old_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=10)
    await real_dal(real_dal.clusters.id == cluster.id).update(last_heartbeat=old_heartbeat)

    await mgr._check_cluster_health()

    updated = await mgr.get_cluster(cluster.id)
    assert updated is not None
    assert updated.status == "stale"


@pytest.mark.asyncio
async def test_monitor_health_happy_path_then_cancelled(
    real_dal, monkeypatch: pytest.MonkeyPatch
) -> None:
    """monitor_health runs one successful iteration then exits on CancelledError."""
    mgr = ClusterManager(real_dal, "tenant-monitor")
    calls = {"check": 0}

    async def fake_check() -> None:
        calls["check"] += 1

    async def fake_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(mgr, "_check_cluster_health", fake_check)
    monkeypatch.setattr(cluster_manager_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await mgr.monitor_health()

    assert calls["check"] == 1


@pytest.mark.asyncio
async def test_monitor_health_error_path_then_cancelled(
    real_dal, monkeypatch: pytest.MonkeyPatch
) -> None:
    """monitor_health logs and retries on error, then exits on CancelledError."""
    mgr = ClusterManager(real_dal, "tenant-monitor-err")

    async def failing_check() -> None:
        raise RuntimeError("health check failed")

    async def fake_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(mgr, "_check_cluster_health", failing_check)
    monkeypatch.setattr(cluster_manager_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await mgr.monitor_health()


# =============================================================================
# ClientRegistry
# =============================================================================


@pytest.mark.asyncio
async def test_client_registry_initialize_success(real_dal) -> None:
    """initialize() logs and returns without error."""
    registry = ClientRegistry(real_dal, "tenant-init")
    await registry.initialize()


@pytest.mark.asyncio
async def test_client_registry_initialize_error_reraises(
    real_dal, monkeypatch: pytest.MonkeyPatch
) -> None:
    """initialize() re-raises after logging when logger.info fails."""
    registry = ClientRegistry(real_dal, "tenant-init-err")
    monkeypatch.setattr(
        client_registry_module.logger, "info", MagicMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError, match="boom"):
        await registry.initialize()


@pytest.mark.asyncio
async def test_client_registry_shutdown(real_dal) -> None:
    """shutdown() completes without raising."""
    registry = ClientRegistry(real_dal, "tenant-shutdown")
    await registry.shutdown()


@pytest.mark.asyncio
async def test_client_registry_authenticate_none_api_key_fails_closed(real_dal) -> None:
    """A non-string api_key raises inside the try block and is fail-closed to None."""
    registry = ClientRegistry(real_dal, "tenant-auth-err")

    result = await registry.authenticate_client(None)  # type: ignore[arg-type]

    assert result is None


@pytest.mark.asyncio
async def test_client_registry_authenticate_hash_mismatch() -> None:
    """Stored hash mismatch (defense-in-depth check) returns None."""
    db = MagicMock()
    row = MagicMock()
    row.id = "client-1"
    row.tenant = "tenant-a"
    row.status = "active"
    row.api_key_hash = "different-hash-than-queried"

    rowset = MagicMock()
    rowset.first.return_value = row

    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=rowset)
    query_proxy.update = AsyncMock(return_value=None)
    query_proxy.__and__ = MagicMock(return_value=query_proxy)

    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy
    db.clients = MagicMock()

    registry = ClientRegistry(db, "tenant-a")
    result = await registry.authenticate_client("some-api-key")

    assert result is None


@pytest.mark.asyncio
async def test_client_registry_update_status_with_metadata_merge(real_dal) -> None:
    """update_client_status merges new metadata into existing metadata."""
    tenant = "tenant-meta"
    registry = ClientRegistry(real_dal, tenant)

    client, _ = await registry.register_client(
        {
            "id": str(uuid4()),
            "name": "meta-client",
            "type": "docker",
            "cluster_id": "cluster-1",
            "public_key": "ssh-rsa AAAAB3...",
            "ip_address": "192.168.1.1",
            "metadata": {"existing": "value"},
        }
    )

    success = await registry.update_client_status(
        client.id, "active", metadata={"new_key": "new_value"}
    )
    assert success is True

    updated = await registry.get_client(client.id)
    assert updated is not None
    assert updated.metadata["existing"] == "value"
    assert updated.metadata["new_key"] == "new_value"


@pytest.mark.asyncio
async def test_client_registry_update_status_error_returns_false() -> None:
    """update_client_status fails closed (returns False) on DB error."""
    db = MagicMock()
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    query_proxy.__and__ = MagicMock(return_value=query_proxy)
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    registry = ClientRegistry(db, "tenant-err")
    result = await registry.update_client_status("client-1", "active")

    assert result is False


@pytest.mark.asyncio
async def test_client_registry_get_all_clients(real_dal) -> None:
    """get_all_clients returns all clients registered for the tenant."""
    tenant = "tenant-all"
    registry = ClientRegistry(real_dal, tenant)

    client1, _ = await registry.register_client(
        {
            "id": str(uuid4()),
            "name": "client-a",
            "type": "docker",
            "cluster_id": "cluster-1",
            "public_key": "ssh-rsa AAAAB3...",
            "ip_address": "192.168.1.1",
        }
    )
    client2, _ = await registry.register_client(
        {
            "id": str(uuid4()),
            "name": "client-b",
            "type": "native",
            "cluster_id": "cluster-1",
            "public_key": "ssh-rsa AAAAB3...",
            "ip_address": "192.168.1.2",
        }
    )

    all_clients = await registry.get_all_clients()
    ids = {c.id for c in all_clients}
    assert client1.id in ids
    assert client2.id in ids


@pytest.mark.asyncio
async def test_client_registry_remove_client(real_dal) -> None:
    """remove_client deletes an existing client and returns True."""
    tenant = "tenant-remove"
    registry = ClientRegistry(real_dal, tenant)

    client, _ = await registry.register_client(
        {
            "id": str(uuid4()),
            "name": "removable",
            "type": "docker",
            "cluster_id": "cluster-1",
            "public_key": "ssh-rsa AAAAB3...",
            "ip_address": "192.168.1.1",
        }
    )

    success = await registry.remove_client(client.id)
    assert success is True

    retrieved = await registry.get_client(client.id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_client_registry_remove_client_not_found(real_dal) -> None:
    """remove_client on a nonexistent client returns False."""
    registry = ClientRegistry(real_dal, "tenant-remove-2")

    success = await registry.remove_client("nonexistent")
    assert success is False


@pytest.mark.asyncio
async def test_client_registry_remove_client_error_returns_false() -> None:
    """remove_client fails closed (returns False) on DB error."""
    db = MagicMock()
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))
    query_proxy.__and__ = MagicMock(return_value=query_proxy)
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    registry = ClientRegistry(db, "tenant-err-2")
    result = await registry.remove_client("client-1")

    assert result is False


@pytest.mark.asyncio
async def test_client_registry_get_client_count(real_dal) -> None:
    """get_client_count reflects registered clients for the tenant."""
    tenant = "tenant-count"
    registry = ClientRegistry(real_dal, tenant)

    await registry.register_client(
        {
            "id": str(uuid4()),
            "name": "count-client",
            "type": "docker",
            "cluster_id": "cluster-1",
            "public_key": "ssh-rsa AAAAB3...",
            "ip_address": "192.168.1.1",
        }
    )

    count = await registry.get_client_count()
    assert count >= 1


@pytest.mark.asyncio
async def test_client_registry_is_healthy_true(real_dal) -> None:
    """is_healthy returns True when get_client_count succeeds."""
    registry = ClientRegistry(real_dal, "tenant-health")
    assert await registry.is_healthy() is True


@pytest.mark.asyncio
async def test_client_registry_is_healthy_false_on_error() -> None:
    """is_healthy returns False when the underlying query raises."""
    db = MagicMock()
    query_proxy = MagicMock()
    query_proxy.count = AsyncMock(side_effect=RuntimeError("db down"))
    query_proxy.__and__ = MagicMock(return_value=query_proxy)
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    registry = ClientRegistry(db, "tenant-unhealthy")
    assert await registry.is_healthy() is False


@pytest.mark.asyncio
async def test_cleanup_stale_clients_removes_inactive(real_dal) -> None:
    """_cleanup_stale_clients removes clients that are stale and non-active."""
    tenant = "tenant-cleanup"
    registry = ClientRegistry(real_dal, tenant)

    client, _ = await registry.register_client(
        {
            "id": str(uuid4()),
            "name": "stale-client",
            "type": "docker",
            "cluster_id": "cluster-1",
            "public_key": "ssh-rsa AAAAB3...",
            "ip_address": "192.168.1.1",
        }
    )
    old_seen = datetime.now(timezone.utc) - timedelta(hours=48)
    await real_dal(real_dal.clients.id == client.id).update(last_seen=old_seen)

    await registry._cleanup_stale_clients()

    remaining = await registry.get_client(client.id)
    assert remaining is None


@pytest.mark.asyncio
async def test_cleanup_expired_happy_path_then_cancelled(
    real_dal, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cleanup_expired runs one successful iteration then exits on CancelledError."""
    registry = ClientRegistry(real_dal, "tenant-cleanup-loop")
    calls = {"cleanup": 0}

    async def fake_cleanup() -> None:
        calls["cleanup"] += 1

    async def fake_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(registry, "_cleanup_stale_clients", fake_cleanup)
    monkeypatch.setattr(client_registry_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await registry.cleanup_expired()

    assert calls["cleanup"] == 1


@pytest.mark.asyncio
async def test_cleanup_expired_error_path_then_cancelled(
    real_dal, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cleanup_expired logs and retries on error, then exits on CancelledError."""
    registry = ClientRegistry(real_dal, "tenant-cleanup-loop-err")

    async def failing_cleanup() -> None:
        raise RuntimeError("cleanup failed")

    async def fake_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(registry, "_cleanup_stale_clients", failing_cleanup)
    monkeypatch.setattr(client_registry_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await registry.cleanup_expired()
