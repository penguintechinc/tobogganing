"""SASE module - Security and Access Service Edge control plane."""
from __future__ import annotations

from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the SASE module.

    Returns:
        ModuleContract with empty blueprint/nav/flags/entitlements lists
        and no health check (scaffold phase).
    """
    return ModuleContract(
        name="sase",
        blueprints=[],
        nav=[],
        flags=[],
        entitlements=[],
        migrations=[],
        health=None,
    )
