"""Scheduler integration for recurring tenant-scoped security scans.

Registers the ``sase_scanner``/``run_security_scans`` handler with the scheduler
registry and provides the Celery task the sweep dispatches to.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from hub_api.scheduler.celery_app import celery_app
from hub_api.scheduler.registry import register_job_handler

logger = structlog.get_logger()

SCANNER_MODULE = "sase_scanner"
SCANNER_JOB_TYPE = "run_security_scans"
SCANNER_TASK_NAME = "hub_api.modules.sase.security.scanner.tasks.run_scheduled_scans"
ENSURE_JOBS_TASK_NAME = "hub_api.modules.sase.security.scanner.tasks.ensure_scan_jobs_sweep"
#: Default sweep interval; each scan type still honours its own schedule.
DEFAULT_INTERVAL_SECONDS = 300

__all__ = [
    "SCANNER_JOB_TYPE",
    "SCANNER_MODULE",
    "SCANNER_TASK_NAME",
    "ENSURE_JOBS_TASK_NAME",
    "ensure_scan_jobs_for_all_tenants",
    "ensure_scan_jobs_sweep",
    "ensure_security_scan_job",
    "register_scanner_jobs",
    "run_scheduled_scans",
    "schedule_security_scans",
]


def register_scanner_jobs() -> None:
    """Register the scheduled security-scan handler with the scheduler registry.

    Idempotent; called at module load so the sweep can resolve persisted jobs.
    """
    register_job_handler(SCANNER_MODULE, SCANNER_JOB_TYPE, SCANNER_TASK_NAME)


async def schedule_security_scans(
    db: Any, tenant_id: str, interval_seconds: int = DEFAULT_INTERVAL_SECONDS
) -> dict[str, Any]:
    """Persist a recurring scheduler job that runs due security scans for a tenant.

    Raises:
        ValueError: Missing tenant.
    """
    from hub_api.scheduler.job_manager import JobManager

    if not tenant_id:
        raise ValueError("tenant_id is required for scheduled security scans")
    register_scanner_jobs()
    return await JobManager(db).create_job(
        tenant=tenant_id,
        module=SCANNER_MODULE,
        job_type=SCANNER_JOB_TYPE,
        payload={},
        interval_seconds=interval_seconds,
    )


async def _run_scheduled_scans_async(tenant: str, db: Any = None) -> dict[str, int]:
    """Run all due scans for one tenant; raises on any failure (fail loud).

    Raises:
        ValueError: Missing tenant.
        RuntimeError: One or more scans failed.
    """
    from .core import SecurityScanner

    if not tenant:
        raise ValueError("scheduled security scan requires a tenant")
    if db is None:
        from penguin_dal import AsyncDB

        from hub_api.config import Config, build_db_uri

        cfg = Config()
        db = AsyncDB(uri=build_db_uri(cfg), pool_size=cfg.db_pool_size)
        await db.reflect()
    result = await SecurityScanner(db, tenant_id=tenant).run_due_scans()
    logger.info("scheduled_security_scans_completed", tenant=tenant, ran=result["ran"])
    return result


@celery_app.task(name=SCANNER_TASK_NAME)
def run_scheduled_scans(
    job_id: str, tenant: str, module: str, job_type: str, payload: Any
) -> dict[str, int]:
    """Celery entry point dispatched by the scheduler sweep.

    Args mirror the sweep's dispatch kwargs; only tenant is used.
    """
    logger.info("scheduled_security_scans_started", job_id=job_id[:8], tenant=tenant)
    return asyncio.run(_run_scheduled_scans_async(tenant))


async def ensure_security_scan_job(db: Any, tenant_id: str) -> bool:
    """Ensure exactly one scan job exists for a tenant; create it only if missing.

    Returns:
        True if a job was created, False if one already existed (idempotent).

    Raises:
        ValueError: Missing tenant.
    """
    from hub_api.scheduler.job_manager import JobManager

    if not tenant_id:
        raise ValueError("tenant_id is required for scheduled security scans")
    register_scanner_jobs()
    existing = await JobManager(db).list_jobs(tenant_id, module=SCANNER_MODULE)
    if any(j["job_type"] == SCANNER_JOB_TYPE for j in existing):
        return False
    await schedule_security_scans(db, tenant_id)
    logger.info("security_scan_job_created", tenant=tenant_id)
    return True


async def ensure_scan_jobs_for_all_tenants(db: Any) -> int:
    """Ensure every existing tenant (distinct ``users.tenant``) has a scan job.

    Tenants have no table of their own; the identity table's tenant column is the
    tenant registry. Returns the number of jobs created.
    """
    rows = await db(db.users.tenant != None).select(db.users.tenant)  # noqa: E711 - DAL null
    tenants = sorted({r.tenant for r in rows if r.tenant})
    created = 0
    for tenant in tenants:
        if await ensure_security_scan_job(db, tenant):
            created += 1
    logger.info("security_scan_jobs_ensured", tenants=len(tenants), created=created)
    return created


async def _ensure_scan_jobs_async(db: Any = None) -> int:
    """Build a DAL when needed and run the all-tenant ensure sweep."""
    if db is None:
        from penguin_dal import AsyncDB

        from hub_api.config import Config, build_db_uri

        cfg = Config()
        db = AsyncDB(uri=build_db_uri(cfg), pool_size=cfg.db_pool_size)
        await db.reflect()
    return await ensure_scan_jobs_for_all_tenants(db)


@celery_app.task(name=ENSURE_JOBS_TASK_NAME)
def ensure_scan_jobs_sweep() -> int:
    """Celery beat entry point: backfill scan jobs for every tenant (idempotent)."""
    return asyncio.run(_ensure_scan_jobs_async())
