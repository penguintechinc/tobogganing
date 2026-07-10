"""HTTP client for communicating with WaddlePerf testserver engine.

This module provides an async HTTP client for the control plane to drive
the Go testserver engine, proxying test requests with authentication.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

# Allowed test types matching testserver endpoints
ALLOWED_TEST_TYPES = {
    "http",
    "tcp",
    "udp",
    "icmp",
    "http_trace",
    "tcp_trace",
    "udp_trace",
    "traceroute",
}

# Timeout for engine requests (seconds)
DEFAULT_TIMEOUT = 30.0


@dataclass(slots=True)
class EngineError(Exception):
    """Raised when engine communication fails."""

    message: str
    status_code: int | None = None
    details: str | None = None

    def __str__(self) -> str:
        """Return string representation."""
        msg = self.message
        if self.status_code:
            msg = f"{msg} (HTTP {self.status_code})"
        if self.details:
            msg = f"{msg}: {self.details}"
        return msg


class EngineClient:
    """Async HTTP client for WaddlePerf testserver engine.

    Proxies test requests from the control plane to the testserver engine,
    injecting authentication headers and device metadata.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize engine client.

        Args:
            base_url: Engine base URL (defaults to ENGINE_URL env var or
                http://testserver:8080)
            api_key: API key for authentication (defaults to ENGINE_API_KEY env var)
            timeout: Request timeout in seconds (default 30)

        Raises:
            EngineError: If base_url is invalid or empty after env lookup
        """
        # Check for explicit empty string (fail closed)
        if base_url is not None and not base_url:
            raise EngineError("base_url required (set ENGINE_URL env var)")

        self.base_url = base_url or os.environ.get(
            "ENGINE_URL", "http://testserver:8080"
        )

        self.api_key = api_key or os.environ.get("ENGINE_API_KEY")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client.

        Returns:
            AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> EngineClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def health(self) -> bool:
        """Check engine health status.

        Returns:
            True if engine is healthy (HTTP 200), False otherwise

        Raises:
            EngineError: On network or communication errors
        """
        try:
            client = await self._get_client()
            url = f"{self.base_url}/health"
            log.debug("health_check", url=url)

            response = await client.get(url)
            return response.status_code == 200
        except httpx.RequestError as e:
            log.error("health_check_failed", error=str(e))
            raise EngineError(
                f"Failed to reach engine at {self.base_url}", details=str(e)
            ) from e
        except Exception as e:
            log.error("health_check_exception", error=str(e), exc_info=True)
            raise EngineError("Unexpected error during health check", details=str(e)) from e

    async def run_test(
        self,
        test_type: str,
        target: str,
        device_headers: dict[str, str] | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Execute a test on the engine.

        Args:
            test_type: Type of test (http, tcp, udp, icmp, http_trace, tcp_trace,
                udp_trace, traceroute)
            target: Target host/IP for the test
            device_headers: Optional device metadata headers (X-Device-*)
            **params: Additional test parameters (port, timeout, count, etc.)

        Returns:
            Parsed JSON response from engine as dict

        Raises:
            EngineError: If test_type is invalid, or on network/HTTP errors
        """
        # Validate test type
        if test_type not in ALLOWED_TEST_TYPES:
            msg = f"Invalid test_type: {test_type}"
            log.error("invalid_test_type", test_type=test_type)
            raise EngineError(msg)

        try:
            client = await self._get_client()
            url = f"{self.base_url}/api/v1/test/{test_type}"

            # Prepare request body
            request_body = {
                "target": target,
                **params,
            }

            # Prepare headers
            headers: dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # Add device headers
            if device_headers:
                headers.update(device_headers)

            log.debug(
                "run_test",
                url=url,
                test_type=test_type,
                target=target,
                headers_keys=list(headers.keys()),
            )

            response = await client.post(url, json=request_body, headers=headers)

            # Check for HTTP errors
            if response.status_code >= 400:
                error_text = response.text[:500]  # Truncate for logging
                log.error(
                    "test_failed",
                    status_code=response.status_code,
                    details=error_text,
                )
                raise EngineError(
                    f"Test execution failed",
                    status_code=response.status_code,
                    details=error_text,
                )

            # Parse and return response
            result: dict[str, Any] = response.json()
            log.info("test_complete", test_type=test_type, target=target)
            return result

        except httpx.RequestError as e:
            log.error("test_network_error", error=str(e))
            raise EngineError(
                "Failed to communicate with engine", details=str(e)
            ) from e
        except EngineError:
            # Re-raise our own errors
            raise
        except Exception as e:
            log.error("test_exception", error=str(e), exc_info=True)
            raise EngineError("Unexpected error during test", details=str(e)) from e
