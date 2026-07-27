"""Tests for the ziti module."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from quart import Quart

from hub_api.modules.ziti import module
from hub_api.registry import ModuleContext


@pytest.mark.asyncio
async def test_ziti_module_contract() -> None:
    """Test that the ziti module returns a valid contract.

    Verifies:
    - Module name is 'ziti'
    - Feature flags are declared
    - Entitlements have correct tiers
    """
    contract = module()

    assert contract.name == "ziti"
    assert "tobogganing.ziti.control_plane" in contract.flags
    assert "tobogganing.ziti.sdk_integration" in contract.flags
    assert len(contract.flags) == 2

    # Check entitlements
    feature_tiers = {e.feature: e.tier for e in contract.entitlements}
    assert feature_tiers["ziti.control_plane"] == "professional"
    assert feature_tiers["ziti.sdk_integration"] == "enterprise"
    assert len(contract.entitlements) == 2

    # No migrations for ziti scaffold
    assert contract.migrations == []


@pytest.mark.asyncio
async def test_ziti_module_nav() -> None:
    """Test that the ziti module has correct navigation entries.

    Verifies:
    - Navigation entry label and path
    - Shield icon is set
    """
    contract = module()

    assert len(contract.nav) == 1
    nav_entry = contract.nav[0]
    assert nav_entry.label == "Identity"
    assert nav_entry.path == "/api/v1/ziti"
    assert nav_entry.icon == "shield"


@pytest.mark.asyncio
async def test_ziti_module_registers_in_app(app: Quart, mock_db: MagicMock) -> None:
    """Test that the ziti module can be registered with the app without errors.

    Verifies:
    - Module loads and registers
    - Blueprint mounts successfully
    - App boot succeeds with ziti in modules
    """
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair

    # Set up key provider for module registration
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Apply registry to app (includes ziti module)
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    # Verify ziti flags are declared
    flags = app.registry.declared_flags()
    assert "tobogganing.ziti.control_plane" in flags
    assert "tobogganing.ziti.sdk_integration" in flags


@pytest.mark.asyncio
async def test_ziti_module_health_endpoint() -> None:
    """Test that the ziti health endpoint returns scaffold status.

    Verifies:
    - Endpoint returns 200 OK
    - Response indicates module is in scaffold state
    """
    import asyncio
    from quart import Quart

    app = Quart(__name__)

    # Register just the ziti blueprint for this test
    from hub_api.modules.ziti.api import blueprints

    for bp in blueprints:
        app.register_blueprint(bp)

    client = app.test_client()
    response = await client.get("/api/v1/ziti/health")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "scaffold"
    assert data["module"] == "ziti"
