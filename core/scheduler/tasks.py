"""Celery tasks for scheduler sweep execution.

Implements the core sweep task that queries due jobs, resolves handlers,
and dispatches to per-module task handlers.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable

import structlog

from core.config import Config, build_db_uri
from core.scheduler.celery_app import celery_app
from core.scheduler.job_manager import JobManager
from core.scheduler.registry import handler_for
from penguin_dal import AsyncDB

logger = structlog.get_logger()


@celery_app.task(name="core.scheduler.tasks.sweep")
def sweep() -> int:
    """Celery sweep task entry point.

    Runs the async sweep logic via asyncio.run.

    Returns:
        Count of jobs successfully dispatched.
    """
    return asyncio.run(_sweep_async())


async def _sweep_async(
    db: AsyncDB | None = None,
    dispatch: Callable[[str, dict[str, Any]], None] | None = None,
    now: datetime | None = None,
) -> int:
    """Async sweep implementation.

    Queries due jobs, resolves handlers, dispatches to task queues, and
    marks jobs as run. Resilient to missing handlers and dispatch failures.

    Args:
        db: AsyncDB instance (created fresh from config if None).
        dispatch: Callable to dispatch tasks (default uses celery_app.send_task).
            Signature: dispatch(task_name: str, kwargs: dict[str, Any]).
        now: Current timestamp (defaults to now in UTC).

    Returns:
        Count of jobs successfully dispatched to handlers (does not include
        jobs skipped due to unknown handlers).
    """
    # Use provided now or current time
    if now is None:
        now = datetime.now(timezone.utc)

    # Create fresh AsyncDB if not provided
    if db is None:
        try:
            cfg = Config()
            db_uri = build_db_uri(cfg)
            db = AsyncDB(uri=db_uri, pool_size=cfg.db_pool_size)
            await db.reflect()
        except Exception as e:
            logger.error(
                "sweep_failed_to_create_dal",
                error=str(e),
            )
            raise

    # Use default dispatch if not provided
    if dispatch is None:
        def default_dispatch(task_name: str, kwargs: dict[str, Any]) -> None:
            """Default dispatch via celery_app.send_task."""
            celery_app.send_task(task_name, kwargs=kwargs)
        dispatch = default_dispatch

    # Fetch due jobs
    job_mgr = JobManager(db)
    try:
        due_jobs_list = await job_mgr.due_jobs(now, limit=100)
    except Exception as e:
        logger.error(
            "sweep_failed_to_query_due_jobs",
            error=str(e),
        )
        raise

    dispatched_count = 0

    # Process each due job
    for job in due_jobs_list:
        job_id = job["id"]
        tenant = job["tenant"]
        module = job["module"]
        job_type = job["job_type"]
        payload = job["payload"]

        # Resolve handler
        task_name = handler_for(module, job_type)

        if not task_name:
            # Unknown handler: warn, advance, and continue
            logger.warning(
                "sweep_unknown_handler",
                job_id=job_id[:8],
                tenant=tenant,
                module=module,
                job_type=job_type,
            )
            try:
                await job_mgr.mark_ran(job_id, now)
            except Exception as e:
                logger.error(
                    "sweep_failed_to_mark_ran_after_unknown_handler",
                    job_id=job_id[:8],
                    error=str(e),
                )
            continue

        # Attempt to dispatch
        try:
            dispatch(
                task_name,
                {
                    "job_id": job_id,
                    "tenant": tenant,
                    "module": module,
                    "job_type": job_type,
                    "payload": payload,
                },
            )
            dispatched_count += 1
        except Exception as e:
            logger.error(
                "sweep_dispatch_failed",
                job_id=job_id[:8],
                tenant=tenant,
                module=module,
                job_type=job_type,
                task_name=task_name,
                error=str(e),
            )
            # Continue to mark_ran even after dispatch failure
            # so the job doesn't wedge the sweep

        # Mark job as run (always, regardless of dispatch success)
        try:
            await job_mgr.mark_ran(job_id, now)
        except Exception as e:
            logger.error(
                "sweep_failed_to_mark_ran",
                job_id=job_id[:8],
                error=str(e),
            )

    logger.info(
        "sweep_completed",
        total_jobs=len(due_jobs_list),
        dispatched_count=dispatched_count,
    )

    return dispatched_count
