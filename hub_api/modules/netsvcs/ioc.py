"""Thin wrapper over BlocklistStore for netsvcs IOC checking."""
from __future__ import annotations

import structlog

from hub_api.cache.client import CacheClient
from hub_api.modules.threatintel.blocklist.store import BlocklistStore

logger = structlog.get_logger()


class IOCChecker:
    """Check Indicators of Compromise via BlocklistStore."""

    def __init__(self, cache: CacheClient) -> None:
        """Initialize IOCChecker.

        Args:
            cache: CacheClient instance for Valkey access
        """
        self.store = BlocklistStore(cache=cache)

    async def check_domain(self, domain: str) -> dict:
        """Check if domain is blocked.

        Args:
            domain: Domain name to check (fail-open if error)

        Returns:
            Dict with 'blocked' bool, 'reason' str, 'feed_source' str, 'severity' str
            If not blocked, returns blocked=False with empty reason/source/severity.
        """
        try:
            verdict = await self.store.check("domain", domain)
            if verdict:
                return {
                    "blocked": True,
                    "reason": f"Blocked by {verdict.source}",
                    "feed_source": verdict.source,
                    "severity": verdict.severity,
                }
            return {
                "blocked": False,
                "reason": "",
                "feed_source": "",
                "severity": "",
            }
        except Exception as e:
            logger.warning("ioc_domain_check_error", domain=domain, error=str(e))
            # Fail open: if cache error, treat as not blocked
            return {
                "blocked": False,
                "reason": "",
                "feed_source": "",
                "severity": "",
            }

    async def check_ip(self, ip: str) -> dict:
        """Check if IP is blocked.

        Args:
            ip: IP address to check (fail-open if error)

        Returns:
            Dict with 'blocked' bool, 'reason' str, 'feed_source' str, 'severity' str
            If not blocked, returns blocked=False with empty reason/source/severity.
        """
        try:
            verdict = await self.store.check("ip", ip)
            if verdict:
                return {
                    "blocked": True,
                    "reason": f"Blocked by {verdict.source}",
                    "feed_source": verdict.source,
                    "severity": verdict.severity,
                }
            return {
                "blocked": False,
                "reason": "",
                "feed_source": "",
                "severity": "",
            }
        except Exception as e:
            logger.warning("ioc_ip_check_error", ip=ip, error=str(e))
            # Fail open: if cache error, treat as not blocked
            return {
                "blocked": False,
                "reason": "",
                "feed_source": "",
                "severity": "",
            }
