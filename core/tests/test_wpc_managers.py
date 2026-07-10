"""Tests for WaddlePerf cluster managers (TestManager and StatsManager)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from core.modules.waddleperf_cluster.services.test_manager import (
    TestManager,
    PerfTestResult,
)
from core.modules.waddleperf_cluster.services.stats_manager import StatsManager


def make_mock_row(data: dict) -> MagicMock:
    """Create a mock row object that behaves like a penguin-dal row."""
    row = MagicMock()
    for key, value in data.items():
        setattr(row, key, value)
    row.as_dict.return_value = data
    return row


def make_mock_rowset(rows: list) -> MagicMock:
    """Create a mock rowset that supports .first() and iteration."""
    rowset = MagicMock()
    rowset.first.return_value = rows[0] if rows else None
    rowset.__iter__ = MagicMock(side_effect=lambda: iter(rows))
    rowset.__len__ = MagicMock(return_value=len(rows))
    return rowset


@pytest.fixture
def mock_db() -> MagicMock:
    """Provide a mock database for testing managers."""
    db = MagicMock()

    # Mock perf_test_results table (synchronous methods for asyncio.to_thread)
    perf_table = MagicMock()
    perf_table.select = MagicMock(return_value=None)
    perf_table.select_list = MagicMock(return_value=[])
    perf_table.create = MagicMock(return_value=None)
    perf_table.update = MagicMock(return_value=None)
    perf_table.delete = MagicMock(return_value=None)

    db.perf_test_results = perf_table

    return db


@pytest.fixture
def now() -> datetime:
    """Get current datetime."""
    return datetime.now(timezone.utc)


class TestStatsManager:
    """Test StatsManager aggregation operations."""

    @pytest.mark.asyncio
    async def test_summary_empty(self, mock_db: MagicMock) -> None:
        """Test summary with no test results."""
        manager = StatsManager(mock_db, "tenant1")

        mock_db.perf_test_results.select_list = MagicMock(return_value=[])

        result = await manager.summary()

        assert result["total_tests"] == 0
        assert result["completed_count"] == 0
        assert result["success_rate"] == 0.0
        assert result["avg_latency_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_summary_with_results(self, mock_db: MagicMock, now: datetime) -> None:
        """Test summary statistics aggregation."""
        manager = StatsManager(mock_db, "tenant1")

        tests = [
            make_mock_row(
                {
                    "id": "test-1",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "latency",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": 50.0,
                    "throughput": 100.0,
                    "test_output": None,
                    "created_at": now,
                }
            ),
            make_mock_row(
                {
                    "id": "test-2",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "throughput",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": 60.0,
                    "throughput": 110.0,
                    "test_output": None,
                    "created_at": now,
                }
            ),
            make_mock_row(
                {
                    "id": "test-3",
                    "tenant": "tenant1",
                    "device_id": "device-2",
                    "test_type": "latency",
                    "status": "pending",
                    "target": None,
                    "started_at": None,
                    "completed_at": None,
                    "latency_ms": None,
                    "throughput": None,
                    "test_output": None,
                    "created_at": now,
                }
            ),
        ]

        mock_db.perf_test_results.select_list = MagicMock(return_value=tests)

        result = await manager.summary()

        assert result["total_tests"] == 3
        assert result["completed_count"] == 2
        assert result["pending_count"] == 1
        assert result["failed_count"] == 0
        assert result["success_rate"] == 66.67  # 2 completed with latency / 3 total
        assert result["avg_latency_ms"] == 55.0  # (50 + 60) / 2
        assert result["avg_throughput"] == 105.0  # (100 + 110) / 2

    @pytest.mark.asyncio
    async def test_by_device(self, mock_db: MagicMock, now: datetime) -> None:
        """Test statistics aggregated by device."""
        manager = StatsManager(mock_db, "tenant1")

        tests = [
            make_mock_row(
                {
                    "id": "test-1",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "latency",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": 50.0,
                    "throughput": None,
                    "test_output": None,
                    "created_at": now,
                }
            ),
            make_mock_row(
                {
                    "id": "test-2",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "throughput",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": None,
                    "throughput": 100.0,
                    "test_output": None,
                    "created_at": now,
                }
            ),
            make_mock_row(
                {
                    "id": "test-3",
                    "tenant": "tenant1",
                    "device_id": "device-2",
                    "test_type": "latency",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": 60.0,
                    "throughput": None,
                    "test_output": None,
                    "created_at": now,
                }
            ),
        ]

        mock_db.perf_test_results.select_list = MagicMock(return_value=tests)

        result = await manager.by_device()

        assert len(result) == 2
        assert result[0]["device_id"] == "device-1"
        assert result[0]["total_tests"] == 2
        assert result[0]["completed_count"] == 2
        assert result[1]["device_id"] == "device-2"
        assert result[1]["total_tests"] == 1

    @pytest.mark.asyncio
    async def test_by_type(self, mock_db: MagicMock, now: datetime) -> None:
        """Test statistics aggregated by test type."""
        manager = StatsManager(mock_db, "tenant1")

        tests = [
            make_mock_row(
                {
                    "id": "test-1",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "latency",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": 50.0,
                    "throughput": None,
                    "test_output": None,
                    "created_at": now,
                }
            ),
            make_mock_row(
                {
                    "id": "test-2",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "latency",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": 60.0,
                    "throughput": None,
                    "test_output": None,
                    "created_at": now,
                }
            ),
            make_mock_row(
                {
                    "id": "test-3",
                    "tenant": "tenant1",
                    "device_id": "device-2",
                    "test_type": "throughput",
                    "status": "completed",
                    "target": None,
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": None,
                    "throughput": 100.0,
                    "test_output": None,
                    "created_at": now,
                }
            ),
        ]

        mock_db.perf_test_results.select_list = MagicMock(return_value=tests)

        result = await manager.by_type()

        assert len(result) == 2
        assert result[0]["test_type"] == "latency"
        assert result[0]["total_tests"] == 2
        assert result[0]["avg_latency_ms"] == 55.0
        assert result[1]["test_type"] == "throughput"
        assert result[1]["total_tests"] == 1

    @pytest.mark.asyncio
    async def test_trends_daily(self, mock_db: MagicMock, now: datetime) -> None:
        """Test time-series trends by day."""
        manager = StatsManager(mock_db, "tenant1")

        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        tests = [
            make_mock_row(
                {
                    "id": "test-1",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "latency",
                    "status": "completed",
                    "target": None,
                    "started_at": yesterday,
                    "completed_at": yesterday + timedelta(seconds=5),
                    "latency_ms": 50.0,
                    "throughput": None,
                    "test_output": None,
                    "created_at": yesterday,
                }
            ),
            make_mock_row(
                {
                    "id": "test-2",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "latency",
                    "status": "completed",
                    "target": None,
                    "started_at": today,
                    "completed_at": today + timedelta(seconds=5),
                    "latency_ms": 60.0,
                    "throughput": None,
                    "test_output": None,
                    "created_at": today,
                }
            ),
        ]

        mock_db.perf_test_results.select_list = MagicMock(return_value=tests)

        result = await manager.trends(interval="daily", metric="success_rate")

        assert len(result["timestamps"]) == 2
        assert len(result["values"]) == 2
        assert result["metric"] == "success_rate"
        assert result["interval"] == "daily"

    @pytest.mark.asyncio
    async def test_recent(self, mock_db: MagicMock, now: datetime) -> None:
        """Test recent test results."""
        manager = StatsManager(mock_db, "tenant1")

        tests = [
            make_mock_row(
                {
                    "id": "test-1",
                    "tenant": "tenant1",
                    "device_id": "device-1",
                    "test_type": "latency",
                    "status": "completed",
                    "target": "8.8.8.8",
                    "started_at": now,
                    "completed_at": now + timedelta(seconds=5),
                    "latency_ms": 50.0,
                    "throughput": None,
                    "test_output": None,
                    "created_at": now,
                }
            ),
        ]

        mock_db.perf_test_results.select_list = MagicMock(return_value=tests)

        result = await manager.recent(limit=20)

        assert len(result) == 1
        assert result[0]["id"] == "test-1"
        assert result[0]["latency_ms"] == 50.0

    @pytest.mark.asyncio
    async def test_recent_filtered_by_device(
        self, mock_db: MagicMock, now: datetime
    ) -> None:
        """Test recent results filtered by device."""
        manager = StatsManager(mock_db, "tenant1")

        test_obj = make_mock_row(
            {
                "id": "test-1",
                "tenant": "tenant1",
                "device_id": "device-1",
                "test_type": "latency",
                "status": "completed",
                "target": None,
                "started_at": now,
                "completed_at": now + timedelta(seconds=5),
                "latency_ms": 50.0,
                "throughput": None,
                "test_output": None,
                "created_at": now,
            }
        )

        mock_db.perf_test_results.select_list = MagicMock(return_value=[test_obj])

        result = await manager.recent(device_id="device-1")

        assert len(result) == 1
        # Verify filter was passed
        call_kwargs = mock_db.perf_test_results.select_list.call_args[1]
        assert call_kwargs["device_id"] == "device-1"

    @pytest.mark.asyncio
    async def test_stats_tenant_scoping(self, mock_db: MagicMock) -> None:
        """Test that all stats queries are tenant-scoped."""
        manager = StatsManager(mock_db, "tenant-y")

        mock_db.perf_test_results.select_list = MagicMock(return_value=[])

        await manager.summary()

        # Verify tenant was passed
        call_kwargs = mock_db.perf_test_results.select_list.call_args[1]
        assert call_kwargs["tenant"] == "tenant-y"
