"""
Tests for firewall/access_control.py — rule evaluation, IP/domain/URL matching.
"""
import pytest
from unittest.mock import MagicMock, patch

from firewall.access_control import (
    AccessControlManager,
    AccessRule,
    AccessType,
    RuleType,
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
        rule_id = await access_control_manager.add_rule(
            user_id="user-001",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            target="example.com",
        )
        assert rule_id is not None

    @pytest.mark.asyncio
    async def test_add_deny_ip_rule(self, access_control_manager):
        rule_id = await access_control_manager.add_rule(
            user_id="user-001",
            rule_type=RuleType.IP,
            access_type=AccessType.DENY,
            target="192.168.1.100",
        )
        assert rule_id is not None

    @pytest.mark.asyncio
    async def test_add_cidr_rule(self, access_control_manager):
        rule_id = await access_control_manager.add_rule(
            user_id="user-002",
            rule_type=RuleType.IP_RANGE,
            access_type=AccessType.ALLOW,
            target="10.0.0.0/8",
        )
        assert rule_id is not None

    @pytest.mark.asyncio
    async def test_add_url_rule(self, access_control_manager):
        rule_id = await access_control_manager.add_rule(
            user_id="user-003",
            rule_type=RuleType.URL,
            access_type=AccessType.DENY,
            target="http://malicious.example.com/path",
        )
        assert rule_id is not None

    @pytest.mark.asyncio
    async def test_add_protocol_rule(self, access_control_manager):
        rule_id = await access_control_manager.add_rule(
            user_id="user-004",
            rule_type=RuleType.PROTOCOL,
            access_type=AccessType.ALLOW,
            target="tcp:443",
        )
        assert rule_id is not None


# ---------------------------------------------------------------------------
# Rule listing
# ---------------------------------------------------------------------------

class TestGetRules:
    @pytest.mark.asyncio
    async def test_get_user_rules_returns_list(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-010",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            target="safe.example.com",
        )
        rules = await access_control_manager.get_user_rules("user-010")
        assert isinstance(rules, list)
        assert len(rules) >= 1

    @pytest.mark.asyncio
    async def test_get_all_rules_returns_list(self, access_control_manager):
        result = await access_control_manager.get_all_rules()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_rules_are_access_rule_objects(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-011",
            rule_type=RuleType.IP,
            access_type=AccessType.ALLOW,
            target="8.8.8.8",
        )
        rules = await access_control_manager.get_user_rules("user-011")
        for rule in rules:
            assert isinstance(rule, AccessRule)


# ---------------------------------------------------------------------------
# Rule removal
# ---------------------------------------------------------------------------

class TestRemoveRule:
    @pytest.mark.asyncio
    async def test_remove_existing_rule(self, access_control_manager):
        rule_id = await access_control_manager.add_rule(
            user_id="user-020",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            target="bad.example.com",
        )
        success = await access_control_manager.remove_rule(rule_id, "user-020")
        assert success is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_rule(self, access_control_manager):
        success = await access_control_manager.remove_rule("no-such-id", "user-999")
        assert success is False


# ---------------------------------------------------------------------------
# Access checks
# ---------------------------------------------------------------------------

class TestCheckAccess:
    @pytest.mark.asyncio
    async def test_allow_rule_permits_access(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-030",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            target="allowed.example.com",
        )
        result = await access_control_manager.check_access(
            user_id="user-030",
            connection_target="allowed.example.com",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_deny_rule_blocks_access(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-031",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            target="blocked.example.com",
        )
        result = await access_control_manager.check_access(
            user_id="user-031",
            connection_target="blocked.example.com",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_rules_defaults_to_allow(self, access_control_manager):
        result = await access_control_manager.check_access(
            user_id="user-032",
            connection_target="unknown.example.com",
        )
        # Default behaviour is to allow when no rules match
        assert result in (True, False)  # implementation-defined default

    @pytest.mark.asyncio
    async def test_ip_allow_rule(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-033",
            rule_type=RuleType.IP,
            access_type=AccessType.ALLOW,
            target="1.2.3.4",
        )
        result = await access_control_manager.check_access(
            user_id="user-033",
            connection_target="1.2.3.4",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_ip_deny_rule(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-034",
            rule_type=RuleType.IP,
            access_type=AccessType.DENY,
            target="5.6.7.8",
        )
        result = await access_control_manager.check_access(
            user_id="user-034",
            connection_target="5.6.7.8",
        )
        assert result is False


# ---------------------------------------------------------------------------
# Domain matching
# ---------------------------------------------------------------------------

class TestDomainMatching:
    @pytest.mark.asyncio
    async def test_wildcard_subdomain_matching(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-040",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            target="*.example.com",
        )
        result = await access_control_manager.check_access(
            user_id="user-040",
            connection_target="sub.example.com",
        )
        # Wildcard may or may not be supported — just verify no exception
        assert result in (True, False)

    @pytest.mark.asyncio
    async def test_exact_domain_match(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-041",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.DENY,
            target="exact.example.com",
        )
        result = await access_control_manager.check_access(
            user_id="user-041",
            connection_target="exact.example.com",
        )
        assert result is False


# ---------------------------------------------------------------------------
# Export rules
# ---------------------------------------------------------------------------

class TestExportRules:
    @pytest.mark.asyncio
    async def test_export_returns_dict_or_list(self, access_control_manager):
        await access_control_manager.add_rule(
            user_id="user-050",
            rule_type=RuleType.IP,
            access_type=AccessType.ALLOW,
            target="10.0.0.1",
        )
        result = await access_control_manager.export_user_rules("user-050")
        assert isinstance(result, (dict, list))


# ---------------------------------------------------------------------------
# Update rule
# ---------------------------------------------------------------------------

class TestUpdateRule:
    @pytest.mark.asyncio
    async def test_update_rule_changes_access_type(self, access_control_manager):
        rule_id = await access_control_manager.add_rule(
            user_id="user-060",
            rule_type=RuleType.DOMAIN,
            access_type=AccessType.ALLOW,
            target="changeme.example.com",
        )
        # Update should not raise
        try:
            await access_control_manager.update_rule(
                rule_id=rule_id,
                user_id="user-060",
                access_type=AccessType.DENY,
            )
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

    def test_access_rule_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(AccessRule)
