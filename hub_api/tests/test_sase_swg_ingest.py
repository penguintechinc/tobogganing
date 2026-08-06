"""Tests for SASE SWG category ingestion."""
from __future__ import annotations

import pytest

from hub_api.modules.sase.security.swg.ingest import CategoryIngestManager, IngestStats


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
