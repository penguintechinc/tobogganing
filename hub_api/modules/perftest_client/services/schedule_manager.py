"""Test schedule management for WaddlePerf client."""
from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any
from uuid import uuid4

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

    def __init__(self, db: Any, tenant_id: str) -> None:
        """Initialize ScheduleManager.

        Args:
            db: penguin-dal AsyncDB instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id

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
        schedule_id = str(uuid4())
        now = datetime.now(dt_timezone.utc)
        enabled = data.get("enabled", True)

        await self.db.test_schedules.async_insert(
            id=schedule_id,
            tenant=self.tenant_id,
            org_unit_id=data.get("org_unit_id"),
            test_type=data.get("test_type"),
            target=data.get("target"),
            interval_seconds=data.get("interval_seconds"),
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

        logger.info(
            "created_schedule",
            schedule_id=schedule_id,
            test_type=data.get("test_type"),
            tenant=self.tenant_id,
        )

        return TestScheduleDTO(
            id=schedule_id,
            tenant=self.tenant_id,
            org_unit_id=data.get("org_unit_id"),
            test_type=data.get("test_type"),
            target=data.get("target"),
            interval_seconds=data.get("interval_seconds"),
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

    async def get_schedule(self, schedule_id: str) -> TestScheduleDTO | None:
        """Get a test schedule by ID.

        Args:
            schedule_id: Schedule identifier

        Returns:
            TestScheduleDTO or None if not found
        """
        rowset = await self.db(
            (self.db.test_schedules.id == schedule_id)
            & (self.db.test_schedules.tenant == self.tenant_id)
        ).select()

        row = rowset.first()
        if not row:
            return None

        return TestScheduleDTO(
            id=row.id,
            tenant=row.tenant,
            org_unit_id=row.org_unit_id,
            test_type=row.test_type,
            target=row.target,
            interval_seconds=row.interval_seconds,
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
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
            rowset = await self.db(
                (self.db.test_schedules.tenant == self.tenant_id)
                & (self.db.test_schedules.org_unit_id == org_unit_id)
            ).select(limitby=(offset, offset + limit))
        else:
            rowset = await self.db(
                self.db.test_schedules.tenant == self.tenant_id
            ).select(limitby=(offset, offset + limit))

        return [
            TestScheduleDTO(
                id=row.id,
                tenant=row.tenant,
                org_unit_id=row.org_unit_id,
                test_type=row.test_type,
                target=row.target,
                interval_seconds=row.interval_seconds,
                enabled=row.enabled,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rowset
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

        update_data = {
            k: v
            for k, v in data.items()
            if k in ["test_type", "target", "interval_seconds", "enabled"]
        }
        update_data["updated_at"] = datetime.now(dt_timezone.utc)

        await self.db(
            (self.db.test_schedules.id == schedule_id)
            & (self.db.test_schedules.tenant == self.tenant_id)
        ).update(**update_data)

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

        await self.db(
            (self.db.test_schedules.id == schedule_id)
            & (self.db.test_schedules.tenant == self.tenant_id)
        ).delete()

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
        ou_rowset = await self.db(
            (self.db.test_schedules.tenant == self.tenant_id)
            & (self.db.test_schedules.org_unit_id == device.org_unit_id)
            & (self.db.test_schedules.enabled == True)  # noqa: E712
        ).select()

        # Query tenant-wide schedules (org_unit_id is None)
        tenant_wide_rowset = await self.db(
            (self.db.test_schedules.tenant == self.tenant_id)
            & (self.db.test_schedules.org_unit_id == None)  # noqa: E712
            & (self.db.test_schedules.enabled == True)  # noqa: E712
        ).select()

        # Combine and deduplicate by id
        all_rows = list(ou_rowset) + list(tenant_wide_rowset)
        seen_ids = set()
        result = []

        for row in all_rows:
            if row.id not in seen_ids:
                seen_ids.add(row.id)
                result.append(
                    TestScheduleDTO(
                        id=row.id,
                        tenant=row.tenant,
                        org_unit_id=row.org_unit_id,
                        test_type=row.test_type,
                        target=row.target,
                        interval_seconds=row.interval_seconds,
                        enabled=row.enabled,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
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
