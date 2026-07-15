"""SASE module - Security and Access Service Edge control plane."""
from __future__ import annotations

from core.modules.sase.api import blueprints
from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the SASE module.

    Returns:
        ModuleContract with SASE blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    return ModuleContract(
        name="sase",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Clusters", "/api/v1/sase/clusters", "server"),
            NavEntry("Clients", "/api/v1/sase/clients", "laptop"),
            NavEntry("Status", "/api/v1/sase/status", "activity"),
        ],
        flags=[
            "tobogganing.sase.clusters",
            "tobogganing.sase.clients",
            "tobogganing.sase.status",
            "tobogganing.sase.certs",
            "tobogganing.sase.auth",
            "tobogganing.sase.wireguard",
            "tobogganing.sase.large_cluster",
        ],
        entitlements=[
            Entitlement("sase.clusters", "community"),
            Entitlement("sase.clients", "community"),
            Entitlement("sase.status", "community"),
            Entitlement("sase.certs", "community"),
            Entitlement("sase.auth", "community"),
            Entitlement("sase.wireguard", "community"),
            Entitlement("sase.large_cluster", "professional"),
        ],
        migrations=["0002", "0003", "0004", "0005", "0006", "0007", "0008"],
        health=None,
    )
