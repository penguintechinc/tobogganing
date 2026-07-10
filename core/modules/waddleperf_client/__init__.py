"""WaddlePerf client module - test schedule/config distribution + version check.

Scaffold: the full ModuleContract is wired in Phase 3b Group B2. Until then
this returns an empty contract so the package imports cleanly.
"""
from __future__ import annotations

from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the waddleperf_client module.

    Returns:
        ModuleContract with empty lists during scaffold phase.
    """
    return ModuleContract(
        name="waddleperf_client",
        blueprints=[],
        nav=[],
        flags=[],
        entitlements=[],
        migrations=[],
        health=None,
    )
