"""Tests for the NetSvcs module."""

from __future__ import annotations

import pytest
from quart import Quart

from hub_api.modules.netsvcs import module as netsvcs_module


@pytest.mark.asyncio
async def test_netsvcs_module_returns_valid_contract() -> None:
    """Test that the NetSvcs module returns a valid ModuleContract.

    Verifies the contract has the correct name, blueprints, flags, and entitlements.
    """
    contract = netsvcs_module()

    assert contract.name == "netsvcs"
    assert len(contract.blueprints) == 3  # zones, dns_servers, analytics blueprints
    assert len(contract.nav) == 3  # Zones, DNS Servers, Analytics nav entries
    assert len(contract.flags) == 6  # dns, zones, dns_servers, analytics, dhcp, ntp
    assert len(contract.entitlements) == 6  # same set, per-entitlement
    assert len(contract.migrations) == 1  # 0025
    assert contract.health is None

    # Verify blueprints are present
    blueprint_names = {bp.name for bp in contract.blueprints}
    assert "netsvcs_zones" in blueprint_names
    assert "netsvcs_dns_servers" in blueprint_names
    assert "netsvcs_analytics" in blueprint_names

    # Verify nav entries (portal sidebar slugs derive from these labels)
    nav_labels = {entry.label for entry in contract.nav}
    assert nav_labels == {"Zones", "DNS Servers", "Analytics"}

    # Verify flags
    expected_flags = {
        "tobogganing.netsvcs.dns",
        "tobogganing.netsvcs.zones",
        "tobogganing.netsvcs.dns_servers",
        "tobogganing.netsvcs.analytics",
        "tobogganing.netsvcs.dhcp",
        "tobogganing.netsvcs.ntp",
    }
    assert set(contract.flags) == expected_flags

    # Verify entitlements all at community tier
    expected_entitlements = {
        "netsvcs.dns",
        "netsvcs.zones",
        "netsvcs.dns_servers",
        "netsvcs.analytics",
        "netsvcs.dhcp",
        "netsvcs.ntp",
    }
    assert {e.feature for e in contract.entitlements} == expected_entitlements
    for ent in contract.entitlements:
        assert ent.tier == "community"

    # Verify migrations
    assert contract.migrations == ["0025"]


@pytest.mark.asyncio
async def test_netsvcs_blueprints_mount_at_correct_urls(app: Quart) -> None:
    """Test that NetSvcs blueprints mount at the expected URL prefixes.

    Args:
        app: Quart test app.
    """
    # Get the module contract
    contract = netsvcs_module()

    # Verify the blueprints are registered (app fixture already does this)
    # Just verify the blueprint naming convention matches what we expect
    blueprint_urls = {
        "netsvcs_zones": "/api/v1/netsvcs/zones",
        "netsvcs_dns_servers": "/api/v1/netsvcs/dns-servers",
        "netsvcs_analytics": "/api/v1/netsvcs/analytics",
    }

    for bp in contract.blueprints:
        assert bp.name in blueprint_urls
        expected_prefix = blueprint_urls[bp.name].replace("/api/v1/netsvcs", "")
        # Verify the blueprint's url_prefix matches expected (for later route mounting)
        assert bp.url_prefix == expected_prefix
