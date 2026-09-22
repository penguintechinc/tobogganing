"""Shared Redis sliding-window rate limiter + Quart enforcement decorator.

Generalizes the ZSET sliding-window counter originally written for live-test
throttling (perftest_cluster/security/live_test_ratelimit.py, which now
delegates its counting logic to sliding_window_redis_check/
sliding_window_fallback_check below) so any caller can rate-limit on an
arbitrary string key, not just tenant_id. Used to protect the pre-auth /
machine-auth / public credential endpoints (login, refresh, logout, machine
token issue/refresh/validate, enrollment) against brute force -- see
security-audit 2026-09-21 finding Dim 3 (A04/A07).

Fails open on any Redis error or the fixed timeout: a limiter-infra failure
never blocks or 500s a request, it just falls back to an in-process per-key
deque counter (not distributed, best-effort) -- see security.md Client
graceful-degradation rule. This is an always-on security control: unlike
product features it is never gated behind a PostHog flag.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import redis
import structlog
from quart import jsonify, request

logger = structlog.get_logger()

_REDIS_CHECK_TIMEOUT_SECS = 0.05

# Dedicated Redis/Valkey db for all rate-limit ZSETs -- distinct from
# CacheClient's general-purpose cache (db=0, hub_api/cache/client.py) and
# the live-test limiter's original db (db=2, unchanged for backward
# compatibility). Same host/port/creds as CacheClient (CACHE_HOST/
# CACHE_PORT/CACHE_USER/CACHE_PASS) -- one Redis/Valkey instance, separate
# db namespaces per concern.
RATE_LIMIT_REDIS_DB = int(os.getenv("RATE_LIMIT_REDIS_DB", "3"))

# Number of trusted reverse-proxy hops between the client and this service --
# i.e. how many entries X-Forwarded-For accumulates before reaching an entry
# this service can actually trust. Default 1 matches security.md Kubernetes
# Network Security's single Ingress/Gateway API hop. See client_ip() below
# for why this must count from the RIGHT, never the left.
_TRUSTED_PROXY_HOPS = int(os.getenv("RATE_LIMIT_TRUSTED_PROXY_HOPS", "1"))


def sliding_window_redis_check(
    redis_client: redis.Redis,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """Sliding-window check+record against a Redis ZSET.

    Shared by SlidingWindowRateLimiter and (via a thin wrapper)
    LiveTestRateLimiter so both mechanisms use identical counting logic.
    The ZSET member is `{timestamp}-{random}` rather than a bare timestamp
    so multiple requests within the same wall-clock second are each
    recorded instead of colliding into a single ZADD (a bare-timestamp
    member would let same-second bursts undercount, weakening exactly the
    brute-force protection this exists for).
    """
    try:
        now = int(time.time())
        window_start = now - window_seconds

        pipeline = redis_client.pipeline()
        pipeline.zremrangebyscore(key, 0, window_start)
        pipeline.zcard(key)
        pipeline.expire(key, window_seconds)
        results = pipeline.execute()

        current_count = results[1]

        if current_count >= max_requests:
            oldest_entry = redis_client.zrange(key, 0, 0, withscores=True)
            if oldest_entry:
                oldest_time = int(oldest_entry[0][1])  # type: ignore[index]
                retry_after = window_seconds - (now - oldest_time)
                return False, max(retry_after, 1)
            return False, window_seconds

        redis_client.zadd(key, {f"{now}-{secrets.token_hex(4)}": now})
        return True, 0
    except Exception as e:
        logger.error("rate_limit_redis_error", error=str(e))
        raise


def sliding_window_fallback_check(
    counters: dict[str, deque[float]],
    key: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """In-memory (per-process, best-effort) sliding-window check+record.

    Same semantics as sliding_window_redis_check; used when Redis is
    unavailable.
    """
    now = time.time()
    counter = counters[key]
    while counter and counter[0] < now - window_seconds:
        counter.popleft()

    if len(counter) >= max_requests:
        if counter:
            retry_after = window_seconds - (now - counter[0])
            return False, max(int(retry_after), 1)
        return False, window_seconds

    counter.append(now)
    return True, 0


@dataclass(slots=True)
class SlidingWindowRateLimiter:
    """Generic Redis-ZSET sliding-window rate limiter, keyed by any string.

    Use one instance per logical bucket (e.g. "auth_login_ip",
    "enroll_secret") with its own max_requests/window_seconds, then call
    `is_allowed(key)` per request with the caller-derived identifier
    (client IP, hashed account/secret, etc.) as `key`.
    """

    max_requests: int
    window_seconds: int
    key_prefix: str
    redis_db: int = RATE_LIMIT_REDIS_DB
    redis_client: Optional[redis.Redis] = None
    _redis_init_failed: bool = False
    _fallback_counters: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    async def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check + record one request for `key`.

        Returns (allowed, retry_after_seconds); retry_after_seconds is 0
        when allowed. Never raises -- any Redis error/timeout fails open to
        the in-memory fallback and is logged at debug level, and Redis is
        skipped for the rest of this process's lifetime once it has failed
        once (matches LiveTestRateLimiter's existing behavior).
        """
        full_key = f"rl:{self.key_prefix}:{key}"

        if self._redis_init_failed:
            return sliding_window_fallback_check(
                self._fallback_counters, full_key, self.max_requests, self.window_seconds
            )

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    sliding_window_redis_check,
                    self._ensure_redis(),
                    full_key,
                    self.max_requests,
                    self.window_seconds,
                ),
                timeout=_REDIS_CHECK_TIMEOUT_SECS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            self._redis_init_failed = True
            logger.debug(
                "rate_limit_redis_unavailable",
                key_prefix=self.key_prefix,
                timeout=isinstance(e, asyncio.TimeoutError),
                error=str(e),
            )
            return sliding_window_fallback_check(
                self._fallback_counters, full_key, self.max_requests, self.window_seconds
            )

    def _ensure_redis(self) -> redis.Redis:
        """Lazy-init the Redis client with short fail-fast timeouts."""
        if self.redis_client is None:
            self.redis_client = redis.Redis(
                host=os.getenv("CACHE_HOST", "localhost"),
                port=int(os.getenv("CACHE_PORT", "6379")),
                db=self.redis_db,
                username=os.getenv("CACHE_USER"),
                password=os.getenv("CACHE_PASS"),
                decode_responses=True,
                socket_timeout=0.01,
                socket_connect_timeout=0.01,
                health_check_interval=0,
            )
        return self.redis_client


def client_ip() -> str:
    """Best-effort client IP for rate-limit keying, using a trusted-hop model.

    The LEFTMOST X-Forwarded-For entry is always attacker-controlled and
    must never be used for a security decision: nginx-ingress/Gateway API
    APPEND the peer IP they observe to whatever XFF the client already
    sent, so a client sending `X-Forwarded-For: 9.9.9.9` arrives at this
    app as `X-Forwarded-For: 9.9.9.9, <real-client-ip>` -- an attacker who
    rotates the leftmost entry every request gets a fresh rate-limit
    bucket each time, bypassing IP limiting entirely (and 4 of the 7
    IP-keyed endpoints here have no second bucket to fall back on).

    Instead this walks in from the RIGHT by RATE_LIMIT_TRUSTED_PROXY_HOPS
    (default 1, matching security.md Kubernetes Network Security's single
    Ingress/Gateway API hop -- this service is never directly
    internet-facing in beta/prod, no NodePort/HostPort/hostNetwork) --
    that entry is the one appended by the outermost *trusted* proxy, which
    only the proxy itself can set. Falls back to the ASGI-reported peer
    address when XFF is absent (local/dev/direct-connection testing) or
    doesn't have enough hops to satisfy the configured trust depth.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        hops = _TRUSTED_PROXY_HOPS
        if 0 < hops <= len(parts):
            return parts[-hops]
    return request.remote_addr or "unknown"


async def ip_key() -> Optional[str]:
    """Standard async rate-limit key func: the request's client IP.

    Reusable directly as a `rate_limited()` check for any endpoint that only
    needs an IP-scoped bucket (no body-derived account/secret bucket).
    """
    return client_ip()


def hash_identifier(value: str) -> str:
    """SHA-256 (truncated to 16 hex chars) of a sensitive identifier.

    Used to build rate-limit bucket keys from account identifiers, API
    keys, and enrollment secrets without ever storing or logging the raw
    value (security.md Token & Secret Hygiene) -- callers normalize (e.g.
    lowercase emails) before calling.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


RateLimitKeyFunc = Callable[[], Awaitable[Optional[str]]]
RateLimitCheck = tuple[SlidingWindowRateLimiter, RateLimitKeyFunc]


def rate_limited(
    *checks: RateLimitCheck, event: str
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator enforcing one or more sliding-window rate-limit checks.

    Each check is a (limiter, key_func) pair; key_func is awaited fresh per
    request to derive that check's bucket key (client IP, hashed account/
    secret identifier, etc.) -- return None to skip a check when no
    identifier is available for this request (e.g. malformed body). All
    checks are consulted in order; the first one over its limit wins and
    short-circuits the request with 429 + Retry-After, before the wrapped
    handler runs -- the response shape and status code are identical
    regardless of which bucket (IP vs account) tripped, so a caller cannot
    distinguish "account exists and is locked out" from "IP is rate
    limited" (security.md: differential limiting must not leak account
    existence). Never raises on limiter-infra failure
    (SlidingWindowRateLimiter.is_allowed always fails open).

    `event` names the structured log emitted on a 429 (metrics/traces for
    this signal are pending this app's own OTel SDK wiring -- a
    pre-existing gap, not introduced here; the structured log is the
    observable signal until that lands).
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            for limiter, key_func in checks:
                key = await key_func()
                if not key:
                    continue
                allowed, retry_after = await limiter.is_allowed(key)
                if not allowed:
                    # structlog's BoundLogger reserves `event` as the log
                    # message's own positional name -- passing our `event`
                    # (the rate-limit check name) as a same-named kwarg
                    # collides with it, so it's logged as `rl_event`.
                    logger.warning(
                        "rate_limit_exceeded",
                        rl_event=event,
                        bucket=limiter.key_prefix,
                        retry_after_secs=retry_after,
                    )
                    response = jsonify({"error": "Rate limit exceeded", "retry_after": retry_after})
                    response.headers["Retry-After"] = str(retry_after)
                    return response, 429
            return await func(*args, **kwargs)

        return wrapper

    return decorator
