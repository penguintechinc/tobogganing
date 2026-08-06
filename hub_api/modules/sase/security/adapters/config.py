"""Configuration for security analysis adapters."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class AdapterConfig:
    """Configuration for a single analysis adapter.

    Each adapter reads its configuration from environment variables,
    with sane defaults (all tools disabled by default).
    """

    source: str
    enabled: bool
    endpoint: str | None
    log_path: str | None

    @classmethod
    def from_env(cls, source: str) -> AdapterConfig:
        """Load adapter config from environment variables.

        Convention: {SOURCE}_ENABLED, {SOURCE}_ENDPOINT, {SOURCE}_LOG_PATH

        Args:
            source: Tool name (suricata, zeek, strelka, cape, arkime).

        Returns:
            AdapterConfig instance.
        """
        env_prefix = source.upper()
        enabled = os.getenv(f"{env_prefix}_ENABLED", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        endpoint = os.getenv(f"{env_prefix}_ENDPOINT")
        log_path = os.getenv(f"{env_prefix}_LOG_PATH")

        return cls(
            source=source,
            enabled=enabled,
            endpoint=endpoint,
            log_path=log_path,
        )


# Pre-built configs for all tools
SURICATA_CONFIG = AdapterConfig.from_env("suricata")
ZEEK_CONFIG = AdapterConfig.from_env("zeek")
STRELKA_CONFIG = AdapterConfig.from_env("strelka")
CAPE_CONFIG = AdapterConfig.from_env("cape")
ARKIME_CONFIG = AdapterConfig.from_env("arkime")

ADAPTER_CONFIGS = {
    "suricata": SURICATA_CONFIG,
    "zeek": ZEEK_CONFIG,
    "strelka": STRELKA_CONFIG,
    "cape": CAPE_CONFIG,
    "arkime": ARKIME_CONFIG,
}
