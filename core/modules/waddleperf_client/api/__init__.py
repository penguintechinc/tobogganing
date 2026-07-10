"""WaddlePerf client API blueprints."""
from __future__ import annotations

from core.modules.waddleperf_client.api.schedules import blueprint as schedules_blueprint
from core.modules.waddleperf_client.api.client_config import blueprint as client_config_blueprint
from core.modules.waddleperf_client.api.version import blueprint as version_blueprint

blueprints = [
    schedules_blueprint,
    client_config_blueprint,
    version_blueprint,
]

__all__ = ["blueprints"]
