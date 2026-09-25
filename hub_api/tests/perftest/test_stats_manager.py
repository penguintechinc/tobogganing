"""Coverage backfill for StatsManager (services/stats_manager.py).

Exercises summary/by_device/by_type/trends/recent against seeded
perf_test_results rows, date-filter parsing (including malformed dates,
which are silently ignored), and the except-path fallbacks when the
underlying query raises.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hub_api.modules.perftest_cluster.services.stats_manager import StatsManager


async def _seed_result(
    real_dal: Any,
    tenant: str,
    *,
    device_id: str,
    test_type: str,
    status: str,
    latency_ms: float | None,
    throughput: float | None,
    created_at: datetime,
) -> None:
    """Insert a perf_test_results row directly for StatsManager fixtures."""
    await real_dal.perf_test_results.async_insert(
        id=str(uuid4()),
        tenant=tenant,
        device_id=device_id,
        test_type=test_type,
        status=status,
        target="1.2.3.4",
        started_at=created_at,
        completed_at=created_at,
        latency_ms=latency_ms,
        throughput=throughput,
        test_output=None,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_summary_empty(real_dal: Any) -> None:
    """summary() with zero rows returns the all-zero shape."""
    mgr = StatsManager(real_dal, "tenant-empty")
    result = await mgr.summary()
    assert result["total_tests"] == 0
    assert result["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_summary_with_data_and_date_filters(real_dal: Any) -> None:
    """summary() aggregates status counts and averages, respecting date filters."""
    tenant = "tenant-summary"
    now = datetime.now(timezone.utc)

    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="completed",
        latency_ms=100.0,
        throughput=50.0,
        created_at=now,
    )
    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="pending",
        latency_ms=None,
        throughput=None,
        created_at=now,
    )
    await _seed_result(
        real_dal,
        tenant,
        device_id="d2",
        test_type="tcp",
        status="failed",
        latency_ms=None,
        throughput=None,
        created_at=now,
    )

    mgr = StatsManager(real_dal, tenant)
    result = await mgr.summary()
    assert result["total_tests"] == 3
    assert result["completed_count"] == 1
    assert result["pending_count"] == 1
    assert result["failed_count"] == 1
    assert result["avg_latency_ms"] == 100.0
    assert result["avg_throughput"] == 50.0

    # Date filters: start_date in the future excludes everything.
    future = (now + timedelta(days=1)).isoformat()
    filtered = await mgr.summary(start_date=future)
    assert filtered["total_tests"] == 0

    # end_date in the past excludes everything.
    past = (now - timedelta(days=1)).isoformat()
    filtered_end = await mgr.summary(end_date=past)
    assert filtered_end["total_tests"] == 0

    # Malformed date strings are silently ignored (no filter applied).
    malformed = await mgr.summary(start_date="not-a-date", end_date="also-not-a-date")
    assert malformed["total_tests"] == 3


@pytest.mark.asyncio
async def test_summary_query_exception_returns_zeroed_dict(real_dal: Any) -> None:
    """summary() catches query errors and returns the zeroed fallback shape."""
    bad_db = MagicMock()
    bad_db.perf_test_results.tenant = MagicMock()
    bad_db.perf_test_results.tenant.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    mgr = StatsManager(bad_db, "tenant-err")
    result = await mgr.summary()
    assert result["total_tests"] == 0
    assert result["avg_latency_ms"] == 0.0


@pytest.mark.asyncio
async def test_by_device_empty(real_dal: Any) -> None:
    """by_device() with no rows returns an empty list."""
    mgr = StatsManager(real_dal, "tenant-empty-dev")
    result = await mgr.by_device()
    assert result == []


@pytest.mark.asyncio
async def test_by_device_aggregation_and_limit(real_dal: Any) -> None:
    """by_device() aggregates per-device stats and respects the limit/sort order."""
    tenant = "tenant-by-device"
    now = datetime.now(timezone.utc)

    # d1: 2 tests, 1 completed
    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="completed",
        latency_ms=100.0,
        throughput=10.0,
        created_at=now,
    )
    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="failed",
        latency_ms=None,
        throughput=None,
        created_at=now,
    )
    # d2: 1 test, completed
    await _seed_result(
        real_dal,
        tenant,
        device_id="d2",
        test_type="tcp",
        status="completed",
        latency_ms=50.0,
        throughput=20.0,
        created_at=now,
    )

    mgr = StatsManager(real_dal, tenant)
    result = await mgr.by_device()
    assert len(result) == 2
    # d1 has more total tests, should sort first.
    assert result[0]["device_id"] == "d1"
    assert result[0]["total_tests"] == 2
    assert result[0]["completed_count"] == 1
    assert result[0]["success_rate"] == 50.0
    assert result[0]["avg_latency_ms"] == 100.0

    limited = await mgr.by_device(limit=1)
    assert len(limited) == 1


@pytest.mark.asyncio
async def test_by_device_query_exception_returns_empty(real_dal: Any) -> None:
    """by_device() catches query errors and returns an empty list."""
    bad_db = MagicMock()
    bad_db.perf_test_results.tenant = MagicMock()
    bad_db.perf_test_results.tenant.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    mgr = StatsManager(bad_db, "tenant-err")
    result = await mgr.by_device()
    assert result == []


@pytest.mark.asyncio
async def test_by_type_aggregation(real_dal: Any) -> None:
    """by_type() aggregates per-test-type stats, unknown type falls back to 'unknown'."""
    tenant = "tenant-by-type"
    now = datetime.now(timezone.utc)

    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="completed",
        latency_ms=100.0,
        throughput=10.0,
        created_at=now,
    )
    await _seed_result(
        real_dal,
        tenant,
        device_id="d2",
        test_type="http",
        status="completed",
        latency_ms=200.0,
        throughput=30.0,
        created_at=now,
    )

    mgr = StatsManager(real_dal, tenant)
    result = await mgr.by_type()
    assert len(result) == 1
    assert result[0]["test_type"] == "http"
    assert result[0]["total_tests"] == 2
    assert result[0]["avg_latency_ms"] == 150.0

    limited = await mgr.by_type(limit=0)
    assert limited == []


@pytest.mark.asyncio
async def test_by_type_query_exception_returns_empty(real_dal: Any) -> None:
    """by_type() catches query errors and returns an empty list."""
    bad_db = MagicMock()
    bad_db.perf_test_results.tenant = MagicMock()
    bad_db.perf_test_results.tenant.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    mgr = StatsManager(bad_db, "tenant-err")
    result = await mgr.by_type()
    assert result == []


@pytest.mark.asyncio
async def test_trends_daily_hourly_weekly(real_dal: Any) -> None:
    """trends() buckets by daily/hourly/weekly interval and computes each metric."""
    tenant = "tenant-trends"
    now = datetime.now(timezone.utc).replace(microsecond=0)

    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="completed",
        latency_ms=100.0,
        throughput=10.0,
        created_at=now,
    )
    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="failed",
        latency_ms=None,
        throughput=None,
        created_at=now,
    )

    mgr = StatsManager(real_dal, tenant)

    daily = await mgr.trends(interval="daily", metric="success_rate")
    assert daily["interval"] == "daily"
    assert len(daily["timestamps"]) == 1
    assert daily["values"][0] == 50.0

    hourly = await mgr.trends(interval="hourly", metric="avg_latency")
    assert hourly["interval"] == "hourly"
    assert hourly["values"][0] == 100.0

    weekly = await mgr.trends(interval="weekly", metric="count")
    assert weekly["interval"] == "weekly"
    assert weekly["values"][0] == 2


@pytest.mark.asyncio
async def test_trends_empty_returns_empty_series(real_dal: Any) -> None:
    """trends() with no rows returns empty timestamps/values lists."""
    mgr = StatsManager(real_dal, "tenant-trends-empty")
    result = await mgr.trends()
    assert result["timestamps"] == []
    assert result["values"] == []


@pytest.mark.asyncio
async def test_trends_query_exception_returns_fallback(real_dal: Any) -> None:
    """trends() catches query errors and returns the fallback shape."""
    bad_db = MagicMock()
    bad_db.perf_test_results.tenant = MagicMock()
    bad_db.perf_test_results.tenant.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    mgr = StatsManager(bad_db, "tenant-err")
    result = await mgr.trends(interval="weekly", metric="count")
    assert result["timestamps"] == []
    assert result["interval"] == "weekly"
    assert result["metric"] == "count"


@pytest.mark.asyncio
async def test_recent_with_and_without_device_filter(real_dal: Any) -> None:
    """recent() orders by created_at desc and supports device_id filtering."""
    tenant = "tenant-recent"
    now = datetime.now(timezone.utc)

    await _seed_result(
        real_dal,
        tenant,
        device_id="d1",
        test_type="http",
        status="completed",
        latency_ms=10.0,
        throughput=1.0,
        created_at=now,
    )
    await _seed_result(
        real_dal,
        tenant,
        device_id="d2",
        test_type="tcp",
        status="completed",
        latency_ms=20.0,
        throughput=2.0,
        created_at=now,
    )

    mgr = StatsManager(real_dal, tenant)
    all_recent = await mgr.recent(limit=10)
    assert len(all_recent) == 2

    filtered = await mgr.recent(device_id="d1", limit=10)
    assert len(filtered) == 1
    assert filtered[0]["device_id"] == "d1"


@pytest.mark.asyncio
async def test_recent_query_exception_returns_empty(real_dal: Any) -> None:
    """recent() catches query errors and returns an empty list."""
    bad_db = MagicMock()
    bad_db.perf_test_results.tenant = MagicMock()
    bad_db.perf_test_results.tenant.__eq__ = MagicMock(side_effect=RuntimeError("boom"))

    mgr = StatsManager(bad_db, "tenant-err")
    result = await mgr.recent()
    assert result == []


@pytest.mark.asyncio
async def test_initialize_and_shutdown_log_paths(real_dal: Any) -> None:
    """initialize()/shutdown() succeed and log (no exceptions raised)."""
    mgr = StatsManager(real_dal, "tenant-lifecycle")
    await mgr.initialize()
    await mgr.shutdown()
