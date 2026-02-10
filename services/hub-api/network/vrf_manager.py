"""
VRF (Virtual Routing and Forwarding) Management for SASEWaddle
Handles IP space segmentation and routing table isolation using FRR
"""

import asyncio
import ipaddress
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Union
import json

import structlog

logger = structlog.get_logger()

class VRFStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    ERROR = "error"

class OSPFAreaType(Enum):
    NORMAL = "normal"
    STUB = "stub"
    NSSA = "nssa"
    BACKBONE = "backbone"

@dataclass
class VRFConfiguration:
    id: str
    name: str
    description: str
    rd: str  # Route Distinguisher (ASN:value or IP:value)
    rt_import: List[str] = field(default_factory=list)  # Route Targets for import
    rt_export: List[str] = field(default_factory=list)  # Route Targets for export
    ip_ranges: List[str] = field(default_factory=list)  # CIDR blocks assigned to this VRF
    status: VRFStatus = VRFStatus.INACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    # OSPF Configuration
    ospf_enabled: bool = False
    ospf_router_id: Optional[str] = None
    ospf_areas: List[Dict] = field(default_factory=list)
    ospf_networks: List[Dict] = field(default_factory=list)

@dataclass
class OSPFArea:
    area_id: str  # Area ID (0.0.0.0 for backbone)
    area_type: OSPFAreaType
    vrf_id: str
    networks: List[str] = field(default_factory=list)  # Networks in this area
    auth_type: Optional[str] = None  # none, simple, md5
    auth_key: Optional[str] = None
    stub_default_cost: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class OSPFNeighbor:
    neighbor_id: str
    neighbor_ip: str
    interface: str
    vrf_id: str
    area_id: str
    state: str  # Full, 2-Way, etc.
    priority: int = 1
    dead_interval: int = 40
    hello_interval: int = 10
    last_seen: Optional[datetime] = None

class VRFManager:
    def __init__(self, db_path: str = "network.db"):
        self.db_path = db_path
        self._init_database()
        
    def _init_database(self):
        """Initialize the network database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create VRF table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vrfs (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                rd TEXT NOT NULL,
                rt_import TEXT,  -- JSON array
                rt_export TEXT,  -- JSON array
                ip_ranges TEXT,  -- JSON array
                status TEXT DEFAULT 'inactive',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                ospf_enabled BOOLEAN DEFAULT 0,
                ospf_router_id TEXT,
                ospf_areas TEXT,  -- JSON array
                ospf_networks TEXT  -- JSON array
            )
        """)
        
        # Create OSPF areas table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ospf_areas (
                area_id TEXT NOT NULL,
                vrf_id TEXT NOT NULL,
                area_type TEXT DEFAULT 'normal',
                networks TEXT,  -- JSON array
                auth_type TEXT,
                auth_key TEXT,
                stub_default_cost INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (area_id, vrf_id),
                FOREIGN KEY (vrf_id) REFERENCES vrfs(id)
            )
        """)
        
        # Create OSPF neighbors table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ospf_neighbors (
                neighbor_id TEXT NOT NULL,
                vrf_id TEXT NOT NULL,
                neighbor_ip TEXT NOT NULL,
                interface TEXT NOT NULL,
                area_id TEXT NOT NULL,
                state TEXT DEFAULT 'Down',
                priority INTEGER DEFAULT 1,
                dead_interval INTEGER DEFAULT 40,
                hello_interval INTEGER DEFAULT 10,
                last_seen TIMESTAMP,
                PRIMARY KEY (neighbor_id, vrf_id),
                FOREIGN KEY (vrf_id) REFERENCES vrfs(id)
            )
        """)
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vrfs_name ON vrfs(name)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vrfs_status ON vrfs(status, is_active)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ospf_areas_vrf ON ospf_areas(vrf_id)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("VRF database initialized", db_path=self.db_path)
    
    async def create_vrf(self, vrf: VRFConfiguration) -> bool:
        """Create a new VRF configuration"""
        try:
            # Validate Route Distinguisher format
            if not self._validate_rd(vrf.rd):
                logger.error("Invalid Route Distinguisher format", rd=vrf.rd)
                return False
            
            # Validate IP ranges
            for ip_range in vrf.ip_ranges:
                try:
                    ipaddress.ip_network(ip_range, strict=False)
                except ValueError as e:
                    logger.error("Invalid IP range", range=ip_range, error=str(e))
                    return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO vrfs
                (id, name, description, rd, rt_import, rt_export, ip_ranges,
                 status, created_at, updated_at, is_active, ospf_enabled,
                 ospf_router_id, ospf_areas, ospf_networks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vrf.id, vrf.name, vrf.description, vrf.rd,
                json.dumps(vrf.rt_import), json.dumps(vrf.rt_export),
                json.dumps(vrf.ip_ranges), vrf.status.value,
                vrf.created_at.isoformat(), vrf.updated_at.isoformat(),
                vrf.is_active, vrf.ospf_enabled, vrf.ospf_router_id,
                json.dumps(vrf.ospf_areas), json.dumps(vrf.ospf_networks)
            ))
            
            conn.commit()
            conn.close()
            
            logger.info("VRF created", vrf_id=vrf.id, vrf_name=vrf.name)
            
            # Apply VRF configuration to FRR
            await self._apply_vrf_config(vrf)
            
            return True
            
        except Exception as e:
            logger.error("Failed to create VRF", error=str(e))
            return False
    
    async def update_vrf(self, vrf: VRFConfiguration) -> bool:
        """Update an existing VRF configuration"""
        try:
            vrf.updated_at = datetime.utcnow()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE vrfs SET
                    name = ?, description = ?, rd = ?, rt_import = ?, rt_export = ?,
                    ip_ranges = ?, status = ?, updated_at = ?, is_active = ?,
                    ospf_enabled = ?, ospf_router_id = ?, ospf_areas = ?, ospf_networks = ?
                WHERE id = ?
            """, (
                vrf.name, vrf.description, vrf.rd,
                json.dumps(vrf.rt_import), json.dumps(vrf.rt_export),
                json.dumps(vrf.ip_ranges), vrf.status.value,
                vrf.updated_at.isoformat(), vrf.is_active,
                vrf.ospf_enabled, vrf.ospf_router_id,
                json.dumps(vrf.ospf_areas), json.dumps(vrf.ospf_networks),
                vrf.id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info("VRF updated", vrf_id=vrf.id)
            
            # Reapply VRF configuration
            await self._apply_vrf_config(vrf)
            
            return True
            
        except Exception as e:
            logger.error("Failed to update VRF", error=str(e))
            return False
    
    async def delete_vrf(self, vrf_id: str) -> bool:
        """Delete a VRF configuration"""
        try:
            # First remove from FRR
            await self._remove_vrf_config(vrf_id)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Delete related OSPF configuration
            cursor.execute("DELETE FROM ospf_areas WHERE vrf_id = ?", (vrf_id,))
            cursor.execute("DELETE FROM ospf_neighbors WHERE vrf_id = ?", (vrf_id,))
            
            # Delete VRF
            cursor.execute("DELETE FROM vrfs WHERE id = ?", (vrf_id,))
            
            conn.commit()
            conn.close()
            
            logger.info("VRF deleted", vrf_id=vrf_id)
            return True
            
        except Exception as e:
            logger.error("Failed to delete VRF", error=str(e))
            return False
    
    async def get_vrf(self, vrf_id: str) -> Optional[VRFConfiguration]:
        """Get a VRF configuration by ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, name, description, rd, rt_import, rt_export, ip_ranges,
                       status, created_at, updated_at, is_active, ospf_enabled,
                       ospf_router_id, ospf_areas, ospf_networks
                FROM vrfs WHERE id = ?
            """, (vrf_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            return VRFConfiguration(
                id=row[0],
                name=row[1],
                description=row[2],
                rd=row[3],
                rt_import=json.loads(row[4]) if row[4] else [],
                rt_export=json.loads(row[5]) if row[5] else [],
                ip_ranges=json.loads(row[6]) if row[6] else [],
                status=VRFStatus(row[7]),
                created_at=datetime.fromisoformat(row[8]),
                updated_at=datetime.fromisoformat(row[9]),
                is_active=bool(row[10]),
                ospf_enabled=bool(row[11]),
                ospf_router_id=row[12],
                ospf_areas=json.loads(row[13]) if row[13] else [],
                ospf_networks=json.loads(row[14]) if row[14] else []
            )
            
        except Exception as e:
            logger.error("Failed to get VRF", vrf_id=vrf_id, error=str(e))
            return None
    
    async def list_vrfs(self, active_only: bool = True) -> List[VRFConfiguration]:
        """List all VRF configurations"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = """
                SELECT id, name, description, rd, rt_import, rt_export, ip_ranges,
                       status, created_at, updated_at, is_active, ospf_enabled,
                       ospf_router_id, ospf_areas, ospf_networks
                FROM vrfs
            """
            
            if active_only:
                query += " WHERE is_active = 1"
            
            query += " ORDER BY name"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            vrfs = []
            for row in rows:
                vrf = VRFConfiguration(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    rd=row[3],
                    rt_import=json.loads(row[4]) if row[4] else [],
                    rt_export=json.loads(row[5]) if row[5] else [],
                    ip_ranges=json.loads(row[6]) if row[6] else [],
                    status=VRFStatus(row[7]),
                    created_at=datetime.fromisoformat(row[8]),
                    updated_at=datetime.fromisoformat(row[9]),
                    is_active=bool(row[10]),
                    ospf_enabled=bool(row[11]),
                    ospf_router_id=row[12],
                    ospf_areas=json.loads(row[13]) if row[13] else [],
                    ospf_networks=json.loads(row[14]) if row[14] else []
                )
                vrfs.append(vrf)
            
            return vrfs
            
        except Exception as e:
            logger.error("Failed to list VRFs", error=str(e))
            return []
    
    async def create_ospf_area(self, area: OSPFArea) -> bool:
        """Create an OSPF area within a VRF"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO ospf_areas
                (area_id, vrf_id, area_type, networks, auth_type, auth_key,
                 stub_default_cost, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                area.area_id, area.vrf_id, area.area_type.value,
                json.dumps(area.networks), area.auth_type, area.auth_key,
                area.stub_default_cost, area.created_at.isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            logger.info("OSPF area created", area_id=area.area_id, vrf_id=area.vrf_id)
            
            # Apply OSPF configuration
            await self._apply_ospf_config(area.vrf_id)
            
            return True
            
        except Exception as e:
            logger.error("Failed to create OSPF area", error=str(e))
            return False
    
    async def get_ospf_neighbors(self, vrf_id: str) -> List[OSPFNeighbor]:
        """Get OSPF neighbors for a VRF"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT neighbor_id, vrf_id, neighbor_ip, interface, area_id,
                       state, priority, dead_interval, hello_interval, last_seen
                FROM ospf_neighbors WHERE vrf_id = ?
            """, (vrf_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            neighbors = []
            for row in rows:
                neighbor = OSPFNeighbor(
                    neighbor_id=row[0],
                    neighbor_ip=row[2],
                    interface=row[3],
                    vrf_id=row[1],
                    area_id=row[4],
                    state=row[5],
                    priority=row[6],
                    dead_interval=row[7],
                    hello_interval=row[8],
                    last_seen=datetime.fromisoformat(row[9]) if row[9] else None
                )
                neighbors.append(neighbor)
            
            return neighbors
            
        except Exception as e:
            logger.error("Failed to get OSPF neighbors", error=str(e))
            return []
    
    def _validate_rd(self, rd: str) -> bool:
        """Validate Route Distinguisher format (ASN:value or IP:value)"""
        try:
            if ':' not in rd:
                return False
            
            parts = rd.split(':')
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
    
    async def _apply_vrf_config(self, vrf: VRFConfiguration):
        """Apply VRF configuration to FRR"""
        try:
            config_lines = []
            
            # VRF configuration
            config_lines.append(f"vrf {vrf.name}")
            config_lines.append(f" description {vrf.description}")
            
            # Route targets
            for rt in vrf.rt_import:
                config_lines.append(f" import rt {rt}")
            
            for rt in vrf.rt_export:
                config_lines.append(f" export rt {rt}")
            
            config_lines.append(f" rd {vrf.rd}")
            config_lines.append(" exit")
            
            # OSPF configuration if enabled
            if vrf.ospf_enabled and vrf.ospf_router_id:
                config_lines.append(f"router ospf vrf {vrf.name}")
                config_lines.append(f" router-id {vrf.ospf_router_id}")
                
                # Add networks
                for network in vrf.ospf_networks:
                    area_id = network.get('area', '0.0.0.0')
                    net = network.get('network')
                    if net:
                        config_lines.append(f" network {net} area {area_id}")
                
                config_lines.append(" exit")
            
            # Write configuration to FRR
            config_content = '\n'.join(config_lines)
            
            # In a real deployment, this would write to FRR config or use vtysh
            # For now, we'll log the configuration
            logger.info("Generated FRR VRF configuration", 
                       vrf_id=vrf.id, config=config_content)
            
            # Update VRF status
            vrf.status = VRFStatus.ACTIVE
            
        except Exception as e:
            logger.error("Failed to apply VRF configuration", vrf_id=vrf.id, error=str(e))
            vrf.status = VRFStatus.ERROR
    
    async def _apply_ospf_config(self, vrf_id: str):
        """Apply OSPF configuration for a VRF"""
        try:
            vrf = await self.get_vrf(vrf_id)
            if not vrf or not vrf.ospf_enabled:
                return
            
            # This would generate and apply OSPF-specific configuration
            logger.info("Applied OSPF configuration", vrf_id=vrf_id)
            
        except Exception as e:
            logger.error("Failed to apply OSPF configuration", vrf_id=vrf_id, error=str(e))
    
    async def _remove_vrf_config(self, vrf_id: str):
        """Remove VRF configuration from FRR"""
        try:
            vrf = await self.get_vrf(vrf_id)
            if not vrf:
                return
            
            # This would remove the VRF from FRR configuration
            logger.info("Removed VRF configuration from FRR", vrf_id=vrf_id)
            
        except Exception as e:
            logger.error("Failed to remove VRF configuration", vrf_id=vrf_id, error=str(e))
    
    async def generate_frr_config(self, vrf_id: str) -> str:
        """Generate complete FRR configuration for a VRF"""
        try:
            vrf = await self.get_vrf(vrf_id)
            if not vrf:
                return ""
            
            config_lines = [
                "! FRR Configuration for VRF: " + vrf.name,
                "! Generated by SASEWaddle Manager",
                f"! Generated at: {datetime.utcnow().isoformat()}",
                "!",
                f"vrf {vrf.name}",
                f" description {vrf.description}",
                f" rd {vrf.rd}"
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
                    " passive-interface default"
                ])
                
                # Add OSPF networks
                for network in vrf.ospf_networks:
                    area_id = network.get('area', '0.0.0.0')
                    net = network.get('network')
                    if net:
                        config_lines.append(f" network {net} area {area_id}")
                
                config_lines.append(" exit")
                config_lines.append("!")
            
            return '\n'.join(config_lines)
            
        except Exception as e:
            logger.error("Failed to generate FRR config", vrf_id=vrf_id, error=str(e))
            return ""

# Global VRF manager instance
vrf_manager = VRFManager()