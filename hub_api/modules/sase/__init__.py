"""SASE module - Security inspection and context-based authentication."""
from __future__ import annotations

from hub_api.modules.sase.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the SASE module.

    Returns:
        ModuleContract with SASE security blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    return ModuleContract(
        name="sase",
        blueprints=list(blueprints),
        nav=[NavEntry("Security", "/api/v1/sase/security", "shield")],
        flags=[
            "tobogganing.sase.threat_feeds",
            "tobogganing.sase.scanner",
            "tobogganing.sase.protection",
            "tobogganing.sase.context_auth",
        ],
        entitlements=[
            Entitlement("sase.threat_feeds", "community"),
            Entitlement("sase.scanner", "community"),
            Entitlement("sase.protection", "community"),
            Entitlement("sase.context_auth", "professional"),
        ],
        migrations=["0006", "0008"],
        health=None,
    )
