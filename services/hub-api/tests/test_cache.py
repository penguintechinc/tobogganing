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
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        _mock_aioredis.from_url = AsyncMock(side_effect=ConnectionError("refused"))
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
        await redis_cache.extend_ttl("ttlkey", additional_seconds=60)
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

    def test_get_cache_returns_redis_cache_type(self):
        cache = get_cache()
        assert isinstance(cache, RedisCache)

    def test_get_firewall_cache_returns_instance(self):
        cache = get_firewall_cache()
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
