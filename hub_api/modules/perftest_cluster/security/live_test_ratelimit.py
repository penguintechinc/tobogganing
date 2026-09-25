"""Rate limiting for live-test endpoints (WS + HTTP).

Reuses Redis sliding window counter from SASE module core logic.
Per-tenant rate limiting with configurable limits.

The actual ZSET/fallback counting logic now lives in
hub_api/security/rate_limit.py (sliding_window_redis_check /
sliding_window_fallback_check), shared with the auth-credential rate
limiting (login/refresh/enrollment/machine-auth -- security-audit
2026-09-21). This class keeps its original public/private API (is_allowed,
_check_rule_redis, _check_rule_fallback, redis_client, _fallback_counters)
unchanged for its existing call sites and tests.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque

import redis
import structlog

from hub_api.security.rate_limit import (
    sliding_window_fallback_check,
    sliding_window_redis_check,
)

logger = structlog.get_logger()


class LiveTestRateLimiter:
    """Rate limit live-test execution (tests-per-tenant over a time window).

    Reuses the SASE module's Redis sliding window counter pattern.
    Falls back to in-memory counting if Redis unavailable.

    Tracks: tenant_id → (max_tests, window_seconds)
    Default: 10 tests per 60 seconds per tenant.
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        max_tests: int = 10,
        window_seconds: int = 60,
    ) -> None:
        """Initialize LiveTestRateLimiter.

        Args:
            redis_client: Redis client. Lazy init on first use if None.
            max_tests: Max tests per window (default 10).
            window_seconds: Sliding window duration in seconds (default 60).
        """
        self.redis_client = redis_client
        self.max_tests = max_tests
        self.window_seconds = window_seconds
        self._redis_init_failed = False  # Track failed init to avoid repeated attempts

        # Fallback in-memory counters (deque per key)
        self._fallback_counters: dict[str, deque[float]] = defaultdict(deque)

    async def is_allowed(self, tenant_id: str, connection_id: str = "") -> tuple[bool, int]:
        """Check if a test is allowed for the tenant.

        Reuses SASE's Redis sliding window counter logic:
        1. Remove entries older than window
        2. Count entries in window
        3. If count >= max, return (False, retry_after)
        4. Else add entry and return (True, 0)

        Args:
            tenant_id: Tenant identifier (required, scopes all limits).
            connection_id: Optional connection/request ID per-connection limit.
                          If empty, limit is per-tenant only.

        Returns:
            Tuple of (allowed, retry_after_seconds).
            - allowed: True if test execution allowed
            - retry_after_seconds: Seconds to wait if not allowed, else 0
        """
        # Build rate limit key: rl:live_test:{tenant}:{connection_id if any}
        key_parts = ["rl", "live_test", tenant_id]
        if connection_id:
            key_parts.append(connection_id)
        key = ":".join(key_parts)

        # If Redis already failed, skip it and use in-memory immediately
        if self._redis_init_failed:
            return self._check_rule_fallback(key)

        # Try Redis with very fast timeout (50ms); fall back to in-memory immediately on any error
        # This ensures we never block the event loop waiting for Redis in tests or prod degradation
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._check_rule_redis, key),
                timeout=0.05,
            )
            return result
        except (asyncio.TimeoutError, Exception) as e:
            # Mark Redis as failed so we skip it on future calls
            self._redis_init_failed = True
            if isinstance(e, asyncio.TimeoutError):
                logger.debug(
                    "live_test_rate_limit_redis_timeout",
                    timeout_sec=0.05,
                    tenant=tenant_id,
                )
            else:
                logger.debug(
                    "live_test_rate_limit_redis_error",
                    error=str(e),
                    tenant=tenant_id,
                )
            # Fallback to in-memory sliding window immediately
            return self._check_rule_fallback(key)

    def _check_rule_redis(self, key: str) -> tuple[bool, int]:
        """Check rate limit using Redis sliding window (SASE pattern).

        Uses a ZSET sliding window; counting logic delegates to the shared
        hub_api.security.rate_limit.sliding_window_redis_check so both
        LiveTestRateLimiter and the newer auth-endpoint limiters stay in
        sync. Lazy-inits the Redis client with short timeouts on first call.
        """
        # Lazy-init Redis client with short socket+connect timeouts
        if self.redis_client is None:
            self.redis_client = redis.Redis(
                host="localhost",
                port=6379,
                db=2,  # Separate from SASE's db=1
                decode_responses=True,
                socket_timeout=0.01,  # 10ms socket timeout
                socket_connect_timeout=0.01,  # 10ms connection timeout
                health_check_interval=0,  # Disable health checks
            )

        return sliding_window_redis_check(
            self.redis_client, key, self.max_tests, self.window_seconds
        )

    def _check_rule_fallback(self, key: str) -> tuple[bool, int]:
        """Fallback in-memory sliding window (same logic as Redis version).

        Used when Redis unavailable. Per-process only (not distributed).
        Delegates to the shared hub_api.security.rate_limit.
        sliding_window_fallback_check.
        """
        return sliding_window_fallback_check(
            self._fallback_counters, key, self.max_tests, self.window_seconds
        )
