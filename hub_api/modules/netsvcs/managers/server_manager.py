"""DNS server management using penguin-dal."""
from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

logger = structlog.get_logger()


@dataclass(slots=True)
class DNSServerRecord:
    """DNS server data structure."""

    id: str
    name: str
    status: str
    version: str | None
    region: str | None
    hostname: str | None
    last_heartbeat: datetime | None
    tenant: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class DNSMetricsRecord:
    """DNS server metrics data structure."""

    id: str
    server_id: str
    timestamp: datetime
    queries_total: int
    cache_hits: int
    errors: int
    avg_response_ms: float


class ServerManager:
    """Manages DNS server registration and health monitoring using penguin-dal."""

    def __init__(self, db: Any, tenant_id: str) -> None:
        """Initialize ServerManager.

        Args:
            db: penguin-dal AsyncDB instance
            tenant_id: Tenant identifier for scoping queries
        """
        self.db = db
        self.tenant_id = tenant_id

    async def initialize(self) -> None:
        """Initialize the ServerManager."""
        try:
            logger.info("ServerManager initialized", tenant=self.tenant_id)
        except Exception as e:
            logger.error("Failed to initialize ServerManager", error=str(e))
            raise

    async def register_server(
        self,
        name: str,
        hostname: str,
        version: str,
        region: str,
    ) -> DNSServerRecord:
        """Register a new DNS server.

        Args:
            name: Server name
            hostname: Server hostname
            version: Server version
            region: Server region

        Returns:
            DNSServerRecord for the registered server
        """
        server_id = str(__import__("uuid").uuid4())
        now = datetime.now(timezone.utc)

        await self.db.dns_servers.async_insert(
            id=server_id,
            name=name,
            hostname=hostname,
            version=version,
            region=region,
            status="online",
            last_heartbeat=now,
            tenant=self.tenant_id,
            created_at=now,
            updated_at=now,
        )

        record = DNSServerRecord(
            id=server_id,
            name=name,
            status="online",
            version=version,
            region=region,
            hostname=hostname,
            last_heartbeat=now,
            tenant=self.tenant_id,
            created_at=now,
            updated_at=now,
        )

        logger.info(
            "dns_server_registered",
            server_id=server_id,
            name=name,
            region=region,
            tenant=self.tenant_id,
        )

        return record

    async def get_all_servers(self) -> list[DNSServerRecord]:
        """Get all DNS servers for this tenant.

        Returns:
            List of DNSServerRecord instances
        """
        rowset = await self.db(self.db.dns_servers.tenant == self.tenant_id).select()
        return [
            DNSServerRecord(
                id=row.id,
                name=row.name,
                status=row.status,
                version=row.version,
                region=row.region,
                hostname=row.hostname,
                last_heartbeat=row.last_heartbeat,
                tenant=row.tenant,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rowset
        ]

    async def get_server(self, server_id: str) -> DNSServerRecord | None:
        """Get a single DNS server by ID.

        Args:
            server_id: Server ID to retrieve

        Returns:
            DNSServerRecord if found, None otherwise
        """
        rowset = await self.db(
            self.db.dns_servers.id == server_id,
            self.db.dns_servers.tenant == self.tenant_id,
        ).select()
        row = rowset.first()

        if not row:
            return None

        return DNSServerRecord(
            id=row.id,
            name=row.name,
            status=row.status,
            version=row.version,
            region=row.region,
            hostname=row.hostname,
            last_heartbeat=row.last_heartbeat,
            tenant=row.tenant,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def delete_server(self, server_id: str) -> bool:
        """Delete a DNS server and cascade metrics.

        Args:
            server_id: Server ID to delete

        Returns:
            True if deleted, False if not found
        """
        # First verify server belongs to tenant
        server = await self.get_server(server_id)
        if not server:
            logger.warning(
                "delete_server_not_found",
                server_id=server_id,
                tenant=self.tenant_id,
            )
            return False

        # Delete metrics first (cascade)
        await self.db(
            self.db.dns_server_metrics.server_id == server_id,
            self.db.dns_server_metrics.tenant == self.tenant_id,
        ).delete()

        # Delete server
        await self.db(
            self.db.dns_servers.id == server_id,
            self.db.dns_servers.tenant == self.tenant_id,
        ).delete()

        logger.info(
            "dns_server_deleted",
            server_id=server_id,
            tenant=self.tenant_id,
        )

        return True

    async def record_heartbeat(
        self, server_id: str, metrics_dict: dict[str, Any]
    ) -> bool:
        """Record a server heartbeat and ingest metrics.

        Args:
            server_id: Server ID
            metrics_dict: Metrics dictionary with keys:
                queries_total, cache_hits, errors, avg_response_ms

        Returns:
            True if recorded, False if server not found
        """
        # Verify server belongs to tenant
        server = await self.get_server(server_id)
        if not server:
            logger.warning(
                "heartbeat_server_not_found",
                server_id=server_id,
                tenant=self.tenant_id,
            )
            return False

        now = datetime.now(timezone.utc)

        # Update server heartbeat
        await self.db(
            self.db.dns_servers.id == server_id,
            self.db.dns_servers.tenant == self.tenant_id,
        ).update(
            last_heartbeat=now,
            status="online",
            updated_at=now,
        )

        # Insert metrics
        metric_id = str(__import__("uuid").uuid4())
        await self.db.dns_server_metrics.async_insert(
            id=metric_id,
            server_id=server_id,
            tenant=self.tenant_id,
            timestamp=now,
            queries_total=metrics_dict.get("queries_total", 0),
            cache_hits=metrics_dict.get("cache_hits", 0),
            errors=metrics_dict.get("errors", 0),
            avg_response_ms=metrics_dict.get("avg_response_ms", 0.0),
            created_at=now,
        )

        logger.info(
            "server_heartbeat_recorded",
            server_id=server_id,
            queries=metrics_dict.get("queries_total", 0),
            tenant=self.tenant_id,
        )

        return True

    async def get_metrics(
        self, server_id: str, hours: int = 24
    ) -> list[DNSMetricsRecord]:
        """Get metrics for a server in the last N hours.

        Args:
            server_id: Server ID
            hours: Number of hours to look back (default 24)

        Returns:
            List of DNSMetricsRecord instances
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        rowset = await self.db(
            self.db.dns_server_metrics.server_id == server_id,
            self.db.dns_server_metrics.tenant == self.tenant_id,
            self.db.dns_server_metrics.timestamp >= cutoff,
        ).select()

        return [
            DNSMetricsRecord(
                id=row.id,
                server_id=row.server_id,
                timestamp=row.timestamp,
                queries_total=row.queries_total,
                cache_hits=row.cache_hits,
                errors=row.errors,
                avg_response_ms=row.avg_response_ms,
            )
            for row in rowset
        ]
