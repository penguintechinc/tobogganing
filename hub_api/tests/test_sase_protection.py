"""Tests for SASE security protection module."""

from __future__ import annotations

import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.modules.sase.security.protection import (
    DDoSProtection,
    RateLimiter,
    RateLimitRuleData,
    SecurityMiddleware,
)


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock penguin-dal database instance supporting async operations."""
    db = MagicMock()

    # Sync session operations (legacy)
    db.session = MagicMock()
    db.query = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    # Async table operations (new async DAL API)
    table_mock = AsyncMock()
    table_mock.async_insert = AsyncMock(return_value=1)
    db.security_events = table_mock
    db.rate_limit_rules = table_mock

    # Async query operations: db(query).select()
    query_result = AsyncMock()
    query_result.select = AsyncMock(return_value=[])
    db.return_value = query_result
    db.__call__ = MagicMock(return_value=query_result)

    return db


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create a mock Redis client."""
    redis_client = MagicMock()
    redis_client.pipeline.return_value.__enter__.return_value.execute.return_value = [
        None,
        0,
    ]
    redis_client.zcard.return_value = 0
    redis_client.zrange.return_value = []
    redis_client.zadd.return_value = 1
    redis_client.expire.return_value = True
    redis_client.zremrangebyscore.return_value = 0
    redis_client.scard.return_value = 5
    redis_client.lrange.return_value = []
    redis_client.lpush.return_value = 1
    redis_client.ltrim.return_value = True
    return redis_client


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_rate_limiter_init(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test RateLimiter initialization."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        assert limiter.db == mock_db
        assert limiter.redis_client == mock_redis
        assert len(limiter.rules) > 0
        assert limiter.blocked_ips == set()

    @pytest.mark.asyncio
    async def test_is_allowed_request(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test allowing a request within rate limits."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)

        # Setup mock redis to return low request count
        pipeline_mock = MagicMock()
        pipeline_mock.__enter__.return_value.execute.return_value = [None, 1]
        mock_redis.pipeline.return_value = pipeline_mock

        allowed, rule, retry_after = await limiter.is_allowed(
            "192.168.1.1", "/api/test", "Mozilla/5.0"
        )

        assert allowed is True
        assert rule is None
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_is_allowed_blocked_ip(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test that blocked IPs are denied."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)

        # Manually block an IP
        limiter._block_ip("192.168.1.1", 300)

        allowed, rule, retry_after = await limiter.is_allowed(
            "192.168.1.1", "/api/test", "Mozilla/5.0"
        )

        assert allowed is False
        assert retry_after > 0

    def test_block_ip(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test blocking an IP address."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        limiter._block_ip("192.168.1.1", 300)

        assert "192.168.1.1" in limiter.blocked_ips
        assert "192.168.1.1" in limiter.blocked_until
        mock_redis.setex.assert_called_once()

    def test_unblock_ip(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test unblocking an IP address."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        limiter._block_ip("192.168.1.1", 300)

        result = limiter.unblock_ip("192.168.1.1")

        assert result is True
        assert "192.168.1.1" not in limiter.blocked_ips
        mock_redis.delete.assert_called_with("blocked_ip:192.168.1.1")

    def test_get_blocked_ips(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test retrieving list of blocked IPs."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        limiter._block_ip("192.168.1.1", 300)
        limiter._block_ip("192.168.1.2", 600)

        blocked = limiter.get_blocked_ips()

        assert len(blocked) == 2
        assert any(ip["ip_address"] == "192.168.1.1" for ip in blocked)
        assert any(ip["ip_address"] == "192.168.1.2" for ip in blocked)

    def test_rule_applies_endpoint_match(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test rule application with endpoint matching."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(
            name="test_rule",
            max_requests=10,
            window_seconds=60,
            endpoints=["/api/test"],
        )

        assert limiter._rule_applies(rule, "/api/test/123", "192.168.1.1") is True
        assert limiter._rule_applies(rule, "/other/endpoint", "192.168.1.1") is False

    def test_rule_applies_exempt_ip(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test rule exemption for specific IPs."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(
            name="test_rule",
            max_requests=10,
            window_seconds=60,
            exempt_ips=["192.168.1.100"],
        )

        assert limiter._rule_applies(rule, "/api/test", "192.168.1.100") is False
        assert limiter._rule_applies(rule, "/api/test", "192.168.1.1") is True

    @pytest.mark.asyncio
    async def test_log_security_event(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test logging security events."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        await limiter._log_security_event(
            "test_event",
            "192.168.1.1",
            "/api/test",
            "Mozilla/5.0",
            "medium",
            {"test": "data"},
        )

        # Verify async insert was called on security_events table
        mock_db.security_events.async_insert.assert_called_once()


class TestDDoSProtection:
    """Tests for DDoSProtection class."""

    def test_ddos_init(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test DDoSProtection initialization."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        assert ddos.rate_limiter == limiter
        assert ddos.redis_client == mock_redis
        assert ddos.request_threshold == 1000

    def test_detect_no_attack(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test detection returns no attack for normal traffic."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        is_attack, attack_type, severity = ddos.detect_ddos_attack(
            "192.168.1.1", "/api/normal", "Mozilla/5.0"
        )

        assert is_attack is False
        assert attack_type == ""
        assert severity == ""

    def test_detect_suspicious_pattern(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test detection of suspicious request patterns."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        is_attack, attack_type, severity = ddos.detect_ddos_attack(
            "192.168.1.1", "/api/test.php", "Mozilla/5.0"
        )

        assert is_attack is True
        assert "pattern" in attack_type
        assert severity in ["low", "medium", "high", "critical"]

    def test_check_volume_attack(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test volume-based attack detection."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        # Setup mock to return high request count
        mock_redis.zcard.return_value = 1500

        result = ddos._check_volume_attack("192.168.1.1")

        assert result is True

    def test_mitigate_attack(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test attack mitigation."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        ddos.mitigate_attack("192.168.1.1", "volume", "high")

        # Verify IP was blocked (core DDoS mitigation behavior preserved)
        assert "192.168.1.1" in limiter.blocked_ips


class TestSecurityMiddleware:
    """Tests for SecurityMiddleware class."""

    def test_middleware_init(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test SecurityMiddleware initialization."""
        middleware = SecurityMiddleware(db=mock_db, redis_client=mock_redis)

        assert middleware.db == mock_db
        assert middleware.rate_limiter is not None
        assert middleware.ddos_protection is not None

    @pytest.mark.asyncio
    async def test_process_allowed_request(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test processing an allowed request."""
        middleware = SecurityMiddleware(db=mock_db, redis_client=mock_redis)

        # Setup mock redis to allow request
        pipeline_mock = MagicMock()
        pipeline_mock.__enter__.return_value.execute.return_value = [None, 1]
        mock_redis.pipeline.return_value = pipeline_mock

        allowed, headers = await middleware.process_request(
            {
                "ip_address": "192.168.1.1",
                "endpoint": "/api/normal",
                "user_agent": "Mozilla/5.0",
            }
        )

        assert allowed is True
        assert "X-RateLimit-Remaining" in headers

    @pytest.mark.asyncio
    async def test_process_rate_limited_request(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Test processing a rate-limited request."""
        middleware = SecurityMiddleware(db=mock_db, redis_client=mock_redis)

        # Block the IP first
        middleware.rate_limiter._block_ip("192.168.1.1", 300)

        allowed, headers = await middleware.process_request(
            {
                "ip_address": "192.168.1.1",
                "endpoint": "/api/test",
                "user_agent": "Mozilla/5.0",
            }
        )

        assert allowed is False
        assert headers["X-RateLimit-Remaining"] == "0"
        assert "Retry-After" in headers

    def test_get_blocked_ips(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test retrieving blocked IPs through middleware."""
        middleware = SecurityMiddleware(db=mock_db, redis_client=mock_redis)
        middleware.rate_limiter._block_ip("192.168.1.1", 300)

        blocked = middleware.get_blocked_ips()

        assert len(blocked) == 1
        assert blocked[0]["ip_address"] == "192.168.1.1"

    def test_unblock_ip_through_middleware(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """Test unblocking an IP through middleware."""
        middleware = SecurityMiddleware(db=mock_db, redis_client=mock_redis)
        middleware.rate_limiter._block_ip("192.168.1.1", 300)

        result = middleware.unblock_ip("192.168.1.1")

        assert result is True
        assert len(middleware.get_blocked_ips()) == 0


class TestRateLimiterCoverageGaps:
    """Targeted tests for RateLimiter branches not exercised above."""

    @pytest.mark.asyncio
    async def test_load_custom_rules_appends_and_resorts(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """load_custom_rules appends DB-backed rules and re-sorts by priority."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis, tenant_id="tenant-x")
        before = len(limiter.rules)

        custom_row = MagicMock()
        custom_row.name = "custom_rule"
        custom_row.max_requests = 42
        custom_row.window_seconds = 30
        custom_row.block_duration = 120
        custom_row.endpoints = ["/custom/"]
        custom_row.exempt_ips = None
        custom_row.priority = 0

        query_result = AsyncMock()
        query_result.select = AsyncMock(return_value=[custom_row])
        mock_db.return_value = query_result

        await limiter.load_custom_rules()

        assert len(limiter.rules) == before + 1
        assert limiter.rules[0].name == "custom_rule"  # priority 0 sorts first

    @pytest.mark.asyncio
    async def test_load_custom_rules_swallows_db_exception(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """load_custom_rules logs and swallows exceptions from the DB query."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        before = list(limiter.rules)
        mock_db.side_effect = RuntimeError("query failed")

        await limiter.load_custom_rules()  # must not raise

        assert limiter.rules == before

    def test_check_rule_within_limit_adds_request(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_check_rule allows the request and records it when under the limit."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(name="under", max_requests=5, window_seconds=60)

        pipeline_mock = MagicMock()
        pipeline_mock.execute.return_value = [None, 2]
        mock_redis.pipeline.return_value = pipeline_mock

        allowed, retry_after = limiter._check_rule(rule, "1.1.1.1", "/x")

        assert allowed is True
        assert retry_after == 0
        mock_redis.zadd.assert_called()

    def test_check_rule_exceeded_with_oldest_entry(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_check_rule denies and computes retry_after from the oldest window entry."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(name="over", max_requests=3, window_seconds=60)

        pipeline_mock = MagicMock()
        pipeline_mock.execute.return_value = [None, 10]
        mock_redis.pipeline.return_value = pipeline_mock
        now = int(time.time())
        mock_redis.zrange.return_value = [(str(now - 5), now - 5)]

        allowed, retry_after = limiter._check_rule(rule, "1.1.1.2", "/x")

        assert allowed is False
        assert retry_after >= 1

    def test_check_rule_exceeded_without_oldest_entry(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_check_rule falls back to the full window when no oldest entry is found."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(name="over2", max_requests=3, window_seconds=45)

        pipeline_mock = MagicMock()
        pipeline_mock.execute.return_value = [None, 10]
        mock_redis.pipeline.return_value = pipeline_mock
        mock_redis.zrange.return_value = []

        allowed, retry_after = limiter._check_rule(rule, "1.1.1.3", "/x")

        assert allowed is False
        assert retry_after == 45

    def test_fallback_rate_limit_purges_stale_and_allows(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_fallback_rate_limit purges stale entries and allows a fresh request."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(name="fb", max_requests=5, window_seconds=1)
        ip = "9.9.9.7"
        key = f"{rule.name}:{ip}"
        limiter._fallback_counters = {key: deque([time.time() - 100])}

        allowed, retry_after = limiter._fallback_rate_limit(rule, ip, "/x")

        assert allowed is True
        assert retry_after == 0
        assert len(limiter._fallback_counters[key]) == 1  # stale entry purged

    def test_fallback_rate_limit_denies_over_limit(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_fallback_rate_limit denies once the in-memory counter hits max_requests."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(name="fb2", max_requests=2, window_seconds=60)
        ip = "9.9.9.8"

        limiter._fallback_rate_limit(rule, ip, "/x")
        limiter._fallback_rate_limit(rule, ip, "/x")
        allowed, retry_after = limiter._fallback_rate_limit(rule, ip, "/x")

        assert allowed is False
        assert retry_after >= 1

    @pytest.mark.asyncio
    async def test_is_allowed_violation_blocks_and_logs(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """is_allowed blocks the IP and logs a security event on violation."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)

        pipeline_mock = MagicMock()
        pipeline_mock.execute.return_value = [None, 999]  # far over any rule's limit
        mock_redis.pipeline.return_value = pipeline_mock
        mock_redis.zrange.return_value = []

        allowed, rule, retry_after = await limiter.is_allowed("2.2.2.2", "/login", "Mozilla/5.0")

        assert allowed is False
        assert rule is not None
        assert retry_after >= 1
        assert "2.2.2.2" in limiter.blocked_ips
        mock_db.security_events.async_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_allowed_violation_log_failure_still_blocks(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """is_allowed still returns denied even if security-event logging raises."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        limiter._log_security_event = AsyncMock(side_effect=RuntimeError("log down"))

        pipeline_mock = MagicMock()
        pipeline_mock.execute.return_value = [None, 999]
        mock_redis.pipeline.return_value = pipeline_mock
        mock_redis.zrange.return_value = []

        allowed, rule, retry_after = await limiter.is_allowed("2.2.2.3", "/login", "Mozilla/5.0")

        assert allowed is False
        assert rule is not None

    def test_is_ip_blocked_expired_entry_is_cleared(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_is_ip_blocked clears stale block state once the timeout has passed."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        limiter.blocked_ips.add("6.6.6.6")
        limiter.blocked_until["6.6.6.6"] = time.time() - 10

        result = limiter._is_ip_blocked("6.6.6.6")

        assert result is False
        assert "6.6.6.6" not in limiter.blocked_until
        assert "6.6.6.6" not in limiter.blocked_ips

    def test_block_ip_redis_exception_still_blocks_in_memory(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_block_ip keeps the in-memory block even if Redis persistence fails."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        mock_redis.setex.side_effect = RuntimeError("redis down")

        limiter._block_ip("5.5.5.5", 100)

        assert "5.5.5.5" in limiter.blocked_ips

    def test_rule_applies_cidr_exempt(self, mock_db: MagicMock, mock_redis: MagicMock) -> None:
        """_rule_applies exempts an IP that falls within a CIDR range."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(
            name="cidr", max_requests=1, window_seconds=1, exempt_ips=["10.0.0.0/8"]
        )

        assert limiter._rule_applies(rule, "/api/test", "10.1.2.3") is False

    def test_rule_applies_invalid_ip_format_swallowed(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_rule_applies swallows a malformed IP and falls through to endpoint check."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(
            name="badip",
            max_requests=1,
            window_seconds=1,
            exempt_ips=["10.0.0.0/8"],
            endpoints=None,
        )

        assert limiter._rule_applies(rule, "/whatever", "not-an-ip") is True

    @pytest.mark.asyncio
    async def test_log_security_event_db_exception_swallowed(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_log_security_event logs and swallows DB insert failures."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        mock_db.security_events.async_insert = AsyncMock(side_effect=RuntimeError("db down"))

        await limiter._log_security_event(
            "evt", "1.2.3.4", "/x", "UA", "high", {"a": 1}
        )  # must not raise

    def test_unblock_ip_not_blocked_returns_false(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """unblock_ip returns False for an IP that was never blocked."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)

        assert limiter.unblock_ip("7.7.7.7") is False

    def test_unblock_ip_redis_exception_still_returns_false_path(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """unblock_ip logs and swallows Redis delete failures."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        limiter._block_ip("8.8.8.8", 300)
        mock_redis.delete.side_effect = RuntimeError("redis down")

        result = limiter.unblock_ip("8.8.8.8")

        # Exception is swallowed after logging; falls through to `return False`
        assert result is False
        # In-memory state was already cleared before the Redis call
        assert "8.8.8.8" not in limiter.blocked_until


class TestDDoSProtectionCoverageGaps:
    """Targeted tests for DDoSProtection branches not exercised above."""

    def test_check_suspicious_patterns_user_agent_match(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """A suspicious user-agent (e.g. a scanner) triggers pattern detection."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        assert ddos._check_suspicious_patterns("/normal/path", "sqlmap/1.0") is True

    def test_check_suspicious_patterns_none_match(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Benign endpoint and user-agent produce no pattern match."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        assert ddos._check_suspicious_patterns("/normal/path", "Mozilla/5.0") is False

    def test_check_behavioral_anomaly_many_unique_endpoints(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Accessing many distinct endpoints trips the behavioral anomaly check."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.scard.return_value = 25  # over the 20-endpoint threshold

        assert ddos._check_behavioral_anomaly("3.3.3.3", "/api/x") is True

    def test_check_behavioral_anomaly_regular_timing(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Suspiciously regular request timing (low variance) reads as bot-like."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.scard.return_value = 1  # below endpoint-count threshold

        now = time.time()
        # Evenly spaced timestamps -> near-zero variance, tight interval < 2s
        mock_redis.lrange.return_value = [now - i for i in (1, 2, 3, 4, 5)]

        assert ddos._check_behavioral_anomaly("3.3.3.4", "/api/x") is True

    def test_check_behavioral_anomaly_redis_exception(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Redis failures during behavioral analysis are swallowed (fail-open)."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.sadd.side_effect = RuntimeError("redis down")

        assert ddos._check_behavioral_anomaly("3.3.3.5", "/api/x") is False

    def test_check_distributed_attack_over_threshold(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """More than 50 unique IPs in the window reads as a distributed attack."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.zcard.return_value = 75

        assert ddos._check_distributed_attack() is True

    def test_check_distributed_attack_redis_exception(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Redis failures during distributed-attack checks are swallowed."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.zremrangebyscore.side_effect = RuntimeError("redis down")

        assert ddos._check_distributed_attack() is False

    def test_mitigate_attack_critical_enables_emergency_mode(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Critical-severity attacks flip on emergency mode via Redis."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        ddos.mitigate_attack("4.4.4.4", "distributed", "critical")

        mock_redis.setex.assert_any_call("emergency_mode", 3600, "1")

    def test_enable_emergency_mode_redis_exception_swallowed(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_enable_emergency_mode logs and swallows Redis failures."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.setex.side_effect = RuntimeError("redis down")

        ddos._enable_emergency_mode()  # must not raise

    def test_detect_ddos_attack_volume_only_high_severity(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """detect_ddos_attack surfaces a volume indicator at 'high' severity."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        def zcard_side_effect(key: str, *a: object, **kw: object) -> int:
            return 1500 if key.startswith("ddos_volume:") else 0

        mock_redis.zcard.side_effect = zcard_side_effect

        is_attack, attack_type, severity = ddos.detect_ddos_attack(
            "1.2.3.4", "/normal", "Mozilla/5.0"
        )

        assert is_attack is True
        assert "volume" in attack_type
        assert severity == "high"

    def test_detect_ddos_attack_distributed_critical_severity(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """detect_ddos_attack surfaces a distributed indicator at 'critical' severity."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        def zcard_side_effect(key: str, *a: object, **kw: object) -> int:
            return 75 if key == "ddos_distributed:ips" else 0

        mock_redis.zcard.side_effect = zcard_side_effect

        is_attack, attack_type, severity = ddos.detect_ddos_attack(
            "1.2.3.5", "/normal", "Mozilla/5.0"
        )

        assert is_attack is True
        assert "distributed" in attack_type
        assert severity == "critical"

    def test_detect_ddos_attack_behavioral_indicator(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """detect_ddos_attack surfaces a behavioral indicator."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.scard.return_value = 25  # over the endpoint-diversity threshold

        is_attack, attack_type, severity = ddos.detect_ddos_attack(
            "1.2.3.6", "/normal", "Mozilla/5.0"
        )

        assert is_attack is True
        assert "behavioral" in attack_type

    def test_check_volume_attack_redis_exception(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """_check_volume_attack swallows Redis failures and reports no attack."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)
        mock_redis.zremrangebyscore.side_effect = RuntimeError("redis down")

        assert ddos._check_volume_attack("1.1.1.9") is False

    def test_check_suspicious_patterns_endpoint_regex_exception(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """A non-string endpoint raises inside re.search and is swallowed per-pattern."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        # None is not a valid re.search subject -> TypeError caught per pattern
        assert ddos._check_suspicious_patterns(None, "Mozilla/5.0") is False  # type: ignore[arg-type]

    def test_check_suspicious_patterns_ua_regex_exception(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """A non-string user-agent raises inside re.search and is swallowed per-pattern."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        assert ddos._check_suspicious_patterns("/normal", None) is False  # type: ignore[arg-type]


class TestSecurityMiddlewareCoverageGaps:
    """Targeted tests for SecurityMiddleware branches not exercised above."""

    @pytest.mark.asyncio
    async def test_process_request_ddos_detected_blocks(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """process_request blocks and returns DDoS headers when an attack is detected."""
        middleware = SecurityMiddleware(db=mock_db, redis_client=mock_redis)

        pipeline_mock = MagicMock()
        pipeline_mock.execute.return_value = [None, 1]  # well under any rule's limit
        mock_redis.pipeline.return_value = pipeline_mock

        allowed, headers = await middleware.process_request(
            {
                "ip_address": "9.1.1.1",
                "endpoint": "/api/test.php",  # matches DDoS suspicious-pattern regex
                "user_agent": "Mozilla/5.0",
            }
        )

        assert allowed is False
        assert headers["X-Security-Block"] == "DDoS-Protection"
        assert "pattern" in headers["X-Block-Reason"]
        assert "9.1.1.1" in middleware.rate_limiter.blocked_ips
