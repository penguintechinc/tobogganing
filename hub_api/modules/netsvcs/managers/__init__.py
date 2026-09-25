"""DNS server and config management for netsvcs module."""
from __future__ import annotations

from hub_api.modules.netsvcs.managers.config_service import ConfigService
from hub_api.modules.netsvcs.managers.server_manager import ServerManager

__all__ = ["ConfigService", "ServerManager"]
