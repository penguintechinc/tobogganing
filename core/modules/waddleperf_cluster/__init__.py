"""WaddlePerf cluster module - network performance testing control plane.

Scaffold: the full ModuleContract (blueprints, flags, entitlements, nav,
migrations, health) is wired in Phase 3a Group E. Until then this returns an
empty contract so the package imports cleanly without registering routes.
"""
from __future__ import annotations

from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the waddleperf_cluster module.

    Returns:
        ModuleContract with empty lists during scaffold phase.
    """
    return ModuleContract(
        name="waddleperf_cluster",
        blueprints=[],
        nav=[],
        flags=[],
        entitlements=[],
        migrations=[],
        health=None,
    )
