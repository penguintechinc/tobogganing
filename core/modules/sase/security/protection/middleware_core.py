"""Main security middleware integrating all protection mechanisms."""
from __future__ import annotations

import time
from typing import Any

import redis
import structlog

from .ddos import DDoSProtection
from .ratelimit import RateLimiter

logger = structlog.get_logger()


class SecurityMiddleware:
    """Main security middleware integrating all protection mechanisms."""

    def __init__(
        self,
        db: Any,
        redis_client: redis.Redis | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Initialize security middleware.

        Args:
            db: penguin-dal DAL instance for database operations.
            redis_client: Redis client for caching and rate limiting.
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

        # Initialize protection mechanisms
        self.rate_limiter = RateLimiter(
            db=db,
            redis_client=self.redis_client,
            tenant_id=tenant_id,
        )
        self.ddos_protection = DDoSProtection(
            rate_limiter=self.rate_limiter,
            redis_client=self.redis_client,
            tenant_id=tenant_id,
        )

    def process_request(
        self, request_info: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        """Process incoming request through security layers.

        Args:
            request_info: Dict containing ip_address, endpoint, user_agent, etc.

        Returns:
            Tuple of (allowed, response_headers).
        """
        ip_address = request_info.get("ip_address", "")
        endpoint = request_info.get("endpoint", "")
        user_agent = request_info.get("user_agent", "")

        # Check rate limits
        allowed, violated_rule, retry_after = self.rate_limiter.is_allowed(
            ip_address, endpoint, user_agent
        )

        if not allowed:
            headers = {
                "X-RateLimit-Limit": (
                    str(violated_rule.max_requests) if violated_rule else "0"
                ),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                "Retry-After": str(retry_after),
            }
            logger.warning(
                "request_rate_limited",
                ip_address=ip_address,
                endpoint=endpoint,
                retry_after=retry_after,
            )
            return False, headers

        # Check for DDoS patterns
        is_attack, attack_type, severity = self.ddos_protection.detect_ddos_attack(
            ip_address, endpoint, user_agent
        )

        if is_attack:
            self.ddos_protection.mitigate_attack(ip_address, attack_type, severity)
            headers = {
                "X-Security-Block": "DDoS-Protection",
                "X-Block-Reason": attack_type,
            }
            logger.warning(
                "request_blocked_ddos",
                ip_address=ip_address,
                endpoint=endpoint,
                attack_type=attack_type,
                severity=severity,
            )
            return False, headers

        # Request allowed
        headers = {
            "X-RateLimit-Remaining": (
                str(violated_rule.max_requests - 1) if violated_rule else "999"
            )
        }
        return True, headers

    def get_blocked_ips(self) -> list[dict[str, Any]]:
        """Get list of currently blocked IPs.

        Returns:
            List of blocked IP entries with block details.
        """
        return self.rate_limiter.get_blocked_ips()

    def unblock_ip(self, ip_address: str) -> bool:
        """Manually unblock an IP address.

        Args:
            ip_address: IP address to unblock.

        Returns:
            True if unblocked successfully, False otherwise.
        """
        return self.rate_limiter.unblock_ip(ip_address)
