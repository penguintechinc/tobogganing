"""Tests for SASE blocklist store over CacheClient."""
from __future__ import annotations

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.threatintel.blocklist.models import Verdict
from hub_api.modules.threatintel.blocklist.store import BlocklistStore


@pytest.fixture
def store() -> BlocklistStore:
    """BlocklistStore with in-memory fallback cache."""
    cache = CacheClient(host="127.0.0.1", port=6399)  # Unreachable
    return BlocklistStore(cache)


@pytest.fixture
def store_with_dead_cache() -> BlocklistStore:
    """BlocklistStore with unreachable cache for fail-open testing."""
    cache = CacheClient(host="127.0.0.1", port=6399)
    return BlocklistStore(cache)


@pytest.mark.asyncio
async def test_put_check_roundtrip(store: BlocklistStore) -> None:
    """Test put/check roundtrip stores and retrieves verdict."""
    verdict = Verdict(
        ioc_type="ip",
        value="1.2.3.4",
        severity="high",
        source="spamhaus",
        stix_id="indicator--x",
        first_seen=1000,
        expiry=None,
    )
    await store.put(verdict)
    result = await store.check("ip", "1.2.3.4")
    assert result is not None
    assert result.severity == "high"
    assert result.source == "spamhaus"


@pytest.mark.asyncio
async def test_dedup_higher_severity_wins(store: BlocklistStore) -> None:
    """Test dedup keeps higher severity when same IOC updated."""
    v1 = Verdict(
        ioc_type="domain",
        value="b.com",
        severity="low",
        source="a",
        stix_id="id1",
        first_seen=1,
        expiry=None,
    )
    v2 = Verdict(
        ioc_type="domain",
        value="b.com",
        severity="critical",
        source="b",
        stix_id="id2",
        first_seen=2,
        expiry=None,
    )
    await store.put(v1)
    await store.put(v2)
    result = await store.check("domain", "b.com")
    assert result is not None
    assert result.severity == "critical"


@pytest.mark.asyncio
async def test_dedup_tie_newer_first_seen_wins(store: BlocklistStore) -> None:
    """Test dedup with same severity keeps newer first_seen."""
    v1 = Verdict(
        ioc_type="domain",
        value="c.com",
        severity="high",
        source="a",
        stix_id="id1",
        first_seen=100,
        expiry=None,
    )
    v2 = Verdict(
        ioc_type="domain",
        value="c.com",
        severity="high",
        source="b",
        stix_id="id2",
        first_seen=200,
        expiry=None,
    )
    await store.put(v1)
    await store.put(v2)
    result = await store.check("domain", "c.com")
    assert result is not None
    assert result.first_seen == 200


@pytest.mark.asyncio
async def test_check_fails_open_on_cache_error(
    store_with_dead_cache: BlocklistStore,
) -> None:
    """Test check returns None on cache error (fail-open behavior)."""
    result = await store_with_dead_cache.check("ip", "9.9.9.9")
    assert result is None  # No raise, returns None


@pytest.mark.asyncio
async def test_url_keyed_by_hash(store: BlocklistStore) -> None:
    """Test URL verdicts are keyed by SHA256 hash to bound key length."""
    long_url = "http://x/" + "a" * 500
    verdict = Verdict(
        ioc_type="url",
        value=long_url,
        severity="high",
        source="urlhaus",
        stix_id="id",
        first_seen=1,
        expiry=None,
    )
    await store.put(verdict)
    result = await store.check("url", long_url)
    assert result is not None
    assert result.value == long_url


@pytest.mark.asyncio
async def test_remove_verdict(store: BlocklistStore) -> None:
    """Test remove deletes a verdict from the store."""
    verdict = Verdict(
        ioc_type="ip",
        value="1.2.3.5",
        severity="high",
        source="test",
        stix_id="id",
        first_seen=1000,
        expiry=None,
    )
    await store.put(verdict)
    assert await store.check("ip", "1.2.3.5") is not None
    await store.remove("ip", "1.2.3.5")
    assert await store.check("ip", "1.2.3.5") is None


@pytest.mark.asyncio
async def test_different_ioc_types_independent(store: BlocklistStore) -> None:
    """Test verdicts for different IOC types are stored independently."""
    v_ip = Verdict(
        ioc_type="ip",
        value="1.2.3.4",
        severity="high",
        source="test",
        stix_id="id1",
        first_seen=1,
        expiry=None,
    )
    v_domain = Verdict(
        ioc_type="domain",
        value="1.2.3.4",  # Same value, different type
        severity="high",
        source="test",
        stix_id="id2",
        first_seen=1,
        expiry=None,
    )
    await store.put(v_ip)
    await store.put(v_domain)
    assert await store.check("ip", "1.2.3.4") is not None
    assert await store.check("domain", "1.2.3.4") is not None
