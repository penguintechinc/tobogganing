"""HTTP client for communicating with WaddlePerf testserver engine.

This module provides an async HTTP client for the control plane to drive
the Go testserver engine, proxying test requests with authentication.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import structlog

log = structlog.get_logger(__name__)

# Allowed test types. Most map 1:1 to a testserver `/api/v1/test/{type}`
# endpoint; "throughput" is dispatched through ThroughputBackend instead
# (see below) since the heavy-tier speed test does not follow that
# generic JSON request/response convention.
#
# NOTE(http2 seam): "http2" follows the generic `/api/v1/test/http2`
# convention like `http`/`tcp`/etc., but the testserver-side HTTP/2 probe
# handler does not exist yet in engines/testserver -- that's a documented
# Go-side follow-up. Until it lands, calling this type against a real
# (current) testserver fails with a normal EngineError (404 -> "Test
# execution failed"), same as any other not-yet-implemented endpoint.
ALLOWED_TEST_TYPES = {
    "http",
    "tcp",
    "udp",
    "icmp",
    "http_trace",
    "tcp_trace",
    "udp_trace",
    "traceroute",
    "throughput",
    "http2",
}

# Input aliases normalized to a canonical ALLOWED_TEST_TYPES member before
# validation/dispatch -- callers may use either spelling.
TEST_TYPE_ALIASES: dict[str, str] = {
    "speedtest": "throughput",
    "http2_ping": "http2",
}

# Timeout for engine requests (seconds)
DEFAULT_TIMEOUT = 30.0

# Payload size bounds (MB) for the default throughput backend's upload test.
DEFAULT_THROUGHPUT_SIZE_MB = 10
MIN_THROUGHPUT_SIZE_MB = 1
MAX_THROUGHPUT_SIZE_MB = 100


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


class ThroughputBackend(Protocol):
    """Adapter seam for the heavy-tier throughput ("speedtest") invocation.

    Decouples *how* a throughput measurement is obtained from AutoPerf's
    tier-escalation logic and EngineClient's dispatch table -- both only
    ever call ``EngineClient.run_test("throughput", ...)``. Today the
    default backend drives the Go testserver's single-stream
    ``/speedtest/upload`` endpoint; a planned custom multi-client Rust
    throughput server (multi-stream, modern auth) is expected to replace it
    later. Swap the backend passed to :class:`EngineClient`, not the tier
    logic or callers.
    """

    async def run(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        target: str,
        headers: dict[str, str],
        **params: Any,
    ) -> dict[str, Any]:
        """Execute a throughput measurement and return a normalized result."""
        ...


class TestserverSpeedtestBackend:
    """Default throughput backend: the Go testserver's ``/speedtest/upload`` endpoint.

    Uploads a random payload and normalizes the server-reported
    ``throughput_mbps`` into the ``throughput`` key already used across the
    perftest_cluster pipeline (``PerfTestResult.throughput``, alert
    evaluation, stats aggregation), alongside the raw ``throughput_mbps``
    for callers that want the untranslated value.
    """

    async def run(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        target: str,
        headers: dict[str, str],
        **params: Any,
    ) -> dict[str, Any]:
        """Upload a payload to ``/speedtest/upload`` and map the response.

        Args:
            client: Shared httpx.AsyncClient (reused across engine calls).
            base_url: Engine base URL -- the upload always targets the
                engine instance itself (the cluster device's local
                testserver), which *is* the speedtest server for that
                device; ``target`` is carried through for record-keeping.
            target: Test target, recorded in the result but not used to
                build the upload URL.
            headers: Request headers (auth + device metadata).
            **params: Optional ``size_mb`` (1-100, default 10) controlling
                upload payload size.

        Returns:
            Normalized result dict with ``throughput`` (mbps), the raw
            ``throughput_mbps``, ``bytes_transferred``, and ``duration_ms``.

        Raises:
            EngineError: On HTTP error status from the engine. Network
                errors (``httpx.RequestError``) propagate to the caller
                (``EngineClient.run_test``), which normalizes them.
        """
        size_mb = params.get("size_mb", DEFAULT_THROUGHPUT_SIZE_MB)
        try:
            size_mb = int(size_mb)
        except (TypeError, ValueError):
            size_mb = DEFAULT_THROUGHPUT_SIZE_MB
        size_mb = max(MIN_THROUGHPUT_SIZE_MB, min(size_mb, MAX_THROUGHPUT_SIZE_MB))
        payload = os.urandom(size_mb * 1024 * 1024)

        url = f"{base_url}/speedtest/upload"
        response = await client.post(url, content=payload, headers=headers)

        if response.status_code >= 400:
            error_text = response.text[:500]
            log.error(
                "throughput_test_failed",
                status_code=response.status_code,
                details=error_text,
            )
            raise EngineError(
                "Test execution failed",
                status_code=response.status_code,
                details=error_text,
            )

        data: dict[str, Any] = response.json()
        throughput_mbps = data.get("throughput_mbps")

        return {
            "throughput": throughput_mbps,
            "throughput_mbps": throughput_mbps,
            "latency_ms": data.get("latency_ms"),
            "bytes_transferred": data.get("bytes_received"),
            "duration_ms": data.get("duration_ms"),
            "target": target,
            "output": data,
        }


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
        throughput_backend: ThroughputBackend | None = None,
    ) -> None:
        """Initialize engine client.

        Args:
            base_url: Engine base URL (defaults to ENGINE_URL env var or
                http://testserver:8080)
            api_key: API key for authentication (defaults to ENGINE_API_KEY env var)
            timeout: Request timeout in seconds (default 30)
            throughput_backend: Adapter used for the "throughput" test type
                (defaults to :class:`TestserverSpeedtestBackend`). Inject a
                different backend to point the heavy-tier speed test at a
                different server implementation without touching callers.

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
        self.throughput_backend: ThroughputBackend = (
            throughput_backend or TestserverSpeedtestBackend()
        )
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
                udp_trace, traceroute, throughput, http2). "speedtest" is
                accepted as an alias for "throughput", "http2_ping" for
                "http2".
            target: Target host/IP for the test
            device_headers: Optional device metadata headers (X-Device-*)
            **params: Additional test parameters (port, timeout, count, etc.)

        Returns:
            Parsed JSON response from engine as dict

        Raises:
            EngineError: If test_type is invalid, or on network/HTTP errors
        """
        # Normalize aliases, then validate test type
        test_type = TEST_TYPE_ALIASES.get(test_type, test_type)
        if test_type not in ALLOWED_TEST_TYPES:
            msg = f"Invalid test_type: {test_type}"
            log.error("invalid_test_type", test_type=test_type)
            raise EngineError(msg)

        # Prepare headers (shared by both the generic and throughput paths)
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if device_headers:
            headers.update(device_headers)

        try:
            client = await self._get_client()

            if test_type == "throughput":
                log.debug(
                    "run_throughput_test",
                    target=target,
                    backend=type(self.throughput_backend).__name__,
                )
                result = await self.throughput_backend.run(
                    client, self.base_url, target, headers, **params
                )
                log.info("test_complete", test_type=test_type, target=target)
                return result

            url = f"{self.base_url}/api/v1/test/{test_type}"

            # Prepare request body
            request_body = {
                "target": target,
                **params,
            }

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
                    "Test execution failed",
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
