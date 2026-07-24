"""DDoS protection with advanced detection and mitigation."""
from __future__ import annotations

import re
import time
from typing import Any

import redis
import structlog

from .ratelimit import RateLimiter

logger = structlog.get_logger()


class DDoSProtection:
    """DDoS protection with advanced detection and mitigation."""

    def __init__(
        self,
        rate_limiter: RateLimiter,
        redis_client: redis.Redis | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Initialize DDoS protection.

        Args:
            rate_limiter: RateLimiter instance for blocking and logging.
            redis_client: Redis client for tracking attack patterns.
            tenant_id: Tenant ID for multi-tenant scoping.
        """
        self.rate_limiter = rate_limiter
        self.redis_client = redis_client or rate_limiter.redis_client
        self.db = rate_limiter.db
        self.tenant_id = tenant_id

        # DDoS detection thresholds
        self.connection_threshold = 100
        self.request_threshold = 1000
        self.time_window = 60

        # Pattern detection regex patterns
        self.suspicious_patterns = [
            r"\.php$",
            r"wp-admin",
            r"\.asp$",
            r"sql",
            r"<script",
            r"union.*select",
            r"etc/passwd",
        ]

        # Geolocation-based rules
        self.blocked_countries: list[str] = []
        self.monitored_countries: list[str] = []

    def detect_ddos_attack(
        self, ip_address: str, endpoint: str, user_agent: str
    ) -> tuple[bool, str, str]:
        """Detect potential DDoS attack patterns.

        Args:
            ip_address: Client IP address.
            endpoint: Request endpoint/path.
            user_agent: Client user agent.

        Returns:
            Tuple of (is_attack, attack_type, severity).
        """
        attack_indicators: list[tuple[str, str]] = []

        # Volume-based detection
        if self._check_volume_attack(ip_address):
            attack_indicators.append(("volume", "high"))

        # Pattern-based detection
        if self._check_suspicious_patterns(endpoint, user_agent):
            attack_indicators.append(("pattern", "medium"))

        # Behavioral analysis
        if self._check_behavioral_anomaly(ip_address, endpoint):
            attack_indicators.append(("behavioral", "medium"))

        # Distributed attack detection
        if self._check_distributed_attack():
            attack_indicators.append(("distributed", "critical"))

        if attack_indicators:
            severities = [indicator[1] for indicator in attack_indicators]
            if "critical" in severities:
                severity = "critical"
            elif "high" in severities:
                severity = "high"
            else:
                severity = "medium"

            attack_types = ",".join([indicator[0] for indicator in attack_indicators])
            return True, attack_types, severity

        return False, "", ""

    def _check_volume_attack(self, ip_address: str) -> bool:
        """Check for volume-based attacks from a single IP."""
        try:
            key = f"ddos_volume:{ip_address}"
            now = int(time.time())
            window_start = now - self.time_window

            # Count requests in the time window
            self.redis_client.zremrangebyscore(key, 0, window_start)
            count = self.redis_client.zcard(key)

            # Add current request
            self.redis_client.zadd(key, {str(now): now})
            self.redis_client.expire(key, self.time_window)

            return count > self.request_threshold

        except Exception as e:
            logger.error("volume_attack_detection_error", error=str(e))
            return False

    def _check_suspicious_patterns(self, endpoint: str, user_agent: str) -> bool:
        """Check for suspicious request patterns."""
        # Check endpoint against suspicious patterns
        for pattern in self.suspicious_patterns:
            try:
                if re.search(pattern, endpoint, re.IGNORECASE):
                    return True
            except Exception as e:
                logger.warning("regex_pattern_error", error=str(e), pattern=pattern)
                continue

        # Check user agent patterns
        suspicious_ua_patterns = [
            r"bot",
            r"crawler",
            r"spider",
            r"scanner",
            r"sqlmap",
            r"nikto",
            r"masscan",
        ]

        for pattern in suspicious_ua_patterns:
            try:
                if re.search(pattern, user_agent, re.IGNORECASE):
                    return True
            except Exception as e:
                logger.warning("ua_pattern_error", error=str(e), pattern=pattern)
                continue

        return False

    def _check_behavioral_anomaly(self, ip_address: str, endpoint: str) -> bool:
        """Check for behavioral anomalies."""
        try:
            key = f"ddos_behavior:{ip_address}"

            # Track unique endpoints accessed
            self.redis_client.sadd(key, endpoint)
            self.redis_client.expire(key, 300)

            # Check if accessing too many different endpoints
            unique_endpoints = self.redis_client.scard(key)
            if unique_endpoints > 20:
                return True

            # Check request timing patterns
            timing_key = f"ddos_timing:{ip_address}"
            now = time.time()

            # Get last few request times
            last_requests = self.redis_client.lrange(timing_key, 0, 9)

            # Add current request
            self.redis_client.lpush(timing_key, now)
            self.redis_client.ltrim(timing_key, 0, 9)
            self.redis_client.expire(timing_key, 60)

            # Check for suspiciously regular timing (bot behavior)
            if len(last_requests) >= 5:
                intervals: list[float] = []
                prev_time = now
                for req_time in last_requests:
                    interval = prev_time - float(req_time)
                    intervals.append(interval)
                    prev_time = float(req_time)

                # Calculate variance in intervals
                if len(intervals) > 1:
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum(
                        (x - avg_interval) ** 2 for x in intervals
                    ) / len(intervals)

                    # Low variance indicates bot-like behavior
                    if variance < 0.1 and avg_interval < 2:
                        return True

            return False

        except Exception as e:
            logger.error("behavioral_anomaly_detection_error", error=str(e))
            return False

    def _check_distributed_attack(self) -> bool:
        """Check for distributed DDoS attacks."""
        try:
            key = "ddos_distributed"
            now = int(time.time())
            window_start = now - 60

            # Count unique IPs making requests
            unique_ips_key = f"{key}:ips"

            # Check if we have too many unique IPs in recent requests
            self.redis_client.zremrangebyscore(unique_ips_key, 0, window_start)
            unique_ip_count = self.redis_client.zcard(unique_ips_key)

            # If more than 50 unique IPs in 1 minute, consider it distributed
            return unique_ip_count > 50

        except Exception as e:
            logger.error("distributed_attack_detection_error", error=str(e))
            return False

    def mitigate_attack(
        self, ip_address: str, attack_type: str, severity: str
    ) -> None:
        """Implement DDoS mitigation measures.

        Args:
            ip_address: IP address to mitigate.
            attack_type: Type of attack detected.
            severity: Severity level of attack.
        """
        # Block duration based on severity
        duration_map = {"low": 300, "medium": 900, "high": 3600, "critical": 7200}

        block_duration = duration_map.get(severity, 300)

        # Block the IP
        self.rate_limiter._block_ip(ip_address, block_duration)

        # Log the attack
        self.rate_limiter._log_security_event(
            "ddos_attack",
            ip_address,
            "/",
            "",
            severity,
            {
                "attack_type": attack_type,
                "mitigation": "ip_block",
                "block_duration": block_duration,
            },
        )

        # Additional mitigations based on severity
        if severity in ["high", "critical"]:
            self._enable_emergency_mode()

        # Notify administrators
        self._notify_attack(ip_address, attack_type, severity)

    def _enable_emergency_mode(self) -> None:
        """Enable emergency mode with stricter rate limits."""
        try:
            self.redis_client.setex("emergency_mode", 3600, "1")
            logger.critical("ddos_emergency_mode_enabled", duration_seconds=3600)
        except Exception as e:
            logger.error("failed_to_enable_emergency_mode", error=str(e))

    def _notify_attack(
        self, ip_address: str, attack_type: str, severity: str
    ) -> None:
        """Send notifications about DDoS attacks."""
        logger.critical(
            "ddos_attack_detected",
            ip_address=ip_address,
            attack_type=attack_type,
            severity=severity,
        )
