"""
HTTP module - HTTP utilities.

Provides:
- correlation: Request ID/correlation middleware
- client: Resilient HTTP client with retries
"""

from .client import (
    CircuitBreakerConfig,
    CircuitState,
    HTTPClient,
    HTTPClientConfig,
    RetryConfig,
)
from .correlation import (
    CorrelationMiddleware,
    generate_correlation_id,
    get_correlation_id,
)

__all__ = [
    # Correlation ID utilities
    "CorrelationMiddleware",
    "generate_correlation_id",
    "get_correlation_id",
    # HTTP client
    "HTTPClient",
    "HTTPClientConfig",
    "RetryConfig",
    "CircuitBreakerConfig",
    "CircuitState",
]
