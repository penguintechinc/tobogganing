"""Async Redis/Valkey caching for DNS results.

Fail-open design: cache errors never break resolution. Any cache operation
failure logs but returns gracefully (get→None, set→no-op).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheManager:
    """Async Redis/Valkey cache manager for DNS results.

    Fail-open: cache connection issues do not interrupt resolution.
    - get() returns None on error (cache miss)
    - set() silently skips on error (no caching, but resolution continues)
    """

    def __init__(self, cache_url: str, ttl: int = 300) -> None:
        """Initialize cache manager with Redis/Valkey connection.

        Args:
            cache_url: Redis connection URL (redis://host:port/db).
            ttl: Default time-to-live in seconds for cached entries.
        """
        self.cache_url = cache_url
        self.ttl = ttl
        self.redis: aioredis.Redis | None = None
        self.cache_hits = 0
        self.cache_misses = 0

    async def connect(self) -> None:
        """Establish async connection to Redis/Valkey.

        Fails gracefully — logs error but does not raise if connection fails.
        The resolver continues without caching.
        """
        try:
            self.redis = await aioredis.from_url(self.cache_url, decode_responses=True)
            await self.redis.ping()
            logger.info(f"Connected to cache at {self.cache_url}")
        except Exception as e:
            logger.error(f"Failed to connect to cache: {e}")
            self.redis = None

    async def disconnect(self) -> None:
        """Close async Redis connection."""
        if self.redis:
            await self.redis.close()

    async def get(self, domain: str, record_type: str) -> dict[str, Any] | None:
        """Get cached DNS result (fail-open).

        Args:
            domain: Domain name.
            record_type: Record type (A, AAAA, etc.).

        Returns:
            Cached DNS response (Google DoH-JSON format) or None if not cached/error.
        """
        if not self.redis:
            self.cache_misses += 1
            return None

        cache_key = f"dns:{domain}:{record_type}"

        try:
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                self.cache_hits += 1
                logger.debug(f"Cache hit: {cache_key}")
                return json.loads(cached_data)
            else:
                self.cache_misses += 1
                logger.debug(f"Cache miss: {cache_key}")
                return None

        except Exception as e:
            logger.error(f"Cache get error for {cache_key}: {e}")
            self.cache_misses += 1
            # Fail-open: return None (cache miss), do not raise
            return None

    async def set(
        self, domain: str, record_type: str, result: dict[str, Any], ttl: int | None = None
    ) -> None:
        """Cache DNS result (fail-open).

        Args:
            domain: Domain name.
            record_type: Record type.
            result: DNS response (Google DoH-JSON format).
            ttl: Time-to-live in seconds; defaults to self.ttl.
        """
        if not self.redis:
            return

        cache_key = f"dns:{domain}:{record_type}"
        ttl_seconds = ttl if ttl is not None else self.ttl

        try:
            await self.redis.setex(cache_key, ttl_seconds, json.dumps(result))
            logger.debug(f"Cached: {cache_key} (TTL: {ttl_seconds}s)")

        except Exception as e:
            logger.error(f"Cache set error for {cache_key}: {e}")
            # Fail-open: log but do not raise

    async def clear(self) -> None:
        """Clear all DNS cache entries (fail-open).

        Silently skips if cache is unavailable.
        """
        if not self.redis:
            return

        try:
            keys = await self.redis.keys("dns:*")
            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries")
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            # Fail-open: log but do not raise

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics.

        Returns:
            Dict with hit count, miss count, and hit rate.
        """
        total = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total if total > 0 else 0.0

        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": hit_rate,
        }
