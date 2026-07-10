"""WaddlePerf cluster module - network performance testing control plane."""
from __future__ import annotations

from core.modules.waddleperf_cluster.api import blueprints
from core.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the waddleperf_cluster module.

    Returns:
        ModuleContract with WaddlePerf cluster blueprints, feature flags,
        entitlements, and navigation entries.
    """
    return ModuleContract(
        name="waddleperf_cluster",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Org Units", "/api/v1/waddleperf_cluster/org-units", "organization"),
            NavEntry("Devices", "/api/v1/waddleperf_cluster/devices", "laptop"),
            NavEntry("Tests", "/api/v1/waddleperf_cluster/tests", "activity"),
            NavEntry("Stats", "/api/v1/waddleperf_cluster/stats", "bar-chart-2"),
        ],
        flags=[
            "tobogganing.waddleperf_cluster.org_units",
            "tobogganing.waddleperf_cluster.devices",
            "tobogganing.waddleperf_cluster.enrollment",
            "tobogganing.waddleperf_cluster.tests",
            "tobogganing.waddleperf_cluster.stats",
            "tobogganing.waddleperf_cluster.live_test",
            "tobogganing.waddleperf_cluster.large_fleet",
        ],
        entitlements=[
            Entitlement("waddleperf_cluster.org_units", "community"),
            Entitlement("waddleperf_cluster.devices", "community"),
            Entitlement("waddleperf_cluster.enrollment", "community"),
            Entitlement("waddleperf_cluster.tests", "community"),
            Entitlement("waddleperf_cluster.stats", "community"),
            Entitlement("waddleperf_cluster.live_test", "community"),
            Entitlement("waddleperf_cluster.large_fleet", "professional"),
        ],
        migrations=["0010", "0011", "0012"],
        health=None,
    )
