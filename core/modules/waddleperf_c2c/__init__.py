"""WaddlePerf cluster2cluster module - node/region-to-region perf testing.

Scaffold: the full ModuleContract is wired in Phase 4 Group E. Until then
this returns an empty contract so the package imports cleanly.
"""
from __future__ import annotations

from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the waddleperf_c2c module.

    Returns:
        ModuleContract with empty lists during scaffold phase.
    """
    return ModuleContract(
        name="waddleperf_c2c",
        blueprints=[],
        nav=[],
        flags=[],
        entitlements=[],
        migrations=[],
        health=None,
    )
