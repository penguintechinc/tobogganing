"""WaddlePerf cluster API blueprints."""
from __future__ import annotations

from core.modules.waddleperf_cluster.api.alerts import alerts_bp as alerts_blueprint
from core.modules.waddleperf_cluster.api.devices import blueprint as devices_blueprint
from core.modules.waddleperf_cluster.api.enrollment import blueprint as enrollment_blueprint
from core.modules.waddleperf_cluster.api.live_test import blueprint as live_test_blueprint
from core.modules.waddleperf_cluster.api.org_units import blueprint as org_units_blueprint
from core.modules.waddleperf_cluster.api.scheduled_tests import (
    blueprint as scheduled_tests_blueprint,
)
from core.modules.waddleperf_cluster.api.stats import blueprint as stats_blueprint
from core.modules.waddleperf_cluster.api.tests import blueprint as tests_blueprint

blueprints = [
    org_units_blueprint,
    devices_blueprint,
    enrollment_blueprint,
    tests_blueprint,
    scheduled_tests_blueprint,
    stats_blueprint,
    live_test_blueprint,
    alerts_blueprint,
]

__all__ = ["blueprints"]
