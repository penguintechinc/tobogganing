"""Port configuration management for headend servers."""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PortProtocol(Enum):
    """Supported protocols for port listening."""
    TCP = "tcp"
    UDP = "udp"


@dataclass
class PortRange:
    """Represents a range of ports for listening."""
    id: Optional[str] = None
    start_port: int = 0
    end_port: int = 0
    protocol: PortProtocol = PortProtocol.TCP
    description: str = ""
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'start_port': self.start_port,
            'end_port': self.end_port,
            'protocol': self.protocol.value,
            'description': self.description,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'PortRange':
        """Create PortRange from dictionary."""
        return cls(
            id=data.get('id'),
            start_port=data.get('start_port', 0),
            end_port=data.get('end_port', 0),
            protocol=PortProtocol(data.get('protocol', 'tcp')),
            description=data.get('description', ''),
            enabled=data.get('enabled', True),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None,
        )


@dataclass
class HeadendPortConfig:
    """Port configuration for a specific headend server."""
    headend_id: str
    cluster_id: str
    tcp_ranges: List[PortRange] = field(default_factory=list)
    udp_ranges: List[PortRange] = field(default_factory=list)
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'headend_id': self.headend_id,
            'cluster_id': self.cluster_id,
            'tcp_ranges': [pr.to_dict() for pr in self.tcp_ranges],
            'udp_ranges': [pr.to_dict() for pr in self.udp_ranges],
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_tcp_range_string(self) -> str:
        """Get TCP ranges as a comma-separated string (e.g., '8000-8100,9000,9500-9600')."""
        ranges = []
        for pr in self.tcp_ranges:
            if not pr.enabled:
                continue
            if pr.start_port == pr.end_port:
                ranges.append(str(pr.start_port))
            else:
                ranges.append(f"{pr.start_port}-{pr.end_port}")
        return ",".join(ranges)

    def get_udp_range_string(self) -> str:
        """Get UDP ranges as a comma-separated string (e.g., '8000-8100,9000,9500-9600')."""
        ranges = []
        for pr in self.udp_ranges:
            if not pr.enabled:
                continue
            if pr.start_port == pr.end_port:
                ranges.append(str(pr.start_port))
            else:
                ranges.append(f"{pr.start_port}-{pr.end_port}")
        return ",".join(ranges)


class PortConfigManager:
    """Manages port configurations for headend servers."""

    def __init__(self, db_path: str = "data/sasewaddle.db"):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create necessary database tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS port_ranges (
                    id TEXT PRIMARY KEY,
                    headend_id TEXT NOT NULL,
                    cluster_id TEXT NOT NULL,
                    start_port INTEGER NOT NULL,
                    end_port INTEGER NOT NULL,
                    protocol TEXT NOT NULL,
                    description TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_port_ranges_headend 
                ON port_ranges(headend_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_port_ranges_cluster 
                ON port_ranges(cluster_id)
            """)

    async def get_headend_config(self, headend_id: str) -> Optional[HeadendPortConfig]:
        """Get port configuration for a specific headend."""
        loop = asyncio.get_event_loop()
        
        def _get_config():
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM port_ranges 
                    WHERE headend_id = ? AND enabled = 1
                    ORDER BY protocol, start_port
                """, (headend_id,))
                
                rows = cursor.fetchall()
                if not rows:
                    return None
                
                tcp_ranges = []
                udp_ranges = []
                cluster_id = rows[0]['cluster_id']
                
                for row in rows:
                    port_range = PortRange(
                        id=row['id'],
                        start_port=row['start_port'],
                        end_port=row['end_port'],
                        protocol=PortProtocol(row['protocol']),
                        description=row['description'] or '',
                        enabled=bool(row['enabled']),
                        created_at=datetime.fromisoformat(row['created_at']),
                        updated_at=datetime.fromisoformat(row['updated_at']),
                    )
                    
                    if port_range.protocol == PortProtocol.TCP:
                        tcp_ranges.append(port_range)
                    else:
                        udp_ranges.append(port_range)
                
                return HeadendPortConfig(
                    headend_id=headend_id,
                    cluster_id=cluster_id,
                    tcp_ranges=tcp_ranges,
                    udp_ranges=udp_ranges,
                )
        
        return await loop.run_in_executor(None, _get_config)

    async def get_cluster_config(self, cluster_id: str) -> Dict[str, HeadendPortConfig]:
        """Get port configurations for all headends in a cluster."""
        loop = asyncio.get_event_loop()
        
        def _get_configs():
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT DISTINCT headend_id FROM port_ranges 
                    WHERE cluster_id = ? AND enabled = 1
                """, (cluster_id,))
                
                headend_ids = [row['headend_id'] for row in cursor.fetchall()]
                return headend_ids
        
        headend_ids = await loop.run_in_executor(None, _get_configs)
        configs = {}
        
        for headend_id in headend_ids:
            config = await self.get_headend_config(headend_id)
            if config:
                configs[headend_id] = config
        
        return configs

    async def add_port_range(self, headend_id: str, cluster_id: str, port_range: PortRange) -> str:
        """Add a new port range configuration."""
        import uuid
        
        port_range.id = str(uuid.uuid4())
        port_range.created_at = datetime.utcnow()
        port_range.updated_at = datetime.utcnow()
        
        # Validate port range
        if port_range.start_port < 1 or port_range.end_port > 65535:
            raise ValueError("Port numbers must be between 1 and 65535")
        
        if port_range.start_port > port_range.end_port:
            raise ValueError("Start port must be less than or equal to end port")
        
        # Check for overlaps
        if await self._has_port_overlap(headend_id, port_range):
            raise ValueError(f"Port range {port_range.start_port}-{port_range.end_port} overlaps with existing range")
        
        loop = asyncio.get_event_loop()
        
        def _add_range():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO port_ranges 
                    (id, headend_id, cluster_id, start_port, end_port, protocol, description, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    port_range.id,
                    headend_id,
                    cluster_id,
                    port_range.start_port,
                    port_range.end_port,
                    port_range.protocol.value,
                    port_range.description,
                    port_range.enabled,
                    port_range.created_at.isoformat(),
                    port_range.updated_at.isoformat(),
                ))
        
        await loop.run_in_executor(None, _add_range)
        logger.info(f"Added port range {port_range.start_port}-{port_range.end_port} ({port_range.protocol.value}) for headend {headend_id}")
        
        return port_range.id

    async def remove_port_range(self, range_id: str) -> bool:
        """Remove a port range configuration."""
        loop = asyncio.get_event_loop()
        
        def _remove_range():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM port_ranges WHERE id = ?", (range_id,))
                return cursor.rowcount > 0
        
        success = await loop.run_in_executor(None, _remove_range)
        if success:
            logger.info(f"Removed port range {range_id}")
        
        return success

    async def update_port_range(self, range_id: str, **kwargs) -> bool:
        """Update a port range configuration."""
        valid_fields = {'start_port', 'end_port', 'protocol', 'description', 'enabled'}
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        
        if not updates:
            return False
        
        updates['updated_at'] = datetime.utcnow().isoformat()
        
        # Build UPDATE query
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [range_id]
        
        loop = asyncio.get_event_loop()
        
        def _update_range():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE port_ranges SET {set_clause} WHERE id = ?", values)
                return cursor.rowcount > 0
        
        success = await loop.run_in_executor(None, _update_range)
        if success:
            logger.info(f"Updated port range {range_id}")
        
        return success

    async def _has_port_overlap(self, headend_id: str, new_range: PortRange) -> bool:
        """Check if a new port range overlaps with existing ranges."""
        loop = asyncio.get_event_loop()
        
        def _check_overlap():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM port_ranges 
                    WHERE headend_id = ? AND protocol = ? AND enabled = 1
                    AND (
                        (start_port <= ? AND end_port >= ?) OR
                        (start_port <= ? AND end_port >= ?) OR
                        (start_port >= ? AND end_port <= ?)
                    )
                """, (
                    headend_id,
                    new_range.protocol.value,
                    new_range.start_port, new_range.start_port,
                    new_range.end_port, new_range.end_port,
                    new_range.start_port, new_range.end_port,
                ))
                
                return cursor.fetchone()[0] > 0
        
        return await loop.run_in_executor(None, _check_overlap)

    async def get_all_configs(self) -> Dict[str, HeadendPortConfig]:
        """Get all port configurations for all headends."""
        loop = asyncio.get_event_loop()
        
        def _get_all_headends():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT headend_id FROM port_ranges WHERE enabled = 1")
                return [row[0] for row in cursor.fetchall()]
        
        headend_ids = await loop.run_in_executor(None, _get_all_headends)
        configs = {}
        
        for headend_id in headend_ids:
            config = await self.get_headend_config(headend_id)
            if config:
                configs[headend_id] = config
        
        return configs

    async def set_default_config(self, headend_id: str, cluster_id: str) -> None:
        """Set default port configuration for a headend."""
        # Default proxy ports
        default_ranges = [
            PortRange(start_port=8443, end_port=8443, protocol=PortProtocol.TCP, description="HTTPS Proxy"),
            PortRange(start_port=8444, end_port=8444, protocol=PortProtocol.TCP, description="TCP Proxy"),
            PortRange(start_port=8445, end_port=8445, protocol=PortProtocol.UDP, description="UDP Proxy"),
            # Common application ports
            PortRange(start_port=3000, end_port=3010, protocol=PortProtocol.TCP, description="Development Services"),
            PortRange(start_port=8000, end_port=8010, protocol=PortProtocol.TCP, description="Web Services"),
            PortRange(start_port=9000, end_port=9010, protocol=PortProtocol.TCP, description="Application Services"),
        ]
        
        for port_range in default_ranges:
            try:
                await self.add_port_range(headend_id, cluster_id, port_range)
            except ValueError as e:
                logger.warning(f"Could not add default range {port_range.start_port}-{port_range.end_port}: {e}")


# Global instance
port_config_manager = PortConfigManager()