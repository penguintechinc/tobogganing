"""
HTTP client with retry logic and circuit breaker pattern.

Provides a production-ready HTTP client with exponential backoff,
configurable timeouts, and optional circuit breaker protection.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

import httpx

from .correlation import get_correlation_id

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass(slots=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass(slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    enabled: bool = False
    failure_threshold: int = 5  # Failures before opening circuit
    success_threshold: int = 2  # Successes before closing circuit
    timeout: float = 60.0  # seconds to wait before half-open


@dataclass(slots=True)
class CircuitBreakerState:
    """Internal state for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0


@dataclass(slots=True)
class HTTPClientConfig:
    """Configuration for HTTP client."""

    timeout: float = 30.0  # seconds
    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    headers: Dict[str, str] = field(default_factory=dict)
    follow_redirects: bool = True
    verify_ssl: bool = True


class HTTPClient:
    """
    Production-ready HTTP client with retries and circuit breaker.

    Features:
    - Exponential backoff with jitter
    - Configurable timeouts
    - Request/response logging
    - Correlation ID propagation
    - Optional circuit breaker pattern

    Example:
        config = HTTPClientConfig(
            timeout=30.0,
            retry=RetryConfig(max_retries=3, base_delay=1.0)
        )
        client = HTTPClient(config)

        response = client.get("https://api.example.com/users")
        data = response.json()
    """

    def __init__(self, config: Optional[HTTPClientConfig] = None) -> None:
        """
        Initialize HTTP client.

        Args:
            config: Client configuration (uses defaults if None)
        """
        self.config = config or HTTPClientConfig()
        self._circuit_state = CircuitBreakerState()
        self._client = httpx.Client(
            timeout=self.config.timeout,
            follow_redirects=self.config.follow_redirects,
            verify=self.config.verify_ssl,
        )

    def __enter__(self) -> "HTTPClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            float: Delay in seconds
        """
        delay = min(
            self.config.retry.base_delay
            * (self.config.retry.exponential_base**attempt),
            self.config.retry.max_delay,
        )

        if self.config.retry.jitter:
            import random

            delay *= 0.5 + random.random()  # Add jitter (50-150% of base)

        return delay

    def _check_circuit_breaker(self) -> None:
        """
        Check circuit breaker state and raise exception if open.

        Raises:
            HTTPError: If circuit breaker is open
        """
        if not self.config.circuit_breaker.enabled:
            return

        now = time.time()

        if self._circuit_state.state == CircuitState.OPEN:
            elapsed = now - self._circuit_state.last_failure_time
            if elapsed >= self.config.circuit_breaker.timeout:
                logger.info("Circuit breaker entering HALF_OPEN state")
                self._circuit_state.state = CircuitState.HALF_OPEN
                self._circuit_state.success_count = 0
            else:
                raise httpx.HTTPError(
                    f"Circuit breaker is OPEN (retry after {self.config.circuit_breaker.timeout - elapsed:.1f}s)"
                )

    def _record_success(self) -> None:
        """Record successful request for circuit breaker."""
        if not self.config.circuit_breaker.enabled:
            return

        if self._circuit_state.state == CircuitState.HALF_OPEN:
            self._circuit_state.success_count += 1
            if (
                self._circuit_state.success_count
                >= self.config.circuit_breaker.success_threshold
            ):
                logger.info("Circuit breaker closing after successful requests")
                self._circuit_state.state = CircuitState.CLOSED
                self._circuit_state.failure_count = 0
        elif self._circuit_state.state == CircuitState.CLOSED:
            self._circuit_state.failure_count = 0

    def _record_failure(self) -> None:
        """Record failed request for circuit breaker."""
        if not self.config.circuit_breaker.enabled:
            return

        self._circuit_state.last_failure_time = time.time()

        if self._circuit_state.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker opening after failure in HALF_OPEN state")
            self._circuit_state.state = CircuitState.OPEN
            self._circuit_state.failure_count = 0
        elif self._circuit_state.state == CircuitState.CLOSED:
            self._circuit_state.failure_count += 1
            if (
                self._circuit_state.failure_count
                >= self.config.circuit_breaker.failure_threshold
            ):
                logger.warning(
                    f"Circuit breaker opening after {self._circuit_state.failure_count} failures"
                )
                self._circuit_state.state = CircuitState.OPEN

    def _prepare_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        """
        Prepare request headers with correlation ID.

        Args:
            headers: User-provided headers

        Returns:
            Dict[str, str]: Combined headers
        """
        combined = dict(self.config.headers)
        if headers:
            combined.update(headers)

        # Add correlation ID if available
        correlation_id = get_correlation_id()
        if correlation_id and "X-Correlation-ID" not in combined:
            combined["X-Correlation-ID"] = correlation_id
            combined["X-Request-ID"] = correlation_id

        return combined

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Execute HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments for httpx request

        Returns:
            httpx.Response: HTTP response

        Raises:
            HTTPError: If all retries exhausted or circuit breaker open
        """
        self._check_circuit_breaker()

        # Prepare headers
        headers = self._prepare_headers(kwargs.get("headers"))
        kwargs["headers"] = headers

        last_exception: Optional[Exception] = None

        for attempt in range(self.config.retry.max_retries + 1):
            try:
                logger.debug(
                    f"HTTP {method} {url} (attempt {attempt + 1}/{self.config.retry.max_retries + 1})"
                )

                response = self._client.request(method, url, **kwargs)
                response.raise_for_status()

                logger.debug(
                    f"HTTP {method} {url} -> {response.status_code} ({len(response.content)} bytes)"
                )

                self._record_success()
                return response

            except (httpx.HTTPError, httpx.RequestError) as e:
                last_exception = e
                logger.warning(
                    f"HTTP {method} {url} failed (attempt {attempt + 1}): {e}"
                )

                self._record_failure()

                # Don't retry on client errors (4xx) except 429 (rate limit)
                if isinstance(e, httpx.HTTPStatusError):
                    if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                        raise

                # If this was the last attempt, raise
                if attempt >= self.config.retry.max_retries:
                    raise

                # Calculate and apply delay
                delay = self._calculate_delay(attempt)
                logger.info(f"Retrying in {delay:.2f}s...")
                time.sleep(delay)

        # Should never reach here, but satisfy type checker
        if last_exception:
            raise last_exception
        raise httpx.HTTPError("Request failed with no exception")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Execute GET request with retry logic."""
        return self._request_with_retry("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Execute POST request with retry logic."""
        return self._request_with_retry("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Execute PUT request with retry logic."""
        return self._request_with_retry("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Execute PATCH request with retry logic."""
        return self._request_with_retry("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Execute DELETE request with retry logic."""
        return self._request_with_retry("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        """Execute HEAD request with retry logic."""
        return self._request_with_retry("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        """Execute OPTIONS request with retry logic."""
        return self._request_with_retry("OPTIONS", url, **kwargs)
