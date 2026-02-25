"""
Scope-based authorization middleware for py4web.

Provides JWT extraction, tenant resolution, and scope enforcement decorators.
The primary decorator for endpoints is ``require_scope``, which composes both
tenant and scope checks in a single application.

Usage::

    from auth.middleware import require_scope

    @action("api/v1/policies", method=["GET"])
    @require_scope("policies:read")
    def list_policies():
        tenant = request.tenant       # TenantContext
        claims = request.jwt_claims   # dict
        ...
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from typing import Any, Callable, Optional

import structlog
from py4web import request, response

from auth.scopes import has_required_scopes, parse_scope_string
from database.models import TenantContext

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# JWT manager — lazy singleton to avoid import-time side effects
# ---------------------------------------------------------------------------

_jwt_manager = None


def _get_jwt_manager():
    """Return the module-level JWTManager singleton, creating it on first call."""
    global _jwt_manager
    if _jwt_manager is None:
        from auth.jwt_manager import JWTManager
        _jwt_manager = JWTManager()
    return _jwt_manager


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine from synchronous py4web decorator context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running inside an existing loop (e.g. tests or ASGI)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
            asyncio.set_event_loop(None)


# ---------------------------------------------------------------------------
# Error response helpers
# ---------------------------------------------------------------------------

def _error_response(status_code: int, message: str, **extra) -> dict:
    """Return an envelope-format error dict and set the response status."""
    response.status = status_code
    response.headers["Content-Type"] = "application/json"
    data: dict[str, Any] = {"message": message}
    data.update(extra)
    return {"status": "error", "data": data}


# ---------------------------------------------------------------------------
# 1. get_jwt_claims
# ---------------------------------------------------------------------------

def get_jwt_claims() -> Optional[dict[str, Any]]:
    """Extract and validate JWT claims from the Authorization header.

    Looks for a ``Bearer <token>`` header in the current request and calls
    :meth:`~auth.jwt_manager.JWTManager.validate_token` to verify the
    signature and Redis active-status check.

    Returns:
        The decoded JWT payload dict on success, or ``None`` if the header is
        absent, malformed, or the token is invalid / revoked / expired.
    """
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[len("Bearer "):]
    if not token:
        return None

    try:
        claims = _run_async(_get_jwt_manager().validate_token(token))
        return claims
    except Exception:
        logger.warning("JWT validation raised an exception", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# 2. tenant_required
# ---------------------------------------------------------------------------

def tenant_required(f: Callable) -> Callable:
    """Decorator: resolve the ``tenant`` JWT claim to a live TenantContext.

    Must run before :func:`scope_required`.  Attaches the resolved context
    to ``request.tenant`` and the raw claims to ``request.jwt_claims`` so
    downstream decorators and handlers can access them without repeating the
    header parse.

    Behaviour:
    - No / invalid JWT       → 401 (missing authentication, not a 403).
    - Missing tenant claim   → 403.
    - Tenant not found in DB → 403.
    - Tenant not active      → 403.

    Args:
        f: The py4web action function to wrap.

    Returns:
        The wrapped function preserving the original name and docstring.
    """
    @functools.wraps(f)
    def _wrapper(*args, **kwargs):
        claims = get_jwt_claims()

        if claims is None:
            return _error_response(401, "Authentication required")

        # Attach raw claims early so downstream code can use them
        request.jwt_claims = claims

        tenant_claim: Optional[str] = claims.get("tenant")
        if not tenant_claim:
            return _error_response(403, "Tenant claim required")

        # PyDAL lookup — runtime-only, migrate=False
        try:
            from database import get_db
            db = get_db()
            row = db(
                db.tenants.tenant_id == tenant_claim
            ).select(
                db.tenants.tenant_id,
                db.tenants.name,
                db.tenants.spiffe_trust_domain,
                db.tenants.is_active,
            ).first()
        except Exception:
            logger.exception("DB error during tenant lookup", tenant_id=tenant_claim)
            return _error_response(503, "Service temporarily unavailable")

        if row is None:
            logger.warning("Tenant not found", tenant_id=tenant_claim)
            return _error_response(403, "Tenant not found or access denied")

        if not row.is_active:
            logger.warning("Tenant is inactive", tenant_id=tenant_claim)
            return _error_response(403, "Tenant is inactive")

        request.tenant = TenantContext(
            tenant_id=row.tenant_id,
            name=row.name,
            spiffe_trust_domain=row.spiffe_trust_domain,
            is_active=row.is_active,
        )

        return f(*args, **kwargs)

    return _wrapper


# ---------------------------------------------------------------------------
# 3. scope_required
# ---------------------------------------------------------------------------

def scope_required(*required_scopes: str) -> Callable:
    """Decorator factory: enforce that the caller holds all *required_scopes*.

    Expects ``request.jwt_claims`` to already be set (i.e. :func:`tenant_required`
    ran first).  The ``scope`` claim is treated as a space-delimited RFC 9068
    string and expanded by :func:`~auth.scopes.parse_scope_string`.

    Wildcard rules (``*:read``, ``*:*``, etc.) are resolved by
    :func:`~auth.scopes.has_required_scopes`.

    Args:
        *required_scopes: One or more scope strings the endpoint requires,
            e.g. ``"policies:read"``, ``"users:admin"``.

    Returns:
        A decorator that wraps the target function.

    Example::

        @scope_required("policies:read", "hubs:read")
        def list_policies(): ...
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def _wrapper(*args, **kwargs):
            # Retrieve claims — set by tenant_required; fall back to fresh parse.
            claims: Optional[dict[str, Any]] = getattr(request, "jwt_claims", None)
            if claims is None:
                claims = get_jwt_claims()
                if claims is None:
                    return _error_response(401, "Authentication required")
                request.jwt_claims = claims

            scope_string: str = claims.get("scope", "") or claims.get("scopes", "") or ""
            # ``scope`` may also arrive as a list when issued internally
            if isinstance(scope_string, list):
                user_scopes: list[str] = scope_string
            else:
                user_scopes = parse_scope_string(str(scope_string))

            scopes_needed = list(required_scopes)

            if not has_required_scopes(scopes_needed, user_scopes):
                logger.warning(
                    "Insufficient scopes",
                    required=scopes_needed,
                    available=user_scopes,
                )
                return _error_response(
                    403,
                    "Insufficient scopes",
                    required=scopes_needed,
                    available=user_scopes,
                )

            return f(*args, **kwargs)

        return _wrapper

    return decorator


# ---------------------------------------------------------------------------
# 4. require_scope  (combined entry-point)
# ---------------------------------------------------------------------------

def require_scope(*scopes: str) -> Callable:
    """Combined decorator: apply tenant resolution and scope enforcement.

    This is the **primary decorator** that API endpoints should use.  It
    composes :func:`tenant_required` and :func:`scope_required` so callers
    only need a single decorator line.

    Application order (outer → inner):

    1. :func:`scope_required` — wraps the handler first (innermost).
    2. :func:`tenant_required` — wraps the scope-guarded handler (outermost
       at runtime, so it runs first in the call chain).

    This ensures ``request.jwt_claims`` is always populated before the scope
    check executes.

    Args:
        *scopes: One or more required scope strings
            (e.g. ``"policies:read"``).

    Returns:
        A single decorator that enforces both tenant presence and scope
        membership.

    Example::

        from auth.middleware import require_scope

        @action("api/v1/policies", method=["GET"])
        @require_scope("policies:read")
        def list_policies():
            tenant = request.tenant       # TenantContext
            claims = request.jwt_claims   # dict[str, Any]
            ...

        @action("api/v1/policies/<policy_id>", method=["DELETE"])
        @require_scope("policies:delete")
        def delete_policy(policy_id: str):
            ...
    """
    def decorator(f: Callable) -> Callable:
        # Build the chain: tenant_required -> scope_required -> f
        scope_guarded = scope_required(*scopes)(f)
        tenant_and_scope_guarded = tenant_required(scope_guarded)

        # Preserve the original function's identity on the outermost wrapper
        @functools.wraps(f)
        def _wrapper(*args, **kwargs):
            return tenant_and_scope_guarded(*args, **kwargs)

        return _wrapper

    return decorator
