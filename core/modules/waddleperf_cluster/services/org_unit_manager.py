"""Organizational unit management using penguin-dal."""
from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = structlog.get_logger()


@dataclass(slots=True)
class OrgUnit:
    """Organizational unit data structure."""

    id: str
    tenant: str
    name: str
    parent_id: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrgUnitManager:
    """Manages organizational units (OUs) with hierarchy support using penguin-dal."""

    def __init__(self, db: object, tenant_id: str) -> None:
        """Initialize OrgUnitManager.

        Args:
            db: penguin-dal DAL instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the OrgUnitManager."""
        try:
            logger.info("OrgUnitManager initialized", tenant=self.tenant_id)
        except Exception as e:
            logger.error("Failed to initialize OrgUnitManager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown the OrgUnitManager."""
        logger.info("OrgUnitManager shutdown complete")

    async def create_ou(self, data: dict) -> OrgUnit:
        """Create a new organizational unit.

        Args:
            data: OU data dictionary (name, parent_id, description, is_active)

        Returns:
            OrgUnit object
        """
        async with self._lock:
            ou_obj = await asyncio.to_thread(
                self.db.org_units.create,
                tenant=self.tenant_id,
                name=data.get("name"),
                parent_id=data.get("parent_id"),
                description=data.get("description"),
                is_active=data.get("is_active", True),
            )

            logger.info(
                "created_ou",
                ou_id=ou_obj.id,
                name=ou_obj.name,
                tenant=self.tenant_id,
            )

            return OrgUnit(
                id=ou_obj.id,
                tenant=ou_obj.tenant,
                name=ou_obj.name,
                parent_id=ou_obj.parent_id,
                description=ou_obj.description,
                is_active=ou_obj.is_active,
                created_at=ou_obj.created_at,
                updated_at=ou_obj.updated_at,
            )

    async def get_ou(self, ou_id: str) -> OrgUnit | None:
        """Get an organizational unit by ID.

        Args:
            ou_id: OU identifier

        Returns:
            OrgUnit or None if not found
        """
        ou_obj = await asyncio.to_thread(
            self.db.org_units.select,
            id=ou_id,
            tenant=self.tenant_id,
        )
        if not ou_obj:
            return None

        return OrgUnit(
            id=ou_obj.id,
            tenant=ou_obj.tenant,
            name=ou_obj.name,
            parent_id=ou_obj.parent_id,
            description=ou_obj.description,
            is_active=ou_obj.is_active,
            created_at=ou_obj.created_at,
            updated_at=ou_obj.updated_at,
        )

    async def list_ous(
        self, parent_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[OrgUnit]:
        """List organizational units for the tenant.

        Args:
            parent_id: Optional parent OU ID for hierarchy filtering
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of OrgUnit objects
        """
        if parent_id is not None:
            ous = await asyncio.to_thread(
                self.db.org_units.select_list,
                tenant=self.tenant_id,
                parent_id=parent_id,
                limitby=(offset, offset + limit),
            )
        else:
            ous = await asyncio.to_thread(
                self.db.org_units.select_list,
                tenant=self.tenant_id,
                limitby=(offset, offset + limit),
            )

        return [
            OrgUnit(
                id=ou.id,
                tenant=ou.tenant,
                name=ou.name,
                parent_id=ou.parent_id,
                description=ou.description,
                is_active=ou.is_active,
                created_at=ou.created_at,
                updated_at=ou.updated_at,
            )
            for ou in ous
        ]

    async def update_ou(self, ou_id: str, data: dict) -> OrgUnit | None:
        """Update an organizational unit.

        Args:
            ou_id: OU identifier
            data: Updated OU data

        Returns:
            Updated OrgUnit or None if not found
        """
        existing = await self.get_ou(ou_id)
        if not existing:
            return None

        async with self._lock:
            update_data = {k: v for k, v in data.items() if k in ["name", "description", "parent_id", "is_active"]}
            update_data["updated_at"] = datetime.now(timezone.utc)

            await asyncio.to_thread(
                self.db.org_units.update,
                id=ou_id,
                tenant=self.tenant_id,
                **update_data,
            )

            logger.info(
                "updated_ou",
                ou_id=ou_id,
                tenant=self.tenant_id,
            )

        return await self.get_ou(ou_id)

    async def delete_ou(self, ou_id: str) -> bool:
        """Delete an organizational unit.

        Args:
            ou_id: OU identifier

        Returns:
            True if successful, False if not found
        """
        existing = await self.get_ou(ou_id)
        if not existing:
            return False

        async with self._lock:
            await asyncio.to_thread(
                self.db.org_units.delete,
                id=ou_id,
                tenant=self.tenant_id,
            )

            logger.info(
                "deleted_ou",
                ou_id=ou_id,
                tenant=self.tenant_id,
            )

        return True
