"""Seam 3 (P5-E2E/D): feed ingest -> BlocklistCurator -> BlocklistStore ->
IOCChecker.check_domain/check_ip — the path any DNS resolver's block
decision (and gRPC CheckIOC, seam 4) ultimately depends on.

Regression: BlocklistEntryManager's write-through and BlocklistCurator's
bulk curation are two independent paths into the same BlocklistStore — this
covers the curation path (feed-sourced), the one seam 4's full pipeline
depends on.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from penguin_dal import AsyncDB

from hub_api.cache.client import CacheClient
from hub_api.modules.netsvcs.ioc import IOCChecker
from hub_api.modules.threatintel.blocklist.curator import BlocklistCurator
from hub_api.modules.threatintel.blocklist.store import BlocklistStore
from hub_api.modules.threatintel.feeds.ingestor import ingest_feed_source

from .conftest import FakeFeedSession


@pytest.mark.asyncio
async def test_csv_feed_ingest_curate_ioc_checker_blocks_domain_allows_unlisted(
    real_dal: AsyncDB,
) -> None:
    """CSV feed ingest -> curate into BlocklistStore -> IOCChecker.check_domain
    blocks the ingested domain, allows an unlisted one."""
    tenant_id = str(uuid4())
    csv_body = "domain,confidence\nmalicious-seam3.example.com,90\n"
    session = FakeFeedSession(200, csv_body)

    stats = await ingest_feed_source(
        real_dal, tenant_id, "csv", "https://feeds.example.com/seam3.csv", session
    )
    assert stats == {"added": 1, "updated": 0, "errors": 0}

    # Unreachable host -> in-memory fallback (matches test_sase_blocklist_store.py).
    cache = CacheClient(host="127.0.0.1", port=6399)
    store = BlocklistStore(cache=cache)
    curator = BlocklistCurator(real_dal, store)

    curation_stats = await curator.curate(tenant_id)
    assert curation_stats.scanned == 1
    assert curation_stats.stored == 1
    assert curation_stats.skipped == 0

    checker = IOCChecker(cache=cache)

    blocked_result = await checker.check_domain("malicious-seam3.example.com")
    assert blocked_result["blocked"] is True
    assert blocked_result["feed_source"] == "csv"
    assert blocked_result["severity"] == "critical"  # confidence=90 -> critical (>85)

    allowed_result = await checker.check_domain("clean-seam3.example.com")
    assert allowed_result["blocked"] is False
    assert allowed_result["feed_source"] == ""


@pytest.mark.asyncio
async def test_stix_feed_ingest_curate_ioc_checker_blocks_ip(real_dal: AsyncDB) -> None:
    """STIX bundle ingest of a malicious IP -> curate -> IOCChecker.check_ip blocks it."""
    tenant_id = str(uuid4())
    # Note: RFC 5737 documentation ranges (192.0.2.0/24, 198.51.100.0/24,
    # 203.0.113.0/24) are flagged `is_private` by Python's `ipaddress` module
    # and get silently filtered by `_is_valid_ip` — use plain non-reserved
    # addresses here so the STIX pattern actually parses to an indicator.
    stix_payload = {
        "objects": [
            {
                "type": "indicator",
                "id": "indicator--seam3-ip",
                "pattern": "[ipv4-addr:value = '1.2.3.4']",
                "labels": ["malicious-activity"],
                "confidence": "high",
            }
        ]
    }
    session = FakeFeedSession(200, json.dumps(stix_payload))

    stats = await ingest_feed_source(
        real_dal, tenant_id, "stix", "https://stix.example.com/seam3-bundle.json", session
    )
    assert stats == {"added": 1, "updated": 0, "errors": 0}

    cache = CacheClient(host="127.0.0.1", port=6399)
    store = BlocklistStore(cache=cache)
    curator = BlocklistCurator(real_dal, store)

    curation_stats = await curator.curate(tenant_id)
    assert curation_stats.stored == 1

    checker = IOCChecker(cache=cache)
    result = await checker.check_ip("1.2.3.4")
    assert result["blocked"] is True
    assert result["feed_source"] == "stix"

    clean_result = await checker.check_ip("5.6.7.8")
    assert clean_result["blocked"] is False


@pytest.mark.asyncio
async def test_curate_is_tenant_scoped(real_dal: AsyncDB) -> None:
    """Curating tenant A's indicators never blocks tenant B's IOC checker
    (both share the same global BlocklistStore keyspace by ioc value, so
    tenant-scoping happens at the threat_indicators read, not the store)."""
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    session_a = FakeFeedSession(200, "domain,confidence\ntenant-a-only.example.com,70\n")

    stats = await ingest_feed_source(
        real_dal, tenant_a, "csv", "https://feeds.example.com/tenant-a.csv", session_a
    )
    assert stats == {"added": 1, "updated": 0, "errors": 0}

    cache = CacheClient(host="127.0.0.1", port=6399)
    store = BlocklistStore(cache=cache)
    curator = BlocklistCurator(real_dal, store)

    # Curating tenant B (which has no indicators) must not touch tenant A's rows.
    b_stats = await curator.curate(tenant_b)
    assert b_stats.scanned == 0
    assert b_stats.stored == 0

    checker = IOCChecker(cache=cache)
    # Not yet curated (only tenant B was curated) -> not blocked.
    result = await checker.check_domain("tenant-a-only.example.com")
    assert result["blocked"] is False

    # Now curate tenant A -> becomes visible.
    a_stats = await curator.curate(tenant_a)
    assert a_stats.stored == 1
    result_after = await checker.check_domain("tenant-a-only.example.com")
    assert result_after["blocked"] is True
