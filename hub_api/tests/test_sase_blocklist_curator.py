"""Tests for SASE blocklist curator from threat_indicators."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.sase.security.blocklist.curator import BlocklistCurator
from hub_api.modules.sase.security.blocklist.store import BlocklistStore


@pytest.fixture
def store() -> BlocklistStore:
    """BlocklistStore with in-memory fallback cache."""
    cache = CacheClient(host="127.0.0.1", port=6399)  # Unreachable
    return BlocklistStore(cache)


@pytest.mark.asyncio
async def test_curate_populates_store(real_dal, store: BlocklistStore) -> None:
    """Test curate() populates store from threat_indicators table."""
    tenant_id = str(uuid4())

    # Seed threat_indicators rows
    now = datetime.now(timezone.utc)
    await real_dal.threat_indicators.async_insert(
        id=str(uuid4()),
        tenant_id=tenant_id,
        indicator_type="ip",
        value="192.168.1.1",
        threat_types=["malware"],
        source="spamhaus",
        confidence=85,
        first_seen=now,
        last_seen=now,
        ttl=3600,
        active=True,
        created_at=now,
        updated_at=now,
    )
    await real_dal.threat_indicators.async_insert(
        id=str(uuid4()),
        tenant_id=tenant_id,
        indicator_type="domain",
        value="malicious.com",
        threat_types=["phishing"],
        source="urlhaus",
        confidence=75,
        first_seen=now,
        last_seen=now,
        ttl=3600,
        active=True,
        created_at=now,
        updated_at=now,
    )

    # Curate
    curator = BlocklistCurator(real_dal, store)
    stats = await curator.curate(tenant_id)

    # Verify stats
    assert stats.scanned >= 2
    assert stats.stored >= 2

    # Verify verdicts in store
    ip_result = await store.check("ip", "192.168.1.1")
    assert ip_result is not None
    assert ip_result.source == "spamhaus"

    domain_result = await store.check("domain", "malicious.com")
    assert domain_result is not None
    assert domain_result.source == "urlhaus"


@pytest.mark.asyncio
async def test_curate_dedups_same_ioc(real_dal, store: BlocklistStore) -> None:
    """Test curate() dedups same IOC, keeping higher severity."""
    tenant_id = str(uuid4())

    # Seed two rows for same domain, low then high severity
    now = datetime.now(timezone.utc)
    await real_dal.threat_indicators.async_insert(
        id=str(uuid4()),
        tenant_id=tenant_id,
        indicator_type="domain",
        value="dedup-test.com",
        threat_types=["malware"],
        source="source1",
        confidence=50,  # medium severity
        first_seen=now,
        last_seen=now,
        ttl=3600,
        active=True,
        created_at=now,
        updated_at=now,
    )
    await real_dal.threat_indicators.async_insert(
        id=str(uuid4()),
        tenant_id=tenant_id,
        indicator_type="domain",
        value="dedup-test.com",
        threat_types=["malware", "botnet"],
        source="source2",
        confidence=95,  # critical severity
        first_seen=now,
        last_seen=now,
        ttl=3600,
        active=True,
        created_at=now,
        updated_at=now,
    )

    # Curate
    curator = BlocklistCurator(real_dal, store)
    await curator.curate(tenant_id)

    # Should have only one entry with critical severity
    result = await store.check("domain", "dedup-test.com")
    assert result is not None
    assert result.severity == "critical"


@pytest.mark.asyncio
async def test_curate_skips_malformed_without_crashing(
    real_dal, store: BlocklistStore
) -> None:
    """Test curate() skips unmappable indicator_type without aborting."""
    tenant_id = str(uuid4())

    # Seed one valid and one invalid (unmappable) indicator
    now = datetime.now(timezone.utc)
    await real_dal.threat_indicators.async_insert(
        id=str(uuid4()),
        tenant_id=tenant_id,
        indicator_type="ip",
        value="10.0.0.1",
        threat_types=["malware"],
        source="spamhaus",
        confidence=90,
        first_seen=now,
        last_seen=now,
        ttl=3600,
        active=True,
        created_at=now,
        updated_at=now,
    )
    await real_dal.threat_indicators.async_insert(
        id=str(uuid4()),
        tenant_id=tenant_id,
        indicator_type="unmappable_type",  # Not in IOC_TYPES
        value="unknown-value",
        threat_types=["unknown"],
        source="unknown_source",
        confidence=50,
        first_seen=now,
        last_seen=now,
        ttl=3600,
        active=True,
        created_at=now,
        updated_at=now,
    )

    # Curate should not crash
    curator = BlocklistCurator(real_dal, store)
    stats = await curator.curate(tenant_id)

    # Should have scanned both, stored one, skipped one
    assert stats.scanned >= 2
    assert stats.stored >= 1
    assert stats.skipped >= 1

    # Valid one should be in store
    result = await store.check("ip", "10.0.0.1")
    assert result is not None
