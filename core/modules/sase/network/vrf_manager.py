"""VRF (Virtual Routing and Forwarding) management using penguin-dal."""
from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class VRFStatus(Enum):
    """VRF operational status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    ERROR = "error"


class OSPFAreaType(Enum):
    """OSPF area type classification."""

    NORMAL = "normal"
    STUB = "stub"
    NSSA = "nssa"
    BACKBONE = "backbone"


@dataclass(slots=True)
class VRFConfiguration:
    """VRF configuration data structure."""

    id: str
    tenant: str
    name: str
    description: str | None
    rd: str  # Route Distinguisher (ASN:value or IP:value)
    rt_import: list[str] = field(default_factory=list)
    rt_export: list[str] = field(default_factory=list)
    ip_ranges: list[str] = field(default_factory=list)
    status: VRFStatus = VRFStatus.INACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    ospf_enabled: bool = False
    ospf_router_id: str | None = None


@dataclass(slots=True)
class OSPFArea:
    """OSPF area configuration."""

    id: str
    tenant: str
    vrf_id: str
    area_id: str  # Area ID (0.0.0.0 for backbone)
    area_type: OSPFAreaType
    networks: list[str] = field(default_factory=list)
    auth_type: str | None = None  # none, simple, md5
    auth_key: str | None = None
    stub_default_cost: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class OSPFNeighbor:
    """OSPF neighbor relationship."""

    id: str
    tenant: str
    vrf_id: str
    neighbor_id: str
    neighbor_ip: str
    interface: str
    area_id: str
    state: str = "Down"  # Full, 2-Way, etc.
    priority: int = 1
    dead_interval: int = 40
    hello_interval: int = 10
    last_seen: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class VRFManager:
    """Manages VRF configurations via penguin-dal."""

    def __init__(self, db: Any) -> None:
        """Initialize VRF manager with a DAL instance.

        Args:
            db: penguin-dal DAL instance for database operations.
        """
        self.db = db

    async def create_vrf(self, vrf: VRFConfiguration) -> bool:
        """Create a new VRF configuration.

        Args:
            vrf: VRFConfiguration to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            # Validate Route Distinguisher format
            if not self._validate_rd(vrf.rd):
                logger.error("invalid_route_distinguisher", rd=vrf.rd)
                return False

            # Validate IP ranges
            for ip_range in vrf.ip_ranges:
                try:
                    ipaddress.ip_network(ip_range, strict=False)
                except ValueError as e:
                    logger.error("invalid_ip_range", ip_range=ip_range, error=str(e))
                    return False

            await self.db.vrfs.async_insert(
                id=vrf.id,
                tenant=vrf.tenant,
                name=vrf.name,
                description=vrf.description,
                rd=vrf.rd,
                rt_import=json.dumps(vrf.rt_import),
                rt_export=json.dumps(vrf.rt_export),
                ip_ranges=json.dumps(vrf.ip_ranges),
                status=vrf.status.value,
                ospf_enabled=vrf.ospf_enabled,
                ospf_router_id=vrf.ospf_router_id,
                is_active=vrf.is_active,
                created_at=vrf.created_at,
                updated_at=vrf.updated_at,
            )

            logger.info("vrf_created", vrf_id=vrf.id, tenant=vrf.tenant, name=vrf.name)
            return True

        except Exception as e:
            logger.error("failed_to_create_vrf", error=str(e))
            return False

    async def update_vrf(self, vrf: VRFConfiguration) -> bool:
        """Update an existing VRF configuration.

        Args:
            vrf: VRFConfiguration with updated values.

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            vrf.updated_at = datetime.utcnow()

            await self.db(
                self.db.vrfs.id == vrf.id,
                self.db.vrfs.tenant == vrf.tenant,
            ).update(
                name=vrf.name,
                description=vrf.description,
                rd=vrf.rd,
                rt_import=json.dumps(vrf.rt_import),
                rt_export=json.dumps(vrf.rt_export),
                ip_ranges=json.dumps(vrf.ip_ranges),
                status=vrf.status.value,
                ospf_enabled=vrf.ospf_enabled,
                ospf_router_id=vrf.ospf_router_id,
                is_active=vrf.is_active,
                updated_at=vrf.updated_at,
            )

            logger.info("vrf_updated", vrf_id=vrf.id, tenant=vrf.tenant)
            return True

        except Exception as e:
            logger.error("failed_to_update_vrf", vrf_id=vrf.id, error=str(e))
            return False

    async def delete_vrf(self, vrf_id: str, tenant: str) -> bool:
        """Delete a VRF configuration.

        Args:
            vrf_id: ID of VRF to delete.
            tenant: Tenant ID for scoping.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            # Delete related OSPF configuration
            await self.db(
                self.db.ospf_neighbors.vrf_id == vrf_id,
                self.db.ospf_neighbors.tenant == tenant,
            ).delete()

            await self.db(
                self.db.ospf_areas.vrf_id == vrf_id,
                self.db.ospf_areas.tenant == tenant,
            ).delete()

            # Delete VRF
            await self.db(
                self.db.vrfs.id == vrf_id,
                self.db.vrfs.tenant == tenant,
            ).delete()

            logger.info("vrf_deleted", vrf_id=vrf_id, tenant=tenant)
            return True

        except Exception as e:
            logger.error("failed_to_delete_vrf", vrf_id=vrf_id, error=str(e))
            return False

    async def get_vrf(self, vrf_id: str, tenant: str) -> VRFConfiguration | None:
        """Get a VRF configuration by ID.

        Args:
            vrf_id: ID of VRF to retrieve.
            tenant: Tenant ID for scoping.

        Returns:
            VRFConfiguration if found, None otherwise.
        """
        try:
            rowset = await self.db(
                self.db.vrfs.id == vrf_id,
                self.db.vrfs.tenant == tenant,
            ).select()

            row = rowset.first() if rowset else None
            if not row:
                return None

            return VRFConfiguration(
                id=row.id,
                tenant=row.tenant,
                name=row.name,
                description=row.description,
                rd=row.rd,
                rt_import=json.loads(row.rt_import) if row.rt_import else [],
                rt_export=json.loads(row.rt_export) if row.rt_export else [],
                ip_ranges=json.loads(row.ip_ranges) if row.ip_ranges else [],
                status=VRFStatus(row.status),
                created_at=row.created_at,
                updated_at=row.updated_at,
                is_active=row.is_active,
                ospf_enabled=row.ospf_enabled,
                ospf_router_id=row.ospf_router_id,
            )

        except Exception as e:
            logger.error("failed_to_get_vrf", vrf_id=vrf_id, tenant=tenant, error=str(e))
            return None

    async def list_vrfs(self, tenant: str, active_only: bool = True) -> list[VRFConfiguration]:
        """List all VRF configurations for a tenant.

        Args:
            tenant: Tenant ID for scoping.
            active_only: Filter to active VRFs only.

        Returns:
            List of VRFConfiguration objects.
        """
        try:
            if active_only:
                rowset = await self.db(
                    self.db.vrfs.tenant == tenant,
                    self.db.vrfs.is_active == True,  # noqa: E712
                ).select(orderby=self.db.vrfs.name)
            else:
                rowset = await self.db(
                    self.db.vrfs.tenant == tenant,
                ).select(orderby=self.db.vrfs.name)

            vrfs: list[VRFConfiguration] = []
            for row in rowset:
                vrf = VRFConfiguration(
                    id=row.id,
                    tenant=row.tenant,
                    name=row.name,
                    description=row.description,
                    rd=row.rd,
                    rt_import=json.loads(row.rt_import) if row.rt_import else [],
                    rt_export=json.loads(row.rt_export) if row.rt_export else [],
                    ip_ranges=json.loads(row.ip_ranges) if row.ip_ranges else [],
                    status=VRFStatus(row.status),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    is_active=row.is_active,
                    ospf_enabled=row.ospf_enabled,
                    ospf_router_id=row.ospf_router_id,
                )
                vrfs.append(vrf)

            return vrfs

        except Exception as e:
            logger.error("failed_to_list_vrfs", tenant=tenant, error=str(e))
            return []

    async def create_ospf_area(self, area: OSPFArea) -> bool:
        """Create an OSPF area within a VRF.

        Args:
            area: OSPFArea to create.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            await self.db.ospf_areas.async_insert(
                id=area.id,
                tenant=area.tenant,
                vrf_id=area.vrf_id,
                area_id=area.area_id,
                area_type=area.area_type.value,
                networks=json.dumps(area.networks),
                auth_type=area.auth_type,
                auth_key=area.auth_key,
                stub_default_cost=area.stub_default_cost,
                created_at=area.created_at,
                updated_at=area.updated_at,
            )

            logger.info(
                "ospf_area_created",
                area_id=area.area_id,
                vrf_id=area.vrf_id,
                tenant=area.tenant,
            )
            return True

        except Exception as e:
            logger.error("failed_to_create_ospf_area", error=str(e))
            return False

    async def get_ospf_neighbors(
        self, vrf_id: str, tenant: str
    ) -> list[OSPFNeighbor]:
        """Get OSPF neighbors for a VRF.

        Args:
            vrf_id: ID of VRF.
            tenant: Tenant ID for scoping.

        Returns:
            List of OSPFNeighbor objects.
        """
        try:
            rowset = await self.db(
                self.db.ospf_neighbors.vrf_id == vrf_id,
                self.db.ospf_neighbors.tenant == tenant,
            ).select()

            neighbors: list[OSPFNeighbor] = []
            for row in rowset:
                neighbor = OSPFNeighbor(
                    id=row.id,
                    tenant=row.tenant,
                    vrf_id=row.vrf_id,
                    neighbor_id=row.neighbor_id,
                    neighbor_ip=row.neighbor_ip,
                    interface=row.interface,
                    area_id=row.area_id,
                    state=row.state,
                    priority=row.priority,
                    dead_interval=row.dead_interval,
                    hello_interval=row.hello_interval,
                    last_seen=row.last_seen,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                neighbors.append(neighbor)

            return neighbors

        except Exception as e:
            logger.error(
                "failed_to_get_ospf_neighbors",
                vrf_id=vrf_id,
                tenant=tenant,
                error=str(e),
            )
            return []

    async def generate_frr_config(self, vrf_id: str, tenant: str) -> str:
        """Generate complete FRR configuration for a VRF.

        Args:
            vrf_id: ID of VRF.
            tenant: Tenant ID for scoping.

        Returns:
            FRR configuration string.
        """
        try:
            vrf = await self.get_vrf(vrf_id, tenant)
            if not vrf:
                return ""

            config_lines = [
                "! FRR Configuration for VRF: " + vrf.name,
                "! Generated by SASEWaddle Manager",
                f"! Generated at: {datetime.utcnow().isoformat()}",
                "!",
                f"vrf {vrf.name}",
                f" description {vrf.description or ''}",
                f" rd {vrf.rd}",
            ]

            for rt in vrf.rt_import:
                config_lines.append(f" import rt {rt}")

            for rt in vrf.rt_export:
                config_lines.append(f" export rt {rt}")

            config_lines.append(" exit")
            config_lines.append("!")

            if vrf.ospf_enabled and vrf.ospf_router_id:
                config_lines.extend([
                    f"router ospf vrf {vrf.name}",
                    f" router-id {vrf.ospf_router_id}",
                    " log-adjacency-changes",
                    " passive-interface default",
                ])

                # Get OSPF areas to add networks
                areas = await self.db(
                    self.db.ospf_areas.vrf_id == vrf_id,
                    self.db.ospf_areas.tenant == tenant,
                ).select()

                for area_row in areas:
                    networks = json.loads(area_row.networks) if area_row.networks else []
                    for network in networks:
                        config_lines.append(f" network {network} area {area_row.area_id}")

                config_lines.append(" exit")
                config_lines.append("!")

            return "\n".join(config_lines)

        except Exception as e:
            logger.error(
                "failed_to_generate_frr_config", vrf_id=vrf_id, error=str(e)
            )
            return ""

    @staticmethod
    def _validate_rd(rd: str) -> bool:
        """Validate Route Distinguisher format (ASN:value or IP:value).

        Args:
            rd: Route Distinguisher string to validate.

        Returns:
            True if valid, False otherwise.
        """
        try:
            if ":" not in rd:
                return False

            parts = rd.split(":")
            if len(parts) != 2:
                return False

            left, right = parts

            # Check if left part is ASN (number) or IP address
            try:
                # Try as ASN
                asn = int(left)
                if not (1 <= asn <= 4294967295):  # Valid ASN range
                    return False
            except ValueError:
                # Try as IP address
                try:
                    ipaddress.ip_address(left)
                except ValueError:
                    return False

            # Right part should be a number
            try:
                value = int(right)
                if not (0 <= value <= 65535):
                    return False
            except ValueError:
                return False

            return True

        except Exception:
            return False
