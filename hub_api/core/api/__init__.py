"""Core API blueprints."""
from __future__ import annotations

from hub_api.core.api.certs import blueprint as certs_blueprint
from hub_api.core.api.jwt import blueprint as jwt_blueprint

__all__ = ["certs_blueprint", "jwt_blueprint"]
