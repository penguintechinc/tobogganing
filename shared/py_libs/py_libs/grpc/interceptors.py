"""gRPC security interceptors for authentication, rate limiting, and audit logging."""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

import grpc
import jwt

logger = logging.getLogger(__name__)


class AuthInterceptor(grpc.ServerInterceptor):
    """JWT authentication and scope-based authorization interceptor for gRPC servers.

    Validates JWT tokens in metadata and, when a method has required scopes
    configured, enforces OIDC scope-based authorization before invoking the
    handler — never role names, per org standard (security.md JWT Claims).
    """

    def __init__(
        self,
        secret_key: str,
        algorithms: list[str] | None = None,
        public_methods: set[str] | None = None,
        method_scopes: dict[str, set[str]] | None = None,
    ):
        """Initialize auth interceptor.

        Args:
            secret_key: JWT secret key for validation
            algorithms: List of allowed JWT algorithms (default: ['HS256'])
            public_methods: Set of method names that don't require auth
            method_scopes: Optional mapping of method name -> set of required
                OIDC scopes (`resource:action` format). All listed scopes must
                be present in the token's `scope` claim for the call to be
                authorized. Methods with no entry are authenticated only —
                callers that need authorization must configure this.

        """
        self.secret_key = secret_key
        self.algorithms = algorithms or ["HS256"]
        self.public_methods = public_methods or set()
        self.method_scopes = {
            method: set(scopes) for method, scopes in (method_scopes or {}).items()
        }

    def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], grpc.RpcMethodHandler],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept and validate authentication."""
        method = handler_call_details.method

        # Skip auth for public methods
        if method in self.public_methods:
            return continuation(handler_call_details)

        # Extract token from metadata
        metadata = dict(handler_call_details.invocation_metadata)
        auth_header = metadata.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            logger.warning(f"Missing or invalid auth header for {method}")
            return self._abort_with_error(
                grpc.StatusCode.UNAUTHENTICATED,
                "Missing or invalid authorization header",
            )

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        try:
            # Validate JWT token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=self.algorithms,
            )

            # Add user info to context (can be retrieved in handlers)
            user_id = payload.get("sub")

            # Scope-based authorization (OIDC scopes, never role names)
            required_scopes = self.method_scopes.get(method)
            if required_scopes:
                token_scopes = set(str(payload.get("scope", "")).split())
                if not required_scopes.issubset(token_scopes):
                    logger.warning(
                        f"Insufficient scope for {method}",
                        extra={
                            "user_id": user_id,
                            "required_scopes": sorted(required_scopes),
                            "token_scopes": sorted(token_scopes),
                        },
                    )
                    return self._abort_with_error(
                        grpc.StatusCode.PERMISSION_DENIED,
                        "Insufficient scope for this operation",
                    )

            logger.info(f"Authenticated request to {method}", extra={"user_id": user_id})

            return continuation(handler_call_details)

        except jwt.ExpiredSignatureError:
            logger.warning(f"Expired token for {method}")
            return self._abort_with_error(grpc.StatusCode.UNAUTHENTICATED, "Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token for {method}: {e}")
            return self._abort_with_error(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")

    def _abort_with_error(
        self,
        code: grpc.StatusCode,
        details: str,
    ) -> grpc.RpcMethodHandler:
        """Return an RPC handler that aborts with error."""

        def abort(request: Any, context: grpc.ServicerContext) -> None:
            context.abort(code, details)

        return grpc.unary_unary_rpc_method_handler(
            abort,
            request_deserializer=lambda x: x,
            response_serializer=lambda x: x,
        )


@dataclass(slots=True)
class RateLimitEntry:
    """Track rate limit for a client."""

    count: int = 0
    window_start: float = 0.0


class RateLimitInterceptor(grpc.ServerInterceptor):
    """Rate limiting interceptor with per-client limits.

    Implements sliding window rate limiting.
    """

    def __init__(
        self,
        requests_per_minute: int = 100,
        per_user: bool = True,
        secret_key: str | None = None,
        algorithms: list[str] | None = None,
    ):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
            per_user: Rate limit per user (True) or per IP (False)
            secret_key: JWT secret key used to verify the token's signature
                before trusting its `sub` claim as the rate-limit identity.
                Pass the same key configured on `AuthInterceptor`. Required
                for `per_user=True` — without it, the `sub` claim cannot be
                trusted (an unverified decode would let a caller forge any
                identity to dodge or frame another client's limit), so the
                limiter falls back to IP-based identification instead.
            algorithms: List of allowed JWT algorithms (default: ['HS256'])

        """
        self.requests_per_minute = requests_per_minute
        self.per_user = per_user
        self.secret_key = secret_key
        self.algorithms = algorithms or ["HS256"]
        self.limits: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self.lock = Lock()

    def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], grpc.RpcMethodHandler],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept and check rate limits."""
        # Determine client identifier
        metadata = dict(handler_call_details.invocation_metadata)

        if self.per_user:
            # Extract user from token — signature MUST be verified before the
            # `sub` claim is trusted for a security decision (rate limiting).
            # An unverified decode would let any caller forge a `sub` to
            # dodge their own limit or frame another client's identity.
            auth_header = metadata.get("authorization", "")
            if auth_header.startswith("Bearer ") and self.secret_key:
                try:
                    token = auth_header[7:]
                    payload = jwt.decode(token, self.secret_key, algorithms=self.algorithms)
                    client_id = payload.get("sub", "anonymous")
                except jwt.InvalidTokenError:
                    client_id = "anonymous"
            elif auth_header.startswith("Bearer ") and not self.secret_key:
                # No key material configured to verify the token — fall back
                # to IP-based limiting rather than trusting an unverified sub.
                logger.warning(
                    "RateLimitInterceptor per_user=True without secret_key; "
                    "falling back to IP-based rate limiting"
                )
                client_id = metadata.get("x-forwarded-for", "unknown")
            else:
                client_id = "anonymous"
        else:
            # Use peer address (IP)
            client_id = metadata.get("x-forwarded-for", "unknown")

        # Check rate limit
        current_time = time.time()

        with self.lock:
            entry = self.limits[client_id]

            # Reset window if expired
            if current_time - entry.window_start >= 60.0:
                entry.count = 0
                entry.window_start = current_time

            # Check limit
            if entry.count >= self.requests_per_minute:
                logger.warning(
                    f"Rate limit exceeded for {client_id}",
                    extra={
                        "client_id": client_id,
                        "requests": entry.count,
                    },
                )
                return self._abort_with_error(
                    grpc.StatusCode.RESOURCE_EXHAUSTED, "Rate limit exceeded"
                )

            # Increment counter
            entry.count += 1

        return continuation(handler_call_details)

    def _abort_with_error(
        self,
        code: grpc.StatusCode,
        details: str,
    ) -> grpc.RpcMethodHandler:
        """Return an RPC handler that aborts with error."""

        def abort(request: Any, context: grpc.ServicerContext) -> None:
            context.abort(code, details)

        return grpc.unary_unary_rpc_method_handler(
            abort,
            request_deserializer=lambda x: x,
            response_serializer=lambda x: x,
        )


class AuditInterceptor(grpc.ServerInterceptor):
    """Audit logging interceptor for request/response tracking.

    Logs method calls, duration, and status codes.
    """

    def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], grpc.RpcMethodHandler],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept and log requests."""
        method = handler_call_details.method
        start_time = time.time()

        # Get correlation ID from metadata
        metadata = dict(handler_call_details.invocation_metadata)
        correlation_id = metadata.get("x-correlation-id", "unknown")

        logger.info(
            f"gRPC request started: {method}",
            extra={
                "method": method,
                "correlation_id": correlation_id,
            },
        )

        handler = continuation(handler_call_details)

        # Wrap handler to log completion
        if handler and handler.unary_unary:
            original_handler = handler.unary_unary

            def logged_handler(request: Any, context: grpc.ServicerContext) -> Any:
                try:
                    response = original_handler(request, context)
                    duration_ms = (time.time() - start_time) * 1000

                    logger.info(
                        f"gRPC request completed: {method}",
                        extra={
                            "method": method,
                            "duration_ms": duration_ms,
                            "correlation_id": correlation_id,
                            "status": "OK",
                        },
                    )
                    return response

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000

                    logger.error(
                        f"gRPC request failed: {method}",
                        extra={
                            "method": method,
                            "duration_ms": duration_ms,
                            "correlation_id": correlation_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    raise

            return grpc.unary_unary_rpc_method_handler(
                logged_handler,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler


class CorrelationInterceptor(grpc.ServerInterceptor):
    """Correlation ID interceptor for request tracing.

    Adds or propagates correlation IDs across service calls.
    """

    def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], grpc.RpcMethodHandler],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept and add correlation ID."""
        metadata = dict(handler_call_details.invocation_metadata)

        # Get or create correlation ID
        correlation_id = metadata.get("x-correlation-id")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
            logger.debug(f"Generated new correlation ID: {correlation_id}")

        # Store in context for handlers to access
        # (This would typically use contextvars in production)

        return continuation(handler_call_details)


class RecoveryInterceptor(grpc.ServerInterceptor):
    """Recovery interceptor for exception handling.

    Catches unexpected exceptions and returns proper gRPC errors.
    """

    def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], grpc.RpcMethodHandler],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept and handle exceptions."""
        handler = continuation(handler_call_details)

        if handler and handler.unary_unary:
            original_handler = handler.unary_unary

            def recovery_handler(request: Any, context: grpc.ServicerContext) -> Any:
                try:
                    return original_handler(request, context)

                except grpc.RpcError:
                    # Let gRPC errors pass through
                    raise

                except Exception as e:
                    # Convert unexpected exceptions to gRPC errors
                    method = handler_call_details.method
                    error_trace = traceback.format_exc()

                    logger.error(
                        f"Unexpected error in {method}",
                        extra={
                            "method": method,
                            "error": str(e),
                            "trace": error_trace,
                        },
                        exc_info=True,
                    )

                    context.abort(grpc.StatusCode.INTERNAL, f"Internal server error: {str(e)}")

            return grpc.unary_unary_rpc_method_handler(
                recovery_handler,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler
