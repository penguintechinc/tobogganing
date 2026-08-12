"""Configuration for DNS resolver service.

Environment-driven config using @dataclass(slots=True) for memory efficiency.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Config:
    """DNS resolver service configuration."""

    # Control plane gRPC connection
    control_plane_grpc_addr: str
    enrollment_bootstrap_token: str
    grpc_tls_ca_path: str | None
    grpc_insecure_dev_flag: bool

    # Server identity
    server_name: str
    hostname: str
    region: str
    version: str

    # Caching (redis/valkey)
    cache_url: str

    # Ports (not served in P3-S0, but configured)
    doh_port: int
    dot_port: int

    # TLS for DoT (not used in P3-S0)
    dot_tls_cert_path: str | None
    dot_tls_key_path: str | None

    # Logging
    log_level: str

    # Offline cache directory
    config_cache_dir: str

    @staticmethod
    def from_env() -> Config:
        """Load configuration from environment variables."""
        control_plane_grpc_addr = os.getenv("CONTROL_PLANE_GRPC_ADDR")
        if not control_plane_grpc_addr:
            raise ValueError("CONTROL_PLANE_GRPC_ADDR environment variable required")

        enrollment_bootstrap_token = os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN")
        if not enrollment_bootstrap_token:
            raise ValueError("ENROLLMENT_BOOTSTRAP_TOKEN environment variable required")

        return Config(
            control_plane_grpc_addr=control_plane_grpc_addr,
            enrollment_bootstrap_token=enrollment_bootstrap_token,
            grpc_tls_ca_path=os.getenv("GRPC_TLS_CA_PATH"),
            grpc_insecure_dev_flag=os.getenv("NETSVCS_DNS_GRPC_INSECURE", "0") == "1",
            server_name=os.getenv("SERVER_NAME", "dns-resolver"),
            hostname=os.getenv("HOSTNAME", "localhost"),
            region=os.getenv("REGION", "us-east-1"),
            version=os.getenv("VERSION", "0.1.0"),
            cache_url=os.getenv("CACHE_URL", "redis://localhost:6379/0"),
            doh_port=int(os.getenv("DOH_PORT", "8053")),
            dot_port=int(os.getenv("DOT_PORT", "853")),
            dot_tls_cert_path=os.getenv("DOT_TLS_CERT_PATH"),
            dot_tls_key_path=os.getenv("DOT_TLS_KEY_PATH"),
            log_level=os.getenv("LOG_LEVEL", "info"),
            config_cache_dir=os.getenv("CONFIG_CACHE_DIR", os.path.expanduser("~/.cache/netsvcs-dns")),
        )
