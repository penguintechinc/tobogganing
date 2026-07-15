"""AutoPerf tiered monitoring policy manager and state machine."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from core.scheduler.job_manager import JobManager

log = structlog.get_logger(__name__)


class AutoPerfManager:
    """Manage AutoPerf policies and escalation state machine.

    Handles policy CRUD, state machine transitions (escalation/de-escalation),
    and synchronized scheduler job interval retuning based on tier changes.
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

    async def create_policy(
        self,
        tenant: str,
        name: str,
        device_id: str,
        target: str,
        t1_interval_seconds: int = 300,
        t2_interval_seconds: int = 120,
        t3_interval_seconds: int = 60,
        deescalate_after_clean: int = 3,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new AutoPerf policy with state and scheduler job.

        Validates interval constraints (>=30, t3<=t2<=t1), creates policy row,
        then state row, then scheduler job atomically-in-order.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            name: Human-readable policy name.
            device_id: Device to monitor.
            target: Test target (e.g., IP, hostname).
            t1_interval_seconds: Tier 1 (baseline) interval in seconds (default 300).
            t2_interval_seconds: Tier 2 (escalated) interval in seconds (default 120).
            t3_interval_seconds: Tier 3 (critical) interval in seconds (default 60).
            deescalate_after_clean: Clean cycles needed to de-escalate one tier (default 3).
            enabled: Whether policy starts enabled (default True).

        Returns:
            Policy row dict.

        Raises:
            ValueError: If intervals fail validation.
        """
        # Validate intervals
        if t1_interval_seconds < 30:
            raise ValueError("t1_interval_seconds must be >= 30")
        if t2_interval_seconds < 30:
            raise ValueError("t2_interval_seconds must be >= 30")
        if t3_interval_seconds < 30:
            raise ValueError("t3_interval_seconds must be >= 30")

        if not (t3_interval_seconds <= t2_interval_seconds <= t1_interval_seconds):
            raise ValueError("t3_interval_seconds <= t2_interval_seconds <= t1_interval_seconds required")

        now = datetime.now(timezone.utc)

        # Create policy row
        policy_id = str(uuid4())
        await self.db.autoperf_policies.async_insert(
            id=policy_id,
            tenant=tenant,
            name=name,
            device_id=device_id,
            target=target,
            t1_interval_seconds=t1_interval_seconds,
            t2_interval_seconds=t2_interval_seconds,
            t3_interval_seconds=t3_interval_seconds,
            deescalate_after_clean=deescalate_after_clean,
            enabled=enabled,
            created_at=now,
        )

        # Create state row
        await self.db.autoperf_state.async_insert(
            id=str(uuid4()),
            tenant=tenant,
            policy_id=policy_id,
            current_tier=1,
            clean_cycles=0,
            last_cycle_at=None,
            escalated_at=None,
            updated_at=now,
        )

        # Create scheduler job with t1 interval
        await self.job_manager.create_job(
            tenant=tenant,
            module="waddleperf_cluster",
            job_type="autoperf_cycle",
            payload={"policy_id": policy_id},
            interval_seconds=t1_interval_seconds,
            enabled=enabled,
        )

        return {
            "id": policy_id,
            "tenant": tenant,
            "name": name,
            "device_id": device_id,
            "target": target,
            "t1_interval_seconds": t1_interval_seconds,
            "t2_interval_seconds": t2_interval_seconds,
            "t3_interval_seconds": t3_interval_seconds,
            "deescalate_after_clean": deescalate_after_clean,
            "enabled": enabled,
            "created_at": now,
        }

    async def get_state(
        self, tenant: str, policy_id: str
    ) -> dict[str, Any] | None:
        """Get AutoPerf state for a policy.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            policy_id: Policy ID to retrieve state for.

        Returns:
            State row dict or None if not found or tenant mismatch.
        """
        rowset = await self.db(
            (self.db.autoperf_state.tenant == tenant)
            & (self.db.autoperf_state.policy_id == policy_id)
        ).select()

        row = rowset.first()
        if not row:
            return None

        return {
            "id": row.id,
            "tenant": row.tenant,
            "policy_id": row.policy_id,
            "current_tier": row.current_tier,
            "clean_cycles": row.clean_cycles,
            "last_cycle_at": row.last_cycle_at,
            "escalated_at": row.escalated_at,
            "updated_at": row.updated_at,
        }

    async def record_cycle(
        self, tenant: str, policy_id: str, breached: bool
    ) -> dict[str, Any]:
        """Record a monitoring cycle and execute state machine.

        Breached cycles escalate tier (capped at 3) and reset clean_cycles,
        setting escalated_at. Clean cycles increment clean_cycles counter;
        when clean_cycles >= deescalate_after_clean and tier > 1, de-escalate
        one tier and reset clean_cycles. Tier changes trigger interval retune
        on the associated scheduler job.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            policy_id: Policy ID for the cycle.
            breached: Whether the cycle detected a breach.

        Returns:
            Updated state row dict.

        Raises:
            RuntimeError: If policy or state not found.
        """
        now = datetime.now(timezone.utc)

        # Get current state
        state = await self.get_state(tenant, policy_id)
        if state is None:
            raise RuntimeError(f"Policy {policy_id} not found or tenant mismatch")

        # Get policy to know deescalate_after_clean and interval mappings
        policy_rowset = await self.db(
            (self.db.autoperf_policies.tenant == tenant)
            & (self.db.autoperf_policies.id == policy_id)
        ).select()

        policy_row = policy_rowset.first()
        if not policy_row:
            raise RuntimeError(f"Policy {policy_id} not found or tenant mismatch")

        current_tier = state["current_tier"]
        clean_cycles = state["clean_cycles"]

        if breached:
            # Escalate: tier = min(tier + 1, 3), clean_cycles = 0, escalated_at = now
            current_tier = min(current_tier + 1, 3)
            clean_cycles = 0
            escalated_at = now
        else:
            # Clean cycle: clean_cycles += 1, check for de-escalation
            clean_cycles += 1
            escalated_at = state["escalated_at"]

            if (
                clean_cycles >= policy_row.deescalate_after_clean
                and current_tier > 1
            ):
                current_tier -= 1
                clean_cycles = 0

        # Update state
        await self.db(
            (self.db.autoperf_state.tenant == tenant)
            & (self.db.autoperf_state.policy_id == policy_id)
        ).update(
            current_tier=current_tier,
            clean_cycles=clean_cycles,
            last_cycle_at=now,
            escalated_at=escalated_at,
            updated_at=now,
        )

        # Retune scheduler job interval based on tier
        interval_seconds = self._tier_to_interval(
            current_tier,
            policy_row.t1_interval_seconds,
            policy_row.t2_interval_seconds,
            policy_row.t3_interval_seconds,
        )

        await self._update_job_interval(tenant, policy_id, interval_seconds)

        return {
            "id": state["id"],
            "tenant": tenant,
            "policy_id": policy_id,
            "current_tier": current_tier,
            "clean_cycles": clean_cycles,
            "last_cycle_at": now,
            "escalated_at": escalated_at,
            "updated_at": now,
        }

    async def delete_policy(self, tenant: str, policy_id: str) -> bool:
        """Delete policy, state, and associated scheduler job.

        Args:
            tenant: Tenant ID for multi-tenancy scoping.
            policy_id: Policy ID to delete.

        Returns:
            True if policy was deleted, False if not found or tenant mismatch.
        """
        # Get the state to find the job
        state = await self.get_state(tenant, policy_id)
        if state is None:
            return False

        # Find and delete the scheduler job
        jobs = await self.job_manager.list_jobs(
            tenant, "waddleperf_cluster"
        )
        for job in jobs:
            if (
                job["job_type"] == "autoperf_cycle"
                and job["payload"].get("policy_id") == policy_id
            ):
                await self.job_manager.delete_job(tenant, job["id"])
                break

        # Delete state
        await self.db(
            (self.db.autoperf_state.tenant == tenant)
            & (self.db.autoperf_state.policy_id == policy_id)
        ).delete()

        # Delete policy
        count = await self.db(
            (self.db.autoperf_policies.tenant == tenant)
            & (self.db.autoperf_policies.id == policy_id)
        ).delete()

        return count > 0

    def _tier_to_interval(
        self,
        tier: int,
        t1: int,
        t2: int,
        t3: int,
    ) -> int:
        """Map tier number to interval seconds.

        Args:
            tier: Current tier (1, 2, or 3).
            t1: Tier 1 interval.
            t2: Tier 2 interval.
            t3: Tier 3 interval.

        Returns:
            Interval in seconds for the tier.
        """
        if tier == 1:
            return t1
        elif tier == 2:
            return t2
        else:  # tier >= 3
            return t3

    async def _update_job_interval(
        self, tenant: str, policy_id: str, interval_seconds: int
    ) -> None:
        """Update scheduler job interval_seconds for a policy.

        Finds the autoperf_cycle job for the policy and updates its interval.
        Raises a warning if job not found.

        Args:
            tenant: Tenant ID.
            policy_id: Policy ID to find job for.
            interval_seconds: New interval in seconds.
        """
        jobs = await self.job_manager.list_jobs(tenant, "waddleperf_cluster")
        for job in jobs:
            if (
                job["job_type"] == "autoperf_cycle"
                and job["payload"].get("policy_id") == policy_id
            ):
                # Update the job directly via DAL
                now = datetime.now(timezone.utc)
                await self.db(
                    self.db.scheduled_jobs.id == job["id"]
                ).update(
                    interval_seconds=interval_seconds,
                    updated_at=now,
                )
                return

        log.warning(
            "autoperf_job_not_found",
            policy_id=policy_id,
            tenant=tenant,
        )
