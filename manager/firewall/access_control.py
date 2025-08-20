"""
Domain and IP access control management for SASEWaddle users
"""

import asyncio
import ipaddress
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Union
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()

class AccessType(Enum):
    ALLOW = "allow"
    DENY = "deny"

class RuleType(Enum):
    DOMAIN = "domain"
    IP = "ip"
    IP_RANGE = "ip_range"
    URL_PATTERN = "url_pattern"
    PROTOCOL_RULE = "protocol_rule"  # For TCP/UDP/ICMP with ports

@dataclass
class AccessRule:
    id: str
    user_id: str
    rule_type: RuleType
    access_type: AccessType
    pattern: str
    priority: int = 100
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    description: Optional[str] = None
    
    # Enhanced protocol-based filtering
    src_ip: Optional[str] = None        # Source IP/CIDR (IPv4/IPv6)
    dst_ip: Optional[str] = None        # Destination IP/CIDR (IPv4/IPv6)
    protocol: Optional[str] = None      # TCP, UDP, ICMP, etc.
    src_port: Optional[str] = None      # Source port or range (80, 80-443, *)
    dst_port: Optional[str] = None      # Destination port or range
    direction: Optional[str] = None     # inbound, outbound, both

class AccessControlManager:
    def __init__(self, db_path: str = "firewall.db"):
        self.db_path = db_path
        self._init_database()
        
    def _init_database(self):
        """Initialize the firewall database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create access rules table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS access_rules (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                access_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                priority INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                description TEXT,
                src_ip TEXT,
                dst_ip TEXT,
                protocol TEXT,
                src_port TEXT,
                dst_port TEXT,
                direction TEXT,
                UNIQUE(user_id, pattern, rule_type, src_ip, dst_ip, protocol, src_port, dst_port)
            )
        """)
        
        # Create index for efficient lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_access_rules_user_id 
            ON access_rules(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_access_rules_active 
            ON access_rules(is_active, priority)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("Access control database initialized", db_path=self.db_path)
    
    async def add_rule(self, rule: AccessRule) -> bool:
        """Add a new access control rule"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO access_rules
                (id, user_id, rule_type, access_type, pattern, priority, 
                 created_at, updated_at, is_active, description, src_ip, dst_ip, 
                 protocol, src_port, dst_port, direction)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule.id, rule.user_id, rule.rule_type.value, rule.access_type.value,
                rule.pattern, rule.priority, rule.created_at.isoformat(),
                rule.updated_at.isoformat(), rule.is_active, rule.description,
                rule.src_ip, rule.dst_ip, rule.protocol, rule.src_port, rule.dst_port, rule.direction
            ))
            
            conn.commit()
            conn.close()
            
            logger.info("Access rule added", 
                       rule_id=rule.id, user_id=rule.user_id, 
                       pattern=rule.pattern, access_type=rule.access_type.value)
            
            return True
            
        except Exception as e:
            logger.error("Failed to add access rule", error=str(e))
            return False
    
    async def remove_rule(self, rule_id: str) -> bool:
        """Remove an access control rule"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM access_rules WHERE id = ?", (rule_id,))
            
            conn.commit()
            conn.close()
            
            logger.info("Access rule removed", rule_id=rule_id)
            return True
            
        except Exception as e:
            logger.error("Failed to remove access rule", error=str(e))
            return False
    
    async def get_user_rules(self, user_id: str) -> List[AccessRule]:
        """Get all active access rules for a user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, user_id, rule_type, access_type, pattern, priority,
                       created_at, updated_at, is_active, description, src_ip, dst_ip,
                       protocol, src_port, dst_port, direction
                FROM access_rules
                WHERE user_id = ? AND is_active = 1
                ORDER BY priority ASC
            """, (user_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            rules = []
            for row in rows:
                rule = AccessRule(
                    id=row[0],
                    user_id=row[1],
                    rule_type=RuleType(row[2]),
                    access_type=AccessType(row[3]),
                    pattern=row[4],
                    priority=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    updated_at=datetime.fromisoformat(row[7]),
                    is_active=bool(row[8]),
                    description=row[9],
                    src_ip=row[10],
                    dst_ip=row[11],
                    protocol=row[12],
                    src_port=row[13],
                    dst_port=row[14],
                    direction=row[15]
                )
                rules.append(rule)
            
            return rules
            
        except Exception as e:
            logger.error("Failed to get user rules", user_id=user_id, error=str(e))
            return []
    
    async def check_access(self, user_id: str, target: str) -> bool:
        """
        Check if user has access to a domain/IP/URL
        
        Args:
            user_id: User ID to check access for
            target: Domain, IP, or URL to check access to
            
        Returns:
            True if access is allowed, False if denied
        """
        rules = await self.get_user_rules(user_id)
        
        if not rules:
            # No rules defined - default to allow
            return True
        
        # Process rules by priority (lower number = higher priority)
        for rule in sorted(rules, key=lambda r: r.priority):
            if self._rule_matches(rule, target):
                return rule.access_type == AccessType.ALLOW
        
        # No matching rule - default to deny
        return False
    
    def _rule_matches(self, rule: AccessRule, target: str) -> bool:
        """Check if a rule matches the target"""
        try:
            if rule.rule_type == RuleType.DOMAIN:
                return self._match_domain(rule.pattern, target)
            elif rule.rule_type == RuleType.IP:
                return self._match_ip(rule.pattern, target)
            elif rule.rule_type == RuleType.IP_RANGE:
                return self._match_ip_range(rule.pattern, target)
            elif rule.rule_type == RuleType.URL_PATTERN:
                return self._match_url_pattern(rule.pattern, target)
            elif rule.rule_type == RuleType.PROTOCOL_RULE:
                return self._match_protocol_rule(rule, target)
        except Exception as e:
            logger.error("Error matching rule", rule_id=rule.id, error=str(e))
            
        return False
    
    def _match_domain(self, pattern: str, target: str) -> bool:
        """Match domain pattern against target"""
        # Extract domain from URL if target is a URL
        if target.startswith(('http://', 'https://')):
            parsed = urlparse(target)
            target_domain = parsed.netloc.lower()
        else:
            target_domain = target.lower()
        
        pattern = pattern.lower()
        
        # Exact match
        if pattern == target_domain:
            return True
        
        # Wildcard subdomain match (*.example.com matches sub.example.com)
        if pattern.startswith('*.'):
            base_domain = pattern[2:]
            if target_domain == base_domain or target_domain.endswith('.' + base_domain):
                return True
        
        return False
    
    def _match_ip(self, pattern: str, target: str) -> bool:
        """Match IP pattern against target"""
        try:
            # Extract IP from URL if target is a URL
            if target.startswith(('http://', 'https://')):
                parsed = urlparse(target)
                target_ip = parsed.netloc.split(':')[0]  # Remove port if present
            else:
                target_ip = target.split(':')[0]  # Remove port if present
            
            target_addr = ipaddress.ip_address(target_ip)
            pattern_addr = ipaddress.ip_address(pattern)
            
            return target_addr == pattern_addr
            
        except ValueError:
            return False
    
    def _match_ip_range(self, pattern: str, target: str) -> bool:
        """Match IP range/CIDR against target"""
        try:
            # Extract IP from URL if target is a URL
            if target.startswith(('http://', 'https://')):
                parsed = urlparse(target)
                target_ip = parsed.netloc.split(':')[0]  # Remove port if present
            else:
                target_ip = target.split(':')[0]  # Remove port if present
            
            target_addr = ipaddress.ip_address(target_ip)
            network = ipaddress.ip_network(pattern, strict=False)
            
            return target_addr in network
            
        except ValueError:
            return False
    
    def _match_url_pattern(self, pattern: str, target: str) -> bool:
        """Match URL pattern against target using regex"""
        try:
            return bool(re.match(pattern, target, re.IGNORECASE))
        except re.error:
            logger.error("Invalid regex pattern", pattern=pattern)
            return False
    
    def _match_protocol_rule(self, rule: AccessRule, target: str) -> bool:
        """
        Match protocol-based rule against target
        Target can be a connection descriptor like 'tcp:192.168.1.1:80->8.8.8.8:53'
        """
        try:
            # Parse target connection string
            conn_info = self._parse_connection_target(target)
            if not conn_info:
                return False
            
            # Check protocol
            if rule.protocol and rule.protocol.lower() != conn_info['protocol'].lower():
                return False
            
            # Check source IP
            if rule.src_ip and not self._match_ip_or_range(rule.src_ip, conn_info['src_ip']):
                return False
            
            # Check destination IP  
            if rule.dst_ip and not self._match_ip_or_range(rule.dst_ip, conn_info['dst_ip']):
                return False
            
            # Check source port
            if rule.src_port and not self._match_port(rule.src_port, conn_info['src_port']):
                return False
            
            # Check destination port
            if rule.dst_port and not self._match_port(rule.dst_port, conn_info['dst_port']):
                return False
            
            # Check direction
            if rule.direction and rule.direction != 'both':
                if rule.direction != conn_info.get('direction', 'outbound'):
                    return False
            
            return True
            
        except Exception as e:
            logger.error("Error matching protocol rule", rule_id=rule.id, error=str(e))
            return False
    
    def _parse_connection_target(self, target: str) -> Optional[Dict]:
        """
        Parse connection target string into components
        Formats supported:
        - 'tcp:192.168.1.1:80->8.8.8.8:53'
        - 'udp:*:*->192.168.1.1:53'
        - 'icmp:192.168.1.1->8.8.8.8'
        - 'protocol:src_ip:src_port->dst_ip:dst_port:direction'
        """
        try:
            # Basic format: protocol:src->dst or protocol:src->dst:direction
            if '->' not in target:
                return None
            
            parts = target.split('->')
            if len(parts) < 2:
                return None
            
            src_part = parts[0]
            dst_part = parts[1]
            
            # Parse protocol and source
            if ':' in src_part:
                src_components = src_part.split(':')
                protocol = src_components[0]
                src_ip = src_components[1] if len(src_components) > 1 else '*'
                src_port = src_components[2] if len(src_components) > 2 else '*'
            else:
                return None
            
            # Parse destination (and optional direction)
            dst_components = dst_part.split(':')
            dst_ip = dst_components[0] if dst_components else '*'
            dst_port = dst_components[1] if len(dst_components) > 1 else '*'
            direction = dst_components[2] if len(dst_components) > 2 else 'outbound'
            
            return {
                'protocol': protocol,
                'src_ip': src_ip,
                'src_port': src_port,
                'dst_ip': dst_ip,
                'dst_port': dst_port,
                'direction': direction
            }
            
        except Exception as e:
            logger.error("Error parsing connection target", target=target, error=str(e))
            return None
    
    def _match_ip_or_range(self, rule_ip: str, target_ip: str) -> bool:
        """Match IP or IP range against target IP"""
        if rule_ip == '*' or target_ip == '*':
            return True
        
        try:
            # Check if rule_ip is a CIDR range
            if '/' in rule_ip:
                network = ipaddress.ip_network(rule_ip, strict=False)
                target_addr = ipaddress.ip_address(target_ip)
                return target_addr in network
            else:
                # Exact IP match
                return ipaddress.ip_address(rule_ip) == ipaddress.ip_address(target_ip)
        except ValueError:
            return False
    
    def _match_port(self, rule_port: str, target_port: str) -> bool:
        """Match port or port range against target port"""
        if rule_port == '*' or target_port == '*':
            return True
        
        try:
            target_port_num = int(target_port)
            
            if '-' in rule_port:
                # Port range (e.g., "80-443")
                start, end = rule_port.split('-', 1)
                return int(start) <= target_port_num <= int(end)
            elif ',' in rule_port:
                # Port list (e.g., "80,443,8080")
                ports = [int(p.strip()) for p in rule_port.split(',')]
                return target_port_num in ports
            else:
                # Single port
                return int(rule_port) == target_port_num
        except ValueError:
            return False
    
    async def get_all_rules(self) -> List[AccessRule]:
        """Get all access rules for management interface"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, user_id, rule_type, access_type, pattern, priority,
                       created_at, updated_at, is_active, description, src_ip, dst_ip,
                       protocol, src_port, dst_port, direction
                FROM access_rules
                ORDER BY user_id, priority ASC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            rules = []
            for row in rows:
                rule = AccessRule(
                    id=row[0],
                    user_id=row[1],
                    rule_type=RuleType(row[2]),
                    access_type=AccessType(row[3]),
                    pattern=row[4],
                    priority=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    updated_at=datetime.fromisoformat(row[7]),
                    is_active=bool(row[8]),
                    description=row[9],
                    src_ip=row[10],
                    dst_ip=row[11],
                    protocol=row[12],
                    src_port=row[13],
                    dst_port=row[14],
                    direction=row[15]
                )
                rules.append(rule)
            
            return rules
            
        except Exception as e:
            logger.error("Failed to get all rules", error=str(e))
            return []
    
    async def update_rule(self, rule: AccessRule) -> bool:
        """Update an existing access control rule"""
        try:
            rule.updated_at = datetime.utcnow()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE access_rules
                SET rule_type = ?, access_type = ?, pattern = ?, priority = ?,
                    updated_at = ?, is_active = ?, description = ?
                WHERE id = ?
            """, (
                rule.rule_type.value, rule.access_type.value, rule.pattern,
                rule.priority, rule.updated_at.isoformat(), rule.is_active,
                rule.description, rule.id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info("Access rule updated", rule_id=rule.id)
            return True
            
        except Exception as e:
            logger.error("Failed to update access rule", error=str(e))
            return False
    
    async def export_user_rules(self, user_id: str) -> Dict:
        """Export user rules for headend consumption"""
        rules = await self.get_user_rules(user_id)
        
        export_data = {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "rules": {
                "allow_domains": [],
                "deny_domains": [],
                "allow_ips": [],
                "deny_ips": [],
                "allow_ip_ranges": [],
                "deny_ip_ranges": [],
                "allow_url_patterns": [],
                "deny_url_patterns": [],
                "allow_protocol_rules": [],
                "deny_protocol_rules": []
            }
        }
        
        for rule in rules:
            key_prefix = "allow_" if rule.access_type == AccessType.ALLOW else "deny_"
            
            if rule.rule_type == RuleType.DOMAIN:
                export_data["rules"][key_prefix + "domains"].append({
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "description": rule.description
                })
            elif rule.rule_type == RuleType.IP:
                export_data["rules"][key_prefix + "ips"].append({
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "description": rule.description
                })
            elif rule.rule_type == RuleType.IP_RANGE:
                export_data["rules"][key_prefix + "ip_ranges"].append({
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "description": rule.description
                })
            elif rule.rule_type == RuleType.URL_PATTERN:
                export_data["rules"][key_prefix + "url_patterns"].append({
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "description": rule.description
                })
            elif rule.rule_type == RuleType.PROTOCOL_RULE:
                export_data["rules"][key_prefix + "protocol_rules"].append({
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "description": rule.description,
                    "src_ip": rule.src_ip,
                    "dst_ip": rule.dst_ip,
                    "protocol": rule.protocol,
                    "src_port": rule.src_port,
                    "dst_port": rule.dst_port,
                    "direction": rule.direction
                })
        
        return export_data

# Global access control manager instance
access_control_manager = AccessControlManager()