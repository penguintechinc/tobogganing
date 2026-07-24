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
    assert len(contract.blueprints) == 6
    assert len(contract.nav) == 3
    assert len(contract.flags) == 7
    assert len(contract.entitlements) == 7
    assert len(contract.migrations) == 7
    assert contract.health is None

    # Verify blueprint names
    blueprint_names = {bp.name for bp in contract.blueprints}
    expected_names = {
        "sase_clusters",
        "sase_clients",
        "sase_status",
        "sase_certs",
        "sase_jwt",
        "sase_wireguard",
    }
    assert blueprint_names == expected_names

    # Verify flags include SASE features
    expected_flags = {
        "tobogganing.sase.clusters",
        "tobogganing.sase.clients",
        "tobogganing.sase.status",
        "tobogganing.sase.certs",
        "tobogganing.sase.auth",
        "tobogganing.sase.wireguard",
        "tobogganing.sase.large_cluster",
    }
    assert set(contract.flags) == expected_flags

    # Verify nav entries
    nav_paths = {entry.path for entry in contract.nav}
    assert "/api/v1/sase/clusters" in nav_paths
    assert "/api/v1/sase/clients" in nav_paths
    assert "/api/v1/sase/status" in nav_paths


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
    assert "tobogganing.sase.clusters" in flags
    assert "tobogganing.sase.clients" in flags
    assert "tobogganing.sase.status" in flags
    assert "tobogganing.sase.certs" in flags
    assert "tobogganing.sase.auth" in flags
    assert "tobogganing.sase.wireguard" in flags
    assert "tobogganing.sase.large_cluster" in flags


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

    # Expected SASE routes based on the specification
    expected_routes = {
        "/api/v1/sase/clusters",  # POST, GET
        "/api/v1/sase/clusters/<cluster_id>/heartbeat",  # POST
        "/api/v1/sase/clusters/<cluster_id>/headend-config",  # GET
        "/api/v1/sase/clients",  # POST, GET
        "/api/v1/sase/clients/<client_id>/config",  # GET
        "/api/v1/sase/clients/<client_id>/tunnel-config",  # PUT
        "/api/v1/sase/clients/<client_id>/rotate-key",  # POST
        "/api/v1/sase/clients/<client_id>/metrics",  # POST
        "/api/v1/sase/clients/headends/<headend_id>/metrics",  # POST
        "/api/v1/sase/status",  # GET
        "/api/v1/sase/certs/certificates",  # POST
        "/api/v1/sase/jwt/token",  # POST
        "/api/v1/sase/jwt/refresh",  # POST
        "/api/v1/sase/jwt/validate",  # POST
        "/api/v1/sase/jwt/revoke",  # POST
        "/api/v1/sase/jwt/public-key",  # GET
        "/api/v1/sase/wireguard/keys",  # POST
        "/api/v1/sase/wireguard/peers",  # GET
        "/api/v1/sase/wireguard/keys/<node_id>",  # DELETE
    }

    # Verify all expected routes exist
    for expected_route in expected_routes:
        assert (
            expected_route in routes
        ), f"Expected route {expected_route} not found in app routes.\nAvailable routes: {sorted(routes)}"
