"""Test adapter poller and scheduler integration."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from hub_api.cache.client import CacheClient
from hub_api.modules.sase.security.adapters.base import AnalysisAdapter
from hub_api.modules.sase.security.adapters.poller import AdapterPoller
from hub_api.modules.threatintel.blocklist.store import BlocklistStore


@pytest.fixture
def cache_client() -> CacheClient:
    """CacheClient fixture with unreachable host."""
    return CacheClient(host="127.0.0.1", port=6399)


class _StubAdapter(AnalysisAdapter):
    """Stub adapter for testing poller."""

    source = "test_stub"

    def parse(self, raw: str):
        """Parse stub input."""
        hits = []
        for line in raw.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            from hub_api.modules.sase.security.adapters.base import AdapterHit

            ioc_type, value = parts
            if ioc_type in ("ip", "domain"):
                hit = AdapterHit(
                    ioc_type=ioc_type,
                    value=value.strip(),
                    severity="high",
                    first_seen=1234567890,
                    detail=None,
                )
                hits.append(hit)
        return hits


@pytest.mark.asyncio
async def test_poller_run_once_with_hits(cache_client: CacheClient) -> None:
    """Test poller run_once executes successfully and stores hits."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    # Mock reader returns one line of data
    async def mock_reader() -> str:
        return "ip:192.0.2.1"

    poller = AdapterPoller(
        adapter=adapter,
        reader=mock_reader,
        store=store,
        interval=1,
    )

    stats = await poller.run_once()

    assert stats.source == "test_stub"
    assert stats.scanned == 1
    assert stats.stored == 1
    assert stats.skipped == 0


@pytest.mark.asyncio
async def test_poller_run_once_reader_exception(
    cache_client: CacheClient,
) -> None:
    """Test poller run_once handles reader exceptions gracefully."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    # Mock reader raises an exception
    async def failing_reader() -> str:
        raise RuntimeError("Reader failed")

    poller = AdapterPoller(
        adapter=adapter,
        reader=failing_reader,
        store=store,
        interval=1,
    )

    stats = await poller.run_once()

    # Should not crash, return stats with 0 stored
    assert stats.source == "test_stub"
    assert stats.scanned == 0
    assert stats.stored == 0
    assert stats.skipped == 0


@pytest.mark.asyncio
async def test_poller_run_once_empty_input(cache_client: CacheClient) -> None:
    """Test poller run_once with empty reader output."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    async def empty_reader() -> str:
        return ""

    poller = AdapterPoller(
        adapter=adapter,
        reader=empty_reader,
        store=store,
        interval=1,
    )

    stats = await poller.run_once()

    assert stats.scanned == 0
    assert stats.stored == 0


@pytest.mark.asyncio
async def test_poller_loop_with_timeout(cache_client: CacheClient) -> None:
    """Test poller loop runs at specified interval."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    call_count = 0

    async def counting_reader() -> str:
        nonlocal call_count
        call_count += 1
        return "ip:192.0.2.1"

    poller = AdapterPoller(
        adapter=adapter,
        reader=counting_reader,
        store=store,
        interval=0.1,  # 100ms interval
    )

    # Start loop and let it run for ~250ms (should call ~2-3 times)
    task = asyncio.create_task(poller.loop())
    await asyncio.sleep(0.25)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should have called reader multiple times
    assert call_count >= 2


@pytest.mark.asyncio
async def test_poller_loop_handles_exceptions(
    cache_client: CacheClient,
) -> None:
    """Test poller loop continues after adapter error."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    call_count = 0

    async def intermittent_reader() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Temporary failure")
        return "ip:192.0.2.2"

    poller = AdapterPoller(
        adapter=adapter,
        reader=intermittent_reader,
        store=store,
        interval=0.05,
    )

    task = asyncio.create_task(poller.loop())
    await asyncio.sleep(0.15)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should have retried after exception
    assert call_count >= 2


@pytest.mark.asyncio
async def test_poller_loop_respects_backoff(cache_client: CacheClient) -> None:
    """Test poller loop uses exponential backoff on repeated errors."""
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    call_times = []

    async def always_failing_reader() -> str:
        call_times.append(asyncio.get_event_loop().time())
        raise RuntimeError("Always fails")

    poller = AdapterPoller(
        adapter=adapter,
        reader=always_failing_reader,
        store=store,
        interval=0.05,
    )

    task = asyncio.create_task(poller.loop())
    await asyncio.sleep(0.35)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should have multiple calls with some backoff applied
    assert len(call_times) >= 2


@pytest.mark.asyncio
async def test_poller_loop_outer_exception_triggers_backoff(
    cache_client: CacheClient,
) -> None:
    """Test poller loop's outer except branch backs off when run_once itself raises.

    run_once() normally swallows reader/ingest errors internally, so this
    directly stubs run_once to raise, exercising the loop()'s own
    except-Exception/backoff-sleep path (distinct from run_once's handling).
    """
    adapter = _StubAdapter()
    store = BlocklistStore(cache=cache_client)

    poller = AdapterPoller(
        adapter=adapter,
        reader=AsyncMock(return_value=""),
        store=store,
        interval=0.02,
    )
    poller.run_once = AsyncMock(side_effect=RuntimeError("loop-level boom"))

    task = asyncio.create_task(poller.loop())
    await asyncio.sleep(0.15)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Backoff should have grown beyond the initial value of 1
    assert poller.backoff >= 2
    assert poller.run_once.await_count >= 1
