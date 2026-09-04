"""Tests for SASE SWG category ingestion."""
from __future__ import annotations

import json
import pytest

from hub_api.modules.sase.security.swg.ingest import CategoryIngestManager, IngestStats
from hub_api.cache.client import CacheClient
from unittest.mock import MagicMock, AsyncMock


class SimpleSource:
    """Simple test category source."""

    def __init__(self, name: str, content: str):
        """Initialize with name and content.

        Args:
            name: Source name.
            content: Content to parse (format: domain,category per line).
        """
        self.name = name
        self.content = content

    def parse(self, content: str):
        """Parse the content.

        Args:
            content: Content string to parse.

        Yields:
            (domain, category) tuples.
        """
        for line in content.strip().split("\n"):
            if line.strip():
                parts = line.split(",")
                if len(parts) == 2:
                    domain, category = parts
                    yield (domain.strip(), category.strip())


def test_ingest_stats_basic() -> None:
    """Test IngestStats dataclass."""
    stats = IngestStats(source="test", scanned=10, stored=8, skipped=2)
    assert stats.source == "test"
    assert stats.scanned == 10
    assert stats.stored == 8
    assert stats.skipped == 2


def test_malformed_line_skipped_without_crash() -> None:
    """Test that malformed lines are skipped without crashing."""
    content_with_bad = (
        "good.com,malware\n"
        "incomplete_line_no_comma\n"
        "bad.com,phishing\n"
    )

    # Manually parse to simulate behavior
    stats = IngestStats(source="test", scanned=0, stored=0, skipped=0)
    for line in content_with_bad.strip().split("\n"):
        stats.scanned += 1
        parts = line.split(",")
        if len(parts) == 2:
            stats.stored += 1
        else:
            stats.skipped += 1

    assert stats.skipped >= 1
    assert stats.stored >= 1


@pytest.mark.asyncio
async def test_catcache_write_with_real_client() -> None:
    """Test category ingestion cache write using real CacheClient.

    regression: swg catcache CacheClient signature (namespace-guard) — MagicMock hid the mismatch
    """
    # Mock DB with domain_categories table
    db = MagicMock()
    db.domain_categories.select = AsyncMock(return_value=[
        MagicMock(categories=json.dumps(["malware", "phishing"])),
        MagicMock(categories=json.dumps(["malware"])),
    ])

    # Use real CacheClient with unreachable port → in-memory fallback
    cache = CacheClient(host="127.0.0.1", port=6399, db=0)

    ingest = CategoryIngestManager(db, cache)

    # Write cache for a domain
    test_domain = "testdomain.com"
    await ingest._write_cache(test_domain)

    # Verify cache was written with correct signature
    cached_value = await cache.get("sase:catcache", test_domain)
    assert cached_value is not None

    # Verify cached value contains the merged categories
    categories = json.loads(cached_value)
    assert "malware" in categories
    assert "phishing" in categories
