"""Additional coverage for hub_api.cache.client: redis success paths, fail-closed
branches for delete/exists, fallback TTL/cap behavior, and lazy client init.

test_cache_client.py covers the basic fallback roundtrip and fail-closed
get/set against an unreachable backend; this file mocks a working `redis.Redis`
to cover the success paths, and directly exercises the in-memory fallback
internals (TTL expiry, 10k-key cap) and the already-failed-backend branches.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from hub_api.cache.client import CacheClient, CacheUnavailable


class TestAvailableProperty:
    """Tests for CacheClient.available."""

    def test_available_true_initially(self) -> None:
        """available is True before any backend failure."""
        c = CacheClient(host="127.0.0.1", port=6399)
        assert c.available is True

    @pytest.mark.asyncio
    async def test_available_false_after_failure(self) -> None:
        """available becomes False after a failed backend operation."""
        c = CacheClient(host="127.0.0.1", port=6399)
        await c.get("rl", "k")  # unreachable port; will fail fast internally
        assert c.available is False


class TestRedisSuccessPaths:
    """Tests using a mocked, successfully-responding redis.Redis client."""

    def _client_with_fake_redis(self, fake_redis: MagicMock) -> CacheClient:
        c = CacheClient(host="127.0.0.1", port=6379)
        object.__setattr__(c, "_redis", fake_redis)
        return c

    @pytest.mark.asyncio
    async def test_get_success_returns_value(self) -> None:
        """get() returns the Redis value directly when the backend responds."""
        fake_redis = MagicMock()
        fake_redis.get.return_value = "cached-value"
        c = self._client_with_fake_redis(fake_redis)

        result = await c.get("rl", "k")

        assert result == "cached-value"
        assert c.available is True

    @pytest.mark.asyncio
    async def test_set_success_with_ttl(self) -> None:
        """set() calls setex() when a TTL is given."""
        fake_redis = MagicMock()
        c = self._client_with_fake_redis(fake_redis)

        await c.set("rl", "k", value="v", ttl_seconds=30)

        fake_redis.setex.assert_called_once_with("rl:k", 30, "v")
        fake_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_success_without_ttl(self) -> None:
        """set() calls plain set() when no TTL is given."""
        fake_redis = MagicMock()
        c = self._client_with_fake_redis(fake_redis)

        await c.set("rl", "k", value="v")

        fake_redis.set.assert_called_once_with("rl:k", "v")
        fake_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        """delete() calls Redis delete() when the backend is healthy."""
        fake_redis = MagicMock()
        c = self._client_with_fake_redis(fake_redis)

        await c.delete("rl", "k")

        fake_redis.delete.assert_called_once_with("rl:k")

    @pytest.mark.asyncio
    async def test_exists_success_true(self) -> None:
        """exists() returns True when Redis reports the key present."""
        fake_redis = MagicMock()
        fake_redis.exists.return_value = 1
        c = self._client_with_fake_redis(fake_redis)

        result = await c.exists("rl", "k")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_success_false(self) -> None:
        """exists() returns False when Redis reports the key absent."""
        fake_redis = MagicMock()
        fake_redis.exists.return_value = 0
        c = self._client_with_fake_redis(fake_redis)

        result = await c.exists("rl", "k")

        assert result is False


class TestAlreadyFailedBackendBranches:
    """Tests for the _backend_failed=True short-circuit branches."""

    def _failed_client(self) -> CacheClient:
        c = CacheClient(host="127.0.0.1", port=6399)
        object.__setattr__(c, "_backend_failed", True)
        return c

    @pytest.mark.asyncio
    async def test_get_fail_closed_raises_immediately(self) -> None:
        """get() with an already-failed backend and fail_closed=True raises immediately."""
        c = self._failed_client()
        with pytest.raises(CacheUnavailable):
            await c.get("rl", "k", fail_closed=True)

    @pytest.mark.asyncio
    async def test_set_fail_closed_raises_immediately(self) -> None:
        """set() with an already-failed backend and fail_closed=True raises immediately."""
        c = self._failed_client()
        with pytest.raises(CacheUnavailable):
            await c.set("rl", "k", value="v", fail_closed=True)

    @pytest.mark.asyncio
    async def test_delete_uses_fallback_when_already_failed(self) -> None:
        """delete() falls back to the in-memory store without touching Redis."""
        c = self._failed_client()
        await c.set("rl", "k", value="v")  # populate fallback
        await c.delete("rl", "k")
        assert await c.get("rl", "k") is None

    @pytest.mark.asyncio
    async def test_exists_uses_fallback_when_already_failed(self) -> None:
        """exists() falls back to the in-memory store without touching Redis."""
        c = self._failed_client()
        await c.set("rl", "k", value="v")
        assert await c.exists("rl", "k") is True


class TestFallbackInternals:
    """Direct tests for the in-memory fallback store's TTL and cap behavior."""

    def test_fallback_expiry(self) -> None:
        """_get_fallback() returns None and evicts entries past their expiry."""
        c = CacheClient()
        key = "rl:k"
        c._fallback[key] = (time.time() - 1, "expired-value")  # already expired

        result = c._get_fallback(key)

        assert result is None
        assert key not in c._fallback

    def test_fallback_exists_expiry(self) -> None:
        """_exists_fallback() returns False and evicts entries past their expiry."""
        c = CacheClient()
        key = "rl:k"
        c._fallback[key] = (time.time() - 1, "expired-value")

        result = c._exists_fallback(key)

        assert result is False
        assert key not in c._fallback

    def test_fallback_cap_clears_at_10k(self) -> None:
        """_set_fallback() clears the whole store once it reaches the 10k-key cap."""
        c = CacheClient()
        for i in range(10000):
            c._fallback[f"k{i}"] = (time.time() + 3600, "v")
        assert len(c._fallback) == 10000

        c._set_fallback("rl:new-key", "new-value", None)

        # The cap-triggered clear means only the newly-set key remains.
        assert len(c._fallback) == 1
        assert "rl:new-key" in c._fallback


class TestEnsureRedisAuth:
    """Tests for _ensure_redis()'s username/password wiring."""

    def test_ensure_redis_with_credentials(self) -> None:
        """_ensure_redis() passes username/password through to redis.Redis()."""
        c = CacheClient(host="cache.local", port=6379, user="svc", password="secret")

        with patch("hub_api.cache.client.redis.Redis") as mock_redis_cls:
            c._ensure_redis()

        mock_redis_cls.assert_called_once()
        _, kwargs = mock_redis_cls.call_args
        assert kwargs["username"] == "svc"
        assert kwargs["password"] == "secret"

    def test_ensure_redis_cached_on_second_call(self) -> None:
        """_ensure_redis() only constructs the Redis client once."""
        c = CacheClient(host="cache.local", port=6379)

        with patch("hub_api.cache.client.redis.Redis") as mock_redis_cls:
            first = c._ensure_redis()
            second = c._ensure_redis()

        assert first is second
        mock_redis_cls.assert_called_once()
