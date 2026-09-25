"""Tests for the SASE module."""
from __future__ import annotations

import pytest
from quart import Quart

from hub_api.modules.sase import module as sase_module


@pytest.mark.asyncio
async def test_sase_module_returns_valid_contract() -> None:
    """Test that the SASE module returns a valid ModuleContract.

    Verifies the contract has the correct name, blueprints, flags, and entitlements.
    """
    contract = sase_module()

    assert contract.name == "sase"
    assert len(contract.blueprints) == 2  # swg + blockpages blueprints (blocklist moved to threatintel)
    assert len(contract.nav) == 1  # Security nav only
    assert len(contract.flags) == 7  # scanner, protection, context_auth, adapters, swg, swg_ai_categorizer, blockpages
    assert len(contract.entitlements) == 7  # same set, per-entitlement
    assert len(contract.migrations) == 6  # 0006, 0008, 0021, 0022, 0023, 0024
    assert contract.health is None

    # Verify swg and blockpages blueprints are present (blocklist is now in threatintel)
    blueprint_names = {bp.name for bp in contract.blueprints}
    assert "sase_swg" in blueprint_names
    assert "sase_blockpages" in blueprint_names

    # Verify flags (threat_feeds and blocklist moved to threatintel module)
    expected_flags = {
        "tobogganing.sase.scanner",
        "tobogganing.sase.protection",
        "tobogganing.sase.context_auth",
        "tobogganing.sase.adapters",
        "tobogganing.sase.swg",
        "tobogganing.sase.swg_ai_categorizer",  # Slice E: AI Tier-2
        "tobogganing.sase.blockpages",  # Slice C: block pages
    }
    assert set(contract.flags) == expected_flags


@pytest.mark.asyncio
async def test_sase_module_registered_in_app(app: Quart) -> None:
    """Test that the SASE module is registered in the app registry.

    Verifies the module is present in the registry's internal modules dict.

    Args:
        app: Test app fixture with both modules pre-registered.
    """
    # The test app fixture should have both ping and sase modules registered
    # Verify by checking that we can get the contract from the registry
    flags = app.registry.declared_flags()

    # Verify both ping and SASE module flags are present (threat_feeds and blocklist moved to threatintel)
    assert "tobogganing.ping.enabled" in flags
    assert "tobogganing.sase.scanner" in flags
    assert "tobogganing.sase.protection" in flags
    assert "tobogganing.sase.context_auth" in flags
    assert "tobogganing.sase.adapters" in flags
    assert "tobogganing.sase.swg" in flags
    assert "tobogganing.sase.blockpages" in flags
    # Transport flags (and cert/jwt auth) moved to sdwan/core respectively
    assert "tobogganing.sdwan.clusters" in flags
    assert "tobogganing.sdwan.clients" in flags
    assert "tobogganing.sdwan.status" in flags
    assert "tobogganing.sdwan.wireguard" in flags
    assert "tobogganing.sdwan.large_cluster" in flags


@pytest.mark.asyncio
async def test_sase_routes_registered_at_correct_urls() -> None:
    """Test that SASE routes are registered at the correct URLs.

    Verifies the URL map contains all expected SASE routes with proper paths.
    Creates a minimal app with SASE module and registry to verify routing.
    Note: cert/jwt endpoints are now core-owned and served from /api/v1/{certs,jwt}
    """
    from unittest.mock import MagicMock

    from hub_api.registry import ModuleContext, ModuleRegistry
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair

    app = Quart(__name__)
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    mock_db = MagicMock()
    app.registry = ModuleRegistry()

    # Register SASE module (now security-only, no cert/jwt blueprints)
    sase_contract = sase_module()
    app.registry.register(sase_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=None, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    # Collect all registered routes from the app's URL map
    routes = {str(rule.rule) for rule in app.url_map.iter_rules()}

    # SASE module no longer registers blocklist (moved to threatintel module)
    # Verify swg and blockpages routes are registered
    sase_routes = [r for r in routes if "/api/v1/sase" in r]
    assert len(sase_routes) >= 1, f"SASE should have swg/blockpages routes, found: {sase_routes}"
    # Blocklist should NOT be under /api/v1/sase (it's now under /api/v1/threatintel)
    assert "/api/v1/sase/blocklist/check" not in routes, "Blocklist route should not be under sase anymore"
