"""SASE module - Security and Access Service Edge control plane."""
from __future__ import annotations

from hub_api.modules.sase.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the SASE module.

    Returns:
        ModuleContract with SASE blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    return ModuleContract(
        name="sase",
        blueprints=list(blueprints),
        nav=[],
        flags=[
            "tobogganing.sase.certs",
            "tobogganing.sase.auth",
        ],
        entitlements=[
            Entitlement("sase.certs", "community"),
            Entitlement("sase.auth", "community"),
        ],
        migrations=["0005", "0006", "0008"],
        health=None,
    )
