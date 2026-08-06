"""SASE module - Security inspection and context-based authentication."""
from __future__ import annotations

from hub_api.modules.sase.api import blueprints
from hub_api.modules.sase.security.blocklist.api import blueprint as blocklist_blueprint
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the SASE module.

    Returns:
        ModuleContract with SASE security blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    # Combine existing blueprints with blocklist blueprint
    all_blueprints = list(blueprints) + [blocklist_blueprint]

    return ModuleContract(
        name="sase",
        blueprints=all_blueprints,
        nav=[NavEntry("Security", "/api/v1/sase/security", "shield")],
        flags=[
            "tobogganing.sase.threat_feeds",
            "tobogganing.sase.scanner",
            "tobogganing.sase.protection",
            "tobogganing.sase.context_auth",
            "tobogganing.sase.blocklist",
            "tobogganing.sase.adapters",
        ],
        entitlements=[
            Entitlement("sase.threat_feeds", "community"),
            Entitlement("sase.scanner", "community"),
            Entitlement("sase.protection", "community"),
            Entitlement("sase.context_auth", "professional"),
            Entitlement("sase.blocklist", "community"),
            Entitlement("sase.adapters", "community"),
        ],
        migrations=["0006", "0008"],
        health=None,
    )
