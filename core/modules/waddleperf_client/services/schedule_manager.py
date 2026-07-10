"""Test schedule management for WaddlePerf client."""
from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = structlog.get_logger()


@dataclass(slots=True)
class TestScheduleDTO:
    """Test schedule data transfer object."""

    id: str
    tenant: str
    org_unit_id: str | None
    test_type: str
    target: str
    interval_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ScheduleManager:
    """Manages test schedules for WaddlePerf client using penguin-dal."""

    def __init__(self, db: object, tenant_id: str) -> None:
        """Initialize ScheduleManager.

        Args:
            db: penguin-dal DAL instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the ScheduleManager."""
        try:
            logger.info("ScheduleManager initialized", tenant=self.tenant_id)
        except Exception as e:
            logger.error("Failed to initialize ScheduleManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the ScheduleManager."""
        logger.info("ScheduleManager shutdown complete")

    async def create_schedule(self, data: dict) -> TestScheduleDTO:
        """Create a new test schedule.

        Args:
            data: Schedule data (org_unit_id, test_type, target, interval_seconds, enabled)

        Returns:
            TestScheduleDTO object
        """
        async with self._lock:
            schedule_obj = await asyncio.to_thread(
                self.db.test_schedules.create,
                tenant=self.tenant_id,
                org_unit_id=data.get("org_unit_id"),
                test_type=data.get("test_type"),
                target=data.get("target"),
                interval_seconds=data.get("interval_seconds"),
                enabled=data.get("enabled", True),
            )

            logger.info(
                "created_schedule",
                schedule_id=schedule_obj.id,
                test_type=schedule_obj.test_type,
                tenant=self.tenant_id,
            )

            return TestScheduleDTO(
                id=schedule_obj.id,
                tenant=schedule_obj.tenant,
                org_unit_id=schedule_obj.org_unit_id,
                test_type=schedule_obj.test_type,
                target=schedule_obj.target,
                interval_seconds=schedule_obj.interval_seconds,
                enabled=schedule_obj.enabled,
                created_at=schedule_obj.created_at,
                updated_at=schedule_obj.updated_at,
            )

    async def get_schedule(self, schedule_id: str) -> TestScheduleDTO | None:
        """Get a test schedule by ID.

        Args:
            schedule_id: Schedule identifier

        Returns:
            TestScheduleDTO or None if not found
        """
        schedule_obj = await asyncio.to_thread(
            self.db.test_schedules.select,
            id=schedule_id,
            tenant=self.tenant_id,
        )
        if not schedule_obj:
            return None

        return TestScheduleDTO(
            id=schedule_obj.id,
            tenant=schedule_obj.tenant,
            org_unit_id=schedule_obj.org_unit_id,
            test_type=schedule_obj.test_type,
            target=schedule_obj.target,
            interval_seconds=schedule_obj.interval_seconds,
            enabled=schedule_obj.enabled,
            created_at=schedule_obj.created_at,
            updated_at=schedule_obj.updated_at,
        )

    async def list_schedules(
        self,
        org_unit_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TestScheduleDTO]:
        """List test schedules for the tenant.

        Args:
            org_unit_id: Optional org unit ID for filtering
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of TestScheduleDTO objects
        """
        if org_unit_id is not None:
            schedules = await asyncio.to_thread(
                self.db.test_schedules.select_list,
                tenant=self.tenant_id,
                org_unit_id=org_unit_id,
                limitby=(offset, offset + limit),
            )
        else:
            schedules = await asyncio.to_thread(
                self.db.test_schedules.select_list,
                tenant=self.tenant_id,
                limitby=(offset, offset + limit),
            )

        return [
            TestScheduleDTO(
                id=s.id,
                tenant=s.tenant,
                org_unit_id=s.org_unit_id,
                test_type=s.test_type,
                target=s.target,
                interval_seconds=s.interval_seconds,
                enabled=s.enabled,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in schedules
        ]

    async def update_schedule(self, schedule_id: str, data: dict) -> TestScheduleDTO | None:
        """Update a test schedule.

        Args:
            schedule_id: Schedule identifier
            data: Updated schedule data

        Returns:
            Updated TestScheduleDTO or None if not found
        """
        existing = await self.get_schedule(schedule_id)
        if not existing:
            return None

        async with self._lock:
            update_data = {
                k: v
                for k, v in data.items()
                if k in ["test_type", "target", "interval_seconds", "enabled"]
            }
            update_data["updated_at"] = datetime.now(timezone.utc)

            await asyncio.to_thread(
                self.db.test_schedules.update,
                id=schedule_id,
                tenant=self.tenant_id,
                **update_data,
            )

            logger.info(
                "updated_schedule",
                schedule_id=schedule_id,
                tenant=self.tenant_id,
            )

        return await self.get_schedule(schedule_id)

    async def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a test schedule.

        Args:
            schedule_id: Schedule identifier

        Returns:
            True if successful, False if not found
        """
        existing = await self.get_schedule(schedule_id)
        if not existing:
            return False

        async with self._lock:
            await asyncio.to_thread(
                self.db.test_schedules.delete,
                id=schedule_id,
                tenant=self.tenant_id,
            )

            logger.info(
                "deleted_schedule",
                schedule_id=schedule_id,
                tenant=self.tenant_id,
            )

        return True

    async def resolve_for_device(self, device: object) -> list[TestScheduleDTO]:
        """Resolve enabled test schedules applicable to a device.

        Returns schedules that are either:
        - Specific to the device's org_unit_id and enabled
        - Tenant-wide (org_unit_id is None) and enabled

        Args:
            device: Device object with org_unit_id attribute

        Returns:
            List of applicable enabled TestScheduleDTO objects
        """
        # Query org-unit-specific schedules
        ou_schedules = await asyncio.to_thread(
            self.db.test_schedules.select_list,
            tenant=self.tenant_id,
            org_unit_id=device.org_unit_id,
            enabled=True,
        )

        # Query tenant-wide schedules (org_unit_id is None)
        tenant_wide_schedules = await asyncio.to_thread(
            self.db.test_schedules.select_list,
            tenant=self.tenant_id,
            org_unit_id=None,
            enabled=True,
        )

        # Combine and deduplicate by id
        all_schedules = list(ou_schedules) + list(tenant_wide_schedules)
        seen_ids = set()
        result = []

        for s in all_schedules:
            if s.id not in seen_ids:
                seen_ids.add(s.id)
                result.append(
                    TestScheduleDTO(
                        id=s.id,
                        tenant=s.tenant,
                        org_unit_id=s.org_unit_id,
                        test_type=s.test_type,
                        target=s.target,
                        interval_seconds=s.interval_seconds,
                        enabled=s.enabled,
                        created_at=s.created_at,
                        updated_at=s.updated_at,
                    )
                )

        logger.info(
            "resolved_schedules_for_device",
            device_id=device.id,
            org_unit_id=device.org_unit_id,
            schedule_count=len(result),
            tenant=self.tenant_id,
        )

        return result
