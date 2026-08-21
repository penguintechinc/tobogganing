"""Additional coverage for hub_api.entitlements.metering error/exception branches.

test_metering.py covers the happy paths; this file fills in the nested
exception handlers in count_active_seats, count_registered_nodes, and the
top-level fallback branches in UsageReporter.snapshot()/report().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.entitlements.metering import (
    Usage,
    UsageReporter,
    count_active_seats,
    count_registered_nodes,
)


@pytest.mark.asyncio
async def test_count_active_seats_inner_query_error_returns_zero() -> None:
    """count_active_seats() returns 0 when db.users.select() raises inside the thread."""
    mock_db = MagicMock()
    mock_db.users.select.side_effect = RuntimeError("db down")

    result = await count_active_seats(mock_db)

    assert result == 0


@pytest.mark.asyncio
async def test_count_active_seats_outer_error_returns_zero() -> None:
    """count_active_seats() returns 0 when asyncio.to_thread itself raises."""
    mock_db = MagicMock()

    with patch(
        "hub_api.entitlements.metering.asyncio.to_thread",
        side_effect=RuntimeError("thread pool exhausted"),
    ):
        result = await count_active_seats(mock_db)

    assert result == 0


def test_count_registered_nodes_error_returns_zero() -> None:
    """count_registered_nodes() returns 0 when db.clusters.select() raises."""
    mock_db = MagicMock()
    mock_db.clusters.select.side_effect = RuntimeError("db down")

    result = count_registered_nodes(mock_db)

    assert result == 0


@pytest.mark.asyncio
async def test_snapshot_outer_failure_returns_empty_without_cache() -> None:
    """snapshot() returns an empty Usage when construction itself fails and no cache exists.

    The first Usage(...) call (building the real snapshot) raises; the second
    Usage(...) call inside the except-fallback must succeed normally so we can
    observe the empty-usage fallback value.
    """
    mock_db = MagicMock()
    mock_db.users.select.return_value = MagicMock(__len__=lambda self: 0)
    reporter = UsageReporter(mock_db, MagicMock())

    real_usage = Usage
    call_count = {"n": 0}

    def fake_usage(*args: object, **kwargs: object) -> Usage:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return real_usage(*args, **kwargs)  # type: ignore[arg-type]

    with patch("hub_api.entitlements.metering.Usage", side_effect=fake_usage):
        usage = await reporter.snapshot()

    assert usage.seats == 0
    assert usage.nodes == 0
    assert usage.features == frozenset()


@pytest.mark.asyncio
async def test_snapshot_seats_counter_raising_is_caught() -> None:
    """snapshot() catches count_active_seats() raising and defaults seats to 0."""
    from quart import Quart

    mock_db = MagicMock()
    app = Quart(__name__)
    registry = MagicMock()
    registry._entitlements = []
    app.registry = registry  # type: ignore[attr-defined]

    reporter = UsageReporter(mock_db, MagicMock())

    async with app.app_context():
        with patch(
            "hub_api.entitlements.metering.count_active_seats",
            side_effect=RuntimeError("boom"),
        ):
            usage = await reporter.snapshot()

    assert usage.seats == 0


@pytest.mark.asyncio
async def test_snapshot_node_counter_raising_is_caught() -> None:
    """snapshot() catches node_counter() raising and defaults nodes to 0."""
    from quart import Quart

    mock_db = MagicMock()
    mock_db.users.select.return_value = MagicMock(__len__=lambda self: 0)
    app = Quart(__name__)
    registry = MagicMock()
    registry._entitlements = []
    app.registry = registry  # type: ignore[attr-defined]

    def bad_node_counter() -> int:
        raise RuntimeError("boom")

    reporter = UsageReporter(mock_db, MagicMock(), node_counter=bad_node_counter)

    async with app.app_context():
        usage = await reporter.snapshot()

    assert usage.nodes == 0


@pytest.mark.asyncio
async def test_snapshot_outer_failure_falls_back_to_cache() -> None:
    """snapshot() returns the last-known-good snapshot when a later call fails."""
    mock_db = MagicMock()
    mock_db.users.select.return_value = MagicMock(__len__=lambda self: 0)
    reporter = UsageReporter(mock_db, MagicMock())
    cached = Usage(seats=7, nodes=3, features=frozenset({"x.y"}))
    reporter._last_snapshot = cached

    with patch("hub_api.entitlements.metering.Usage", side_effect=RuntimeError("boom")):
        usage = await reporter.snapshot()

    assert usage is cached


@pytest.mark.asyncio
async def test_report_top_level_exception_returns_false() -> None:
    """report() returns False when snapshot() itself raises unexpectedly."""
    reporter = UsageReporter(MagicMock(), MagicMock())
    reporter.snapshot = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    result = await reporter.report()

    assert result is False


@pytest.mark.asyncio
async def test_snapshot_collects_enterprise_features_enabled() -> None:
    """snapshot() adds enabled Enterprise-tier features to the usage set."""
    from quart import Quart

    from hub_api.registry.contract import Entitlement

    mock_db = MagicMock()
    mock_db.users.select.return_value = MagicMock(__len__=lambda self: 0)

    app = Quart(__name__)
    registry = MagicMock()
    registry._entitlements = [
        Entitlement(feature="hub_api.external_kms", tier="enterprise"),
        Entitlement(feature="hub_api.basic_thing", tier="community"),
    ]
    app.registry = registry  # type: ignore[attr-defined]

    reporter = UsageReporter(mock_db, MagicMock())

    async with app.app_context():
        with patch("hub_api.flags.feature_enabled", return_value=True):
            usage = await reporter.snapshot()

    assert "hub_api.external_kms" in usage.features
    assert "hub_api.basic_thing" not in usage.features
