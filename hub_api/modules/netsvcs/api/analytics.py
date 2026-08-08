"""Analytics blueprint for netsvcs module."""
from __future__ import annotations

from quart import Blueprint

analytics_bp = Blueprint("netsvcs_analytics", __name__, url_prefix="/analytics")

# Routes for analytics and metrics will be added in S1
