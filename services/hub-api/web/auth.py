"""
Web Authentication Decorators and Helpers for py4web.

Provides both the new scope-based auth fixtures (preferred) and legacy
session-cookie decorators kept for backward compatibility.

Migration guide
---------------
Old code using ``require_auth`` / ``require_role`` continues to work but
those decorators are **deprecated** — they rely on session cookies and the
internal UserManager.  New routes should use the OIDC Fixture pattern::

    from auth.oidc_fixture import OIDCFixture
    from auth.scope_fixture import ScopeFixture

    oidc = OIDCFixture()
    require_read = ScopeFixture("policies:read", oidc)

    @action("api/v1/policies")
    @action.uses(require_read)
    def list_policies():
        claims = request.local.claims  # pydantic Claims model
        ...
"""

from __future__ import annotations

import functools
import logging
import warnings
from typing import Optional

from py4web import request, response, redirect, URL, abort
from auth.user_manager import UserManager, User, UserRole

# Re-export new OIDC fixtures so callers can import from one place.
from auth.oidc_fixture import OIDCFixture  # noqa: F401
from auth.scope_fixture import ScopeFixture  # noqa: F401

logger = logging.getLogger(__name__)

# Global user manager instance (retained for legacy decorators)
user_manager = UserManager()


# ---------------------------------------------------------------------------
# OIDC scope-based helper (new preferred approach)
# ---------------------------------------------------------------------------

def require_scope(scope: str, oidc_fixture: Optional[OIDCFixture] = None) -> ScopeFixture:
    """Return a py4web Fixture that enforces a single OIDC scope.

    This is a thin wrapper that constructs an :class:`~auth.scope_fixture.ScopeFixture`
    using the provided (or a default) :class:`~auth.oidc_fixture.OIDCFixture`.

    Args:
        scope:        The required scope string (e.g. ``"policies:write"``).
        oidc_fixture: Optional existing OIDCFixture to reuse; creates a
                      new one from environment variables when omitted.

    Returns:
        A configured :class:`~auth.scope_fixture.ScopeFixture` ready for
        ``@action.uses()``.
    """
    rp_fixture = oidc_fixture if oidc_fixture is not None else OIDCFixture()
    return ScopeFixture(scope, rp_fixture)


# ---------------------------------------------------------------------------
# Legacy session-cookie decorators (deprecated — kept for backward compat)
# ---------------------------------------------------------------------------

def get_current_user() -> Optional[User]:
    """Get current authenticated user from session cookie.

    .. deprecated::
        Use :class:`~auth.oidc_fixture.OIDCFixture` with Bearer tokens
        and read ``request.local.claims`` instead.
    """
    import asyncio

    session_id = request.get_cookie("tobogganing_session")
    if not session_id:
        return None

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run, user_manager.validate_session(session_id)
                )
                return future.result(timeout=5)
        return loop.run_until_complete(user_manager.validate_session(session_id))
    except Exception:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(user_manager.validate_session(session_id))
        except Exception as exc:
            logger.warning("Session validation failed: %s", exc)
            return None


def require_auth(f):  # type: ignore[no-untyped-def]
    """Require an authenticated session cookie.

    .. deprecated::
        Use :class:`~auth.oidc_fixture.OIDCFixture` with ``@action.uses()``
        for new routes.  This decorator validates a session cookie via the
        internal UserManager; it does not validate OIDC Bearer tokens.
    """
    warnings.warn(
        "require_auth is deprecated; use OIDCFixture with @action.uses() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):  # type: ignore[no-untyped-def]
        user = get_current_user()
        if not user:
            if request.headers.get("Accept", "").startswith("application/json"):
                response.status = 401
                return {"error": "Authentication required"}
            return redirect(URL("login"))

        request.user = user
        return f(*args, **kwargs)

    return decorated_function


def require_role(role: UserRole):  # type: ignore[no-untyped-def]
    """Require a specific legacy role.

    .. deprecated::
        Use :func:`require_scope` or :class:`~auth.scope_fixture.ScopeFixture`
        with OIDC scopes instead.
    """
    warnings.warn(
        "require_role is deprecated; use ScopeFixture with OIDC scopes instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def decorator(f):  # type: ignore[no-untyped-def]
        @functools.wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):  # type: ignore[no-untyped-def]
            user = request.user
            if user.role != role and user.role != UserRole.ADMIN:
                if request.headers.get("Accept", "").startswith("application/json"):
                    response.status = 403
                    return {"error": f"Role {role.value} required"}
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_permission(permission: str):  # type: ignore[no-untyped-def]
    """Require a specific legacy permission.

    .. deprecated::
        Use :func:`require_scope` or :class:`~auth.scope_fixture.ScopeFixture`
        with OIDC scopes instead.
    """
    warnings.warn(
        "require_permission is deprecated; use ScopeFixture with OIDC scopes instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def decorator(f):  # type: ignore[no-untyped-def]
        @functools.wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):  # type: ignore[no-untyped-def]
            user = request.user
            if not user_manager.has_permission(user, permission):
                if request.headers.get("Accept", "").startswith("application/json"):
                    response.status = 403
                    return {"error": f"Permission {permission} required"}
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator

async def create_user_session(user: User) -> str:
    """Create session and set cookie"""
    user_agent = request.headers.get('User-Agent', '')
    ip_address = request.environ.get('REMOTE_ADDR', '')
    
    session = await user_manager.create_session(user, user_agent, ip_address)
    
    # Set secure cookie
    response.set_cookie(
        "tobogganing_session",
        session.session_id,
        max_age=8*3600,  # 8 hours
        secure=True if request.headers.get('X-Forwarded-Proto') == 'https' else False,
        httponly=True,
        samesite='Lax'
    )
    
    return session.session_id

async def logout_user():
    """Logout current user"""
    session_id = request.get_cookie("tobogganing_session")
    if session_id:
        await user_manager.logout(session_id)
    
    # Clear cookie
    response.set_cookie(
        "tobogganing_session", 
        "", 
        max_age=0,
        secure=True if request.headers.get('X-Forwarded-Proto') == 'https' else False,
        httponly=True
    )