"""Tests for async Redis/Valkey cache manager.

Verifies async operations, fail-open behavior, and cache statistics.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

# Add the app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.cache import CacheManager


class TestCacheManagerConnect:
    """Test cache connection."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful cache connection."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=None)

        async def mock_from_url_coro(url, **kwargs):
            return mock_redis

        with patch("app.cache.aioredis.from_url", side_effect=mock_from_url_coro):
            cache = CacheManager("redis://localhost:6379/0")
            await cache.connect()

            assert cache.redis is not None
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure_fail_open(self) -> None:
        """Test connection failure → fail-open (no exception)."""
        with patch("app.cache.aioredis.from_url") as mock_from_url:
            mock_from_url.side_effect = Exception("Connection failed")

            cache = CacheManager("redis://localhost:6379/0")
            await cache.connect()

            # Fail-open: no exception raised, redis is None
            assert cache.redis is None

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test cache disconnection."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()

        await cache.disconnect()

        cache.redis.close.assert_called_once()


class TestCacheGet:
    """Test cache get operations."""

    @pytest.mark.asyncio
    async def test_get_cache_hit(self) -> None:
        """Test cache hit (found)."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.get = AsyncMock(
            return_value='{"Status": 0, "Answer": [{"data": "192.0.2.1"}]}'
        )

        result = await cache.get("example.com", "A")

        assert result is not None
        assert result["Status"] == 0
        assert cache.cache_hits == 1
        assert cache.cache_misses == 0
        cache.redis.get.assert_called_once_with("dns:example.com:A")

    @pytest.mark.asyncio
    async def test_get_cache_miss(self) -> None:
        """Test cache miss (not found)."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.get = AsyncMock(return_value=None)

        result = await cache.get("example.com", "A")

        assert result is None
        assert cache.cache_hits == 0
        assert cache.cache_misses == 1

    @pytest.mark.asyncio
    async def test_get_no_redis_connection(self) -> None:
        """Test get without redis connection → fail-open."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = None

        result = await cache.get("example.com", "A")

        assert result is None
        assert cache.cache_misses == 1

    @pytest.mark.asyncio
    async def test_get_redis_error_fail_open(self) -> None:
        """Test get with redis error → fail-open (no exception)."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.get = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise, should fail-open to None
        result = await cache.get("example.com", "A")

        assert result is None
        assert cache.cache_misses == 1

    @pytest.mark.asyncio
    async def test_get_malformed_json(self) -> None:
        """Test get with malformed JSON → fail-open."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.get = AsyncMock(return_value="NOT VALID JSON")

        # Should not raise, should fail-open
        result = await cache.get("example.com", "A")

        assert result is None
        assert cache.cache_misses == 1


class TestCacheSet:
    """Test cache set operations."""

    @pytest.mark.asyncio
    async def test_set_cache_hit(self) -> None:
        """Test setting a cache entry."""
        cache = CacheManager("redis://localhost:6379/0", ttl=300)
        cache.redis = AsyncMock()
        cache.redis.setex = AsyncMock()

        result_data = {"Status": 0, "Answer": []}
        await cache.set("example.com", "A", result_data)

        cache.redis.setex.assert_called_once()
        call_args = cache.redis.setex.call_args
        assert call_args[0][0] == "dns:example.com:A"
        assert call_args[0][1] == 300
        assert '"Status": 0' in call_args[0][2]

    @pytest.mark.asyncio
    async def test_set_custom_ttl(self) -> None:
        """Test set with custom TTL."""
        cache = CacheManager("redis://localhost:6379/0", ttl=300)
        cache.redis = AsyncMock()
        cache.redis.setex = AsyncMock()

        result_data = {"Status": 0, "Answer": []}
        await cache.set("example.com", "A", result_data, ttl=600)

        call_args = cache.redis.setex.call_args
        assert call_args[0][1] == 600

    @pytest.mark.asyncio
    async def test_set_no_redis_connection(self) -> None:
        """Test set without redis connection → fail-open (no-op)."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = None

        result_data = {"Status": 0, "Answer": []}
        await cache.set("example.com", "A", result_data)

        # Should not raise, should silently skip

    @pytest.mark.asyncio
    async def test_set_redis_error_fail_open(self) -> None:
        """Test set with redis error → fail-open (no exception)."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.setex = AsyncMock(side_effect=Exception("Redis error"))

        result_data = {"Status": 0, "Answer": []}
        await cache.set("example.com", "A", result_data)

        # Should not raise, should fail-open


class TestCacheClear:
    """Test cache clear operations."""

    @pytest.mark.asyncio
    async def test_clear_cache(self) -> None:
        """Test clearing cache."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.keys = AsyncMock(return_value=["dns:example.com:A", "dns:other.com:A"])
        cache.redis.delete = AsyncMock()

        await cache.clear()

        cache.redis.keys.assert_called_once_with("dns:*")
        cache.redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_cache_no_keys(self) -> None:
        """Test clear when cache is empty."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.keys = AsyncMock(return_value=[])
        cache.redis.delete = AsyncMock()

        await cache.clear()

        cache.redis.keys.assert_called_once()
        cache.redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_no_redis_connection(self) -> None:
        """Test clear without redis connection → fail-open."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = None

        await cache.clear()

        # Should not raise

    @pytest.mark.asyncio
    async def test_clear_redis_error_fail_open(self) -> None:
        """Test clear with redis error → fail-open."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.redis = AsyncMock()
        cache.redis.keys = AsyncMock(side_effect=Exception("Redis error"))

        await cache.clear()

        # Should not raise


class TestCacheStats:
    """Test cache statistics."""

    def test_get_stats_initial(self) -> None:
        """Test initial statistics."""
        cache = CacheManager("redis://localhost:6379/0")

        stats = cache.get_stats()

        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_get_stats_with_hits_and_misses(self) -> None:
        """Test statistics with hits and misses."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.cache_hits = 7
        cache.cache_misses = 3

        stats = cache.get_stats()

        assert stats["cache_hits"] == 7
        assert stats["cache_misses"] == 3
        assert stats["hit_rate"] == 0.7

    def test_get_stats_only_hits(self) -> None:
        """Test statistics with only hits."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.cache_hits = 10
        cache.cache_misses = 0

        stats = cache.get_stats()

        assert stats["hit_rate"] == 1.0

    def test_get_stats_only_misses(self) -> None:
        """Test statistics with only misses."""
        cache = CacheManager("redis://localhost:6379/0")
        cache.cache_hits = 0
        cache.cache_misses = 10

        stats = cache.get_stats()

        assert stats["hit_rate"] == 0.0


class TestCacheFailOpenRoundTrip:
    """Test cache fail-open roundtrip scenarios."""

    @pytest.mark.asyncio
    async def test_get_set_roundtrip_with_connection(self) -> None:
        """Test successful get/set roundtrip."""
        cache = CacheManager("redis://localhost:6379/0", ttl=300)
        cache.redis = AsyncMock()

        result_data = {"Status": 0, "Answer": [{"data": "192.0.2.1"}]}

        # Set
        await cache.set("example.com", "A", result_data)
        cache.redis.setex.assert_called_once()

        # Get (simulate Redis returning what we stored)
        cache.redis.get = AsyncMock(return_value='{"Status": 0, "Answer": [{"data": "192.0.2.1"}]}')
        retrieved = await cache.get("example.com", "A")

        assert retrieved == result_data

    @pytest.mark.asyncio
    async def test_cache_survives_connection_loss(self) -> None:
        """Test that resolver can continue if cache connection lost."""
        cache = CacheManager("redis://localhost:6379/0")

        # Start with connection
        cache.redis = AsyncMock()

        # Connection lost (error)
        cache.redis.get = AsyncMock(side_effect=Exception("Connection lost"))
        result = await cache.get("example.com", "A")

        # Fail-open: get returns None, but doesn't crash
        assert result is None
        # Resolver would continue with direct resolution
