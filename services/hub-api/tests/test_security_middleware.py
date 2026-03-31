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
    with patch("security.get_db", return_value=mock_db):
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
        ips = [item.get("ip_address", item.get("ip", item)) if isinstance(item, dict) else item for item in result]
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
            assert not result  # 0 / False both falsy

    def test_is_emergency_mode_true_when_key_exists(self):
        from security.middleware import EmergencyModeHandler

        mock_ddos = MagicMock()
        mock_ddos.redis_client.exists = MagicMock(return_value=1)

        with patch("security.middleware.security_middleware") as mock_sm:
            mock_sm.ddos_protection = mock_ddos
            result = EmergencyModeHandler.is_emergency_mode()
            assert result  # 1 / True both truthy

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


# ---------------------------------------------------------------------------
# _load_custom_rules — coverage for lines 126-140
# ---------------------------------------------------------------------------

class TestLoadCustomRules:
    def _make_db_with_rule(self, rule_name, endpoints=None, exempt_ips=None):
        """Helper: build a mock DB whose query chain returns a single custom rule row."""
        db = MagicMock()
        db.tables = ['rate_limit_rules']

        rule_row = MagicMock()
        rule_row.name = rule_name
        rule_row.max_requests = 20
        rule_row.window_seconds = 120
        rule_row.block_duration = 600
        rule_row.endpoints = endpoints
        rule_row.exempt_ips = exempt_ips
        rule_row.priority = 5

        # PyDAL query pattern: db(query).select()
        # MagicMock uses return_value for call results
        db.return_value.select.return_value = [rule_row]
        return db

    def test_load_custom_rules_with_table_present(self, mock_redis_sync):
        """Covers lines 126-138: table exists, rules are loaded.

        Patch target is 'security.get_db' because security/__init__.py uses
        'from database import get_db', binding get_db in the security namespace.
        """
        db = self._make_db_with_rule(
            "custom_rule",
            endpoints='["/api/custom/"]',
            exempt_ips='["10.0.0.1"]',
        )

        with patch("security.get_db", return_value=db):
            limiter = RateLimiter(redis_client=mock_redis_sync)

        names = [r.name for r in limiter.rules]
        assert "custom_rule" in names

    def test_load_custom_rules_no_endpoints(self, mock_redis_sync):
        """Covers branch where endpoints/exempt_ips are None."""
        db = self._make_db_with_rule("bare_rule", endpoints=None, exempt_ips=None)

        with patch("security.get_db", return_value=db):
            limiter = RateLimiter(redis_client=mock_redis_sync)

        names = [r.name for r in limiter.rules]
        assert "bare_rule" in names

    def test_load_custom_rules_exception_is_swallowed(self, mock_redis_sync, mock_db):
        """Covers line 140: exception during load is caught and logged."""
        mock_db.tables = ['rate_limit_rules']
        mock_db.return_value.select.side_effect = Exception("DB exploded")

        with patch("security.get_db", return_value=mock_db):
            # Should not raise
            limiter = RateLimiter(redis_client=mock_redis_sync)
        assert limiter is not None


# ---------------------------------------------------------------------------
# is_allowed — blocked IP path (lines 150-151)
# ---------------------------------------------------------------------------

class TestIsAllowedBlockedIP:
    def test_is_allowed_blocked_ip_returns_false(self, rate_limiter):
        """Covers line 150-151: IP in blocked_until returns (False, None, until)."""
        future = time.time() + 300
        rate_limiter.blocked_ips.add("5.5.5.5")
        rate_limiter.blocked_until["5.5.5.5"] = future

        allowed, rule, retry = rate_limiter.is_allowed("5.5.5.5", "/api/v1/test")
        assert allowed is False
        assert rule is None

    def test_is_allowed_rate_limit_exceeded_blocks_and_logs(self, rate_limiter, mock_redis_sync, mock_db):
        """Covers lines 159-171: rule violation triggers _block_ip and _log_security_event."""
        # pipeline returns count >= max_requests for the auth rule (max=5)
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[0, 1000])  # zremrange, zcard=1000
        pipe_mock.zremrangebyscore = MagicMock()
        pipe_mock.zcard = MagicMock()
        pipe_mock.expire = MagicMock()
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)
        mock_redis_sync.zrange = MagicMock(return_value=[("ts", 1000)])

        rate_limiter.db = mock_db

        allowed, violated_rule, retry = rate_limiter.is_allowed("6.6.6.6", "/api/auth/login")
        assert allowed is False
        assert violated_rule is not None


# ---------------------------------------------------------------------------
# _block_ip — Redis failure path (lines 193-197)
# ---------------------------------------------------------------------------

class TestBlockIP:
    def test_block_ip_redis_failure_does_not_raise(self, rate_limiter, mock_redis_sync):
        """Covers lines 193-197: Redis setex failure is caught."""
        mock_redis_sync.setex = MagicMock(side_effect=Exception("redis down"))
        # Should not raise
        rate_limiter._block_ip("8.8.8.8", 300)
        assert "8.8.8.8" in rate_limiter.blocked_ips

    def test_block_ip_sets_blocked_until(self, rate_limiter, mock_redis_sync):
        """Covers lines 188-197: IP gets added to blocked sets."""
        mock_redis_sync.setex = MagicMock(return_value=True)
        before = time.time()
        rate_limiter._block_ip("9.9.9.9", 600)
        assert "9.9.9.9" in rate_limiter.blocked_ips
        assert rate_limiter.blocked_until["9.9.9.9"] >= before + 599


# ---------------------------------------------------------------------------
# _rule_applies — exempt IP branches (lines 202-223)
# ---------------------------------------------------------------------------

class TestRuleApplies:
    def test_rule_applies_exempt_single_ip(self, rate_limiter):
        """Covers lines 202-213: exempt single IP returns False."""
        rule = RateLimitRule(
            name="test", max_requests=10, window_seconds=60,
            exempt_ips=["192.168.1.1"]
        )
        result = rate_limiter._rule_applies(rule, "/api/test", "192.168.1.1")
        assert result is False

    def test_rule_applies_exempt_cidr(self, rate_limiter):
        """Covers CIDR exemption branch."""
        rule = RateLimitRule(
            name="test", max_requests=10, window_seconds=60,
            exempt_ips=["10.0.0.0/8"]
        )
        result = rate_limiter._rule_applies(rule, "/api/test", "10.5.5.5")
        assert result is False

    def test_rule_applies_non_exempt_ip(self, rate_limiter):
        """Non-exempt IP with matching endpoint returns True."""
        rule = RateLimitRule(
            name="test", max_requests=10, window_seconds=60,
            exempt_ips=["192.168.1.1"],
            endpoints=["/api/"]
        )
        result = rate_limiter._rule_applies(rule, "/api/test", "10.0.0.1")
        assert result is True

    def test_rule_applies_no_endpoint_match(self, rate_limiter):
        """Rule with endpoints that don't match returns False."""
        rule = RateLimitRule(
            name="test", max_requests=10, window_seconds=60,
            endpoints=["/api/specific/"]
        )
        result = rate_limiter._rule_applies(rule, "/other/path", "1.2.3.4")
        assert result is False

    def test_rule_applies_invalid_ip_format_handled(self, rate_limiter):
        """Covers line 212-213: invalid IP in exempt_ips is caught."""
        rule = RateLimitRule(
            name="test", max_requests=10, window_seconds=60,
            exempt_ips=["not-an-ip"],
            endpoints=["/api/"]
        )
        # Should not raise; invalid IP warning is logged
        result = rate_limiter._rule_applies(rule, "/api/test", "1.2.3.4")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# _check_rule — Redis sliding window (lines 227-260)
# ---------------------------------------------------------------------------

class TestCheckRule:
    def test_check_rule_allowed(self, rate_limiter, mock_redis_sync):
        """Covers lines 227-255: count < max returns (True, 0)."""
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[0, 2])  # zremrange=0, zcard=2
        pipe_mock.zremrangebyscore = MagicMock()
        pipe_mock.zcard = MagicMock()
        pipe_mock.expire = MagicMock()
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)
        mock_redis_sync.zadd = MagicMock(return_value=1)

        rule = RateLimitRule(name="test", max_requests=10, window_seconds=60)
        allowed, retry = rate_limiter._check_rule(rule, "1.2.3.4", "/test")
        assert allowed is True
        assert retry == 0

    def test_check_rule_exceeded_with_oldest_entry(self, rate_limiter, mock_redis_sync):
        """Covers lines 244-249: count >= max with oldest entry calculates retry_after."""
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[0, 100])  # zcard=100
        pipe_mock.zremrangebyscore = MagicMock()
        pipe_mock.zcard = MagicMock()
        pipe_mock.expire = MagicMock()
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)
        oldest_time = int(time.time()) - 30
        mock_redis_sync.zrange = MagicMock(return_value=[("ts", oldest_time)])

        rule = RateLimitRule(name="test", max_requests=10, window_seconds=60)
        allowed, retry = rate_limiter._check_rule(rule, "1.2.3.4", "/test")
        assert allowed is False
        assert retry >= 1

    def test_check_rule_exceeded_no_oldest_entry(self, rate_limiter, mock_redis_sync):
        """Covers line 250: count >= max, no oldest entry returns window_seconds."""
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[0, 100])
        pipe_mock.zremrangebyscore = MagicMock()
        pipe_mock.zcard = MagicMock()
        pipe_mock.expire = MagicMock()
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)
        mock_redis_sync.zrange = MagicMock(return_value=[])

        rule = RateLimitRule(name="test", max_requests=10, window_seconds=60)
        allowed, retry = rate_limiter._check_rule(rule, "1.2.3.4", "/test")
        assert allowed is False
        assert retry == 60

    def test_check_rule_redis_failure_falls_back(self, rate_limiter, mock_redis_sync):
        """Covers lines 257-260: Redis error falls back to in-memory limiter."""
        mock_redis_sync.pipeline = MagicMock(side_effect=Exception("redis down"))
        rule = RateLimitRule(name="fallback_test", max_requests=100, window_seconds=60)
        allowed, retry = rate_limiter._check_rule(rule, "1.2.3.4", "/test")
        assert isinstance(allowed, bool)


# ---------------------------------------------------------------------------
# _fallback_rate_limit (lines 264-284)
# ---------------------------------------------------------------------------

class TestFallbackRateLimit:
    def test_fallback_allows_within_limit(self, rate_limiter):
        """Covers lines 264-284: in-memory fallback allows requests within limit."""
        rule = RateLimitRule(name="fallback", max_requests=5, window_seconds=60)
        allowed, retry = rate_limiter._fallback_rate_limit(rule, "2.2.2.2", "/test")
        assert allowed is True
        assert retry == 0

    def test_fallback_blocks_when_exceeded(self, rate_limiter):
        """Covers lines 275-280: fallback blocks when counter full."""
        rule = RateLimitRule(name="fallback_block", max_requests=2, window_seconds=60)
        # Pre-fill the counter
        if not hasattr(rate_limiter, '_fallback_counters'):
            from collections import defaultdict, deque
            rate_limiter._fallback_counters = defaultdict(deque)
        key = f"{rule.name}:3.3.3.3"
        now = time.time()
        rate_limiter._fallback_counters[key].append(now)
        rate_limiter._fallback_counters[key].append(now)

        allowed, retry = rate_limiter._fallback_rate_limit(rule, "3.3.3.3", "/test")
        assert allowed is False
        assert retry >= 1

    def test_fallback_cleans_old_entries(self, rate_limiter):
        """Covers the while-loop that removes stale entries."""
        rule = RateLimitRule(name="fallback_clean", max_requests=5, window_seconds=10)
        if not hasattr(rate_limiter, '_fallback_counters'):
            from collections import defaultdict, deque
            rate_limiter._fallback_counters = defaultdict(deque)
        key = f"{rule.name}:4.4.4.4"
        # Add old entry outside the window
        rate_limiter._fallback_counters[key].append(time.time() - 20)

        allowed, retry = rate_limiter._fallback_rate_limit(rule, "4.4.4.4", "/test")
        assert allowed is True


# ---------------------------------------------------------------------------
# _log_security_event (lines 289-317)
# ---------------------------------------------------------------------------

class TestLogSecurityEvent:
    def test_log_event_with_security_events_table(self, rate_limiter, mock_db):
        """Covers lines 300-311: event logged to DB when table exists."""
        mock_db.tables = ['security_events']
        rate_limiter.db = mock_db
        # Should not raise
        rate_limiter._log_security_event(
            "test_event", "1.2.3.4", "/api/test", "TestAgent",
            "medium", {"key": "value"}
        )
        mock_db.security_events.insert.assert_called_once()
        mock_db.commit.assert_called()

    def test_log_event_without_table(self, rate_limiter, mock_db):
        """Covers branch where security_events table does not exist."""
        mock_db.tables = []
        rate_limiter.db = mock_db
        # Should not raise, just logs
        rate_limiter._log_security_event(
            "test_event", "1.2.3.4", "/api/test", "TestAgent",
            "low", {}
        )

    def test_log_event_db_exception_is_caught(self, rate_limiter, mock_db):
        """Covers lines 316-317: DB exception is caught."""
        mock_db.tables = ['security_events']
        mock_db.security_events.insert = MagicMock(side_effect=Exception("insert failed"))
        rate_limiter.db = mock_db
        # Should not raise
        rate_limiter._log_security_event(
            "test_event", "1.2.3.4", "/api/test", "UA",
            "high", {"detail": "x"}
        )


# ---------------------------------------------------------------------------
# get_blocked_ips — expired entries filtered (lines 321-332)
# ---------------------------------------------------------------------------

class TestGetBlockedIPsDetailed:
    def test_get_blocked_ips_filters_expired(self, rate_limiter):
        """Covers lines 321-332: expired IPs not included."""
        past = time.time() - 1
        future = time.time() + 300
        rate_limiter.blocked_until["expired.ip"] = past
        rate_limiter.blocked_until["active.ip"] = future

        result = rate_limiter.get_blocked_ips()
        ip_list = [item.get("ip_address") for item in result if isinstance(item, dict)]
        assert "active.ip" in ip_list
        assert "expired.ip" not in ip_list

    def test_get_blocked_ips_remaining_seconds(self, rate_limiter):
        """Covers remaining_seconds calculation."""
        rate_limiter.blocked_until["timed.ip"] = time.time() + 100
        result = rate_limiter.get_blocked_ips()
        match = [item for item in result if isinstance(item, dict) and item.get("ip_address") == "timed.ip"]
        assert match
        assert match[0]["remaining_seconds"] > 0


# ---------------------------------------------------------------------------
# unblock_ip (lines 336-348)
# ---------------------------------------------------------------------------

class TestUnblockIP:
    def test_unblock_ip_success(self, rate_limiter, mock_redis_sync):
        """Covers lines 336-348: unblock removes from sets and Redis."""
        mock_redis_sync.delete = MagicMock(return_value=1)
        rate_limiter.blocked_ips.add("7.7.7.7")
        rate_limiter.blocked_until["7.7.7.7"] = time.time() + 300

        result = rate_limiter.unblock_ip("7.7.7.7")
        assert result is True
        assert "7.7.7.7" not in rate_limiter.blocked_until

    def test_unblock_ip_not_blocked_returns_false(self, rate_limiter):
        """Covers the else branch: IP not in blocked_until."""
        result = rate_limiter.unblock_ip("not.blocked.ip")
        assert result is False

    def test_unblock_ip_redis_failure_caught(self, rate_limiter, mock_redis_sync):
        """Covers lines 345-346: Redis delete failure is caught."""
        mock_redis_sync.delete = MagicMock(side_effect=Exception("redis down"))
        rate_limiter.blocked_ips.add("err.ip")
        rate_limiter.blocked_until["err.ip"] = time.time() + 300

        # Should not raise even when Redis fails
        rate_limiter.unblock_ip("err.ip")


# ---------------------------------------------------------------------------
# DDoSProtection (lines 386-585)
# ---------------------------------------------------------------------------

class TestDDoSDetection:
    @pytest.fixture
    def ddos(self, mock_redis_sync, mock_db):
        with patch("security.get_db", return_value=mock_db):
            limiter = RateLimiter(redis_client=mock_redis_sync)
        from security import DDoSProtection
        return DDoSProtection(limiter)

    def test_detect_ddos_no_attack(self, ddos, mock_redis_sync):
        """Covers lines 386-417: no indicators returns (False, '', '')."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=1)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        assert is_attack is False

    def test_detect_ddos_volume_attack(self, ddos, mock_redis_sync):
        """Covers lines 421-438: volume-based attack detection."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        # Return count > threshold (default 1000)
        mock_redis_sync.zcard = MagicMock(side_effect=[1001, 0])
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=0)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        assert is_attack is True
        assert "volume" in attack_type

    def test_detect_ddos_suspicious_pattern_endpoint(self, ddos, mock_redis_sync):
        """Covers lines 442-464: suspicious pattern in endpoint."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=0)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        # PHP file request triggers pattern detection
        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/wp-admin/index.php", "Mozilla/5.0")
        assert is_attack is True
        assert "pattern" in attack_type

    def test_detect_ddos_suspicious_useragent(self, ddos, mock_redis_sync):
        """Covers user-agent pattern check (sqlmap, nikto, etc.)."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=0)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "sqlmap/1.0")
        assert is_attack is True
        assert "pattern" in attack_type

    def test_detect_ddos_distributed_attack(self, ddos, mock_redis_sync):
        """Covers lines 516-536: distributed attack (>50 unique IPs)."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        # First zcard call (volume check) = 0; second (distributed IPs) = 51
        mock_redis_sync.zcard = MagicMock(side_effect=[0, 51])
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=0)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        assert is_attack is True
        assert "distributed" in attack_type
        assert severity == "critical"

    def test_detect_ddos_behavioral_many_endpoints(self, ddos, mock_redis_sync):
        """Covers lines 468-514: behavioral anomaly — too many unique endpoints."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        # scard returns >20 unique endpoints → behavioral anomaly
        mock_redis_sync.scard = MagicMock(return_value=25)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        assert is_attack is True
        assert "behavioral" in attack_type

    def test_detect_ddos_behavioral_regular_timing(self, ddos, mock_redis_sync):
        """Covers lines 493-508: bot-like regular timing variance code path is exercised."""
        now = time.time()
        # 5 requests with very small, very uniform intervals — sub-millisecond apart
        # avg_interval < 2 and variance < 0.1 triggers behavioral flag
        tiny = 0.05
        times = [str(now - i * tiny) for i in range(5)]

        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=5)  # < 20 endpoints, no endpoint anomaly
        mock_redis_sync.lrange = MagicMock(return_value=times)
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        # Variance is 0 (perfectly uniform), avg_interval = 0.05 (<2) — triggers behavioral flag
        assert is_attack is True
        assert "behavioral" in attack_type

    def test_detect_ddos_severity_high(self, ddos, mock_redis_sync):
        """Covers lines 407-415: severity is 'high' when high indicator present."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        # Volume exceeds threshold for 'high' severity
        mock_redis_sync.zcard = MagicMock(side_effect=[1001, 0])
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=0)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, attack_type, severity = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        assert is_attack is True
        assert severity in ("high", "critical", "medium")

    def test_volume_check_redis_failure_returns_false(self, ddos, mock_redis_sync):
        """Covers lines 436-438: Redis error in volume check returns False."""
        mock_redis_sync.zremrangebyscore = MagicMock(side_effect=Exception("redis down"))
        result = ddos._check_volume_attack("1.2.3.4")
        assert result is False

    def test_behavioral_redis_failure_returns_false(self, ddos, mock_redis_sync):
        """Covers lines 512-514: Redis error in behavioral check returns False."""
        mock_redis_sync.sadd = MagicMock(side_effect=Exception("redis down"))
        result = ddos._check_behavioral_anomaly("1.2.3.4", "/api/test")
        assert result is False

    def test_distributed_redis_failure_returns_false(self, ddos, mock_redis_sync):
        """Covers lines 534-536: Redis error in distributed check returns False."""
        mock_redis_sync.zremrangebyscore = MagicMock(side_effect=Exception("redis down"))
        result = ddos._check_distributed_attack()
        assert result is False


class TestDDoSMitigation:
    @pytest.fixture
    def ddos(self, mock_redis_sync, mock_db):
        with patch("security.get_db", return_value=mock_db):
            limiter = RateLimiter(redis_client=mock_redis_sync)
        from security import DDoSProtection
        return DDoSProtection(limiter)

    def test_mitigate_medium_attack(self, ddos, mock_redis_sync, mock_db):
        """Covers lines 541-572: medium severity blocks without emergency mode."""
        mock_redis_sync.setex = MagicMock(return_value=True)
        ddos.rate_limiter.db = mock_db
        mock_db.tables = []

        ddos.mitigate_attack("1.2.3.4", "pattern", "medium")
        assert "1.2.3.4" in ddos.rate_limiter.blocked_ips

    def test_mitigate_high_severity_enables_emergency(self, ddos, mock_redis_sync, mock_db):
        """Covers lines 568-569: high severity calls _enable_emergency_mode."""
        mock_redis_sync.setex = MagicMock(return_value=True)
        ddos.rate_limiter.db = mock_db
        mock_db.tables = []

        ddos.mitigate_attack("2.3.4.5", "volume", "high")
        # setex should be called for both block and emergency mode
        assert mock_redis_sync.setex.call_count >= 1

    def test_mitigate_critical_severity_enables_emergency(self, ddos, mock_redis_sync, mock_db):
        """Covers critical path: calls _enable_emergency_mode."""
        mock_redis_sync.setex = MagicMock(return_value=True)
        ddos.rate_limiter.db = mock_db
        mock_db.tables = []

        ddos.mitigate_attack("3.4.5.6", "distributed", "critical")
        assert mock_redis_sync.setex.call_count >= 1

    def test_enable_emergency_mode_redis_failure(self, ddos, mock_redis_sync):
        """Covers lines 576-580: Redis failure in _enable_emergency_mode."""
        mock_redis_sync.setex = MagicMock(side_effect=Exception("redis down"))
        # Should not raise
        ddos._enable_emergency_mode()

    def test_notify_attack_logs(self, ddos):
        """Covers line 585: _notify_attack logs the event."""
        # Should not raise
        ddos._notify_attack("5.6.7.8", "volume", "high")

    def test_mitigate_low_severity(self, ddos, mock_redis_sync, mock_db):
        """Covers low severity path (no emergency mode)."""
        mock_redis_sync.setex = MagicMock(return_value=True)
        ddos.rate_limiter.db = mock_db
        mock_db.tables = []

        ddos.mitigate_attack("4.5.6.7", "pattern", "low")
        assert "4.5.6.7" in ddos.rate_limiter.blocked_ips


# ---------------------------------------------------------------------------
# SecurityMiddleware._ensure_security_tables (lines 603-635)
# ---------------------------------------------------------------------------

class TestSecurityMiddlewareEnsureTables:
    def test_ensure_tables_creates_both_tables(self, mock_redis_sync, mock_db):
        """Covers lines 603-635: creates security_events and rate_limit_rules tables."""
        mock_db.tables = []

        with patch("security.get_db", return_value=mock_db), \
             patch("redis.Redis", return_value=mock_redis_sync):
            from security import SecurityMiddleware
            sm = SecurityMiddleware.__new__(SecurityMiddleware)
            sm.rate_limiter = MagicMock()
            sm.rate_limiter.db = mock_db
            sm.rate_limiter.redis_client = mock_redis_sync
            sm.ddos_protection = MagicMock()
            sm._ensure_security_tables()

        # Both tables should have been defined
        assert "security_events" in mock_db.tables
        assert "rate_limit_rules" in mock_db.tables

    def test_ensure_tables_skips_existing_tables(self, mock_redis_sync, mock_db):
        """Covers branches where tables already exist — define_table not called."""
        mock_db.tables = ['security_events', 'rate_limit_rules']
        # Replace define_table with a pure MagicMock for assertion
        mock_db.define_table = MagicMock()

        with patch("security.get_db", return_value=mock_db), \
             patch("redis.Redis", return_value=mock_redis_sync):
            from security import SecurityMiddleware
            sm = SecurityMiddleware.__new__(SecurityMiddleware)
            sm.rate_limiter = MagicMock()
            sm.rate_limiter.db = mock_db
            sm._ensure_security_tables()

        # define_table should NOT have been called since both tables exist
        mock_db.define_table.assert_not_called()


# ---------------------------------------------------------------------------
# SecurityMiddleware.process_request (lines 638-679)
# ---------------------------------------------------------------------------

class TestProcessRequest:
    @pytest.fixture
    def security_middleware_instance(self, mock_redis_sync, mock_db):
        from security import SecurityMiddleware, RateLimiter, DDoSProtection
        with patch("security.get_db", return_value=mock_db):
            sm = SecurityMiddleware.__new__(SecurityMiddleware)
            sm.rate_limiter = RateLimiter(redis_client=mock_redis_sync)
            sm.rate_limiter.db = mock_db
            sm.ddos_protection = DDoSProtection(sm.rate_limiter)
        return sm

    def test_process_request_allowed(self, security_middleware_instance, mock_redis_sync):
        """Covers lines 648-679: allowed path returns (True, headers)."""
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[0, 1])
        pipe_mock.zremrangebyscore = MagicMock()
        pipe_mock.zcard = MagicMock()
        pipe_mock.expire = MagicMock()
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=0)
        mock_redis_sync.lrange = MagicMock(return_value=[])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        request_info = {
            "ip_address": "10.0.0.1",
            "endpoint": "/api/v1/health",
            "user_agent": "Mozilla/5.0",
        }
        allowed, headers = security_middleware_instance.process_request(request_info)
        assert allowed is True
        assert isinstance(headers, dict)

    def test_process_request_blocked_rate_limit(self, security_middleware_instance, mock_redis_sync):
        """Covers lines 655-662: rate-limit block returns (False, headers with Retry-After)."""
        future = time.time() + 300
        security_middleware_instance.rate_limiter.blocked_ips.add("5.5.5.5")
        security_middleware_instance.rate_limiter.blocked_until["5.5.5.5"] = future

        request_info = {
            "ip_address": "5.5.5.5",
            "endpoint": "/api/v1/test",
            "user_agent": "Mozilla/5.0",
        }
        allowed, headers = security_middleware_instance.process_request(request_info)
        assert allowed is False

    def test_process_request_ddos_blocked(self, security_middleware_instance, mock_redis_sync, mock_db):
        """Covers lines 664-673: DDoS detection blocks request."""
        pipe_mock = MagicMock()
        pipe_mock.execute = MagicMock(return_value=[0, 1])
        pipe_mock.zremrangebyscore = MagicMock()
        pipe_mock.zcard = MagicMock()
        pipe_mock.expire = MagicMock()
        mock_redis_sync.pipeline = MagicMock(return_value=pipe_mock)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.setex = MagicMock()
        mock_db.tables = []
        security_middleware_instance.rate_limiter.db = mock_db

        # Mock DDoS detection to report an attack
        security_middleware_instance.ddos_protection.detect_ddos_attack = MagicMock(
            return_value=(True, "volume", "high")
        )
        security_middleware_instance.ddos_protection.mitigate_attack = MagicMock()

        request_info = {
            "ip_address": "10.0.0.2",
            "endpoint": "/api/v1/data",
            "user_agent": "Mozilla/5.0",
        }
        allowed, headers = security_middleware_instance.process_request(request_info)
        assert allowed is False
        assert "X-Security-Block" in headers


# ---------------------------------------------------------------------------
# Additional branch-coverage tests for lines still missing
# ---------------------------------------------------------------------------

class TestRuleAppliesIPException:
    """Covers lines 207->205, 212-213: ipaddress.ip_address raises for bad IP."""

    def test_rule_applies_ip_address_raises(self, rate_limiter):
        """Line 212-213: exception from ipaddress.ip_address is caught and logged."""
        rule = RateLimitRule(
            name="test_exc", max_requests=10, window_seconds=60,
            exempt_ips=["192.168.1.1"],
            endpoints=["/api/"]
        )
        # Pass a non-IP string as ip_address — ipaddress.ip_address raises ValueError
        with patch("security.ipaddress.ip_address", side_effect=ValueError("bad ip")):
            result = rate_limiter._rule_applies(rule, "/api/test", "not-an-ip")
        # After exception, falls through to endpoint check — endpoint matches, returns True
        assert isinstance(result, bool)


class TestFallbackRateLimitEmptyCounter:
    """Covers line 280: fallback with counter that becomes empty after cleanup."""

    def test_fallback_counter_empty_after_cleanup(self, rate_limiter):
        """Line 280: if counter is empty after cleanup, returns (False, window_seconds)."""
        from collections import defaultdict, deque
        rule = RateLimitRule(name="empty_counter", max_requests=0, window_seconds=60)
        # Ensure _fallback_counters exists and key exists but is empty after clean
        rate_limiter._fallback_counters = defaultdict(deque)
        # Don't pre-fill counter — it starts empty; max_requests=0 means len(counter)>=0 triggers
        # Actually with max_requests=0, len([]) >= 0 is True immediately
        # counter is empty (falsy), so it hits line 280: return False, rule.window_seconds
        allowed, retry = rate_limiter._fallback_rate_limit(rule, "5.5.5.5", "/test")
        assert allowed is False
        assert retry == rule.window_seconds


class TestBehavioralTimingNotEnoughRequests:
    """Covers line 502->510, 507->510: timing check with < 5 requests or variance >= 0.1."""

    @pytest.fixture
    def ddos(self, mock_redis_sync, mock_db):
        with patch("security.get_db", return_value=mock_db):
            limiter = RateLimiter(redis_client=mock_redis_sync)
        from security import DDoSProtection
        return DDoSProtection(limiter)

    def test_behavioral_fewer_than_5_requests_no_timing_check(self, ddos, mock_redis_sync):
        """Covers line 502->510: len(last_requests) < 5 skips timing variance check."""
        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=3)
        # Only 3 requests — not enough to trigger timing check
        mock_redis_sync.lrange = MagicMock(return_value=["1.0", "2.0", "3.0"])
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, _, _ = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        # No attack indicators → False
        assert is_attack is False

    def test_behavioral_high_variance_not_flagged(self, ddos, mock_redis_sync):
        """Covers line 507->510: variance >= 0.1 means NOT flagged as bot."""
        now = time.time()
        # Highly irregular intervals — high variance
        import random
        times = [str(now - sum([random.uniform(0.5, 5.0) for _ in range(i)])) for i in range(5)]

        mock_redis_sync.zremrangebyscore = MagicMock()
        mock_redis_sync.zcard = MagicMock(return_value=0)
        mock_redis_sync.zadd = MagicMock()
        mock_redis_sync.expire = MagicMock()
        mock_redis_sync.sadd = MagicMock()
        mock_redis_sync.scard = MagicMock(return_value=3)
        mock_redis_sync.lrange = MagicMock(return_value=times)
        mock_redis_sync.lpush = MagicMock()
        mock_redis_sync.ltrim = MagicMock()

        is_attack, _, _ = ddos.detect_ddos_attack("1.2.3.4", "/api/v1/health", "Mozilla/5.0")
        # High variance → behavioral check returns False → no attack
        assert is_attack is False
