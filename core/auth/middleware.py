"""Authentication middleware for tenant-first + scope-based authorization."""

from __future__ import annotations

import functools
from typing import Any, Callable, Optional

from quart import current_app, g, jsonify, request

from core.auth.jwt import decode_token


def _scope_satisfied(required: str, granted: set[str]) -> bool:
    """Check if a required scope is satisfied by granted scopes.

    Supports exact match and wildcard patterns:
    - Exact: 'resource:action'
    - Wildcard resource: 'resource:*'
    - Wildcard action: '*:action'
    - Wildcard all: '*:*'

    Args:
        required: Required scope (e.g., 'clusters:read').
        granted: Set of granted scopes from token.

    Returns:
        True if required scope is satisfied, False otherwise.
    """
    # Check if exactly present or wildcard all
    if required in granted or "*:*" in granted:
        return True

    # Check wildcard patterns (must have ':' separator)
    if ":" in required:
        resource, action = required.split(":", 1)
        # Check *:action or resource:*
        return f"*:{action}" in granted or f"{resource}:*" in granted

    # Invalid format (no colon)
    return False


def _extract_token_from_header() -> str | None:
    """Extract JWT token from Authorization header.

    Expected format: Authorization: Bearer <token>

    Returns:
        Token string if present, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]  # Remove "Bearer " prefix


def current_claims() -> dict[str, Any] | None:
    """Get validated claims from current request context.

    Returns:
        Dictionary of JWT claims if token valid, None otherwise.
    """
    if not hasattr(g, "claims"):
        return None
    return g.claims


async def _validate_and_store_token() -> bool:
    """Validate JWT token and store claims in request context.

    Stores decoded claims in g.claims if token is valid.

    Returns:
        True if token valid, False otherwise.
    """
    if hasattr(g, "claims"):
        # Already validated in this request
        return g.claims is not None

    token = _extract_token_from_header()
    if not token:
        g.claims = None
        return False

    key_provider = current_app.config.get("KEY_PROVIDER")
    if not key_provider:
        g.claims = None
        return False

    claims = decode_token(token, key_provider)
    g.claims = claims
    return claims is not None


def require_tenant(func: Callable) -> Callable:
    """Decorator to require a valid tenant claim.

    Runs first, before any scope checks. Returns 403 if tenant claim is missing
    or the token is invalid.

    Args:
        func: Async route handler to protect.

    Returns:
        Decorated function.
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Validate token and extract claims
        token_valid = await _validate_and_store_token()

        if not token_valid:
            return jsonify({"error": "Unauthorized: missing or invalid token"}), 403

        claims = current_claims()
        if not claims:
            return jsonify({"error": "Unauthorized: invalid token"}), 403

        # Verify tenant claim is present
        if "tenant" not in claims:
            return jsonify({"error": "Unauthorized: missing tenant claim"}), 403

        # Call the original handler
        return await func(*args, **kwargs)

    return wrapper


def require_scope(*required_scopes: str) -> Callable:
    """Decorator to require specific scopes.

    Returns 403 unless token's scope set satisfies all required scopes.
    Checks scopes only, never branches on role names.

    Supports wildcard matching:
    - Exact match: 'resource:action'
    - Wildcard resource: 'resource:*'
    - Wildcard action: '*:action'
    - Wildcard all: '*:*'

    Args:
        required_scopes: Variable number of required scope strings.
                        Each scope is matched with exact or wildcard patterns.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Validate token and extract claims (tenant-first runs here implicitly)
            token_valid = await _validate_and_store_token()

            if not token_valid:
                return jsonify({"error": "Unauthorized: missing or invalid token"}), 403

            claims = current_claims()
            if not claims:
                return jsonify({"error": "Unauthorized: invalid token"}), 403

            # Verify tenant claim is present (tenant-first)
            if "tenant" not in claims:
                return jsonify({"error": "Unauthorized: missing tenant claim"}), 403

            # Check scopes
            token_scope = claims.get("scope", "")
            if not token_scope:
                return jsonify({"error": "Forbidden: insufficient privileges"}), 403

            # Parse token scopes (space-separated)
            token_scopes = set(token_scope.split())

            # Verify all required scopes are satisfied
            for required_scope in required_scopes:
                if not _scope_satisfied(required_scope, token_scopes):
                    return jsonify({"error": "Forbidden: insufficient privileges"}), 403

            # Call the original handler
            return await func(*args, **kwargs)

        return wrapper

    return decorator
