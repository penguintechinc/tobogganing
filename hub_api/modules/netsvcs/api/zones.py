"""DNS zones and records blueprint for netsvcs module."""
from __future__ import annotations

from quart import Blueprint

zones_bp = Blueprint("netsvcs_zones", __name__, url_prefix="/zones")

# Routes for zones CRUD and records will be added in S1
