"""SDWAN transport layer module."""
from __future__ import annotations

from hub_api.modules.sdwan.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the SDWAN module.

    Returns:
        ModuleContract with SDWAN blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    return ModuleContract(
        name="sdwan",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Clusters", "/api/v1/sdwan/clusters", "server"),
            NavEntry("Clients", "/api/v1/sdwan/clients", "laptop"),
            NavEntry("Status", "/api/v1/sdwan/status", "activity"),
        ],
        flags=[
            "tobogganing.sdwan.clusters",
            "tobogganing.sdwan.clients",
            "tobogganing.sdwan.status",
            "tobogganing.sdwan.wireguard",
            "tobogganing.sdwan.large_cluster",
        ],
        entitlements=[
            Entitlement("sdwan.clusters", "community"),
            Entitlement("sdwan.clients", "community"),
            Entitlement("sdwan.status", "community"),
            Entitlement("sdwan.wireguard", "community"),
            Entitlement("sdwan.large_cluster", "professional"),
        ],
        migrations=["0002", "0003", "0004", "0007", "0009"],
        health=None,
    )
