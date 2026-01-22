"""
gRPC server helpers with health checks and graceful shutdown.
"""

from __future__ import annotations

import logging
import signal
from concurrent import futures
from dataclasses import dataclass
from typing import Any, Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ServerOptions:
    """Configuration options for gRPC server."""

    max_workers: int = 10
    max_concurrent_rpcs: int = 100
    enable_reflection: bool = True
    enable_health_check: bool = True
    port: int = 50051
    max_connection_idle_ms: int = 300000  # 5 minutes
    max_connection_age_ms: int = 600000  # 10 minutes
    keepalive_time_ms: int = 60000  # 1 minute
    keepalive_timeout_ms: int = 20000  # 20 seconds


def create_server(
    interceptors: Optional[list[grpc.ServerInterceptor]] = None,
    options: Optional[ServerOptions] = None,
) -> grpc.Server:
    """
    Create a gRPC server with standard configuration.

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
    """
    Register health check service on the server.

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


def start_server_with_graceful_shutdown(
    server: grpc.Server,
    port: int = 50051,
    grace_period: float = 30.0,
) -> None:
    """
    Start server and handle graceful shutdown on SIGTERM/SIGINT.

    Args:
        server: gRPC server instance
        port: Port to listen on
        grace_period: Seconds to wait for ongoing RPCs to complete

    Example:
        >>> server = create_server()
        >>> # Add your servicers
        >>> start_server_with_graceful_shutdown(server, port=50051)
    """
    server.add_insecure_port(f"[::]:{port}")
    server.start()

    logger.info(f"gRPC server listening on port {port}")

    # Setup graceful shutdown
    def handle_shutdown(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        server.stop(grace_period)
        logger.info("Server stopped gracefully")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Wait for termination
    server.wait_for_termination()
