"""Port configuration management using penguin-dal."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class PortProtocol(Enum):
    """Supported protocols for port listening."""

    TCP = "tcp"
    UDP = "udp"


@dataclass(slots=True)
class PortRangeConfig:
    """Represents a range of ports for listening."""

    id: str
    tenant: str
    headend_id: str
    cluster_id: str
    start_port: int
    end_port: int
    protocol: PortProtocol
    description: str | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class HeadendPortConfig:
    """Port configuration for a specific headend server."""

    headend_id: str
    cluster_id: str
    tenant: str
    tcp_ranges: list[PortRangeConfig] = field(default_factory=list)
    udp_ranges: list[PortRangeConfig] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class PortConfigManager:
    """Manages port configurations for headend servers via penguin-dal."""

    def __init__(self, db: Any) -> None:
        """Initialize port config manager with a DAL instance.

        Args:
            db: penguin-dal DAL instance for database operations.
        """
        self.db = db

    async def get_headend_config(
        self, headend_id: str, tenant: str
    ) -> HeadendPortConfig | None:
        """Get port configuration for a specific headend.

        Args:
            headend_id: ID of the headend.
            tenant: Tenant ID for scoping.

        Returns:
            HeadendPortConfig if found, None otherwise.
        """
        try:
            rowset = await self.db(
                (self.db.port_ranges.headend_id == headend_id)
                & (self.db.port_ranges.tenant == tenant)
                & (self.db.port_ranges.enabled == True)  # noqa: E712
            ).select(orderby=[self.db.port_ranges.protocol, self.db.port_ranges.start_port])

            if not rowset:
                return None

            tcp_ranges: list[PortRangeConfig] = []
            udp_ranges: list[PortRangeConfig] = []
            cluster_id = None

            for row in rowset:
                cluster_id = row.cluster_id
                port_range = PortRangeConfig(
                    id=row.id,
                    tenant=row.tenant,
                    headend_id=row.headend_id,
                    cluster_id=row.cluster_id,
                    start_port=row.start_port,
                    end_port=row.end_port,
                    protocol=PortProtocol(row.protocol),
                    description=row.description,
                    enabled=row.enabled,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )

                if port_range.protocol == PortProtocol.TCP:
                    tcp_ranges.append(port_range)
                else:
                    udp_ranges.append(port_range)

            if cluster_id is None:
                return None

            return HeadendPortConfig(
                headend_id=headend_id,
                cluster_id=cluster_id,
                tenant=tenant,
                tcp_ranges=tcp_ranges,
                udp_ranges=udp_ranges,
            )

        except Exception as e:
            logger.error(
                "failed_to_get_headend_config",
                headend_id=headend_id,
                tenant=tenant,
                error=str(e),
            )
            return None

    async def get_cluster_config(
        self, cluster_id: str, tenant: str
    ) -> dict[str, HeadendPortConfig]:
        """Get port configurations for all headends in a cluster.

        Args:
            cluster_id: ID of the cluster.
            tenant: Tenant ID for scoping.

        Returns:
            Dictionary mapping headend_id to HeadendPortConfig.
        """
        try:
            rowset = await self.db(
                (self.db.port_ranges.cluster_id == cluster_id)
                & (self.db.port_ranges.tenant == tenant)
                & (self.db.port_ranges.enabled == True)  # noqa: E712
            ).select(orderby=self.db.port_ranges.headend_id)

            headend_ids = set()
            for row in rowset:
                headend_ids.add(row.headend_id)

            configs: dict[str, HeadendPortConfig] = {}
            for headend_id in headend_ids:
                config = await self.get_headend_config(headend_id, tenant)
                if config:
                    configs[headend_id] = config

            return configs

        except Exception as e:
            logger.error(
                "failed_to_get_cluster_config",
                cluster_id=cluster_id,
                tenant=tenant,
                error=str(e),
            )
            return {}

    async def add_port_range(
        self,
        headend_id: str,
        cluster_id: str,
        tenant: str,
        port_range: PortRangeConfig,
    ) -> str | None:
        """Add a new port range configuration.

        Args:
            headend_id: ID of the headend.
            cluster_id: ID of the cluster.
            tenant: Tenant ID for scoping.
            port_range: PortRangeConfig to add.

        Returns:
            Port range ID if successful, None otherwise.
        """
        try:
            # Validate port range
            if port_range.start_port < 1 or port_range.end_port > 65535:
                logger.error("invalid_port_range", start=port_range.start_port, end=port_range.end_port)
                return None

            if port_range.start_port > port_range.end_port:
                logger.error("start_port_greater_than_end_port")
                return None

            # Check for overlaps
            if await self._has_port_overlap(
                headend_id, tenant, port_range
            ):
                logger.error(
                    "port_range_overlap",
                    start=port_range.start_port,
                    end=port_range.end_port,
                )
                return None

            await self.db.port_ranges.async_insert(
                id=port_range.id,
                tenant=tenant,
                headend_id=headend_id,
                cluster_id=cluster_id,
                start_port=port_range.start_port,
                end_port=port_range.end_port,
                protocol=port_range.protocol.value,
                description=port_range.description,
                enabled=port_range.enabled,
                created_at=port_range.created_at,
                updated_at=port_range.updated_at,
            )

            logger.info(
                "port_range_added",
                range_id=port_range.id,
                headend_id=headend_id,
                protocol=port_range.protocol.value,
                tenant=tenant,
            )
            return port_range.id

        except Exception as e:
            logger.error("failed_to_add_port_range", error=str(e))
            return None

    async def remove_port_range(self, range_id: str, tenant: str) -> bool:
        """Remove a port range configuration.

        Args:
            range_id: ID of the port range to remove.
            tenant: Tenant ID for scoping.

        Returns:
            True if removed successfully, False otherwise.
        """
        try:
            await self.db(
                (self.db.port_ranges.id == range_id)
                & (self.db.port_ranges.tenant == tenant)
            ).delete()

            logger.info("port_range_removed", range_id=range_id, tenant=tenant)
            return True

        except Exception as e:
            logger.error("failed_to_remove_port_range", range_id=range_id, error=str(e))
            return False

    async def update_port_range(
        self, range_id: str, tenant: str, **kwargs: Any
    ) -> bool:
        """Update a port range configuration.

        Args:
            range_id: ID of the port range to update.
            tenant: Tenant ID for scoping.
            **kwargs: Fields to update (start_port, end_port, protocol, description, enabled).

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            valid_fields = {
                "start_port",
                "end_port",
                "protocol",
                "description",
                "enabled",
            }
            updates = {k: v for k, v in kwargs.items() if k in valid_fields}

            if not updates:
                return False

            updates["updated_at"] = datetime.utcnow()

            await self.db(
                (self.db.port_ranges.id == range_id)
                & (self.db.port_ranges.tenant == tenant)
            ).update(**updates)

            logger.info("port_range_updated", range_id=range_id, tenant=tenant)
            return True

        except Exception as e:
            logger.error("failed_to_update_port_range", range_id=range_id, error=str(e))
            return False

    async def get_all_configs(self, tenant: str) -> dict[str, HeadendPortConfig]:
        """Get all port configurations for all headends in a tenant.

        Args:
            tenant: Tenant ID for scoping.

        Returns:
            Dictionary mapping headend_id to HeadendPortConfig.
        """
        try:
            rowset = await self.db(
                (self.db.port_ranges.tenant == tenant)
                & (self.db.port_ranges.enabled == True)  # noqa: E712
            ).select(orderby=self.db.port_ranges.headend_id)

            headend_ids = set()
            for row in rowset:
                headend_ids.add(row.headend_id)

            configs: dict[str, HeadendPortConfig] = {}
            for headend_id in headend_ids:
                config = await self.get_headend_config(headend_id, tenant)
                if config:
                    configs[headend_id] = config

            return configs

        except Exception as e:
            logger.error("failed_to_get_all_configs", tenant=tenant, error=str(e))
            return {}

    async def set_default_config(
        self, headend_id: str, cluster_id: str, tenant: str
    ) -> bool:
        """Set default port configuration for a headend.

        Args:
            headend_id: ID of the headend.
            cluster_id: ID of the cluster.
            tenant: Tenant ID for scoping.

        Returns:
            True if successful, False otherwise.
        """
        try:
            import uuid

            default_ranges = [
                PortRangeConfig(
                    id=str(uuid.uuid4()),
                    tenant=tenant,
                    headend_id=headend_id,
                    cluster_id=cluster_id,
                    start_port=8443,
                    end_port=8443,
                    protocol=PortProtocol.TCP,
                    description="HTTPS Proxy",
                ),
                PortRangeConfig(
                    id=str(uuid.uuid4()),
                    tenant=tenant,
                    headend_id=headend_id,
                    cluster_id=cluster_id,
                    start_port=8444,
                    end_port=8444,
                    protocol=PortProtocol.TCP,
                    description="TCP Proxy",
                ),
                PortRangeConfig(
                    id=str(uuid.uuid4()),
                    tenant=tenant,
                    headend_id=headend_id,
                    cluster_id=cluster_id,
                    start_port=8445,
                    end_port=8445,
                    protocol=PortProtocol.UDP,
                    description="UDP Proxy",
                ),
                PortRangeConfig(
                    id=str(uuid.uuid4()),
                    tenant=tenant,
                    headend_id=headend_id,
                    cluster_id=cluster_id,
                    start_port=3000,
                    end_port=3010,
                    protocol=PortProtocol.TCP,
                    description="Development Services",
                ),
                PortRangeConfig(
                    id=str(uuid.uuid4()),
                    tenant=tenant,
                    headend_id=headend_id,
                    cluster_id=cluster_id,
                    start_port=8000,
                    end_port=8010,
                    protocol=PortProtocol.TCP,
                    description="Web Services",
                ),
                PortRangeConfig(
                    id=str(uuid.uuid4()),
                    tenant=tenant,
                    headend_id=headend_id,
                    cluster_id=cluster_id,
                    start_port=9000,
                    end_port=9010,
                    protocol=PortProtocol.TCP,
                    description="Application Services",
                ),
            ]

            for port_range in default_ranges:
                result = await self.add_port_range(
                    headend_id, cluster_id, tenant, port_range
                )
                if result is None:
                    logger.warning(
                        "could_not_add_default_range",
                        start=port_range.start_port,
                        end=port_range.end_port,
                    )

            return True

        except Exception as e:
            logger.error("failed_to_set_default_config", error=str(e))
            return False

    async def _has_port_overlap(
        self, headend_id: str, tenant: str, new_range: PortRangeConfig
    ) -> bool:
        """Check if a new port range overlaps with existing ranges.

        Args:
            headend_id: ID of the headend.
            tenant: Tenant ID for scoping.
            new_range: Port range to check.

        Returns:
            True if overlap detected, False otherwise.
        """
        try:
            rowset = await self.db(
                (self.db.port_ranges.headend_id == headend_id)
                & (self.db.port_ranges.tenant == tenant)
                & (self.db.port_ranges.protocol == new_range.protocol.value)
                & (self.db.port_ranges.enabled == True)  # noqa: E712
            ).select()

            for row in rowset:
                # Check if ranges overlap
                if (
                    (row.start_port <= new_range.start_port <= row.end_port)
                    or (row.start_port <= new_range.end_port <= row.end_port)
                    or (new_range.start_port <= row.start_port <= new_range.end_port)
                ):
                    return True

            return False

        except Exception as e:
            logger.error(
                "failed_to_check_port_overlap",
                headend_id=headend_id,
                error=str(e),
            )
            return False
