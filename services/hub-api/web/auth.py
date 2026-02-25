"""
Web Authentication Decorators and Helpers for py4web

Implements scope-based authorization using RFC 9068 OAuth 2.0 scope format.
Scopes follow the pattern: resource:action (e.g., policies:read, users:admin).
"""

import functools
from typing import Optional
from py4web import request, response, redirect, URL, abort
from auth.user_manager import UserManager, User, UserRole

# Global user manager instance
user_manager = UserManager()

# Backward compatibility mapping from old permission strings to scope format
_PERMISSION_TO_SCOPE = {
    "view_dashboard": "*:read",
    "view_metrics": "*:read",
    "view_clients": "clients:read",
    "view_clusters": "clusters:read",
    "view_status": "*:read",
}

def get_current_user() -> Optional[User]:
    """Get current authenticated user from session

    Also loads tenant_id from database if available.
    """
    session_id = request.get_cookie("sasewaddle_session")
    if not session_id:
        return None

    # This would normally be async, but py4web decorators need sync
    # In production, consider using async/await patterns
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        user = loop.run_until_complete(user_manager.validate_session(session_id))
    except:
        # Create new event loop if none exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        user = loop.run_until_complete(user_manager.validate_session(session_id))

    # Load tenant_id from database if available
    if user and not hasattr(user, 'tenant_id'):
        try:
            from database import db
            user_row = db(db.users.id == user.id).select().first()
            if user_row and hasattr(user_row, 'tenant_id'):
                user.tenant_id = user_row.tenant_id
        except Exception:
            # DB may not be initialized or user not in database yet
            pass

    return user

def require_auth(f):
    """Decorator to require authentication"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.headers.get('Accept', '').startswith('application/json'):
                response.status = 401
                return {"error": "Authentication required"}
            else:
                return redirect(URL('login'))
        
        # Add user to request context
        request.user = user
        return f(*args, **kwargs)
    
    return decorated_function

def require_scope(*required_scopes):
    """Decorator to require specific scopes for web routes.

    Uses RFC 9068 OAuth 2.0 scope format: resource:action
    Examples:
        @require_scope("policies:read")
        @require_scope("policies:read", "policies:write")
        @require_scope("*:admin")

    If user doesn't have scopes in JWT, falls back to expanding role to scopes.
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.headers.get('Accept', '').startswith('application/json'):
                    response.status = 401
                    return {"status": "error", "data": {"message": "Authentication required"}}
                else:
                    return redirect(URL('login'))

            request.user = user

            # Get user scopes from JWT claims or session
            user_scopes = getattr(user, 'scopes', [])
            if not user_scopes:
                # Fall back to expanding role to scopes
                from auth.scopes import expand_role_to_scopes
                user_role = user.role if hasattr(user, 'role') else 'viewer'
                user_scopes = expand_role_to_scopes(user_role)

            from auth.scopes import has_required_scopes
            if not has_required_scopes(list(required_scopes), user_scopes):
                if request.headers.get('Accept', '').startswith('application/json'):
                    response.status = 403
                    return {
                        "status": "error",
                        "data": {
                            "message": "Insufficient scopes",
                            "required": list(required_scopes)
                        }
                    }
                else:
                    abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_permission(permission: str):
    """Decorator to require specific permission (backward compatibility wrapper).

    Maps old permission strings to OAuth 2.0 scope format and delegates to
    require_scope. See _PERMISSION_TO_SCOPE for mapping.

    Example:
        @require_permission("view_clients")  # Maps to clients:read
    """
    scope = _PERMISSION_TO_SCOPE.get(permission)
    if not scope:
        # If no mapping exists, try treating permission as a scope directly
        scope = permission

    return require_scope(scope)

async def create_user_session(user: User) -> str:
    """Create session and set cookie"""
    user_agent = request.headers.get('User-Agent', '')
    ip_address = request.environ.get('REMOTE_ADDR', '')
    
    session = await user_manager.create_session(user, user_agent, ip_address)
    
    # Set secure cookie
    response.set_cookie(
        "sasewaddle_session",
        session.session_id,
        max_age=8*3600,  # 8 hours
        secure=True if request.headers.get('X-Forwarded-Proto') == 'https' else False,
        httponly=True,
        samesite='Lax'
    )
    
    return session.session_id

async def logout_user():
    """Logout current user"""
    session_id = request.get_cookie("sasewaddle_session")
    if session_id:
        await user_manager.logout(session_id)
    
    # Clear cookie
    response.set_cookie(
        "sasewaddle_session", 
        "", 
        max_age=0,
        secure=True if request.headers.get('X-Forwarded-Proto') == 'https' else False,
        httponly=True
    )