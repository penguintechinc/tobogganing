"""Edge-case tests for BlocklistStore dedup logic and fail-open error paths.

Covers dedup precedence (higher severity wins, newer first_seen wins),
corrupted-cache-entry recovery, and fail-open/fail-silent behavior on
cache backend errors for put()/check()/remove().
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.threatintel.blocklist.models import Verdict
from hub_api.modules.threatintel.blocklist.store import BlocklistStore


def _verdict(**overrides: object) -> Verdict:
    base = dict(
        ioc_type="domain",
        value="example-dedup.com",
        severity="medium",
        source="feed-a",
        stix_id="indicator--1",
        first_seen=1_700_000_000,
        expiry=None,
    )
    base.update(overrides)
    return Verdict(**base)  # type: ignore[arg-type]


@pytest.fixture
def store() -> BlocklistStore:
    """BlocklistStore backed by a real CacheClient pointed at an unreachable host.

    CacheClient fails open to its in-memory fallback dict on connection error,
    so put()/check()/remove() exercise real dedup logic without needing Valkey.
    """
    cache = CacheClient(host="127.0.0.1", port=6399)
    return BlocklistStore(cache)


@pytest.mark.asyncio
async def test_put_keeps_existing_when_higher_severity(store: BlocklistStore) -> None:
    """Existing critical verdict is kept when a new low-severity verdict arrives."""
    await store.put(_verdict(severity="critical", source="original", first_seen=100))
    await store.put(_verdict(severity="low", source="newcomer", first_seen=200))

    result = await store.check("domain", "example-dedup.com")
    assert result is not None
    assert result.severity == "critical"
    assert result.source == "original"


@pytest.mark.asyncio
async def test_put_keeps_existing_when_same_severity_and_newer(
    store: BlocklistStore,
) -> None:
    """Existing verdict wins when same severity and its first_seen is >= the new one's."""
    await store.put(_verdict(severity="high", source="original", first_seen=1_000))
    await store.put(_verdict(severity="high", source="older-report", first_seen=500))

    result = await store.check("domain", "example-dedup.com")
    assert result is not None
    assert result.source == "original"


@pytest.mark.asyncio
async def test_put_replaces_when_new_is_higher_severity(store: BlocklistStore) -> None:
    """New verdict replaces existing when its severity is strictly higher."""
    await store.put(_verdict(severity="low", source="original", first_seen=100))
    await store.put(_verdict(severity="critical", source="upgrade", first_seen=200))

    result = await store.check("domain", "example-dedup.com")
    assert result is not None
    assert result.source == "upgrade"
    assert result.severity == "critical"


@pytest.mark.asyncio
async def test_put_recovers_from_corrupted_existing_json(store: BlocklistStore) -> None:
    """A non-JSON existing cache entry is logged and overwritten, not fatal."""
    await store.cache.set(
        "threatintel:blocklist", "domain", "example-dedup.com", value="not-json{{{"
    )

    await store.put(_verdict(severity="high", source="recovered"))

    result = await store.check("domain", "example-dedup.com")
    assert result is not None
    assert result.source == "recovered"


@pytest.mark.asyncio
async def test_put_recovers_from_unknown_existing_severity(store: BlocklistStore) -> None:
    """An existing entry with a severity outside SEVERITIES is treated as corrupt."""
    import json

    await store.cache.set(
        "threatintel:blocklist",
        "domain",
        "example-dedup.com",
        value=json.dumps(
            {
                "ioc_type": "domain",
                "value": "example-dedup.com",
                "severity": "not-a-real-severity",
                "source": "corrupt",
                "stix_id": "indicator--0",
                "first_seen": 1,
                "expiry": None,
            }
        ),
    )

    await store.put(_verdict(severity="high", source="recovered"))

    result = await store.check("domain", "example-dedup.com")
    assert result is not None
    assert result.source == "recovered"


@pytest.mark.asyncio
async def test_put_swallows_cache_set_error() -> None:
    """put() logs and does not raise when the cache backend errors on write."""
    store = BlocklistStore(cache=AsyncMock())
    store.cache.get = AsyncMock(return_value=None)
    store.cache.set = AsyncMock(side_effect=RuntimeError("backend unavailable"))

    await store.put(_verdict())  # Must not raise


@pytest.mark.asyncio
async def test_check_fails_open_on_cache_error() -> None:
    """check() returns None (fail open) when the cache backend raises directly."""
    store = BlocklistStore(cache=AsyncMock())
    store.cache.get = AsyncMock(side_effect=RuntimeError("backend unavailable"))

    result = await store.check("domain", "whatever.com")

    assert result is None


@pytest.mark.asyncio
async def test_remove_swallows_cache_error() -> None:
    """remove() logs and does not raise when the cache backend errors."""
    store = BlocklistStore(cache=AsyncMock())
    store.cache.delete = AsyncMock(side_effect=RuntimeError("backend unavailable"))

    await store.remove("domain", "whatever.com")  # Must not raise


@pytest.mark.asyncio
async def test_remove_success(store: BlocklistStore) -> None:
    """remove() deletes a stored verdict so a later check() returns None."""
    await store.put(_verdict())
    await store.remove("domain", "example-dedup.com")

    result = await store.check("domain", "example-dedup.com")
    assert result is None


@pytest.mark.asyncio
async def test_key_hashes_url_values(store: BlocklistStore) -> None:
    """URL IOCs are keyed by sha256 hash to bound key length."""
    ioc_type, key_value = store._key("url", "https://example.com/malware/payload")
    assert ioc_type == "url"
    assert len(key_value) == 64  # sha256 hex digest length


@pytest.mark.asyncio
async def test_put_with_expiry_computes_ttl(store: BlocklistStore) -> None:
    """put() with an expiry computes a positive ttl_seconds for the cache write."""
    import time

    future_expiry = int(time.time()) + 3600
    await store.put(_verdict(expiry=future_expiry))

    result = await store.check("domain", "example-dedup.com")
    assert result is not None
    assert result.expiry == future_expiry
