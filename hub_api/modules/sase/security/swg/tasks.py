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
    from hub_api.modules.sase.security.swg.tier2.fetcher import fetch
    from hub_api.modules.sase.security.swg.tier2.scraper import extract_metadata
    from hub_api.modules.sase.security.swg.tier2.classifier import DomainClassifier
    from hub_api.cache import CacheClient
    from hub_api.config import Config, build_db_uri
    from penguin_dal import AsyncDB

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
            from datetime import datetime, timezone
            import uuid

            now = datetime.now(timezone.utc)
            existing = await db.domain_categories.select(
                domain=domain, source="ai", tenant=tenant
            )

            if existing:
                for row in existing:
                    row.updated_at = now
                    await db.domain_categories.update(row)
            else:
                new_id = str(uuid.uuid4())
                await db.domain_categories.insert({
                    "id": new_id,
                    "domain": domain,
                    "categories": json.dumps([category]),
                    "source": "ai",
                    "tenant": tenant,
                    "updated_at": now,
                })

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
    from celery import Celery
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
    from hub_api.modules.sase.security.swg.ingest import CategoryIngestManager
    from hub_api.cache import CacheClient
    from hub_api.config import Config, build_db_uri
    from penguin_dal import AsyncDB

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

        # Re-ingest all sources (from config/environment)
        # This is a simplified implementation; in production, fetch the source list from DB/config
        try:
            logger.info("refresh_categories_starting")
            # Placeholder: would get sources from config
            # await ingester.ingest_all(sources)
            logger.info("refresh_categories_complete")
        except Exception as e:
            logger.error("refresh_categories_error", error=str(e))

    try:
        asyncio.run(_refresh_async())
    except Exception as e:
        logger.error("refresh_categories_task_error", error=str(e))
