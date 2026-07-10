"""WaddlePerf cluster2cluster module - node/region-to-region perf testing."""
from __future__ import annotations

from core.modules.waddleperf_c2c.api import blueprints
from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the waddleperf_c2c module.

    Returns:
        ModuleContract with c2c blueprints, feature flags, and
        Professional-tier entitlements.
    """
    return ModuleContract(
        name="waddleperf_c2c",
        blueprints=list(blueprints),
        nav=[
            NavEntry("C2C Nodes", "/api/v1/waddleperf_c2c/endpoints", "server"),
            NavEntry("C2C Runs", "/api/v1/waddleperf_c2c/runs", "activity"),
            NavEntry("C2C Matrix", "/api/v1/waddleperf_c2c/matrix", "grid"),
        ],
        flags=[
            "tobogganing.waddleperf_c2c.endpoints",
            "tobogganing.waddleperf_c2c.runs",
            "tobogganing.waddleperf_c2c.matrix",
        ],
        entitlements=[
            Entitlement("waddleperf_c2c.endpoints", "professional"),
            Entitlement("waddleperf_c2c.runs", "professional"),
            Entitlement("waddleperf_c2c.matrix", "professional"),
        ],
        migrations=["0014", "0015"],
        health=None,
    )
