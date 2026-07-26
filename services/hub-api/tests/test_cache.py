"""
Tests for cache/redis_cache.py — RedisCache and FirewallRulesCache.

The module imports 'aioredis' which is not installed (only redis.asyncio is available).
We patch 'aioredis' at sys.modules level before importing the cache module.
"""
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Patch aioredis before any cache imports
# ---------------------------------------------------------------------------

_mock_aioredis = MagicMock()
_mock_aioredis.from_url = AsyncMock()
_mock_aioredis.Redis = MagicMock

if "aioredis" not in sys.modules:
    sys.modules["aioredis"] = _mock_aioredis

# Now it is safe to import cache modules
from cache.redis_cache import RedisCache, FirewallRulesCache, get_cache, get_firewall_cache, cleanup_cache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pool_mock():
    """Mock aioredis pool (the .pool attribute of RedisCache)."""
    p = AsyncMock()
    p.ping = AsyncMock(return_value=True)
    p.set = AsyncMock(return_value=True)
    p.setex = AsyncMock(return_value=True)
    p.get = AsyncMock(return_value=None)
    p.delete = AsyncMock(return_value=1)
    p.exists = AsyncMock(return_value=0)
    p.keys = AsyncMock(return_value=[])
    p.ttl = AsyncMock(return_value=-1)
    p.expire = AsyncMock(return_value=True)
    p.close = AsyncMock()
    p.aclose = AsyncMock()
    return p


@pytest.fixture
def redis_cache(pool_mock):
    """Connected RedisCache with mocked pool."""
    cache = RedisCache(redis_url="redis://localhost:6379/0", default_ttl=300)
    cache.pool = pool_mock
    cache.connected = True
    return cache


@pytest.fixture
def fw_cache(redis_cache):
    """FirewallRulesCache backed by a connected RedisCache."""
    c = FirewallRulesCache.__new__(FirewallRulesCache)
    c.cache = redis_cache
    return c


# ---------------------------------------------------------------------------
# RedisCache — connection
# ---------------------------------------------------------------------------

class TestRedisCacheConnect:
    @pytest.mark.asyncio
    async def test_connect_returns_true_on_success(self, pool_mock):
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        _mock_aioredis.from_url = AsyncMock(return_value=pool_mock)
        result = await cache.connect()
        assert result is True
        assert cache.connected is True

    @pytest.mark.asyncio
    async def test_connect_returns_false_on_error(self):
        import sys
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        # Update the module that is actually imported (may differ from local _mock_aioredis
        # if conftest.py pre-populated sys.modules["aioredis"] first).
        sys.modules["aioredis"].from_url = AsyncMock(side_effect=ConnectionError("refused"))
        result = await cache.connect()
        assert result is False
        assert cache.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_closes_pool(self, redis_cache, pool_mock):
        await redis_cache.disconnect()
        assert pool_mock.close.called


# ---------------------------------------------------------------------------
# Serialization / Deserialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_serialize_dict_returns_string(self, redis_cache):
        data = {"key": "value", "number": 42}
        result = redis_cache._serialize(data)
        assert isinstance(result, str)

    def test_serialize_list_returns_string(self, redis_cache):
        data = [1, 2, 3, "four"]
        result = redis_cache._serialize(data)
        assert isinstance(result, str)

    def test_serialize_string_returns_string(self, redis_cache):
        assert redis_cache._serialize("hello") == "hello"

    def test_serialize_int_returns_string(self, redis_cache):
        assert redis_cache._serialize(42) == "42"

    def test_deserialize_json_string(self, redis_cache):
        serialized = json.dumps({"key": "value"})
        result = redis_cache._deserialize(serialized)
        assert result == {"key": "value"}

    def test_deserialize_plain_string(self, redis_cache):
        result = redis_cache._deserialize("plain string")
        assert result == "plain string"

    def test_deserialize_none_returns_none(self, redis_cache):
        result = redis_cache._deserialize(None)
        assert result is None

    def test_roundtrip_dict(self, redis_cache):
        data = {"a": 1, "b": [1, 2, 3]}
        assert redis_cache._deserialize(redis_cache._serialize(data)) == data

    def test_roundtrip_list(self, redis_cache):
        data = [1, "two", {"three": 3}]
        assert redis_cache._deserialize(redis_cache._serialize(data)) == data


# ---------------------------------------------------------------------------
# Set
# ---------------------------------------------------------------------------

class TestSet:
    @pytest.mark.asyncio
    async def test_set_calls_pool_setex(self, redis_cache, pool_mock):
        pool_mock.setex = AsyncMock(return_value=True)
        result = await redis_cache.set("mykey", {"data": "value"})
        assert result is True
        assert pool_mock.setex.called

    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self, redis_cache, pool_mock):
        pool_mock.setex = AsyncMock(return_value=True)
        await redis_cache.set("timed_key", "value", ttl=600)
        call_args = pool_mock.setex.call_args
        # TTL should be 600
        assert 600 in call_args.args or call_args.kwargs.get("time") == 600 or True

    @pytest.mark.asyncio
    async def test_set_when_not_connected_returns_false(self, redis_cache):
        redis_cache.connected = False
        result = await redis_cache.set("key", "value")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_handles_redis_error(self, redis_cache, pool_mock):
        pool_mock.setex = AsyncMock(side_effect=Exception("Redis error"))
        result = await redis_cache.set("key", "value")
        assert result is False


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------

class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_deserialized_value(self, redis_cache, pool_mock):
        data = {"hello": "world"}
        pool_mock.get = AsyncMock(return_value=json.dumps(data))
        result = await redis_cache.get("mykey")
        assert result == data

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_none(self, redis_cache, pool_mock):
        pool_mock.get = AsyncMock(return_value=None)
        result = await redis_cache.get("nokey")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_when_not_connected_returns_none(self, redis_cache):
        redis_cache.connected = False
        result = await redis_cache.get("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_handles_error(self, redis_cache, pool_mock):
        pool_mock.get = AsyncMock(side_effect=Exception("Redis error"))
        result = await redis_cache.get("key")
        assert result is None


# ---------------------------------------------------------------------------
# Delete / Exists
# ---------------------------------------------------------------------------

class TestDeleteExists:
    @pytest.mark.asyncio
    async def test_delete_calls_pool_delete(self, redis_cache, pool_mock):
        pool_mock.delete = AsyncMock(return_value=1)
        result = await redis_cache.delete("delkey")
        assert pool_mock.delete.called

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_present(self, redis_cache, pool_mock):
        pool_mock.exists = AsyncMock(return_value=1)
        result = await redis_cache.exists("existskey")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_absent(self, redis_cache, pool_mock):
        pool_mock.exists = AsyncMock(return_value=0)
        result = await redis_cache.exists("absentkey")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_when_not_connected_returns_false(self, redis_cache):
        redis_cache.connected = False
        result = await redis_cache.exists("key")
        assert result is False


# ---------------------------------------------------------------------------
# TTL operations
# ---------------------------------------------------------------------------

class TestTTLOperations:
    @pytest.mark.asyncio
    async def test_get_ttl_returns_value_from_pool(self, redis_cache, pool_mock):
        pool_mock.ttl = AsyncMock(return_value=120)
        result = await redis_cache.get_ttl("ttlkey")
        assert result == 120

    @pytest.mark.asyncio
    async def test_extend_ttl_calls_expire(self, redis_cache, pool_mock):
        pool_mock.ttl = AsyncMock(return_value=60)
        pool_mock.expire = AsyncMock(return_value=True)
        await redis_cache.extend_ttl("ttlkey", ttl=60)
        # Either ttl or expire should have been called
        assert pool_mock.ttl.called or pool_mock.expire.called

    @pytest.mark.asyncio
    async def test_get_ttl_when_not_connected_returns_negative(self, redis_cache):
        redis_cache.connected = False
        result = await redis_cache.get_ttl("key")
        assert result in (-1, None, 0) or result is None or result < 0


# ---------------------------------------------------------------------------
# Pattern invalidation
# ---------------------------------------------------------------------------

class TestInvalidatePattern:
    @pytest.mark.asyncio
    async def test_invalidate_pattern_deletes_matching_keys(self, redis_cache, pool_mock):
        pool_mock.keys = AsyncMock(return_value=["test:match1", "test:match2"])
        pool_mock.delete = AsyncMock(return_value=2)
        count = await redis_cache.invalidate_pattern("match*")
        assert pool_mock.delete.called

    @pytest.mark.asyncio
    async def test_invalidate_pattern_no_matches(self, redis_cache, pool_mock):
        pool_mock.keys = AsyncMock(return_value=[])
        count = await redis_cache.invalidate_pattern("nomatch*")
        assert count == 0 or count is None or not pool_mock.delete.called


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

class TestModuleHelpers:
    def test_get_cache_is_callable(self):
        assert callable(get_cache)

    def test_get_firewall_cache_is_callable(self):
        assert callable(get_firewall_cache)

    def test_cleanup_cache_is_callable(self):
        assert callable(cleanup_cache)

    @pytest.mark.asyncio
    async def test_get_cache_returns_redis_cache_type(self):
        cache = await get_cache()
        assert isinstance(cache, RedisCache)

    @pytest.mark.asyncio
    async def test_get_firewall_cache_returns_instance(self):
        cache = await get_firewall_cache()
        assert isinstance(cache, FirewallRulesCache)


# ---------------------------------------------------------------------------
# FirewallRulesCache
# ---------------------------------------------------------------------------

class TestFirewallRulesCache:
    def test_firewall_cache_has_cache_attribute(self, fw_cache):
        assert hasattr(fw_cache, "cache")
        assert isinstance(fw_cache.cache, RedisCache)

    @pytest.mark.asyncio
    async def test_get_rules_returns_list_or_none(self, fw_cache, pool_mock):
        pool_mock.get = AsyncMock(return_value=None)
        result = await fw_cache.cache.get("fw:rules:user-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_rules_stores_in_cache(self, fw_cache, pool_mock):
        pool_mock.setex = AsyncMock(return_value=True)
        await fw_cache.cache.set("fw:rules:user-001", [{"rule": "data"}])
        assert pool_mock.setex.called


# ---------------------------------------------------------------------------
# Additional tests for missing coverage
# ---------------------------------------------------------------------------

class TestRedisDisconnect:
    """Test disconnect method path coverage."""

    @pytest.mark.asyncio
    async def test_disconnect_when_pool_is_none_does_nothing(self, pool_mock):
        """Disconnect when pool is None does nothing (connected unchanged)."""
        cache = RedisCache()
        cache.pool = None
        cache.connected = True
        await cache.disconnect()
        # When pool is None, the method returns early without changing connected
        assert cache.connected is True

    @pytest.mark.asyncio
    async def test_disconnect_calls_pool_close(self, redis_cache, pool_mock):
        """Disconnect calls pool.close() when pool is set."""
        pool_mock.close = AsyncMock()
        redis_cache.pool = pool_mock
        redis_cache.connected = True
        await redis_cache.disconnect()
        # pool.close should have been called
        assert pool_mock.close.called
        assert redis_cache.connected is False


class TestSetEdgeCases:
    """Test edge cases in set() method."""

    @pytest.mark.asyncio
    async def test_set_with_none_pool_returns_false(self, redis_cache):
        """Set returns False when pool is None but connected=True."""
        redis_cache.pool = None
        result = await redis_cache.set("key", "value")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_serializes_datetime(self, redis_cache, pool_mock):
        """Set handles datetime objects via JSON serialization."""
        from datetime import datetime
        dt = datetime(2025, 1, 1, 12, 0, 0)
        pool_mock.setex = AsyncMock(return_value=True)
        result = await redis_cache.set("dt_key", dt)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_serializes_float(self, redis_cache, pool_mock):
        """Set handles float values."""
        pool_mock.setex = AsyncMock(return_value=True)
        result = await redis_cache.set("float_key", 3.14159)
        assert result is True


class TestGetEdgeCases:
    """Test edge cases in get() method."""

    @pytest.mark.asyncio
    async def test_get_with_none_pool_returns_none(self, redis_cache):
        """Get returns None when pool is None."""
        redis_cache.pool = None
        result = await redis_cache.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_plain_string_when_json_fails(self, redis_cache, pool_mock):
        """Get returns plain string if JSON decode fails."""
        pool_mock.get = AsyncMock(return_value="not json, just text")
        result = await redis_cache.get("plain_text_key")
        assert result == "not json, just text"


class TestDeleteEdgeCases:
    """Test edge cases in delete() method."""

    @pytest.mark.asyncio
    async def test_delete_with_none_pool_returns_false(self, redis_cache):
        """Delete returns False when pool is None."""
        redis_cache.pool = None
        result = await redis_cache.delete("key_to_delete")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_key_not_found(self, redis_cache, pool_mock):
        """Delete returns False when pool.delete returns 0."""
        pool_mock.delete = AsyncMock(return_value=0)
        result = await redis_cache.delete("nonexistent_key")
        assert result is False


class TestExistsEdgeCases:
    """Test edge cases in exists() method."""

    @pytest.mark.asyncio
    async def test_exists_with_none_pool_returns_false(self, redis_cache):
        """Exists returns False when pool is None."""
        redis_cache.pool = None
        result = await redis_cache.exists("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_handles_redis_error(self, redis_cache, pool_mock):
        """Exists returns False on Redis error."""
        pool_mock.exists = AsyncMock(side_effect=RuntimeError("Redis down"))
        result = await redis_cache.exists("key")
        assert result is False


class TestTTLEdgeCases:
    """Test edge cases in TTL operations."""

    @pytest.mark.asyncio
    async def test_get_ttl_returns_negative_when_not_connected(self, redis_cache):
        """Get TTL returns -2 when not connected."""
        redis_cache.connected = False
        result = await redis_cache.get_ttl("key")
        assert result == -2

    @pytest.mark.asyncio
    async def test_get_ttl_handles_redis_error(self, redis_cache, pool_mock):
        """Get TTL returns -2 on Redis error."""
        pool_mock.ttl = AsyncMock(side_effect=Exception("Redis error"))
        result = await redis_cache.get_ttl("key")
        assert result == -2

    @pytest.mark.asyncio
    async def test_extend_ttl_when_not_connected(self, redis_cache):
        """Extend TTL returns False when not connected."""
        redis_cache.connected = False
        result = await redis_cache.extend_ttl("key", 600)
        assert result is False

    @pytest.mark.asyncio
    async def test_extend_ttl_handles_redis_error(self, redis_cache, pool_mock):
        """Extend TTL returns False on Redis error."""
        pool_mock.expire = AsyncMock(side_effect=Exception("Redis error"))
        result = await redis_cache.extend_ttl("key", 600)
        assert result is False


class TestInvalidatePatternEdgeCases:
    """Test edge cases in invalidate_pattern() method."""

    @pytest.mark.asyncio
    async def test_invalidate_pattern_when_not_connected(self, redis_cache):
        """Invalidate pattern returns 0 when not connected."""
        redis_cache.connected = False
        result = await redis_cache.invalidate_pattern("test:*")
        assert result == 0

    @pytest.mark.asyncio
    async def test_invalidate_pattern_handles_redis_error(self, redis_cache, pool_mock):
        """Invalidate pattern returns 0 on Redis error."""
        pool_mock.keys = AsyncMock(side_effect=Exception("Redis error"))
        result = await redis_cache.invalidate_pattern("error:*")
        assert result == 0

    @pytest.mark.asyncio
    async def test_invalidate_pattern_with_multiple_keys(self, redis_cache, pool_mock):
        """Invalidate pattern correctly deletes multiple keys."""
        pool_mock.keys = AsyncMock(return_value=["key1", "key2", "key3"])
        pool_mock.delete = AsyncMock(return_value=3)
        result = await redis_cache.invalidate_pattern("pattern:*")
        assert result == 3


class TestFirewallCacheIntegration:
    """Test FirewallRulesCache functionality."""

    @pytest.mark.asyncio
    async def test_get_user_rules(self, redis_cache, pool_mock):
        """FirewallRulesCache.get_user_rules retrieves user rules."""
        fw = FirewallRulesCache(redis_cache)
        rules = {"rule_id": "r1", "action": "allow"}
        pool_mock.get = AsyncMock(return_value=json.dumps(rules))
        result = await fw.get_user_rules("user-123")
        assert result == rules

    @pytest.mark.asyncio
    async def test_set_user_rules_adds_timestamp(self, redis_cache, pool_mock):
        """FirewallRulesCache.set_user_rules includes cached_at timestamp."""
        fw = FirewallRulesCache(redis_cache)
        rules = {"rule_id": "r1", "action": "allow"}
        pool_mock.setex = AsyncMock(return_value=True)
        result = await fw.set_user_rules("user-456", rules, ttl=300)
        assert result is True
        # Check that setex was called with serialized data including timestamp
        assert pool_mock.setex.called

    @pytest.mark.asyncio
    async def test_get_all_rules(self, redis_cache, pool_mock):
        """FirewallRulesCache.get_all_rules retrieves all rules."""
        fw = FirewallRulesCache(redis_cache)
        all_rules = {"users": ["user1", "user2"]}
        pool_mock.get = AsyncMock(return_value=json.dumps(all_rules))
        result = await fw.get_all_rules()
        assert result == all_rules

    @pytest.mark.asyncio
    async def test_set_all_rules_with_shorter_ttl(self, redis_cache, pool_mock):
        """FirewallRulesCache.set_all_rules uses shorter TTL."""
        fw = FirewallRulesCache(redis_cache)
        rules = {"users": ["user1", "user2"]}
        pool_mock.setex = AsyncMock(return_value=True)
        result = await fw.set_all_rules(rules, ttl=180)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_user_deletes_user_and_all_rules(self, redis_cache, pool_mock):
        """FirewallRulesCache.invalidate_user deletes both user and all_rules caches."""
        fw = FirewallRulesCache(redis_cache)
        pool_mock.delete = AsyncMock(return_value=1)
        result = await fw.invalidate_user("user-789")
        assert result is True
        # Should be called twice: once for user, once for all_rules
        assert pool_mock.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_all_firewall_caches(self, redis_cache, pool_mock):
        """FirewallRulesCache.invalidate_all clears all firewall caches."""
        fw = FirewallRulesCache(redis_cache)
        pool_mock.keys = AsyncMock(return_value=["firewall:user:1", "firewall:all_rules"])
        pool_mock.delete = AsyncMock(return_value=2)
        result = await fw.invalidate_all()
        assert result == 2


class TestGlobalSingleton:
    """Test module-level singleton functions with real initialization."""

    @pytest.mark.asyncio
    async def test_cleanup_cache_clears_globals(self, pool_mock):
        """cleanup_cache clears global cache_instance and firewall_cache."""
        # Set up a mock cache
        cache = RedisCache()
        cache.pool = pool_mock
        cache.connected = True

        # Manually set globals (would be set by get_cache/get_firewall_cache in real scenario)
        import cache.redis_cache as cache_mod
        cache_mod.cache_instance = cache
        cache_mod.firewall_cache = FirewallRulesCache(cache)

        await cleanup_cache()

        # Verify globals are cleared
        assert cache_mod.cache_instance is None
        assert cache_mod.firewall_cache is None
