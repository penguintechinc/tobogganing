"""gRPC server helpers with health checks and graceful shutdown."""

from __future__ import annotations

import logging
import os
import signal
from concurrent import futures
from dataclasses import dataclass, field
from typing import Any

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

logger = logging.getLogger(__name__)

_DEV_ENV_VALUES = {"dev", "development", "local"}
_TRUTHY_VALUES = {"1", "true", "yes", "on"}

# grpc-python's own built-in receive default; send was previously left at
# grpc's -1 (unlimited) by omission here. Bounding both prevents a single
# oversized message from exhausting memory/CPU on this server -- an
# unbounded gRPC message size is the RPC equivalent of an unbounded HTTP
# request body (security.md Input Validation: bounds validation).
_DEFAULT_MAX_MESSAGE_BYTES = 4 * 1024 * 1024  # 4 MiB


def _default_allow_insecure() -> bool:
    """Whether add_insecure_port is permitted when no TLS credentials are given.

    Fails closed: plaintext is refused by default (security.md TLS 1.2+
    mandatory) unless GRPC_ALLOW_INSECURE explicitly opts in (e.g. local
    dev/tests, or intra-pod loopback where mTLS is terminated by a
    sidecar) -- mirrors _default_enable_reflection's env-driven,
    explicit-override pattern.
    """
    return os.getenv("GRPC_ALLOW_INSECURE", "").strip().lower() in _TRUTHY_VALUES


def _default_enable_reflection() -> bool:
    """Reflection defaults on only for local/dev; off everywhere else.

    Reflection exposes the full RPC/service surface for introspection — a
    convenience for local debugging, but a discovery aid for an attacker in
    staging/prod. Fails closed: `GRPC_ENABLE_REFLECTION` wins if set
    (either direction); otherwise the default is derived from `ENV`, and
    any value other than dev/development/local — including unset — disables
    it.
    """
    override = os.getenv("GRPC_ENABLE_REFLECTION")
    if override is not None:
        return override.strip().lower() in _TRUTHY_VALUES
    return os.getenv("ENV", "production").strip().lower() in _DEV_ENV_VALUES


@dataclass(slots=True, frozen=True)
class ServerOptions:
    """Configuration options for gRPC server."""

    max_workers: int = 10
    max_concurrent_rpcs: int = 100
    enable_reflection: bool = field(default_factory=_default_enable_reflection)
    enable_health_check: bool = True
    port: int = 50051
    max_connection_idle_ms: int = 300000  # 5 minutes
    max_connection_age_ms: int = 600000  # 10 minutes
    keepalive_time_ms: int = 60000  # 1 minute
    keepalive_timeout_ms: int = 20000  # 20 seconds
    max_receive_message_length: int = _DEFAULT_MAX_MESSAGE_BYTES
    max_send_message_length: int = _DEFAULT_MAX_MESSAGE_BYTES


def create_server(
    interceptors: list[grpc.ServerInterceptor] | None = None,
    options: ServerOptions | None = None,
) -> grpc.Server:
    """Create a gRPC server with standard configuration.

    Args:
        interceptors: List of server interceptors for auth, logging, etc.
        options: Server configuration options

    Returns:
        Configured gRPC server instance

    Example:
        >>> from py_libs.grpc import create_server, AuthInterceptor
        >>> interceptors = [AuthInterceptor()]
        >>> server = create_server(interceptors=interceptors)
        >>> # Add servicers
        >>> server.add_insecure_port('[::]:50051')
        >>> server.start()

    """
    if options is None:
        options = ServerOptions()

    if interceptors is None:
        interceptors = []

    # Server configuration options
    server_options = [
        ("grpc.max_concurrent_streams", options.max_concurrent_rpcs),
        ("grpc.max_connection_idle_ms", options.max_connection_idle_ms),
        ("grpc.max_connection_age_ms", options.max_connection_age_ms),
        ("grpc.keepalive_time_ms", options.keepalive_time_ms),
        ("grpc.keepalive_timeout_ms", options.keepalive_timeout_ms),
        ("grpc.http2.max_pings_without_data", 0),
        ("grpc.http2.min_time_between_pings_ms", 10000),
        ("grpc.http2.min_ping_interval_without_data_ms", 5000),
        ("grpc.max_receive_message_length", options.max_receive_message_length),
        ("grpc.max_send_message_length", options.max_send_message_length),
    ]

    # Create server with thread pool
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=options.max_workers),
        interceptors=interceptors,
        options=server_options,
    )

    # Register health check service
    if options.enable_health_check:
        register_health_check(server)

    # Enable reflection for debugging
    if options.enable_reflection:
        _enable_reflection(server)

    logger.info(
        "gRPC server created",
        extra={
            "max_workers": options.max_workers,
            "max_concurrent_rpcs": options.max_concurrent_rpcs,
            "interceptors": len(interceptors),
        },
    )

    return server


def register_health_check(server: grpc.Server) -> health.HealthServicer:
    """Register health check service on the server.

    Args:
        server: gRPC server instance

    Returns:
        Health servicer for status management

    Example:
        >>> health_servicer = register_health_check(server)
        >>> health_servicer.set("myservice", health_pb2.HealthCheckResponse.SERVING)

    """
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Set overall server health
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    logger.info("Health check service registered")
    return health_servicer


def _enable_reflection(server: grpc.Server) -> None:
    """Enable server reflection for debugging."""
    service_names = (
        reflection.SERVICE_NAME,
        health.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)
    logger.info("Server reflection enabled")


def bind_server_port(
    server: grpc.Server,
    port: int,
    server_credentials: grpc.ServerCredentials | None = None,
    allow_insecure: bool | None = None,
) -> None:
    """Bind `server` to `port`, TLS-preferred, plaintext fail-closed.

    Pass `server_credentials` (e.g. SPIFFE/SPIRE-issued X.509-SVID or any
    `grpc.ssl_server_credentials`) to bind a secure port -- every service
    is SPIFFE-ready per security.md regardless of whether SPIRE is
    deployed yet. Without credentials, plaintext is refused unless
    explicitly opted into via `allow_insecure=True` or `GRPC_ALLOW_INSECURE`
    (fail closed -- security.md TLS 1.2+ mandatory). Split out from
    `start_server_with_graceful_shutdown` so the bind decision is testable
    without also invoking `server.start()`/`wait_for_termination()`.

    Args:
        server: gRPC server instance.
        port: Port to bind.
        server_credentials: TLS server credentials. When provided, binds
            `add_secure_port` instead of `add_insecure_port`.
        allow_insecure: Explicit opt-in to `add_insecure_port` when no
            credentials are supplied. Defaults to `GRPC_ALLOW_INSECURE`
            (fail closed) when None.

    Raises:
        RuntimeError: No credentials supplied and insecure binding was not
            explicitly allowed.

    """
    if server_credentials is not None:
        server.add_secure_port(f"[::]:{port}", server_credentials)
        logger.info(f"gRPC server binding port {port} (TLS)")
        return

    insecure_ok = allow_insecure if allow_insecure is not None else _default_allow_insecure()
    if not insecure_ok:
        raise RuntimeError(
            "bind_server_port: no server_credentials supplied and GRPC_ALLOW_INSECURE "
            "is not set -- refusing to bind a plaintext port (security.md TLS 1.2+ "
            "mandatory). Pass server_credentials for TLS, or set "
            "GRPC_ALLOW_INSECURE=true / allow_insecure=True to explicitly opt into "
            "plaintext (e.g. local dev, or intra-pod loopback behind an mTLS sidecar)."
        )
    server.add_insecure_port(f"[::]:{port}")
    logger.warning(f"gRPC server binding port {port} (insecure -- explicit opt-in)")


def start_server_with_graceful_shutdown(
    server: grpc.Server,
    port: int = 50051,
    grace_period: float = 30.0,
    server_credentials: grpc.ServerCredentials | None = None,
    allow_insecure: bool | None = None,
) -> None:
    """Start server and handle graceful shutdown on SIGTERM/SIGINT.

    See `bind_server_port` for the TLS-preferred/fail-closed-plaintext
    binding behavior and its `server_credentials`/`allow_insecure` args.

    Args:
        server: gRPC server instance
        port: Port to listen on
        grace_period: Seconds to wait for ongoing RPCs to complete
        server_credentials: Forwarded to `bind_server_port`.
        allow_insecure: Forwarded to `bind_server_port`.

    Raises:
        RuntimeError: No credentials supplied and insecure binding was not
            explicitly allowed.

    Example:
        >>> server = create_server()
        >>> # Add your servicers
        >>> start_server_with_graceful_shutdown(server, port=50051, server_credentials=creds)

    """
    bind_server_port(server, port, server_credentials, allow_insecure)
    server.start()

    # Setup graceful shutdown
    def handle_shutdown(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        server.stop(grace_period)
        logger.info("Server stopped gracefully")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Wait for termination
    server.wait_for_termination()
