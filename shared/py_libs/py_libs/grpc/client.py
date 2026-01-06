"""
gRPC client with connection management, retries, and TLS support.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

import grpc

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass(slots=True, frozen=True)
class ClientOptions:
    """Configuration options for gRPC client."""

    max_retries: int = 3
    initial_backoff_ms: int = 100
    max_backoff_ms: int = 5000
    backoff_multiplier: float = 2.0
    timeout_seconds: float = 30.0
    enable_tls: bool = False
    ca_cert_path: Optional[str] = None
    client_cert_path: Optional[str] = None
    client_key_path: Optional[str] = None
    keepalive_time_ms: int = 60000  # 1 minute
    keepalive_timeout_ms: int = 20000  # 20 seconds


class GrpcClient:
    """
    gRPC client wrapper with connection management and retry logic.

    Example:
        >>> from py_libs.grpc import GrpcClient, ClientOptions
        >>> options = ClientOptions(enable_tls=True)
        >>> client = GrpcClient('localhost:50051', options)
        >>>
        >>> # Use with stub
        >>> with client.channel() as channel:
        >>>     stub = MyServiceStub(channel)
        >>>     response = stub.MyMethod(request)
    """

    def __init__(
        self,
        target: str,
        options: Optional[ClientOptions] = None,
    ):
        """
        Initialize gRPC client.

        Args:
            target: Server address (e.g., 'localhost:50051')
            options: Client configuration options
        """
        self.target = target
        self.options = options or ClientOptions()
        self._channel: Optional[grpc.Channel] = None

        logger.info(f"gRPC client initialized for {target}")

    def channel(self) -> grpc.Channel:
        """
        Get or create gRPC channel.

        Returns:
            gRPC channel instance
        """
        if self._channel is None:
            self._channel = self._create_channel()
        return self._channel

    def _create_channel(self) -> grpc.Channel:
        """Create gRPC channel with configuration."""
        channel_options = [
            ('grpc.keepalive_time_ms', self.options.keepalive_time_ms),
            ('grpc.keepalive_timeout_ms', self.options.keepalive_timeout_ms),
            ('grpc.keepalive_permit_without_calls', 1),
            ('grpc.http2.max_pings_without_data', 0),
        ]

        if self.options.enable_tls:
            credentials = self._create_credentials()
            channel = grpc.secure_channel(
                self.target,
                credentials,
                options=channel_options,
            )
            logger.info(f"Secure gRPC channel created to {self.target}")
        else:
            channel = grpc.insecure_channel(
                self.target,
                options=channel_options,
            )
            logger.info(f"Insecure gRPC channel created to {self.target}")

        return channel

    def _create_credentials(self) -> grpc.ChannelCredentials:
        """Create TLS credentials for secure channel."""
        root_certs = None
        if self.options.ca_cert_path:
            with open(self.options.ca_cert_path, 'rb') as f:
                root_certs = f.read()

        private_key = None
        certificate_chain = None
        if self.options.client_cert_path and self.options.client_key_path:
            with open(self.options.client_key_path, 'rb') as f:
                private_key = f.read()
            with open(self.options.client_cert_path, 'rb') as f:
                certificate_chain = f.read()

        return grpc.ssl_channel_credentials(
            root_certificates=root_certs,
            private_key=private_key,
            certificate_chain=certificate_chain,
        )

    def call_with_retry(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Call gRPC method with exponential backoff retry.

        Args:
            func: gRPC stub method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Response from the gRPC method

        Raises:
            grpc.RpcError: If all retries fail

        Example:
            >>> client = GrpcClient('localhost:50051')
            >>> with client.channel() as channel:
            >>>     stub = MyServiceStub(channel)
            >>>     response = client.call_with_retry(
            >>>         stub.MyMethod,
            >>>         request,
            >>>         timeout=10.0
            >>>     )
        """
        backoff_ms = self.options.initial_backoff_ms
        last_exception = None

        for attempt in range(self.options.max_retries):
            try:
                # Set default timeout if not provided
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = self.options.timeout_seconds

                return func(*args, **kwargs)

            except grpc.RpcError as e:
                last_exception = e
                code = e.code()

                # Don't retry on certain errors
                if code in (
                    grpc.StatusCode.INVALID_ARGUMENT,
                    grpc.StatusCode.NOT_FOUND,
                    grpc.StatusCode.ALREADY_EXISTS,
                    grpc.StatusCode.PERMISSION_DENIED,
                    grpc.StatusCode.UNAUTHENTICATED,
                ):
                    logger.error(f"Non-retryable error: {code}", exc_info=True)
                    raise

                # Retry on transient errors
                if attempt < self.options.max_retries - 1:
                    logger.warning(
                        f"RPC failed (attempt {attempt + 1}/{self.options.max_retries}): {code}",
                        extra={
                            'target': self.target,
                            'backoff_ms': backoff_ms,
                        }
                    )

                    # Exponential backoff
                    time.sleep(backoff_ms / 1000.0)
                    backoff_ms = min(
                        backoff_ms * self.options.backoff_multiplier,
                        self.options.max_backoff_ms,
                    )
                else:
                    logger.error(
                        f"RPC failed after {self.options.max_retries} attempts",
                        exc_info=True
                    )

        # All retries failed
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in call_with_retry")

    def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            self._channel.close()
            self._channel = None
            logger.info(f"gRPC channel to {self.target} closed")

    def __enter__(self) -> GrpcClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
