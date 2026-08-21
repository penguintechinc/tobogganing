"""Fetch configured feed source URLs and store parsed indicators.

Bridges FeedSourceManager (user-configured MISP/STIX/TAXII/CSV sources) to
the existing parser + storage stack (parsers.py, SecurityFeedsManager).
"""

from __future__ import annotations

from typing import Any

import aiohttp
import structlog

from .manager import SecurityFeedsManager
from .parsers import parse_misp_feed, parse_stix_bundle, parse_threat_csv
from .sources import FeedSource

logger = structlog.get_logger()

# TAXII 2.x collection endpoints serve STIX 2.x bundles over HTTP, so TAXII
# sources are parsed identically to STIX for this MVP ingestion path. Full
# TAXII 2.1 collection discovery/paging/polling is out of scope.
SOURCE_TYPE_TO_FEED_SOURCE: dict[str, FeedSource] = {
    "misp": FeedSource.MISP,
    "stix": FeedSource.STIX,
    "taxii": FeedSource.TAXII,
    "csv": FeedSource.CSV,
}

FEED_SOURCE_TYPES = frozenset(SOURCE_TYPE_TO_FEED_SOURCE)


async def ingest_feed_source(
    db: Any,
    tenant_id: str,
    source_type: str,
    url: str,
    session: aiohttp.ClientSession,
) -> dict[str, int]:
    """Fetch a configured feed source URL and store parsed indicators.

    Dispatches to the parser matching source_type, then stores every parsed
    indicator into threat_indicators (tenant-scoped) via
    SecurityFeedsManager, reusing the existing dedup/update logic.

    Args:
        db: penguin-dal AsyncDB instance.
        tenant_id: Tenant ID to scope stored indicators to.
        source_type: One of "misp", "stix", "taxii", "csv".
        url: Feed source URL to fetch.
        session: aiohttp session to use for the fetch.

    Returns:
        Stats dict with added/updated/errors counts.

    Raises:
        ValueError: If source_type is not supported.
        RuntimeError: If the feed source returns a non-200 response.
    """
    if source_type not in FEED_SOURCE_TYPES:
        raise ValueError(f"unsupported source_type: {source_type}")

    feed_source = SOURCE_TYPE_TO_FEED_SOURCE[source_type]
    stats = {"added": 0, "updated": 0, "errors": 0}

    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from feed source {url}")

        if source_type == "csv":
            content = await resp.text()
            indicators = parse_threat_csv(content, source=feed_source)
        elif source_type == "misp":
            payload = await resp.json(content_type=None)
            indicators = parse_misp_feed(payload, source=feed_source)
        else:  # stix, taxii
            payload = await resp.json(content_type=None)
            indicators = parse_stix_bundle(payload, source=feed_source)

    manager = SecurityFeedsManager(db)
    for indicator in indicators:
        try:
            added = await manager._store_indicator(tenant_id, indicator)
            if added:
                stats["added"] += 1
            else:
                stats["updated"] += 1
        except Exception as e:
            logger.warning(
                "feed_source_indicator_store_error",
                error=str(e),
                source_type=source_type,
                tenant_id=tenant_id,
            )
            stats["errors"] += 1

    return stats
