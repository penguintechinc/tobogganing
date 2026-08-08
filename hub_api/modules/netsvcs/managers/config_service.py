"""DNS configuration assembly and versioning service using penguin-dal."""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = structlog.get_logger()


@dataclass(slots=True)
class DNSRecordDTO:
    """DNS record data transfer object."""

    name: str
    type: str
    value: str
    ttl: int
    priority: int | None = None
    weight: int | None = None
    port: int | None = None


@dataclass(slots=True)
class DNSZoneDTO:
    """DNS zone data transfer object."""

    name: str
    visibility: str
    records: list[DNSRecordDTO] = field(default_factory=list)


@dataclass(slots=True)
class DNSServerConfigDTO:
    """Complete DNS server configuration."""

    zones: list[DNSZoneDTO] = field(default_factory=list)
    cache_settings: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    version: int = 0


class ConfigService:
    """Assembles resolver configuration and manages config versioning."""

    def __init__(self, db: Any, tenant_id: str) -> None:
        """Initialize ConfigService.

        Args:
            db: penguin-dal AsyncDB instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id

    async def get_config_version(self) -> int:
        """Get current config version for this tenant.

        Returns:
            Version number (monotonic counter)
        """
        rowset = await self.db(
            self.db.dns_config_versions.tenant == self.tenant_id,
        ).select()
        row = rowset.first()

        if not row:
            return 0

        return row.version

    async def bump_version(self) -> int:
        """Increment config version for this tenant.

        Creates the version row if absent. Returns the new version.

        NOTE: This read-then-write is NOT atomic. penguin-dal does not support
        column-expression updates (e.g., SET version = version + 1) required for
        true atomicity. In a high-concurrency environment, concurrent bump calls
        may drop increments. This is acceptable for DNS config versioning (a client
        checking a slightly-stale version still pulls the latest config on next
        sync), but would require a database-level trigger or SQLAlchemy direct
        execution for full atomicity. Limitation accepted; document if upgrading.

        Returns:
            New monotonic version number
        """
        # Try to get existing version row
        rowset = await self.db(
            self.db.dns_config_versions.tenant == self.tenant_id
        ).select()
        row = rowset.first()

        now = datetime.now(timezone.utc)

        if row:
            # Increment existing (non-atomic, see NOTE above)
            new_version = row.version + 1
            await self.db(
                self.db.dns_config_versions.id == row.id,
            ).update(
                version=new_version,
                updated_at=now,
            )
        else:
            # Create new version row starting at 1
            version_id = str(__import__("uuid").uuid4())
            await self.db.dns_config_versions.async_insert(
                id=version_id,
                tenant=self.tenant_id,
                scope_key="default",  # Monotonic counter per tenant
                version=1,
                updated_at=now,
            )
            new_version = 1

        logger.info(
            "config_version_bumped",
            tenant=self.tenant_id,
            version=new_version,
        )

        return new_version

    async def get_server_config(self) -> DNSServerConfigDTO:
        """Assemble complete server configuration for this tenant.

        Gathers all zones and their records for the tenant.
        Includes hook for threatintel IOC enrichment (not implemented in S1a).

        Returns:
            DNSServerConfigDTO with zones, cache settings, and version
        """
        # Get current version (monotonic, bumped on zone/record changes)
        current_version = await self.get_config_version()

        # Fetch all zones for this tenant
        zones_rowset = await self.db(
            self.db.dns_zones.tenant == self.tenant_id
        ).select()

        zone_dtos = []
        for zone_row in zones_rowset:
            # Fetch records for this zone
            records_rowset = await self.db(
                (self.db.dns_records.zone_id == zone_row.id)
                & (self.db.dns_records.tenant == self.tenant_id)
            ).select()

            record_dtos = [
                DNSRecordDTO(
                    name=rec.name,
                    type=rec.type,
                    value=rec.value,
                    ttl=rec.ttl,
                    priority=rec.priority,
                    weight=rec.weight,
                    port=rec.port,
                )
                for rec in records_rowset
            ]

            # TODO (S2): Threatintel IOC enrichment hook
            # Call BlocklistStore.check("domain", rec.name) for filtering
            # Apply visibility filtering (public/internal/restricted/private)

            zone_dtos.append(
                DNSZoneDTO(
                    name=zone_row.name,
                    visibility=zone_row.visibility,
                    records=record_dtos,
                )
            )

        # Placeholder cache/settings (S1a minimal)
        cache_settings = {
            "ttl": 300,
            "max_entries": 10000,
        }
        settings = {
            "log_queries": True,
            "enable_dnssec": False,
            # S2: Threatintel IOC filtering enabled for this tenant
            "ioc_filtering": True,
        }

        return DNSServerConfigDTO(
            zones=zone_dtos,
            cache_settings=cache_settings,
            settings=settings,
            version=current_version,
        )
