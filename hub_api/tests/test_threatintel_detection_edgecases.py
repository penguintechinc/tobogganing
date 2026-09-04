"""Edge-case tests for DetectionLogger error handling and aggregation branches.

Complements tests/test_sase_feeds.py::TestDetectionLogger with the
log_threat_detection() exception path, get_threat_statistics()'s
per-source count>0 branch, and the entirely-untested
get_top_threat_sources() method.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hub_api.modules.threatintel.feeds.detection import DetectionLogger


def _comparable_db() -> MagicMock:
    """MagicMock DAL whose column attributes support `>=` against a real datetime.

    Plain MagicMock raises TypeError on `mock_attr >= datetime_instance` (no
    default __ge__), which every DetectionLogger query builds via
    `...detected_at >= since`. Configuring __ge__ on the relevant leaf
    attributes lets query-building succeed so the success path is exercised.
    """
    db = MagicMock()
    db.threat_detections.detected_at.__ge__ = MagicMock(return_value=True)
    db.threat_indicators.detected_at.__ge__ = MagicMock(return_value=True)
    return db


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.threat_detections = MagicMock()
    db.threat_detections.async_insert = AsyncMock(side_effect=RuntimeError("insert failed"))

    def query_mock(*_args: object, **_kwargs: object) -> MagicMock:
        query_obj = MagicMock()
        query_obj.select = AsyncMock(return_value=[])
        query_obj.count = AsyncMock(return_value=0)
        return query_obj

    db.side_effect = query_mock
    return db


@pytest.mark.asyncio
async def test_log_threat_detection_error_returns_empty_string() -> None:
    """log_threat_detection() catches insert failures and returns ''."""
    db = _mock_db()
    logger = DetectionLogger(db)

    detection_id = await logger.log_threat_detection(
        tenant_id="tenant-1",
        client_ip="10.0.0.1",
        requested_domain="fail.example.com",
    )

    assert detection_id == ""


@pytest.mark.asyncio
async def test_get_threat_statistics_includes_nonzero_source_counts() -> None:
    """get_threat_statistics() adds a source to indicators_by_source when count > 0."""
    db = _comparable_db()

    def query_mock(*args: object, **_kwargs: object) -> MagicMock:
        query_obj = MagicMock()
        query_obj.select = AsyncMock(return_value=[])
        # Return a nonzero count so the "source" branch (count > 0) executes.
        query_obj.count = AsyncMock(return_value=7)
        return query_obj

    db.side_effect = query_mock

    logger = DetectionLogger(db)
    stats = await logger.get_threat_statistics("tenant-1", hours_back=24)

    assert stats["total_detections"] == 7
    assert stats["indicators_by_source"]  # at least one source populated
    assert all(v == 7 for v in stats["indicators_by_source"].values())
    assert stats["action_counts"]  # blocked/logged/allowed all got count=7


@pytest.mark.asyncio
async def test_get_threat_statistics_error_returns_zeroed_stats() -> None:
    """get_threat_statistics() fails open with zeroed counters on a DB error."""
    db = MagicMock()
    db.side_effect = RuntimeError("db unavailable")

    logger = DetectionLogger(db)
    stats = await logger.get_threat_statistics("tenant-1", hours_back=48)

    assert stats == {
        "period_hours": 48,
        "total_detections": 0,
        "action_counts": {},
        "active_indicators": 0,
        "indicators_by_source": {},
    }


@pytest.mark.asyncio
async def test_get_top_threat_sources_aggregates_and_sorts() -> None:
    """get_top_threat_sources() aggregates by source, sorts descending, respects limit."""
    rows = [
        {"source": "spamhaus"},
        {"source": "spamhaus"},
        {"source": "blackweb"},
        {"source": "spamhaus"},
        {"source": "dnsbl"},
        {"source": None},  # falsy source skipped
    ]

    db = _comparable_db()

    def query_mock(*_args: object, **_kwargs: object) -> MagicMock:
        query_obj = MagicMock()
        query_obj.select = AsyncMock(return_value=rows)
        return query_obj

    db.side_effect = query_mock

    logger = DetectionLogger(db)
    top = await logger.get_top_threat_sources("tenant-1", hours_back=24, limit=2)

    assert top == [
        {"source": "spamhaus", "count": 3},
        {"source": "blackweb", "count": 1},
    ]


@pytest.mark.asyncio
async def test_get_top_threat_sources_attribute_style_rows() -> None:
    """get_top_threat_sources() supports rows exposing .source as an attribute."""

    class Row:
        """Plain attribute-style row with no .get() method (unlike a dict/Mapping)."""

        def __init__(self, source: str) -> None:
            self.source = source

    rows = [Row("urlhaus"), Row("urlhaus")]

    db = _comparable_db()

    def query_mock(*_args: object, **_kwargs: object) -> MagicMock:
        query_obj = MagicMock()
        query_obj.select = AsyncMock(return_value=rows)
        return query_obj

    db.side_effect = query_mock

    logger = DetectionLogger(db)
    top = await logger.get_top_threat_sources("tenant-1")

    assert top == [{"source": "urlhaus", "count": 2}]


@pytest.mark.asyncio
async def test_get_top_threat_sources_error_returns_empty_list() -> None:
    """get_top_threat_sources() fails open with an empty list on a DB error."""
    db = MagicMock()
    db.side_effect = RuntimeError("db unavailable")

    logger = DetectionLogger(db)
    top = await logger.get_top_threat_sources("tenant-1")

    assert top == []
