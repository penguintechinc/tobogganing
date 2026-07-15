"""Manager for scheduled jobs using penguin-dal."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class JobManager:
    """Manages scheduled jobs via penguin-dal AsyncDB.

    Provides CRUD and query operations for server-side scheduled tasks.
    All operations are tenant-scoped except due_jobs which is cross-tenant
    by design (system actor sweeping).
    """

    def __init__(self, db: Any) -> None:
        """Initialize job manager with a DAL instance.

        Args:
            db: penguin-dal AsyncDB instance.

        Raises:
            ValueError: If db is None.
        """
        if db is None:
            raise ValueError("Database instance cannot be None")
        self.db = db

    async def create_job(
        self,
        tenant: str,
        module: str,
        job_type: str,
        payload: dict[str, Any],
        interval_seconds: int,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new scheduled job.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            module: Module name (e.g., "waddleperf_cluster").
            job_type: Job type identifier (e.g., "server_test").
            payload: Job-specific parameters as dict.
            interval_seconds: Interval in seconds between runs (>= 30).
            enabled: Whether job is enabled (default True).

        Returns:
            Created job row as dict with all fields.

        Raises:
            ValueError: If interval_seconds < 30.
        """
        if interval_seconds < 30:
            raise ValueError("interval_seconds must be at least 30")

        job_id = str(uuid4())
        now = datetime.now(timezone.utc)
        next_run = now + timedelta(seconds=interval_seconds)
        payload_json = json.dumps(payload)

        await self.db.scheduled_jobs.async_insert(
            id=job_id,
            tenant=tenant,
            module=module,
            job_type=job_type,
            payload=payload_json,
            interval_seconds=interval_seconds,
            enabled=enabled,
            last_run_at=None,
            next_run_at=next_run,
            created_at=now,
            updated_at=now,
        )

        logger.info(
            "job_created",
            job_id=job_id[:8],
            tenant=tenant,
            module=module,
            job_type=job_type,
            interval_seconds=interval_seconds,
        )

        return {
            "id": job_id,
            "tenant": tenant,
            "module": module,
            "job_type": job_type,
            "payload": payload,
            "interval_seconds": interval_seconds,
            "enabled": enabled,
            "last_run_at": None,
            "next_run_at": next_run,
            "created_at": now,
            "updated_at": now,
        }

    async def list_jobs(
        self,
        tenant: str,
        module: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all jobs for a tenant, optionally filtered by module.

        Args:
            tenant: Tenant ID to scope to.
            module: Optional module filter.

        Returns:
            List of job rows as dicts.
        """
        if module is None:
            rowset = await self.db(self.db.scheduled_jobs.tenant == tenant).select()
        else:
            rowset = await self.db(
                (self.db.scheduled_jobs.tenant == tenant)
                & (self.db.scheduled_jobs.module == module)
            ).select()

        return [
            {
                "id": row.id,
                "tenant": row.tenant,
                "module": row.module,
                "job_type": row.job_type,
                "payload": json.loads(row.payload),
                "interval_seconds": row.interval_seconds,
                "enabled": row.enabled,
                "last_run_at": row.last_run_at,
                "next_run_at": row.next_run_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rowset
        ]

    async def get_job(
        self,
        tenant: str,
        job_id: str,
    ) -> dict[str, Any] | None:
        """Get a specific job by ID, tenant-scoped.

        Args:
            tenant: Tenant ID for scoping.
            job_id: Job ID to retrieve.

        Returns:
            Job row as dict, or None if not found or cross-tenant.
        """
        rowset = await self.db(
            (self.db.scheduled_jobs.id == job_id)
            & (self.db.scheduled_jobs.tenant == tenant)
        ).select()

        row = rowset.first()
        if not row:
            return None

        return {
            "id": row.id,
            "tenant": row.tenant,
            "module": row.module,
            "job_type": row.job_type,
            "payload": json.loads(row.payload),
            "interval_seconds": row.interval_seconds,
            "enabled": row.enabled,
            "last_run_at": row.last_run_at,
            "next_run_at": row.next_run_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    async def set_enabled(
        self,
        tenant: str,
        job_id: str,
        enabled: bool,
    ) -> bool:
        """Enable or disable a job, tenant-scoped.

        Args:
            tenant: Tenant ID for scoping.
            job_id: Job ID to update.
            enabled: True to enable, False to disable.

        Returns:
            True if updated, False if not found or cross-tenant.
        """
        # Verify ownership first
        rowset = await self.db(
            (self.db.scheduled_jobs.id == job_id)
            & (self.db.scheduled_jobs.tenant == tenant)
        ).select()

        if not rowset.first():
            return False

        now = datetime.now(timezone.utc)
        await self.db(self.db.scheduled_jobs.id == job_id).update(
            enabled=enabled,
            updated_at=now,
        )

        logger.info(
            "job_enabled_updated",
            job_id=job_id[:8],
            tenant=tenant,
            enabled=enabled,
        )

        return True

    async def delete_job(
        self,
        tenant: str,
        job_id: str,
    ) -> bool:
        """Delete a job, tenant-scoped.

        Args:
            tenant: Tenant ID for scoping.
            job_id: Job ID to delete.

        Returns:
            True if deleted, False if not found or cross-tenant.
        """
        # Verify ownership first
        rowset = await self.db(
            (self.db.scheduled_jobs.id == job_id)
            & (self.db.scheduled_jobs.tenant == tenant)
        ).select()

        if not rowset.first():
            return False

        await self.db(self.db.scheduled_jobs.id == job_id).delete()

        logger.info(
            "job_deleted",
            job_id=job_id[:8],
            tenant=tenant,
        )

        return True

    async def due_jobs(
        self,
        now: datetime,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get jobs that are due to run (cross-tenant).

        Returns only enabled jobs with next_run_at <= now. This is a system
        operation (sweep task), so it is intentionally cross-tenant.

        Args:
            now: Current timestamp for comparison.
            limit: Maximum number of jobs to return.

        Returns:
            List of due job rows as dicts (unsorted, limit applied).
        """
        rowset = await self.db(
            (self.db.scheduled_jobs.enabled == True)  # noqa: E712
            & (self.db.scheduled_jobs.next_run_at <= now)
        ).select()

        # Manually apply limit since rowset doesn't have slicing
        results = []
        for i, row in enumerate(rowset):
            if i >= limit:
                break
            results.append(
                {
                    "id": row.id,
                    "tenant": row.tenant,
                    "module": row.module,
                    "job_type": row.job_type,
                    "payload": json.loads(row.payload),
                    "interval_seconds": row.interval_seconds,
                    "enabled": row.enabled,
                    "last_run_at": row.last_run_at,
                    "next_run_at": row.next_run_at,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
            )

        return results

    async def mark_ran(
        self,
        job_id: str,
        now: datetime,
    ) -> None:
        """Mark a job as having just run, advance next_run_at.

        Sets last_run_at=now, next_run_at = now + interval_seconds.
        No tenant scoping: system operation.

        Args:
            job_id: Job ID to update.
            now: Current timestamp (used for last_run_at and next_run_at calc).
        """
        # Fetch current interval
        rowset = await self.db(self.db.scheduled_jobs.id == job_id).select()
        row = rowset.first()
        if not row:
            logger.warning("mark_ran_job_not_found", job_id=job_id[:8])
            return

        interval = row.interval_seconds
        next_run = now + timedelta(seconds=interval)

        await self.db(self.db.scheduled_jobs.id == job_id).update(
            last_run_at=now,
            next_run_at=next_run,
            updated_at=now,
        )

        logger.debug(
            "job_marked_ran",
            job_id=job_id[:8],
            next_run_at=next_run.isoformat(),
        )
