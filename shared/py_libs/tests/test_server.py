"""Tests for gRPC server reflection gating.

Reflection previously registered unconditionally (`enable_reflection: bool =
True`), exposing the full RPC surface for discovery in every environment.
It now defaults on only for dev/local, fails closed everywhere else, and
`GRPC_ENABLE_REFLECTION` allows an explicit override in either direction.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import py_libs.grpc.server as server_mod
from py_libs.grpc.server import ServerOptions, _default_enable_reflection, create_server


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("GRPC_ENABLE_REFLECTION", raising=False)


def test_defaults_closed_when_env_unset() -> None:
    assert _default_enable_reflection() is False
    assert ServerOptions().enable_reflection is False


@pytest.mark.parametrize("env_value", ["production", "staging", "PROD", ""])
def test_defaults_closed_for_non_dev_env(monkeypatch: pytest.MonkeyPatch, env_value: str) -> None:
    monkeypatch.setenv("ENV", env_value)
    assert _default_enable_reflection() is False


@pytest.mark.parametrize("env_value", ["dev", "development", "local", "DEV"])
def test_defaults_open_for_dev_env(monkeypatch: pytest.MonkeyPatch, env_value: str) -> None:
    monkeypatch.setenv("ENV", env_value)
    assert _default_enable_reflection() is True
    assert ServerOptions().enable_reflection is True


def test_explicit_override_enables_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("GRPC_ENABLE_REFLECTION", "true")
    assert _default_enable_reflection() is True


def test_explicit_override_disables_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("GRPC_ENABLE_REFLECTION", "false")
    assert _default_enable_reflection() is False


def test_server_options_can_still_force_enable_explicitly() -> None:
    """Callers can always pass enable_reflection=True explicitly regardless of env."""
    options = ServerOptions(enable_reflection=True)
    assert options.enable_reflection is True


def test_create_server_skips_reflection_registration_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_enable = MagicMock()
    monkeypatch.setattr(server_mod.reflection, "enable_server_reflection", fake_enable)
    options = ServerOptions(enable_reflection=False, enable_health_check=False)
    server = create_server(options=options)
    try:
        fake_enable.assert_not_called()
    finally:
        server.stop(grace=None)


def test_create_server_registers_reflection_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_enable = MagicMock()
    monkeypatch.setattr(server_mod.reflection, "enable_server_reflection", fake_enable)
    server = create_server(options=ServerOptions(enable_reflection=True, enable_health_check=False))
    try:
        fake_enable.assert_called_once()
    finally:
        server.stop(grace=None)
