"""Celery tasks for SWG Tier-2 AI categorizer (Slice E Task 4).

Background tasks:
1. categorize_domain(domain, tenant) - fetch → scrape → classify → write-back
2. refresh_categories_daily() - re-ingest feed categories + radix rebuild
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

logger = structlog.get_logger()

__all__ = ["categorize_domain", "refresh_categories_daily"]


async def _categorize_domain_async(domain: str, tenant: str) -> None:
    """Async implementation of domain categorization.

    Fetches page content, scrapes metadata, classifies, and writes back
    to domain_categories + cache if confident.

    Args:
        domain: Domain to categorize.
        tenant: Tenant ID.
    """
    from penguin_dal import AsyncDB

    from hub_api.cache import CacheClient
    from hub_api.config import Config, build_db_uri
    from hub_api.modules.sase.security.swg.tier2.classifier import DomainClassifier
    from hub_api.modules.sase.security.swg.tier2.fetcher import fetch
    from hub_api.modules.sase.security.swg.tier2.scraper import extract_metadata

    CONFIDENCE_THRESHOLD = 0.5
    MODEL_PATH = "/opt/penguintech/models/domain_classifier.joblib"  # Configurable

    try:
        # Step 1: Fetch
        url = f"https://{domain}/"
        html = await fetch(url, max_bytes=512_000, timeout_s=5.0)
        if not html:
            logger.info("categorize_no_fetch", domain=domain, tenant=tenant)
            return

        # Step 2: Scrape metadata
        metadata = extract_metadata(html, max_chars=4000)
        if not metadata:
            logger.info("categorize_no_metadata", domain=domain, tenant=tenant)
            return

        # Step 3: Classify
        classifier = DomainClassifier(model_path=MODEL_PATH)
        category, confidence = classifier.classify(metadata)

        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                "categorize_low_confidence",
                domain=domain,
                category=category,
                confidence=confidence,
                tenant=tenant,
            )
            return

        # Step 4: Write back to DB + cache
        cfg = Config()
        db_uri = build_db_uri(
            db_type=cfg.db_type,
            host=cfg.db_host,
            port=cfg.db_port,
            name=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_pass,
        )
        db = AsyncDB(db_uri)

        try:
            # Upsert to domain_categories (source="ai", tenant-aware)
            import uuid
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            existing = await db.domain_categories.select(domain=domain, source="ai", tenant=tenant)

            if existing:
                for row in existing:
                    row.updated_at = now
                    await db.domain_categories.update(row)
            else:
                new_id = str(uuid.uuid4())
                await db.domain_categories.insert(
                    {
                        "id": new_id,
                        "domain": domain,
                        "categories": json.dumps([category]),
                        "source": "ai",
                        "tenant": tenant,
                        "updated_at": now,
                    }
                )

            # Write to cache (canonical signature)
            cache = CacheClient()
            await cache.set(
                "sase:catcache",
                domain,
                value=json.dumps(sorted([category])),
                ttl_seconds=86400,  # 24hr TTL
            )

            logger.info(
                "categorize_success",
                domain=domain,
                category=category,
                confidence=confidence,
                tenant=tenant,
            )

        except Exception as e:
            logger.error("categorize_write_failed", domain=domain, error=str(e), tenant=tenant)

    except Exception as e:
        logger.error("categorize_error", domain=domain, error=str(e), tenant=tenant)


# Celery task registration (try/except to handle Celery unavailability)
try:
    from hub_api.modules.sase.security.swg.worker.celery_app import celery_app

    @celery_app.task(bind=True, name="sase.categorize_domain", max_retries=0)
    def categorize_domain(self: Any, domain: str, tenant: str) -> None:
        """Celery task wrapper for async categorization.

        Sync task wrapping asyncio.run(_categorize_domain_async).

        Args:
            self: Celery task self.
            domain: Domain to categorize.
            tenant: Tenant ID.
        """
        try:
            asyncio.run(_categorize_domain_async(domain, tenant))
        except Exception as e:
            logger.error("categorize_task_error", domain=domain, error=str(e), tenant=tenant)
            # Do NOT retry; fail-soft design

except (ImportError, AttributeError):
    # Celery not available; provide a no-op fallback
    def categorize_domain(domain: str, tenant: str) -> None:
        """Fallback (no Celery): log and no-op."""
        logger.debug("categorize_domain_no_celery", domain=domain, tenant=tenant)


def refresh_categories_daily() -> None:
    """Refresh categories daily: ingest all sources + rebuild radix.

    Fixes the dangling handler registered in scheduler.py.
    Called by the scheduler on a daily schedule.
    """
    from penguin_dal import AsyncDB

    from hub_api.cache import CacheClient
    from hub_api.config import Config, build_db_uri
    from hub_api.modules.sase.security.swg.ingest import CategoryIngestManager

    async def _refresh_async() -> None:
        cfg = Config()
        db_uri = build_db_uri(
            db_type=cfg.db_type,
            host=cfg.db_host,
            port=cfg.db_port,
            name=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_pass,
        )
        db = AsyncDB(db_uri)
        cache = CacheClient()

        ingester = CategoryIngestManager(db, cache)
        try:
            await _run_category_refresh(ingester, CATEGORY_SOURCES)
        finally:
            if ingester.session is not None:
                await ingester.session.close()

    from hub_api.modules.sase.security.swg.sources import CATEGORY_SOURCES

    try:
        asyncio.run(_refresh_async())
    except Exception as e:
        logger.error("refresh_categories_task_error", error=str(e))
        raise


async def _run_category_refresh(ingester: Any, sources: list[Any]) -> dict[str, Any]:
    """Ingest every category source and report real per-source outcomes.

    A source that yields zero scanned entries (fetch/parse failure or empty
    feed) counts as failed. Raises RuntimeError when no sources are
    configured or every source failed, so the run is never logged as success
    when nothing was ingested.
    """
    if not sources:
        logger.error("refresh_categories_no_sources")
        raise RuntimeError("refresh_categories: no category sources configured")

    logger.info("refresh_categories_starting", sources=len(sources))
    failed: list[str] = []
    scanned = stored = skipped = 0
    for source in sources:
        stats = await ingester.ingest_source(source)
        if stats.scanned == 0:
            failed.append(source.name)
        scanned += stats.scanned
        stored += stats.stored
        skipped += stats.skipped

    result = {
        "sources": len(sources),
        "failed": failed,
        "scanned": scanned,
        "stored": stored,
        "skipped": skipped,
    }
    if len(failed) == len(sources):
        logger.error("refresh_categories_failed", **result)
        raise RuntimeError(f"refresh_categories: all {len(sources)} sources failed")
    if failed:
        logger.warning("refresh_categories_partial", **result)
    else:
        logger.info("refresh_categories_complete", **result)
    return result
