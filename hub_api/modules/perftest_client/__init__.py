"""WaddlePerf client module - test schedule/config distribution + version check."""
from __future__ import annotations

from hub_api.modules.perftest_client.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the perftest_client module.

    Returns:
        ModuleContract with WaddlePerf client blueprints, feature flags,
        and entitlements.
    """
    return ModuleContract(
        name="perftest_client",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Schedules", "/api/v1/perftest_client/schedules", "calendar"),
            NavEntry("Config", "/api/v1/perftest_client/config", "settings"),
            NavEntry("Version", "/api/v1/perftest_client/version", "info"),
        ],
        flags=[
            "tobogganing.perftest_client.schedules",
            "tobogganing.perftest_client.config",
            "tobogganing.perftest_client.version",
        ],
        entitlements=[
            Entitlement("perftest_client.schedules", "community"),
            Entitlement("perftest_client.config", "community"),
            Entitlement("perftest_client.version", "community"),
        ],
        migrations=["0013"],
        health=None,
    )
