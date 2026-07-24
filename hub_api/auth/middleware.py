"""Authentication middleware for tenant-first + scope-based authorization.

Supports both Bearer/JWT (via @require_scope, @require_tenant) and session cookie
(via @require_session_user, @require_role, @require_permission) authentication paths.
"""

from __future__ import annotations

import functools
from datetime import datetime
from typing import Any, Callable, Optional

import structlog
from quart import current_app, g, jsonify, request, Response

from hub_api.auth.jwt import decode_token

logger = structlog.get_logger()


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


def require_tenant(func: Callable[..., Any]) -> Callable[..., Any]:
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


def require_scope(*required_scopes: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
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

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
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


# Session-based authentication (SASE module)


async def _validate_and_store_session(
    session_token: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate session cookie via DAL and return (user_dict, tenant).

    Args:
        session_token: Session token from cookie.

    Returns:
        Tuple of (user_dict, tenant) if valid, (None, None) otherwise.
        user_dict contains: id, username, email, role, tenant, created_at, is_active.
    """
    if not session_token:
        return None, None

    try:
        dal = current_app.config.get("DAL")
        if not dal:
            logger.error("session_validation_failed", reason="dal_not_configured")
            return None, None

        # Query session via DAL (session token is unique)
        rowset = await dal(dal.sessions.token == session_token).select()
        session_row = rowset.first()

        if not session_row:
            logger.debug("session_not_found", token=session_token[:8])
            return None, None

        # Check if session is expired
        if session_row.expires_at < datetime.utcnow():
            logger.debug(
                "session_expired",
                session_id=session_row.id[:8],
                token=session_token[:8],
            )
            # Clean up expired session
            await dal(dal.sessions.id == session_row.id).delete()
            return None, None

        # Get user for this session (tenant-scoped)
        user_rowset = await dal(
            dal.users.id == session_row.user_id,
            dal.users.tenant == session_row.tenant,
            dal.users.is_active == True,  # noqa: E712
        ).select()

        user_row = user_rowset.first()
        if not user_row:
            logger.debug(
                "user_not_found_for_session",
                user_id=session_row.user_id,
                tenant=session_row.tenant,
            )
            return None, None

        user_dict = {
            "id": user_row.id,
            "username": user_row.username,
            "email": user_row.email,
            "role": user_row.role or "reporter",
            "tenant": user_row.tenant,
            "created_at": user_row.created_at,
            "is_active": bool(user_row.is_active),
        }

        return user_dict, session_row.tenant

    except Exception as e:
        logger.error("session_validation_error", token=session_token[:8], error=str(e))
        return None, None


def require_session_user(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to require a valid session cookie.

    Reads `sasewaddle_session` cookie, validates it via the DAL, and attaches
    the authenticated user to `g.user` with tenant isolation. Returns 401 if
    the cookie is missing, invalid, or expired.

    Args:
        func: Async route handler to protect.

    Returns:
        Decorated function.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        session_token = request.cookies.get("sasewaddle_session")
        if not session_token:
            logger.debug("session_cookie_missing")
            return jsonify({"error": "Unauthorized: session cookie required"}), 401

        user_dict, tenant = await _validate_and_store_session(session_token)
        if not user_dict or not tenant:
            logger.warning("session_validation_failed", token=session_token[:8])
            return jsonify({"error": "Unauthorized: invalid or expired session"}), 401

        # Attach user and tenant to request context
        g.user = user_dict
        g.tenant = tenant

        logger.info(
            "session_authenticated",
            user_id=user_dict["id"],
            username=user_dict["username"],
            tenant=tenant,
        )

        return await func(*args, **kwargs)

    return wrapper


def require_role(role: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to require a specific role.

    Must be used with @require_session_user or after session validation.
    Allows admin role to bypass (admin has all permissions).

    Args:
        role: Required role name (e.g., "admin", "reporter").

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Ensure session is validated first
            if not hasattr(g, "user"):
                return jsonify({"error": "Unauthorized: session required"}), 401

            user = g.user
            user_role = user.get("role", "reporter")

            # Admin bypasses all role checks
            if user_role == "admin" or user_role == role:
                return await func(*args, **kwargs)

            logger.warning(
                "role_check_failed",
                user_id=user.get("id"),
                required_role=role,
                user_role=user_role,
            )
            return jsonify({"error": f"Forbidden: role {role} required"}), 403

        return wrapper

    return decorator


def require_permission(perm: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to require a specific permission.

    Permission is checked via role-based mapping (admin has all, reporter has read-only).
    Must be used with @require_session_user or after session validation.

    Args:
        perm: Permission name (e.g., "view_dashboard", "edit_rules").

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Ensure session is validated first
            if not hasattr(g, "user"):
                return jsonify({"error": "Unauthorized: session required"}), 401

            user = g.user
            user_role = user.get("role", "reporter")

            # Admin has all permissions
            if user_role == "admin":
                return await func(*args, **kwargs)

            # Reporter permissions (read-only)
            reporter_permissions = {
                "view_dashboard",
                "view_metrics",
                "view_clients",
                "view_clusters",
                "view_status",
                "view_rules",
            }

            if user_role == "reporter" and perm in reporter_permissions:
                return await func(*args, **kwargs)

            logger.warning(
                "permission_check_failed",
                user_id=user.get("id"),
                required_permission=perm,
                user_role=user_role,
            )
            return jsonify({"error": f"Forbidden: permission {perm} required"}), 403

        return wrapper

    return decorator


def require_admin(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to require admin access.

    Allows admin via:
    - Session role == "admin"
    - Bearer JWT with scope "*:admin"

    Returns 403 if neither condition is met. Supports both session and JWT auth.

    Args:
        func: Async route handler to protect.

    Returns:
        Decorated function.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Check session auth first
        if hasattr(g, "user"):
            user = g.user
            if user.get("role") == "admin":
                logger.info("admin_access_granted_via_session", user_id=user.get("id"))
                return await func(*args, **kwargs)

        # Check JWT auth (Bearer token)
        token_valid = await _validate_and_store_token()
        if token_valid:
            claims = current_claims()
            if claims and "tenant" in claims:
                token_scopes = set(claims.get("scope", "").split())
                if _scope_satisfied("*:admin", token_scopes):
                    logger.info(
                        "admin_access_granted_via_jwt",
                        user_id=claims.get("sub"),
                    )
                    return await func(*args, **kwargs)

        logger.warning("admin_access_denied")
        return jsonify({"error": "Forbidden: admin role required"}), 403

    return wrapper


def set_session_cookie(
    response: Response,
    session_id: str,
) -> None:
    """Set secure session cookie on response.

    Attributes: max_age 8h, httponly, samesite=Lax, secure if X-Forwarded-Proto == https.

    Args:
        response: Quart response object.
        session_id: Session token to set in cookie.
    """
    secure = request.headers.get("X-Forwarded-Proto", "").lower() == "https"

    response.set_cookie(
        "sasewaddle_session",
        session_id,
        max_age=8 * 3600,  # 8 hours
        httponly=True,
        samesite="Lax",
        secure=secure,
    )

    logger.info(
        "session_cookie_set",
        secure=secure,
        max_age_hours=8,
    )


def clear_session_cookie(response: Response) -> None:
    """Clear session cookie from response.

    Args:
        response: Quart response object.
    """
    response.set_cookie(
        "sasewaddle_session",
        "",
        max_age=0,
        httponly=True,
        samesite="Lax",
    )

    logger.info("session_cookie_cleared")
