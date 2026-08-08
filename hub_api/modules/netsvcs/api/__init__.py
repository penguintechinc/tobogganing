"""NetSvcs API blueprints for DNS zones, servers, and analytics."""
from __future__ import annotations

from hub_api.modules.netsvcs.api.zones import zones_bp
from hub_api.modules.netsvcs.api.dns_servers import dns_servers_bp
from hub_api.modules.netsvcs.api.analytics import analytics_bp

blueprints = [zones_bp, dns_servers_bp, analytics_bp]

__all__ = ["blueprints"]
