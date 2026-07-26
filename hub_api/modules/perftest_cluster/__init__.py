"""WaddlePerf cluster module - network performance testing control plane."""
from __future__ import annotations

from hub_api.modules.perftest_cluster.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry
from hub_api.scheduler.registry import register_job_handler


def module() -> ModuleContract:
    """Return the module contract for the perftest_cluster module.

    Returns:
        ModuleContract with WaddlePerf cluster blueprints, feature flags,
        entitlements, and navigation entries.
    """
    contract = ModuleContract(
        name="perftest_cluster",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Org Units", "/api/v1/perftest_cluster/org-units", "organization"),
            NavEntry("Devices", "/api/v1/perftest_cluster/devices", "laptop"),
            NavEntry("Tests", "/api/v1/perftest_cluster/tests", "activity"),
            NavEntry("Stats", "/api/v1/perftest_cluster/stats", "bar-chart-2"),
            NavEntry("Alerts", "/api/v1/perftest_cluster/alerts", "bell"),
            NavEntry("Scheduled Tests", "/api/v1/perftest_cluster/scheduled-tests", "clock"),
            NavEntry("AutoPerf", "/api/v1/perftest_cluster/autoperf", "zap"),
            NavEntry("Live Test", "/api/v1/perftest_cluster/live-test", "radio"),
        ],
        flags=[
            "tobogganing.perftest_cluster.org_units",
            "tobogganing.perftest_cluster.devices",
            "tobogganing.perftest_cluster.enrollment",
            "tobogganing.perftest_cluster.tests",
            "tobogganing.perftest_cluster.stats",
            "tobogganing.perftest_cluster.live_test",
            "tobogganing.perftest_cluster.large_fleet",
            "tobogganing.perftest_cluster.scheduled_tests",
            "tobogganing.perftest_cluster.alerts",
            "tobogganing.perftest_cluster.alert_routing",
            "tobogganing.perftest_cluster.autoperf",
        ],
        entitlements=[
            Entitlement("perftest_cluster.org_units", "community"),
            Entitlement("perftest_cluster.devices", "community"),
            Entitlement("perftest_cluster.enrollment", "community"),
            Entitlement("perftest_cluster.tests", "community"),
            Entitlement("perftest_cluster.stats", "community"),
            Entitlement("perftest_cluster.live_test", "community"),
            Entitlement("perftest_cluster.large_fleet", "professional"),
            Entitlement("perftest_cluster.scheduled_tests", "community"),
            Entitlement("perftest_cluster.alerts", "community"),
            Entitlement("perftest_cluster.alert_routing", "professional"),
            Entitlement("perftest_cluster.autoperf", "professional"),
        ],
        migrations=["0010", "0011", "0012"],
        health=None,
    )

    # Register handler for scheduled server tests
    register_job_handler(
        "perftest_cluster",
        "server_test",
        "hub_api.modules.perftest_cluster.worker.tasks.run_server_test",
    )

    # Register handler for alert sweep
    register_job_handler(
        "perftest_cluster",
        "alert_sweep",
        "hub_api.modules.perftest_cluster.worker.tasks.alert_sweep",
    )

    # Register handler for autoperf cycle
    register_job_handler(
        "perftest_cluster",
        "autoperf_cycle",
        "hub_api.modules.perftest_cluster.worker.tasks.autoperf_cycle",
    )

    return contract
