"""NetSvcs API blueprints for DNS zones, servers, and analytics."""

from __future__ import annotations

from hub_api.modules.netsvcs.api.analytics import analytics_bp
from hub_api.modules.netsvcs.api.dns_servers import dns_servers_bp
from hub_api.modules.netsvcs.api.resolver_settings import resolver_settings_bp
from hub_api.modules.netsvcs.api.zones import zones_bp

blueprints = [zones_bp, dns_servers_bp, analytics_bp, resolver_settings_bp]

__all__ = ["blueprints"]
