"""Adapter poller for continuous IOC ingestion."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

import structlog

from hub_api.modules.sase.security.blocklist.store import BlocklistStore

from .base import AdapterStats, AnalysisAdapter


logger = structlog.get_logger()


class AdapterPoller:
    """Poll analysis tool output and ingest IOCs into the blocklist.

    Runs an async loop that periodically reads from a tool (via a reader
    callback) and ingests results into the blocklist store. Handles errors
    gracefully with exponential backoff.
    """

    def __init__(
        self,
        adapter: AnalysisAdapter,
        reader: Callable[[], asyncio.coroutine],
        store: BlocklistStore,
        interval: int | float,
    ) -> None:
        """Initialize poller.

        Args:
            adapter: AnalysisAdapter instance (Suricata, Zeek, etc.).
            reader: Async callable that returns raw tool output (str).
            store: BlocklistStore to write verdicts to.
            interval: Poll interval in seconds.
        """
        self.adapter = adapter
        self.reader = reader
        self.store = store
        self.interval = interval
        self.backoff = 1  # Exponential backoff multiplier

    async def run_once(self) -> AdapterStats:
        """Execute one poll cycle.

        Reads tool output and ingests into blocklist. Handles exceptions
        from reader gracefully (returns empty stats).

        Returns:
            AdapterStats from ingest().
        """
        try:
            raw = await self.reader()
            stats = await self.adapter.ingest(raw, self.store)
            self.backoff = 1  # Reset backoff on success
            return stats
        except Exception as e:
            logger.warning(
                "adapter_poller_read_error",
                source=self.adapter.source,
                error=str(e),
            )
            # Return empty stats on error (don't crash)
            return AdapterStats(
                source=self.adapter.source,
                scanned=0,
                stored=0,
                skipped=0,
            )

    async def loop(self) -> None:
        """Run the poller loop indefinitely.

        Polls at the configured interval, with exponential backoff on error.
        The loop runs until cancelled via task.cancel().
        """
        while True:
            try:
                stats = await self.run_once()
                logger.info(
                    "adapter_poll_complete",
                    source=self.adapter.source,
                    scanned=stats.scanned,
                    stored=stats.stored,
                    skipped=stats.skipped,
                    backoff=self.backoff,
                )
                # Sleep for the configured interval
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                logger.info("adapter_poller_cancelled", source=self.adapter.source)
                raise
            except Exception as e:
                logger.error(
                    "adapter_poller_loop_error",
                    source=self.adapter.source,
                    error=str(e),
                )
                # Exponential backoff: sleep longer before retry
                backoff_sleep = self.interval * self.backoff
                await asyncio.sleep(backoff_sleep)
                self.backoff = min(self.backoff * 2, 60)  # Max 60s backoff
