"""Tests for the threatintel shared module."""

from __future__ import annotations

import pytest
from quart import Quart

from hub_api.modules.threatintel import module as threatintel_module


@pytest.mark.asyncio
async def test_threatintel_module_returns_valid_contract() -> None:
    """Test that the threatintel module returns a valid ModuleContract.

    Verifies the contract has the correct name, blueprints, flags, entitlements, and migrations.
    """
    contract = threatintel_module()

    assert contract.name == "threatintel"
    assert len(contract.blueprints) == 2  # blocklist + feeds blueprints
    assert len(contract.nav) == 3  # Feeds, Blocklist, IOC Check
    assert len(contract.flags) == 2  # blocklist, feeds
    assert len(contract.entitlements) == 2  # same set, per-entitlement
    assert len(contract.migrations) == 2  # 0008 (sase scanner/protection) + 0026 (feed sources)
    assert contract.health is None

    # Verify blocklist + feeds blueprints are present
    blueprint_names = {bp.name for bp in contract.blueprints}
    assert "sase_blocklist" in blueprint_names
    assert "threatintel_feeds" in blueprint_names

    # Verify nav entries
    nav_labels = {n.label for n in contract.nav}
    assert nav_labels == {"Feeds", "Blocklist", "IOC Check"}

    # Verify flags match expectations
    expected_flags = {
        "tobogganing.threatintel.blocklist",
        "tobogganing.threatintel.feeds",
    }
    assert set(contract.flags) == expected_flags

    # Verify entitlements
    expected_entitlements = {
        ("threatintel.blocklist", "community"),
        ("threatintel.feeds", "community"),
    }
    actual_entitlements = {(e.feature, e.tier) for e in contract.entitlements}
    assert actual_entitlements == expected_entitlements


@pytest.mark.asyncio
async def test_threatintel_blocklist_route_registered() -> None:
    """Test that the blocklist route is registered at the correct URL under threatintel.

    Verifies the URL map contains /api/v1/threatintel/blocklist/check.
    """
    from unittest.mock import MagicMock

    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext, ModuleRegistry

    app = Quart(__name__)
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    mock_db = MagicMock()
    app.registry = ModuleRegistry()

    # Register threatintel module
    threatintel_contract = threatintel_module()
    app.registry.register(threatintel_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=None, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    # Collect all registered routes from the app's URL map
    routes = {str(rule.rule) for rule in app.url_map.iter_rules()}

    # Verify threatintel blocklist route is registered
    threatintel_routes = [r for r in routes if "/api/v1/threatintel" in r]
    assert (
        len(threatintel_routes) >= 1
    ), f"Threatintel should have blocklist route, found: {threatintel_routes}"
    assert (
        "/api/v1/threatintel/blocklist/check" in routes
    ), "Blocklist check route should be registered under threatintel"
