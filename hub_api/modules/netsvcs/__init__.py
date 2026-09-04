"""NetSvcs control plane module for DNS, DHCP, and NTP services."""

from __future__ import annotations

from hub_api.modules.netsvcs.api import blueprints
from hub_api.registry import Entitlement, ModuleContract, NavEntry


def module() -> ModuleContract:
    """Return the module contract for the NetSvcs module.

    Returns:
        ModuleContract with NetSvcs blueprints, feature flags, entitlements,
        navigation entries, and migration history.
    """
    return ModuleContract(
        name="netsvcs",
        blueprints=list(blueprints),
        nav=[
            NavEntry("Zones", "/api/v1/netsvcs/zones", "globe"),
            NavEntry("DNS Servers", "/api/v1/netsvcs/dns-servers", "server"),
            NavEntry("Analytics", "/api/v1/netsvcs/analytics", "bar-chart"),
        ],
        flags=[
            "tobogganing.netsvcs.dns",
            "tobogganing.netsvcs.zones",
            "tobogganing.netsvcs.dns_servers",
            "tobogganing.netsvcs.analytics",
            "tobogganing.netsvcs.dhcp",
            "tobogganing.netsvcs.ntp",
        ],
        entitlements=[
            Entitlement("netsvcs.dns", "community"),
            Entitlement("netsvcs.zones", "community"),
            Entitlement("netsvcs.dns_servers", "community"),
            Entitlement("netsvcs.analytics", "community"),
            Entitlement("netsvcs.dhcp", "community"),
            Entitlement("netsvcs.ntp", "community"),
        ],
        migrations=["0025"],
        health=None,
    )
