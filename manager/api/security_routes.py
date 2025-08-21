"""Security management API endpoints for SASEWaddle Manager."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from py4web import action, request, response, abort, URL, HTTP
from py4web.utils.cors import cors

from database import get_db
from ..security import security_middleware, RateLimitRule
from ..security.middleware import security_fixture, require_admin_role, get_security_stats, EmergencyModeHandler

logger = logging.getLogger(__name__)


@action('api/security/status', method=['GET'])
@action.uses(cors())
def security_status():
    """Get current security system status."""
    try:
        stats = get_security_stats()
        return {
            'success': True,
            'data': stats,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get security status: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/blocked-ips', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def get_blocked_ips():
    """Get list of currently blocked IP addresses."""
    try:
        blocked_ips = security_middleware.rate_limiter.get_blocked_ips()
        return {
            'success': True,
            'data': {
                'blocked_ips': blocked_ips,
                'count': len(blocked_ips)
            }
        }
    except Exception as e:
        logger.error(f"Failed to get blocked IPs: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/blocked-ips/<ip_address>', method=['DELETE'])
@action.uses(security_fixture, cors())
@require_admin_role
def unblock_ip(ip_address):
    """Unblock a specific IP address."""
    try:
        success = security_middleware.rate_limiter.unblock_ip(ip_address)
        
        if success:
            # Log admin action
            security_middleware.rate_limiter._log_security_event(
                "admin_unblock_ip",
                ip_address,
                request.path,
                request.environ.get('HTTP_USER_AGENT', ''),
                "low",
                {
                    "admin_user": request.environ.get('user', {}).get('username', 'unknown'),
                    "action": "unblock_ip"
                }
            )
            
            return {
                'success': True,
                'message': f'IP {ip_address} unblocked successfully'
            }
        else:
            return {
                'success': False,
                'error': f'IP {ip_address} was not blocked or unblock failed'
            }
    except Exception as e:
        logger.error(f"Failed to unblock IP {ip_address}: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/emergency-mode', method=['GET', 'POST', 'DELETE'])
@action.uses(security_fixture, cors())
@require_admin_role
def emergency_mode():
    """Manage emergency mode status."""
    try:
        if request.method == 'GET':
            # Get emergency mode status
            is_active = EmergencyModeHandler.is_emergency_mode()
            return {
                'success': True,
                'data': {
                    'emergency_mode': is_active
                }
            }
        
        elif request.method == 'POST':
            # Enable emergency mode
            data = request.json or {}
            duration = data.get('duration', 3600)  # Default 1 hour
            
            EmergencyModeHandler.enable_emergency_mode(duration)
            
            # Log admin action
            security_middleware.rate_limiter._log_security_event(
                "admin_emergency_mode",
                request.environ.get('REMOTE_ADDR', ''),
                request.path,
                request.environ.get('HTTP_USER_AGENT', ''),
                "high",
                {
                    "admin_user": request.environ.get('user', {}).get('username', 'unknown'),
                    "action": "enable_emergency_mode",
                    "duration": duration
                }
            )
            
            return {
                'success': True,
                'message': f'Emergency mode enabled for {duration} seconds'
            }
        
        elif request.method == 'DELETE':
            # Disable emergency mode
            EmergencyModeHandler.disable_emergency_mode()
            
            # Log admin action
            security_middleware.rate_limiter._log_security_event(
                "admin_emergency_mode",
                request.environ.get('REMOTE_ADDR', ''),
                request.path,
                request.environ.get('HTTP_USER_AGENT', ''),
                "low",
                {
                    "admin_user": request.environ.get('user', {}).get('username', 'unknown'),
                    "action": "disable_emergency_mode"
                }
            )
            
            return {
                'success': True,
                'message': 'Emergency mode disabled'
            }
    
    except Exception as e:
        logger.error(f"Emergency mode operation failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/rate-limit-rules', method=['GET', 'POST'])
@action.uses(security_fixture, cors())
@require_admin_role
def rate_limit_rules():
    """Manage rate limiting rules."""
    db = get_db()
    
    try:
        if request.method == 'GET':
            # Get all rate limit rules
            rules = []
            
            # Built-in rules
            for rule in security_middleware.rate_limiter.rules:
                rules.append({
                    'name': rule.name,
                    'max_requests': rule.max_requests,
                    'window_seconds': rule.window_seconds,
                    'block_duration': rule.block_duration,
                    'endpoints': rule.endpoints,
                    'exempt_ips': rule.exempt_ips,
                    'priority': rule.priority,
                    'built_in': True,
                    'enabled': True
                })
            
            # Custom rules from database
            if 'rate_limit_rules' in db.tables:
                custom_rules = db(db.rate_limit_rules).select()
                for rule in custom_rules:
                    rules.append({
                        'id': rule.id,
                        'name': rule.name,
                        'max_requests': rule.max_requests,
                        'window_seconds': rule.window_seconds,
                        'block_duration': rule.block_duration,
                        'endpoints': json.loads(rule.endpoints) if rule.endpoints else None,
                        'exempt_ips': json.loads(rule.exempt_ips) if rule.exempt_ips else None,
                        'priority': rule.priority,
                        'built_in': False,
                        'enabled': rule.enabled,
                        'created_at': rule.created_at.isoformat() if rule.created_at else None,
                        'updated_at': rule.updated_at.isoformat() if rule.updated_at else None
                    })
            
            return {
                'success': True,
                'data': {
                    'rules': rules,
                    'count': len(rules)
                }
            }
        
        elif request.method == 'POST':
            # Create new rate limit rule
            data = request.json or {}
            
            # Validate required fields
            required_fields = ['name', 'max_requests', 'window_seconds']
            for field in required_fields:
                if field not in data:
                    return {
                        'success': False,
                        'error': f'Missing required field: {field}'
                    }
            
            # Insert new rule
            rule_id = db.rate_limit_rules.insert(
                name=data['name'],
                max_requests=int(data['max_requests']),
                window_seconds=int(data['window_seconds']),
                block_duration=int(data.get('block_duration', 300)),
                endpoints=json.dumps(data.get('endpoints')) if data.get('endpoints') else None,
                exempt_ips=json.dumps(data.get('exempt_ips')) if data.get('exempt_ips') else None,
                priority=int(data.get('priority', 10)),
                enabled=bool(data.get('enabled', True))
            )
            db.commit()
            
            # Reload rules in security middleware
            security_middleware.rate_limiter._load_custom_rules()
            security_middleware.rate_limiter.rules.sort(key=lambda r: r.priority)
            
            # Log admin action
            security_middleware.rate_limiter._log_security_event(
                "admin_create_rule",
                request.environ.get('REMOTE_ADDR', ''),
                request.path,
                request.environ.get('HTTP_USER_AGENT', ''),
                "low",
                {
                    "admin_user": request.environ.get('user', {}).get('username', 'unknown'),
                    "action": "create_rate_limit_rule",
                    "rule_name": data['name'],
                    "rule_id": rule_id
                }
            )
            
            return {
                'success': True,
                'message': 'Rate limit rule created successfully',
                'data': {'rule_id': rule_id}
            }
    
    except Exception as e:
        logger.error(f"Rate limit rules operation failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/rate-limit-rules/<rule_id:int>', method=['GET', 'PUT', 'DELETE'])
@action.uses(security_fixture, cors())
@require_admin_role
def rate_limit_rule(rule_id):
    """Manage individual rate limit rule."""
    db = get_db()
    
    try:
        # Check if rule exists
        rule = db(db.rate_limit_rules.id == rule_id).select().first()
        if not rule:
            return {
                'success': False,
                'error': 'Rate limit rule not found'
            }
        
        if request.method == 'GET':
            # Get specific rule
            return {
                'success': True,
                'data': {
                    'id': rule.id,
                    'name': rule.name,
                    'max_requests': rule.max_requests,
                    'window_seconds': rule.window_seconds,
                    'block_duration': rule.block_duration,
                    'endpoints': json.loads(rule.endpoints) if rule.endpoints else None,
                    'exempt_ips': json.loads(rule.exempt_ips) if rule.exempt_ips else None,
                    'priority': rule.priority,
                    'enabled': rule.enabled,
                    'created_at': rule.created_at.isoformat() if rule.created_at else None,
                    'updated_at': rule.updated_at.isoformat() if rule.updated_at else None
                }
            }
        
        elif request.method == 'PUT':
            # Update rule
            data = request.json or {}
            
            # Update fields
            update_fields = {}
            if 'name' in data:
                update_fields['name'] = data['name']
            if 'max_requests' in data:
                update_fields['max_requests'] = int(data['max_requests'])
            if 'window_seconds' in data:
                update_fields['window_seconds'] = int(data['window_seconds'])
            if 'block_duration' in data:
                update_fields['block_duration'] = int(data['block_duration'])
            if 'endpoints' in data:
                update_fields['endpoints'] = json.dumps(data['endpoints']) if data['endpoints'] else None
            if 'exempt_ips' in data:
                update_fields['exempt_ips'] = json.dumps(data['exempt_ips']) if data['exempt_ips'] else None
            if 'priority' in data:
                update_fields['priority'] = int(data['priority'])
            if 'enabled' in data:
                update_fields['enabled'] = bool(data['enabled'])
            
            update_fields['updated_at'] = datetime.utcnow()
            
            # Update in database
            db(db.rate_limit_rules.id == rule_id).update(**update_fields)
            db.commit()
            
            # Reload rules in security middleware
            security_middleware.rate_limiter._load_custom_rules()
            security_middleware.rate_limiter.rules.sort(key=lambda r: r.priority)
            
            # Log admin action
            security_middleware.rate_limiter._log_security_event(
                "admin_update_rule",
                request.environ.get('REMOTE_ADDR', ''),
                request.path,
                request.environ.get('HTTP_USER_AGENT', ''),
                "low",
                {
                    "admin_user": request.environ.get('user', {}).get('username', 'unknown'),
                    "action": "update_rate_limit_rule",
                    "rule_id": rule_id,
                    "changes": list(update_fields.keys())
                }
            )
            
            return {
                'success': True,
                'message': 'Rate limit rule updated successfully'
            }
        
        elif request.method == 'DELETE':
            # Delete rule
            db(db.rate_limit_rules.id == rule_id).delete()
            db.commit()
            
            # Reload rules in security middleware
            security_middleware.rate_limiter._load_custom_rules()
            security_middleware.rate_limiter.rules.sort(key=lambda r: r.priority)
            
            # Log admin action
            security_middleware.rate_limiter._log_security_event(
                "admin_delete_rule",
                request.environ.get('REMOTE_ADDR', ''),
                request.path,
                request.environ.get('HTTP_USER_AGENT', ''),
                "low",
                {
                    "admin_user": request.environ.get('user', {}).get('username', 'unknown'),
                    "action": "delete_rate_limit_rule",
                    "rule_id": rule_id,
                    "rule_name": rule.name
                }
            )
            
            return {
                'success': True,
                'message': 'Rate limit rule deleted successfully'
            }
    
    except Exception as e:
        logger.error(f"Rate limit rule operation failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/events', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def security_events():
    """Get security events with filtering and pagination."""
    db = get_db()
    
    try:
        # Parse query parameters
        page = int(request.query.get('page', 1))
        limit = min(int(request.query.get('limit', 50)), 1000)  # Max 1000 events
        offset = (page - 1) * limit
        
        event_type = request.query.get('event_type')
        ip_address = request.query.get('ip_address')
        severity = request.query.get('severity')
        hours_back = int(request.query.get('hours_back', 24))
        
        # Build query
        query = db.security_events.timestamp > (datetime.utcnow() - timedelta(hours=hours_back))
        
        if event_type:
            query &= (db.security_events.event_type == event_type)
        if ip_address:
            query &= (db.security_events.ip_address == ip_address)
        if severity:
            query &= (db.security_events.severity == severity)
        
        # Get total count
        total_count = db(query).count()
        
        # Get events with pagination
        events = db(query).select(
            orderby=~db.security_events.timestamp,
            limitby=(offset, offset + limit)
        )
        
        # Format events
        formatted_events = []
        for event in events:
            formatted_events.append({
                'id': event.id,
                'event_type': event.event_type,
                'ip_address': event.ip_address,
                'endpoint': event.endpoint,
                'user_agent': event.user_agent,
                'timestamp': event.timestamp.isoformat() if event.timestamp else None,
                'severity': event.severity,
                'details': json.loads(event.details) if event.details else {},
                'created_at': event.created_at.isoformat() if event.created_at else None
            })
        
        return {
            'success': True,
            'data': {
                'events': formatted_events,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': (total_count + limit - 1) // limit
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get security events: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@action('api/security/metrics', method=['GET'])
@action.uses(security_fixture, cors())
@require_admin_role
def security_metrics():
    """Get security metrics and statistics."""
    db = get_db()
    
    try:
        now = datetime.utcnow()
        
        # Get metrics for different time periods
        metrics = {}
        
        for period_name, hours in [('last_hour', 1), ('last_24h', 24), ('last_7d', 168)]:
            since = now - timedelta(hours=hours)
            
            if 'security_events' in db.tables:
                # Event counts by type
                event_counts = {}
                event_types = db(db.security_events.timestamp > since).select(
                    db.security_events.event_type,
                    db.security_events.id.count(),
                    groupby=db.security_events.event_type
                )
                
                for row in event_types:
                    event_counts[row.security_events.event_type] = row._extra[db.security_events.id.count()]
                
                # Top IPs by event count
                top_ips = db(db.security_events.timestamp > since).select(
                    db.security_events.ip_address,
                    db.security_events.id.count(),
                    groupby=db.security_events.ip_address,
                    orderby=~db.security_events.id.count(),
                    limitby=(0, 10)
                )
                
                top_ips_list = []
                for row in top_ips:
                    top_ips_list.append({
                        'ip_address': row.security_events.ip_address,
                        'event_count': row._extra[db.security_events.id.count()]
                    })
                
                metrics[period_name] = {
                    'event_counts': event_counts,
                    'total_events': sum(event_counts.values()),
                    'top_ips': top_ips_list
                }
            else:
                metrics[period_name] = {
                    'event_counts': {},
                    'total_events': 0,
                    'top_ips': []
                }
        
        # Current status
        current_status = get_security_stats()
        
        return {
            'success': True,
            'data': {
                'metrics': metrics,
                'current_status': current_status,
                'timestamp': now.isoformat()
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get security metrics: {e}")
        return {
            'success': False,
            'error': str(e)
        }