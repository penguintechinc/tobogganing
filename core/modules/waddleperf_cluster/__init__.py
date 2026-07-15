"""WaddlePerf cluster module - network performance testing control plane."""
from __future__ import annotations

from core.modules.waddleperf_cluster.api import blueprints
from core.registry import Entitlement, ModuleContract, NavEntry
from core.scheduler.registry import register_job_handler


def module() -> ModuleContract:
    """Return the module contract for the waddleperf_cluster module.

    Returns:
        ModuleContract with WaddlePerf cluster blueprints, feature flags,
        entitlements, and navigation entries.
    """
    contract = ModuleContract(
        name="waddleperf_cluster",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Org Units", "/api/v1/waddleperf_cluster/org-units", "organization"),
            NavEntry("Devices", "/api/v1/waddleperf_cluster/devices", "laptop"),
            NavEntry("Tests", "/api/v1/waddleperf_cluster/tests", "activity"),
            NavEntry("Stats", "/api/v1/waddleperf_cluster/stats", "bar-chart-2"),
            NavEntry("Alerts", "/api/v1/waddleperf_cluster/alerts", "bell"),
            NavEntry("Scheduled Tests", "/api/v1/waddleperf_cluster/scheduled-tests", "clock"),
            NavEntry("AutoPerf", "/api/v1/waddleperf_cluster/autoperf", "zap"),
            NavEntry("Live Test", "/api/v1/waddleperf_cluster/live-test", "radio"),
        ],
        flags=[
            "tobogganing.waddleperf_cluster.org_units",
            "tobogganing.waddleperf_cluster.devices",
            "tobogganing.waddleperf_cluster.enrollment",
            "tobogganing.waddleperf_cluster.tests",
            "tobogganing.waddleperf_cluster.stats",
            "tobogganing.waddleperf_cluster.live_test",
            "tobogganing.waddleperf_cluster.large_fleet",
            "tobogganing.waddleperf_cluster.scheduled_tests",
            "tobogganing.waddleperf_cluster.alerts",
            "tobogganing.waddleperf_cluster.alert_routing",
            "tobogganing.waddleperf_cluster.autoperf",
        ],
        entitlements=[
            Entitlement("waddleperf_cluster.org_units", "community"),
            Entitlement("waddleperf_cluster.devices", "community"),
            Entitlement("waddleperf_cluster.enrollment", "community"),
            Entitlement("waddleperf_cluster.tests", "community"),
            Entitlement("waddleperf_cluster.stats", "community"),
            Entitlement("waddleperf_cluster.live_test", "community"),
            Entitlement("waddleperf_cluster.large_fleet", "professional"),
            Entitlement("waddleperf_cluster.scheduled_tests", "community"),
            Entitlement("waddleperf_cluster.alerts", "community"),
            Entitlement("waddleperf_cluster.alert_routing", "professional"),
            Entitlement("waddleperf_cluster.autoperf", "professional"),
        ],
        migrations=["0010", "0011", "0012"],
        health=None,
    )

    # Register handler for scheduled server tests
    register_job_handler(
        "waddleperf_cluster",
        "server_test",
        "core.modules.waddleperf_cluster.worker.tasks.run_server_test",
    )

    # Register handler for alert sweep
    register_job_handler(
        "waddleperf_cluster",
        "alert_sweep",
        "core.modules.waddleperf_cluster.worker.tasks.alert_sweep",
    )

    # Register handler for autoperf cycle
    register_job_handler(
        "waddleperf_cluster",
        "autoperf_cycle",
        "core.modules.waddleperf_cluster.worker.tasks.autoperf_cycle",
    )

    return contract
