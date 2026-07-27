"""SASE API blueprints."""
from __future__ import annotations

from hub_api.modules.sase.api.certs import blueprint as certs_blueprint
from hub_api.modules.sase.api.jwt import blueprint as jwt_blueprint

blueprints = [
    certs_blueprint,
    jwt_blueprint,
]

__all__ = ["blueprints"]
