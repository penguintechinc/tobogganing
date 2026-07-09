"""Domain and IP access control management using penguin-dal."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


class AccessType(Enum):
    """Access permission type."""

    ALLOW = "allow"
    DENY = "deny"


class RuleType(Enum):
    """Rule matching type."""

    DOMAIN = "domain"
    IP = "ip"
    IP_RANGE = "ip_range"
    URL_PATTERN = "url_pattern"
    PROTOCOL_RULE = "protocol_rule"


@dataclass(slots=True)
class AccessRule:
    """Access control rule data structure."""

    id: str
    tenant: str
    user_id: str
    rule_type: RuleType
    access_type: AccessType
    pattern: str
    priority: int = 100
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    description: str | None = None
    src_ip: str | None = None
    dst_ip: str | None = None
    protocol: str | None = None
    src_port: str | None = None
    dst_port: str | None = None
    direction: str | None = None


class AccessControlManager:
    """Manages firewall access control rules via penguin-dal."""

    def __init__(self, db: Any) -> None:
        """Initialize access control manager with a DAL instance.

        Args:
            db: penguin-dal DAL instance for database operations.
        """
        self.db = db

    async def add_rule(self, rule: AccessRule) -> bool:
        """Add a new access control rule.

        Args:
            rule: AccessRule to add.

        Returns:
            True if rule added successfully, False otherwise.
        """
        try:
            await self.db.firewall_rules.async_insert(
                id=rule.id,
                tenant=rule.tenant,
                user_id=rule.user_id,
                rule_type=rule.rule_type.value,
                access_type=rule.access_type.value,
                pattern=rule.pattern,
                priority=rule.priority,
                created_at=rule.created_at,
                updated_at=rule.updated_at,
                is_active=rule.is_active,
                description=rule.description,
                src_ip=rule.src_ip,
                dst_ip=rule.dst_ip,
                protocol=rule.protocol,
                src_port=rule.src_port,
                dst_port=rule.dst_port,
                direction=rule.direction,
            )

            logger.info(
                "access_rule_added",
                rule_id=rule.id,
                tenant=rule.tenant,
                user_id=rule.user_id,
                pattern=rule.pattern,
                access_type=rule.access_type.value,
            )
            return True

        except Exception as e:
            logger.error("failed_to_add_access_rule", error=str(e))
            return False

    async def remove_rule(self, rule_id: str, tenant: str) -> bool:
        """Remove an access control rule.

        Args:
            rule_id: ID of rule to remove.
            tenant: Tenant ID for scoping.

        Returns:
            True if rule removed successfully, False otherwise.
        """
        try:
            await self.db(
                self.db.firewall_rules.id == rule_id,
                self.db.firewall_rules.tenant == tenant,
            ).delete()

            logger.info("access_rule_removed", rule_id=rule_id, tenant=tenant)
            return True

        except Exception as e:
            logger.error("failed_to_remove_access_rule", error=str(e))
            return False

    async def get_user_rules(self, user_id: str, tenant: str) -> list[AccessRule]:
        """Get all active access rules for a user.

        Args:
            user_id: User ID to retrieve rules for.
            tenant: Tenant ID for scoping.

        Returns:
            List of AccessRule objects sorted by priority.
        """
        try:
            rowset = await self.db(
                self.db.firewall_rules.user_id == user_id,
                self.db.firewall_rules.tenant == tenant,
                self.db.firewall_rules.is_active == True,  # noqa: E712
            ).select(orderby=self.db.firewall_rules.priority)

            rules: list[AccessRule] = []
            for row in rowset:
                rule = AccessRule(
                    id=row.id,
                    tenant=row.tenant,
                    user_id=row.user_id,
                    rule_type=RuleType(row.rule_type),
                    access_type=AccessType(row.access_type),
                    pattern=row.pattern,
                    priority=row.priority,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    is_active=row.is_active,
                    description=row.description,
                    src_ip=row.src_ip,
                    dst_ip=row.dst_ip,
                    protocol=row.protocol,
                    src_port=row.src_port,
                    dst_port=row.dst_port,
                    direction=row.direction,
                )
                rules.append(rule)

            return rules

        except Exception as e:
            logger.error("failed_to_get_user_rules", user_id=user_id, tenant=tenant, error=str(e))
            return []

    async def check_access(self, user_id: str, tenant: str, target: str) -> bool:
        """Check if user has access to a domain/IP/URL.

        Args:
            user_id: User ID to check access for.
            tenant: Tenant ID for scoping.
            target: Domain, IP, or URL to check access to.

        Returns:
            True if access is allowed, False if denied.
        """
        rules = await self.get_user_rules(user_id, tenant)

        if not rules:
            # No rules defined - default to allow
            return True

        # Process rules by priority (lower number = higher priority)
        for rule in sorted(rules, key=lambda r: r.priority):
            if self._rule_matches(rule, target):
                return rule.access_type == AccessType.ALLOW

        # No matching rule - default to deny
        return False

    async def get_all_rules(self, tenant: str) -> list[AccessRule]:
        """Get all access rules for management interface.

        Args:
            tenant: Tenant ID for scoping.

        Returns:
            List of all AccessRule objects in tenant.
        """
        try:
            rowset = await self.db(
                self.db.firewall_rules.tenant == tenant,
            ).select(orderby=[self.db.firewall_rules.user_id, self.db.firewall_rules.priority])

            rules: list[AccessRule] = []
            for row in rowset:
                rule = AccessRule(
                    id=row.id,
                    tenant=row.tenant,
                    user_id=row.user_id,
                    rule_type=RuleType(row.rule_type),
                    access_type=AccessType(row.access_type),
                    pattern=row.pattern,
                    priority=row.priority,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    is_active=row.is_active,
                    description=row.description,
                    src_ip=row.src_ip,
                    dst_ip=row.dst_ip,
                    protocol=row.protocol,
                    src_port=row.src_port,
                    dst_port=row.dst_port,
                    direction=row.direction,
                )
                rules.append(rule)

            return rules

        except Exception as e:
            logger.error("failed_to_get_all_rules", tenant=tenant, error=str(e))
            return []

    async def update_rule(self, rule: AccessRule) -> bool:
        """Update an existing access control rule.

        Args:
            rule: AccessRule with updated values.

        Returns:
            True if rule updated successfully, False otherwise.
        """
        try:
            rule.updated_at = datetime.utcnow()

            await self.db(
                self.db.firewall_rules.id == rule.id,
                self.db.firewall_rules.tenant == rule.tenant,
            ).update(
                rule_type=rule.rule_type.value,
                access_type=rule.access_type.value,
                pattern=rule.pattern,
                priority=rule.priority,
                updated_at=rule.updated_at,
                is_active=rule.is_active,
                description=rule.description,
            )

            logger.info("access_rule_updated", rule_id=rule.id, tenant=rule.tenant)
            return True

        except Exception as e:
            logger.error("failed_to_update_access_rule", rule_id=rule.id, error=str(e))
            return False

    async def export_user_rules(self, user_id: str, tenant: str) -> dict[str, Any]:
        """Export user rules for headend consumption.

        Args:
            user_id: User ID to export rules for.
            tenant: Tenant ID for scoping.

        Returns:
            Dictionary with user_id, timestamp, and categorized rules.
        """
        rules = await self.get_user_rules(user_id, tenant)

        export_data: dict[str, Any] = {
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
                "deny_protocol_rules": [],
            },
        }

        for rule in rules:
            key_prefix = "allow_" if rule.access_type == AccessType.ALLOW else "deny_"

            rule_data = {
                "pattern": rule.pattern,
                "priority": rule.priority,
                "description": rule.description,
            }

            if rule.rule_type == RuleType.DOMAIN:
                export_data["rules"][key_prefix + "domains"].append(rule_data)
            elif rule.rule_type == RuleType.IP:
                export_data["rules"][key_prefix + "ips"].append(rule_data)
            elif rule.rule_type == RuleType.IP_RANGE:
                export_data["rules"][key_prefix + "ip_ranges"].append(rule_data)
            elif rule.rule_type == RuleType.URL_PATTERN:
                export_data["rules"][key_prefix + "url_patterns"].append(rule_data)
            elif rule.rule_type == RuleType.PROTOCOL_RULE:
                protocol_data = rule_data.copy()
                protocol_data.update(
                    {
                        "src_ip": rule.src_ip,
                        "dst_ip": rule.dst_ip,
                        "protocol": rule.protocol,
                        "src_port": rule.src_port,
                        "dst_port": rule.dst_port,
                        "direction": rule.direction,
                    }
                )
                export_data["rules"][key_prefix + "protocol_rules"].append(protocol_data)

        return export_data

    def _rule_matches(self, rule: AccessRule, target: str) -> bool:
        """Check if a rule matches the target.

        Args:
            rule: AccessRule to match.
            target: Target to match against.

        Returns:
            True if rule matches target, False otherwise.
        """
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
            logger.error("error_matching_rule", rule_id=rule.id, error=str(e))

        return False

    @staticmethod
    def _match_domain(pattern: str, target: str) -> bool:
        """Match domain pattern against target.

        Args:
            pattern: Domain pattern (supports wildcards *.example.com).
            target: Target domain or URL.

        Returns:
            True if pattern matches target, False otherwise.
        """
        # Extract domain from URL if target is a URL
        if target.startswith(("http://", "https://")):
            parsed = urlparse(target)
            # Strip port from netloc
            target_domain = parsed.netloc.split(":")[0].lower()
        else:
            target_domain = target.lower()

        pattern = pattern.lower()

        # Exact match
        if pattern == target_domain:
            return True

        # Wildcard subdomain match (*.example.com matches sub.example.com only, not example.com)
        if pattern.startswith("*."):
            base_domain = pattern[2:]
            if target_domain.endswith("." + base_domain):
                return True

        return False

    @staticmethod
    def _match_ip(pattern: str, target: str) -> bool:
        """Match IP pattern against target.

        Args:
            pattern: IP address.
            target: Target IP or URL.

        Returns:
            True if pattern matches target, False otherwise.
        """
        try:
            # Extract IP from URL if target is a URL
            if target.startswith(("http://", "https://")):
                parsed = urlparse(target)
                target_ip = parsed.netloc.split(":")[0]  # Remove port if present
            else:
                target_ip = target.split(":")[0]  # Remove port if present

            target_addr = ipaddress.ip_address(target_ip)
            pattern_addr = ipaddress.ip_address(pattern)

            return target_addr == pattern_addr

        except ValueError:
            return False

    @staticmethod
    def _match_ip_range(pattern: str, target: str) -> bool:
        """Match IP range/CIDR against target.

        Args:
            pattern: IP range in CIDR notation.
            target: Target IP or URL.

        Returns:
            True if pattern matches target, False otherwise.
        """
        try:
            # Extract IP from URL if target is a URL
            if target.startswith(("http://", "https://")):
                parsed = urlparse(target)
                target_ip = parsed.netloc.split(":")[0]  # Remove port if present
            else:
                target_ip = target.split(":")[0]  # Remove port if present

            target_addr = ipaddress.ip_address(target_ip)
            network = ipaddress.ip_network(pattern, strict=False)

            return target_addr in network

        except ValueError:
            return False

    @staticmethod
    def _match_url_pattern(pattern: str, target: str) -> bool:
        """Match URL pattern against target using regex.

        Args:
            pattern: Regex pattern.
            target: Target URL.

        Returns:
            True if pattern matches target, False otherwise.
        """
        try:
            return bool(re.match(pattern, target, re.IGNORECASE))
        except re.error:
            logger.error("invalid_regex_pattern", pattern=pattern)
            return False

    def _match_protocol_rule(self, rule: AccessRule, target: str) -> bool:
        """Match protocol-based rule against target.

        Target can be a connection descriptor like 'tcp:192.168.1.1:80->8.8.8.8:53'

        Args:
            rule: AccessRule with protocol info.
            target: Connection descriptor.

        Returns:
            True if rule matches target, False otherwise.
        """
        try:
            # Parse target connection string
            conn_info = self._parse_connection_target(target)
            if not conn_info:
                return False

            # Check protocol
            if rule.protocol and rule.protocol.lower() != conn_info["protocol"].lower():
                return False

            # Check source IP
            if rule.src_ip and not self._match_ip_or_range(rule.src_ip, conn_info["src_ip"]):
                return False

            # Check destination IP
            if rule.dst_ip and not self._match_ip_or_range(rule.dst_ip, conn_info["dst_ip"]):
                return False

            # Check source port
            if rule.src_port and not self._match_port(rule.src_port, conn_info["src_port"]):
                return False

            # Check destination port
            if rule.dst_port and not self._match_port(rule.dst_port, conn_info["dst_port"]):
                return False

            # Check direction
            if rule.direction and rule.direction != "both":
                if rule.direction != conn_info.get("direction", "outbound"):
                    return False

            return True

        except Exception as e:
            logger.error("error_matching_protocol_rule", rule_id=rule.id, error=str(e))
            return False

    @staticmethod
    def _parse_connection_target(target: str) -> dict[str, str] | None:
        """Parse connection target string into components.

        Formats supported:
        - 'tcp:192.168.1.1:80->8.8.8.8:53'
        - 'udp:*:*->192.168.1.1:53'
        - 'icmp:192.168.1.1->8.8.8.8'
        - 'protocol:src_ip:src_port->dst_ip:dst_port:direction'

        Args:
            target: Connection descriptor string.

        Returns:
            Dict with protocol, src_ip, src_port, dst_ip, dst_port, direction; None if parse fails.
        """
        try:
            # Basic format: protocol:src->dst or protocol:src->dst:direction
            if "->" not in target:
                return None

            parts = target.split("->")
            if len(parts) < 2:
                return None

            src_part = parts[0]
            dst_part = parts[1]

            # Parse protocol and source
            if ":" in src_part:
                src_components = src_part.split(":")
                protocol = src_components[0]
                src_ip = src_components[1] if len(src_components) > 1 else "*"
                src_port = src_components[2] if len(src_components) > 2 else "*"
            else:
                return None

            # Parse destination (and optional direction)
            dst_components = dst_part.split(":")
            dst_ip = dst_components[0] if dst_components else "*"
            dst_port = dst_components[1] if len(dst_components) > 1 else "*"
            direction = dst_components[2] if len(dst_components) > 2 else "outbound"

            return {
                "protocol": protocol,
                "src_ip": src_ip,
                "src_port": src_port,
                "dst_ip": dst_ip,
                "dst_port": dst_port,
                "direction": direction,
            }

        except Exception as e:
            logger.error("error_parsing_connection_target", target=target, error=str(e))
            return None

    @staticmethod
    def _match_ip_or_range(rule_ip: str, target_ip: str) -> bool:
        """Match IP or IP range against target IP.

        Args:
            rule_ip: IP or CIDR from rule.
            target_ip: Target IP.

        Returns:
            True if rule_ip matches target_ip, False otherwise.
        """
        if rule_ip == "*" or target_ip == "*":
            return True

        try:
            # Check if rule_ip is a CIDR range
            if "/" in rule_ip:
                network = ipaddress.ip_network(rule_ip, strict=False)
                target_addr = ipaddress.ip_address(target_ip)
                return target_addr in network
            else:
                # Exact IP match
                return ipaddress.ip_address(rule_ip) == ipaddress.ip_address(target_ip)
        except ValueError:
            return False

    @staticmethod
    def _match_port(rule_port: str, target_port: str) -> bool:
        """Match port or port range against target port.

        Args:
            rule_port: Port or port range from rule.
            target_port: Target port.

        Returns:
            True if rule_port matches target_port, False otherwise.
        """
        if rule_port == "*" or target_port == "*":
            return True

        try:
            target_port_num = int(target_port)

            if "-" in rule_port:
                # Port range (e.g., "80-443")
                start, end = rule_port.split("-", 1)
                return int(start) <= target_port_num <= int(end)
            elif "," in rule_port:
                # Port list (e.g., "80,443,8080")
                ports = [int(p.strip()) for p in rule_port.split(",")]
                return target_port_num in ports
            else:
                # Single port
                return int(rule_port) == target_port_num
        except ValueError:
            return False
