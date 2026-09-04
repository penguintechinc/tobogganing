"""Real-DAL integration tests for the WaddlePerf cluster StatsManager.

Exercises the async aggregation methods against a real migrated sqlite DB
(the ``real_dal`` fixture) — the API test for stats mocks the manager, so this
is the only coverage that runs the real DAL query paths and proves tenant
isolation.
"""
from __future__ import annotations

import datetime
from typing import Any

import pytest

from hub_api.modules.perftest_cluster.services.stats_manager import StatsManager


async def _seed_result(
    dal: Any,
    *,
    rid: str,
    tenant: str,
    device_id: str,
    test_type: str,
    status: str,
    latency: float | None = None,
    throughput: float | None = None,
) -> None:
    now = datetime.datetime.now(datetime.UTC)
    await dal.perf_test_results.async_insert(
        id=rid,
        tenant=tenant,
        device_id=device_id,
        test_type=test_type,
        status=status,
        target="host-1",
        started_at=now,
        completed_at=now,
        latency_ms=latency,
        throughput=throughput,
        test_output="ok",
        created_at=now,
    )


@pytest.mark.asyncio
async def test_summary_counts_and_averages_scoped_to_tenant(real_dal: Any) -> None:
    """summary() aggregates only the caller tenant's rows."""
    await _seed_result(real_dal, rid="r1", tenant="t1", device_id="d1",
                        test_type="http", status="completed", latency=10.0, throughput=100.0)
    await _seed_result(real_dal, rid="r2", tenant="t1", device_id="d1",
                        test_type="http", status="failed")
    # Other tenant's rows must not be counted.
    await _seed_result(real_dal, rid="r3", tenant="t2", device_id="d9",
                        test_type="http", status="completed", latency=999.0)

    summary = await StatsManager(real_dal, "t1").summary()
    assert summary["total_tests"] == 2
    assert summary["completed_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["avg_latency_ms"] == 10.0


@pytest.mark.asyncio
async def test_by_device_scoped_to_tenant(real_dal: Any) -> None:
    """by_device() groups only the caller tenant's rows by device."""
    await _seed_result(real_dal, rid="r1", tenant="t1", device_id="d1",
                        test_type="http", status="completed", latency=5.0)
    await _seed_result(real_dal, rid="r2", tenant="t2", device_id="d1",
                        test_type="http", status="completed", latency=500.0)

    result = await StatsManager(real_dal, "t1").by_device()
    # Only t1's device is aggregated, never t2's (same device_id, other tenant).
    assert len(result) == 1
    assert result[0]["device_id"] == "d1"
    assert result[0]["total_tests"] == 1


@pytest.mark.asyncio
async def test_by_type_scoped_to_tenant(real_dal: Any) -> None:
    """by_type() aggregates only the caller tenant's rows by test type."""
    await _seed_result(real_dal, rid="r1", tenant="t1", device_id="d1",
                        test_type="tcp", status="completed")
    await _seed_result(real_dal, rid="r2", tenant="t2", device_id="d2",
                        test_type="tcp", status="completed")

    result = await StatsManager(real_dal, "t1").by_type()
    assert len(result) == 1
    assert result[0]["test_type"] == "tcp"
    assert result[0]["total_tests"] == 1
