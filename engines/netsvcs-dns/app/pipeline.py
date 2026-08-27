"""Shared DNS resolution pipeline for DoH and DoT.

This is the core resolve logic that both HTTP and TLS transports feed into.
It composes the S1 components (resolver, router, cache) with resilience modes,
IOC checking, and split-horizon routing.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from dataclasses import dataclass

from app.resolver import DNSResolver
from app.router import SelectiveRouter, TokenClaims
from app.cache import CacheManager
from app.manager_client import ManagerClient
from app.metrics import MetricsReporter

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ResolvePipelineConfig:
    """Configuration for the resolve pipeline."""

    cache_ttl_hours: int = 24
    cache_ttl_seconds: int = 300


class ResolvePipeline:
    """Composable DNS resolution pipeline.

    Orchestrates:
    1. Resilience mode detection (normal/cached/degraded)
    2. IOC blocking (S3 wiring hook)
    3. Cache lookup
    4. Split-horizon routing + token permission checks (S3 wiring hook)
    5. Custom zone or upstream recursion
    6. Cache storage (on success)
    7. Metrics recording (hook)
    """

    def __init__(
        self,
        resolver: DNSResolver,
        router: SelectiveRouter,
        cache: CacheManager,
        manager_client: ManagerClient | None = None,
        config: ResolvePipelineConfig | None = None,
    ) -> None:
        """Initialize the resolve pipeline.

        Args:
            resolver: DNSResolver instance for upstream queries.
            router: SelectiveRouter for zone matching and permissions.
            cache: CacheManager for result caching.
            manager_client: ManagerClient for control-plane integration (S3+).
            config: Pipeline configuration.
        """
        self.resolver = resolver
        self.router = router
        self.cache = cache
        self.manager_client = manager_client
        self.config = config or ResolvePipelineConfig()

        # Operational mode tracking
        self._mode = "normal"
        self._last_mode_check = time.time()

    async def resolve_query(
        self,
        name: str,
        record_type: str,
        token: str | None = None,
        *,
        mode: str = "normal",
    ) -> dict[str, Any]:
        """Resolve a DNS query through the full pipeline.

        Returns Google DoH-JSON response format:
        {
            "Status": <0|2|3|5>,  # 0=NOERROR, 2=SERVFAIL, 3=NXDOMAIN, 5=REFUSED
            "Question": [{"name": domain, "type": record_type}],
            "Answer": [{"name": domain, "type": record_type, "TTL": ttl, "data": value}]
        }

        Args:
            name: Domain name to resolve.
            record_type: DNS record type (A, AAAA, CNAME, etc.).
            token: Optional Bearer token for authorization.
            mode: Operational mode (normal/cached/degraded).

        Returns:
            DNS response dict in Google DoH-JSON format.
        """
        start_time = time.time()
        query = {"name": name, "type": record_type}

        logger.info(f"resolve_query: {name} {record_type} mode={mode}")

        # Step 1: Cache lookup
        cached_result = await self.cache.get(name, record_type)
        if cached_result:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"cache_hit: {name} {record_type} ({elapsed_ms:.1f}ms)")
            MetricsReporter.record_cache_hit()
            return cached_result

        MetricsReporter.record_cache_miss()

        # Step 2: IOC check (S3 HOOK: wire to control-plane CheckIOC gRPC)
        # For S2, returns False (not blocked); S3 replaces with real gRPC call
        if await self.ioc_check(name):
            logger.warning(f"ioc_blocked: {name}")
            response = {
                "Status": 3,  # NXDOMAIN for blocked domains
                "Question": [query],
                "Answer": [],
            }
            MetricsReporter.record_ioc_block()
            return response

        # Step 3: Extract token claims (S3 HOOK: validate via control-plane ValidateToken gRPC)
        # For S2, returns None; S3 replaces with real JWT validation
        token_claims = await self._claims_for_token(token)

        # Step 4: Split-horizon routing + permission check
        if not self.router.should_serve_zone(name, token_claims, mode):
            logger.warning(f"refused_zone: {name} mode={mode}")
            response = {
                "Status": 5,  # REFUSED
                "Question": [query],
                "Answer": [],
            }
            MetricsReporter.record_error("refused")
            return response

        # Step 5: Try custom zones first, then upstream
        zone_records = self.router.get_zone_records(name)

        if zone_records is not None:
            logger.info(f"serving_custom_zone: {name}")
            result = self.resolver.resolve_custom_zone(name, record_type, zone_records)
        else:
            logger.info(f"resolving_upstream: {name}")
            result = await self.resolver.resolve(name, record_type)

        # Step 6: Cache on success (Status 0)
        if result.get("Status") == 0:
            await self.cache.set(
                name, record_type, result, ttl=self.config.cache_ttl_seconds
            )

        elapsed_ms = (time.time() - start_time) * 1000
        elapsed_seconds = elapsed_ms / 1000.0
        MetricsReporter.record_query_latency(elapsed_seconds)
        MetricsReporter.record_query(record_type)

        logger.info(
            f"resolve_complete: {name} {record_type} status={result.get('Status')} "
            f"elapsed_ms={elapsed_ms:.1f}"
        )

        return result

    async def ioc_check(self, name: str) -> bool:
        """Check if domain is blocked by IOC feeds via control plane.

        Uses control-plane CheckIOC gRPC with fail-open posture:
        any error → returns False (allows resolution).
        This ensures DNS never hangs due to control-plane unavailability.

        Args:
            name: Domain to check.

        Returns:
            True if domain is IOC-blocked, False otherwise (or on error).
        """
        if not self.manager_client:
            return False

        result = await self.manager_client.check_ioc(name)
        return result.get("blocked", False)

    async def _claims_for_token(self, token: str | None) -> TokenClaims | None:
        """Extract and validate token claims via control plane.

        Delegates token validation to the control plane's ValidateToken RPC.
        The control plane returns allowed_zone_ids based on the token's tenant+teams.

        Do NOT decode or verify the token locally with verify_signature=False.
        The control plane is the authoritative token validator.

        Fails closed: returns None on any error (invalid/unvalidatable token → no claims).

        Args:
            token: Bearer token (without 'Bearer ' prefix).

        Returns:
            TokenClaims if valid token, None otherwise (or on error).
        """
        if not token or not self.manager_client:
            return None

        result = await self.manager_client.validate_token(token)

        if not result.get("valid"):
            logger.debug(f"Token validation failed: {result.get('reason', 'unknown')}")
            return None

        # Token is valid; extract claims from control-plane response
        return TokenClaims(
            teams=[],  # Teams would be in the token itself; for now, empty
            allowed_zone_ids=result.get("allowed_zone_ids", []),
            role=None,  # Role would be in the token itself; for now, None
        )


    async def close(self) -> None:
        """Clean up pipeline resources."""
        await self.cache.disconnect()
