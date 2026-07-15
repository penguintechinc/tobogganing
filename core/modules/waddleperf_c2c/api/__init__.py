"""WaddlePerf c2c API blueprints."""
from __future__ import annotations

from core.modules.waddleperf_c2c.api.endpoints import blueprint as endpoints_blueprint
from core.modules.waddleperf_c2c.api.matrix import blueprint as matrix_blueprint
from core.modules.waddleperf_c2c.api.recurring import blueprint as recurring_blueprint
from core.modules.waddleperf_c2c.api.regions import blueprint as regions_blueprint
from core.modules.waddleperf_c2c.api.runs import blueprint as runs_blueprint

blueprints = [
    endpoints_blueprint,
    runs_blueprint,
    matrix_blueprint,
    recurring_blueprint,
    regions_blueprint,
]

__all__ = ["blueprints"]
