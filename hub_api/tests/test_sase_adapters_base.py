"""Test adapter base classes."""
from __future__ import annotations

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.sase.security.adapters.base import (
    AdapterHit,
    AdapterStats,
    AnalysisAdapter,
)
from hub_api.modules.sase.security.blocklist.store import BlocklistStore


@pytest.fixture
def cache_client() -> CacheClient:
    """CacheClient fixture with unreachable host (for fail-soft testing)."""
    return CacheClient(host="127.0.0.1", port=6399)


class _StubAdapter(AnalysisAdapter):
    """Stub adapter for testing."""

    def __init__(self) -> None:
        """Initialize stub adapter."""
        self.source = "stub"

    def parse(self, raw: str) -> list[AdapterHit]:
        """Parse stub input: lines starting with 'ip:', 'domain:', 'url:', 'hash:'.

        Args:
            raw: Raw input string.

        Returns:
            List of AdapterHits.
        """
        hits = []
        for line in raw.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            ioc_type, value = parts
            if ioc_type not in ("ip", "domain", "url", "hash"):
                continue
            hit = AdapterHit(
                ioc_type=ioc_type,
                value=value.strip(),
                severity="high",
                first_seen=1234567890,
                detail=None,
            )
            hits.append(hit)
        return hits


@pytest.mark.asyncio
async def test_adapter_base_ingest_success(cache_client: CacheClient) -> None:
    """Test adapter ingest with successful hits."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    raw = "ip:192.0.2.1\ndomain:example.com"
    stats = await adapter.ingest(raw, store)

    assert stats.source == "stub"
    assert stats.scanned == 2
    assert stats.stored == 2
    assert stats.skipped == 0

    # Verify stored verdicts
    verdict_ip = await store.check("ip", "192.0.2.1")
    assert verdict_ip is not None
    assert verdict_ip.source == "stub"
    assert verdict_ip.severity == "high"

    verdict_domain = await store.check("domain", "example.com")
    assert verdict_domain is not None
    assert verdict_domain.source == "stub"


@pytest.mark.asyncio
async def test_adapter_base_ingest_with_normalization_error(
    cache_client: CacheClient,
) -> None:
    """Test adapter ingest handles normalization errors gracefully."""

    class _FailingAdapter(AnalysisAdapter):
        """Adapter that fails on certain inputs."""

        source = "failing"

        def parse(self, raw: str) -> list[AdapterHit]:
            """Parse and yield hits that may raise during normalization."""
            # Return a hit with an invalid ioc_type to trigger a ValueError
            return [
                AdapterHit(
                    ioc_type="invalid_type",
                    value="192.0.2.1",
                    severity="high",
                    first_seen=1234567890,
                    detail=None,
                )
            ]

    adapter = _FailingAdapter()
    store = BlocklistStore(cache=cache_client)

    raw = "any input"
    stats = await adapter.ingest(raw, store)

    # Should skip the hit with invalid ioc_type, no crash
    assert stats.source == "failing"
    assert stats.scanned == 1
    assert stats.stored == 0
    assert stats.skipped == 1


@pytest.mark.asyncio
async def test_adapter_base_ingest_empty_input(cache_client: CacheClient) -> None:
    """Test adapter ingest with empty input."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    stats = await adapter.ingest("", store)

    assert stats.source == "stub"
    assert stats.scanned == 0
    assert stats.stored == 0
    assert stats.skipped == 0
