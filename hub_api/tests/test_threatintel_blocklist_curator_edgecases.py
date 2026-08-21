"""Edge-case tests for BlocklistCurator confidence mapping and error handling.

Complements tests/test_sase_blocklist_curator.py (happy-path curate() flow)
with the low-confidence severity branch, row-processing error resilience,
and non-datetime first_seen handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hub_api.modules.threatintel.blocklist.curator import (
    BlocklistCurator,
    confidence_to_severity,
)
from hub_api.modules.threatintel.blocklist.store import BlocklistStore


@pytest.mark.parametrize(
    "confidence,expected",
    [
        (0, "low"),
        (30, "low"),
        (31, "medium"),
        (60, "medium"),
        (61, "high"),
        (85, "high"),
        (86, "critical"),
        (100, "critical"),
    ],
)
def test_confidence_to_severity_boundaries(confidence: int, expected: str) -> None:
    """confidence_to_severity() maps every boundary to the correct tier."""
    assert confidence_to_severity(confidence) == expected


@pytest.mark.asyncio
async def test_curate_row_processing_error_is_skipped_not_fatal(real_dal) -> None:
    """A row whose curate_one() raises is counted as skipped; curate() keeps going."""
    tenant_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await real_dal.threat_indicators.async_insert(
        id=str(uuid4()),
        tenant_id=tenant_id,
        indicator_type="ip",
        value="203.0.113.5",
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

    store = MagicMock(spec=BlocklistStore)
    store.put = AsyncMock(side_effect=RuntimeError("store unavailable"))

    curator = BlocklistCurator(real_dal, store)
    stats = await curator.curate(tenant_id)

    assert stats.scanned == 1
    assert stats.skipped == 1
    assert stats.stored == 0


@pytest.mark.asyncio
async def test_curate_read_error_returns_empty_stats() -> None:
    """A DAL read failure is caught; curate() returns zeroed stats, doesn't raise."""
    broken_dal = MagicMock()
    broken_dal.threat_indicators = MagicMock()
    broken_dal.side_effect = RuntimeError("db unavailable")

    store = MagicMock(spec=BlocklistStore)
    curator = BlocklistCurator(broken_dal, store)

    stats = await curator.curate("tenant-error")

    assert stats.scanned == 0
    assert stats.stored == 0
    assert stats.skipped == 0


@pytest.mark.asyncio
async def test_curate_one_non_datetime_first_seen_uses_int_timestamp() -> None:
    """curate_one() accepts a raw unix-timestamp int for first_seen."""
    store = MagicMock(spec=BlocklistStore)
    store.put = AsyncMock()
    curator = BlocklistCurator(dal=MagicMock(), store=store)

    from hub_api.modules.threatintel.blocklist.curator import CurationStats

    stats = CurationStats(scanned=0, stored=0, deduped=0, skipped=0)
    row = {
        "indicator_type": "domain",
        "value": "raw-ts.example.com",
        "source": "feed-x",
        "confidence": 20,
        "first_seen": 1_700_000_000,
        "ttl": 3600,
    }

    await curator.curate_one(row, stats)

    assert stats.stored == 1
    store.put.assert_called_once()
    verdict = store.put.call_args[0][0]
    assert verdict.first_seen == 1_700_000_000
    assert verdict.severity == "low"


@pytest.mark.asyncio
async def test_curate_one_missing_first_seen_defaults_to_now() -> None:
    """curate_one() defaults first_seen to current time when absent."""
    store = MagicMock(spec=BlocklistStore)
    store.put = AsyncMock()
    curator = BlocklistCurator(dal=MagicMock(), store=store)

    from hub_api.modules.threatintel.blocklist.curator import CurationStats

    stats = CurationStats(scanned=0, stored=0, deduped=0, skipped=0)
    row = {
        "indicator_type": "ip",
        "value": "198.51.100.9",
        "source": "feed-y",
        "confidence": 95,
        "first_seen": None,
        "ttl": 0,
    }

    before = int(datetime.now(timezone.utc).timestamp())
    await curator.curate_one(row, stats)
    after = int(datetime.now(timezone.utc).timestamp())

    verdict = store.put.call_args[0][0]
    assert before <= verdict.first_seen <= after
    assert verdict.expiry is None  # ttl falsy -> no expiry
    assert verdict.severity == "critical"
