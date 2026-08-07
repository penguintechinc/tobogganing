"""Category ingestion manager for SWG domain categorization."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import aiohttp
import structlog

from hub_api.cache import CacheClient

__all__ = ["IngestStats", "CategoryIngestManager"]

logger = structlog.get_logger()


@dataclass(slots=True)
class IngestStats:
    """Statistics from a category ingestion run.

    Tracks the number of entries scanned, stored, and skipped
    during an ingestion operation.
    """

    source: str
    scanned: int
    stored: int
    skipped: int


class CategoryIngestManager:
    """Manages category feed ingestion and cache updates.

    Fetches category data from sources, parses, and upserts into the
    database and Valkey cache.
    """

    def __init__(self, db: Any, cache: CacheClient) -> None:
        """Initialize the ingestion manager.

        Args:
            db: penguin-dal DAL instance.
            cache: CacheClient for Valkey access.
        """
        self.db = db
        self.cache = cache
        self.session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def ingest_source(self, source: Any) -> IngestStats:
        """Fetch and ingest a single category source.

        Args:
            source: CategorySource with name, url, and parse function.

        Returns:
            IngestStats with counts of scanned, stored, and skipped entries.
        """
        stats = IngestStats(source=source.name, scanned=0, stored=0, skipped=0)

        try:
            session = await self._get_session()
            async with session.get(source.url) as resp:
                if resp.status != 200:
                    logger.warning(
                        "ingest_source_fetch_failed",
                        source=source.name,
                        status=resp.status,
                    )
                    return stats

                content = await resp.text()
        except Exception as e:
            logger.error("ingest_source_fetch_error", source=source.name, error=str(e))
            return stats

        # Parse entries
        try:
            entries: Iterable[tuple[str, str]] = source.parse(content)
        except Exception as e:
            logger.error("ingest_source_parse_error", source=source.name, error=str(e))
            return stats

        # Upsert each entry
        for domain, category in entries:
            stats.scanned += 1

            try:
                domain = domain.lower().strip()
                category = category.lower().strip()

                if not domain or not category:
                    stats.skipped += 1
                    continue

                # Build or fetch existing categories for this domain
                await self._upsert_category(domain, category, source.name)
                stats.stored += 1

                # Write to cache: sase:catcache:<domain> = JSON array of categories
                await self._write_cache(domain)

            except Exception as e:
                logger.debug(
                    "ingest_category_error",
                    domain=domain,
                    category=category,
                    error=str(e),
                )
                stats.skipped += 1

        logger.info(
            "ingest_source_complete",
            source=source.name,
            scanned=stats.scanned,
            stored=stats.stored,
            skipped=stats.skipped,
        )
        return stats

    async def ingest_all(self, sources: list[Any]) -> IngestStats:
        """Ingest all category sources.

        Args:
            sources: List of CategorySource objects.

        Returns:
            Aggregate IngestStats across all sources.
        """
        aggregate = IngestStats(source="all", scanned=0, stored=0, skipped=0)

        for source in sources:
            stats = await self.ingest_source(source)
            aggregate.scanned += stats.scanned
            aggregate.stored += stats.stored
            aggregate.skipped += stats.skipped

        logger.info(
            "ingest_all_complete",
            total_scanned=aggregate.scanned,
            total_stored=aggregate.stored,
            total_skipped=aggregate.skipped,
        )
        return aggregate

    async def upsert_custom(
        self, domain: str, category: str, *, tenant: str | None = None
    ) -> None:
        """Upsert a custom (admin-defined) category for a domain.

        Custom categories (source="custom") win on conflict during radix build.

        Args:
            domain: Domain name.
            category: Category name.
            tenant: Tenant ID (required for custom categories).
        """
        domain = domain.lower().strip()
        category = category.lower().strip()

        if not domain or not category:
            logger.warning("upsert_custom_invalid", domain=domain, category=category)
            return

        await self._upsert_category(domain, category, source="custom", tenant=tenant)
        await self._write_cache(domain)

        logger.info("upsert_custom_success", domain=domain, category=category, tenant=tenant)

    # Private methods

    async def _upsert_category(
        self, domain: str, category: str, source: str = "feed", *, tenant: str | None = None
    ) -> None:
        """Insert or update a domain-category mapping in the database.

        Args:
            domain: Domain name.
            category: Category name.
            source: Source name (feed name or "custom").
            tenant: Tenant ID (optional, for custom categories).
        """
        # Check if this (domain, category, source, tenant) already exists
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        # Using penguin-dal to upsert
        # For now, we'll do a simple insert-or-skip (fail-soft on duplicates)
        try:
            # Try to fetch existing
            existing = await self._get_category(domain, category, source, tenant)
            if existing:
                # Update updated_at
                existing.updated_at = now
                await self.db.domain_categories.update(existing)
            else:
                # Insert new
                new_id = str(uuid.uuid4())
                categories_json = json.dumps([category])
                await self.db.domain_categories.insert({
                    "id": new_id,
                    "domain": domain,
                    "categories": categories_json,
                    "source": source,
                    "tenant": tenant,
                    "updated_at": now,
                })
        except Exception as e:
            logger.debug("upsert_category_failed", domain=domain, error=str(e))

    async def _get_category(
        self, domain: str, category: str, source: str, tenant: str | None
    ) -> Any:
        """Fetch an existing category entry.

        Args:
            domain: Domain name.
            category: Category name.
            source: Source name.
            tenant: Tenant ID (or None).

        Returns:
            Existing row, or None.
        """
        try:
            rows = await self.db.domain_categories.select(
                domain=domain, source=source, tenant=tenant
            )
            for row in rows:
                # Check if category is in the JSON array
                try:
                    existing_cats = json.loads(row.categories)
                    if category in existing_cats:
                        return row
                except Exception:
                    pass
            return None
        except Exception:
            return None

    async def _write_cache(self, domain: str) -> None:
        """Write domain's categories to Valkey cache.

        Args:
            domain: Domain name to cache.
        """
        try:
            # Fetch all categories for this domain from DB
            rows = await self.db.domain_categories.select(domain=domain)
            all_categories = set()
            for row in rows:
                try:
                    cats = json.loads(row.categories)
                    all_categories.update(cats)
                except Exception:
                    pass

            if all_categories:
                # Write to cache: sase:catcache:<domain> = JSON array
                cache_value = json.dumps(sorted(list(all_categories)))
                await self.cache.set("sase:catcache", domain, value=cache_value, ttl_seconds=86400)  # 24hr TTL
        except Exception as e:
            logger.debug("write_cache_failed", domain=domain, error=str(e))
