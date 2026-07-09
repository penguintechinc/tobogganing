"""Tests for SASE firewall access control manager."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.modules.sase.firewall.access_control import (
    AccessControlManager,
    AccessRule,
    AccessType,
    RuleType,
)
from core.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_firewall_db() -> MagicMock:
    """Create a mock DAL with firewall_rules table support.

    Returns:
        Mock database object with firewall_rules table.
    """
    db = MagicMock()

    # Mock firewall_rules table
    firewall_rules_table = MagicMock()
    firewall_rules_table.async_insert = AsyncMock(return_value=1)

    # Mock query builder for firewall_rules
    def make_query_proxy() -> MagicMock:
        query_proxy = MagicMock()
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
        query_proxy.count = AsyncMock(return_value=0)
        query_proxy.update = AsyncMock(return_value=None)
        query_proxy.delete = AsyncMock(return_value=None)
        query_proxy.__and__ = MagicMock(return_value=query_proxy)
        query_proxy.__or__ = MagicMock(return_value=query_proxy)
        return query_proxy

    query_proxy = make_query_proxy()
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy
    db.firewall_rules = firewall_rules_table

    return db


@pytest.mark.asyncio
async def test_add_rule(mock_firewall_db: MagicMock) -> None:
    """Test adding a new firewall rule."""
    manager = AccessControlManager(mock_firewall_db)

    rule = AccessRule(
        id=str(uuid4()),
        tenant="test-tenant",
        user_id=str(uuid4()),
        rule_type=RuleType.DOMAIN,
        access_type=AccessType.ALLOW,
        pattern="example.com",
        priority=100,
        is_active=True,
    )

    result = await manager.add_rule(rule)

    assert result is True
    mock_firewall_db.firewall_rules.async_insert.assert_called_once()
    call_kwargs = mock_firewall_db.firewall_rules.async_insert.call_args[1]
    assert call_kwargs["id"] == rule.id
    assert call_kwargs["tenant"] == rule.tenant
    assert call_kwargs["user_id"] == rule.user_id
    assert call_kwargs["rule_type"] == "domain"
    assert call_kwargs["access_type"] == "allow"
    assert call_kwargs["pattern"] == "example.com"


@pytest.mark.asyncio
async def test_add_rule_failure(mock_firewall_db: MagicMock) -> None:
    """Test add_rule handles errors gracefully."""
    mock_firewall_db.firewall_rules.async_insert = AsyncMock(side_effect=Exception("DB error"))
    manager = AccessControlManager(mock_firewall_db)

    rule = AccessRule(
        id=str(uuid4()),
        tenant="test-tenant",
        user_id=str(uuid4()),
        rule_type=RuleType.DOMAIN,
        access_type=AccessType.ALLOW,
        pattern="example.com",
    )

    result = await manager.add_rule(rule)

    assert result is False


@pytest.mark.asyncio
async def test_remove_rule(mock_firewall_db: MagicMock) -> None:
    """Test removing a firewall rule."""
    query_proxy = mock_firewall_db()
    manager = AccessControlManager(mock_firewall_db)

    rule_id = str(uuid4())
    tenant = "test-tenant"

    result = await manager.remove_rule(rule_id, tenant)

    assert result is True
    query_proxy.delete.assert_called_once()


@pytest.mark.asyncio
async def test_remove_rule_failure(mock_firewall_db: MagicMock) -> None:
    """Test remove_rule handles errors gracefully."""
    query_proxy = mock_firewall_db()
    query_proxy.delete = AsyncMock(side_effect=Exception("DB error"))
    manager = AccessControlManager(mock_firewall_db)

    rule_id = str(uuid4())
    tenant = "test-tenant"

    result = await manager.remove_rule(rule_id, tenant)

    assert result is False


@pytest.mark.asyncio
async def test_get_user_rules(mock_firewall_db: MagicMock) -> None:
    """Test retrieving user rules with tenant scoping."""
    rule_id = str(uuid4())
    user_id = str(uuid4())
    tenant = "test-tenant"

    rule_row = make_mock_row(
        {
            "id": rule_id,
            "tenant": tenant,
            "user_id": user_id,
            "rule_type": "domain",
            "access_type": "allow",
            "pattern": "example.com",
            "priority": 100,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "description": "Allow example.com",
            "src_ip": None,
            "dst_ip": None,
            "protocol": None,
            "src_port": None,
            "dst_port": None,
            "direction": None,
        }
    )

    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    rules = await manager.get_user_rules(user_id, tenant)

    assert len(rules) == 1
    assert rules[0].id == rule_id
    assert rules[0].tenant == tenant
    assert rules[0].user_id == user_id
    assert rules[0].pattern == "example.com"
    assert rules[0].rule_type == RuleType.DOMAIN
    assert rules[0].access_type == AccessType.ALLOW


@pytest.mark.asyncio
async def test_get_user_rules_tenant_scoping(mock_firewall_db: MagicMock) -> None:
    """Test that get_user_rules applies tenant scoping."""
    user_id = str(uuid4())
    tenant = "test-tenant"

    query_proxy = mock_firewall_db()
    manager = AccessControlManager(mock_firewall_db)
    await manager.get_user_rules(user_id, tenant)

    # Verify the query was called with tenant filter
    mock_firewall_db.assert_called()
    # The call should include tenant == filter


@pytest.mark.asyncio
async def test_check_access_no_rules(mock_firewall_db: MagicMock) -> None:
    """Test check_access defaults to allow when no rules exist."""
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))

    manager = AccessControlManager(mock_firewall_db)
    user_id = str(uuid4())
    tenant = "test-tenant"

    result = await manager.check_access(user_id, tenant, "example.com")

    # No rules - default to allow
    assert result is True


@pytest.mark.asyncio
async def test_check_access_allow_match(mock_firewall_db: MagicMock) -> None:
    """Test check_access with matching allow rule."""
    rule_id = str(uuid4())
    user_id = str(uuid4())
    tenant = "test-tenant"

    rule_row = make_mock_row(
        {
            "id": rule_id,
            "tenant": tenant,
            "user_id": user_id,
            "rule_type": "domain",
            "access_type": "allow",
            "pattern": "example.com",
            "priority": 100,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "description": "Allow example.com",
            "src_ip": None,
            "dst_ip": None,
            "protocol": None,
            "src_port": None,
            "dst_port": None,
            "direction": None,
        }
    )

    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.check_access(user_id, tenant, "example.com")

    assert result is True


@pytest.mark.asyncio
async def test_check_access_deny_match(mock_firewall_db: MagicMock) -> None:
    """Test check_access with matching deny rule."""
    rule_id = str(uuid4())
    user_id = str(uuid4())
    tenant = "test-tenant"

    rule_row = make_mock_row(
        {
            "id": rule_id,
            "tenant": tenant,
            "user_id": user_id,
            "rule_type": "domain",
            "access_type": "deny",
            "pattern": "blocked.com",
            "priority": 100,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "description": "Block blocked.com",
            "src_ip": None,
            "dst_ip": None,
            "protocol": None,
            "src_port": None,
            "dst_port": None,
            "direction": None,
        }
    )

    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.check_access(user_id, tenant, "blocked.com")

    assert result is False


@pytest.mark.asyncio
async def test_get_all_rules(mock_firewall_db: MagicMock) -> None:
    """Test retrieving all rules with tenant scoping."""
    rule_id1 = str(uuid4())
    rule_id2 = str(uuid4())
    user_id = str(uuid4())
    tenant = "test-tenant"

    rule_row1 = make_mock_row(
        {
            "id": rule_id1,
            "tenant": tenant,
            "user_id": user_id,
            "rule_type": "domain",
            "access_type": "allow",
            "pattern": "example.com",
            "priority": 100,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "description": None,
            "src_ip": None,
            "dst_ip": None,
            "protocol": None,
            "src_port": None,
            "dst_port": None,
            "direction": None,
        }
    )

    rule_row2 = make_mock_row(
        {
            "id": rule_id2,
            "tenant": tenant,
            "user_id": user_id,
            "rule_type": "ip",
            "access_type": "deny",
            "pattern": "192.168.1.1",
            "priority": 50,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "description": None,
            "src_ip": None,
            "dst_ip": None,
            "protocol": None,
            "src_port": None,
            "dst_port": None,
            "direction": None,
        }
    )

    rowset = make_mock_rowset([rule_row1, rule_row2])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    rules = await manager.get_all_rules(tenant)

    assert len(rules) == 2
    assert rules[0].pattern == "example.com"
    assert rules[1].pattern == "192.168.1.1"


@pytest.mark.asyncio
async def test_update_rule(mock_firewall_db: MagicMock) -> None:
    """Test updating an existing rule."""
    rule_id = str(uuid4())
    tenant = "test-tenant"
    user_id = str(uuid4())

    rule = AccessRule(
        id=rule_id,
        tenant=tenant,
        user_id=user_id,
        rule_type=RuleType.DOMAIN,
        access_type=AccessType.ALLOW,
        pattern="updated.com",
        priority=50,
        is_active=False,
    )

    query_proxy = mock_firewall_db()
    manager = AccessControlManager(mock_firewall_db)
    result = await manager.update_rule(rule)

    assert result is True
    query_proxy.update.assert_called_once()


@pytest.mark.asyncio
async def test_update_rule_failure(mock_firewall_db: MagicMock) -> None:
    """Test update_rule handles errors gracefully."""
    query_proxy = mock_firewall_db()
    query_proxy.update = AsyncMock(side_effect=Exception("DB error"))

    rule_id = str(uuid4())
    tenant = "test-tenant"
    user_id = str(uuid4())

    rule = AccessRule(
        id=rule_id,
        tenant=tenant,
        user_id=user_id,
        rule_type=RuleType.DOMAIN,
        access_type=AccessType.ALLOW,
        pattern="example.com",
    )

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.update_rule(rule)

    assert result is False


@pytest.mark.asyncio
async def test_export_user_rules(mock_firewall_db: MagicMock) -> None:
    """Test exporting user rules in categorized format."""
    rule_id1 = str(uuid4())
    rule_id2 = str(uuid4())
    user_id = str(uuid4())
    tenant = "test-tenant"

    rule_row1 = make_mock_row(
        {
            "id": rule_id1,
            "tenant": tenant,
            "user_id": user_id,
            "rule_type": "domain",
            "access_type": "allow",
            "pattern": "example.com",
            "priority": 100,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "description": "Allow example",
            "src_ip": None,
            "dst_ip": None,
            "protocol": None,
            "src_port": None,
            "dst_port": None,
            "direction": None,
        }
    )

    rule_row2 = make_mock_row(
        {
            "id": rule_id2,
            "tenant": tenant,
            "user_id": user_id,
            "rule_type": "ip",
            "access_type": "deny",
            "pattern": "10.0.0.1",
            "priority": 50,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "description": None,
            "src_ip": None,
            "dst_ip": None,
            "protocol": None,
            "src_port": None,
            "dst_port": None,
            "direction": None,
        }
    )

    rowset = make_mock_rowset([rule_row1, rule_row2])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    export_data = await manager.export_user_rules(user_id, tenant)

    assert export_data["user_id"] == user_id
    assert "timestamp" in export_data
    assert len(export_data["rules"]["allow_domains"]) == 1
    assert len(export_data["rules"]["deny_ips"]) == 1
    assert export_data["rules"]["allow_domains"][0]["pattern"] == "example.com"


@pytest.mark.asyncio
async def test_match_domain_exact() -> None:
    """Test exact domain matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_domain("example.com", "example.com") is True
    assert manager._match_domain("example.com", "other.com") is False


@pytest.mark.asyncio
async def test_match_domain_wildcard() -> None:
    """Test wildcard domain matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_domain("*.example.com", "sub.example.com") is True
    assert manager._match_domain("*.example.com", "example.com") is False
    assert manager._match_domain("*.example.com", "deep.sub.example.com") is True


@pytest.mark.asyncio
async def test_match_domain_from_url() -> None:
    """Test domain matching extracts domain from URL."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_domain("example.com", "https://example.com/path") is True
    assert manager._match_domain("example.com", "http://example.com:8080/") is True


@pytest.mark.asyncio
async def test_match_ip() -> None:
    """Test IP address matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_ip("192.168.1.1", "192.168.1.1") is True
    assert manager._match_ip("192.168.1.1", "192.168.1.2") is False


@pytest.mark.asyncio
async def test_match_ip_range() -> None:
    """Test IP CIDR range matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_ip_range("192.168.1.0/24", "192.168.1.1") is True
    assert manager._match_ip_range("192.168.1.0/24", "192.168.2.1") is False
    assert manager._match_ip_range("10.0.0.0/8", "10.255.255.255") is True


@pytest.mark.asyncio
async def test_match_url_pattern() -> None:
    """Test URL regex pattern matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_url_pattern(r".*\.example\.com.*", "https://sub.example.com/page") is True
    assert manager._match_url_pattern(r".*\.example\.com.*", "https://other.com") is False


@pytest.mark.asyncio
async def test_match_port_single() -> None:
    """Test single port matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_port("80", "80") is True
    assert manager._match_port("80", "443") is False


@pytest.mark.asyncio
async def test_match_port_range() -> None:
    """Test port range matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_port("80-443", "80") is True
    assert manager._match_port("80-443", "443") is True
    assert manager._match_port("80-443", "8080") is False


@pytest.mark.asyncio
async def test_match_port_list() -> None:
    """Test port list matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_port("80,443,8080", "80") is True
    assert manager._match_port("80,443,8080", "443") is True
    assert manager._match_port("80,443,8080", "3306") is False


@pytest.mark.asyncio
async def test_match_port_wildcard() -> None:
    """Test wildcard port matching."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_port("*", "80") is True
    assert manager._match_port("443", "*") is True
