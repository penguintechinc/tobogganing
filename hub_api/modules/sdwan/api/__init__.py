"""SDWAN transport layer API blueprints."""
from __future__ import annotations

from hub_api.modules.sdwan.api.clients import blueprint as clients_blueprint
from hub_api.modules.sdwan.api.clusters import blueprint as clusters_blueprint
from hub_api.modules.sdwan.api.status import blueprint as status_blueprint
from hub_api.modules.sdwan.api.wireguard import blueprint as wireguard_blueprint

blueprints = [
    clusters_blueprint,
    clients_blueprint,
    status_blueprint,
    wireguard_blueprint,
]

__all__ = ["blueprints"]
