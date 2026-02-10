"""
Web Authentication Decorators and Helpers for py4web
"""

import functools
from typing import Optional
from py4web import request, response, redirect, URL, abort
from auth.user_manager import UserManager, User, UserRole

# Global user manager instance
user_manager = UserManager()

def get_current_user() -> Optional[User]:
    """Get current authenticated user from session"""
    session_id = request.get_cookie("sasewaddle_session")
    if not session_id:
        return None
    
    # This would normally be async, but py4web decorators need sync
    # In production, consider using async/await patterns
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(user_manager.validate_session(session_id))
    except:
        # Create new event loop if none exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(user_manager.validate_session(session_id))

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

def require_role(role: UserRole):
    """Decorator to require specific role"""
    def decorator(f):
        @functools.wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user = request.user
            if user.role != role and user.role != UserRole.ADMIN:
                if request.headers.get('Accept', '').startswith('application/json'):
                    response.status = 403
                    return {"error": f"Role {role.value} required"}
                else:
                    abort(403)
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def require_permission(permission: str):
    """Decorator to require specific permission"""
    def decorator(f):
        @functools.wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user = request.user
            if not user_manager.has_permission(user, permission):
                if request.headers.get('Accept', '').startswith('application/json'):
                    response.status = 403
                    return {"error": f"Permission {permission} required"}
                else:
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