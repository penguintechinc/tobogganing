"""SASE module - Security inspection and context-based authentication."""
from __future__ import annotations

from hub_api.modules.sase.api import blueprints
from hub_api.modules.sase.security.blocklist.api import blueprint as blocklist_blueprint
from hub_api.modules.sase.security.swg.api import blueprint as swg_blueprint
from hub_api.registry import Entitlement, ModuleContract, NavEntry
from hub_api.modules.sase.security.swg.scheduler import register_swg_jobs


def module() -> ModuleContract:
    """Return the module contract for the SASE module.

    Returns:
        ModuleContract with SASE security blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    # Combine existing blueprints with blocklist and SWG blueprints
    all_blueprints = list(blueprints) + [blocklist_blueprint, swg_blueprint]

    # Register SWG scheduled jobs
    register_swg_jobs()

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
            "tobogganing.sase.swg",
            "tobogganing.sase.swg_ai_categorizer",  # Slice E: AI Tier-2 (professional)
        ],
        entitlements=[
            Entitlement("sase.threat_feeds", "community"),
            Entitlement("sase.scanner", "community"),
            Entitlement("sase.protection", "community"),
            Entitlement("sase.context_auth", "professional"),
            Entitlement("sase.blocklist", "community"),
            Entitlement("sase.adapters", "community"),
            Entitlement("sase.swg", "community"),
            Entitlement("sase.swg_ai_categorizer", "professional"),  # Slice E: AI Tier-2
        ],
        migrations=["0006", "0008", "0021", "0022"],
        health=None,
    )
