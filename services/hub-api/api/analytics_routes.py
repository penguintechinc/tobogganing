"""Analytics dashboard API routes for SASEWaddle Manager."""

import os
from datetime import datetime, timedelta
from py4web import action, request, response, abort, redirect, URL
from py4web.core import Fixture
import json

from analytics import analytics_manager
from web.auth import get_current_user, user_manager


@action('api/analytics/os-stats', method=['GET'])
@action.uses('json')
async def get_os_statistics():
    """Get operating system distribution statistics."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        # Get query parameters
        days_back = int(request.query.get('days', 7))
        days_back = min(days_back, 90)  # Limit to 90 days max
        
        stats = analytics_manager.get_os_statistics(days_back=days_back)
        
        return {
            "success": True,
            "data": stats,
            "period_days": days_back,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except ValueError as e:
        response.status = 400
        return {"error": f"Invalid parameter: {str(e)}"}
    except Exception as e:
        response.status = 500
        return {"error": str(e)}


@action('api/analytics/traffic-stats', method=['GET'])
@action.uses('json')
async def get_traffic_statistics():
    """Get traffic statistics by headend."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        # Get query parameters
        days_back = int(request.query.get('days', 7))
        days_back = min(days_back, 90)  # Limit to 90 days max
        
        stats = analytics_manager.get_traffic_statistics(days_back=days_back)
        
        return {
            "success": True,
            "data": stats,
            "period_days": days_back,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except ValueError as e:
        response.status = 400
        return {"error": f"Invalid parameter: {str(e)}"}
    except Exception as e:
        response.status = 500
        return {"error": str(e)}


@action('api/analytics/search', method=['GET'])
@action.uses('json')
async def search_agents_headends():
    """Search and filter agents and headends."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        # Get query parameters
        search_term = request.query.get('q', '').strip()
        filter_type = request.query.get('type', 'all')  # 'all', 'agents', 'headends'
        sort_by = request.query.get('sort', 'last_seen')  # 'last_seen', 'hostname', 'os_name'
        limit = int(request.query.get('limit', 100))
        
        # Validate parameters
        if filter_type not in ['all', 'agents', 'headends']:
            response.status = 400
            return {"error": "Invalid filter type. Must be 'all', 'agents', or 'headends'"}
        
        if sort_by not in ['last_seen', 'hostname', 'os_name']:
            response.status = 400
            return {"error": "Invalid sort field. Must be 'last_seen', 'hostname', or 'os_name'"}
        
        limit = min(limit, 500)  # Limit to 500 results max
        
        results = analytics_manager.search_agents_and_headends(
            search_term=search_term,
            filter_type=filter_type,
            sort_by=sort_by,
            limit=limit
        )
        
        return {
            "success": True,
            "data": results,
            "search_term": search_term,
            "filter_type": filter_type,
            "sort_by": sort_by,
            "limit": limit,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except ValueError as e:
        response.status = 400
        return {"error": f"Invalid parameter: {str(e)}"}
    except Exception as e:
        response.status = 500
        return {"error": str(e)}


@action('api/analytics/client/<client_id>/details', method=['GET'])
@action.uses('json')
async def get_client_details(client_id):
    """Get detailed information about a specific client."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        db = analytics_manager.db
        
        # Get client details
        client = db(db.client_analytics.client_id == client_id).select().first()
        
        if not client:
            response.status = 404
            return {"error": f"Client {client_id} not found"}
        
        # Calculate additional metrics
        last_seen_minutes = (datetime.utcnow() - client.last_seen).total_seconds() / 60
        total_bytes = (client.bytes_sent or 0) + (client.bytes_received or 0)
        
        if last_seen_minutes <= 5:
            status = 'online'
        elif last_seen_minutes <= 60:
            status = 'recently_active'
        elif last_seen_minutes <= 1440:  # 24 hours
            status = 'offline'
        else:
            status = 'stale'
        
        # Get connection history (if we have it)
        connection_history = []
        # This would query a connection_logs table if we had one
        
        client_details = {
            "client_id": client.client_id,
            "hostname": client.hostname,
            "os_info": {
                "name": client.os_name,
                "version": client.os_version,
                "architecture": client.architecture
            },
            "client_version": client.client_version,
            "network_info": {
                "ip_address": client.ip_address,
                "connected_headend": client.connected_headend
            },
            "connection_stats": {
                "duration": client.connection_duration,
                "bytes_sent": client.bytes_sent,
                "bytes_received": client.bytes_received,
                "packets_sent": client.packets_sent,
                "packets_received": client.packets_received,
                "total_bytes": total_bytes
            },
            "timestamps": {
                "created_at": client.created_at.isoformat() if client.created_at else None,
                "last_seen": client.last_seen.isoformat() if client.last_seen else None,
                "updated_at": client.updated_at.isoformat() if client.updated_at else None,
                "minutes_since_last_seen": int(last_seen_minutes)
            },
            "status": status,
            "connection_history": connection_history
        }
        
        return {
            "success": True,
            "data": client_details,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}


@action('api/analytics/headend/<headend_id>/details', method=['GET'])
@action.uses('json')
async def get_headend_details(headend_id):
    """Get detailed information about a specific headend."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        db = analytics_manager.db
        
        # Get headend details
        headend = db(db.headend_analytics.headend_id == headend_id).select().first()
        
        if not headend:
            response.status = 404
            return {"error": f"Headend {headend_id} not found"}
        
        # Calculate additional metrics
        last_heartbeat_minutes = (datetime.utcnow() - headend.last_heartbeat).total_seconds() / 60
        auth_total = (headend.auth_successes or 0) + (headend.auth_failures or 0)
        auth_success_rate = (headend.auth_successes / auth_total * 100) if auth_total > 0 else 0
        
        if last_heartbeat_minutes <= 2:
            status = 'healthy'
        elif last_heartbeat_minutes <= 10:
            status = 'warning'
        else:
            status = 'critical'
        
        # Get connected clients
        connected_clients = db(db.client_analytics.connected_headend == headend_id).select(
            limitby=(0, 50),  # Limit to 50 most recent
            orderby=~db.client_analytics.last_seen
        )
        
        client_list = []
        for client in connected_clients:
            client_list.append({
                "client_id": client.client_id,
                "hostname": client.hostname,
                "os_name": client.os_name,
                "ip_address": client.ip_address,
                "last_seen": client.last_seen.isoformat() if client.last_seen else None
            })
        
        headend_details = {
            "headend_id": headend.headend_id,
            "hostname": headend.hostname,
            "location_info": {
                "region": headend.region,
                "cluster_id": headend.cluster_id
            },
            "version": headend.version,
            "connection_stats": {
                "active_connections": headend.active_connections,
                "total_connections": headend.total_connections,
                "bytes_proxied": headend.bytes_proxied,
                "packets_proxied": headend.packets_proxied
            },
            "system_metrics": {
                "cpu_usage_percent": headend.cpu_usage_percent,
                "memory_usage_mb": headend.memory_usage_mb,
                "disk_usage_percent": headend.disk_usage_percent
            },
            "auth_stats": {
                "successes": headend.auth_successes,
                "failures": headend.auth_failures,
                "success_rate": round(auth_success_rate, 2),
                "total_attempts": auth_total
            },
            "error_stats": {
                "network_errors": headend.network_errors
            },
            "timestamps": {
                "created_at": headend.created_at.isoformat() if headend.created_at else None,
                "last_heartbeat": headend.last_heartbeat.isoformat() if headend.last_heartbeat else None,
                "updated_at": headend.updated_at.isoformat() if headend.updated_at else None,
                "minutes_since_heartbeat": int(last_heartbeat_minutes)
            },
            "status": status,
            "connected_clients": client_list,
            "connected_clients_count": len(client_list)
        }
        
        return {
            "success": True,
            "data": headend_details,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}


@action('api/analytics/record/client', method=['POST'])
@action.uses('json')
async def record_client_activity():
    """Record client activity data (called by clients or headends)."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        # Get client data from request
        data = await request.json()
        
        # Validate required fields
        if 'client_id' not in data:
            response.status = 400
            return {"error": "client_id is required"}
        
        # Record the activity
        success = analytics_manager.record_client_activity(data)
        
        if success:
            return {
                "success": True,
                "message": "Client activity recorded",
                "client_id": data['client_id']
            }
        else:
            response.status = 500
            return {"error": "Failed to record client activity"}
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}


@action('api/analytics/record/headend', method=['POST'])
@action.uses('json')
async def record_headend_stats():
    """Record headend statistics (called by headends)."""
    # Check authentication - could be API key or token-based for headends
    user = get_current_user()
    if not user:
        # Try API key authentication for headend services
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != os.getenv('HEADEND_API_KEY'):
            response.status = 401
            return {"error": "Authentication required"}
    
    try:
        # Get headend data from request
        data = await request.json()
        
        # Validate required fields
        if 'headend_id' not in data:
            response.status = 400
            return {"error": "headend_id is required"}
        
        # Record the stats
        success = analytics_manager.record_headend_stats(data)
        
        if success:
            return {
                "success": True,
                "message": "Headend stats recorded",
                "headend_id": data['headend_id']
            }
        else:
            response.status = 500
            return {"error": "Failed to record headend stats"}
        
    except Exception as e:
        response.status = 500
        return {"error": str(e)}


@action('api/analytics/dashboard/overview', method=['GET'])
@action.uses('json')
async def get_dashboard_overview():
    """Get overview dashboard data combining all analytics."""
    # Check authentication
    user = get_current_user()
    if not user:
        response.status = 401
        return {"error": "Authentication required"}
    
    try:
        # Get query parameters
        days_back = int(request.query.get('days', 7))
        days_back = min(days_back, 90)  # Limit to 90 days max
        
        # Gather all dashboard data
        os_stats = analytics_manager.get_os_statistics(days_back=days_back)
        traffic_stats = analytics_manager.get_traffic_statistics(days_back=days_back)
        
        # Get recent activity summary
        search_results = analytics_manager.search_agents_and_headends(
            search_term="",
            filter_type="all",
            sort_by="last_seen",
            limit=10
        )
        
        overview = {
            "summary": {
                "total_clients": os_stats.get('total_clients', 0),
                "active_clients_24h": os_stats.get('active_last_24h', 0),
                "active_clients_1h": os_stats.get('active_last_hour', 0),
                "active_headends": traffic_stats.get('active_headends', 0),
                "total_bytes_proxied": traffic_stats.get('total_bytes_proxied', 0),
                "total_connections": traffic_stats.get('total_connections', 0)
            },
            "os_distribution": os_stats.get('by_os', {}),
            "architecture_distribution": os_stats.get('by_architecture', {}),
            "traffic_by_region": traffic_stats.get('by_region', {}),
            "top_headends": [
                {
                    "headend_id": hid,
                    "hostname": hdata.get('hostname'),
                    "region": hdata.get('region'),
                    "bytes_proxied": hdata.get('bytes_proxied', 0),
                    "active_connections": hdata.get('active_connections', 0),
                    "status": "healthy" if hdata.get('last_heartbeat') else "unknown"
                }
                for hid, hdata in list(traffic_stats.get('by_headend', {}).items())[:5]
            ],
            "recent_agents": search_results.get('agents', [])[:5],
            "recent_headends": search_results.get('headends', [])[:5],
            "period_days": days_back,
            "generated_at": datetime.utcnow().isoformat()
        }
        
        return {
            "success": True,
            "data": overview
        }
        
    except ValueError as e:
        response.status = 400
        return {"error": f"Invalid parameter: {str(e)}"}
    except Exception as e:
        response.status = 500
        return {"error": str(e)}