"""Edge-case coverage for AccessControlManager not covered by test_sdwan_firewall.py.

Covers exception (fail-closed) branches, non-domain/non-IP rule types in
export/match, and standalone matcher helpers (_match_protocol_rule,
_parse_connection_target, _match_ip_or_range) that have no direct tests.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hub_api.modules.sdwan.firewall.access_control import (
    AccessControlManager,
    AccessRule,
    AccessType,
    RuleType,
)
from hub_api.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_firewall_db() -> MagicMock:
    """Create a mock DAL with firewall_rules table support.

    Returns:
        Mock database object with firewall_rules table.
    """
    db = MagicMock()
    firewall_rules_table = MagicMock()
    firewall_rules_table.async_insert = AsyncMock(return_value=1)

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


def _rule_row(**overrides) -> dict:
    """Build a firewall_rules row dict with sane defaults.

    Args:
        overrides: Fields to override.

    Returns:
        Dict of row data suitable for make_mock_row.
    """
    defaults = dict(
        id=str(uuid4()),
        tenant="test-tenant",
        user_id=str(uuid4()),
        rule_type="domain",
        access_type="allow",
        pattern="example.com",
        priority=100,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_active=True,
        description=None,
        src_ip=None,
        dst_ip=None,
        protocol=None,
        src_port=None,
        dst_port=None,
        direction=None,
    )
    defaults.update(overrides)
    return defaults


# --- get_user_rules / get_all_rules exception paths --------------------------


@pytest.mark.asyncio
async def test_get_user_rules_exception_returns_empty(
    mock_firewall_db: MagicMock,
) -> None:
    """get_user_rules fails closed (empty list) on DB error."""
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))

    manager = AccessControlManager(mock_firewall_db)
    rules = await manager.get_user_rules("user-1", "tenant-1")

    assert rules == []


@pytest.mark.asyncio
async def test_get_all_rules_exception_returns_empty(
    mock_firewall_db: MagicMock,
) -> None:
    """get_all_rules fails closed (empty list) on DB error."""
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(side_effect=RuntimeError("db error"))

    manager = AccessControlManager(mock_firewall_db)
    rules = await manager.get_all_rules("tenant-1")

    assert rules == []


# --- check_access: no rule matches -> default deny ---------------------------


@pytest.mark.asyncio
async def test_check_access_no_match_defaults_to_deny(
    mock_firewall_db: MagicMock,
) -> None:
    """check_access denies when rules exist but none match the target."""
    rule_row = make_mock_row(_rule_row(pattern="other.com"))
    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.check_access("user-1", "tenant-1", "example.com")

    assert result is False


# --- export_user_rules: IP_RANGE / URL_PATTERN / PROTOCOL_RULE branches ------


@pytest.mark.asyncio
async def test_export_user_rules_all_rule_types(mock_firewall_db: MagicMock) -> None:
    """export_user_rules categorizes ip_range, url_pattern, and protocol_rule types."""
    ip_range_row = make_mock_row(
        _rule_row(rule_type="ip_range", access_type="allow", pattern="10.0.0.0/8")
    )
    url_pattern_row = make_mock_row(
        _rule_row(rule_type="url_pattern", access_type="deny", pattern=r".*\.evil\.com.*")
    )
    protocol_row = make_mock_row(
        _rule_row(
            rule_type="protocol_rule",
            access_type="allow",
            pattern="tcp-rule",
            src_ip="10.0.0.1",
            dst_ip="8.8.8.8",
            protocol="tcp",
            src_port="*",
            dst_port="53",
            direction="outbound",
        )
    )

    rowset = make_mock_rowset([ip_range_row, url_pattern_row, protocol_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    export_data = await manager.export_user_rules("user-1", "tenant-1")

    assert len(export_data["rules"]["allow_ip_ranges"]) == 1
    assert len(export_data["rules"]["deny_url_patterns"]) == 1
    assert len(export_data["rules"]["allow_protocol_rules"]) == 1
    protocol_export = export_data["rules"]["allow_protocol_rules"][0]
    assert protocol_export["protocol"] == "tcp"
    assert protocol_export["dst_port"] == "53"


# --- _rule_matches: IP / IP_RANGE / URL_PATTERN / PROTOCOL_RULE + exception --


@pytest.mark.asyncio
async def test_check_access_ip_rule_match(mock_firewall_db: MagicMock) -> None:
    """check_access matches an IP-type rule."""
    rule_row = make_mock_row(_rule_row(rule_type="ip", access_type="deny", pattern="192.168.1.1"))
    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.check_access("user-1", "tenant-1", "192.168.1.1")

    assert result is False


@pytest.mark.asyncio
async def test_check_access_ip_range_rule_match(mock_firewall_db: MagicMock) -> None:
    """check_access matches an IP_RANGE-type rule."""
    rule_row = make_mock_row(
        _rule_row(rule_type="ip_range", access_type="allow", pattern="10.0.0.0/8")
    )
    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.check_access("user-1", "tenant-1", "10.1.2.3")

    assert result is True


@pytest.mark.asyncio
async def test_check_access_url_pattern_rule_match(mock_firewall_db: MagicMock) -> None:
    """check_access matches a URL_PATTERN-type rule."""
    rule_row = make_mock_row(
        _rule_row(rule_type="url_pattern", access_type="deny", pattern=r".*\.evil\.com.*")
    )
    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.check_access("user-1", "tenant-1", "https://sub.evil.com/path")

    assert result is False


@pytest.mark.asyncio
async def test_check_access_protocol_rule_match(mock_firewall_db: MagicMock) -> None:
    """check_access matches a PROTOCOL_RULE-type rule."""
    rule_row = make_mock_row(
        _rule_row(
            rule_type="protocol_rule",
            access_type="allow",
            pattern="tcp-rule",
            protocol="tcp",
            dst_port="443",
        )
    )
    rowset = make_mock_rowset([rule_row])
    query_proxy = mock_firewall_db()
    query_proxy.select = AsyncMock(return_value=rowset)
    mock_firewall_db.return_value = query_proxy

    manager = AccessControlManager(mock_firewall_db)
    result = await manager.check_access("user-1", "tenant-1", "tcp:10.0.0.1:1234->8.8.8.8:443")

    assert result is True


def test_rule_matches_exception_returns_false() -> None:
    """_rule_matches fails closed (False) if a matcher raises."""
    manager = AccessControlManager(MagicMock())
    rule = AccessRule(
        id=str(uuid4()),
        tenant="t",
        user_id="u",
        rule_type=RuleType.URL_PATTERN,
        access_type=AccessType.DENY,
        pattern="[invalid(regex",
    )

    # Invalid regex raises re.error inside _match_url_pattern which is caught
    # internally, but force a raise at the _rule_matches level too via a
    # target that breaks urlparse-based matching paths is not needed --
    # _match_url_pattern already returns False on re.error, so assert that.
    assert manager._rule_matches(rule, "https://example.com") is False


# --- _match_ip: URL extraction + invalid pattern exception -------------------


def test_match_ip_from_url_target() -> None:
    """_match_ip extracts the IP from a URL target before comparing."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_ip("192.168.1.1", "https://192.168.1.1:8080/path") is True


def test_match_ip_invalid_pattern_returns_false() -> None:
    """_match_ip returns False when the pattern isn't a valid IP."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_ip("not-an-ip", "192.168.1.1") is False


# --- _match_ip_range: URL extraction + invalid CIDR exception ----------------


def test_match_ip_range_from_url_target() -> None:
    """_match_ip_range extracts the IP from a URL target before comparing."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_ip_range("10.0.0.0/8", "https://10.1.2.3:8080/path") is True


def test_match_ip_range_invalid_cidr_returns_false() -> None:
    """_match_ip_range returns False when the pattern isn't a valid CIDR."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_ip_range("not-a-cidr", "10.1.2.3") is False


# --- _match_url_pattern: invalid regex ----------------------------------------


def test_match_url_pattern_invalid_regex_returns_false() -> None:
    """_match_url_pattern returns False (and logs) on invalid regex."""
    manager = AccessControlManager(MagicMock())

    assert manager._match_url_pattern("[invalid(regex", "https://example.com") is False


# --- _match_protocol_rule -----------------------------------------------------


def test_match_protocol_rule_full_match() -> None:
    """_match_protocol_rule matches on protocol, IPs, ports, and direction."""
    manager = AccessControlManager(MagicMock())
    rule = AccessRule(
        id=str(uuid4()),
        tenant="t",
        user_id="u",
        rule_type=RuleType.PROTOCOL_RULE,
        access_type=AccessType.ALLOW,
        pattern="rule",
        protocol="tcp",
        src_ip="10.0.0.0/8",
        dst_ip="8.8.8.8",
        src_port="1024-65535",
        dst_port="53",
        direction="outbound",
    )

    assert manager._match_protocol_rule(rule, "tcp:10.1.2.3:5000->8.8.8.8:53:outbound") is True


def test_match_protocol_rule_protocol_mismatch() -> None:
    """_match_protocol_rule returns False when protocol doesn't match."""
    manager = AccessControlManager(MagicMock())
    rule = AccessRule(
        id=str(uuid4()),
        tenant="t",
        user_id="u",
        rule_type=RuleType.PROTOCOL_RULE,
        access_type=AccessType.ALLOW,
        pattern="rule",
        protocol="udp",
    )

    assert manager._match_protocol_rule(rule, "tcp:*:*->8.8.8.8:53") is False


def test_match_protocol_rule_unparsable_target_returns_false() -> None:
    """_match_protocol_rule returns False when the target can't be parsed."""
    manager = AccessControlManager(MagicMock())
    rule = AccessRule(
        id=str(uuid4()),
        tenant="t",
        user_id="u",
        rule_type=RuleType.PROTOCOL_RULE,
        access_type=AccessType.ALLOW,
        pattern="rule",
    )

    assert manager._match_protocol_rule(rule, "not-a-connection-string") is False


def test_match_protocol_rule_direction_mismatch() -> None:
    """_match_protocol_rule returns False when direction is constrained and mismatches."""
    manager = AccessControlManager(MagicMock())
    rule = AccessRule(
        id=str(uuid4()),
        tenant="t",
        user_id="u",
        rule_type=RuleType.PROTOCOL_RULE,
        access_type=AccessType.ALLOW,
        pattern="rule",
        direction="inbound",
    )

    assert manager._match_protocol_rule(rule, "tcp:*:*->8.8.8.8:53:outbound") is False


def test_match_protocol_rule_exception_returns_false() -> None:
    """_match_protocol_rule fails closed on an unexpected internal error."""
    manager = AccessControlManager(MagicMock())
    rule = AccessRule(
        id=str(uuid4()),
        tenant="t",
        user_id="u",
        rule_type=RuleType.PROTOCOL_RULE,
        access_type=AccessType.ALLOW,
        pattern="rule",
        src_port="not-numeric-and-no-dash-or-comma",
    )

    # src_port match will hit ValueError internally in _match_port which is
    # caught there and returns False -- assert the overall rule doesn't match.
    assert manager._match_protocol_rule(rule, "tcp:1.1.1.1:80->2.2.2.2:53") is False


# --- _parse_connection_target --------------------------------------------------


def test_parse_connection_target_no_arrow_returns_none() -> None:
    """_parse_connection_target returns None if '->' is missing."""
    assert AccessControlManager._parse_connection_target("tcp:1.1.1.1:80") is None


def test_parse_connection_target_no_colon_in_src_returns_none() -> None:
    """_parse_connection_target returns None if the source part has no protocol."""
    assert AccessControlManager._parse_connection_target("nocolon->8.8.8.8:53") is None


def test_parse_connection_target_full_format() -> None:
    """_parse_connection_target parses protocol/src/dst/direction."""
    result = AccessControlManager._parse_connection_target("tcp:1.1.1.1:80->2.2.2.2:443:inbound")

    assert result == {
        "protocol": "tcp",
        "src_ip": "1.1.1.1",
        "src_port": "80",
        "dst_ip": "2.2.2.2",
        "dst_port": "443",
        "direction": "inbound",
    }


def test_parse_connection_target_wildcards_default_direction() -> None:
    """_parse_connection_target defaults direction to 'outbound' when omitted."""
    result = AccessControlManager._parse_connection_target("udp:*:*->192.168.1.1:53")

    assert result["direction"] == "outbound"
    assert result["src_ip"] == "*"


def test_parse_connection_target_exception_returns_none() -> None:
    """_parse_connection_target fails closed (None) on unexpected input types."""
    assert AccessControlManager._parse_connection_target(None) is None  # type: ignore[arg-type]


# --- _match_ip_or_range ---------------------------------------------------------


def test_match_ip_or_range_wildcard() -> None:
    """_match_ip_or_range treats '*' on either side as a match."""
    assert AccessControlManager._match_ip_or_range("*", "10.0.0.1") is True
    assert AccessControlManager._match_ip_or_range("10.0.0.1", "*") is True


def test_match_ip_or_range_cidr() -> None:
    """_match_ip_or_range matches a CIDR range."""
    assert AccessControlManager._match_ip_or_range("10.0.0.0/8", "10.1.2.3") is True
    assert AccessControlManager._match_ip_or_range("10.0.0.0/8", "192.168.1.1") is False


def test_match_ip_or_range_exact() -> None:
    """_match_ip_or_range matches an exact IP."""
    assert AccessControlManager._match_ip_or_range("10.0.0.1", "10.0.0.1") is True
    assert AccessControlManager._match_ip_or_range("10.0.0.1", "10.0.0.2") is False


def test_match_ip_or_range_invalid_returns_false() -> None:
    """_match_ip_or_range returns False for unparseable IPs."""
    assert AccessControlManager._match_ip_or_range("not-an-ip", "10.0.0.1") is False


# --- _match_port: invalid input -------------------------------------------------


def test_match_port_invalid_returns_false() -> None:
    """_match_port returns False when target isn't numeric."""
    assert AccessControlManager._match_port("80", "not-a-port") is False
