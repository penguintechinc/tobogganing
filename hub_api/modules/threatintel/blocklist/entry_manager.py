"""Tenant-scoped management of manually-curated blocklist entries.

Blocklist entries are persisted in threat_indicators (the same table
BlocklistCurator reads from) so they get filter/pagination/tenant-isolated
list+delete-by-id semantics from penguin-dal, and mirrored into
BlocklistStore (Valkey) for immediate O(1) /check visibility — the same
write path BlocklistCurator uses.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

from hub_api.modules.threatintel.blocklist.curator import confidence_to_severity
from hub_api.modules.threatintel.blocklist.models import IOC_TYPES, Verdict
from hub_api.modules.threatintel.blocklist.stix_normalizer import to_stix_indicator
from hub_api.modules.threatintel.blocklist.store import BlocklistStore

logger = structlog.get_logger()

DEFAULT_MANUAL_SOURCE = "manual"


@dataclass(slots=True)
class BlocklistEntryRecord:
    """A tenant-scoped blocklist entry (backed by threat_indicators)."""

    id: str
    indicator_type: str
    value: str
    source: str
    confidence: int
    active: bool
    created_at: datetime
    updated_at: datetime


class BlocklistEntryManager:
    """Manage tenant-scoped manual blocklist entries with cache write-through."""

    def __init__(self, db: Any, tenant_id: str, store: BlocklistStore | None = None) -> None:
        """Initialize BlocklistEntryManager.

        Args:
            db: penguin-dal AsyncDB instance.
            tenant_id: Tenant identifier for scoping queries.
            store: Optional BlocklistStore for cache write-through. If None,
                entries are DB-only (no /check visibility until curated).
        """
        self.db = db
        self.tenant_id = tenant_id
        self.store = store

    async def list_entries(
        self,
        indicator_type: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BlocklistEntryRecord], int]:
        """List blocklist entries for this tenant with optional filters.

        Args:
            indicator_type: Optional filter by indicator type (ip/domain/url/hash).
            source: Optional filter by source.
            limit: Maximum number of results (page size).
            offset: Offset for pagination.

        Returns:
            Tuple of (entries, total_count).
        """
        query = self.db.threat_indicators.tenant_id == self.tenant_id
        if indicator_type:
            query &= self.db.threat_indicators.indicator_type == indicator_type
        if source:
            query &= self.db.threat_indicators.source == source

        total = await self.db(query).count()
        rowset = await self.db(query).select(limitby=(offset, offset + limit))
        entries = [self._to_record(row) for row in rowset]
        return entries, total

    async def get_entry(self, entry_id: str) -> BlocklistEntryRecord | None:
        """Get a single blocklist entry by ID.

        Args:
            entry_id: Entry ID to retrieve.

        Returns:
            BlocklistEntryRecord if found, None otherwise.
        """
        rowset = await self.db(
            (self.db.threat_indicators.id == entry_id)
            & (self.db.threat_indicators.tenant_id == self.tenant_id)
        ).select()
        row = rowset.first()
        return self._to_record(row) if row else None

    async def add_entry(
        self,
        indicator_type: str,
        value: str,
        source: str = DEFAULT_MANUAL_SOURCE,
        confidence: int = 100,
        ttl: int = 86400,
    ) -> BlocklistEntryRecord | None:
        """Add a manual blocklist entry, tenant-scoped, with cache write-through.

        Args:
            indicator_type: One of IOC_TYPES (ip/domain/url/hash).
            value: Indicator value.
            source: Provenance tag (default "manual").
            confidence: Confidence 0-100 (default 100 for manually curated entries).
            ttl: Seconds until cache expiry (default 24h; 0 disables expiry).

        Returns:
            BlocklistEntryRecord if created, None if invalid type or duplicate.
        """
        if indicator_type not in IOC_TYPES:
            logger.warning(
                "blocklist_entry_invalid_type",
                tenant=self.tenant_id,
                indicator_type=indicator_type,
            )
            return None

        # Mirrors uq_threat_indicators_value_source_tenant (value, source, tenant_id)
        rowset = await self.db(
            (self.db.threat_indicators.value == value)
            & (self.db.threat_indicators.source == source)
            & (self.db.threat_indicators.tenant_id == self.tenant_id)
        ).select()
        if rowset.first():
            logger.warning(
                "blocklist_entry_duplicate",
                tenant=self.tenant_id,
                value=value,
                source=source,
            )
            return None

        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        await self.db.threat_indicators.async_insert(
            id=entry_id,
            tenant_id=self.tenant_id,
            indicator_type=indicator_type,
            value=value,
            threat_types=json.dumps([]),
            source=source,
            confidence=confidence,
            first_seen=now,
            last_seen=now,
            ttl=ttl,
            metadata=json.dumps({"added_via": "blocklist_api"}),
            active=True,
            created_at=now,
            updated_at=now,
        )

        store = self.store
        if store is not None:
            await self._write_through(store, indicator_type, value, source, confidence, now, ttl)

        logger.info(
            "blocklist_entry_added",
            entry_id=entry_id,
            tenant=self.tenant_id,
            indicator_type=indicator_type,
        )

        return BlocklistEntryRecord(
            id=entry_id,
            indicator_type=indicator_type,
            value=value,
            source=source,
            confidence=confidence,
            active=True,
            created_at=now,
            updated_at=now,
        )

    async def remove_entry(self, entry_id: str) -> bool:
        """Remove a blocklist entry (DB row + cache verdict).

        Args:
            entry_id: Entry ID to remove.

        Returns:
            True if removed, False if not found.
        """
        entry = await self.get_entry(entry_id)
        if not entry:
            return False

        await self.db(
            (self.db.threat_indicators.id == entry_id)
            & (self.db.threat_indicators.tenant_id == self.tenant_id)
        ).delete()

        if self.store is not None:
            await self.store.remove(entry.indicator_type, entry.value)

        logger.info("blocklist_entry_removed", entry_id=entry_id, tenant=self.tenant_id)
        return True

    async def _write_through(
        self,
        store: BlocklistStore,
        indicator_type: str,
        value: str,
        source: str,
        confidence: int,
        first_seen: datetime,
        ttl: int,
    ) -> None:
        """Mirror a newly-added entry into BlocklistStore (best-effort)."""
        try:
            severity = confidence_to_severity(confidence)
            first_seen_ts = int(first_seen.timestamp())
            expiry = first_seen_ts + ttl if ttl else None
            stix_indicator = to_stix_indicator(
                indicator_type,
                value,
                severity=severity,
                source=source,
                first_seen=first_seen_ts,
            )
            verdict = Verdict(
                ioc_type=indicator_type,
                value=value,
                severity=severity,
                source=source,
                stix_id=stix_indicator.id,
                first_seen=first_seen_ts,
                expiry=expiry,
            )
            await store.put(verdict)
        except Exception as e:
            logger.warning("blocklist_entry_writethrough_error", error=str(e))

    def _to_record(self, row: Any) -> BlocklistEntryRecord:
        """Convert a penguin-dal row into a BlocklistEntryRecord."""
        return BlocklistEntryRecord(
            id=row.id,
            indicator_type=row.indicator_type,
            value=row.value,
            source=row.source,
            confidence=row.confidence,
            active=bool(row.active),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
