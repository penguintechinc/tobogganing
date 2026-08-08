"""DNS servers blueprint for netsvcs module."""
from __future__ import annotations

from quart import Blueprint

dns_servers_bp = Blueprint("netsvcs_dns_servers", __name__, url_prefix="/dns-servers")

# Routes for server management and node plane will be added in S1
