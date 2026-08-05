"""BlocklistCurator populates IOC blocklist from threat_indicators."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from hub_api.modules.sase.security.blocklist.models import IOC_TYPES, Verdict
from hub_api.modules.sase.security.blocklist.store import BlocklistStore
from hub_api.modules.sase.security.blocklist.stix_normalizer import to_stix_indicator


logger = structlog.get_logger()


# Map threat feed indicator_type to blocklist IOC_TYPES
FEED_TO_IOC_TYPE = {
    "ip": "ip",
    "domain": "domain",
    "url": "url",
    "hash": "hash",
}

# Map confidence (0-100) to severity
def confidence_to_severity(confidence: int) -> str:
    """Map feed confidence to severity level.

    Args:
        confidence: Confidence value (0-100).

    Returns:
        Severity level: low, medium, high, or critical.
    """
    if confidence <= 30:
        return "low"
    elif confidence <= 60:
        return "medium"
    elif confidence <= 85:
        return "high"
    else:
        return "critical"


@dataclass(slots=True)
class CurationStats:
    """Statistics from a curation run."""

    scanned: int
    stored: int
    deduped: int
    skipped: int


class BlocklistCurator:
    """Populate blocklist from threat_indicators table.

    Reads active indicators from threat_indicators, normalizes each to
    STIX, builds a Verdict, and stores in BlocklistStore with dedup and TTL.
    Skips unmappable indicator types without aborting.
    """

    def __init__(self, dal, store: BlocklistStore) -> None:
        """Initialize curator.

        Args:
            dal: penguin-dal DAL instance.
            store: BlocklistStore instance.
        """
        self.dal = dal
        self.store = store

    async def curate(self, tenant_id: str) -> CurationStats:
        """Curate threat_indicators into blocklist for a tenant.

        Reads active rows from threat_indicators, maps each to an IOC,
        normalizes to STIX, builds Verdict, and stores in BlocklistStore.
        Skips unmappable rows (different indicator_type) without crashing.

        Args:
            tenant_id: Tenant ID to curate for.

        Returns:
            CurationStats with counts.
        """
        stats = CurationStats(scanned=0, stored=0, deduped=0, skipped=0)

        try:
            # Read active threat_indicators for this tenant
            rows = await self.dal(
                (self.dal.threat_indicators.tenant_id == tenant_id)
                & (self.dal.threat_indicators.active == True)
            ).select()

            for row in rows:
                stats.scanned += 1
                try:
                    # Convert row to dict if needed
                    row_dict = row if isinstance(row, dict) else row.as_dict() if hasattr(row, 'as_dict') else dict(row)
                    await self.curate_one(row_dict, stats)
                except Exception as e:
                    logger.warning("sase_blocklist_curator_row_error", error=str(e))
                    stats.skipped += 1

        except Exception as e:
            logger.error("sase_blocklist_curator_read_error", error=str(e))

        logger.info(
            "sase_blocklist_curator_complete",
            scanned=stats.scanned,
            stored=stats.stored,
            deduped=stats.deduped,
            skipped=stats.skipped,
        )

        return stats

    async def curate_one(self, row: dict, stats: CurationStats) -> None:
        """Curate a single threat_indicator row.

        Args:
            row: Threat indicator row from database.
            stats: CurationStats to update (deduped, stored, skipped).

        Raises:
            ValueError: If indicator_type is unmappable.
        """
        # Map feed indicator_type to IOC type
        feed_type = row.get("indicator_type")
        ioc_type = FEED_TO_IOC_TYPE.get(feed_type)

        if not ioc_type:
            logger.warning(
                "sase_blocklist_curator_unmappable_type", indicator_type=feed_type
            )
            stats.skipped += 1
            return

        # Extract fields
        value = row.get("value")
        source = row.get("source", "unknown")
        confidence = row.get("confidence", 50)
        first_seen = row.get("first_seen")
        ttl = row.get("ttl", 3600)

        # Convert first_seen to Unix timestamp
        if isinstance(first_seen, datetime):
            first_seen_ts = int(first_seen.timestamp())
        else:
            first_seen_ts = int(first_seen) if first_seen else int(datetime.now(timezone.utc).timestamp())

        # Compute expiry
        expiry = first_seen_ts + ttl if ttl else None

        # Map confidence to severity
        severity = confidence_to_severity(confidence)

        # Build STIX indicator
        stix_indicator = to_stix_indicator(
            ioc_type, value, severity=severity, source=source, first_seen=first_seen_ts
        )

        # Build Verdict
        verdict = Verdict(
            ioc_type=ioc_type,
            value=value,
            severity=severity,
            source=source,
            stix_id=stix_indicator.id,
            first_seen=first_seen_ts,
            expiry=expiry,
        )

        # Store (dedup handled by BlocklistStore.put)
        await self.store.put(verdict)
        stats.stored += 1
