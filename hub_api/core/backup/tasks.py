"""Scheduler integration for recurring tenant-scoped backups.

Registers the ``core_backup``/``create_backup`` handler with the scheduler
registry and provides the Celery task the sweep dispatches to.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import structlog

from hub_api.scheduler.celery_app import celery_app
from hub_api.scheduler.registry import register_job_handler

logger = structlog.get_logger()

BACKUP_MODULE = "core_backup"
BACKUP_JOB_TYPE = "create_backup"
BACKUP_TASK_NAME = "hub_api.core.backup.tasks.run_scheduled_backup"

__all__ = [
    "BACKUP_JOB_TYPE",
    "BACKUP_MODULE",
    "BACKUP_TASK_NAME",
    "register_backup_jobs",
    "run_scheduled_backup",
]


def register_backup_jobs() -> None:
    """Register the scheduled-backup handler with the scheduler registry.

    Idempotent; called before persisting a job so the sweep can resolve it.
    """
    register_job_handler(BACKUP_MODULE, BACKUP_JOB_TYPE, BACKUP_TASK_NAME)


async def _run_scheduled_backup_async(tenant: str, payload: Any, db: Any = None) -> dict[str, Any]:
    """Run one scheduled tenant-scoped backup.

    Args:
        tenant: Tenant ID from the scheduled job (never whole-DB).
        payload: Job payload (dict or JSON string) of create_backup options.
        db: AsyncDB instance; created from config when None.

    Returns:
        create_backup result dict.

    Raises:
        ValueError: Missing tenant, or encryption requested without a key.
    """
    from hub_api.core.backup.manager import BackupManager

    if not tenant:
        raise ValueError("scheduled backup requires a tenant")
    opts: dict[str, Any] = json.loads(payload) if isinstance(payload, str) else dict(payload or {})

    encryption_key = None
    if opts.get("encrypt"):
        encryption_key = os.environ.get("BACKUP_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("encrypt requested but BACKUP_ENCRYPTION_KEY is not set")

    if db is None:
        from penguin_dal import AsyncDB

        from hub_api.config import Config, build_db_uri

        cfg = Config()
        db = AsyncDB(uri=build_db_uri(cfg), pool_size=cfg.db_pool_size)
        await db.reflect()

    manager = BackupManager(db, backup_dir=os.environ.get("BACKUP_DIR", "/backups"))
    result = await manager.create_backup(
        compress=bool(opts.get("compress", True)),
        encrypt=bool(opts.get("encrypt", False)),
        encryption_key=encryption_key,
        upload_to_s3=bool(opts.get("upload_to_s3", False)),
        tenant_id=tenant,
    )
    logger.info("scheduled_backup_completed", tenant=tenant)
    return result


@celery_app.task(name=BACKUP_TASK_NAME)
def run_scheduled_backup(
    job_id: str, tenant: str, module: str, job_type: str, payload: Any
) -> dict[str, Any]:
    """Celery entry point dispatched by the scheduler sweep.

    Args mirror the sweep's dispatch kwargs; only tenant and payload are used.
    """
    logger.info("scheduled_backup_started", job_id=job_id[:8], tenant=tenant)
    return asyncio.run(_run_scheduled_backup_async(tenant, payload))
