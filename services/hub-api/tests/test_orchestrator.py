"""
Comprehensive pytest tests for orchestrator.cluster_manager and orchestrator.client_registry.

Target: 90%+ coverage of both modules (currently ~22%).
"""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Async mock Redis client that covers all methods used by both managers."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.close = AsyncMock()
    client.hset = AsyncMock(return_value=1)
    client.hdel = AsyncMock(return_value=1)
    client.hgetall = AsyncMock(return_value={})
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.keys = AsyncMock(return_value=[])
    return client


def _make_cluster_manager(redis=None):
    """Instantiate ClusterManager without calling initialize()."""
    from orchestrator.cluster_manager import ClusterManager
    mgr = ClusterManager.__new__(ClusterManager)
    mgr.clusters = {}
    mgr.redis = redis
    mgr.health_check_interval = 30
    mgr._lock = asyncio.Lock()
    return mgr


def _make_client_registry(redis=None):
    """Instantiate ClientRegistry without calling initialize()."""
    from orchestrator.client_registry import ClientRegistry
    reg = ClientRegistry.__new__(ClientRegistry)
    reg.clients = {}
    reg.api_keys = {}
    reg.redis = redis
    reg.cleanup_interval = 300
    reg._lock = asyncio.Lock()
    return reg


def _cluster_data(cid="c1", region="us-east", dc="dc1"):
    return {
        "id": cid,
        "name": f"Cluster {cid}",
        "region": region,
        "datacenter": dc,
        "headend_url": f"https://{cid}.example.com",
        "metadata": {"owner": "test"},
    }


def _client_data(cid="client-1", cluster_id="c1", ctype="docker"):
    return {
        "id": cid,
        "name": f"Client {cid}",
        "type": ctype,
        "cluster_id": cluster_id,
        "public_key": "base64pubkey==",
        "ip_address": "10.0.0.1",
        "metadata": {"env": "test"},
    }


# ===========================================================================
# ClusterManager Tests
# ===========================================================================

class TestClusterManagerInitialize:
    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_redis):
        """initialize() connects to Redis and loads existing clusters."""
        from orchestrator.cluster_manager import ClusterManager

        with patch("aioredis.from_url", new=AsyncMock(return_value=mock_redis)):
            mgr = ClusterManager()
            await mgr.initialize()

        assert mgr.redis is mock_redis
        mock_redis.hgetall.assert_awaited_once_with("clusters")

    @pytest.mark.asyncio
    async def test_initialize_loads_clusters_from_redis(self, mock_redis):
        """initialize() deserialises clusters stored in Redis."""
        from orchestrator.cluster_manager import ClusterManager

        stored_cluster = {
            "id": "c1",
            "name": "C1",
            "region": "us-east",
            "datacenter": "dc1",
            "headend_url": "https://c1.example.com",
            "status": "active",
            "last_heartbeat": datetime.now().isoformat(),
            "client_count": 2,
            "metadata": {},
        }
        mock_redis.hgetall = AsyncMock(return_value={"c1": json.dumps(stored_cluster)})

        with patch("aioredis.from_url", new=AsyncMock(return_value=mock_redis)):
            mgr = ClusterManager()
            await mgr.initialize()

        assert "c1" in mgr.clusters
        assert mgr.clusters["c1"].client_count == 2

    @pytest.mark.asyncio
    async def test_initialize_raises_on_redis_failure(self):
        """initialize() propagates exceptions from Redis connection."""
        from orchestrator.cluster_manager import ClusterManager

        with patch("aioredis.from_url", new=AsyncMock(side_effect=ConnectionRefusedError("refused"))):
            mgr = ClusterManager()
            with pytest.raises(ConnectionRefusedError):
                await mgr.initialize()


class TestClusterManagerShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_closes_redis(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.shutdown()
        mock_redis.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_without_redis(self):
        mgr = _make_cluster_manager(redis=None)
        # Should not raise
        await mgr.shutdown()


class TestClusterManagerIsHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_with_redis(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        result = await mgr.is_healthy()
        assert result is True
        mock_redis.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_healthy_redis_ping_fails(self, mock_redis):
        mock_redis.ping = AsyncMock(side_effect=Exception("connection lost"))
        mgr = _make_cluster_manager(redis=mock_redis)
        result = await mgr.is_healthy()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_healthy_without_redis(self):
        mgr = _make_cluster_manager(redis=None)
        result = await mgr.is_healthy()
        assert result is True


class TestClusterManagerGetClusterCount:
    @pytest.mark.asyncio
    async def test_empty(self):
        mgr = _make_cluster_manager()
        assert await mgr.get_cluster_count() == 0

    @pytest.mark.asyncio
    async def test_with_clusters(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        await mgr.register_cluster(_cluster_data("c2"))
        assert await mgr.get_cluster_count() == 2


class TestClusterManagerGetAllClusters:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        mgr = _make_cluster_manager()
        result = await mgr.get_all_clusters()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_registered_clusters(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        await mgr.register_cluster(_cluster_data("c2"))
        result = await mgr.get_all_clusters()
        assert len(result) == 2


class TestClusterManagerRegisterCluster:
    @pytest.mark.asyncio
    async def test_register_without_redis(self):
        mgr = _make_cluster_manager(redis=None)
        cluster = await mgr.register_cluster(_cluster_data("c1"))
        assert cluster.id == "c1"
        assert cluster.status == "active"
        assert cluster.client_count == 0
        assert "c1" in mgr.clusters

    @pytest.mark.asyncio
    async def test_register_with_redis(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        cluster = await mgr.register_cluster(_cluster_data("c1", region="eu-west", dc="lon1"))
        assert cluster.region == "eu-west"
        assert cluster.datacenter == "lon1"
        mock_redis.hset.assert_awaited_once()
        args = mock_redis.hset.call_args
        assert args[0][0] == "clusters"
        assert args[0][1] == "c1"

    @pytest.mark.asyncio
    async def test_register_uses_metadata(self, mock_redis):
        data = _cluster_data("c1")
        data["metadata"] = {"tier": "premium"}
        mgr = _make_cluster_manager(redis=mock_redis)
        cluster = await mgr.register_cluster(data)
        assert cluster.metadata["tier"] == "premium"

    @pytest.mark.asyncio
    async def test_register_default_metadata_when_absent(self, mock_redis):
        data = _cluster_data("c1")
        del data["metadata"]
        mgr = _make_cluster_manager(redis=mock_redis)
        cluster = await mgr.register_cluster(data)
        assert cluster.metadata == {}


class TestClusterManagerUpdateHeartbeat:
    @pytest.mark.asyncio
    async def test_update_heartbeat_existing_cluster(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        result = await mgr.update_heartbeat("c1", client_count=5)
        assert result is True
        assert mgr.clusters["c1"].client_count == 5
        assert mgr.clusters["c1"].status == "active"

    @pytest.mark.asyncio
    async def test_update_heartbeat_missing_cluster(self):
        mgr = _make_cluster_manager()
        result = await mgr.update_heartbeat("nonexistent", client_count=3)
        assert result is False

    @pytest.mark.asyncio
    async def test_update_heartbeat_without_client_count(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        original_count = mgr.clusters["c1"].client_count
        result = await mgr.update_heartbeat("c1")
        assert result is True
        assert mgr.clusters["c1"].client_count == original_count

    @pytest.mark.asyncio
    async def test_update_heartbeat_persists_to_redis(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        mock_redis.hset.reset_mock()
        await mgr.update_heartbeat("c1", client_count=10)
        mock_redis.hset.assert_awaited_once()


class TestClusterManagerGetCluster:
    @pytest.mark.asyncio
    async def test_get_existing_cluster(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        result = await mgr.get_cluster("c1")
        assert result is not None
        assert result.id == "c1"

    @pytest.mark.asyncio
    async def test_get_missing_cluster_returns_none(self):
        mgr = _make_cluster_manager()
        result = await mgr.get_cluster("missing")
        assert result is None


class TestClusterManagerGetByRegionDatacenter:
    @pytest.mark.asyncio
    async def test_get_clusters_by_region(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1", region="us-east"))
        await mgr.register_cluster(_cluster_data("c2", region="eu-west"))
        result = await mgr.get_clusters_by_region("us-east")
        assert len(result) == 1
        assert result[0].id == "c1"

    @pytest.mark.asyncio
    async def test_get_clusters_by_region_no_match(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1", region="us-east"))
        result = await mgr.get_clusters_by_region("ap-southeast")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_clusters_by_datacenter(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1", dc="dc1"))
        await mgr.register_cluster(_cluster_data("c2", dc="dc2"))
        result = await mgr.get_clusters_by_datacenter("dc2")
        assert len(result) == 1
        assert result[0].id == "c2"

    @pytest.mark.asyncio
    async def test_get_clusters_by_datacenter_no_match(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        result = await mgr.get_clusters_by_datacenter("dc99")
        assert result == []


class TestClusterManagerRemoveCluster:
    @pytest.mark.asyncio
    async def test_remove_existing_cluster(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        result = await mgr.remove_cluster("c1")
        assert result is True
        assert "c1" not in mgr.clusters
        mock_redis.hdel.assert_awaited_once_with("clusters", "c1")

    @pytest.mark.asyncio
    async def test_remove_missing_cluster(self):
        mgr = _make_cluster_manager()
        result = await mgr.remove_cluster("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_without_redis(self):
        mgr = _make_cluster_manager(redis=None)
        await mgr.register_cluster(_cluster_data("c1"))
        result = await mgr.remove_cluster("c1")
        assert result is True
        assert "c1" not in mgr.clusters


class TestClusterManagerGetOptimalCluster:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_clusters(self):
        mgr = _make_cluster_manager()
        result = await mgr.get_optimal_cluster({"region": "us-east"})
        assert result is None

    @pytest.mark.asyncio
    async def test_selects_by_datacenter_first(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1", region="us-east", dc="dc1"))
        await mgr.register_cluster(_cluster_data("c2", region="us-east", dc="dc2"))
        result = await mgr.get_optimal_cluster({"region": "us-east", "datacenter": "dc1"})
        assert result is not None
        assert result.id == "c1"

    @pytest.mark.asyncio
    async def test_falls_back_to_region(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1", region="us-east", dc="dc1"))
        await mgr.register_cluster(_cluster_data("c2", region="eu-west", dc="dc2"))
        result = await mgr.get_optimal_cluster({"region": "us-east", "datacenter": "dc99"})
        assert result is not None
        assert result.id == "c1"

    @pytest.mark.asyncio
    async def test_falls_back_to_all_clusters(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1", region="us-east", dc="dc1"))
        result = await mgr.get_optimal_cluster({})
        assert result is not None

    @pytest.mark.asyncio
    async def test_selects_cluster_with_fewest_clients(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1", region="us-east", dc="dc1"))
        await mgr.register_cluster(_cluster_data("c2", region="us-east", dc="dc1"))
        mgr.clusters["c1"].client_count = 10
        mgr.clusters["c2"].client_count = 2
        result = await mgr.get_optimal_cluster({"region": "us-east"})
        assert result.id == "c2"

    @pytest.mark.asyncio
    async def test_skips_non_active_clusters(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        mgr.clusters["c1"].status = "stale"
        result = await mgr.get_optimal_cluster({})
        assert result is None


class TestClusterManagerCheckClusterHealth:
    @pytest.mark.asyncio
    async def test_marks_stale_clusters(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        # Artificially age the heartbeat
        mgr.clusters["c1"].last_heartbeat = datetime.now() - timedelta(minutes=10)
        await mgr._check_cluster_health()
        assert mgr.clusters["c1"].status == "stale"
        mock_redis.hset.assert_awaited()

    @pytest.mark.asyncio
    async def test_does_not_remark_already_stale(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        mgr.clusters["c1"].last_heartbeat = datetime.now() - timedelta(minutes=10)
        mgr.clusters["c1"].status = "stale"
        mock_redis.hset.reset_mock()
        await mgr._check_cluster_health()
        # Should not call hset again since status was already stale
        mock_redis.hset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fresh_cluster_stays_active(self, mock_redis):
        mgr = _make_cluster_manager(redis=mock_redis)
        await mgr.register_cluster(_cluster_data("c1"))
        # heartbeat is just now — should remain active
        await mgr._check_cluster_health()
        assert mgr.clusters["c1"].status == "active"

    @pytest.mark.asyncio
    async def test_health_check_without_redis(self):
        mgr = _make_cluster_manager(redis=None)
        await mgr.register_cluster(_cluster_data("c1"))
        mgr.clusters["c1"].last_heartbeat = datetime.now() - timedelta(minutes=10)
        await mgr._check_cluster_health()
        assert mgr.clusters["c1"].status == "stale"


class TestClusterManagerMonitorHealth:
    @pytest.mark.asyncio
    async def test_monitor_health_runs_and_can_be_cancelled(self, mock_redis):
        """monitor_health() is an infinite loop; cancel it via task cancellation."""
        mgr = _make_cluster_manager(redis=mock_redis)
        mgr.health_check_interval = 0  # avoid actual sleep delay

        call_count = 0

        async def patched():
            nonlocal call_count
            call_count += 1

        mgr._check_cluster_health = patched

        task = asyncio.ensure_future(mgr.monitor_health())
        # Let it run at least one iteration
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_monitor_health_handles_exception_and_retries(self, mock_redis):
        """Errors inside _check_cluster_health should be caught and retried."""
        mgr = _make_cluster_manager(redis=mock_redis)
        # health_check_interval > 0 means after successful check the loop sleeps;
        # we test only the error path, so set to 0 AND patch sleep.
        mgr.health_check_interval = 0

        call_count = 0

        async def patched_check():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            # Cancel after successful second call to terminate the loop.
            raise asyncio.CancelledError()

        mgr._check_cluster_health = patched_check

        # Patch the module-level asyncio so sleep(5) in the except branch is instant.
        sleep_mock = AsyncMock(return_value=None)
        import orchestrator.cluster_manager as _cm_mod
        original_sleep = _cm_mod.asyncio.sleep
        _cm_mod.asyncio.sleep = sleep_mock
        try:
            with pytest.raises(asyncio.CancelledError):
                await mgr.monitor_health()
        finally:
            _cm_mod.asyncio.sleep = original_sleep

        assert call_count == 2


# ===========================================================================
# ClientRegistry Tests
# ===========================================================================

class TestClientRegistryInitialize:
    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_redis):
        from orchestrator.client_registry import ClientRegistry

        with patch("aioredis.from_url", new=AsyncMock(return_value=mock_redis)):
            reg = ClientRegistry()
            await reg.initialize()

        assert reg.redis is mock_redis
        mock_redis.hgetall.assert_awaited_once_with("clients")

    @pytest.mark.asyncio
    async def test_initialize_loads_clients_from_redis(self, mock_redis):
        from orchestrator.client_registry import ClientRegistry

        now = datetime.now()
        stored = {
            "id": "client-1",
            "name": "Test Client",
            "type": "docker",
            "cluster_id": "c1",
            "api_key_hash": "abc123",
            "public_key": "pubkey==",
            "ip_address": "10.0.0.1",
            "status": "active",
            "created_at": now.isoformat(),
            "last_seen": now.isoformat(),
            "metadata": {},
        }
        mock_redis.hgetall = AsyncMock(return_value={"client-1": json.dumps(stored)})

        with patch("aioredis.from_url", new=AsyncMock(return_value=mock_redis)):
            reg = ClientRegistry()
            await reg.initialize()

        assert "client-1" in reg.clients
        assert reg.api_keys.get("abc123") == "client-1"

    @pytest.mark.asyncio
    async def test_initialize_raises_on_failure(self):
        from orchestrator.client_registry import ClientRegistry

        with patch("aioredis.from_url", new=AsyncMock(side_effect=OSError("no redis"))):
            reg = ClientRegistry()
            with pytest.raises(OSError):
                await reg.initialize()


class TestClientRegistryShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_closes_redis(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.shutdown()
        mock_redis.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_without_redis(self):
        reg = _make_client_registry(redis=None)
        await reg.shutdown()  # should not raise


class TestClientRegistryIsHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_with_redis(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        result = await reg.is_healthy()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_healthy_redis_fails(self, mock_redis):
        mock_redis.ping = AsyncMock(side_effect=Exception("down"))
        reg = _make_client_registry(redis=mock_redis)
        result = await reg.is_healthy()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_healthy_no_redis(self):
        reg = _make_client_registry(redis=None)
        result = await reg.is_healthy()
        assert result is True


class TestClientRegistryGetClientCount:
    @pytest.mark.asyncio
    async def test_empty(self):
        reg = _make_client_registry()
        assert await reg.get_client_count() == 0

    @pytest.mark.asyncio
    async def test_with_clients(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        await reg.register_client(_client_data("cl2"))
        assert await reg.get_client_count() == 2


class TestClientRegistryGetAllClients:
    @pytest.mark.asyncio
    async def test_empty(self):
        reg = _make_client_registry()
        result = await reg.get_all_clients()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_registered_clients(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        result = await reg.get_all_clients()
        assert len(result) == 1
        assert result[0].id == "cl1"


class TestClientRegistryRegisterClient:
    @pytest.mark.asyncio
    async def test_register_without_redis(self):
        reg = _make_client_registry(redis=None)
        client, api_key = await reg.register_client(_client_data("cl1"))
        assert client.id == "cl1"
        assert client.status == "pending"
        assert isinstance(api_key, str) and len(api_key) > 10
        expected_hash = hashlib.sha256(api_key.encode()).hexdigest()
        assert client.api_key_hash == expected_hash
        assert reg.api_keys[expected_hash] == "cl1"

    @pytest.mark.asyncio
    async def test_register_with_redis(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        client, api_key = await reg.register_client(_client_data("cl1"))
        mock_redis.hset.assert_awaited()
        mock_redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_uses_optional_ip_address(self, mock_redis):
        data = _client_data("cl1")
        data["ip_address"] = "192.168.1.50"
        reg = _make_client_registry(redis=mock_redis)
        client, _ = await reg.register_client(data)
        assert client.ip_address == "192.168.1.50"

    @pytest.mark.asyncio
    async def test_register_default_ip_when_absent(self, mock_redis):
        data = _client_data("cl1")
        del data["ip_address"]
        reg = _make_client_registry(redis=mock_redis)
        client, _ = await reg.register_client(data)
        assert client.ip_address == ""

    @pytest.mark.asyncio
    async def test_register_default_metadata_when_absent(self, mock_redis):
        data = _client_data("cl1")
        del data["metadata"]
        reg = _make_client_registry(redis=mock_redis)
        client, _ = await reg.register_client(data)
        assert client.metadata == {}


class TestClientRegistryAuthenticateClient:
    @pytest.mark.asyncio
    async def test_authenticate_valid_key(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        client, api_key = await reg.register_client(_client_data("cl1"))
        result = await reg.authenticate_client(api_key)
        assert result is not None
        assert result.id == "cl1"
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_authenticate_unknown_key(self):
        reg = _make_client_registry()
        result = await reg.authenticate_client("totally-invalid-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_fallback_to_redis(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        client, api_key = await reg.register_client(_client_data("cl1"))
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Remove from in-memory map to force Redis fallback
        del reg.api_keys[api_key_hash]

        mock_redis.get = AsyncMock(return_value="cl1")
        result = await reg.authenticate_client(api_key)
        assert result is not None
        assert result.id == "cl1"

    @pytest.mark.asyncio
    async def test_authenticate_redis_returns_unknown_client_id(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        mock_redis.get = AsyncMock(return_value="ghost-client")
        result = await reg.authenticate_client("any-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_persists_last_seen_to_redis(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        _, api_key = await reg.register_client(_client_data("cl1"))
        mock_redis.hset.reset_mock()
        await reg.authenticate_client(api_key)
        mock_redis.hset.assert_awaited()


class TestClientRegistryUpdateClientStatus:
    @pytest.mark.asyncio
    async def test_update_status_existing_client(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        result = await reg.update_client_status("cl1", "active")
        assert result is True
        assert reg.clients["cl1"].status == "active"

    @pytest.mark.asyncio
    async def test_update_status_missing_client(self):
        reg = _make_client_registry()
        result = await reg.update_client_status("nonexistent", "active")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_status_with_metadata(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        result = await reg.update_client_status("cl1", "active", metadata={"version": "1.2.3"})
        assert result is True
        assert reg.clients["cl1"].metadata.get("version") == "1.2.3"

    @pytest.mark.asyncio
    async def test_update_status_without_metadata(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        # metadata=None path
        result = await reg.update_client_status("cl1", "disconnected", metadata=None)
        assert result is True
        assert reg.clients["cl1"].status == "disconnected"

    @pytest.mark.asyncio
    async def test_update_status_persists_to_redis(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        mock_redis.hset.reset_mock()
        await reg.update_client_status("cl1", "active")
        mock_redis.hset.assert_awaited()


class TestClientRegistryGetClient:
    @pytest.mark.asyncio
    async def test_get_existing(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        result = await reg.get_client("cl1")
        assert result is not None
        assert result.id == "cl1"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        reg = _make_client_registry()
        result = await reg.get_client("missing")
        assert result is None


class TestClientRegistryGetByClusterAndType:
    @pytest.mark.asyncio
    async def test_get_clients_by_cluster(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1", cluster_id="c1"))
        await reg.register_client(_client_data("cl2", cluster_id="c2"))
        result = await reg.get_clients_by_cluster("c1")
        assert len(result) == 1
        assert result[0].id == "cl1"

    @pytest.mark.asyncio
    async def test_get_clients_by_cluster_empty(self):
        reg = _make_client_registry()
        result = await reg.get_clients_by_cluster("c99")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_clients_by_type(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1", ctype="docker"))
        await reg.register_client(_client_data("cl2", ctype="native"))
        result = await reg.get_clients_by_type("native")
        assert len(result) == 1
        assert result[0].id == "cl2"

    @pytest.mark.asyncio
    async def test_get_clients_by_type_empty(self):
        reg = _make_client_registry()
        result = await reg.get_clients_by_type("docker")
        assert result == []


class TestClientRegistryRemoveClient:
    @pytest.mark.asyncio
    async def test_remove_existing_client(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        client, api_key = await reg.register_client(_client_data("cl1"))
        api_key_hash = client.api_key_hash

        result = await reg.remove_client("cl1")
        assert result is True
        assert "cl1" not in reg.clients
        assert api_key_hash not in reg.api_keys
        mock_redis.hdel.assert_awaited_with("clients", "cl1")

    @pytest.mark.asyncio
    async def test_remove_missing_client(self):
        reg = _make_client_registry()
        result = await reg.remove_client("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_without_redis(self):
        reg = _make_client_registry(redis=None)
        await reg.register_client(_client_data("cl1"))
        result = await reg.remove_client("cl1")
        assert result is True
        assert "cl1" not in reg.clients

    @pytest.mark.asyncio
    async def test_remove_cleans_up_redis_api_keys(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        client, api_key = await reg.register_client(_client_data("cl1"))
        api_key_hash = client.api_key_hash

        # Simulate Redis returning this client's API key
        mock_redis.keys = AsyncMock(return_value=[f"api_key:{api_key_hash}"])
        mock_redis.get = AsyncMock(return_value="cl1")

        await reg.remove_client("cl1")
        mock_redis.delete.assert_awaited_with(f"api_key:{api_key_hash}")


class TestClientRegistryCleanupExpired:
    @pytest.mark.asyncio
    async def test_cleanup_expired_runs_and_can_be_cancelled(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        reg.cleanup_interval = 0

        call_count = 0

        async def patched():
            nonlocal call_count
            call_count += 1

        reg._cleanup_stale_clients = patched

        task = asyncio.ensure_future(reg.cleanup_expired())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_cleanup_handles_exception_and_retries(self, mock_redis):
        """Errors in _cleanup_stale_clients are caught and retried after sleep(30)."""
        reg = _make_client_registry(redis=mock_redis)
        reg.cleanup_interval = 0

        call_count = 0

        async def patched():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            raise asyncio.CancelledError()

        reg._cleanup_stale_clients = patched

        import orchestrator.client_registry as _cr_mod
        sleep_mock = AsyncMock(return_value=None)
        original_sleep = _cr_mod.asyncio.sleep
        _cr_mod.asyncio.sleep = sleep_mock
        try:
            with pytest.raises(asyncio.CancelledError):
                await reg.cleanup_expired()
        finally:
            _cr_mod.asyncio.sleep = original_sleep

        assert call_count == 2


class TestClientRegistryCleanupStaleClients:
    @pytest.mark.asyncio
    async def test_removes_inactive_stale_clients(self, mock_redis):
        """_cleanup_stale_clients identifies and removes stale inactive clients.

        Note: _cleanup_stale_clients acquires self._lock then calls remove_client
        which also acquires self._lock — this would deadlock with a real asyncio.Lock.
        We mock remove_client to avoid the re-entrant lock issue and focus on
        verifying the correct clients are identified for removal.
        """
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        await reg.register_client(_client_data("cl2"))

        # Make cl1 stale and inactive
        reg.clients["cl1"].last_seen = datetime.now() - timedelta(hours=25)
        reg.clients["cl1"].status = "disconnected"
        # cl2 is recent
        reg.clients["cl2"].last_seen = datetime.now()

        removed = []

        async def mock_remove(client_id):
            removed.append(client_id)
            return True

        reg.remove_client = mock_remove
        await reg._cleanup_stale_clients()

        assert "cl1" in removed
        assert "cl2" not in removed

    @pytest.mark.asyncio
    async def test_does_not_remove_active_old_clients(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        await reg.register_client(_client_data("cl1"))
        reg.clients["cl1"].last_seen = datetime.now() - timedelta(hours=25)
        reg.clients["cl1"].status = "active"  # Still active, should not be removed

        removed = []

        async def mock_remove(client_id):
            removed.append(client_id)
            return True

        reg.remove_client = mock_remove
        await reg._cleanup_stale_clients()
        assert "cl1" not in removed

    @pytest.mark.asyncio
    async def test_cleanup_empty_registry(self):
        reg = _make_client_registry()
        await reg._cleanup_stale_clients()  # Should not raise


class TestClientRegistryRotateApiKey:
    @pytest.mark.asyncio
    async def test_rotate_api_key_success(self, mock_redis):
        reg = _make_client_registry(redis=mock_redis)
        client, old_api_key = await reg.register_client(_client_data("cl1"))
        old_hash = client.api_key_hash

        new_api_key = await reg.rotate_api_key("cl1")
        assert new_api_key is not None
        assert new_api_key != old_api_key

        new_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
        assert reg.clients["cl1"].api_key_hash == new_hash
        assert new_hash in reg.api_keys
        assert old_hash not in reg.api_keys

        mock_redis.setex.assert_awaited()

    @pytest.mark.asyncio
    async def test_rotate_api_key_missing_client(self):
        reg = _make_client_registry()
        result = await reg.rotate_api_key("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_rotate_api_key_without_redis(self):
        reg = _make_client_registry(redis=None)
        await reg.register_client(_client_data("cl1"))
        new_key = await reg.rotate_api_key("cl1")
        assert new_key is not None
        new_hash = hashlib.sha256(new_key.encode()).hexdigest()
        assert reg.api_keys[new_hash] == "cl1"
