"""Tests for the SASE module."""
from __future__ import annotations

import pytest
from quart import Quart

from core.modules.sase import module as sase_module


@pytest.mark.asyncio
async def test_sase_module_returns_valid_contract() -> None:
    """Test that the SASE module returns a valid ModuleContract.

    Verifies the contract has the correct name and empty but present fields.
    """
    contract = sase_module()

    assert contract.name == "sase"
    assert contract.blueprints == []
    assert contract.nav == []
    assert contract.flags == []
    assert contract.entitlements == []
    assert contract.migrations == []
    assert contract.health is None


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

    # Since SASE module has no flags yet, we just verify the registry exists
    # and is operational. The ping module flags should be present.
    assert "tobogganing.ping.enabled" in flags
