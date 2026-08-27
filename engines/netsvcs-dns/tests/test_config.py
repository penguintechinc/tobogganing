"""Tests for Config.from_env()."""

from __future__ import annotations

import pytest
from app.config import Config


def test_from_env_missing_grpc_addr(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env raises ValueError when CONTROL_PLANE_GRPC_ADDR is unset."""
    monkeypatch.delenv("CONTROL_PLANE_GRPC_ADDR", raising=False)
    monkeypatch.delenv("ENROLLMENT_BOOTSTRAP_TOKEN", raising=False)

    with pytest.raises(ValueError, match="CONTROL_PLANE_GRPC_ADDR"):
        Config.from_env()


def test_from_env_missing_bootstrap_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env raises ValueError when ENROLLMENT_BOOTSTRAP_TOKEN is unset."""
    monkeypatch.setenv("CONTROL_PLANE_GRPC_ADDR", "control-plane:50051")
    monkeypatch.delenv("ENROLLMENT_BOOTSTRAP_TOKEN", raising=False)

    with pytest.raises(ValueError, match="ENROLLMENT_BOOTSTRAP_TOKEN"):
        Config.from_env()


def test_from_env_success_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env builds a Config from required env vars, defaulting the rest."""
    monkeypatch.setenv("CONTROL_PLANE_GRPC_ADDR", "control-plane:50051")
    monkeypatch.setenv("ENROLLMENT_BOOTSTRAP_TOKEN", "bootstrap-token")
    for var in (
        "GRPC_TLS_CA_PATH",
        "NETSVCS_DNS_GRPC_INSECURE",
        "SERVER_NAME",
        "HOSTNAME",
        "REGION",
        "VERSION",
        "CACHE_URL",
        "DOH_PORT",
        "DOT_PORT",
        "DOT_TLS_CERT_PATH",
        "DOT_TLS_KEY_PATH",
        "LOG_LEVEL",
        "CONFIG_CACHE_DIR",
    ):
        monkeypatch.delenv(var, raising=False)

    config = Config.from_env()

    assert config.control_plane_grpc_addr == "control-plane:50051"
    assert config.enrollment_bootstrap_token == "bootstrap-token"
    assert config.grpc_tls_ca_path is None
    assert config.grpc_insecure_dev_flag is False
    assert config.server_name == "dns-resolver"
    assert config.hostname == "localhost"
    assert config.region == "us-east-1"
    assert config.version == "0.1.0"
    assert config.cache_url == "redis://localhost:6379/0"
    assert config.doh_port == 8053
    assert config.dot_port == 853
    assert config.dot_tls_cert_path is None
    assert config.dot_tls_key_path is None
    assert config.log_level == "info"
    assert config.config_cache_dir.endswith(".cache/netsvcs-dns")


def test_from_env_success_with_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env honors overrides for optional env vars, including the insecure dev flag."""
    monkeypatch.setenv("CONTROL_PLANE_GRPC_ADDR", "control-plane:50051")
    monkeypatch.setenv("ENROLLMENT_BOOTSTRAP_TOKEN", "bootstrap-token")
    monkeypatch.setenv("GRPC_TLS_CA_PATH", "/etc/ca.pem")
    monkeypatch.setenv("NETSVCS_DNS_GRPC_INSECURE", "1")
    monkeypatch.setenv("DOH_PORT", "9053")
    monkeypatch.setenv("DOT_PORT", "9853")

    config = Config.from_env()

    assert config.grpc_tls_ca_path == "/etc/ca.pem"
    assert config.grpc_insecure_dev_flag is True
    assert config.doh_port == 9053
    assert config.dot_port == 9853
