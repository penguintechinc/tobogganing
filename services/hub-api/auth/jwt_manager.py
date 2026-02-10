"""
JWT Token Management for SASEWaddle Manager Service
Handles JWT token generation, validation, and refresh for nodes and clients
"""

import jwt
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import redis.asyncio as redis
import structlog
import uuid

logger = structlog.get_logger()


class JWTManager:
    """
    Async JWT token management for high-throughput SASE authentication
    Supports thousands of concurrent requests with Redis caching
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        token_expiry_hours: int = 24,
        refresh_expiry_days: int = 7,
        secret_key: Optional[str] = None
    ):
        self.redis_url = redis_url
        self.token_expiry = timedelta(hours=token_expiry_hours)
        self.refresh_expiry = timedelta(days=refresh_expiry_days)
        self.redis_pool = None
        
        # Generate RSA key pair for JWT signing
        if secret_key:
            self.secret_key = secret_key
        else:
            self._generate_rsa_keys()
    
    def _generate_rsa_keys(self):
        """Generate RSA private/public key pair for JWT signing"""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        self.private_key = private_key
        self.public_key = private_key.public_key()
        
        # Serialize for storage/transmission
        self.private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        self.public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    
    async def initialize(self):
        """Initialize Redis connection pool"""
        self.redis_pool = redis.ConnectionPool.from_url(
            self.redis_url, 
            max_connections=100,
            decode_responses=True
        )
        self.redis_client = redis.Redis(connection_pool=self.redis_pool)
        logger.info("JWT Manager initialized with Redis connection")
    
    async def generate_token(
        self, 
        node_id: str, 
        node_type: str,
        permissions: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Generate JWT access and refresh tokens for node/client
        
        Args:
            node_id: Unique identifier for the node/client
            node_type: Type (kubernetes_node, raw_compute, client_docker, client_native)
            permissions: List of permitted actions
            metadata: Additional node metadata
            
        Returns:
            Dict containing access_token, refresh_token, expires_at
        """
        now = datetime.now(timezone.utc)
        access_expires = now + self.token_expiry
        refresh_expires = now + self.refresh_expiry
        
        # Generate unique JTI for token tracking
        access_jti = str(uuid.uuid4())
        refresh_jti = str(uuid.uuid4())
        
        # Access token payload
        access_payload = {
            "sub": node_id,
            "node_type": node_type,
            "permissions": permissions,
            "iat": int(now.timestamp()),
            "exp": int(access_expires.timestamp()),
            "jti": access_jti,
            "type": "access"
        }
        
        if metadata:
            access_payload["metadata"] = metadata
        
        # Refresh token payload (minimal for security)
        refresh_payload = {
            "sub": node_id,
            "iat": int(now.timestamp()),
            "exp": int(refresh_expires.timestamp()),
            "jti": refresh_jti,
            "type": "refresh"
        }
        
        # Sign tokens
        access_token = jwt.encode(
            access_payload, 
            self.private_pem, 
            algorithm="RS256"
        )
        
        refresh_token = jwt.encode(
            refresh_payload,
            self.private_pem,
            algorithm="RS256"
        )
        
        # Cache token metadata in Redis for fast validation
        await self._cache_token_metadata(access_jti, {
            "node_id": node_id,
            "node_type": node_type,
            "permissions": permissions,
            "expires_at": access_expires.isoformat(),
            "active": True
        })
        
        await self._cache_token_metadata(refresh_jti, {
            "node_id": node_id,
            "type": "refresh", 
            "expires_at": refresh_expires.isoformat(),
            "active": True
        })
        
        logger.info("Generated tokens for node", node_id=node_id, node_type=node_type)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": access_expires.isoformat(),
            "token_type": "Bearer"
        }
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate JWT token and return payload if valid
        Uses Redis caching for high-performance validation
        """
        try:
            # Decode without verification first to get JTI
            unverified = jwt.decode(token, options={"verify_signature": False})
            jti = unverified.get("jti")
            
            if not jti:
                return None
                
            # Check Redis cache first
            cached_metadata = await self._get_cached_token_metadata(jti)
            if not cached_metadata or not cached_metadata.get("active"):
                return None
            
            # Verify signature and expiration
            payload = jwt.decode(
                token,
                self.public_pem,
                algorithms=["RS256"]
            )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired", jti=jti)
            await self._invalidate_token(jti)
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token", error=str(e))
            return None
    
    async def refresh_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Refresh access token using valid refresh token"""
        payload = await self.validate_token(refresh_token)
        
        if not payload or payload.get("type") != "refresh":
            return None
        
        node_id = payload["sub"]
        
        # Get original token metadata to recreate access token
        # In production, you'd store this info associated with the node
        # For now, using basic permissions
        return await self.generate_token(
            node_id=node_id,
            node_type="unknown",  # Would be stored in user/node registry
            permissions=["basic"]  # Would be retrieved from node registry
        )
    
    async def revoke_token(self, jti: str) -> bool:
        """Revoke a specific token by JTI"""
        return await self._invalidate_token(jti)
    
    async def revoke_all_tokens(self, node_id: str) -> int:
        """Revoke all tokens for a specific node"""
        pattern = f"token:{node_id}:*"
        keys = await self.redis_client.keys(pattern)
        
        if keys:
            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.hset(key, "active", "false")
            await pipe.execute()
            logger.info("Revoked all tokens for node", node_id=node_id, count=len(keys))
            return len(keys)
        
        return 0
    
    async def get_public_key(self) -> str:
        """Get public key for headend servers to validate tokens"""
        return self.public_pem.decode('utf-8')
    
    async def _cache_token_metadata(self, jti: str, metadata: Dict[str, Any]):
        """Cache token metadata in Redis"""
        key = f"token_metadata:{jti}"
        await self.redis_client.hset(key, mapping=metadata)
        
        # Set expiration based on token type
        if metadata.get("type") == "refresh":
            ttl = int(self.refresh_expiry.total_seconds())
        else:
            ttl = int(self.token_expiry.total_seconds())
        
        await self.redis_client.expire(key, ttl)
    
    async def _get_cached_token_metadata(self, jti: str) -> Optional[Dict[str, Any]]:
        """Get cached token metadata from Redis"""
        key = f"token_metadata:{jti}"
        return await self.redis_client.hgetall(key)
    
    async def _invalidate_token(self, jti: str) -> bool:
        """Mark token as inactive in Redis"""
        key = f"token_metadata:{jti}"
        result = await self.redis_client.hset(key, "active", "false")
        return bool(result)
    
    async def cleanup_expired_tokens(self):
        """Background task to cleanup expired token metadata"""
        pattern = "token_metadata:*"
        cursor = 0
        
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor=cursor, 
                match=pattern, 
                count=1000
            )
            
            if keys:
                pipe = self.redis_client.pipeline()
                for key in keys:
                    pipe.ttl(key)
                ttls = await pipe.execute()
                
                # Remove keys that are expired
                expired_keys = [key for key, ttl in zip(keys, ttls) if ttl == -2]
                if expired_keys:
                    await self.redis_client.delete(*expired_keys)
                    logger.info("Cleaned up expired tokens", count=len(expired_keys))
            
            if cursor == 0:
                break
        
        logger.info("Token cleanup completed")
    
    async def close(self):
        """Close Redis connections"""
        if self.redis_client:
            await self.redis_client.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()