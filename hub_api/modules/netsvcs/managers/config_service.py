"""DNS configuration assembly and versioning service using penguin-dal."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()

# Zone visibility levels the resolver's SelectiveRouter understands. Anything
# else is dropped from the pushed config (fail closed: an unknown level must
# never be served as if it were public).
VALID_VISIBILITIES: frozenset[str] = frozenset({"public", "internal", "restricted", "private"})

# Defaults used when a tenant has no dns_resolver_settings row; these mirror the
# column server defaults in migration 0029.
DEFAULT_RESOLVER_SETTINGS: dict[str, Any] = {
    "cache_enabled": True,
    "cache_ttl": 300,
    "cache_max_entries": 10000,
    "log_queries": True,
    "enable_dnssec": False,
    "ioc_filtering": True,
}

_BOOL_SETTINGS = ("cache_enabled", "log_queries", "enable_dnssec", "ioc_filtering")
_INT_SETTINGS = {"cache_ttl": (0, 86400), "cache_max_entries": (0, 10_000_000)}


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

    id: str
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
        rowset = await self.db(self.db.dns_config_versions.tenant == self.tenant_id).select()
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
        zones_rowset = await self.db(self.db.dns_zones.tenant == self.tenant_id).select()

        zone_dtos = []
        dropped = 0
        for zone_row in zones_rowset:
            visibility = (zone_row.visibility or "").strip().lower()
            if visibility not in VALID_VISIBILITIES:
                dropped += 1
                logger.error(
                    "dns_zone_invalid_visibility_dropped",
                    tenant=self.tenant_id,
                    zone_id=zone_row.id,
                    visibility=zone_row.visibility,
                )
                continue

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

            zone_dtos.append(
                DNSZoneDTO(
                    id=zone_row.id,
                    name=zone_row.name,
                    visibility=visibility,
                    records=record_dtos,
                )
            )

        if dropped:
            logger.warning(
                "dns_server_config_zones_dropped", tenant=self.tenant_id, dropped=dropped
            )

        stored = await self.get_resolver_settings()
        cache_settings = {
            "enabled": stored["cache_enabled"],
            "ttl": stored["cache_ttl"],
            "max_entries": stored["cache_max_entries"],
        }
        settings = {
            "log_queries": stored["log_queries"],
            "enable_dnssec": stored["enable_dnssec"],
            "ioc_filtering": stored["ioc_filtering"],
        }

        return DNSServerConfigDTO(
            zones=zone_dtos,
            cache_settings=cache_settings,
            settings=settings,
            version=current_version,
        )

    async def _settings_row(self) -> Any:
        """Return this tenant's dns_resolver_settings row, or None."""
        rowset = await self.db(self.db.dns_resolver_settings.tenant == self.tenant_id).select()
        return rowset.first()

    async def get_resolver_settings(self) -> dict[str, Any]:
        """Return this tenant's stored resolver settings.

        Reads the tenant's dns_resolver_settings row; a tenant with no row
        gets DEFAULT_RESOLVER_SETTINGS.
        """
        row = await self._settings_row()
        if row is None:
            return dict(DEFAULT_RESOLVER_SETTINGS)
        return {
            key: (bool(getattr(row, key)) if key in _BOOL_SETTINGS else int(getattr(row, key)))
            for key in DEFAULT_RESOLVER_SETTINGS
        }

    async def update_resolver_settings(self, **changes: Any) -> dict[str, Any]:
        """Validate and persist resolver settings, then bump the config version.

        Unknown keys or out-of-range/mistyped values raise ValueError before
        anything is written. Returns the full effective settings.
        """
        for key, value in changes.items():
            if key in _BOOL_SETTINGS:
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be a bool")
            elif key in _INT_SETTINGS:
                lo, hi = _INT_SETTINGS[key]
                if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
                    raise ValueError(f"{key} must be an int in [{lo}, {hi}]")
            else:
                raise ValueError(f"unknown resolver setting: {key}")

        merged = await self.get_resolver_settings()
        merged.update(changes)
        now = datetime.now(timezone.utc)

        row = await self._settings_row()
        if row is None:
            await self.db.dns_resolver_settings.async_insert(
                id=str(uuid.uuid4()), tenant=self.tenant_id, updated_at=now, **merged
            )
        else:
            await self.db(self.db.dns_resolver_settings.id == row.id).update(
                updated_at=now, **merged
            )

        await self.bump_version()
        logger.info("dns_resolver_settings_updated", tenant=self.tenant_id, keys=sorted(changes))
        return merged
