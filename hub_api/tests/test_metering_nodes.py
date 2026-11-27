"""Node metering per org licensing: enrolled compute objects, 30-day staleness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from hub_api.entitlements.metering import (
    NODE_STALENESS_DAYS,
    UsageReporter,
    count_registered_nodes,
)

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


async def _cluster(db: Any, heartbeat: datetime) -> None:
    """Insert an enrolled cluster with the given heartbeat."""
    await db.clusters.async_insert(
        id=str(uuid4()),
        tenant="t1",
        name="c",
        region="r",
        datacenter="d",
        headend_url="https://h",
        status="active",
        last_heartbeat=heartbeat,
        client_count=0,
        created_at=NOW,
        updated_at=NOW,
    )


async def _device(db: Any, heartbeat: datetime | None) -> None:
    """Insert a device; ``None`` heartbeat means never checked in."""
    await db.devices.async_insert(
        id=str(uuid4()),
        tenant="t1",
        org_unit_id=None,
        name="d",
        serial=f"SN-{uuid4().hex[:8]}",
        hostname=None,
        os=None,
        status="online",
        last_heartbeat=heartbeat,
        metadata=None,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_counts_only_enrolled_non_stale_nodes(real_dal: Any) -> None:
    """Fresh clusters + checked-in devices count; stale and never-seen do not."""
    edge = NOW - timedelta(days=NODE_STALENESS_DAYS) + timedelta(minutes=1)
    stale = NOW - timedelta(days=NODE_STALENESS_DAYS + 1)
    await _cluster(real_dal, NOW - timedelta(days=1))
    await _cluster(real_dal, stale)
    await _device(real_dal, edge)
    await _device(real_dal, stale)
    await _device(real_dal, None)  # registered but never enrolled/checked in
    assert await count_registered_nodes(real_dal, now=NOW) == 2


@pytest.mark.asyncio
async def test_stale_node_reappearing_recounts(real_dal: Any) -> None:
    """A node past staleness frees its slot; a fresh check-in re-counts."""
    await _device(real_dal, NOW - timedelta(days=45))
    assert await count_registered_nodes(real_dal, now=NOW) == 0
    await _device(real_dal, NOW)
    assert await count_registered_nodes(real_dal, now=NOW) == 1


@pytest.mark.asyncio
async def test_query_failure_returns_zero() -> None:
    """A DB error is logged and reported as 0, never raised (metering only)."""
    db = MagicMock(side_effect=RuntimeError("db down"))
    assert await count_registered_nodes(db, now=NOW) == 0


@pytest.mark.asyncio
async def test_snapshot_awaits_async_node_counter() -> None:
    """UsageReporter accepts an async node counter (as wired in app.py)."""

    async def counter() -> int:
        return 7

    reporter = UsageReporter(db=MagicMock(), license_client=MagicMock(), node_counter=counter)
    usage = await reporter.snapshot()
    assert usage.nodes == 7
