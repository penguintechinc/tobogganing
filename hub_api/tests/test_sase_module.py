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
    assert len(contract.blueprints) == 2  # certs and jwt only
    assert len(contract.nav) == 0  # transport nav moved to sdwan
    assert len(contract.flags) == 2  # certs and auth only
    assert len(contract.entitlements) == 2  # certs and auth only
    assert len(contract.migrations) == 3  # 0005, 0006, 0008 (user fields, per-tenant-unique, security tables)
    assert contract.health is None

    # Verify blueprint names
    blueprint_names = {bp.name for bp in contract.blueprints}
    expected_names = {
        "sase_certs",
        "sase_jwt",
    }
    assert blueprint_names == expected_names

    # Verify flags include SASE features (auth and certs only)
    expected_flags = {
        "tobogganing.sase.certs",
        "tobogganing.sase.auth",
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

    # Verify both ping and SASE module flags are present
    assert "tobogganing.ping.enabled" in flags
    assert "tobogganing.sase.certs" in flags
    assert "tobogganing.sase.auth" in flags
    # Transport flags moved to sdwan
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

    # Register SASE module
    sase_contract = sase_module()
    app.registry.register(sase_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=None, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    # Collect all registered routes from the app's URL map
    routes = {str(rule.rule) for rule in app.url_map.iter_rules()}

    # Expected SASE routes (auth/certs only; transport moved to sdwan)
    expected_routes = {
        "/api/v1/sase/certs/certificates",  # POST
        "/api/v1/sase/jwt/token",  # POST
        "/api/v1/sase/jwt/refresh",  # POST
        "/api/v1/sase/jwt/validate",  # POST
        "/api/v1/sase/jwt/revoke",  # POST
        "/api/v1/sase/jwt/public-key",  # GET
    }

    # Verify all expected routes exist
    for expected_route in expected_routes:
        assert (
            expected_route in routes
        ), f"Expected route {expected_route} not found in app routes.\nAvailable routes: {sorted(routes)}"
