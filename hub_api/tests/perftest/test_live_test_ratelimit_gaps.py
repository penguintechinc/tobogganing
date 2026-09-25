"""Coverage backfill for perftest_cluster/security/live_test_ratelimit.py.

test_wpc_live_test.py's TestLiveTestRateLimiter class already covers the
in-memory fallback allow/block/per-tenant paths (no live Redis in this
environment); this file targets the connection_id key branch, the Redis
success/timeout branches (mocked -- no live Redis server reachable here),
and the fallback's window-expiry and zero-limit edge cases.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any
from unittest.mock import MagicMock

import pytest

from hub_api.modules.perftest_cluster.security.live_test_ratelimit import (
    LiveTestRateLimiter,
)


@pytest.mark.asyncio
async def test_is_allowed_with_connection_id_builds_scoped_key() -> None:
    """A connection_id appends a per-connection scope to the rate limit key."""
    limiter = LiveTestRateLimiter(max_tests=5, window_seconds=60)
    allowed, retry_after = await limiter.is_allowed("tenant-x", connection_id="conn-1")
    assert allowed is True
    assert retry_after == 0
    assert "rl:live_test:tenant-x:conn-1" in limiter._fallback_counters


@pytest.mark.asyncio
async def test_is_allowed_redis_success_path_returns_result() -> None:
    """When _check_rule_redis succeeds quickly, is_allowed returns its result directly."""
    limiter = LiveTestRateLimiter(max_tests=5, window_seconds=60)
    limiter._check_rule_redis = MagicMock(return_value=(True, 0))  # type: ignore[method-assign]

    allowed, retry_after = await limiter.is_allowed("tenant-redis-ok")
    assert allowed is True
    assert retry_after == 0
    assert limiter._redis_init_failed is False


@pytest.mark.asyncio
async def test_is_allowed_redis_timeout_falls_back(monkeypatch: Any) -> None:
    """A slow _check_rule_redis triggers the 50ms timeout -> in-memory fallback."""
    limiter = LiveTestRateLimiter(max_tests=5, window_seconds=60)

    def _slow(key: str) -> tuple[bool, int]:
        time.sleep(0.2)
        return (True, 0)

    limiter._check_rule_redis = _slow  # type: ignore[method-assign]

    allowed, retry_after = await limiter.is_allowed("tenant-redis-timeout")
    assert allowed is True
    assert limiter._redis_init_failed is True


@pytest.mark.asyncio
async def test_is_allowed_redis_error_falls_back() -> None:
    """A _check_rule_redis exception (non-timeout) also falls back to in-memory."""
    limiter = LiveTestRateLimiter(max_tests=5, window_seconds=60)

    def _boom(key: str) -> tuple[bool, int]:
        raise ConnectionError("redis down")

    limiter._check_rule_redis = _boom  # type: ignore[method-assign]

    allowed, retry_after = await limiter.is_allowed("tenant-redis-error")
    assert allowed is True
    assert limiter._redis_init_failed is True


def test_check_rule_redis_direct_allow_and_block() -> None:
    """_check_rule_redis's own pipeline logic: allow under limit, block over limit."""
    limiter = LiveTestRateLimiter(max_tests=2, window_seconds=60)

    mock_pipeline = MagicMock()
    mock_pipeline.zremrangebyscore = MagicMock()
    mock_pipeline.zcard = MagicMock()
    mock_pipeline.expire = MagicMock()
    # results[1] is the zcard count.
    mock_pipeline.execute = MagicMock(return_value=[None, 1, None])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    mock_redis.zadd = MagicMock()
    limiter.redis_client = mock_redis

    allowed, retry_after = limiter._check_rule_redis("rl:live_test:t1")
    assert allowed is True
    assert retry_after == 0
    mock_redis.zadd.assert_called_once()


def test_check_rule_redis_direct_blocks_with_oldest_entry() -> None:
    """_check_rule_redis returns (False, retry_after) once at/over the limit."""
    limiter = LiveTestRateLimiter(max_tests=1, window_seconds=60)

    mock_pipeline = MagicMock()
    mock_pipeline.execute = MagicMock(return_value=[None, 1, None])  # count=1 >= max=1

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    now = int(time.time())
    mock_redis.zrange = MagicMock(return_value=[("member", float(now - 10))])
    limiter.redis_client = mock_redis

    allowed, retry_after = limiter._check_rule_redis("rl:live_test:t2")
    assert allowed is False
    assert retry_after > 0


def test_check_rule_redis_blocks_with_no_oldest_entry_fallback() -> None:
    """If zrange returns nothing, retry_after falls back to the full window."""
    limiter = LiveTestRateLimiter(max_tests=1, window_seconds=45)

    mock_pipeline = MagicMock()
    mock_pipeline.execute = MagicMock(return_value=[None, 1, None])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    mock_redis.zrange = MagicMock(return_value=[])
    limiter.redis_client = mock_redis

    allowed, retry_after = limiter._check_rule_redis("rl:live_test:t3")
    assert allowed is False
    assert retry_after == 45


def test_check_rule_redis_pipeline_exception_propagates() -> None:
    """A pipeline execution error is logged and re-raised (caller falls back)."""
    limiter = LiveTestRateLimiter(max_tests=1, window_seconds=60)

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(side_effect=RuntimeError("connection reset"))
    limiter.redis_client = mock_redis

    with pytest.raises(RuntimeError, match="connection reset"):
        limiter._check_rule_redis("rl:live_test:t4")


def test_check_rule_fallback_expires_old_entries() -> None:
    """Entries older than window_seconds are evicted before counting (popleft branch)."""
    limiter = LiveTestRateLimiter(max_tests=5, window_seconds=10)
    key = "rl:live_test:expiry-tenant"
    # Seed with a stale entry far outside the window.
    limiter._fallback_counters[key] = deque([time.time() - 100])

    allowed, retry_after = limiter._check_rule_fallback(key)
    assert allowed is True
    # Stale entry evicted, only the new one remains.
    assert len(limiter._fallback_counters[key]) == 1


def test_check_rule_fallback_zero_max_tests_blocks_with_empty_counter() -> None:
    """max_tests=0 with an empty counter still blocks (falls back to full window)."""
    limiter = LiveTestRateLimiter(max_tests=0, window_seconds=30)
    key = "rl:live_test:zero-tenant"

    allowed, retry_after = limiter._check_rule_fallback(key)
    assert allowed is False
    assert retry_after == 30
