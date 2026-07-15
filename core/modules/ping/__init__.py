"""Ping module - trivial demo proving the registry/flag/entitlement contract."""
from __future__ import annotations

from core.modules.ping.routes import blueprint
from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the ping module.

    Returns:
        ModuleContract with blueprint, nav, flags, and entitlements.
    """
    return ModuleContract(
        name="ping",
        blueprints=[blueprint],
        nav=[NavEntry(label="Ping", path="/api/v1/ping", icon="activity")],
        flags=[
            "tobogganing.ping.enabled",
            "tobogganing.ping.pro",
        ],
        entitlements=[
            Entitlement(feature="ping.pro", tier="professional"),
        ],
        migrations=[],
        health=None,
    )
