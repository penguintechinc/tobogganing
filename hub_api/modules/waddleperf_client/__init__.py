"""WaddlePerf client module - test schedule/config distribution + version check."""
from __future__ import annotations

from hub_api.modules.waddleperf_client.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the waddleperf_client module.

    Returns:
        ModuleContract with WaddlePerf client blueprints, feature flags,
        and entitlements.
    """
    return ModuleContract(
        name="waddleperf_client",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Schedules", "/api/v1/waddleperf_client/schedules", "calendar"),
            NavEntry("Config", "/api/v1/waddleperf_client/config", "settings"),
            NavEntry("Version", "/api/v1/waddleperf_client/version", "info"),
        ],
        flags=[
            "tobogganing.waddleperf_client.schedules",
            "tobogganing.waddleperf_client.config",
            "tobogganing.waddleperf_client.version",
        ],
        entitlements=[
            Entitlement("waddleperf_client.schedules", "community"),
            Entitlement("waddleperf_client.config", "community"),
            Entitlement("waddleperf_client.version", "community"),
        ],
        migrations=["0013"],
        health=None,
    )
