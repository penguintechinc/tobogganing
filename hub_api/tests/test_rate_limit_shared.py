"""Unit tests for hub_api/security/rate_limit.py.

Covers the shared sliding-window primitive (Redis + in-memory fallback),
the client_ip/hash_identifier helpers, and the rate_limited() Quart
decorator used to protect the auth-credential endpoints.

regression: no auth rate-limiting (security-audit 2026-09-21)

No live Redis is reachable in this environment (verified: connection to
localhost:6379 refused), so every SlidingWindowRateLimiter.is_allowed()
call below naturally exercises the in-memory fallback after the 10ms
Redis-connect timeout -- matching the existing live-test limiter tests'
approach (hub_api/tests/perftest/test_live_test_ratelimit_gaps.py).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from quart import Quart

from hub_api.security.rate_limit import (
    SlidingWindowRateLimiter,
    client_ip,
    hash_identifier,
    ip_key,
    rate_limited,
    sliding_window_fallback_check,
    sliding_window_redis_check,
)

# ---------------------------------------------------------------------------
# SlidingWindowRateLimiter.is_allowed (in-memory fallback path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allows_under_limit() -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    limiter = SlidingWindowRateLimiter(3, 60, "test_under")
    for i in range(3):
        allowed, retry_after = await limiter.is_allowed("k1")
        assert allowed is True, f"call {i + 1} should be allowed"
        assert retry_after == 0


@pytest.mark.asyncio
async def test_blocks_over_limit_with_positive_retry_after() -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    limiter = SlidingWindowRateLimiter(2, 60, "test_over")
    await limiter.is_allowed("k1")
    await limiter.is_allowed("k1")
    allowed, retry_after = await limiter.is_allowed("k1")
    assert allowed is False
    assert retry_after > 0


@pytest.mark.asyncio
async def test_independent_keys_have_independent_limits() -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- two
    different keys (e.g. two client IPs) are limited independently."""
    limiter = SlidingWindowRateLimiter(1, 60, "test_independent")
    allowed_a, _ = await limiter.is_allowed("ip-a")
    allowed_b, _ = await limiter.is_allowed("ip-b")
    assert allowed_a is True
    assert allowed_b is True

    blocked_a, _ = await limiter.is_allowed("ip-a")
    blocked_b, _ = await limiter.is_allowed("ip-b")
    assert blocked_a is False
    assert blocked_b is False


@pytest.mark.asyncio
async def test_redis_error_fails_open_to_in_memory_counter(monkeypatch: Any) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- a
    limiter-infra (Redis) failure fails open to the in-memory counter
    rather than raising or blocking the request."""
    limiter = SlidingWindowRateLimiter(2, 60, "test_redis_down")

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr("hub_api.security.rate_limit.sliding_window_redis_check", _boom)

    allowed, retry_after = await limiter.is_allowed("k1")
    assert allowed is True
    assert retry_after == 0
    assert limiter._redis_init_failed is True

    # Redis is now marked failed; subsequent calls skip it entirely and the
    # in-memory counter keeps counting correctly.
    allowed2, _ = await limiter.is_allowed("k1")
    assert allowed2 is True
    allowed3, retry_after3 = await limiter.is_allowed("k1")
    assert allowed3 is False
    assert retry_after3 > 0


@pytest.mark.asyncio
async def test_redis_timeout_fails_open_to_in_memory_counter(monkeypatch: Any) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- a
    slow Redis (exceeding the fixed timeout) also fails open."""
    limiter = SlidingWindowRateLimiter(5, 60, "test_redis_timeout")

    def _slow(*args: Any, **kwargs: Any) -> tuple[bool, int]:
        time.sleep(0.2)
        return True, 0

    monkeypatch.setattr("hub_api.security.rate_limit.sliding_window_redis_check", _slow)

    allowed, _ = await limiter.is_allowed("k1")
    assert allowed is True
    assert limiter._redis_init_failed is True


@pytest.mark.asyncio
async def test_redis_failure_latch_resets_after_cooldown(monkeypatch: Any) -> None:
    """regression (ops audit O4/O5): the fail-open latch must not stay
    permanently set. Before this fix, once Redis failed once, this
    process used the in-memory fallback for the rest of its life, even
    after Redis recovered -- desyncing rate-limit state from every other
    replica under N pods."""
    limiter = SlidingWindowRateLimiter(5, 60, "test_redis_recovery")

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr("hub_api.security.rate_limit.sliding_window_redis_check", _boom)
    await limiter.is_allowed("k1")
    assert limiter._redis_init_failed is True

    # Simulate the cooldown having elapsed and Redis becoming healthy again.
    limiter._failed_at = time.time() - 31
    healthy_calls: list[str] = []

    def _healthy(*args: Any, **kwargs: Any) -> tuple[bool, int]:
        healthy_calls.append(args[1])
        return True, 0

    monkeypatch.setattr("hub_api.security.rate_limit.sliding_window_redis_check", _healthy)

    allowed, retry_after = await limiter.is_allowed("k2")

    assert allowed is True
    assert retry_after == 0
    assert healthy_calls, "Redis should have been retried, not skipped"
    assert limiter._redis_init_failed is False


@pytest.mark.asyncio
async def test_redis_not_retried_before_cooldown_elapses(monkeypatch: Any) -> None:
    """A healthy-again Redis is not even probed until the cooldown elapses."""
    limiter = SlidingWindowRateLimiter(5, 60, "test_redis_too_soon")

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr("hub_api.security.rate_limit.sliding_window_redis_check", _boom)
    await limiter.is_allowed("k1")
    assert limiter._redis_init_failed is True

    healthy_calls: list[str] = []

    def _healthy(*args: Any, **kwargs: Any) -> tuple[bool, int]:
        healthy_calls.append(args[1])
        return True, 0

    monkeypatch.setattr("hub_api.security.rate_limit.sliding_window_redis_check", _healthy)

    await limiter.is_allowed("k2")

    assert not healthy_calls, "Redis should still be skipped before the cooldown elapses"
    assert limiter._redis_init_failed is True


# ---------------------------------------------------------------------------
# sliding_window_redis_check / sliding_window_fallback_check (direct)
# ---------------------------------------------------------------------------


def test_sliding_window_redis_check_allows_under_limit() -> None:
    mock_pipeline = MagicMock()
    mock_pipeline.execute = MagicMock(return_value=[None, 1, None])
    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    allowed, retry_after = sliding_window_redis_check(mock_redis, "rl:test:k", 2, 60)
    assert allowed is True
    assert retry_after == 0
    mock_redis.zadd.assert_called_once()


def test_sliding_window_redis_check_blocks_with_oldest_entry() -> None:
    mock_pipeline = MagicMock()
    mock_pipeline.execute = MagicMock(return_value=[None, 1, None])
    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    now = int(time.time())
    mock_redis.zrange = MagicMock(return_value=[("member", float(now - 10))])

    allowed, retry_after = sliding_window_redis_check(mock_redis, "rl:test:k", 1, 60)
    assert allowed is False
    assert retry_after > 0


def test_sliding_window_redis_check_uses_unique_member_per_call() -> None:
    """A bare-timestamp ZSET member would collide within the same wall-clock
    second and undercount concurrent requests -- verify each call adds a
    distinct member."""
    mock_pipeline = MagicMock()
    mock_pipeline.execute = MagicMock(return_value=[None, 0, None])
    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    sliding_window_redis_check(mock_redis, "rl:test:k", 5, 60)
    sliding_window_redis_check(mock_redis, "rl:test:k", 5, 60)

    members = [list(call.args[1].keys())[0] for call in mock_redis.zadd.call_args_list]
    assert len(members) == 2
    assert members[0] != members[1]


def test_sliding_window_redis_check_pipeline_exception_propagates() -> None:
    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(side_effect=RuntimeError("connection reset"))

    with pytest.raises(RuntimeError, match="connection reset"):
        sliding_window_redis_check(mock_redis, "rl:test:k", 1, 60)


def test_sliding_window_fallback_check_zero_max_blocks() -> None:
    counters: dict[str, deque[float]] = defaultdict(deque)
    allowed, retry_after = sliding_window_fallback_check(counters, "k", 0, 30)
    assert allowed is False
    assert retry_after == 30


def test_sliding_window_fallback_check_evicts_stale_entries() -> None:
    counters: dict[str, deque[float]] = defaultdict(deque)
    counters["k"] = deque([time.time() - 100])
    allowed, retry_after = sliding_window_fallback_check(counters, "k", 5, 10)
    assert allowed is True
    assert len(counters["k"]) == 1


# ---------------------------------------------------------------------------
# client_ip / hash_identifier
# ---------------------------------------------------------------------------


def _ip_app() -> Quart:
    app = Quart(__name__)

    @app.route("/ip")
    async def _ip() -> dict[str, Optional[str]]:
        return {"ip": client_ip()}

    return app


@pytest.mark.asyncio
async def test_client_ip_uses_rightmost_xff_entry_for_default_single_hop() -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) --
    with the default trust depth of 1 (one ingress hop), client_ip() takes
    the entry appended by that trusted proxy (rightmost), not the
    client-supplied leftmost one."""
    client = _ip_app().test_client()
    resp = await client.get("/ip", headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
    data = await resp.get_json()
    assert data["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_client_ip_ignores_spoofed_leftmost_entry(monkeypatch: Any) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- an
    attacker varying the leftmost (client-supplied) X-Forwarded-For entry
    every request must NOT change the derived key: only the entry
    appended by the trusted proxy (rightmost, for hops=1) may. Proves the
    leftmost-entry bug (client-spoofable, defeats IP keying entirely) is
    fixed."""
    monkeypatch.setattr("hub_api.security.rate_limit._TRUSTED_PROXY_HOPS", 1)
    client = _ip_app().test_client()

    first = await client.get("/ip", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.5"})
    second = await client.get("/ip", headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.5"})
    data_first = await first.get_json()
    data_second = await second.get_json()

    assert data_first["ip"] == "203.0.113.5"
    assert data_second["ip"] == "203.0.113.5"
    assert data_first["ip"] == data_second["ip"]


@pytest.mark.asyncio
async def test_client_ip_respects_configured_multi_hop_depth(monkeypatch: Any) -> None:
    """A deployment with two trusted proxies in front (hops=2) reads the
    second-from-right entry -- the one appended by the outermost trusted
    proxy, past however many entries the inner hop(s) also appended."""
    monkeypatch.setattr("hub_api.security.rate_limit._TRUSTED_PROXY_HOPS", 2)
    client = _ip_app().test_client()
    resp = await client.get("/ip", headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.5, 10.0.0.1"})
    data = await resp.get_json()
    assert data["ip"] == "203.0.113.5"


@pytest.mark.asyncio
async def test_client_ip_falls_back_when_xff_shorter_than_trust_depth(
    monkeypatch: Any,
) -> None:
    """If XFF has fewer entries than the configured trust depth (misconfig
    or a direct connection bypassing the expected proxy chain), fail safe
    to the ASGI-reported peer address rather than trusting an
    attacker-controlled entry."""
    monkeypatch.setattr("hub_api.security.rate_limit._TRUSTED_PROXY_HOPS", 3)
    client = _ip_app().test_client()
    resp = await client.get("/ip", headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.1"})
    data = await resp.get_json()
    assert data["ip"] != "203.0.113.5"  # never falls back to an attacker-controlled entry
    assert data["ip"]  # still non-empty (remote_addr fallback)


@pytest.mark.asyncio
async def test_client_ip_falls_back_to_remote_addr_without_xff() -> None:
    client = _ip_app().test_client()
    resp = await client.get("/ip")
    data = await resp.get_json()
    assert data["ip"]  # never empty/None -- falls back to the ASGI peer addr


def test_hash_identifier_deterministic_and_distinct() -> None:
    h1 = hash_identifier("alice@example.com")
    h2 = hash_identifier("alice@example.com")
    h3 = hash_identifier("bob@example.com")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16
    assert "alice" not in h1  # never store/log the raw identifier


# ---------------------------------------------------------------------------
# rate_limited() decorator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limited_decorator_returns_429_with_retry_after() -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    app = Quart(__name__)
    limiter = SlidingWindowRateLimiter(1, 60, "decorator_test_ip")

    @app.route("/protected", methods=["POST"])
    @rate_limited((limiter, ip_key), event="decorator_test")
    async def _protected() -> dict[str, bool]:
        return {"ok": True}

    client = app.test_client()
    first = await client.post("/protected", headers={"X-Forwarded-For": "1.2.3.4"})
    assert first.status_code == 200

    second = await client.post("/protected", headers={"X-Forwarded-For": "1.2.3.4"})
    assert second.status_code == 429
    assert "Retry-After" in second.headers
    body = await second.get_json()
    retry_after = int(second.headers["Retry-After"])
    assert body == {"error": "Rate limit exceeded", "retry_after": retry_after}


@pytest.mark.asyncio
async def test_rate_limited_decorator_skips_check_when_key_func_returns_none() -> None:
    """A key_func returning None (no identifier available) skips that check
    entirely rather than blocking every request."""
    app = Quart(__name__)
    limiter = SlidingWindowRateLimiter(1, 60, "decorator_skip_test")

    async def _no_key() -> Optional[str]:
        return None

    @app.route("/skip", methods=["POST"])
    @rate_limited((limiter, _no_key), event="decorator_skip")
    async def _skip() -> dict[str, bool]:
        return {"ok": True}

    client = app.test_client()
    for _ in range(5):
        resp = await client.post("/skip")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rate_limited_decorator_either_bucket_tripping_blocks_request() -> None:
    """Two independent checks (e.g. IP + account bucket): either one over
    its limit blocks the request, with an identical response shape
    regardless of which one tripped -- mirrors login's dual-bucket setup."""
    app = Quart(__name__)
    ip_limiter = SlidingWindowRateLimiter(100, 60, "multi_ip")
    acct_limiter = SlidingWindowRateLimiter(1, 60, "multi_acct")

    async def _acct_key() -> Optional[str]:
        return "acct-x"

    @app.route("/multi", methods=["POST"])
    @rate_limited((ip_limiter, ip_key), (acct_limiter, _acct_key), event="multi_test")
    async def _multi() -> dict[str, bool]:
        return {"ok": True}

    client = app.test_client()
    first = await client.post("/multi", headers={"X-Forwarded-For": "9.9.9.9"})
    assert first.status_code == 200

    # A different IP but the same account bucket is still blocked -- the
    # account check is independent of (and not bypassed by) the IP check.
    second = await client.post("/multi", headers={"X-Forwarded-For": "8.8.8.8"})
    assert second.status_code == 429
    body = await second.get_json()
    assert body["error"] == "Rate limit exceeded"
