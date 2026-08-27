"""Threat-intel shared module — feeds + blocklist consumed by sase and (future) netsvcs."""

from __future__ import annotations

from hub_api.modules.threatintel.blocklist.api import blueprint as blocklist_blueprint
from hub_api.modules.threatintel.feeds.api import feeds_bp
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the shared threat-intel module.

    Returns:
        ModuleContract exposing the blocklist + feeds blueprints plus
        threatintel flags.
    """
    return ModuleContract(
        name="threatintel",
        blueprints=[blocklist_blueprint, feeds_bp],
        nav=[
            NavEntry("Feeds", "/api/v1/threatintel/feeds", "rss"),
            NavEntry("Blocklist", "/api/v1/threatintel/blocklist", "shield-alert"),
            NavEntry("IOC Check", "/api/v1/threatintel/blocklist/check", "search"),
        ],
        flags=[
            "tobogganing.threatintel.blocklist",
            "tobogganing.threatintel.feeds",
        ],
        entitlements=[
            Entitlement("threatintel.blocklist", "community"),
            Entitlement("threatintel.feeds", "community"),
        ],
        migrations=["0008", "0026"],
        health=None,
    )
