"""Scheduled jobs for SWG category refresh and radix rebuild."""
from __future__ import annotations

import structlog

from hub_api.scheduler.registry import register_job_handler

logger = structlog.get_logger()

__all__ = ["register_swg_jobs"]


def register_swg_jobs() -> None:
    """Register scheduled job handlers for SWG operations.

    Registers a daily category-refresh job that:
    1. Fetches updated categories from external sources
    2. Upserts into domain_categories
    3. Writes to catcache
    4. Rebuilds the radix artifact
    5. Updates app config for live use
    """
    register_job_handler(
        "sase_swg",
        "refresh_categories",
        "hub_api.modules.sase.security.swg.tasks.refresh_categories_daily",
    )
