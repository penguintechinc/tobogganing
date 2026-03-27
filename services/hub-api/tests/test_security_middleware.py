"""
Tests for security/__init__.py and security/middleware.py —
RateLimiter, DDoS protection, emergency mode, security stats.

security/__init__.py calls get_db() at module level (inside SecurityMiddleware.__init__
and RateLimiter.__init__). We must patch 'database.get_db' and 'py4web' before the
first import.
"""
import sys
import time
from dataclasses import is_dataclass
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Patch py4web (not installed) and database before importing security modules.
_mock_db_for_security = MagicMock()
_mock_db_for_security.tables = []

if "py4web" not in sys.modules:
    sys.modules["py4web"] = MagicMock()

if "security" not in sys.modules:
    with patch("database.get_db", return_value=_mock_db_for_security), \
         patch("database.initialize_database", return_value=None):
        import security as _security_module
        from security import RateLimitRule, SecurityEvent, RateLimiter
else:
    from security import RateLimitRule, SecurityEvent, RateLimiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis_sync():
    """Synchronous Redis mock for security/__init__.py (uses redis, not aioredis)."""
    r = MagicMock()
    r.get = MagicMock(return_value=None)
    r.set = MagicMock(return_value=True)
    r.setex = MagicMock(return_value=True)
    r.delete = MagicMock(return_value=1)
    r.exists = MagicMock(return_value=0)
    r.keys = MagicMock(return_value=[])
    r.incr = MagicMock(return_value=1)
    r.expire = MagicMock(return_value=True)
    pipe_mock = MagicMock()
    pipe_mock.__enter__ = MagicMock(return_value=MagicMock(
        incr=MagicMock(return_value=None),
        expire=MagicMock(return_value=None),
        execute=MagicMock(return_value=[1, True]),
    ))
    pipe_mock.__exit__ = MagicMock(return_value=False)
    r.pipeline = MagicMock(return_value=pipe_mock)
    return r


@pytest.fixture
def rate_limiter(mock_redis_sync, mock_db):
    """RateLimiter with mocked Redis and DB."""
    with patch("database.get_db", return_value=mock_db):
        limiter = RateLimiter(redis_client=mock_redis_sync)
        return limiter


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestRateLimitRule:
    def test_rate_limit_rule_is_dataclass(self):
        assert is_dataclass(RateLimitRule)

    def test_default_block_duration(self):
        rule = RateLimitRule(name="test", max_requests=100, window_seconds=60)
        assert rule.block_duration == 300

    def test_default_priority(self):
        rule = RateLimitRule(name="test", max_requests=100, window_seconds=60)
        assert rule.priority == 10

    def test_custom_values(self):
        rule = RateLimitRule(
            name="strict",
            max_requests=5,
            window_seconds=10,
            block_duration=600,
            priority=1,
        )
        assert rule.max_requests == 5
        assert rule.window_seconds == 10


class TestSecurityEvent:
    def test_security_event_is_dataclass(self):
        assert is_dataclass(SecurityEvent)

    def test_security_event_fields(self):
        import dataclasses
        fields = {f.name for f in dataclasses.fields(SecurityEvent)}
        assert "event_type" in fields
        assert "ip_address" in fields
        assert "severity" in fields


# ---------------------------------------------------------------------------
# RateLimiter initialization
# ---------------------------------------------------------------------------

class TestRateLimiterInit:
    def test_limiter_has_rules(self, rate_limiter):
        assert hasattr(rate_limiter, "rules")
        assert isinstance(rate_limiter.rules, list)

    def test_limiter_has_blocked_ips(self, rate_limiter):
        assert hasattr(rate_limiter, "blocked_ips") or hasattr(rate_limiter, "blocked_until")

    def test_limiter_has_redis_client(self, rate_limiter):
        assert rate_limiter.redis_client is not None

    def test_limiter_default_rules_populated(self, rate_limiter):
        assert len(rate_limiter.rules) > 0


# ---------------------------------------------------------------------------
# is_allowed (the actual API — not is_ip_blocked or check_rate_limit)
# ---------------------------------------------------------------------------

class TestIsAllowed:
    def test_is_allowed_returns_tuple(self, rate_limiter, mock_redis_sync):
        mock_redis_sync.get = MagicMock(return_value=None)
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[1, True])
        pipe_mock.__enter__ = MagicMock(return_value=pipe_mock)
        pipe_mock.__exit__ = MagicMock(return_value=False)
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)

        result = rate_limiter.is_allowed(
            ip_address="10.0.0.1",
            endpoint="/api/v1/health",
            user_agent="TestAgent/1.0",
        )
        assert isinstance(result, tuple) and len(result) == 3

    def test_is_allowed_non_blocked_ip(self, rate_limiter, mock_redis_sync):
        mock_redis_sync.get = MagicMock(return_value=None)
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[1, True])
        pipe_mock.__enter__ = MagicMock(return_value=pipe_mock)
        pipe_mock.__exit__ = MagicMock(return_value=False)
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)

        allowed, rule, remaining = rate_limiter.is_allowed("10.0.0.1", "/api/v1/health")
        assert allowed is True

    def test_is_allowed_returns_bool_allowed(self, rate_limiter, mock_redis_sync):
        mock_redis_sync.get = MagicMock(return_value=None)
        pipe_mock = MagicMock()
        # High count simulates rate limit exceeded
        pipe_mock.execute = MagicMock(return_value=[1000, True])
        pipe_mock.__enter__ = MagicMock(return_value=pipe_mock)
        pipe_mock.__exit__ = MagicMock(return_value=False)
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)

        allowed, _, _ = rate_limiter.is_allowed("10.0.0.1", "/api/v1/auth/token")
        assert isinstance(allowed, bool)


# ---------------------------------------------------------------------------
# _is_ip_blocked (private method)
# ---------------------------------------------------------------------------

class TestIsIPBlockedPrivate:
    def test_unknown_ip_not_blocked(self, rate_limiter):
        result = rate_limiter._is_ip_blocked("10.0.0.1")
        assert result is False

    def test_blocked_ip_returns_true(self, rate_limiter):
        rate_limiter.blocked_ips.add("192.168.1.1")
        rate_limiter.blocked_until["192.168.1.1"] = time.time() + 9999
        result = rate_limiter._is_ip_blocked("192.168.1.1")
        assert result is True

    def test_expired_block_is_cleared(self, rate_limiter):
        rate_limiter.blocked_ips.add("10.10.10.10")
        rate_limiter.blocked_until["10.10.10.10"] = time.time() - 1
        result = rate_limiter._is_ip_blocked("10.10.10.10")
        assert result is False


# ---------------------------------------------------------------------------
# get_blocked_ips
# ---------------------------------------------------------------------------

class TestGetBlockedIPs:
    def test_get_blocked_ips_returns_list(self, rate_limiter):
        result = rate_limiter.get_blocked_ips()
        assert isinstance(result, list)

    def test_blocked_ip_appears_in_list(self, rate_limiter):
        rate_limiter.blocked_ips.add("9.9.9.9")
        rate_limiter.blocked_until["9.9.9.9"] = time.time() + 300
        result = rate_limiter.get_blocked_ips()
        # Result is list of dicts
        ips = [item["ip"] if isinstance(item, dict) else item for item in result]
        assert "9.9.9.9" in ips

    def test_get_blocked_ips_empty_when_none_blocked(self, rate_limiter):
        rate_limiter.blocked_ips.clear()
        rate_limiter.blocked_until.clear()
        result = rate_limiter.get_blocked_ips()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# EmergencyModeHandler (from middleware.py)
# ---------------------------------------------------------------------------

class TestEmergencyModeHandler:
    def test_is_emergency_mode_false_when_no_key(self):
        from security.middleware import EmergencyModeHandler

        mock_ddos = MagicMock()
        mock_ddos.redis_client.exists = MagicMock(return_value=0)

        with patch("security.middleware.security_middleware") as mock_sm:
            mock_sm.ddos_protection = mock_ddos
            result = EmergencyModeHandler.is_emergency_mode()
            assert result is False

    def test_is_emergency_mode_true_when_key_exists(self):
        from security.middleware import EmergencyModeHandler

        mock_ddos = MagicMock()
        mock_ddos.redis_client.exists = MagicMock(return_value=1)

        with patch("security.middleware.security_middleware") as mock_sm:
            mock_sm.ddos_protection = mock_ddos
            result = EmergencyModeHandler.is_emergency_mode()
            assert result is True

    def test_enable_emergency_mode_calls_setex(self):
        from security.middleware import EmergencyModeHandler

        mock_ddos = MagicMock()
        mock_ddos.redis_client.setex = MagicMock(return_value=True)

        with patch("security.middleware.security_middleware") as mock_sm:
            mock_sm.ddos_protection = mock_ddos
            EmergencyModeHandler.enable_emergency_mode(duration=3600)
            mock_ddos.redis_client.setex.assert_called_once_with("emergency_mode", 3600, "1")

    def test_disable_emergency_mode_calls_delete(self):
        from security.middleware import EmergencyModeHandler

        mock_ddos = MagicMock()
        mock_ddos.redis_client.delete = MagicMock(return_value=1)

        with patch("security.middleware.security_middleware") as mock_sm:
            mock_sm.ddos_protection = mock_ddos
            EmergencyModeHandler.disable_emergency_mode()
            mock_ddos.redis_client.delete.assert_called_once_with("emergency_mode")


# ---------------------------------------------------------------------------
# get_security_stats
# ---------------------------------------------------------------------------

class TestGetSecurityStats:
    def test_get_security_stats_returns_dict(self):
        from security.middleware import get_security_stats

        mock_sm = MagicMock()
        mock_sm.rate_limiter.get_blocked_ips.return_value = []
        mock_sm.rate_limiter.rules = []
        mock_sm.ddos_protection.redis_client.exists.return_value = 0

        with patch("security.middleware.security_middleware", mock_sm):
            result = get_security_stats()
            assert isinstance(result, dict)
            assert "blocked_ips_count" in result

    def test_get_security_stats_handles_redis_error(self):
        from security.middleware import get_security_stats

        mock_sm = MagicMock()
        mock_sm.rate_limiter.get_blocked_ips.side_effect = Exception("redis down")

        with patch("security.middleware.security_middleware", mock_sm):
            result = get_security_stats()
            assert isinstance(result, dict)
            assert "error" in result or "blocked_ips_count" in result


# ---------------------------------------------------------------------------
# handle_security_incident
# ---------------------------------------------------------------------------

class TestHandleSecurityIncident:
    def test_handle_rate_limit_violation(self):
        from security.middleware import handle_security_incident

        mock_sm = MagicMock()
        with patch("security.middleware.security_middleware", mock_sm):
            try:
                handle_security_incident(
                    "rate_limit_violation",
                    {"ip": "1.2.3.4", "endpoint": "/api/v1/test"},
                )
            except Exception as exc:
                pytest.fail(f"handle_security_incident raised: {exc}")

    def test_handle_ddos_attack_triggers_emergency(self):
        from security.middleware import handle_security_incident, EmergencyModeHandler

        mock_sm = MagicMock()
        mock_sm.ddos_protection.redis_client.setex = MagicMock()

        with patch("security.middleware.security_middleware", mock_sm), \
             patch.object(EmergencyModeHandler, "enable_emergency_mode") as mock_enable:
            handle_security_incident(
                "ddos_attack",
                {"severity": "critical", "ip": "6.7.8.9"},
            )
            mock_enable.assert_called()

    def test_handle_unknown_incident_type(self):
        from security.middleware import handle_security_incident

        mock_sm = MagicMock()
        with patch("security.middleware.security_middleware", mock_sm):
            try:
                handle_security_incident("unknown_type", {})
            except Exception as exc:
                pytest.fail(f"handle_security_incident unknown raised: {exc}")
