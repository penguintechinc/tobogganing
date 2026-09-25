"""AutoCheckIn configuration manager: CRUD + tier/parent validation + scheduler wiring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from hub_api.modules.perftest_cluster.services.engine_client import ALLOWED_TEST_TYPES
from hub_api.scheduler.job_manager import JobManager

log = structlog.get_logger(__name__)

VALID_TARGET_KINDS = {"ours", "external"}
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 60
MIN_JITTER_PCT = 0
MAX_JITTER_PCT = 10
MIN_SAMPLES_PER_RUN = 1
MAX_SAMPLES_PER_RUN = 5
VALID_TIERS = {1, 2, 3}


class AutoCheckInManager:
    """Manage AutoCheckIn configurations: CRUD, tier/parent validation, scheduler job wiring.

    Compiles each AutoCheckIn down to a `scheduled_jobs` row (job_type
    "auto_checkin") so the existing Celery Beat sweep drives it -- no new
    scheduler. Tier cascade is expressed via `parent_checkin_id` (validated
    here) and evaluated at cycle time by the `auto_checkin_cycle` worker task
    against `auto_checkin_state.last_breached`.
    """

    def __init__(self, db: Any) -> None:
        """Initialize manager with DAL instance.

        Args:
            db: penguin-dal AsyncDB instance.

        Raises:
            ValueError: If db is None.
        """
        if db is None:
            raise ValueError("Database instance cannot be None")
        self.db = db
        self.job_manager = JobManager(db)

    async def create_checkin(
        self,
        tenant: str,
        name: str,
        device_id: str,
        target_kind: str,
        target: str,
        test_types: list[str],
        interval_minutes: int = 5,
        jitter_pct: int = 0,
        samples_per_run: int = 1,
        threshold_stddev_min: float | None = None,
        threshold_stddev_max: float | None = None,
        threshold_mean: float | None = None,
        tier: int = 1,
        parent_checkin_id: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create an AutoCheckIn, its cascade-state row, and its scheduler job.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            name: Human-readable check-in name.
            device_id: Source client (server or end-user client) device ID.
            target_kind: "ours" (internal service) or "external" (URL/host:port).
            target: Test target.
            test_types: Non-empty list of probe types, each in ALLOWED_TEST_TYPES.
            interval_minutes: 1-60 (default 5).
            jitter_pct: 0-10, applied as +/- percent of interval (default 0).
            samples_per_run: 1-5 probe executions per test_type per cycle (default 1).
            threshold_stddev_min: Optional min acceptable stddev (ms) of cycle samples.
            threshold_stddev_max: Optional max acceptable stddev (ms) of cycle samples.
            threshold_mean: Optional max acceptable mean latency (ms) of cycle samples.
            tier: 1 (always runs), 2 (runs only when its tier-1 parent breaches), or 3
                (runs only when its tier-2 parent breaches).
            parent_checkin_id: Required when tier > 1 (must reference an existing
                tenant-owned check-in at tier - 1); forbidden when tier == 1.
            enabled: Whether the check-in starts enabled (default True).

        Returns:
            Created check-in row dict.

        Raises:
            ValueError: On any validation failure.
        """
        self._validate_bounds(
            target_kind, test_types, interval_minutes, jitter_pct, samples_per_run, tier
        )
        await self._validate_parent(tenant, tier, parent_checkin_id)

        now = datetime.now(timezone.utc)
        checkin_id = str(uuid4())
        test_types_json = json.dumps(test_types)

        await self.db.auto_checkins.async_insert(
            id=checkin_id,
            tenant=tenant,
            name=name,
            device_id=device_id,
            target_kind=target_kind,
            target=target,
            test_types=test_types_json,
            interval_minutes=interval_minutes,
            jitter_pct=jitter_pct,
            samples_per_run=samples_per_run,
            threshold_stddev_min=threshold_stddev_min,
            threshold_stddev_max=threshold_stddev_max,
            threshold_mean=threshold_mean,
            tier=tier,
            parent_checkin_id=parent_checkin_id,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

        await self.db.auto_checkin_state.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            checkin_id=checkin_id,
            last_breached=False,
            last_mean_latency_ms=None,
            last_stddev_latency_ms=None,
            last_run_at=None,
            updated_at=now,
        )

        await self.job_manager.create_job(
            tenant=tenant,
            module="perftest_cluster",
            job_type="auto_checkin",
            payload={"checkin_id": checkin_id},
            interval_seconds=interval_minutes * 60,
            enabled=enabled,
        )

        return {
            "id": checkin_id,
            "tenant": tenant,
            "name": name,
            "device_id": device_id,
            "target_kind": target_kind,
            "target": target,
            "test_types": test_types,
            "interval_minutes": interval_minutes,
            "jitter_pct": jitter_pct,
            "samples_per_run": samples_per_run,
            "threshold_stddev_min": threshold_stddev_min,
            "threshold_stddev_max": threshold_stddev_max,
            "threshold_mean": threshold_mean,
            "tier": tier,
            "parent_checkin_id": parent_checkin_id,
            "enabled": enabled,
            "created_at": now,
            "updated_at": now,
        }

    async def list_checkins(self, tenant: str) -> list[dict[str, Any]]:
        """List all AutoCheckIns for a tenant.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.

        Returns:
            List of check-in row dicts.
        """
        rowset = await self.db(self.db.auto_checkins.tenant == tenant).select()
        return [self._row_to_dict(row) for row in rowset]

    async def get_checkin(self, tenant: str, checkin_id: str) -> dict[str, Any] | None:
        """Get a single AutoCheckIn, tenant-scoped.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to retrieve.

        Returns:
            Check-in row dict, or None if not found/cross-tenant.
        """
        rowset = await self.db(
            (self.db.auto_checkins.tenant == tenant) & (self.db.auto_checkins.id == checkin_id)
        ).select()
        row = rowset.first()
        return self._row_to_dict(row) if row else None

    async def get_state(self, tenant: str, checkin_id: str) -> dict[str, Any] | None:
        """Get cascade state for a check-in, tenant-scoped.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to retrieve state for.

        Returns:
            State row dict, or None if not found/cross-tenant.
        """
        rowset = await self.db(
            (self.db.auto_checkin_state.tenant == tenant)
            & (self.db.auto_checkin_state.checkin_id == checkin_id)
        ).select()
        row = rowset.first()
        if not row:
            return None
        return {
            "checkin_id": row.checkin_id,
            "last_breached": row.last_breached,
            "last_mean_latency_ms": row.last_mean_latency_ms,
            "last_stddev_latency_ms": row.last_stddev_latency_ms,
            "last_run_at": row.last_run_at,
            "updated_at": row.updated_at,
        }

    async def update_checkin(
        self, tenant: str, checkin_id: str, **fields: Any
    ) -> dict[str, Any] | None:
        """Update mutable fields of an AutoCheckIn.

        Structural fields (device_id, target_kind, tier, parent_checkin_id) are
        immutable after creation -- changing them would require re-validating
        the tier chain and any children pointing at this row; create a new
        check-in instead. Unrecognized/None-valued keys in `fields` are ignored
        (this method is called with `**data` from the API's PATCH handler,
        which may include unrelated keys).

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to update.
            **fields: Any of name/target/test_types/interval_minutes/jitter_pct/
                samples_per_run/threshold_stddev_min/threshold_stddev_max/
                threshold_mean/enabled.

        Returns:
            Updated check-in row dict, or None if not found/cross-tenant.

        Raises:
            ValueError: On bound violations for the fields being updated.
        """
        existing = await self.get_checkin(tenant, checkin_id)
        if existing is None:
            return None

        allowed = {
            "name",
            "target",
            "test_types",
            "interval_minutes",
            "jitter_pct",
            "samples_per_run",
            "threshold_stddev_min",
            "threshold_stddev_max",
            "threshold_mean",
            "enabled",
        }
        updates: dict[str, Any] = {
            k: v for k, v in fields.items() if k in allowed and v is not None
        }

        if "test_types" in updates:
            unsupported = set(updates["test_types"]) - ALLOWED_TEST_TYPES
            if unsupported:
                raise ValueError(f"Unsupported test_types: {sorted(unsupported)}")
            updates["test_types"] = json.dumps(updates["test_types"])

        if "interval_minutes" in updates:
            iv = updates["interval_minutes"]
            if not (MIN_INTERVAL_MINUTES <= iv <= MAX_INTERVAL_MINUTES):
                raise ValueError(
                    f"interval_minutes must be {MIN_INTERVAL_MINUTES}-{MAX_INTERVAL_MINUTES}"
                )
        if "jitter_pct" in updates:
            jp = updates["jitter_pct"]
            if not (MIN_JITTER_PCT <= jp <= MAX_JITTER_PCT):
                raise ValueError(f"jitter_pct must be {MIN_JITTER_PCT}-{MAX_JITTER_PCT}")
        if "samples_per_run" in updates:
            sp = updates["samples_per_run"]
            if not (MIN_SAMPLES_PER_RUN <= sp <= MAX_SAMPLES_PER_RUN):
                raise ValueError(
                    f"samples_per_run must be {MIN_SAMPLES_PER_RUN}-{MAX_SAMPLES_PER_RUN}"
                )

        now = datetime.now(timezone.utc)
        updates["updated_at"] = now
        await self.db(
            (self.db.auto_checkins.tenant == tenant) & (self.db.auto_checkins.id == checkin_id)
        ).update(**updates)

        job = await self._find_job(tenant, checkin_id)
        if job:
            if "interval_minutes" in updates:
                await self.db(self.db.scheduled_jobs.id == job["id"]).update(
                    interval_seconds=updates["interval_minutes"] * 60, updated_at=now
                )
            if "enabled" in updates:
                await self.job_manager.set_enabled(tenant, job["id"], updates["enabled"])

        return await self.get_checkin(tenant, checkin_id)

    async def delete_checkin(self, tenant: str, checkin_id: str) -> bool:
        """Delete a check-in, its state, and its scheduler job.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            checkin_id: Check-in ID to delete.

        Returns:
            True if deleted, False if not found/cross-tenant.

        Raises:
            ValueError: If another check-in references this one as its tier
                parent (dependents must be deleted first).
        """
        existing = await self.get_checkin(tenant, checkin_id)
        if existing is None:
            return False

        dependents = await self.db(
            (self.db.auto_checkins.tenant == tenant)
            & (self.db.auto_checkins.parent_checkin_id == checkin_id)
        ).select()
        if len(dependents) > 0:
            raise ValueError(
                "Cannot delete a check-in that is a tier dependency for other check-ins"
            )

        job = await self._find_job(tenant, checkin_id)
        if job:
            await self.job_manager.delete_job(tenant, job["id"])

        await self.db(self.db.auto_checkin_state.checkin_id == checkin_id).delete()
        count = await self.db(
            (self.db.auto_checkins.tenant == tenant) & (self.db.auto_checkins.id == checkin_id)
        ).delete()
        return count > 0

    async def _find_job(self, tenant: str, checkin_id: str) -> dict[str, Any] | None:
        """Find the scheduled_jobs row for a check-in via payload.checkin_id.

        Mirrors AutoPerfManager's `_update_job_interval` lookup pattern -- no
        stored job-id FK, scan-and-match on payload instead.
        """
        jobs = await self.job_manager.list_jobs(tenant, "perftest_cluster")
        for job in jobs:
            if job["job_type"] == "auto_checkin" and job["payload"].get("checkin_id") == checkin_id:
                return job
        return None

    def _validate_bounds(
        self,
        target_kind: str,
        test_types: list[str],
        interval_minutes: int,
        jitter_pct: int,
        samples_per_run: int,
        tier: int,
    ) -> None:
        """Validate all scalar/enum bounds. Raises ValueError on the first violation."""
        if target_kind not in VALID_TARGET_KINDS:
            raise ValueError(f"target_kind must be one of {sorted(VALID_TARGET_KINDS)}")
        if not test_types:
            raise ValueError("test_types must be a non-empty list")
        unsupported = set(test_types) - ALLOWED_TEST_TYPES
        if unsupported:
            raise ValueError(f"Unsupported test_types: {sorted(unsupported)}")
        if not (MIN_INTERVAL_MINUTES <= interval_minutes <= MAX_INTERVAL_MINUTES):
            raise ValueError(
                f"interval_minutes must be {MIN_INTERVAL_MINUTES}-{MAX_INTERVAL_MINUTES}"
            )
        if not (MIN_JITTER_PCT <= jitter_pct <= MAX_JITTER_PCT):
            raise ValueError(f"jitter_pct must be {MIN_JITTER_PCT}-{MAX_JITTER_PCT}")
        if not (MIN_SAMPLES_PER_RUN <= samples_per_run <= MAX_SAMPLES_PER_RUN):
            raise ValueError(f"samples_per_run must be {MIN_SAMPLES_PER_RUN}-{MAX_SAMPLES_PER_RUN}")
        if tier not in VALID_TIERS:
            raise ValueError(f"tier must be one of {sorted(VALID_TIERS)}")

    async def _validate_parent(self, tenant: str, tier: int, parent_checkin_id: str | None) -> None:
        """Validate the parent_checkin_id / tier relationship.

        Raises ValueError if tier==1 has a parent set, tier>1 is missing a
        parent, the parent doesn't exist/cross-tenant, or the parent's tier
        isn't exactly tier - 1.
        """
        if tier == 1:
            if parent_checkin_id is not None:
                raise ValueError("tier 1 check-ins must not set parent_checkin_id")
            return

        if not parent_checkin_id:
            raise ValueError(f"tier {tier} check-ins require parent_checkin_id")

        parent = await self.get_checkin(tenant, parent_checkin_id)
        if parent is None:
            raise ValueError("parent_checkin_id not found or cross-tenant")
        if parent["tier"] != tier - 1:
            raise ValueError(
                f"parent_checkin_id must reference a tier {tier - 1} check-in, "
                f"got tier {parent['tier']}"
            )

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        """Project a DAL row into the explicit response dict shape."""
        return {
            "id": row.id,
            "tenant": row.tenant,
            "name": row.name,
            "device_id": row.device_id,
            "target_kind": row.target_kind,
            "target": row.target,
            "test_types": json.loads(row.test_types),
            "interval_minutes": row.interval_minutes,
            "jitter_pct": row.jitter_pct,
            "samples_per_run": row.samples_per_run,
            "threshold_stddev_min": row.threshold_stddev_min,
            "threshold_stddev_max": row.threshold_stddev_max,
            "threshold_mean": row.threshold_mean,
            "tier": row.tier,
            "parent_checkin_id": row.parent_checkin_id,
            "enabled": row.enabled,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
