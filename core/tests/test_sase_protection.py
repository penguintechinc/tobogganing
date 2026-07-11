"""Tests for SASE security protection module."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.modules.sase.security.protection import (
    DDoSProtection,
    RateLimitRuleData,
    RateLimiter,
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
    async def test_is_allowed_request(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
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
    async def test_is_allowed_blocked_ip(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
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

    def test_rule_applies_endpoint_match(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
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

    def test_rule_applies_exempt_ip(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Test rule exemption for specific IPs."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        rule = RateLimitRuleData(
            name="test_rule",
            max_requests=10,
            window_seconds=60,
            exempt_ips=["192.168.1.100"],
        )

        assert (
            limiter._rule_applies(rule, "/api/test", "192.168.1.100") is False
        )
        assert limiter._rule_applies(rule, "/api/test", "192.168.1.1") is True

    @pytest.mark.asyncio
    async def test_log_security_event(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
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

    def test_detect_no_attack(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Test detection returns no attack for normal traffic."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        is_attack, attack_type, severity = ddos.detect_ddos_attack(
            "192.168.1.1", "/api/normal", "Mozilla/5.0"
        )

        assert is_attack is False
        assert attack_type == ""
        assert severity == ""

    def test_detect_suspicious_pattern(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Test detection of suspicious request patterns."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        is_attack, attack_type, severity = ddos.detect_ddos_attack(
            "192.168.1.1", "/api/test.php", "Mozilla/5.0"
        )

        assert is_attack is True
        assert "pattern" in attack_type
        assert severity in ["low", "medium", "high", "critical"]

    def test_check_volume_attack(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Test volume-based attack detection."""
        limiter = RateLimiter(db=mock_db, redis_client=mock_redis)
        ddos = DDoSProtection(rate_limiter=limiter, redis_client=mock_redis)

        # Setup mock to return high request count
        mock_redis.zcard.return_value = 1500

        result = ddos._check_volume_attack("192.168.1.1")

        assert result is True

    def test_mitigate_attack(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
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
    async def test_process_allowed_request(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
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

    def test_unblock_ip_through_middleware(
        self, mock_db: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Test unblocking an IP through middleware."""
        middleware = SecurityMiddleware(db=mock_db, redis_client=mock_redis)
        middleware.rate_limiter._block_ip("192.168.1.1", 300)

        result = middleware.unblock_ip("192.168.1.1")

        assert result is True
        assert len(middleware.get_blocked_ips()) == 0
