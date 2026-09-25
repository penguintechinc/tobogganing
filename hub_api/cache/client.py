"""Async Valkey/Redis cache client with namespace guards and in-memory fallback."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import redis
import structlog

from hub_api.cache.keys import prefixed

logger = structlog.get_logger()

# How long to stay latched onto the in-memory fallback after a backend
# failure before probing Redis again. Without this, a single blip pins the
# process to per-pod in-memory state (rate-limit counters, JWT-revocation
# checks, etc.) for the rest of its life -- across N replicas that's a
# permanent desync, not a transient degradation (ops audit finding O4/O5).
_RETRY_COOLDOWN_SECS = 30.0


class CacheUnavailable(RuntimeError):
    """Raised when cache backend is unavailable and fail_closed=True."""

    pass


@dataclass(slots=True)
class CacheClient:
    """Async cache client wrapping Valkey/Redis with lazy init and in-memory fallback.

    Configurable via env (CACHE_HOST, CACHE_PORT, CACHE_DB, CACHE_USER, CACHE_PASS).
    Uses short socket timeouts (50ms) and no health checks for fail-fast degradation.
    """

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    user: Optional[str] = None
    password: Optional[str] = None

    _redis: Optional[redis.Redis] = None
    _backend_failed: bool = False  # Track failure to skip repeated init attempts
    _failed_at: float = 0.0  # time.time() of the failure that set _backend_failed
    _fallback: dict[str, tuple[float, str]] = None  # {key: (expiry_time, value)}

    def __post_init__(self) -> None:
        """Initialize fallback dict."""
        if self._fallback is None:
            object.__setattr__(self, "_fallback", {})

    @property
    def available(self) -> bool:
        """Whether the backend is currently available."""
        return not self._backend_failed

    def _cooldown_elapsed(self) -> bool:
        """Whether it's time to retry Redis after a prior failure.

        `_failed_at <= 0` means `_backend_failed` was never actually set via
        `_mark_failed()` (e.g. set directly in a test) -- treated as "not
        yet eligible" so that path stays permanently latched exactly as
        before, rather than probing a backend that was never really timed.
        """
        if self._failed_at <= 0:
            return False
        return (time.time() - self._failed_at) >= _RETRY_COOLDOWN_SECS

    def _mark_failed(self) -> None:
        """Record a backend failure and start the retry cooldown."""
        object.__setattr__(self, "_backend_failed", True)
        object.__setattr__(self, "_failed_at", time.time())

    def _mark_recovered(self) -> None:
        """Clear the failure latch once a backend call succeeds again."""
        if self._backend_failed:
            object.__setattr__(self, "_backend_failed", False)
            object.__setattr__(self, "_failed_at", 0.0)
            logger.info("cache_backend_recovered")

    async def get(self, namespace: str, *parts: str, fail_closed: bool = False) -> Optional[str]:
        """Get a value from cache.

        Args:
            namespace: Cache namespace.
            *parts: Key parts.
            fail_closed: If True, raise CacheUnavailable on backend error.

        Returns:
            Cached value or None if not found.

        Raises:
            CacheUnavailable: If fail_closed=True and backend unavailable.
        """
        key = prefixed(namespace, *parts)

        if self._backend_failed and not self._cooldown_elapsed():
            if fail_closed:
                raise CacheUnavailable("cache backend unavailable")
            return self._get_fallback(key)

        try:
            # Try Redis with 50ms timeout
            result = await asyncio.wait_for(
                asyncio.to_thread(self._redis_get, key),
                timeout=0.05,
            )
            self._mark_recovered()
            return result
        except (asyncio.TimeoutError, Exception) as e:
            self._mark_failed()
            if fail_closed:
                raise CacheUnavailable(f"cache backend unavailable: {e}") from e
            logger.debug("cache_backend_error_fallback", error=str(e), key=key)
            return self._get_fallback(key)

    async def set(
        self,
        namespace: str,
        *parts: str,
        value: str,
        ttl_seconds: Optional[int] = None,
        fail_closed: bool = False,
    ) -> None:
        """Set a value in cache.

        Args:
            namespace: Cache namespace.
            *parts: Key parts.
            value: Value to cache.
            ttl_seconds: Time-to-live in seconds (optional).
            fail_closed: If True, raise CacheUnavailable on backend error.

        Raises:
            CacheUnavailable: If fail_closed=True and backend unavailable.
        """
        key = prefixed(namespace, *parts)

        if self._backend_failed and not self._cooldown_elapsed():
            if fail_closed:
                raise CacheUnavailable("cache backend unavailable")
            self._set_fallback(key, value, ttl_seconds)
            return

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._redis_set, key, value, ttl_seconds),
                timeout=0.05,
            )
            self._mark_recovered()
        except (asyncio.TimeoutError, Exception) as e:
            self._mark_failed()
            if fail_closed:
                raise CacheUnavailable(f"cache backend unavailable: {e}") from e
            logger.debug("cache_backend_error_fallback", error=str(e), key=key)
            self._set_fallback(key, value, ttl_seconds)

    async def delete(self, namespace: str, *parts: str) -> None:
        """Delete a key from cache.

        Args:
            namespace: Cache namespace.
            *parts: Key parts.
        """
        key = prefixed(namespace, *parts)

        if self._backend_failed and not self._cooldown_elapsed():
            self._delete_fallback(key)
            return

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._redis_delete, key),
                timeout=0.05,
            )
            self._mark_recovered()
        except (asyncio.TimeoutError, Exception) as e:
            self._mark_failed()
            logger.debug("cache_backend_error_fallback", error=str(e), key=key)
            self._delete_fallback(key)

    async def exists(self, namespace: str, *parts: str) -> bool:
        """Check if a key exists in cache.

        Args:
            namespace: Cache namespace.
            *parts: Key parts.

        Returns:
            True if key exists, False otherwise.
        """
        key = prefixed(namespace, *parts)

        if self._backend_failed and not self._cooldown_elapsed():
            return self._exists_fallback(key)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._redis_exists, key),
                timeout=0.05,
            )
            self._mark_recovered()
            return result
        except (asyncio.TimeoutError, Exception) as e:
            self._mark_failed()
            logger.debug("cache_backend_error_fallback", error=str(e), key=key)
            return self._exists_fallback(key)

    def _ensure_redis(self) -> redis.Redis:
        """Lazy-init Redis client with short timeouts."""
        if self._redis is None:
            rc = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                username=self.user,
                password=self.password,
                decode_responses=True,
                socket_timeout=0.05,  # 50ms socket timeout
                socket_connect_timeout=0.05,  # 50ms connect timeout
                health_check_interval=0,  # Disable health checks
            )
            object.__setattr__(self, "_redis", rc)
        return self._redis

    def _redis_get(self, key: str) -> Optional[str]:
        """Get from Redis (sync, called via asyncio.to_thread)."""
        r = self._ensure_redis()
        return r.get(key)

    def _redis_set(self, key: str, value: str, ttl_seconds: Optional[int]) -> None:
        """Set in Redis (sync, called via asyncio.to_thread)."""
        r = self._ensure_redis()
        if ttl_seconds:
            r.setex(key, ttl_seconds, value)
        else:
            r.set(key, value)

    def _redis_delete(self, key: str) -> None:
        """Delete from Redis (sync, called via asyncio.to_thread)."""
        r = self._ensure_redis()
        r.delete(key)

    def _redis_exists(self, key: str) -> bool:
        """Check existence in Redis (sync, called via asyncio.to_thread)."""
        r = self._ensure_redis()
        return bool(r.exists(key))

    def _get_fallback(self, key: str) -> Optional[str]:
        """Get from in-memory fallback (best-effort, TTL-aware)."""
        now = time.time()
        if key in self._fallback:
            expiry, value = self._fallback[key]
            if expiry > now:
                return value
            else:
                del self._fallback[key]
        return None

    def _set_fallback(self, key: str, value: str, ttl_seconds: Optional[int]) -> None:
        """Set in in-memory fallback (best-effort, capped at ~10k keys)."""
        # Simple cap: if we exceed 10k, clear the whole fallback
        if len(self._fallback) >= 10000:
            self._fallback.clear()

        expiry = time.time() + (ttl_seconds or 3600)  # Default 1h if no TTL
        self._fallback[key] = (expiry, value)

    def _delete_fallback(self, key: str) -> None:
        """Delete from in-memory fallback."""
        self._fallback.pop(key, None)

    def _exists_fallback(self, key: str) -> bool:
        """Check existence in in-memory fallback (TTL-aware)."""
        now = time.time()
        if key in self._fallback:
            expiry, _ = self._fallback[key]
            if expiry > now:
                return True
            else:
                del self._fallback[key]
        return False
