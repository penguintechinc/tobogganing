"""Security threat feeds manager."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

import aiohttp
import structlog

from .detection import DetectionLogger
from .models import FeedUpdate, ThreatIndicator
from .sources import (
    FeedSource,
    ThreatIndicator as ThreatIndicatorData,
    ThreatType,
    build_threat_indicator,
    fetch_blackweb_domains,
    fetch_blackweb_ips,
    fetch_spamhaus_drop,
    query_dnsbl,
)

logger = logging.getLogger(__name__)
slog = structlog.get_logger()


class SecurityFeedsManager:
    """Manage security threat intelligence feeds."""

    def __init__(self, db: Any) -> None:
        """Initialize security feeds manager.

        Args:
            db: penguin-dal DAL instance.
        """
        self.db = db
        self.session: aiohttp.ClientSession | None = None
        self.detection_logger = DetectionLogger(db)

        self.feed_configs = {
            FeedSource.BLACKWEB: {
                "domains_url": "https://raw.githubusercontent.com/maravento/blackweb/master/blackweb.txt",
                "ips_url": "https://raw.githubusercontent.com/maravento/blackweb/master/blackip.txt",
                "update_interval": 3600,
                "confidence": 85,
            },
            FeedSource.SPAMHAUS: {
                "drop_url": "https://www.spamhaus.org/drop/drop.txt",
                "edrop_url": "https://www.spamhaus.org/drop/edrop.txt",
                "pbl_url": "https://www.spamhaus.org/pbl/pbl.txt",
                "update_interval": 1800,
                "confidence": 95,
            },
            FeedSource.IPVOID: {
                "api_url": "https://endpoint.apivoid.com/iprep/v1/pay-as-you-go/",
                "api_key": os.getenv("IPVOID_API_KEY"),
                "update_interval": 3600,
                "confidence": 90,
            },
            FeedSource.DNSBL: {
                "providers": [
                    "zen.spamhaus.org",
                    "bl.spamcop.net",
                    "dnsbl.sorbs.net",
                    "cbl.abuseat.org",
                ],
                "update_interval": 1800,
                "confidence": 80,
            },
        }

        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.cache_ttl = 300

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=300)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def start_feed_updates(self) -> None:
        """Start automated feed updates."""
        logger.info("Starting security feeds update process")
        await self._get_session()

        tasks = []
        for source in FeedSource:
            tasks.append(self._schedule_feed_updates(source))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_feed_updates(self) -> None:
        """Stop feed updates and cleanup."""
        if self.session:
            await self.session.close()
            self.session = None

    async def _schedule_feed_updates(self, source: FeedSource) -> None:
        """Schedule periodic updates for a feed source."""
        config = self.feed_configs.get(source)
        if not config:
            return

        interval = config.get("update_interval", 3600)

        while True:
            try:
                # Use a default tenant for system-wide feeds
                await self.update_feed("00000000-0000-0000-0000-000000000000", source)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating feed {source.value}: {e}")
                await asyncio.sleep(300)

    async def update_feed(
        self, tenant_id: str, source: FeedSource
    ) -> Dict[str, int]:
        """Update a specific threat feed.

        Args:
            tenant_id: Tenant ID for tenant-scoping.
            source: Feed source to update.

        Returns:
            Stats dictionary with added/updated/removed/errors counts.
        """
        start_time = datetime.utcnow()
        stats = {"added": 0, "updated": 0, "removed": 0, "errors": 0}

        try:
            logger.info(f"Updating threat feed: {source.value}")

            update_id = str(uuid.uuid4())
            await self.db.feed_updates.async_insert(
                id=update_id,
                tenant_id=tenant_id,
                source=source.value,
                update_type="automatic",
                status="running",
                started_at=start_time,
            )

            if source == FeedSource.BLACKWEB:
                stats = await self._update_blackweb_feed(tenant_id)
            elif source == FeedSource.SPAMHAUS:
                stats = await self._update_spamhaus_feed(tenant_id)
            elif source == FeedSource.IPVOID:
                stats = await self._update_ipvoid_feed(tenant_id)
            elif source == FeedSource.DNSBL:
                stats = await self._update_dnsbl_feed(tenant_id)

            duration = int((datetime.utcnow() - start_time).total_seconds())
            await self.db(self.db.feed_updates.id == update_id).async_update(
                status="completed",
                indicators_added=stats["added"],
                indicators_updated=stats["updated"],
                indicators_removed=stats["removed"],
                duration_seconds=duration,
                completed_at=datetime.utcnow(),
            )

            slog.info(
                "feed_updated",
                source=source.value,
                added=stats["added"],
                updated=stats["updated"],
                removed=stats["removed"],
                duration_seconds=duration,
                tenant_id=tenant_id,
            )

        except Exception as e:
            duration = int((datetime.utcnow() - start_time).total_seconds())
            try:
                await self.db(self.db.feed_updates.id == update_id).async_update(
                    status="failed",
                    error_message=str(e),
                    duration_seconds=duration,
                    completed_at=datetime.utcnow(),
                )
            except Exception:
                pass

            slog.error(
                "feed_update_failed",
                source=source.value,
                error=str(e),
                tenant_id=tenant_id,
            )
            stats["errors"] = 1

        return stats

    async def _update_blackweb_feed(self, tenant_id: str) -> Dict[str, int]:
        """Update Blackweb threat feed."""
        stats = {"added": 0, "updated": 0, "removed": 0, "errors": 0}
        config = self.feed_configs[FeedSource.BLACKWEB]
        session = await self._get_session()

        domains = await fetch_blackweb_domains(session, config["domains_url"])
        for domain in domains:
            indicator = build_threat_indicator(
                indicator_type="domain",
                value=domain,
                threat_types=[ThreatType.BLACKLISTED_DOMAIN],
                source=FeedSource.BLACKWEB,
                confidence=config["confidence"],
                ttl=config["update_interval"],
                metadata={"category": "blacklisted"},
            )
            if await self._store_indicator(tenant_id, indicator):
                stats["added"] += 1

        ips = await fetch_blackweb_ips(session, config["ips_url"])
        for ip in ips:
            indicator = build_threat_indicator(
                indicator_type="ip",
                value=ip,
                threat_types=[ThreatType.BLACKLISTED_IP],
                source=FeedSource.BLACKWEB,
                confidence=config["confidence"],
                ttl=config["update_interval"],
                metadata={"category": "blacklisted"},
            )
            if await self._store_indicator(tenant_id, indicator):
                stats["added"] += 1

        return stats

    async def _update_spamhaus_feed(self, tenant_id: str) -> Dict[str, int]:
        """Update Spamhaus threat feed."""
        stats = {"added": 0, "updated": 0, "removed": 0, "errors": 0}
        config = self.feed_configs[FeedSource.SPAMHAUS]
        session = await self._get_session()

        for list_type, url in [("DROP", config["drop_url"]), ("EDROP", config["edrop_url"])]:
            networks = await fetch_spamhaus_drop(session, url)
            for network in networks:
                indicator = build_threat_indicator(
                    indicator_type="ip",
                    value=network,
                    threat_types=[ThreatType.SPAM_DOMAIN, ThreatType.REPUTATION_IP],
                    source=FeedSource.SPAMHAUS,
                    confidence=config["confidence"],
                    ttl=config["update_interval"],
                    metadata={"list": list_type},
                )
                if await self._store_indicator(tenant_id, indicator):
                    stats["added"] += 1

        return stats

    async def _update_ipvoid_feed(self, tenant_id: str) -> Dict[str, int]:
        """Update IPVoid reputation feed (real-time only)."""
        logger.info("IPVoid configured for real-time lookups only")
        return {"added": 0, "updated": 0, "removed": 0, "errors": 0}

    async def _update_dnsbl_feed(self, tenant_id: str) -> Dict[str, int]:
        """Update DNSBL reputation feed (real-time only)."""
        logger.info("DNSBL configured for real-time lookups only")
        return {"added": 0, "updated": 0, "removed": 0, "errors": 0}

    async def _store_indicator(
        self, tenant_id: str, indicator: ThreatIndicatorData
    ) -> bool:
        """Store threat indicator in database.

        Args:
            tenant_id: Tenant ID.
            indicator: Threat indicator to store.

        Returns:
            True if added (new), False if updated or error.
        """
        try:
            existing = await self.db(
                (self.db.threat_indicators.value == indicator.value)
                & (self.db.threat_indicators.source == indicator.source.value)
                & (self.db.threat_indicators.tenant_id == tenant_id)
            ).async_select()

            if existing:
                await self.db(
                    (self.db.threat_indicators.value == indicator.value)
                    & (self.db.threat_indicators.tenant_id == tenant_id)
                ).async_update(
                    threat_types=json.dumps([t.value for t in indicator.threat_types]),
                    confidence=indicator.confidence,
                    last_seen=indicator.last_seen,
                    ttl=indicator.ttl,
                    metadata=json.dumps(indicator.metadata),
                    updated_at=datetime.utcnow(),
                )
                return False

            indicator_id = str(uuid.uuid4())
            await self.db.threat_indicators.async_insert(
                id=indicator_id,
                tenant_id=tenant_id,
                indicator_type=indicator.indicator_type,
                value=indicator.value,
                threat_types=json.dumps([t.value for t in indicator.threat_types]),
                source=indicator.source.value,
                confidence=indicator.confidence,
                first_seen=indicator.first_seen,
                last_seen=indicator.last_seen,
                ttl=indicator.ttl,
                metadata=json.dumps(indicator.metadata),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to store indicator {indicator.value}: {e}")
            return False

    async def check_threat_indicator(
        self, tenant_id: str, value: str, indicator_type: str | None = None
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """Check if a value (domain/IP) is a known threat indicator.

        Args:
            tenant_id: Tenant ID.
            value: Value to check (domain or IP).
            indicator_type: Type hint (domain/ip) or auto-detect.

        Returns:
            (is_threat, threat_details_list)
        """
        threats = []

        if not indicator_type:
            try:
                ipaddress.ip_address(value)
                indicator_type = "ip"
            except ValueError:
                indicator_type = "domain"

        query = (
            (self.db.threat_indicators.value == value)
            & (self.db.threat_indicators.active == True)
            & (self.db.threat_indicators.tenant_id == tenant_id)
        )

        if indicator_type:
            query &= self.db.threat_indicators.indicator_type == indicator_type

        indicators = await self.db(query).async_select()

        for indicator in indicators:
            threats.append(
                {
                    "value": indicator["value"],
                    "threat_types": (
                        json.loads(indicator["threat_types"])
                        if indicator.get("threat_types")
                        else []
                    ),
                    "source": indicator["source"],
                    "confidence": indicator["confidence"],
                    "first_seen": (
                        indicator["first_seen"].isoformat()
                        if indicator.get("first_seen")
                        else None
                    ),
                    "last_seen": (
                        indicator["last_seen"].isoformat()
                        if indicator.get("last_seen")
                        else None
                    ),
                    "metadata": (
                        json.loads(indicator["metadata"])
                        if indicator.get("metadata")
                        else {}
                    ),
                }
            )

        return len(threats) > 0, threats
