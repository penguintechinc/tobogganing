"""py4web middleware integration for SASEWaddle security."""

import logging
from typing import Dict, Any, Optional
import time
from py4web import request, response, abort, HTTP, Fixture

from . import security_middleware

logger = logging.getLogger(__name__)


class SecurityFixture(Fixture):
    """py4web Fixture for security middleware integration."""
    
    def __init__(self):
        self.__prerequisites__ = []
    
    def on_request(self, context):
        """Process request through security layers."""
        # Extract request information
        request_info = {
            'ip_address': self._get_client_ip(),
            'endpoint': request.path,
            'user_agent': request.environ.get('HTTP_USER_AGENT', ''),
            'method': request.method,
            'headers': dict(request.environ),
        }
        
        # Skip security for certain endpoints
        if request.path.startswith('/static/') or request.path in ['/favicon.ico']:
            return
        
        # Process through security layers
        allowed, headers = security_middleware.process_request(request_info)
        
        # Add security headers to response
        for header, value in headers.items():
            response.headers[header] = value
        
        if not allowed:
            # Request blocked - return 429 Too Many Requests
            # Determine block reason
            if 'X-Security-Block' in headers:
                error_msg = f"Request blocked by {headers['X-Security-Block']}"
                if 'X-Block-Reason' in headers:
                    error_msg += f": {headers['X-Block-Reason']}"
            else:
                error_msg = "Rate limit exceeded"
            
            raise HTTP(429, {
                'error': error_msg,
                'status': 429,
                'retry_after': headers.get('Retry-After', '300')
            })
    
    def _get_client_ip(self) -> str:
        """Extract the real client IP address."""
        # Check for forwarded headers (when behind proxy/load balancer)
        forwarded_for = request.environ.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(',')[0].strip()
        
        # Check for real IP header
        real_ip = request.environ.get('HTTP_X_REAL_IP')
        if real_ip:
            return real_ip.strip()
        
        # Fallback to remote address
        return request.environ.get('REMOTE_ADDR', '127.0.0.1')


# Global security fixture instance
security_fixture = SecurityFixture()


def check_security_bypass(func):
    """Decorator to bypass security checks for specific endpoints."""
    def wrapper(*args, **kwargs):
        # Mark request as security bypass
        request.environ['SECURITY_BYPASS'] = True
        return func(*args, **kwargs)
    return wrapper


def require_admin_role(func):
    """Decorator to require admin role for security management endpoints."""
    def wrapper(*args, **kwargs):
        # This would integrate with your authentication system
        # For now, check if user has admin role
        user = request.environ.get('user')
        if not user or user.get('role') != 'admin':
            abort(403, "Admin role required")
        return func(*args, **kwargs)
    return wrapper


class EmergencyModeHandler:
    """Handle emergency mode restrictions."""
    
    @staticmethod
    def is_emergency_mode() -> bool:
        """Check if emergency mode is active."""
        try:
            return security_middleware.ddos_protection.redis_client.exists("emergency_mode")
        except Exception:
            return False
    
    @staticmethod
    def enable_emergency_mode(duration: int = 3600):
        """Enable emergency mode for specified duration."""
        try:
            security_middleware.ddos_protection.redis_client.setex("emergency_mode", duration, "1")
            logger.warning(f"Emergency mode enabled for {duration} seconds")
        except Exception as e:
            logger.error(f"Failed to enable emergency mode: {e}")
    
    @staticmethod
    def disable_emergency_mode():
        """Disable emergency mode."""
        try:
            security_middleware.ddos_protection.redis_client.delete("emergency_mode")
            logger.info("Emergency mode disabled")
        except Exception as e:
            logger.error(f"Failed to disable emergency mode: {e}")


def get_security_stats() -> Dict[str, Any]:
    """Get current security statistics."""
    try:
        blocked_ips = security_middleware.rate_limiter.get_blocked_ips()
        emergency_mode = EmergencyModeHandler.is_emergency_mode()
        
        # Get recent security events count
        db = security_middleware.rate_limiter.db
        recent_events = 0
        if 'security_events' in db.tables:
            recent_events = db(
                db.security_events.timestamp > (time.time() - 3600)  # Last hour
            ).count()
        
        return {
            'blocked_ips_count': len(blocked_ips),
            'blocked_ips': blocked_ips,
            'emergency_mode': emergency_mode,
            'recent_security_events': recent_events,
            'rate_limit_rules_count': len(security_middleware.rate_limiter.rules)
        }
    except Exception as e:
        logger.error(f"Failed to get security stats: {e}")
        return {
            'error': str(e),
            'blocked_ips_count': 0,
            'emergency_mode': False,
            'recent_security_events': 0,
            'rate_limit_rules_count': 0
        }


def handle_security_incident(incident_type: str, details: Dict[str, Any]):
    """Handle security incidents with appropriate responses."""
    severity_map = {
        'rate_limit_violation': 'medium',
        'ddos_attack': 'high',
        'suspicious_pattern': 'medium',
        'auth_failure': 'low',
        'admin_action': 'low'
    }
    
    severity = severity_map.get(incident_type, 'medium')
    
    # Log incident
    logger.warning(f"Security incident: {incident_type} - {details}")
    
    # Take automated actions based on incident type
    if incident_type == 'ddos_attack' and details.get('severity') == 'critical':
        EmergencyModeHandler.enable_emergency_mode(7200)  # 2 hours
    
    # This could trigger additional notifications, integrations, etc.