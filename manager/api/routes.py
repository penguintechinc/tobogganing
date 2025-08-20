from py4web import action, request, response, abort
import json
import structlog
from typing import Optional
import uuid

logger = structlog.get_logger()

def setup_routes(app, cluster_manager, client_registry, cert_manager, jwt_manager):
    
    @action("api/v1/clusters/register", method=["POST"])
    @action.uses("json")
    async def register_cluster():
        try:
            data = await request.json()
            
            # Validate required fields
            required = ['name', 'region', 'datacenter', 'headend_url']
            for field in required:
                if field not in data:
                    response.status = 400
                    return {"error": f"Missing required field: {field}"}
            
            # Generate cluster ID
            data['id'] = str(uuid.uuid4())
            
            # Register cluster
            cluster = await cluster_manager.register_cluster(data)
            
            # Generate headend certificate
            key, cert, ca = await cert_manager.generate_headend_certificate(
                cluster.id,
                cluster.name,
                [cluster.headend_url.split("://")[1].split(":")[0]]
            )
            
            return {
                "cluster_id": cluster.id,
                "status": "registered",
                "certificates": {
                    "key": key,
                    "cert": cert,
                    "ca": ca
                }
            }
        except Exception as e:
            logger.error(f"Failed to register cluster: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/clusters/<cluster_id>/heartbeat", method=["POST"])
    @action.uses("json")
    async def cluster_heartbeat(cluster_id):
        try:
            data = await request.json()
            client_count = data.get('client_count', 0)
            
            success = await cluster_manager.update_heartbeat(cluster_id, client_count)
            
            if not success:
                response.status = 404
                return {"error": "Cluster not found"}
            
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/clusters", method=["GET"])
    @action.uses("json")
    async def list_clusters():
        try:
            clusters = await cluster_manager.get_all_clusters()
            return {
                "clusters": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "region": c.region,
                        "datacenter": c.datacenter,
                        "status": c.status,
                        "client_count": c.client_count
                    }
                    for c in clusters
                ]
            }
        except Exception as e:
            logger.error(f"List clusters error: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/clients/register", method=["POST"])
    @action.uses("json")
    async def register_client():
        try:
            data = await request.json()
            
            # Validate required fields
            required = ['name', 'type', 'public_key']
            for field in required:
                if field not in data:
                    response.status = 400
                    return {"error": f"Missing required field: {field}"}
            
            # Validate client type
            if data['type'] not in ['docker', 'native']:
                response.status = 400
                return {"error": "Invalid client type"}
            
            # Generate client ID
            data['id'] = str(uuid.uuid4())
            
            # Get optimal cluster
            location = data.get('location', {})
            cluster = await cluster_manager.get_optimal_cluster(location)
            
            if not cluster:
                response.status = 503
                return {"error": "No available clusters"}
            
            data['cluster_id'] = cluster.id
            
            # Register client
            client, api_key = await client_registry.register_client(data)
            
            # Generate client certificate
            key, cert, ca = await cert_manager.generate_client_certificate(
                client.id,
                client.name,
                client.type
            )
            
            return {
                "client_id": client.id,
                "api_key": api_key,
                "cluster": {
                    "id": cluster.id,
                    "headend_url": cluster.headend_url
                },
                "certificates": {
                    "key": key,
                    "cert": cert,
                    "ca": ca
                }
            }
        except Exception as e:
            logger.error(f"Failed to register client: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/clients/<client_id>/config", method=["GET"])
    @action.uses("json")
    async def get_client_config(client_id):
        try:
            # Authenticate using API key
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                response.status = 401
                return {"error": "Invalid authorization header"}
            
            api_key = auth_header[7:]
            client = await client_registry.authenticate_client(api_key)
            
            if not client or client.id != client_id:
                response.status = 401
                return {"error": "Unauthorized"}
            
            # Get cluster info
            cluster = await cluster_manager.get_cluster(client.cluster_id)
            
            if not cluster:
                response.status = 503
                return {"error": "Cluster not available"}
            
            return {
                "client_id": client.id,
                "cluster": {
                    "id": cluster.id,
                    "headend_url": cluster.headend_url,
                    "region": cluster.region,
                    "datacenter": cluster.datacenter
                },
                "status": client.status
            }
        except Exception as e:
            logger.error(f"Get config error: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/clients/<client_id>/rotate-key", method=["POST"])
    @action.uses("json")
    async def rotate_client_key(client_id):
        try:
            # Authenticate using current API key
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                response.status = 401
                return {"error": "Invalid authorization header"}
            
            api_key = auth_header[7:]
            client = await client_registry.authenticate_client(api_key)
            
            if not client or client.id != client_id:
                response.status = 401
                return {"error": "Unauthorized"}
            
            # Rotate API key
            new_api_key = await client_registry.rotate_api_key(client_id)
            
            if not new_api_key:
                response.status = 500
                return {"error": "Failed to rotate key"}
            
            return {
                "client_id": client_id,
                "new_api_key": new_api_key
            }
        except Exception as e:
            logger.error(f"Key rotation error: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/clients", method=["GET"])
    @action.uses("json")
    async def list_clients():
        try:
            # This endpoint should require admin authentication
            # For now, we'll allow it for testing
            
            clients = await client_registry.get_all_clients()
            return {
                "clients": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "type": c.type,
                        "cluster_id": c.cluster_id,
                        "status": c.status,
                        "last_seen": c.last_seen.isoformat()
                    }
                    for c in clients
                ]
            }
        except Exception as e:
            logger.error(f"List clients error: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/certs/generate", method=["POST"])
    @action.uses("json")
    async def generate_certificate():
        try:
            data = await request.json()
            
            cert_type = data.get('type', 'client')
            
            if cert_type == 'client':
                key, cert, ca = await cert_manager.generate_client_certificate(
                    data.get('id', str(uuid.uuid4())),
                    data.get('name', 'client'),
                    data.get('client_type', 'docker')
                )
            elif cert_type == 'headend':
                key, cert, ca = await cert_manager.generate_headend_certificate(
                    data.get('id', str(uuid.uuid4())),
                    data.get('name', 'headend'),
                    data.get('san_names', [])
                )
            else:
                response.status = 400
                return {"error": "Invalid certificate type"}
            
            return {
                "type": cert_type,
                "certificates": {
                    "key": key,
                    "cert": cert,
                    "ca": ca
                }
            }
        except Exception as e:
            logger.error(f"Certificate generation error: {e}")
            response.status = 500
            return {"error": "Internal server error"}
    
    # JWT Authentication Endpoints
    @action("api/v1/auth/token", method=["POST"])
    @action.uses("json")
    async def generate_jwt_token():
        """Generate JWT token for authenticated node/client"""
        try:
            data = await request.json()
            
            # Validate required fields for JWT generation
            required = ['node_id', 'node_type', 'api_key']
            for field in required:
                if field not in data:
                    response.status = 400
                    return {"error": f"Missing required field: {field}"}
            
            node_id = data['node_id']
            node_type = data['node_type']
            api_key = data['api_key']
            
            # Authenticate based on node type
            authenticated = False
            permissions = []
            metadata = {}
            
            if node_type in ['kubernetes_node', 'raw_compute']:
                # Authenticate cluster/headend nodes
                cluster = await cluster_manager.authenticate_cluster(api_key)
                if cluster:
                    authenticated = True
                    permissions = ['headend', 'proxy', 'wireguard', 'mirror_traffic']
                    metadata = {
                        'cluster_id': cluster.id,
                        'region': cluster.region,
                        'datacenter': cluster.datacenter
                    }
            elif node_type in ['client_docker', 'client_native']:
                # Authenticate client nodes
                client = await client_registry.authenticate_client(api_key)
                if client and client.id == node_id:
                    authenticated = True
                    permissions = ['connect', 'tunnel', 'route']
                    metadata = {
                        'client_id': client.id,
                        'client_type': client.type,
                        'cluster_id': client.cluster_id
                    }
            
            if not authenticated:
                response.status = 401
                return {"error": "Authentication failed"}
            
            # Generate JWT tokens
            tokens = await jwt_manager.generate_token(
                node_id=node_id,
                node_type=node_type,
                permissions=permissions,
                metadata=metadata
            )
            
            logger.info("JWT tokens generated", node_id=node_id, node_type=node_type)
            
            return tokens
            
        except Exception as e:
            logger.error("JWT token generation failed", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/auth/refresh", method=["POST"])
    @action.uses("json")
    async def refresh_jwt_token():
        """Refresh JWT access token using refresh token"""
        try:
            data = await request.json()
            
            refresh_token = data.get('refresh_token')
            if not refresh_token:
                response.status = 400
                return {"error": "Missing refresh_token"}
            
            # Refresh the token
            new_tokens = await jwt_manager.refresh_token(refresh_token)
            
            if not new_tokens:
                response.status = 401
                return {"error": "Invalid or expired refresh token"}
            
            return new_tokens
            
        except Exception as e:
            logger.error("JWT token refresh failed", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/auth/validate", method=["POST"])
    @action.uses("json")
    async def validate_jwt_token():
        """Validate JWT token (for headend servers)"""
        try:
            # Get token from Authorization header
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                response.status = 401
                return {"error": "Invalid authorization header"}
            
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            
            # Validate the token
            payload = await jwt_manager.validate_token(token)
            
            if not payload:
                response.status = 401
                return {"error": "Invalid or expired token"}
            
            return {
                "valid": True,
                "node_id": payload.get("sub"),
                "node_type": payload.get("node_type"),
                "permissions": payload.get("permissions", []),
                "metadata": payload.get("metadata", {}),
                "expires_at": payload.get("exp")
            }
            
        except Exception as e:
            logger.error("JWT token validation failed", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/auth/revoke", method=["POST"])
    @action.uses("json")
    async def revoke_jwt_token():
        """Revoke specific JWT token or all tokens for a node"""
        try:
            data = await request.json()
            
            if 'node_id' in data:
                # Revoke all tokens for a node
                count = await jwt_manager.revoke_all_tokens(data['node_id'])
                return {"revoked": count, "node_id": data['node_id']}
            elif 'jti' in data:
                # Revoke specific token by JTI
                success = await jwt_manager.revoke_token(data['jti'])
                return {"revoked": success, "jti": data['jti']}
            else:
                response.status = 400
                return {"error": "Missing node_id or jti"}
                
        except Exception as e:
            logger.error("JWT token revocation failed", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/auth/public-key", method=["GET"])
    @action.uses("json")
    async def get_jwt_public_key():
        """Get public key for JWT verification (for headend servers)"""
        try:
            public_key = await jwt_manager.get_public_key()
            return {
                "public_key": public_key,
                "algorithm": "RS256",
                "use": "sig"
            }
        except Exception as e:
            logger.error("Failed to get public key", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    # WireGuard Certificate Management Endpoints
    @action("api/v1/wireguard/keys", method=["POST"])
    @action.uses("json")
    async def generate_wireguard_keys():
        """Generate WireGuard keys and certificates for authenticated nodes"""
        try:
            data = await request.json()
            
            required = ['node_id', 'node_type', 'api_key']
            for field in required:
                if field not in data:
                    response.status = 400
                    return {"error": f"Missing required field: {field}"}
            
            node_id = data['node_id']
            node_type = data['node_type']
            api_key = data['api_key']
            
            # Authenticate based on node type
            authenticated = False
            
            if node_type in ['kubernetes_node', 'raw_compute', 'headend']:
                cluster = await cluster_manager.authenticate_cluster(api_key)
                authenticated = cluster is not None
            elif node_type in ['client_docker', 'client_native']:
                client = await client_registry.authenticate_client(api_key)
                authenticated = client is not None and client.id == node_id
            
            if not authenticated:
                response.status = 401
                return {"error": "Authentication failed"}
            
            # Generate WireGuard keys and assign IP
            wg_config = await cert_manager.generate_wireguard_keys(node_id, node_type)
            
            # Generate X.509 certificate for WireGuard authentication
            if node_type in ['headend', 'kubernetes_node', 'raw_compute']:
                cert_key, cert_pem, ca_cert = await cert_manager.generate_headend_certificate(
                    node_id,
                    f"{node_type}-{node_id}",
                    [wg_config['ip_address']]
                )
            else:
                cert_key, cert_pem, ca_cert = await cert_manager.generate_client_certificate(
                    node_id,
                    f"{node_type}-{node_id}",
                    node_type
                )
            
            logger.info("Generated WireGuard keys and certificate", 
                       node_id=node_id, 
                       node_type=node_type)
            
            return {
                "node_id": node_id,
                "wireguard": {
                    "private_key": wg_config['private_key'],
                    "public_key": wg_config['public_key'],
                    "ip_address": wg_config['ip_address'],
                    "network_cidr": wg_config['network_cidr']
                },
                "certificates": {
                    "private_key": cert_key,
                    "certificate": cert_pem,
                    "ca_certificate": ca_cert
                },
                "authentication_note": "WireGuard requires both certificate AND JWT/SSO authentication"
            }
            
        except Exception as e:
            logger.error("WireGuard key generation failed", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/wireguard/peers", method=["GET"])
    @action.uses("json")
    async def get_wireguard_peers():
        """Get all WireGuard peer configurations (for headend servers)"""
        try:
            # Authenticate headend server
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                response.status = 401
                return {"error": "Invalid authorization header"}
            
            # This could be either JWT or API key - validate both
            token = auth_header[7:]
            
            # Try JWT validation first
            jwt_payload = await jwt_manager.validate_token(token)
            if jwt_payload and 'headend' in jwt_payload.get('permissions', []):
                # Authenticated via JWT
                pass
            else:
                # Try API key validation
                cluster = await cluster_manager.authenticate_cluster(token)
                if not cluster:
                    response.status = 401
                    return {"error": "Authentication failed"}
            
            # Get all WireGuard peers
            peers = await cert_manager.get_all_wireguard_peers()
            
            return {
                "peers": peers,
                "total": len(peers)
            }
            
        except Exception as e:
            logger.error("Failed to get WireGuard peers", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/wireguard/<node_id>/revoke", method=["POST"])
    @action.uses("json") 
    async def revoke_wireguard_keys(node_id):
        """Revoke WireGuard keys for a specific node"""
        try:
            # Admin authentication required (simplified for now)
            auth_header = request.headers.get('Authorization', '')
            if not auth_header:
                response.status = 401
                return {"error": "Authentication required"}
            
            success = await cert_manager.revoke_wireguard_keys(node_id)
            
            if success:
                return {"revoked": True, "node_id": node_id}
            else:
                response.status = 404
                return {"error": "Node not found"}
                
        except Exception as e:
            logger.error("WireGuard key revocation failed", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    # Headend Configuration Endpoint
    @action("api/v1/clusters/<cluster_id>/headend-config", method=["GET"])
    @action.uses("json")
    async def get_headend_config(cluster_id):
        """Get complete headend configuration for a cluster"""
        try:
            # Authenticate cluster
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                response.status = 401
                return {"error": "Invalid authorization header"}
            
            api_key = auth_header[7:]
            cluster = await cluster_manager.authenticate_cluster(api_key)
            
            if not cluster or cluster.id != cluster_id:
                response.status = 401
                return {"error": "Authentication failed"}
            
            # Get WireGuard configuration for this cluster
            wg_config = await cert_manager.get_wireguard_config(cluster_id)
            if not wg_config:
                # Generate WireGuard config for headend if not exists
                wg_config = await cert_manager.generate_wireguard_keys(cluster_id, "headend")
            
            # Get all peers for this cluster's WireGuard network
            peers = await cert_manager.get_all_wireguard_peers()
            
            # Build headend configuration
            config = {
                # Server ports
                "http_port": "8443",
                "tcp_port": "8444", 
                "udp_port": "8445",
                "metrics_port": "9090",
                "cert_file": "/certs/headend.crt",
                "key_file": "/certs/headend.key",
                
                # Authentication configuration
                "auth": {
                    "type": "jwt",  # Default to JWT, can be overridden by env vars
                    "manager_url": request.url_root.rstrip('/'),
                    "jwt_public_key": await jwt_manager.get_public_key(),
                    
                    # OAuth2 config (if needed)
                    "oauth2": {
                        "issuer": "",
                        "client_id": "",
                        "client_secret": "",
                        "redirect_url": ""
                    },
                    
                    # SAML2 config (if needed)  
                    "saml2": {
                        "idp_metadata_url": "",
                        "sp_entity_id": f"headend-{cluster_id}",
                        "sso_url": "",
                        "slo_url": ""
                    }
                },
                
                # WireGuard configuration
                "wireguard": {
                    "interface": "wg0",
                    "private_key": wg_config.get('private_key', ''),
                    "public_key": wg_config.get('public_key', ''),
                    "listen_port": 51820,
                    "network": "10.200.0.0/16",
                    "ip_address": wg_config.get('ip_address', '10.200.0.1'),
                    "peers": [
                        {
                            "node_id": peer['node_id'],
                            "node_type": peer['node_type'],
                            "public_key": peer['public_key'],
                            "allowed_ips": peer['allowed_ips'],
                            "endpoint": peer.get('endpoint')
                        } for peer in peers
                    ]
                },
                
                # Traffic mirroring configuration
                "mirror": {
                    "enabled": False,  # Default disabled
                    "destinations": [],
                    "protocol": "VXLAN",
                    "buffer_size": 1000,
                    "sample_rate": 100,
                    "filter": ""
                },
                
                # Proxy configuration
                "proxy": {
                    "skip_tls_verify": False,
                    "timeout_seconds": 30,
                    "max_idle_conns": 100
                }
            }
            
            logger.info("Provided headend configuration", cluster_id=cluster_id)
            return config
            
        except Exception as e:
            logger.error("Failed to get headend config", error=str(e))
            response.status = 500
            return {"error": "Internal server error"}
    
    @action("api/v1/status", method=["GET"])
    @action.uses("json")
    async def get_status():
        try:
            return {
                "service": "SASEWaddle Manager API",
                "version": open(".version").read().strip(),
                "clusters": {
                    "total": await cluster_manager.get_cluster_count(),
                    "active": len([c for c in await cluster_manager.get_all_clusters() if c.status == 'active'])
                },
                "clients": {
                    "total": await client_registry.get_client_count(),
                    "active": len([c for c in await client_registry.get_all_clients() if c.status == 'active'])
                }
            }
        except Exception as e:
            logger.error(f"Status error: {e}")
            response.status = 500
            return {"error": "Internal server error"}