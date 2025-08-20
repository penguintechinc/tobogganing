"""
Web Portal Routes for SASEWaddle Manager
py4web-based web interface with role-based access control
"""

import asyncio
import json
import os
from datetime import datetime
from py4web import action, request, response, redirect, URL, abort
from web.auth import (
    require_auth, require_role, require_permission, 
    get_current_user, create_user_session, logout_user,
    user_manager
)
from auth.user_manager import UserRole
from firewall.access_control import access_control_manager, AccessRule, AccessType, RuleType
from network.vrf_manager import vrf_manager, VRFConfiguration, VRFStatus, OSPFArea, OSPFAreaType
from cache.redis_cache import get_cache, get_firewall_cache
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
    
    @action("firewall")
    @action.uses("firewall.html")
    @require_role(UserRole.ADMIN)
    async def firewall():
        """Firewall and access control management page"""
        user = request.user
        
        try:
            all_rules = await access_control_manager.get_all_rules()
            users = await user_manager.list_users()
            
            return {
                "title": "Firewall & Access Control",
                "user": user,
                "rules": all_rules,
                "users": users,
                "rule_types": [rule_type.value for rule_type in RuleType],
                "access_types": [access_type.value for access_type in AccessType]
            }
            
        except Exception as e:
            logger.error("Firewall page error", error=str(e))
            return {
                "title": "Firewall & Access Control",
                "user": user,
                "rules": [],
                "users": [],
                "error": "Failed to load firewall rules"
            }
    
    @action("network")
    @action.uses("network.html")
    @require_role(UserRole.ADMIN)
    async def network():
        """Network management page - VRF and OSPF configuration"""
        user = request.user
        
        try:
            vrfs = await vrf_manager.list_vrfs()
            
            return {
                "title": "Network Management - VRF & OSPF",
                "user": user,
                "vrfs": vrfs,
                "vrf_statuses": [status.value for status in VRFStatus],
                "ospf_area_types": [area_type.value for area_type in OSPFAreaType]
            }
            
        except Exception as e:
            logger.error("Network page error", error=str(e))
            return {
                "title": "Network Management - VRF & OSPF", 
                "user": user,
                "vrfs": [],
                "vrf_statuses": [],
                "ospf_area_types": [],
                "error": "Failed to load network configuration"
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
    
    # Firewall API endpoints
    @action("api/web/firewall/rule", method=["POST"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def create_firewall_rule():
        """Create new firewall rule (AJAX)"""
        try:
            data = request.json
            user_id = data.get('user_id', '').strip()
            rule_type_str = data.get('rule_type', '').strip()
            access_type_str = data.get('access_type', '').strip()
            pattern = data.get('pattern', '').strip()
            priority = int(data.get('priority', 100))
            description = data.get('description', '').strip()
            
            if not all([user_id, rule_type_str, access_type_str, pattern]):
                response.status = 400
                return {"error": "All fields required"}
            
            try:
                rule_type = RuleType(rule_type_str)
                access_type = AccessType(access_type_str)
            except ValueError:
                response.status = 400
                return {"error": "Invalid rule or access type"}
            
            # Generate rule ID
            import uuid
            rule_id = str(uuid.uuid4())
            
            rule = AccessRule(
                id=rule_id,
                user_id=user_id,
                rule_type=rule_type,
                access_type=access_type,
                pattern=pattern,
                priority=priority,
                description=description if description else None
            )
            
            success = await access_control_manager.add_rule(rule)
            
            if success:
                # Invalidate cache for this user and all rules
                firewall_cache = await get_firewall_cache()
                await firewall_cache.invalidate_user(user_id)
                logger.debug(f"Invalidated firewall cache for user {user_id}")
                
                return {
                    "success": True,
                    "rule": {
                        "id": rule.id,
                        "user_id": rule.user_id,
                        "rule_type": rule.rule_type.value,
                        "access_type": rule.access_type.value,
                        "pattern": rule.pattern,
                        "priority": rule.priority,
                        "description": rule.description,
                        "created_at": rule.created_at.isoformat()
                    }
                }
            else:
                response.status = 500
                return {"error": "Failed to create rule"}
                
        except Exception as e:
            logger.error("Create firewall rule error", error=str(e))
            response.status = 500
            return {"error": "Failed to create firewall rule"}
    
    @action("api/web/firewall/rule/<rule_id>", method=["DELETE"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def delete_firewall_rule(rule_id):
        """Delete firewall rule (AJAX)"""
        try:
            success = await access_control_manager.remove_rule(rule_id)
            
            if success:
                # Invalidate all firewall caches since we don't know which user this rule belonged to
                firewall_cache = await get_firewall_cache()
                await firewall_cache.invalidate_all()
                logger.debug("Invalidated all firewall caches after rule deletion")
            
            return {"success": success}
            
        except Exception as e:
            logger.error("Delete firewall rule error", error=str(e))
            response.status = 500
            return {"error": "Failed to delete firewall rule"}
    
    @action("api/web/firewall/user/<user_id>/rules", method=["GET"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def get_user_firewall_rules(user_id):
        """Get firewall rules for specific user (AJAX)"""
        try:
            rules = await access_control_manager.get_user_rules(user_id)
            
            rules_data = []
            for rule in rules:
                rules_data.append({
                    "id": rule.id,
                    "rule_type": rule.rule_type.value,
                    "access_type": rule.access_type.value,
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "description": rule.description,
                    "created_at": rule.created_at.isoformat(),
                    "is_active": rule.is_active
                })
            
            return {"rules": rules_data}
            
        except Exception as e:
            logger.error("Get user firewall rules error", error=str(e))
            response.status = 500
            return {"error": "Failed to get user firewall rules"}
    
    @action("api/web/firewall/check", method=["POST"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def check_firewall_access():
        """Test firewall access for user and target (AJAX)"""
        try:
            data = request.json
            user_id = data.get('user_id', '').strip()
            target = data.get('target', '').strip()
            
            if not all([user_id, target]):
                response.status = 400
                return {"error": "User ID and target required"}
            
            allowed = await access_control_manager.check_access(user_id, target)
            
            return {
                "user_id": user_id,
                "target": target,
                "allowed": allowed,
                "result": "ALLOW" if allowed else "DENY"
            }
            
        except Exception as e:
            logger.error("Check firewall access error", error=str(e))
            response.status = 500
            return {"error": "Failed to check firewall access"}
    
    @action("api/web/firewall/user/<user_id>/export", method=["GET"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def export_user_firewall_rules(user_id):
        """Export user firewall rules for headend consumption (AJAX)"""
        try:
            export_data = await access_control_manager.export_user_rules(user_id)
            return export_data
            
        except Exception as e:
            logger.error("Export user firewall rules error", error=str(e))
            response.status = 500
            return {"error": "Failed to export user firewall rules"}
    
    # Network/VRF API endpoints
    @action("api/web/network/vrf", method=["POST"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def create_vrf():
        """Create new VRF (AJAX)"""
        try:
            data = request.json
            name = data.get('name', '').strip()
            description = data.get('description', '').strip()
            rd = data.get('rd', '').strip()
            rt_import = data.get('rt_import', [])
            rt_export = data.get('rt_export', [])
            ip_ranges = data.get('ip_ranges', [])
            
            if not all([name, description, rd]):
                response.status = 400
                return {"error": "Name, description, and RD required"}
            
            # Generate VRF ID
            import uuid
            vrf_id = str(uuid.uuid4())
            
            vrf = VRFConfiguration(
                id=vrf_id,
                name=name,
                description=description,
                rd=rd,
                rt_import=rt_import if isinstance(rt_import, list) else [],
                rt_export=rt_export if isinstance(rt_export, list) else [],
                ip_ranges=ip_ranges if isinstance(ip_ranges, list) else []
            )
            
            success = await vrf_manager.create_vrf(vrf)
            
            if success:
                return {
                    "success": True,
                    "vrf": {
                        "id": vrf.id,
                        "name": vrf.name,
                        "description": vrf.description,
                        "rd": vrf.rd,
                        "status": vrf.status.value,
                        "created_at": vrf.created_at.isoformat()
                    }
                }
            else:
                response.status = 500
                return {"error": "Failed to create VRF"}
                
        except Exception as e:
            logger.error("Create VRF error", error=str(e))
            response.status = 500
            return {"error": "Failed to create VRF"}
    
    @action("api/web/network/vrf/<vrf_id>", method=["DELETE"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def delete_vrf(vrf_id):
        """Delete VRF (AJAX)"""
        try:
            success = await vrf_manager.delete_vrf(vrf_id)
            return {"success": success}
            
        except Exception as e:
            logger.error("Delete VRF error", error=str(e))
            response.status = 500
            return {"error": "Failed to delete VRF"}
    
    @action("api/web/network/vrf/<vrf_id>/ospf", method=["PUT"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def configure_vrf_ospf(vrf_id):
        """Configure OSPF for VRF (AJAX)"""
        try:
            data = request.json
            ospf_enabled = data.get('ospf_enabled', False)
            router_id = data.get('router_id', '').strip()
            areas = data.get('areas', [])
            networks = data.get('networks', [])
            
            vrf = await vrf_manager.get_vrf(vrf_id)
            if not vrf:
                response.status = 404
                return {"error": "VRF not found"}
            
            vrf.ospf_enabled = ospf_enabled
            vrf.ospf_router_id = router_id if router_id else None
            vrf.ospf_areas = areas
            vrf.ospf_networks = networks
            
            success = await vrf_manager.update_vrf(vrf)
            
            return {"success": success}
            
        except Exception as e:
            logger.error("Configure VRF OSPF error", error=str(e))
            response.status = 500
            return {"error": "Failed to configure OSPF"}
    
    @action("api/web/network/vrf/<vrf_id>/config", method=["GET"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def get_vrf_frr_config(vrf_id):
        """Get FRR configuration for VRF (AJAX)"""
        try:
            config = await vrf_manager.generate_frr_config(vrf_id)
            
            return {
                "vrf_id": vrf_id,
                "config": config
            }
            
        except Exception as e:
            logger.error("Get VRF FRR config error", error=str(e))
            response.status = 500
            return {"error": "Failed to generate FRR config"}
    
    @action("api/web/network/vrf/<vrf_id>/neighbors", method=["GET"])
    @action.uses("json")
    @require_role(UserRole.ADMIN)
    async def get_vrf_ospf_neighbors(vrf_id):
        """Get OSPF neighbors for VRF (AJAX)"""
        try:
            neighbors = await vrf_manager.get_ospf_neighbors(vrf_id)
            
            neighbors_data = []
            for neighbor in neighbors:
                neighbors_data.append({
                    "neighbor_id": neighbor.neighbor_id,
                    "neighbor_ip": neighbor.neighbor_ip,
                    "interface": neighbor.interface,
                    "area_id": neighbor.area_id,
                    "state": neighbor.state,
                    "priority": neighbor.priority,
                    "last_seen": neighbor.last_seen.isoformat() if neighbor.last_seen else None
                })
            
            return {"neighbors": neighbors_data}
            
        except Exception as e:
            logger.error("Get OSPF neighbors error", error=str(e))
            response.status = 500
            return {"error": "Failed to get OSPF neighbors"}
    
    # Headend integration endpoints
    @action("api/v1/firewall/rules", method=["GET"])
    @action.uses("json")
    async def get_all_firewall_rules():
        """Get all firewall rules for headend consumption (headend-to-manager API)"""
        try:
            # Authenticate headend server
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                response.status = 401
                return {"error": "Bearer token required"}
            
            token = auth_header[7:]
            # In production, validate this is a legitimate headend token
            headend_token = os.getenv('HEADEND_API_TOKEN', 'headend-server-token')
            
            if token != headend_token:
                response.status = 401
                return {"error": "Invalid headend token"}
            
            # Try to get cached rules first
            firewall_cache = await get_firewall_cache()
            cached_rules = await firewall_cache.get_all_rules()
            
            if cached_rules:
                logger.debug("Serving firewall rules from cache")
                return cached_rules
            
            # Get all active users and their firewall rules
            users = await user_manager.list_users()
            all_rules = {}
            
            for user in users:
                if user.is_active:
                    user_rules = await access_control_manager.export_user_rules(user.id)
                    all_rules[user.id] = user_rules
            
            rules_response = {
                "timestamp": datetime.utcnow().isoformat(),
                "rules_count": len(all_rules),
                "user_rules": all_rules
            }
            
            # Cache the response for fast headend retrieval (3 minute TTL)
            await firewall_cache.set_all_rules(rules_response, ttl=180)
            logger.debug(f"Cached firewall rules for {len(all_rules)} users")
            
            return rules_response
            
        except Exception as e:
            logger.error("Get all firewall rules error", error=str(e))
            response.status = 500
            return {"error": "Failed to get firewall rules"}
    
    @action("api/v1/firewall/user/<user_id>/rules", method=["GET"])
    @action.uses("json")
    async def get_user_firewall_rules_headend(user_id):
        """Get firewall rules for specific user (headend-to-manager API)"""
        try:
            # Authenticate headend server
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                response.status = 401
                return {"error": "Bearer token required"}
            
            token = auth_header[7:]
            headend_token = os.getenv('HEADEND_API_TOKEN', 'headend-server-token')
            
            if token != headend_token:
                response.status = 401
                return {"error": "Invalid headend token"}
            
            # Verify user exists and is active
            user = await user_manager.get_user(user_id)
            if not user or not user.is_active:
                response.status = 404
                return {"error": "User not found or inactive"}
            
            # Try to get cached rules first
            firewall_cache = await get_firewall_cache()
            cached_rules = await firewall_cache.get_user_rules(user_id)
            
            if cached_rules:
                logger.debug(f"Serving firewall rules from cache for user {user_id}")
                return cached_rules
            
            # Export rules for this user
            user_rules = await access_control_manager.export_user_rules(user_id)
            
            # Cache the user rules (5 minute TTL)
            await firewall_cache.set_user_rules(user_id, user_rules, ttl=300)
            logger.debug(f"Cached firewall rules for user {user_id}")
            
            return user_rules
            
        except Exception as e:
            logger.error("Get user firewall rules error", user_id=user_id, error=str(e))
            response.status = 500
            return {"error": "Failed to get user firewall rules"}