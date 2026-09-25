"""WaddlePerf cluster2cluster module - node/region-to-region perf testing."""
from __future__ import annotations

from hub_api.modules.perftest_c2c.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the perftest_c2c module.

    Returns:
        ModuleContract with c2c blueprints, feature flags, and
        Professional-tier entitlements.
    """
    from hub_api.scheduler.registry import register_job_handler

    # Register job handlers for recurring jobs
    register_job_handler(
        "perftest_c2c",
        "matrix_run",
        "hub_api.modules.perftest_c2c.worker.tasks.start_recurring_run",
    )
    register_job_handler(
        "perftest_c2c",
        "node_health",
        "hub_api.modules.perftest_c2c.worker.tasks.node_health",
    )

    return ModuleContract(
        name="perftest_c2c",
        blueprints=list(blueprints),
        nav=[
            NavEntry("C2C Nodes", "/api/v1/perftest_c2c/endpoints", "server"),
            NavEntry("C2C Runs", "/api/v1/perftest_c2c/runs", "activity"),
            NavEntry("C2C Matrix", "/api/v1/perftest_c2c/matrix", "grid"),
            NavEntry("C2C Recurring", "/api/v1/perftest_c2c/recurring", "clock"),
            NavEntry("C2C Regions", "/api/v1/perftest_c2c/regions", "map"),
        ],
        flags=[
            "tobogganing.perftest.c2c.endpoints",
            "tobogganing.perftest.c2c.runs",
            "tobogganing.perftest.c2c.matrix",
            "tobogganing.perftest.c2c.recurring_runs",
            "tobogganing.perftest.c2c.regions",
        ],
        entitlements=[
            Entitlement("perftest.c2c.endpoints", "professional"),
            Entitlement("perftest.c2c.runs", "professional"),
            Entitlement("perftest.c2c.matrix", "professional"),
            Entitlement("perftest.c2c.recurring_runs", "professional"),
            Entitlement("perftest.c2c.regions", "professional"),
        ],
        migrations=["0014", "0015", "0020"],
        health=None,
    )
