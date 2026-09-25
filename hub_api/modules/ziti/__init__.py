"""Ziti module - Identity and access control scaffold for OpenZiti integration."""
from __future__ import annotations

from hub_api.modules.ziti.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the ziti module.

    Provides OpenZiti control-plane and SDK integration scaffolding, functioning
    as an alternative identity/transport layer alongside or independent of sdwan.

    Returns:
        ModuleContract with ziti blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    return ModuleContract(
        name="ziti",
        blueprints=list(blueprints),
        nav=[NavEntry("Identity", "/api/v1/ziti", "shield")],
        flags=[
            "tobogganing.ziti.control_plane",
            "tobogganing.ziti.sdk_integration",
        ],
        entitlements=[
            Entitlement("ziti.control_plane", "professional"),
            Entitlement("ziti.sdk_integration", "enterprise"),
        ],
        migrations=[],
        health=None,
    )
