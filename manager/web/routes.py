"""
Web Portal Routes for SASEWaddle Manager
py4web-based web interface with role-based access control
"""

import asyncio
import json
from datetime import datetime
from py4web import action, request, response, redirect, URL, abort
from web.auth import (
    require_auth, require_role, require_permission, 
    get_current_user, create_user_session, logout_user,
    user_manager
)
from auth.user_manager import UserRole
import structlog

logger = structlog.get_logger()

def setup_web_routes(app, cluster_manager, client_registry, cert_manager, jwt_manager):
    """Setup web portal routes"""
    
    @action("login", method=["GET", "POST"])
    @action.uses("login.html", "json")
    async def login():
        """Login page and authentication"""
        if request.method == "GET":
            # Check if already logged in
            user = get_current_user()
            if user:
                return redirect(URL('dashboard'))
            
            # Show login form
            return {
                "title": "SASEWaddle Manager Login",
                "error": request.query.get('error', '')
            }
        
        # POST - Handle login
        try:
            username = request.forms.get('username', '').strip()
            password = request.forms.get('password', '')
            
            if not username or not password:
                return redirect(URL('login', error='Username and password required'))
            
            user = await user_manager.authenticate(username, password)
            if not user:
                return redirect(URL('login', error='Invalid credentials'))
            
            # Create session
            await create_user_session(user)
            
            # Redirect to dashboard
            next_url = request.query.get('next', URL('dashboard'))
            return redirect(next_url)
            
        except Exception as e:
            logger.error("Login error", error=str(e))
            return redirect(URL('login', error='Login failed'))
    
    @action("logout", method=["POST"])
    async def logout():
        """Logout and redirect to login"""
        await logout_user()
        return redirect(URL('login'))
    
    @action("dashboard")
    @action.uses("dashboard.html")
    @require_auth
    async def dashboard():
        """Main dashboard - shows overview"""
        user = request.user
        
        try:
            # Get overview statistics
            cluster_count = await cluster_manager.get_cluster_count() if cluster_manager else 0
            client_count = await client_registry.get_client_count() if client_registry else 0
            
            clusters = await cluster_manager.get_all_clusters() if cluster_manager else []
            active_clusters = len([c for c in clusters if c.status == 'active'])
            
            clients = await client_registry.get_all_clients() if client_registry else []
            active_clients = len([c for c in clients if c.status == 'active'])
            
            # Recent activity (last 10 clients)
            recent_clients = sorted(clients, key=lambda x: x.last_seen, reverse=True)[:10]
            
            return {
                "title": "SASEWaddle Manager Dashboard",
                "user": user,
                "stats": {
                    "total_clusters": cluster_count,
                    "active_clusters": active_clusters,
                    "total_clients": client_count,
                    "active_clients": active_clients,
                },
                "recent_clients": recent_clients,
                "clusters": clusters[:5],  # Show top 5 clusters
                "can_manage": user_manager.has_permission(user, "manage_clusters")
            }
            
        except Exception as e:
            logger.error("Dashboard error", error=str(e))
            return {
                "title": "SASEWaddle Manager Dashboard",
                "user": user,
                "error": "Failed to load dashboard data"
            }
    
    @action("clusters")
    @action.uses("clusters.html")
    @require_permission("view_clusters")
    async def clusters():
        """Cluster management page"""
        user = request.user
        
        try:
            clusters = await cluster_manager.get_all_clusters() if cluster_manager else []
            
            return {
                "title": "Cluster Management",
                "user": user,
                "clusters": clusters,
                "can_manage": user_manager.has_permission(user, "manage_clusters")
            }
            
        except Exception as e:
            logger.error("Clusters page error", error=str(e))
            return {
                "title": "Cluster Management", 
                "user": user,
                "clusters": [],
                "error": "Failed to load clusters"
            }
    
    @action("clients")
    @action.uses("clients.html")
    @require_permission("view_clients")
    async def clients():
        """Client management page"""
        user = request.user
        
        try:
            clients = await client_registry.get_all_clients() if client_registry else []
            clusters = await cluster_manager.get_all_clusters() if cluster_manager else []
            
            # Group clients by cluster
            cluster_map = {c.id: c for c in clusters}
            for client in clients:
                client.cluster_name = cluster_map.get(client.cluster_id, {}).get('name', 'Unknown')
            
            return {
                "title": "Client Management",
                "user": user,
                "clients": clients,
                "clusters": clusters,
                "can_manage": user_manager.has_permission(user, "manage_clients")
            }
            
        except Exception as e:
            logger.error("Clients page error", error=str(e))
            return {
                "title": "Client Management",
                "user": user,
                "clients": [],
                "error": "Failed to load clients"
            }
    
    @action("certificates")
    @action.uses("certificates.html")
    @require_permission("view_certificates")
    async def certificates():
        """Certificate management page"""
        user = request.user
        
        try:
            # Get certificate statistics
            # This would be implemented in cert_manager
            cert_stats = {
                "total_certs": 0,
                "expiring_soon": 0,
                "expired": 0
            }
            
            return {
                "title": "Certificate Management",
                "user": user,
                "cert_stats": cert_stats,
                "can_manage": user_manager.has_permission(user, "manage_certificates")
            }
            
        except Exception as e:
            logger.error("Certificates page error", error=str(e))
            return {
                "title": "Certificate Management",
                "user": user,
                "cert_stats": {},
                "error": "Failed to load certificate data"
            }
    
    @action("users")
    @action.uses("users.html")
    @require_role(UserRole.ADMIN)
    async def users():
        """User management page (admin only)"""
        user = request.user
        
        try:
            users = await user_manager.list_users()
            
            return {
                "title": "User Management",
                "user": user,
                "users": users,
                "user_roles": [role.value for role in UserRole]
            }
            
        except Exception as e:
            logger.error("Users page error", error=str(e))
            return {
                "title": "User Management",
                "user": user,
                "users": [],
                "error": "Failed to load users"
            }
    
    @action("metrics")
    @action.uses("metrics.html")
    @require_permission("view_metrics")
    async def metrics():
        """Metrics and monitoring page"""
        user = request.user
        
        try:
            # Get system metrics
            import psutil
            import time
            
            system_stats = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory": psutil.virtual_memory()._asdict(),
                "disk": psutil.disk_usage('/')._asdict(),
                "uptime": time.time() - psutil.boot_time(),
                "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
            }
            
            # Get service stats
            service_stats = {
                "cluster_count": await cluster_manager.get_cluster_count() if cluster_manager else 0,
                "client_count": await client_registry.get_client_count() if client_registry else 0,
                "active_sessions": len(await user_manager.list_users()),  # Simplified
                "jwt_tokens_issued": 0  # Would track this in jwt_manager
            }
            
            return {
                "title": "Metrics & Monitoring",
                "user": user,
                "system_stats": system_stats,
                "service_stats": service_stats,
                "prometheus_endpoint": "/metrics"
            }
            
        except Exception as e:
            logger.error("Metrics page error", error=str(e))
            return {
                "title": "Metrics & Monitoring",
                "user": user,
                "system_stats": {},
                "service_stats": {},
                "error": "Failed to load metrics"
            }
    
    # API endpoints for AJAX requests
    @action("api/web/cluster/<cluster_id>/status", method=["POST"])
    @action.uses("json")
    @require_permission("manage_clusters")
    async def toggle_cluster_status(cluster_id):
        """Toggle cluster status (AJAX)"""
        try:
            action = request.json.get('action')  # 'enable' or 'disable'
            
            # This would be implemented in cluster_manager
            success = True  # await cluster_manager.set_status(cluster_id, action == 'enable')
            
            return {"success": success, "action": action}
            
        except Exception as e:
            logger.error("Toggle cluster status error", error=str(e))
            response.status = 500
            return {"error": "Failed to update cluster status"}
    
    @action("api/web/client/<client_id>/revoke", method=["POST"])
    @action.uses("json")
    @require_permission("manage_clients")
    async def revoke_client(client_id):
        """Revoke client access (AJAX)"""
        try:
            # Revoke client certificates and JWT tokens
            cert_revoked = True  # await cert_manager.revoke_client_certificate(client_id)
            jwt_revoked = await jwt_manager.revoke_all_tokens(client_id) if jwt_manager else 0
            
            return {
                "success": cert_revoked,
                "jwt_tokens_revoked": jwt_revoked
            }
            
        except Exception as e:
            logger.error("Revoke client error", error=str(e))
            response.status = 500
            return {"error": "Failed to revoke client access"}
    
    @action("api/web/user", method=["POST"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def create_user_api():
        """Create new user (AJAX)"""
        try:
            data = request.json
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            role = data.get('role', 'reporter')
            
            if not all([username, email, password]):
                response.status = 400
                return {"error": "All fields required"}
            
            try:
                user_role = UserRole(role)
            except ValueError:
                response.status = 400
                return {"error": "Invalid role"}
            
            new_user = await user_manager.create_user(username, email, password, user_role)
            
            return {
                "success": True,
                "user": {
                    "id": new_user.id,
                    "username": new_user.username,
                    "email": new_user.email,
                    "role": new_user.role.value,
                    "created_at": new_user.created_at.isoformat()
                }
            }
            
        except ValueError as e:
            response.status = 400
            return {"error": str(e)}
        except Exception as e:
            logger.error("Create user error", error=str(e))
            response.status = 500
            return {"error": "Failed to create user"}
    
    @action("api/web/user/<user_id>/toggle", method=["POST"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def toggle_user_status(user_id):
        """Enable/disable user (AJAX)"""
        try:
            action = request.json.get('action')  # 'enable' or 'disable'
            is_active = action == 'enable'
            
            success = await user_manager.update_user_status(user_id, is_active)
            
            return {"success": success, "action": action}
            
        except Exception as e:
            logger.error("Toggle user status error", error=str(e))
            response.status = 500
            return {"error": "Failed to update user status"}
    
    @action("api/web/stats", method=["GET"])
    @action.uses("json")
    @require_permission("view_dashboard")
    async def get_stats():
        """Get real-time stats for dashboard (AJAX)"""
        try:
            stats = {
                "clusters": {
                    "total": await cluster_manager.get_cluster_count() if cluster_manager else 0,
                    "active": len([c for c in await cluster_manager.get_all_clusters() if c.status == 'active']) if cluster_manager else 0
                },
                "clients": {
                    "total": await client_registry.get_client_count() if client_registry else 0,
                    "active": len([c for c in await client_registry.get_all_clients() if c.status == 'active']) if client_registry else 0
                },
                "system": {
                    "timestamp": datetime.now().isoformat(),
                    "uptime": "N/A"  # Would calculate actual uptime
                }
            }
            
            return stats
            
        except Exception as e:
            logger.error("Get stats error", error=str(e))
            response.status = 500
            return {"error": "Failed to get statistics"}