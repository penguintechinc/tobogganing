"""SASE API blueprints."""
from __future__ import annotations

from hub_api.modules.sase.api.certs import blueprint as certs_blueprint
from hub_api.modules.sase.api.clients import blueprint as clients_blueprint
from hub_api.modules.sase.api.clusters import blueprint as clusters_blueprint
from hub_api.modules.sase.api.jwt import blueprint as jwt_blueprint
from hub_api.modules.sase.api.status import blueprint as status_blueprint
from hub_api.modules.sase.api.wireguard import blueprint as wireguard_blueprint

blueprints = [
    clusters_blueprint,
    clients_blueprint,
    status_blueprint,
    certs_blueprint,
    jwt_blueprint,
    wireguard_blueprint,
]

__all__ = ["blueprints"]
