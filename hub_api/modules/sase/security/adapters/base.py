"""Base classes for security analysis adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from hub_api.modules.threatintel.blocklist.models import Verdict
from hub_api.modules.threatintel.blocklist.store import BlocklistStore
from hub_api.modules.threatintel.blocklist.stix_normalizer import to_stix_indicator


logger = structlog.get_logger()


@dataclass(slots=True)
class AdapterHit:
    """A single IOC hit from an adapter parser.

    Represents a raw indicator of compromise extracted from tool output,
    ready for normalization and storage in the blocklist.
    """

    ioc_type: str
    value: str
    severity: str
    first_seen: int
    detail: str | None = None


@dataclass(slots=True)
class AdapterStats:
    """Statistics from an adapter ingest run.

    Tracks how many hits were processed, stored, and skipped.
    """

    source: str
    scanned: int
    stored: int
    skipped: int


class AnalysisAdapter(ABC):
    """Base class for security analysis tool adapters.

    Each adapter parses native tool output (EVE, notice logs, scan results, etc.)
    into normalized IOC hits, then ingests them into the blocklist store.
    """

    source: str

    @abstractmethod
    def parse(self, raw: str) -> list[AdapterHit]:
        """Parse raw tool output into IOC hits.

        Args:
            raw: Raw output from the analysis tool (JSON, TSV, etc.).

        Returns:
            List of AdapterHits extracted from the input.
        """
        pass

    async def ingest(self, raw: str, store: BlocklistStore) -> AdapterStats:
        """Ingest raw tool output into the blocklist store.

        Parses the raw input, normalizes each hit to STIX, and stores
        in the blocklist. Fails gracefully: a single normalization error
        increments skipped and continues (no crash).

        Args:
            raw: Raw output from the analysis tool.
            store: BlocklistStore to write verdicts to.

        Returns:
            AdapterStats with counts.
        """
        stats = AdapterStats(source=self.source, scanned=0, stored=0, skipped=0)

        try:
            hits = self.parse(raw)
        except Exception as e:
            logger.warning("adapter_parse_error", source=self.source, error=str(e))
            return stats

        for hit in hits:
            stats.scanned += 1
            try:
                # Normalize to STIX indicator
                stix_indicator = to_stix_indicator(
                    hit.ioc_type,
                    hit.value,
                    severity=hit.severity,
                    source=self.source,
                    first_seen=hit.first_seen,
                )

                # Build verdict
                verdict = Verdict(
                    ioc_type=hit.ioc_type,
                    value=hit.value,
                    severity=hit.severity,
                    source=self.source,
                    stix_id=stix_indicator.id,
                    first_seen=hit.first_seen,
                    expiry=None,
                )

                # Store
                await store.put(verdict)
                stats.stored += 1

            except Exception as e:
                logger.warning(
                    "adapter_normalization_error",
                    source=self.source,
                    ioc_type=hit.ioc_type,
                    value=hit.value,
                    error=str(e),
                )
                stats.skipped += 1

        return stats
