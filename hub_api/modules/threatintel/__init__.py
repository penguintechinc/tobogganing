"""Threat-intel shared module — feeds + blocklist consumed by sase and (future) netsvcs."""
from __future__ import annotations

from hub_api.modules.threatintel.blocklist.api import blueprint as blocklist_blueprint
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the shared threat-intel module.

    Returns:
        ModuleContract exposing the blocklist blueprint plus threatintel flags.
    """
    return ModuleContract(
        name="threatintel",
        blueprints=[blocklist_blueprint],
        nav=[NavEntry("Threat Intel", "/api/v1/threatintel", "shield-alert")],
        flags=[
            "tobogganing.threatintel.blocklist",
            "tobogganing.threatintel.feeds",
        ],
        entitlements=[
            Entitlement("threatintel.blocklist", "community"),
            Entitlement("threatintel.feeds", "community"),
        ],
        migrations=["0008"],
        health=None,
    )
