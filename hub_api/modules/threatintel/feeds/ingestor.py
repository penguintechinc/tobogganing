"""Fetch configured feed source URLs and store parsed indicators.

Bridges FeedSourceManager (user-configured MISP/STIX/TAXII/CSV sources) to
the existing parser + storage stack (parsers.py, SecurityFeedsManager).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import aiohttp
import structlog

from .manager import SecurityFeedsManager
from .parsers import parse_misp_feed, parse_stix_bundle, parse_threat_csv
from .sources import FeedSource
from .url_safety import assert_safe_feed_url

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

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5


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

    SSRF guard: re-validates the URL (scheme + resolved-address checks)
    immediately before every actual network request — the initial fetch and
    each redirect hop — since DNS can rebind between the create-time check
    and now. Redirects are never auto-followed by aiohttp
    (allow_redirects=False); each hop's Location is validated before being
    fetched, up to _MAX_REDIRECTS, else the ingest fails closed.

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
        UnsafeFeedURLError: If the URL or any redirect target fails the
            SSRF guard.
        RuntimeError: If the feed source returns a non-200 response, a
            redirect with no/invalid Location header, or too many redirects.
    """
    if source_type not in FEED_SOURCE_TYPES:
        raise ValueError(f"unsupported source_type: {source_type}")

    feed_source = SOURCE_TYPE_TO_FEED_SOURCE[source_type]
    stats = {"added": 0, "updated": 0, "errors": 0}

    current_url = url
    indicators: list[Any] = []

    for _hop in range(_MAX_REDIRECTS + 1):
        # SSRF guard, checkpoint 2: re-validate every hop right before the
        # actual request (TOCTOU-safe — DNS may have changed since create
        # time or since the previous hop).
        await assert_safe_feed_url(current_url)

        async with session.get(
            current_url,
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=False,
        ) as resp:
            if resp.status in _REDIRECT_STATUSES:
                location = resp.headers.get("Location")
                if not location:
                    raise RuntimeError("redirect response missing Location header")
                current_url = urljoin(current_url, location)
                continue

            if resp.status != 200:
                # Deliberately omit the URL (feed URLs commonly carry auth
                # tokens/API keys as query params — never log those) and the
                # response body (upstream detail must not surface to callers).
                raise RuntimeError(f"non-200 response from feed source: HTTP {resp.status}")

            if source_type == "csv":
                content = await resp.text()
                indicators = parse_threat_csv(content, source=feed_source)
            elif source_type == "misp":
                payload = await resp.json(content_type=None)
                indicators = parse_misp_feed(payload, source=feed_source)
            else:  # stix, taxii
                payload = await resp.json(content_type=None)
                indicators = parse_stix_bundle(payload, source=feed_source)
            break
    else:
        raise RuntimeError("too many redirects")

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
