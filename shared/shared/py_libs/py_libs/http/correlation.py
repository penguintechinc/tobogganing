"""
Request correlation ID middleware for Flask applications.

Provides correlation ID generation and propagation for request tracing
across microservices.
"""

import uuid
from contextvars import ContextVar
from typing import Optional

from flask import Flask, Request, g, request

# Context variable for storing correlation ID
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def generate_correlation_id() -> str:
    """
    Generate a new correlation ID using UUID4.

    Returns:
        str: A new UUID4 string suitable for correlation tracking
    """
    return str(uuid.uuid4())


def get_correlation_id() -> Optional[str]:
    """
    Get the current correlation ID from context.

    Returns:
        Optional[str]: Current correlation ID or None if not set
    """
    # Try context variable first (for async contexts)
    correlation_id = _correlation_id.get()
    if correlation_id:
        return correlation_id

    # Fall back to Flask's g object (for request contexts)
    return getattr(g, "correlation_id", None)


def _extract_correlation_id(req: Request) -> str:
    """
    Extract correlation ID from request headers or generate new one.

    Checks X-Correlation-ID and X-Request-ID headers in order.

    Args:
        req: Flask request object

    Returns:
        str: Extracted or newly generated correlation ID
    """
    # Check X-Correlation-ID first (preferred)
    correlation_id = req.headers.get("X-Correlation-ID")
    if correlation_id:
        return correlation_id

    # Fall back to X-Request-ID
    correlation_id = req.headers.get("X-Request-ID")
    if correlation_id:
        return correlation_id

    # Generate new correlation ID
    return generate_correlation_id()


class CorrelationMiddleware:
    """
    Flask middleware for correlation ID handling.

    Extracts correlation IDs from incoming requests or generates new ones,
    stores them in request context, and adds them to response headers.

    Example:
        app = Flask(__name__)
        middleware = CorrelationMiddleware(app)

        @app.route('/api/v1/example')
        def example():
            correlation_id = get_correlation_id()
            logger.info("Processing request", extra={"correlation_id": correlation_id})
            return {"status": "ok"}
    """

    def __init__(self, app: Optional[Flask] = None) -> None:
        """
        Initialize correlation middleware.

        Args:
            app: Flask application instance (optional, can use init_app later)
        """
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """
        Initialize the middleware with a Flask application.

        Args:
            app: Flask application instance
        """
        self.app = app

        @app.before_request
        def before_request() -> None:
            """Extract or generate correlation ID before processing request."""
            correlation_id = _extract_correlation_id(request)
            g.correlation_id = correlation_id
            _correlation_id.set(correlation_id)

        @app.after_request
        def after_request(response):
            """Add correlation ID to response headers."""
            correlation_id = get_correlation_id()
            if correlation_id:
                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Request-ID"] = correlation_id
            return response

        @app.teardown_request
        def teardown_request(exception=None) -> None:
            """Clean up correlation ID from context."""
            _correlation_id.set(None)
