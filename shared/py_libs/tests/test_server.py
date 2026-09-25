"""Tests for gRPC server reflection gating and hardening.

Reflection previously registered unconditionally (`enable_reflection: bool =
True`), exposing the full RPC surface for discovery in every environment.
It now defaults on only for dev/local, fails closed everywhere else, and
`GRPC_ENABLE_REFLECTION` allows an explicit override in either direction.

Also covers two ops-audit hardening findings: unbounded message-length
limits (max_receive/send_message_length now bounded by default) and
`add_insecure_port` binding unconditionally regardless of whether TLS
credentials were ever supplied (now fail-closed behind
`GRPC_ALLOW_INSECURE` / `allow_insecure`, TLS-preferred via
`server_credentials`).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import grpc
import pytest

import py_libs.grpc.server as server_mod
from py_libs.grpc.server import (
    ServerOptions,
    _default_allow_insecure,
    _default_enable_reflection,
    bind_server_port,
    create_server,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("GRPC_ENABLE_REFLECTION", raising=False)
    monkeypatch.delenv("GRPC_ALLOW_INSECURE", raising=False)


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


class TestMessageLengthLimits:
    """Regression: message-length limits were previously unbounded.

    `max_receive/send_message_length` were previously absent from
    `server_options`, leaving message size effectively unbounded.
    """

    def test_default_options_bound_both_directions(self) -> None:
        options = ServerOptions()
        assert options.max_receive_message_length > 0
        assert options.max_send_message_length > 0

    def test_create_server_passes_length_limits_to_grpc_options(self) -> None:
        captured: dict[str, object] = {}
        original_server = grpc.server

        def _spy_server(*args: object, **kwargs: object) -> grpc.Server:
            captured["options"] = dict(kwargs.get("options", []))
            return original_server(*args, **kwargs)

        with patch.object(server_mod.grpc, "server", side_effect=_spy_server):
            server = create_server(options=ServerOptions(enable_health_check=False))
        try:
            opts = captured["options"]
            defaults = ServerOptions()
            assert opts["grpc.max_receive_message_length"] == defaults.max_receive_message_length
            assert opts["grpc.max_send_message_length"] == defaults.max_send_message_length
        finally:
            server.stop(grace=None)

    def test_custom_length_limits_propagate(self) -> None:
        options = ServerOptions(
            max_receive_message_length=1024,
            max_send_message_length=2048,
            enable_health_check=False,
        )
        server = create_server(options=options)
        try:
            assert options.max_receive_message_length == 1024
            assert options.max_send_message_length == 2048
        finally:
            server.stop(grace=None)


class TestInsecurePortGating:
    """Regression: plaintext binding was previously unconditional.

    `start_server_with_graceful_shutdown` previously called
    `add_insecure_port` unconditionally, regardless of whether TLS
    credentials were ever supplied (security.md TLS 1.2+ mandatory).
    Exercises `bind_server_port` directly (the bind-decision helper
    extracted from `start_server_with_graceful_shutdown`) rather than the
    full function, which also calls `server.start()` and blocks forever
    in `wait_for_termination()`.
    """

    def test_defaults_closed_when_env_unset(self) -> None:
        assert _default_allow_insecure() is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
    def test_env_opt_in_allows_insecure(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("GRPC_ALLOW_INSECURE", value)
        assert _default_allow_insecure() is True

    def test_raises_without_credentials_or_opt_in(self) -> None:
        server = create_server(options=ServerOptions(enable_health_check=False))
        try:
            with pytest.raises(RuntimeError, match="GRPC_ALLOW_INSECURE"):
                bind_server_port(server, port=0, allow_insecure=False)
        finally:
            server.stop(grace=None)

    def test_binds_insecure_port_with_explicit_opt_in(self) -> None:
        server = create_server(options=ServerOptions(enable_health_check=False))
        try:
            with patch.object(server, "add_insecure_port") as add_insecure_port:
                bind_server_port(server, port=0, allow_insecure=True)
            add_insecure_port.assert_called_once()
        finally:
            server.stop(grace=None)

    def test_binds_secure_port_when_credentials_supplied(self) -> None:
        server = create_server(options=ServerOptions(enable_health_check=False))
        fake_credentials = MagicMock(spec=grpc.ServerCredentials)
        try:
            with patch.object(server, "add_secure_port") as add_secure_port:
                bind_server_port(server, port=0, server_credentials=fake_credentials)
            add_secure_port.assert_called_once()
        finally:
            server.stop(grace=None)
