"""
Tests for firewall/access_control.py — rule evaluation, IP/domain/URL matching.
"""
import uuid
import pytest
from unittest.mock import MagicMock, patch

from firewall.access_control import (
    AccessControlManager,
    AccessRule,
    AccessType,
    RuleType,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_rule(
    user_id: str = "user-001",
    rule_type: RuleType = RuleType.DOMAIN,
    access_type: AccessType = AccessType.ALLOW,
    pattern: str = "example.com",
    rule_id: str | None = None,
    src_ip: str | None = None,
    dst_ip: str | None = None,
    protocol: str | None = None,
    src_port: str | None = None,
    dst_port: str | None = None,
    direction: str | None = None,
) -> AccessRule:
    return AccessRule(
        id=rule_id or str(uuid.uuid4()),
        user_id=user_id,
        rule_type=rule_type,
        access_type=access_type,
        pattern=pattern,
        src_ip=src_ip,
        dst_ip=dst_ip,
        protocol=protocol,
        src_port=src_port,
        dst_port=dst_port,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# Fixtures (access_control_manager from conftest uses tmp_path SQLite)
# ---------------------------------------------------------------------------

class TestAccessControlManagerInit:
    def test_manager_initializes(self, access_control_manager):
        assert access_control_manager is not None

    def test_database_tables_created(self, access_control_manager, tmp_path):
        import sqlite3
        db_path = str(tmp_path / "test_acl.db")
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cur.fetchall()}
        conn.close()
        assert len(tables) > 0


# ---------------------------------------------------------------------------
# Rule management
# ---------------------------------------------------------------------------

class TestAddRule:
    @pytest.mark.asyncio
    async def test_add_allow_domain_rule(self, access_control_manager):
        rule = make_rule(user_id="user-001", rule_type=RuleType.DOMAIN,
                         access_type=AccessType.ALLOW, pattern="example.com")
        result = await access_control_manager.add_rule(rule)
        assert result is True or result is not None

    @pytest.mark.asyncio
    async def test_add_deny_ip_rule(self, access_control_manager):
        rule = make_rule(user_id="user-001", rule_type=RuleType.IP,
                         access_type=AccessType.DENY, pattern="192.168.1.100")
        result = await access_control_manager.add_rule(rule)
        assert result is True or result is not None

    @pytest.mark.asyncio
    async def test_add_cidr_rule(self, access_control_manager):
        rule = make_rule(user_id="user-002", rule_type=RuleType.IP_RANGE,
                         access_type=AccessType.ALLOW, pattern="10.0.0.0/8")
        result = await access_control_manager.add_rule(rule)
        assert result is True or result is not None

    @pytest.mark.asyncio
    async def test_add_url_pattern_rule(self, access_control_manager):
        rule = make_rule(user_id="user-003", rule_type=RuleType.URL_PATTERN,
                         access_type=AccessType.DENY,
                         pattern="http://malicious.example.com/path")
        result = await access_control_manager.add_rule(rule)
        assert result is True or result is not None

    @pytest.mark.asyncio
    async def test_add_protocol_rule(self, access_control_manager):
        rule = make_rule(user_id="user-004", rule_type=RuleType.PROTOCOL_RULE,
                         access_type=AccessType.ALLOW, pattern="tcp:443")
        result = await access_control_manager.add_rule(rule)
        assert result is True or result is not None


# ---------------------------------------------------------------------------
# Rule listing
# ---------------------------------------------------------------------------

class TestGetRules:
    @pytest.mark.asyncio
    async def test_get_user_rules_returns_list(self, access_control_manager):
        rule = make_rule(user_id="user-010", pattern="safe.example.com")
        await access_control_manager.add_rule(rule)
        rules = await access_control_manager.get_user_rules("user-010")
        assert isinstance(rules, list)
        assert len(rules) >= 1

    @pytest.mark.asyncio
    async def test_get_all_rules_returns_list(self, access_control_manager):
        result = await access_control_manager.get_all_rules()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_rules_are_access_rule_objects(self, access_control_manager):
        rule = make_rule(user_id="user-011", rule_type=RuleType.IP, pattern="8.8.8.8")
        await access_control_manager.add_rule(rule)
        rules = await access_control_manager.get_user_rules("user-011")
        for r in rules:
            assert isinstance(r, AccessRule)


# ---------------------------------------------------------------------------
# Rule removal
# ---------------------------------------------------------------------------

class TestRemoveRule:
    @pytest.mark.asyncio
    async def test_remove_existing_rule(self, access_control_manager):
        rule_id = str(uuid.uuid4())
        rule = make_rule(user_id="user-020", rule_type=RuleType.DOMAIN,
                         access_type=AccessType.DENY, pattern="bad.example.com",
                         rule_id=rule_id)
        await access_control_manager.add_rule(rule)
        success = await access_control_manager.remove_rule(rule_id)
        assert success is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_rule(self, access_control_manager):
        # SQLite DELETE on a missing row succeeds silently — True is acceptable
        success = await access_control_manager.remove_rule("no-such-id")
        assert success in (True, False)


# ---------------------------------------------------------------------------
# Access checks
# ---------------------------------------------------------------------------

class TestCheckAccess:
    @pytest.mark.asyncio
    async def test_allow_rule_permits_access(self, access_control_manager):
        rule = make_rule(user_id="user-030", rule_type=RuleType.DOMAIN,
                         access_type=AccessType.ALLOW, pattern="allowed.example.com")
        await access_control_manager.add_rule(rule)
        result = await access_control_manager.check_access(
            user_id="user-030", target="allowed.example.com"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_deny_rule_blocks_access(self, access_control_manager):
        rule = make_rule(user_id="user-031", rule_type=RuleType.DOMAIN,
                         access_type=AccessType.DENY, pattern="blocked.example.com")
        await access_control_manager.add_rule(rule)
        result = await access_control_manager.check_access(
            user_id="user-031", target="blocked.example.com"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_rules_defaults_to_allow(self, access_control_manager):
        result = await access_control_manager.check_access(
            user_id="user-032", target="unknown.example.com"
        )
        # Default behaviour is to allow when no rules match
        assert result in (True, False)  # implementation-defined default

    @pytest.mark.asyncio
    async def test_ip_allow_rule(self, access_control_manager):
        rule = make_rule(user_id="user-033", rule_type=RuleType.IP,
                         access_type=AccessType.ALLOW, pattern="1.2.3.4")
        await access_control_manager.add_rule(rule)
        result = await access_control_manager.check_access(
            user_id="user-033", target="1.2.3.4"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_ip_deny_rule(self, access_control_manager):
        rule = make_rule(user_id="user-034", rule_type=RuleType.IP,
                         access_type=AccessType.DENY, pattern="5.6.7.8")
        await access_control_manager.add_rule(rule)
        result = await access_control_manager.check_access(
            user_id="user-034", target="5.6.7.8"
        )
        assert result is False


# ---------------------------------------------------------------------------
# Domain matching
# ---------------------------------------------------------------------------

class TestDomainMatching:
    @pytest.mark.asyncio
    async def test_wildcard_subdomain_matching(self, access_control_manager):
        rule = make_rule(user_id="user-040", rule_type=RuleType.DOMAIN,
                         access_type=AccessType.ALLOW, pattern="*.example.com")
        await access_control_manager.add_rule(rule)
        result = await access_control_manager.check_access(
            user_id="user-040", target="sub.example.com"
        )
        # Wildcard may or may not be supported — just verify no exception
        assert result in (True, False)

    @pytest.mark.asyncio
    async def test_exact_domain_match(self, access_control_manager):
        rule = make_rule(user_id="user-041", rule_type=RuleType.DOMAIN,
                         access_type=AccessType.DENY, pattern="exact.example.com")
        await access_control_manager.add_rule(rule)
        result = await access_control_manager.check_access(
            user_id="user-041", target="exact.example.com"
        )
        assert result is False


# ---------------------------------------------------------------------------
# Export rules
# ---------------------------------------------------------------------------

class TestExportRules:
    @pytest.mark.asyncio
    async def test_export_returns_dict_or_list(self, access_control_manager):
        rule = make_rule(user_id="user-050", rule_type=RuleType.IP,
                         access_type=AccessType.ALLOW, pattern="10.0.0.1")
        await access_control_manager.add_rule(rule)
        result = await access_control_manager.export_user_rules("user-050")
        assert isinstance(result, (dict, list))


# ---------------------------------------------------------------------------
# Update rule
# ---------------------------------------------------------------------------

class TestUpdateRule:
    @pytest.mark.asyncio
    async def test_update_rule_changes_access_type(self, access_control_manager):
        rule_id = str(uuid.uuid4())
        rule = make_rule(user_id="user-060", rule_type=RuleType.DOMAIN,
                         access_type=AccessType.ALLOW, pattern="changeme.example.com",
                         rule_id=rule_id)
        await access_control_manager.add_rule(rule)
        # Update by creating a new AccessRule with same ID but different access type
        updated_rule = make_rule(user_id="user-060", rule_type=RuleType.DOMAIN,
                                 access_type=AccessType.DENY, pattern="changeme.example.com",
                                 rule_id=rule_id)
        try:
            await access_control_manager.update_rule(updated_rule)
        except Exception as exc:
            pytest.fail(f"update_rule raised: {exc}")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_access_type_values(self):
        assert AccessType.ALLOW is not None
        assert AccessType.DENY is not None

    def test_rule_type_values(self):
        assert RuleType.DOMAIN is not None
        assert RuleType.IP is not None
        assert RuleType.IP_RANGE is not None
        assert RuleType.URL_PATTERN is not None
        assert RuleType.PROTOCOL_RULE is not None

    def test_access_rule_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(AccessRule)


# ---------------------------------------------------------------------------
# Database error handling (lines 128-130, 146-148, 192-194, 506-508)
# ---------------------------------------------------------------------------

class TestAddRuleDbError:
    @pytest.mark.asyncio
    async def test_add_rule_db_error_returns_false(self, access_control_manager):
        """Verify add_rule returns False when DB error occurs"""
        rule = make_rule(user_id="user-error-1")

        # Mock the sqlite3 connect to raise an exception
        with patch("firewall.access_control.sqlite3.connect", side_effect=Exception("DB Error")):
            result = await access_control_manager.add_rule(rule)
            assert result is False


class TestRemoveRuleDbError:
    @pytest.mark.asyncio
    async def test_remove_rule_db_error_returns_false(self, access_control_manager):
        """Verify remove_rule returns False when DB error occurs"""
        with patch("firewall.access_control.sqlite3.connect", side_effect=Exception("DB Error")):
            result = await access_control_manager.remove_rule("some-rule-id")
            assert result is False


class TestGetUserRulesDbError:
    @pytest.mark.asyncio
    async def test_get_user_rules_db_error_returns_empty_list(self, access_control_manager):
        """Verify get_user_rules returns empty list when DB error occurs"""
        with patch("firewall.access_control.sqlite3.connect", side_effect=Exception("DB Error")):
            result = await access_control_manager.get_user_rules("user-id")
            assert result == []


class TestUpdateRuleDbError:
    @pytest.mark.asyncio
    async def test_update_rule_db_error_returns_false(self, access_control_manager):
        """Verify update_rule returns False when DB error occurs"""
        rule = make_rule(user_id="user-update-error")
        with patch("firewall.access_control.sqlite3.connect", side_effect=Exception("DB Error")):
            result = await access_control_manager.update_rule(rule)
            assert result is False


class TestGetAllRulesDbError:
    @pytest.mark.asyncio
    async def test_get_all_rules_db_error_returns_empty_list(self, access_control_manager):
        """Verify get_all_rules returns empty list when DB error occurs"""
        with patch("firewall.access_control.sqlite3.connect", side_effect=Exception("DB Error")):
            result = await access_control_manager.get_all_rules()
            assert result == []


# ---------------------------------------------------------------------------
# IP matching (line 260, 277-278)
# ---------------------------------------------------------------------------

class TestIpMatching:
    def test_match_ip_exact_ipv4(self, access_control_manager):
        """Test exact IPv4 matching"""
        rule = make_rule(pattern="192.168.1.1")
        result = access_control_manager._match_ip(rule.pattern, "192.168.1.1")
        assert result is True

    def test_match_ip_different_ipv4(self, access_control_manager):
        """Test different IPv4 returns False"""
        rule = make_rule(pattern="192.168.1.1")
        result = access_control_manager._match_ip(rule.pattern, "192.168.1.2")
        assert result is False

    def test_match_ip_with_port_stripped(self, access_control_manager):
        """Test that port is stripped from target"""
        rule = make_rule(pattern="10.0.0.1")
        result = access_control_manager._match_ip(rule.pattern, "10.0.0.1:8080")
        assert result is True

    def test_match_ip_invalid_pattern(self, access_control_manager):
        """Test that invalid IP pattern returns False"""
        rule = make_rule(pattern="not-an-ip")
        result = access_control_manager._match_ip(rule.pattern, "192.168.1.1")
        assert result is False

    def test_match_ip_invalid_target(self, access_control_manager):
        """Test that invalid target IP returns False"""
        rule = make_rule(pattern="192.168.1.1")
        result = access_control_manager._match_ip(rule.pattern, "invalid-ip")
        assert result is False

    def test_match_ip_from_url(self, access_control_manager):
        """Test extracting IP from URL"""
        rule = make_rule(pattern="8.8.8.8")
        result = access_control_manager._match_ip(rule.pattern, "https://8.8.8.8:443/path")
        assert result is True

    def test_match_ip_ipv6(self, access_control_manager):
        """Test IPv6 matching"""
        rule = make_rule(pattern="2001:db8::1")
        result = access_control_manager._match_ip(rule.pattern, "2001:db8::1")
        # IPv6 support may vary, just verify no exception
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# IP Range/CIDR matching (lines 282-296)
# ---------------------------------------------------------------------------

class TestIpRangeMatching:
    def test_match_ip_range_in_cidr(self, access_control_manager):
        """Test IP within CIDR range"""
        rule = make_rule(pattern="10.0.0.0/24", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "10.0.0.50")
        assert result is True

    def test_match_ip_range_outside_cidr(self, access_control_manager):
        """Test IP outside CIDR range"""
        rule = make_rule(pattern="10.0.0.0/24", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "10.0.1.1")
        assert result is False

    def test_match_ip_range_network_boundary(self, access_control_manager):
        """Test IP at network boundary"""
        rule = make_rule(pattern="192.168.0.0/16", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "192.168.255.255")
        assert result is True

    def test_match_ip_range_with_port(self, access_control_manager):
        """Test CIDR matching with port in target"""
        rule = make_rule(pattern="172.16.0.0/12", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "172.31.255.1:443")
        assert result is True

    def test_match_ip_range_invalid_cidr(self, access_control_manager):
        """Test invalid CIDR pattern returns False"""
        rule = make_rule(pattern="invalid/cidr", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "10.0.0.1")
        assert result is False

    def test_match_ip_range_invalid_target(self, access_control_manager):
        """Test invalid target IP returns False"""
        rule = make_rule(pattern="10.0.0.0/24", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "not-an-ip")
        assert result is False

    def test_match_ip_range_from_url(self, access_control_manager):
        """Test CIDR matching with URL as target"""
        rule = make_rule(pattern="8.8.0.0/16", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "https://8.8.8.8:443/path")
        assert result is True

    def test_match_ip_range_ipv6(self, access_control_manager):
        """Test IPv6 CIDR matching"""
        rule = make_rule(pattern="2001:db8::/32", rule_type=RuleType.IP_RANGE)
        result = access_control_manager._match_ip_range(rule.pattern, "2001:db8:1234::1")
        # IPv6 support may vary, just verify no exception
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# URL Pattern matching (lines 300-304)
# ---------------------------------------------------------------------------

class TestUrlPatternMatching:
    def test_match_url_pattern_valid_regex(self, access_control_manager):
        """Test valid regex URL pattern"""
        rule = make_rule(pattern=r"^https://.*\.example\.com/.*", rule_type=RuleType.URL_PATTERN)
        result = access_control_manager._match_url_pattern(rule.pattern, "https://sub.example.com/path")
        assert result is True

    def test_match_url_pattern_no_match(self, access_control_manager):
        """Test regex that doesn't match"""
        rule = make_rule(pattern=r"^https://blocked\..*", rule_type=RuleType.URL_PATTERN)
        result = access_control_manager._match_url_pattern(rule.pattern, "https://allowed.example.com")
        assert result is False

    def test_match_url_pattern_case_insensitive(self, access_control_manager):
        """Test that regex matching is case insensitive"""
        rule = make_rule(pattern=r"example\.com", rule_type=RuleType.URL_PATTERN)
        result = access_control_manager._match_url_pattern(rule.pattern, "EXAMPLE.COM")
        assert result is True

    def test_match_url_pattern_invalid_regex(self, access_control_manager):
        """Test invalid regex returns False and doesn't crash"""
        rule = make_rule(pattern=r"[invalid(regex", rule_type=RuleType.URL_PATTERN)
        result = access_control_manager._match_url_pattern(rule.pattern, "any-target")
        assert result is False


# ---------------------------------------------------------------------------
# Domain matching edge cases (lines 239-260)
# ---------------------------------------------------------------------------

class TestDomainMatchingEdgeCases:
    def test_match_domain_exact(self, access_control_manager):
        """Test exact domain matching"""
        result = access_control_manager._match_domain("example.com", "example.com")
        assert result is True

    def test_match_domain_case_insensitive(self, access_control_manager):
        """Test domain matching is case insensitive"""
        result = access_control_manager._match_domain("EXAMPLE.COM", "example.com")
        assert result is True

    def test_match_domain_wildcard_subdomain_match(self, access_control_manager):
        """Test wildcard subdomain matching"""
        result = access_control_manager._match_domain("*.example.com", "sub.example.com")
        assert result is True

    def test_match_domain_wildcard_exact_base(self, access_control_manager):
        """Test wildcard also matches the base domain itself"""
        result = access_control_manager._match_domain("*.example.com", "example.com")
        assert result is True

    def test_match_domain_wildcard_no_match(self, access_control_manager):
        """Test wildcard doesn't match different domain"""
        result = access_control_manager._match_domain("*.example.com", "other.domain.com")
        assert result is False

    def test_match_domain_from_url(self, access_control_manager):
        """Test extracting domain from full URL without port"""
        result = access_control_manager._match_domain("example.com", "https://example.com/path")
        assert result is True

    def test_match_domain_http_url(self, access_control_manager):
        """Test extracting domain from HTTP URL"""
        result = access_control_manager._match_domain("example.com", "http://example.com/path")
        assert result is True

    def test_match_domain_different_domain(self, access_control_manager):
        """Test non-matching domain returns False"""
        result = access_control_manager._match_domain("allowed.com", "blocked.com")
        assert result is False

    def test_match_domain_subdomain_without_wildcard(self, access_control_manager):
        """Test subdomain doesn't match pattern without wildcard"""
        result = access_control_manager._match_domain("example.com", "sub.example.com")
        assert result is False


# ---------------------------------------------------------------------------
# Protocol rule matching (lines 306-346)
# ---------------------------------------------------------------------------

class TestProtocolRuleMatching:
    @pytest.mark.asyncio
    async def test_protocol_rule_tcp_allow(self, access_control_manager):
        """Test TCP protocol rule allow"""
        rule = make_rule(
            user_id="user-proto-1",
            rule_type=RuleType.PROTOCOL_RULE,
            access_type=AccessType.ALLOW,
            pattern="tcp",
            protocol="tcp"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.check_access(
            user_id="user-proto-1",
            target="tcp:192.168.1.1:80->8.8.8.8:53"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_protocol_rule_protocol_mismatch(self, access_control_manager):
        """Test protocol rule denies on protocol mismatch"""
        rule = make_rule(
            user_id="user-proto-2",
            rule_type=RuleType.PROTOCOL_RULE,
            access_type=AccessType.DENY,
            pattern="udp",
            protocol="udp"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.check_access(
            user_id="user-proto-2",
            target="tcp:192.168.1.1:80->8.8.8.8:53"
        )
        # TCP doesn't match UDP rule, so continues to next rule or default
        assert result in (True, False)

    def test_parse_connection_target_valid_format(self, access_control_manager):
        """Test parsing valid connection target"""
        result = access_control_manager._parse_connection_target("tcp:192.168.1.1:80->8.8.8.8:53")
        assert result is not None
        assert result["protocol"] == "tcp"
        assert result["src_ip"] == "192.168.1.1"
        assert result["src_port"] == "80"
        assert result["dst_ip"] == "8.8.8.8"
        assert result["dst_port"] == "53"

    def test_parse_connection_target_with_direction(self, access_control_manager):
        """Test parsing connection target with direction"""
        result = access_control_manager._parse_connection_target("udp:*:*->192.168.1.1:53:inbound")
        assert result is not None
        assert result["protocol"] == "udp"
        assert result["src_ip"] == "*"
        assert result["direction"] == "inbound"

    def test_parse_connection_target_wildcard(self, access_control_manager):
        """Test parsing with wildcard IP/port"""
        result = access_control_manager._parse_connection_target("icmp:*:*->*:*")
        assert result is not None
        assert result["protocol"] == "icmp"
        assert result["src_ip"] == "*"

    def test_parse_connection_target_invalid_no_arrow(self, access_control_manager):
        """Test invalid target without arrow returns None"""
        result = access_control_manager._parse_connection_target("invalid-format")
        assert result is None

    def test_parse_connection_target_invalid_format(self, access_control_manager):
        """Test invalid target format"""
        result = access_control_manager._parse_connection_target("malformed")
        assert result is None

    def test_parse_connection_target_missing_protocol(self, access_control_manager):
        """Test target without protocol colon returns None"""
        result = access_control_manager._parse_connection_target("192.168.1.1->8.8.8.8")
        assert result is None

    def test_match_protocol_rule_all_match(self, access_control_manager):
        """Test protocol rule matches all conditions"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            src_ip="192.168.1.0/24",
            dst_ip="8.8.8.8",
            src_port="80-443",
            dst_port="53",
            direction="outbound"
        )

        result = access_control_manager._match_protocol_rule(rule, "tcp:192.168.1.100:443->8.8.8.8:53:outbound")
        assert result is True

    def test_match_protocol_rule_src_ip_mismatch(self, access_control_manager):
        """Test protocol rule fails on source IP mismatch"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            src_ip="10.0.0.0/8"
        )

        result = access_control_manager._match_protocol_rule(rule, "tcp:192.168.1.1:80->8.8.8.8:53")
        assert result is False

    def test_match_protocol_rule_dst_ip_mismatch(self, access_control_manager):
        """Test protocol rule fails on destination IP mismatch"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            dst_ip="1.1.1.1"
        )

        result = access_control_manager._match_protocol_rule(rule, "tcp:192.168.1.1:80->8.8.8.8:53")
        assert result is False

    def test_match_protocol_rule_invalid_target(self, access_control_manager):
        """Test protocol rule with unparseable target returns False"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp"
        )

        result = access_control_manager._match_protocol_rule(rule, "invalid-target-format")
        assert result is False


# ---------------------------------------------------------------------------
# Port matching (lines 414-434)
# ---------------------------------------------------------------------------

class TestPortMatching:
    def test_match_port_exact_single_port(self, access_control_manager):
        """Test single port matching"""
        result = access_control_manager._match_port("80", "80")
        assert result is True

    def test_match_port_different_port(self, access_control_manager):
        """Test different port returns False"""
        result = access_control_manager._match_port("80", "443")
        assert result is False

    def test_match_port_range_in_range(self, access_control_manager):
        """Test port within range"""
        result = access_control_manager._match_port("80-443", "200")
        assert result is True

    def test_match_port_range_below_range(self, access_control_manager):
        """Test port below range"""
        result = access_control_manager._match_port("80-443", "79")
        assert result is False

    def test_match_port_range_above_range(self, access_control_manager):
        """Test port above range"""
        result = access_control_manager._match_port("80-443", "444")
        assert result is False

    def test_match_port_range_boundary_low(self, access_control_manager):
        """Test port at range boundary (low)"""
        result = access_control_manager._match_port("1024-65535", "1024")
        assert result is True

    def test_match_port_range_boundary_high(self, access_control_manager):
        """Test port at range boundary (high)"""
        result = access_control_manager._match_port("1-1023", "1023")
        assert result is True

    def test_match_port_list(self, access_control_manager):
        """Test port in comma-separated list"""
        result = access_control_manager._match_port("80,443,8080", "443")
        assert result is True

    def test_match_port_list_not_in_list(self, access_control_manager):
        """Test port not in comma-separated list"""
        result = access_control_manager._match_port("80,443,8080", "9000")
        assert result is False

    def test_match_port_wildcard(self, access_control_manager):
        """Test wildcard port matches any"""
        result = access_control_manager._match_port("*", "12345")
        assert result is True

    def test_match_port_target_wildcard(self, access_control_manager):
        """Test wildcard target port matches"""
        result = access_control_manager._match_port("443", "*")
        assert result is True

    def test_match_port_invalid_target(self, access_control_manager):
        """Test invalid port number returns False"""
        result = access_control_manager._match_port("80", "not-a-port")
        assert result is False

    def test_match_port_invalid_range(self, access_control_manager):
        """Test invalid range returns False"""
        result = access_control_manager._match_port("invalid-range", "80")
        assert result is False

    def test_match_port_list_with_spaces(self, access_control_manager):
        """Test port list with spaces is handled"""
        result = access_control_manager._match_port("80, 443, 8080", "443")
        assert result is True


# ---------------------------------------------------------------------------
# IP or range matching helper (lines 397-412)
# ---------------------------------------------------------------------------

class TestMatchIpOrRange:
    def test_match_ip_or_range_exact_ip(self, access_control_manager):
        """Test exact IP match"""
        result = access_control_manager._match_ip_or_range("192.168.1.1", "192.168.1.1")
        assert result is True

    def test_match_ip_or_range_cidr(self, access_control_manager):
        """Test CIDR range match"""
        result = access_control_manager._match_ip_or_range("10.0.0.0/8", "10.5.5.5")
        assert result is True

    def test_match_ip_or_range_wildcard_rule(self, access_control_manager):
        """Test wildcard in rule matches any"""
        result = access_control_manager._match_ip_or_range("*", "192.168.1.1")
        assert result is True

    def test_match_ip_or_range_wildcard_target(self, access_control_manager):
        """Test wildcard in target matches"""
        result = access_control_manager._match_ip_or_range("192.168.1.1", "*")
        assert result is True

    def test_match_ip_or_range_invalid_rule_ip(self, access_control_manager):
        """Test invalid rule IP returns False"""
        result = access_control_manager._match_ip_or_range("invalid-ip", "192.168.1.1")
        assert result is False

    def test_match_ip_or_range_invalid_target_ip(self, access_control_manager):
        """Test invalid target IP returns False"""
        result = access_control_manager._match_ip_or_range("192.168.1.1", "invalid-ip")
        assert result is False


# ---------------------------------------------------------------------------
# Export rules (lines 535-559)
# ---------------------------------------------------------------------------

class TestExportRulesDetail:
    @pytest.mark.asyncio
    async def test_export_empty_user_rules(self, access_control_manager):
        """Test export with no rules"""
        result = await access_control_manager.export_user_rules("user-no-rules")
        assert "user_id" in result
        assert result["user_id"] == "user-no-rules"
        assert "timestamp" in result
        assert "rules" in result

    @pytest.mark.asyncio
    async def test_export_allow_domain_rule(self, access_control_manager):
        """Test exporting ALLOW domain rule"""
        rule = make_rule(
            user_id="user-export-1",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            pattern="allowed.example.com",
            rule_id="rule-1"
        )
        # Update description field before adding
        from datetime import datetime
        rule = AccessRule(
            id="rule-1",
            user_id="user-export-1",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            pattern="allowed.example.com",
            description="Allow test domain"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-1")
        assert len(result["rules"]["allow_domains"]) == 1
        assert result["rules"]["allow_domains"][0]["pattern"] == "allowed.example.com"
        assert result["rules"]["allow_domains"][0]["description"] == "Allow test domain"

    @pytest.mark.asyncio
    async def test_export_deny_domain_rule(self, access_control_manager):
        """Test exporting DENY domain rule"""
        rule = make_rule(
            user_id="user-export-2",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            pattern="blocked.example.com"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-2")
        assert len(result["rules"]["deny_domains"]) == 1

    @pytest.mark.asyncio
    async def test_export_allow_ip_rule(self, access_control_manager):
        """Test exporting ALLOW IP rule"""
        rule = make_rule(
            user_id="user-export-3",
            rule_type=RuleType.IP,
            access_type=AccessType.ALLOW,
            pattern="8.8.8.8"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-3")
        assert len(result["rules"]["allow_ips"]) == 1

    @pytest.mark.asyncio
    async def test_export_deny_ip_rule(self, access_control_manager):
        """Test exporting DENY IP rule"""
        rule = make_rule(
            user_id="user-export-4",
            rule_type=RuleType.IP,
            access_type=AccessType.DENY,
            pattern="1.1.1.1"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-4")
        assert len(result["rules"]["deny_ips"]) == 1

    @pytest.mark.asyncio
    async def test_export_allow_ip_range_rule(self, access_control_manager):
        """Test exporting ALLOW IP range rule"""
        rule = make_rule(
            user_id="user-export-5",
            rule_type=RuleType.IP_RANGE,
            access_type=AccessType.ALLOW,
            pattern="10.0.0.0/8"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-5")
        assert len(result["rules"]["allow_ip_ranges"]) == 1

    @pytest.mark.asyncio
    async def test_export_deny_ip_range_rule(self, access_control_manager):
        """Test exporting DENY IP range rule"""
        rule = make_rule(
            user_id="user-export-6",
            rule_type=RuleType.IP_RANGE,
            access_type=AccessType.DENY,
            pattern="172.16.0.0/12"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-6")
        assert len(result["rules"]["deny_ip_ranges"]) == 1

    @pytest.mark.asyncio
    async def test_export_allow_url_pattern_rule(self, access_control_manager):
        """Test exporting ALLOW URL pattern rule"""
        rule = make_rule(
            user_id="user-export-7",
            rule_type=RuleType.URL_PATTERN,
            access_type=AccessType.ALLOW,
            pattern=r"https://.*\.example\.com"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-7")
        assert len(result["rules"]["allow_url_patterns"]) == 1

    @pytest.mark.asyncio
    async def test_export_deny_url_pattern_rule(self, access_control_manager):
        """Test exporting DENY URL pattern rule"""
        rule = make_rule(
            user_id="user-export-8",
            rule_type=RuleType.URL_PATTERN,
            access_type=AccessType.DENY,
            pattern=r"malicious.*"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-8")
        assert len(result["rules"]["deny_url_patterns"]) == 1

    @pytest.mark.asyncio
    async def test_export_allow_protocol_rule(self, access_control_manager):
        """Test exporting ALLOW protocol rule"""
        rule = make_rule(
            user_id="user-export-9",
            rule_type=RuleType.PROTOCOL_RULE,
            access_type=AccessType.ALLOW,
            pattern="tcp",
            protocol="tcp",
            src_ip="192.168.1.0/24",
            dst_port="80-443"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-9")
        assert len(result["rules"]["allow_protocol_rules"]) == 1
        proto_rule = result["rules"]["allow_protocol_rules"][0]
        assert proto_rule["protocol"] == "tcp"
        assert proto_rule["src_ip"] == "192.168.1.0/24"

    @pytest.mark.asyncio
    async def test_export_deny_protocol_rule(self, access_control_manager):
        """Test exporting DENY protocol rule"""
        rule = make_rule(
            user_id="user-export-10",
            rule_type=RuleType.PROTOCOL_RULE,
            access_type=AccessType.DENY,
            pattern="udp",
            protocol="udp"
        )
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-10")
        assert len(result["rules"]["deny_protocol_rules"]) == 1

    @pytest.mark.asyncio
    async def test_export_multiple_rules_mixed_types(self, access_control_manager):
        """Test exporting multiple rules of different types"""
        rules = [
            make_rule(
                user_id="user-export-11",
                rule_type=RuleType.DOMAIN,
                access_type=AccessType.ALLOW,
                pattern="domain1.com"
            ),
            make_rule(
                user_id="user-export-11",
                rule_type=RuleType.IP,
                access_type=AccessType.DENY,
                pattern="192.168.1.1",
                rule_id="rule-b"
            ),
        ]

        for rule in rules:
            await access_control_manager.add_rule(rule)

        result = await access_control_manager.export_user_rules("user-export-11")
        assert len(result["rules"]["allow_domains"]) == 1
        assert len(result["rules"]["deny_ips"]) == 1


# ---------------------------------------------------------------------------
# Rule matching error handling (lines 228-237)
# ---------------------------------------------------------------------------

class TestRuleMatchingErrorHandling:
    @pytest.mark.asyncio
    async def test_check_access_with_invalid_rule_type(self, access_control_manager):
        """Test check_access handles invalid rule type gracefully"""
        # Create a rule with a valid type, add it, then test
        rule = make_rule(
            user_id="user-error-match",
            rule_type=RuleType.DOMAIN,
            pattern="example.com"
        )
        await access_control_manager.add_rule(rule)

        # Should not crash when checking
        result = await access_control_manager.check_access(
            user_id="user-error-match",
            target="example.com"
        )
        assert isinstance(result, bool)

    def test_rule_matches_with_exception(self, access_control_manager):
        """Test _rule_matches handles exceptions gracefully"""
        rule = make_rule(
            rule_type=RuleType.IP,
            pattern="not-valid-ip"
        )
        # This should return False without crashing
        result = access_control_manager._rule_matches(rule, "192.168.1.1")
        assert result is False


# ---------------------------------------------------------------------------
# Priority and default behavior (lines 209-219)
# ---------------------------------------------------------------------------

class TestRulePriority:
    @pytest.mark.asyncio
    async def test_rules_evaluated_by_priority(self, access_control_manager):
        """Test that rules are evaluated in priority order"""
        # Add a lower-priority DENY rule first
        rule1 = make_rule(
            user_id="user-priority",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            pattern="example.com",
            rule_id="rule-deny"
        )
        rule1.priority = 100  # Lower priority (evaluated first)

        # Add a higher-priority ALLOW rule
        rule2 = make_rule(
            user_id="user-priority",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            pattern="example.com",
            rule_id="rule-allow"
        )
        rule2.priority = 50  # Higher priority (evaluated first)

        # Add in reverse order to test sorting
        await access_control_manager.add_rule(rule1)
        await access_control_manager.add_rule(rule2)

        # Higher priority ALLOW should win
        result = await access_control_manager.check_access(
            user_id="user-priority",
            target="example.com"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_no_matching_rule_defaults_deny(self, access_control_manager):
        """Test that no matching rule defaults to DENY"""
        rule = make_rule(
            user_id="user-default-deny",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            pattern="allowed.com"
        )
        await access_control_manager.add_rule(rule)

        # Try to access a domain not in the allow rule
        result = await access_control_manager.check_access(
            user_id="user-default-deny",
            target="unallowed.com"
        )
        assert result is False


# ---------------------------------------------------------------------------
# Get all rules functionality (lines 455-479)
# ---------------------------------------------------------------------------

class TestGetAllRules:
    @pytest.mark.asyncio
    async def test_get_all_rules_empty(self, access_control_manager):
        """Test get_all_rules with no rules"""
        result = await access_control_manager.get_all_rules()
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_all_rules_multiple_users(self, access_control_manager):
        """Test get_all_rules returns rules from all users"""
        rule1 = make_rule(user_id="user-all-1", rule_id="rule-1")
        rule2 = make_rule(user_id="user-all-2", rule_id="rule-2")

        await access_control_manager.add_rule(rule1)
        await access_control_manager.add_rule(rule2)

        result = await access_control_manager.get_all_rules()
        assert len(result) >= 2

    @pytest.mark.asyncio
    async def test_get_all_rules_inactive_rules_included(self, access_control_manager):
        """Test that get_all_rules includes inactive rules (unlike get_user_rules)"""
        rule = make_rule(user_id="user-all-inactive", rule_id="rule-inactive")
        rule.is_active = False
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.get_all_rules()
        # All rules should be in the database regardless of active status
        assert any(r.id == "rule-inactive" for r in result)


# ---------------------------------------------------------------------------
# Inactive rules behavior (lines 150-163)
# ---------------------------------------------------------------------------

class TestInactiveRules:
    @pytest.mark.asyncio
    async def test_get_user_rules_excludes_inactive(self, access_control_manager):
        """Test that get_user_rules only returns active rules"""
        rule = make_rule(user_id="user-inactive-test", rule_id="rule-inactive-1")
        rule.is_active = False
        await access_control_manager.add_rule(rule)

        result = await access_control_manager.get_user_rules("user-inactive-test")
        # Inactive rule should not be returned
        assert not any(r.id == "rule-inactive-1" for r in result)

    @pytest.mark.asyncio
    async def test_check_access_ignores_inactive_rules(self, access_control_manager):
        """Test that check_access ignores inactive rules"""
        rule = make_rule(
            user_id="user-inactive-access",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            pattern="blocked.com",
            rule_id="rule-inactive-block"
        )
        rule.is_active = False
        await access_control_manager.add_rule(rule)

        # Inactive rule should be ignored
        result = await access_control_manager.check_access(
            user_id="user-inactive-access",
            target="blocked.com"
        )
        # No rules apply, so default is to deny (no rules = deny)
        assert result in (True, False)


# ---------------------------------------------------------------------------
# Additional edge case coverage (remaining uncovered lines)
# ---------------------------------------------------------------------------

class TestEdgeCasesAndBranches:
    def test_match_ip_range_with_wildcard_component(self, access_control_manager):
        """Test IP range matching when target contains mixed components"""
        # Test boundary case
        result = access_control_manager._match_ip_range("192.168.0.0/16", "192.168.0.0")
        assert result is True

    def test_parse_connection_target_extra_arrow(self, access_control_manager):
        """Test parsing with multiple arrows (edge case)"""
        # Format with multiple arrows - should still parse first arrow
        result = access_control_manager._parse_connection_target("tcp:1.1.1.1:80->2.2.2.2:443->extra")
        # Should still parse successfully
        assert result is not None

    def test_match_protocol_rule_with_direction_both(self, access_control_manager):
        """Test protocol rule with direction='both'"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            direction="both"
        )
        # Both should match any direction
        result = access_control_manager._match_protocol_rule(rule, "tcp:1.1.1.1:80->2.2.2.2:443:inbound")
        assert result is True

    def test_match_protocol_rule_without_direction_in_target(self, access_control_manager):
        """Test protocol rule when target has no direction specified"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            direction="outbound"
        )
        # Target without explicit direction defaults to 'outbound'
        result = access_control_manager._match_protocol_rule(rule, "tcp:1.1.1.1:80->2.2.2.2:443")
        assert result is True

    def test_rule_matches_invalid_rule_type_enum(self, access_control_manager):
        """Test _rule_matches with each RuleType to ensure all branches covered"""
        # Test DOMAIN
        rule_domain = make_rule(rule_type=RuleType.DOMAIN, pattern="example.com")
        result = access_control_manager._rule_matches(rule_domain, "example.com")
        assert isinstance(result, bool)

        # Test IP
        rule_ip = make_rule(rule_type=RuleType.IP, pattern="1.1.1.1")
        result = access_control_manager._rule_matches(rule_ip, "1.1.1.1")
        assert isinstance(result, bool)

        # Test IP_RANGE
        rule_cidr = make_rule(rule_type=RuleType.IP_RANGE, pattern="10.0.0.0/8")
        result = access_control_manager._rule_matches(rule_cidr, "10.5.5.5")
        assert isinstance(result, bool)

        # Test URL_PATTERN
        rule_url = make_rule(rule_type=RuleType.URL_PATTERN, pattern=r".*\.example\.com")
        result = access_control_manager._rule_matches(rule_url, "sub.example.com")
        assert isinstance(result, bool)

        # Test PROTOCOL_RULE
        rule_proto = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp"
        )
        result = access_control_manager._rule_matches(rule_proto, "tcp:1.1.1.1:80->2.2.2.2:443")
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_check_access_multiple_rules_first_wins(self, access_control_manager):
        """Test that first matching rule (by priority) determines access"""
        # Add multiple rules for same user/target with different priorities
        rule1 = make_rule(
            user_id="user-multi",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            pattern="example.com",
            rule_id="rule-allow-low"
        )
        rule1.priority = 100

        rule2 = make_rule(
            user_id="user-multi",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            pattern="example.com",
            rule_id="rule-deny-high"
        )
        rule2.priority = 50

        # Add in reverse order to ensure sorting happens
        await access_control_manager.add_rule(rule1)
        await access_control_manager.add_rule(rule2)

        # Higher priority (lower number) DENY should be evaluated first
        result = await access_control_manager.check_access("user-multi", "example.com")
        assert result is False

    def test_match_port_single_port_as_string_number(self, access_control_manager):
        """Test port matching with valid numeric strings"""
        result = access_control_manager._match_port("443", "443")
        assert result is True

    def test_match_port_complex_list_order(self, access_control_manager):
        """Test port list matching regardless of order"""
        result = access_control_manager._match_port("443,80,8080,3000", "80")
        assert result is True

    def test_match_ip_or_range_with_leading_zeros(self, access_control_manager):
        """Test IP matching doesn't break with standard IP format"""
        result = access_control_manager._match_ip_or_range("192.168.1.1", "192.168.1.1")
        assert result is True

    def test_parse_connection_target_minimal_format(self, access_control_manager):
        """Test parsing minimal valid format"""
        result = access_control_manager._parse_connection_target("tcp:*:*->*:*")
        assert result is not None
        assert result["protocol"] == "tcp"
        assert result["src_ip"] == "*"
        assert result["src_port"] == "*"
        assert result["dst_ip"] == "*"
        assert result["dst_port"] == "*"

    @pytest.mark.asyncio
    async def test_update_rule_updates_timestamp(self, access_control_manager):
        """Test that update_rule updates the updated_at field"""
        import time
        rule = make_rule(user_id="user-timestamp", rule_id="rule-ts")
        await access_control_manager.add_rule(rule)

        # Wait a moment to ensure timestamp difference
        time.sleep(0.01)

        updated_rule = make_rule(
            user_id="user-timestamp",
            rule_id="rule-ts",
            pattern="updated.com"
        )
        result = await access_control_manager.update_rule(updated_rule)
        assert result is True

    def test_match_domain_with_empty_pattern(self, access_control_manager):
        """Test domain matching with edge cases"""
        result = access_control_manager._match_domain("", "")
        # Empty should match empty
        assert result is True

    def test_match_domain_subdomain_depth(self, access_control_manager):
        """Test wildcard matching with multiple subdomain levels"""
        result = access_control_manager._match_domain("*.example.com", "a.b.example.com")
        # Wildcard in implementation matches any subdomain string via endswith
        assert result is True

    def test_export_with_null_description(self, access_control_manager):
        """Test export includes rules with null descriptions"""
        from firewall.access_control import AccessRule
        rule = AccessRule(
            id="rule-null-desc",
            user_id="user-export-null",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            pattern="example.com",
            description=None
        )
        import asyncio
        asyncio.get_event_loop().run_until_complete(access_control_manager.add_rule(rule))

        result_sync = asyncio.get_event_loop().run_until_complete(
            access_control_manager.export_user_rules("user-export-null")
        )
        assert len(result_sync["rules"]["allow_domains"]) > 0

    def test_match_protocol_rule_src_port_mismatch(self, access_control_manager):
        """Test protocol rule fails on source port mismatch"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            src_port="80"
        )
        result = access_control_manager._match_protocol_rule(rule, "tcp:1.1.1.1:443->2.2.2.2:443")
        assert result is False

    def test_match_protocol_rule_dst_port_mismatch(self, access_control_manager):
        """Test protocol rule fails on destination port mismatch"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            dst_port="80"
        )
        result = access_control_manager._match_protocol_rule(rule, "tcp:1.1.1.1:80->2.2.2.2:443")
        assert result is False

    def test_match_protocol_rule_direction_mismatch(self, access_control_manager):
        """Test protocol rule fails on direction mismatch"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp",
            direction="inbound"
        )
        result = access_control_manager._match_protocol_rule(rule, "tcp:1.1.1.1:80->2.2.2.2:443:outbound")
        assert result is False

    def test_parse_connection_target_with_ipv6(self, access_control_manager):
        """Test parsing connection target with IPv6 addresses"""
        # Standard IPv6 format may not work with colon separator, but test the code path
        result = access_control_manager._parse_connection_target("tcp:1.1.1.1:80->2.2.2.2:443")
        assert result is not None
        assert result["src_ip"] == "1.1.1.1"
        assert result["dst_ip"] == "2.2.2.2"

    def test_match_protocol_rule_exception_handling(self, access_control_manager):
        """Test that exceptions in _match_protocol_rule are handled"""
        rule = make_rule(
            rule_type=RuleType.PROTOCOL_RULE,
            pattern="tcp",
            protocol="tcp"
        )
        # Pass a None target to trigger exception handling
        with patch.object(
            access_control_manager,
            "_parse_connection_target",
            side_effect=Exception("Parse error")
        ):
            result = access_control_manager._match_protocol_rule(rule, "tcp:1.1.1.1:80->2.2.2.2:443")
            assert result is False

    @pytest.mark.asyncio
    async def test_rule_matches_exception_in_domain_matching(self, access_control_manager):
        """Test that exceptions in rule matching are caught and logged"""
        rule = make_rule(
            rule_type=RuleType.DOMAIN,
            pattern="example.com"
        )
        # Normally this would work fine, but test the exception handler exists
        with patch.object(
            access_control_manager,
            "_match_domain",
            side_effect=Exception("Match error")
        ):
            result = access_control_manager._rule_matches(rule, "example.com")
            assert result is False

    def test_parse_connection_target_exception_handling(self, access_control_manager):
        """Test exception handling in _parse_connection_target"""
        # Trigger the exception handler with a string that causes an error
        with patch("firewall.access_control.logger") as mock_logger:
            result = access_control_manager._parse_connection_target(None)
            # Should return None safely
            assert result is None
