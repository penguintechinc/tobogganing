"""WaddlePerf cluster API blueprints."""
from __future__ import annotations

from hub_api.modules.perftest_cluster.api.alerts import alerts_bp as alerts_blueprint
from hub_api.modules.perftest_cluster.api.autoperf import autoperf_bp as autoperf_blueprint
from hub_api.modules.perftest_cluster.api.devices import blueprint as devices_blueprint
from hub_api.modules.perftest_cluster.api.enrollment import blueprint as enrollment_blueprint
from hub_api.modules.perftest_cluster.api.live_test import blueprint as live_test_blueprint
from hub_api.modules.perftest_cluster.api.org_units import blueprint as org_units_blueprint
from hub_api.modules.perftest_cluster.api.scheduled_tests import (
    blueprint as scheduled_tests_blueprint,
)
from hub_api.modules.perftest_cluster.api.stats import blueprint as stats_blueprint
from hub_api.modules.perftest_cluster.api.tests import blueprint as tests_blueprint

blueprints = [
    org_units_blueprint,
    devices_blueprint,
    enrollment_blueprint,
    tests_blueprint,
    scheduled_tests_blueprint,
    stats_blueprint,
    live_test_blueprint,
    alerts_blueprint,
    autoperf_blueprint,
]

__all__ = ["blueprints"]
