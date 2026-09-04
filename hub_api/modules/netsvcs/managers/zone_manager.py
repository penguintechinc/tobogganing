"""DNS zones and records management using penguin-dal."""
from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = structlog.get_logger()


@dataclass(slots=True)
class DNSZoneRecord:
    """DNS zone data structure."""

    id: str
    name: str
    visibility: str
    description: str | None
    tenant: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class DNSRecordRecord:
    """DNS record data structure."""

    id: str
    zone_id: str
    name: str
    type: str
    value: str
    ttl: int
    priority: int | None
    weight: int | None
    port: int | None
    tenant: str
    created_at: datetime
    updated_at: datetime


class ZoneManager:
    """Manages DNS zones and records using penguin-dal."""

    def __init__(self, db: Any, tenant_id: str) -> None:
        """Initialize ZoneManager.

        Args:
            db: penguin-dal AsyncDB instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id

    async def list_zones(self) -> list[DNSZoneRecord]:
        """List all zones for this tenant.

        Returns:
            List of DNSZoneRecord instances
        """
        rowset = await self.db(
            self.db.dns_zones.tenant == self.tenant_id
        ).select()
        return [
            DNSZoneRecord(
                id=row.id,
                name=row.name,
                visibility=row.visibility,
                description=row.description,
                tenant=row.tenant,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rowset
        ]

    async def create_zone(
        self,
        name: str,
        visibility: str = "public",
        description: str | None = None,
    ) -> DNSZoneRecord | None:
        """Create a new zone for this tenant.

        Enforces per-tenant name uniqueness. Returns None on duplicate name.

        Args:
            name: Zone name (must be unique per tenant)
            visibility: Zone visibility (public/internal/restricted/private)
            description: Optional zone description

        Returns:
            DNSZoneRecord if created, None if duplicate name in tenant
        """
        # Check for duplicate name in tenant
        rowset = await self.db(
            (self.db.dns_zones.tenant == self.tenant_id)
            & (self.db.dns_zones.name == name)
        ).select()
        if rowset.first():
            logger.warning(
                "zone_create_duplicate_name",
                tenant=self.tenant_id,
                name=name,
            )
            return None

        zone_id = str(__import__("uuid").uuid4())
        now = datetime.now(timezone.utc)

        await self.db.dns_zones.async_insert(
            id=zone_id,
            tenant=self.tenant_id,
            name=name,
            visibility=visibility,
            description=description,
            created_at=now,
            updated_at=now,
        )

        logger.info(
            "zone_created",
            zone_id=zone_id,
            tenant=self.tenant_id,
            name=name,
            visibility=visibility,
        )

        return DNSZoneRecord(
            id=zone_id,
            name=name,
            visibility=visibility,
            description=description,
            tenant=self.tenant_id,
            created_at=now,
            updated_at=now,
        )

    async def get_zone(self, zone_id: str) -> DNSZoneRecord | None:
        """Get a single zone by ID.

        Args:
            zone_id: Zone ID to retrieve

        Returns:
            DNSZoneRecord if found, None otherwise
        """
        rowset = await self.db(
            (self.db.dns_zones.id == zone_id)
            & (self.db.dns_zones.tenant == self.tenant_id)
        ).select()
        row = rowset.first()

        if not row:
            return None

        return DNSZoneRecord(
            id=row.id,
            name=row.name,
            visibility=row.visibility,
            description=row.description,
            tenant=row.tenant,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def update_zone(
        self,
        zone_id: str,
        name: str | None = None,
        visibility: str | None = None,
        description: str | None = None,
    ) -> DNSZoneRecord | None:
        """Update an existing zone.

        Args:
            zone_id: Zone ID to update
            name: New zone name (must remain unique per tenant)
            visibility: New visibility value
            description: New description

        Returns:
            Updated DNSZoneRecord if found, None otherwise
        """
        # Verify zone exists and belongs to tenant
        zone = await self.get_zone(zone_id)
        if not zone:
            return None

        # Check for name uniqueness if changing name
        if name and name != zone.name:
            rowset = await self.db(
                (self.db.dns_zones.tenant == self.tenant_id)
                & (self.db.dns_zones.name == name)
                & (self.db.dns_zones.id != zone_id)
            ).select()
            if rowset.first():
                logger.warning(
                    "zone_update_duplicate_name",
                    zone_id=zone_id,
                    tenant=self.tenant_id,
                    name=name,
                )
                return None

        now = datetime.now(timezone.utc)
        updates = {}

        if name:
            updates["name"] = name
        if visibility:
            updates["visibility"] = visibility
        if description is not None:
            updates["description"] = description

        updates["updated_at"] = now

        await self.db(
            (self.db.dns_zones.id == zone_id)
            & (self.db.dns_zones.tenant == self.tenant_id)
        ).update(**updates)

        logger.info(
            "zone_updated",
            zone_id=zone_id,
            tenant=self.tenant_id,
            updates=updates.keys(),
        )

        return DNSZoneRecord(
            id=zone.id,
            name=name or zone.name,
            visibility=visibility or zone.visibility,
            description=description if description is not None else zone.description,
            tenant=self.tenant_id,
            created_at=zone.created_at,
            updated_at=now,
        )

    async def delete_zone(self, zone_id: str) -> bool:
        """Delete a zone and cascade records.

        Args:
            zone_id: Zone ID to delete

        Returns:
            True if deleted, False if not found
        """
        # Verify zone belongs to tenant
        zone = await self.get_zone(zone_id)
        if not zone:
            return False

        # Delete records (cascade)
        await self.db(
            (self.db.dns_records.zone_id == zone_id)
            & (self.db.dns_records.tenant == self.tenant_id)
        ).delete()

        # Delete zone
        await self.db(
            (self.db.dns_zones.id == zone_id)
            & (self.db.dns_zones.tenant == self.tenant_id)
        ).delete()

        logger.info(
            "zone_deleted",
            zone_id=zone_id,
            tenant=self.tenant_id,
        )

        return True

    async def list_records(self, zone_id: str) -> list[DNSRecordRecord]:
        """List all records for a zone.

        Args:
            zone_id: Zone ID to list records for

        Returns:
            List of DNSRecordRecord instances
        """
        rowset = await self.db(
            (self.db.dns_records.zone_id == zone_id)
            & (self.db.dns_records.tenant == self.tenant_id)
        ).select()
        return [
            DNSRecordRecord(
                id=row.id,
                zone_id=row.zone_id,
                name=row.name,
                type=row.type,
                value=row.value,
                ttl=row.ttl,
                priority=row.priority,
                weight=row.weight,
                port=row.port,
                tenant=row.tenant,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rowset
        ]

    async def create_record(
        self,
        zone_id: str,
        name: str,
        type: str,
        value: str,
        ttl: int = 300,
        priority: int | None = None,
        weight: int | None = None,
        port: int | None = None,
    ) -> DNSRecordRecord | None:
        """Create a new record in a zone.

        Verifies zone belongs to tenant and type is valid.

        Args:
            zone_id: Zone ID
            name: Record name
            type: Record type (A, AAAA, CNAME, MX, TXT, NS, SOA, PTR, SRV)
            value: Record value
            ttl: Time to live (default 300)
            priority: Priority (for MX, SRV)
            weight: Weight (for SRV)
            port: Port (for SRV)

        Returns:
            DNSRecordRecord if created, None if zone not found or invalid type
        """
        # Validate zone belongs to tenant
        zone = await self.get_zone(zone_id)
        if not zone:
            logger.warning(
                "record_create_zone_not_found",
                zone_id=zone_id,
                tenant=self.tenant_id,
            )
            return None

        # Validate record type
        valid_types = {"A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "PTR", "SRV"}
        if type not in valid_types:
            logger.warning(
                "record_create_invalid_type",
                type=type,
                tenant=self.tenant_id,
            )
            return None

        # Validate TTL
        if ttl < 0:
            logger.warning(
                "record_create_invalid_ttl",
                ttl=ttl,
                tenant=self.tenant_id,
            )
            return None

        record_id = str(__import__("uuid").uuid4())
        now = datetime.now(timezone.utc)

        await self.db.dns_records.async_insert(
            id=record_id,
            zone_id=zone_id,
            tenant=self.tenant_id,
            name=name,
            type=type,
            value=value,
            ttl=ttl,
            priority=priority,
            weight=weight,
            port=port,
            created_at=now,
            updated_at=now,
        )

        logger.info(
            "record_created",
            record_id=record_id,
            zone_id=zone_id,
            tenant=self.tenant_id,
            type=type,
        )

        return DNSRecordRecord(
            id=record_id,
            zone_id=zone_id,
            name=name,
            type=type,
            value=value,
            ttl=ttl,
            priority=priority,
            weight=weight,
            port=port,
            tenant=self.tenant_id,
            created_at=now,
            updated_at=now,
        )

    async def get_record(
        self, zone_id: str, record_id: str
    ) -> DNSRecordRecord | None:
        """Get a single record by ID.

        Args:
            zone_id: Zone ID
            record_id: Record ID to retrieve

        Returns:
            DNSRecordRecord if found, None otherwise
        """
        rowset = await self.db(
            (self.db.dns_records.id == record_id)
            & (self.db.dns_records.zone_id == zone_id)
            & (self.db.dns_records.tenant == self.tenant_id)
        ).select()
        row = rowset.first()

        if not row:
            return None

        return DNSRecordRecord(
            id=row.id,
            zone_id=row.zone_id,
            name=row.name,
            type=row.type,
            value=row.value,
            ttl=row.ttl,
            priority=row.priority,
            weight=row.weight,
            port=row.port,
            tenant=row.tenant,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def update_record(
        self,
        zone_id: str,
        record_id: str,
        name: str | None = None,
        type: str | None = None,
        value: str | None = None,
        ttl: int | None = None,
        priority: int | None = None,
        weight: int | None = None,
        port: int | None = None,
    ) -> DNSRecordRecord | None:
        """Update an existing record.

        Args:
            zone_id: Zone ID
            record_id: Record ID to update
            name: New record name
            type: New record type
            value: New record value
            ttl: New TTL
            priority: New priority
            weight: New weight
            port: New port

        Returns:
            Updated DNSRecordRecord if found, None otherwise
        """
        # Verify record exists and belongs to tenant/zone
        record = await self.get_record(zone_id, record_id)
        if not record:
            return None

        # Validate new type if changing
        if type and type not in {
            "A",
            "AAAA",
            "CNAME",
            "MX",
            "TXT",
            "NS",
            "SOA",
            "PTR",
            "SRV",
        }:
            logger.warning(
                "record_update_invalid_type",
                record_id=record_id,
                tenant=self.tenant_id,
                type=type,
            )
            return None

        # Validate TTL if changing
        if ttl is not None and ttl < 0:
            logger.warning(
                "record_update_invalid_ttl",
                record_id=record_id,
                tenant=self.tenant_id,
                ttl=ttl,
            )
            return None

        now = datetime.now(timezone.utc)
        updates = {}

        if name:
            updates["name"] = name
        if type:
            updates["type"] = type
        if value:
            updates["value"] = value
        if ttl is not None:
            updates["ttl"] = ttl
        if priority is not None:
            updates["priority"] = priority
        if weight is not None:
            updates["weight"] = weight
        if port is not None:
            updates["port"] = port

        updates["updated_at"] = now

        await self.db(
            (self.db.dns_records.id == record_id)
            & (self.db.dns_records.zone_id == zone_id)
            & (self.db.dns_records.tenant == self.tenant_id)
        ).update(**updates)

        logger.info(
            "record_updated",
            record_id=record_id,
            zone_id=zone_id,
            tenant=self.tenant_id,
        )

        return DNSRecordRecord(
            id=record.id,
            zone_id=record.zone_id,
            name=name or record.name,
            type=type or record.type,
            value=value or record.value,
            ttl=ttl if ttl is not None else record.ttl,
            priority=priority if priority is not None else record.priority,
            weight=weight if weight is not None else record.weight,
            port=port if port is not None else record.port,
            tenant=self.tenant_id,
            created_at=record.created_at,
            updated_at=now,
        )

    async def delete_record(self, zone_id: str, record_id: str) -> bool:
        """Delete a record.

        Args:
            zone_id: Zone ID
            record_id: Record ID to delete

        Returns:
            True if deleted, False if not found
        """
        # Verify record belongs to tenant/zone
        record = await self.get_record(zone_id, record_id)
        if not record:
            return False

        # Delete record
        await self.db(
            (self.db.dns_records.id == record_id)
            & (self.db.dns_records.zone_id == zone_id)
            & (self.db.dns_records.tenant == self.tenant_id)
        ).delete()

        logger.info(
            "record_deleted",
            record_id=record_id,
            zone_id=zone_id,
            tenant=self.tenant_id,
        )

        return True
