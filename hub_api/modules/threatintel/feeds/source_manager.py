"""Tenant-scoped management of user-configured threat-intel feed sources.

Manages the ``threatintel_feed_sources`` table (MISP/STIX/TAXII/CSV feed
configuration), distinct from the hardcoded built-in feeds driven by
SecurityFeedsManager.feed_configs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()

VALID_SOURCE_TYPES = frozenset({"misp", "stix", "taxii", "csv"})


@dataclass(slots=True)
class FeedSourceRecord:
    """A tenant-scoped, user-configured threat-intel feed source."""

    id: str
    tenant_id: str
    name: str
    source_type: str
    url: str
    enabled: bool
    last_refresh_at: datetime | None
    last_refresh_status: str | None
    last_refresh_error: str | None
    created_at: datetime
    updated_at: datetime


class FeedSourceManager:
    """Manage user-configured threat-intel feed sources, tenant-scoped."""

    def __init__(self, db: Any, tenant_id: str) -> None:
        """Initialize FeedSourceManager.

        Args:
            db: penguin-dal AsyncDB instance.
            tenant_id: Tenant identifier for scoping queries.
        """
        self.db = db
        self.tenant_id = tenant_id

    async def list_sources(self) -> list[FeedSourceRecord]:
        """List all feed sources for this tenant.

        Returns:
            List of FeedSourceRecord instances.
        """
        rowset = await self.db(
            self.db.threatintel_feed_sources.tenant_id == self.tenant_id
        ).select()
        return [self._to_record(row) for row in rowset]

    async def get_source(self, source_id: str) -> FeedSourceRecord | None:
        """Get a single feed source by ID.

        Args:
            source_id: Feed source ID to retrieve.

        Returns:
            FeedSourceRecord if found, None otherwise.
        """
        rowset = await self.db(
            (self.db.threatintel_feed_sources.id == source_id)
            & (self.db.threatintel_feed_sources.tenant_id == self.tenant_id)
        ).select()
        row = rowset.first()
        return self._to_record(row) if row else None

    async def create_source(
        self,
        name: str,
        source_type: str,
        url: str,
        enabled: bool = True,
    ) -> FeedSourceRecord | None:
        """Create a new feed source for this tenant.

        Enforces per-tenant name uniqueness and a valid source_type.

        Args:
            name: Feed source name (must be unique per tenant).
            source_type: One of "misp", "stix", "taxii", "csv".
            url: Feed source URL.
            enabled: Whether the source is active (default True).

        Returns:
            FeedSourceRecord if created, None if duplicate name or invalid type.
        """
        if source_type not in VALID_SOURCE_TYPES:
            logger.warning(
                "feed_source_invalid_type", tenant=self.tenant_id, source_type=source_type
            )
            return None

        rowset = await self.db(
            (self.db.threatintel_feed_sources.tenant_id == self.tenant_id)
            & (self.db.threatintel_feed_sources.name == name)
        ).select()
        if rowset.first():
            logger.warning("feed_source_duplicate_name", tenant=self.tenant_id, name=name)
            return None

        source_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        await self.db.threatintel_feed_sources.async_insert(
            id=source_id,
            tenant_id=self.tenant_id,
            name=name,
            source_type=source_type,
            url=url,
            enabled=enabled,
            last_refresh_at=None,
            last_refresh_status=None,
            last_refresh_error=None,
            created_at=now,
            updated_at=now,
        )

        logger.info(
            "feed_source_created",
            source_id=source_id,
            tenant=self.tenant_id,
            source_type=source_type,
        )

        return FeedSourceRecord(
            id=source_id,
            tenant_id=self.tenant_id,
            name=name,
            source_type=source_type,
            url=url,
            enabled=enabled,
            last_refresh_at=None,
            last_refresh_status=None,
            last_refresh_error=None,
            created_at=now,
            updated_at=now,
        )

    async def delete_source(self, source_id: str) -> bool:
        """Delete a feed source.

        Args:
            source_id: Feed source ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        source = await self.get_source(source_id)
        if not source:
            return False

        await self.db(
            (self.db.threatintel_feed_sources.id == source_id)
            & (self.db.threatintel_feed_sources.tenant_id == self.tenant_id)
        ).delete()

        logger.info("feed_source_deleted", source_id=source_id, tenant=self.tenant_id)
        return True

    async def mark_refresh_result(
        self, source_id: str, status: str, error: str | None = None
    ) -> None:
        """Record the result of a manual refresh trigger.

        Args:
            source_id: Feed source ID that was refreshed.
            status: Refresh outcome ("completed" or "failed").
            error: Error message if status is "failed" (truncated to 500 chars).
        """
        await self.db(
            (self.db.threatintel_feed_sources.id == source_id)
            & (self.db.threatintel_feed_sources.tenant_id == self.tenant_id)
        ).update(
            last_refresh_at=datetime.now(timezone.utc),
            last_refresh_status=status,
            last_refresh_error=error[:500] if error else None,
            updated_at=datetime.now(timezone.utc),
        )

    def _to_record(self, row: Any) -> FeedSourceRecord:
        """Convert a penguin-dal row into a FeedSourceRecord."""
        return FeedSourceRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            source_type=row.source_type,
            url=row.url,
            enabled=bool(row.enabled),
            last_refresh_at=row.last_refresh_at,
            last_refresh_status=row.last_refresh_status,
            last_refresh_error=row.last_refresh_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
