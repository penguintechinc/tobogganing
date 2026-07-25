"""Rate limiting with Redis backend and multiple strategies."""
from __future__ import annotations

import ipaddress
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any

import redis
import structlog

from .datatypes import RateLimitRuleData, SecurityEventData
from .models import RateLimitRule, SecurityEvent

logger = structlog.get_logger()


class RateLimiter:
    """Advanced rate limiter with Redis backend and multiple strategies."""

    def __init__(
        self,
        db: Any,
        redis_client: redis.Redis | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Initialize RateLimiter.

        Args:
            db: penguin-dal AsyncDB instance for database operations.
            redis_client: Redis client for rate limit tracking.
            tenant_id: Tenant ID for multi-tenant scoping.
        """
        self.db = db
        self.redis_client = redis_client or redis.Redis(
            host="localhost",
            port=6379,
            db=1,
            decode_responses=True,
        )
        self.tenant_id = tenant_id
        self.blocked_ips: set[str] = set()
        self.blocked_until: dict[str, float] = {}
        self.rules: list[RateLimitRuleData] = []

        # Default rate limiting rules
        self._init_default_rules()

        # Note: custom rules must be loaded asynchronously via load_custom_rules()
        # Sort rules by priority
        self.rules.sort(key=lambda r: r.priority)

    async def load_custom_rules(self) -> None:
        """Load custom rate limiting rules from database asynchronously.

        This must be called after __init__ to populate custom rules from the database.
        """
        await self._load_custom_rules()

    def _init_default_rules(self) -> None:
        """Initialize default rate limiting rules."""
        self.rules = [
            RateLimitRuleData(
                name="api_strict",
                max_requests=60,
                window_seconds=60,
                block_duration=300,
                endpoints=["/api/"],
                priority=1,
            ),
            RateLimitRuleData(
                name="auth_strict",
                max_requests=5,
                window_seconds=60,
                block_duration=900,
                endpoints=["/api/auth/", "/login", "/api/v1/auth"],
                priority=1,
            ),
            RateLimitRuleData(
                name="config_moderate",
                max_requests=10,
                window_seconds=300,
                block_duration=600,
                endpoints=["/api/v1/clients/", "/api/analytics/record/"],
                priority=2,
            ),
            RateLimitRuleData(
                name="backup_strict",
                max_requests=3,
                window_seconds=300,
                block_duration=1200,
                endpoints=["/api/backup/"],
                priority=1,
            ),
            RateLimitRuleData(
                name="analytics_moderate",
                max_requests=100,
                window_seconds=60,
                block_duration=300,
                endpoints=["/api/analytics/"],
                priority=3,
            ),
            RateLimitRuleData(
                name="web_lenient",
                max_requests=200,
                window_seconds=60,
                block_duration=60,
                priority=10,
            ),
        ]

    async def _load_custom_rules(self) -> None:
        """Load custom rate limiting rules from database asynchronously."""
        try:
            cond = self.db.rate_limit_rules.enabled == True  # noqa: E712

            if self.tenant_id:
                cond = cond & (self.db.rate_limit_rules.tenant_id == self.tenant_id)

            rows = await self.db(cond).select()
            for row in rows:
                custom_rule = RateLimitRuleData(
                    name=row.name,
                    max_requests=row.max_requests,
                    window_seconds=row.window_seconds,
                    block_duration=row.block_duration,
                    endpoints=row.endpoints,
                    exempt_ips=row.exempt_ips,
                    priority=row.priority,
                )
                self.rules.append(custom_rule)
                logger.info("custom_rate_limit_rule_loaded", rule_name=row.name)

            # Re-sort rules by priority after adding custom rules
            self.rules.sort(key=lambda r: r.priority)

        except Exception as e:
            logger.warning("failed_to_load_custom_rate_limit_rules", error=str(e))

    async def is_allowed(
        self, ip_address: str, endpoint: str, user_agent: str = ""
    ) -> tuple[bool, RateLimitRuleData | None, int]:
        """Check if request is allowed based on rate limiting rules.

        Args:
            ip_address: Client IP address.
            endpoint: Request endpoint/path.
            user_agent: Client user agent.

        Returns:
            Tuple of (allowed, violated_rule, retry_after_seconds).
        """
        # Check if IP is currently blocked
        if self._is_ip_blocked(ip_address):
            retry_after = max(
                int(self.blocked_until.get(ip_address, 0) - time.time()), 1
            )
            return False, None, retry_after

        # Check against each rule
        for rule in self.rules:
            if self._rule_applies(rule, endpoint, ip_address):
                allowed, retry_after = self._check_rule(rule, ip_address, endpoint)
                if not allowed:
                    # Block the IP
                    self._block_ip(ip_address, rule.block_duration)

                    # Log security event (async, but non-blocking)
                    try:
                        await self._log_security_event(
                            "rate_limit_violation",
                            ip_address,
                            endpoint,
                            user_agent,
                            "medium",
                            {
                                "rule": rule.name,
                                "max_requests": rule.max_requests,
                                "window": rule.window_seconds,
                            },
                        )
                    except Exception as e:
                        logger.error("failed_to_log_rate_limit_violation", error=str(e))

                    return False, rule, retry_after

        return True, None, 0

    def _is_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP address is currently blocked."""
        if ip_address in self.blocked_until:
            if time.time() < self.blocked_until[ip_address]:
                return True
            else:
                del self.blocked_until[ip_address]
                self.blocked_ips.discard(ip_address)
        return False

    def _block_ip(self, ip_address: str, duration: int) -> None:
        """Block IP address for specified duration."""
        until = time.time() + duration
        self.blocked_ips.add(ip_address)
        self.blocked_until[ip_address] = until

        try:
            self.redis_client.setex(
                f"blocked_ip:{ip_address}", duration, int(until)
            )
            logger.warning(
                "ip_blocked_rate_limit",
                ip_address=ip_address,
                duration=duration,
            )
        except Exception as e:
            logger.error("failed_to_store_ip_block_redis", error=str(e))

    def _rule_applies(
        self, rule: RateLimitRuleData, endpoint: str, ip_address: str
    ) -> bool:
        """Check if a rule applies to the current request."""
        # Check if IP is exempt
        if rule.exempt_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_address)
                for exempt in rule.exempt_ips:
                    if "/" in exempt:
                        if ip_obj in ipaddress.ip_network(exempt):
                            return False
                    else:
                        if ip_address == exempt:
                            return False
            except Exception as e:
                logger.warning("invalid_ip_format_exempt_check", error=str(e))

        # Check if endpoint matches
        if rule.endpoints is None:
            return True

        for pattern in rule.endpoints:
            if endpoint.startswith(pattern):
                return True

        return False

    def _check_rule(
        self, rule: RateLimitRuleData, ip_address: str, endpoint: str
    ) -> tuple[bool, int]:
        """Check if request violates the rate limit rule."""
        key = f"rl:{rule.name}:{ip_address}"

        try:
            now = int(time.time())
            window_start = now - rule.window_seconds

            # Use Redis sliding window counter
            pipeline = self.redis_client.pipeline()
            pipeline.zremrangebyscore(key, 0, window_start)
            pipeline.zcard(key)
            pipeline.expire(key, rule.window_seconds)
            results = pipeline.execute()

            current_count = results[1]

            if current_count >= rule.max_requests:
                # Get the oldest entry to calculate retry-after
                oldest_entry = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_entry:
                    oldest_time = int(oldest_entry[0][1])
                    retry_after = rule.window_seconds - (now - oldest_time)
                    return False, max(retry_after, 1)
                return False, rule.window_seconds

            # Add current request
            self.redis_client.zadd(key, {str(now): now})

            return True, 0

        except Exception as e:
            logger.error("redis_rate_limit_error", error=str(e))
            # Fall back to in-memory rate limiting
            return self._fallback_rate_limit(rule, ip_address, endpoint)

    def _fallback_rate_limit(
        self, rule: RateLimitRuleData, ip_address: str, endpoint: str
    ) -> tuple[bool, int]:
        """Fallback in-memory rate limiting when Redis is unavailable."""
        key = f"{rule.name}:{ip_address}"
        now = time.time()

        if not hasattr(self, "_fallback_counters"):
            self._fallback_counters: dict[str, deque[float]] = defaultdict(deque)

        # Clean old entries
        counter = self._fallback_counters[key]
        while counter and counter[0] < now - rule.window_seconds:
            counter.popleft()

        if len(counter) >= rule.max_requests:
            if counter:
                retry_after = rule.window_seconds - (now - counter[0])
                return False, max(int(retry_after), 1)
            return False, rule.window_seconds

        # Add current request
        counter.append(now)
        return True, 0

    async def _log_security_event(
        self,
        event_type: str,
        ip_address: str,
        endpoint: str,
        user_agent: str,
        severity: str,
        details: dict[str, Any],
    ) -> None:
        """Log security event to database asynchronously."""
        try:
            await self.db.security_events.async_insert(
                event_type=event_type,
                ip_address=ip_address,
                endpoint=endpoint,
                user_agent=user_agent,
                timestamp=datetime.utcnow(),
                severity=severity,
                details=json.dumps(details) if details else None,
                tenant_id=self.tenant_id,
                created_at=datetime.utcnow(),
            )
            logger.warning(
                "security_event_logged",
                event_type=event_type,
                ip_address=ip_address,
                severity=severity,
            )

        except Exception as e:
            logger.error("failed_to_log_security_event", error=str(e))

    def get_blocked_ips(self) -> list[dict[str, Any]]:
        """Get list of currently blocked IPs."""
        blocked: list[dict[str, Any]] = []
        current_time = time.time()

        for ip, until in self.blocked_until.items():
            if until > current_time:
                blocked.append(
                    {
                        "ip_address": ip,
                        "blocked_until": datetime.fromtimestamp(until),
                        "remaining_seconds": int(until - current_time),
                    }
                )

        return blocked

    def unblock_ip(self, ip_address: str) -> bool:
        """Manually unblock an IP address."""
        if ip_address in self.blocked_until:
            del self.blocked_until[ip_address]
            self.blocked_ips.discard(ip_address)

            try:
                self.redis_client.delete(f"blocked_ip:{ip_address}")
                logger.info("ip_unblocked", ip_address=ip_address)
                return True
            except Exception as e:
                logger.error("failed_to_remove_ip_block_redis", error=str(e))

        return False
