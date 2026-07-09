"""Tests for the module registry and contract."""
from __future__ import annotations

import pytest
from quart import Blueprint, jsonify

from core.app import create_app
from core.registry import Entitlement, ModuleContext, ModuleContract, ModuleRegistry, NavEntry


@pytest.fixture
def registry() -> ModuleRegistry:
    """Create a fresh ModuleRegistry for testing."""
    return ModuleRegistry()


@pytest.fixture
def fake_blueprint() -> Blueprint:
    """Create a fake blueprint for testing."""
    bp = Blueprint("fake", __name__)

    @bp.route("/test", methods=["GET"])
    async def fake_route() -> tuple[dict[str, bool], int]:
        """Fake test route."""
        return {"success": True}, 200

    return bp


@pytest.fixture
def fake_contract(fake_blueprint: Blueprint) -> ModuleContract:
    """Create a fake ModuleContract for testing."""
    return ModuleContract(
        name="fake",
        blueprints=[fake_blueprint],
        nav=[NavEntry(label="Fake Module", path="/fake", icon="star")],
        flags=["tobogganing.fake.thing"],
        entitlements=[Entitlement(feature="tobogganing.fake.advanced", tier="professional")],
        migrations=[],
        health=None,
    )


@pytest.mark.asyncio
async def test_registry_register(registry: ModuleRegistry, fake_contract: ModuleContract) -> None:
    """Test that a module contract can be registered."""
    registry.register(fake_contract)
    assert registry.declared_flags() == ["tobogganing.fake.thing"]


@pytest.mark.asyncio
async def test_registry_apply_to_mounts_blueprints(
    registry: ModuleRegistry, fake_contract: ModuleContract
) -> None:
    """Test that apply_to mounts registered blueprints under versioned API paths."""
    app = create_app()
    registry.register(fake_contract)

    # Create a minimal context (mocked objects are fine for this test)
    ctx = ModuleContext(config={}, db={}, key_provider={})

    # Apply registry to app
    registry.apply_to(app, ctx)

    # Test that the route is mounted under /api/v1/fake/test
    client = app.test_client()
    response = await client.get("/api/v1/fake/test")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_registry_declared_flags(registry: ModuleRegistry, fake_contract: ModuleContract) -> None:
    """Test that declared_flags returns all registered flags."""
    registry.register(fake_contract)
    flags = registry.declared_flags()
    assert "tobogganing.fake.thing" in flags
    assert len(flags) == 1


@pytest.mark.asyncio
async def test_registry_nav_manifest(registry: ModuleRegistry, fake_contract: ModuleContract) -> None:
    """Test that nav_manifest returns navigation entries from all modules."""
    registry.register(fake_contract)
    nav = registry.nav_manifest()
    assert len(nav) == 1
    assert nav[0].label == "Fake Module"
    assert nav[0].path == "/fake"
    assert nav[0].icon == "star"


@pytest.mark.asyncio
async def test_registry_entitlement_for(registry: ModuleRegistry, fake_contract: ModuleContract) -> None:
    """Test that entitlement_for returns the correct entitlement."""
    registry.register(fake_contract)
    entitlement = registry.entitlement_for("tobogganing.fake.advanced")
    assert entitlement is not None
    assert entitlement.feature == "tobogganing.fake.advanced"
    assert entitlement.tier == "professional"


@pytest.mark.asyncio
async def test_registry_entitlement_for_missing(registry: ModuleRegistry, fake_contract: ModuleContract) -> None:
    """Test that entitlement_for returns None for missing features."""
    registry.register(fake_contract)
    entitlement = registry.entitlement_for("nonexistent.feature")
    assert entitlement is None
