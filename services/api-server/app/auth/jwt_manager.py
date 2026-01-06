"""
JWT Token Management for Flask API Server
Handles JWT token generation, validation, and refresh for users and clients
"""

import jwt
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import redis
import logging
import uuid

logger = logging.getLogger(__name__)


class JWTManager:
    """
    JWT token management for Flask applications
    Supports token generation, validation, refresh, and revocation with Redis caching
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
        self.redis_client = None

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

    def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info("JWT Manager initialized with Redis connection")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def generate_token(
        self,
        user_id: str,
        user_type: str,
        permissions: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Generate JWT access and refresh tokens for user/client

        Args:
            user_id: Unique identifier for the user/client
            user_type: Type (user, service_account, api_client)
            permissions: List of permitted actions
            metadata: Additional user metadata

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
            "sub": user_id,
            "user_type": user_type,
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
            "sub": user_id,
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
        self._cache_token_metadata(access_jti, {
            "user_id": user_id,
            "user_type": user_type,
            "permissions": permissions,
            "expires_at": access_expires.isoformat(),
            "active": "true"
        })

        self._cache_token_metadata(refresh_jti, {
            "user_id": user_id,
            "type": "refresh",
            "expires_at": refresh_expires.isoformat(),
            "active": "true"
        })

        logger.info(f"Generated tokens for user {user_id}")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": access_expires.isoformat(),
            "token_type": "Bearer"
        }

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate JWT token and return payload if valid
        Uses Redis caching for fast validation
        """
        try:
            # Decode without verification first to get JTI
            unverified = jwt.decode(token, options={"verify_signature": False})
            jti = unverified.get("jti")

            if not jti:
                return None

            # Check Redis cache first
            cached_metadata = self._get_cached_token_metadata(jti)
            if not cached_metadata or cached_metadata.get("active") != "true":
                return None

            # Verify signature and expiration
            payload = jwt.decode(
                token,
                self.public_pem,
                algorithms=["RS256"]
            )

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expired")
            try:
                jti = jwt.decode(token, options={"verify_signature": False}).get("jti")
                if jti:
                    self._invalidate_token(jti)
            except Exception:
                pass
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    def refresh_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Refresh access token using valid refresh token"""
        payload = self.validate_token(refresh_token)

        if not payload or payload.get("type") != "refresh":
            return None

        user_id = payload["sub"]
        user_type = payload.get("user_type", "unknown")
        permissions = payload.get("permissions", ["basic"])

        return self.generate_token(
            user_id=user_id,
            user_type=user_type,
            permissions=permissions
        )

    def revoke_token(self, jti: str) -> bool:
        """Revoke a specific token by JTI"""
        return self._invalidate_token(jti)

    def revoke_all_tokens(self, user_id: str) -> int:
        """Revoke all tokens for a specific user"""
        pattern = f"token_metadata:{user_id}:*"
        keys = self.redis_client.keys(pattern)

        if keys:
            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.hset(key, "active", "false")
            pipe.execute()
            logger.info(f"Revoked all tokens for user {user_id}, count: {len(keys)}")
            return len(keys)

        return 0

    def get_public_key(self) -> str:
        """Get public key for token validation"""
        return self.public_pem.decode('utf-8')

    def _cache_token_metadata(self, jti: str, metadata: Dict[str, Any]):
        """Cache token metadata in Redis"""
        key = f"token_metadata:{jti}"
        self.redis_client.hset(key, mapping=metadata)

        # Set expiration based on token type
        if metadata.get("type") == "refresh":
            ttl = int(self.refresh_expiry.total_seconds())
        else:
            ttl = int(self.token_expiry.total_seconds())

        self.redis_client.expire(key, ttl)

    def _get_cached_token_metadata(self, jti: str) -> Optional[Dict[str, Any]]:
        """Get cached token metadata from Redis"""
        key = f"token_metadata:{jti}"
        return self.redis_client.hgetall(key)

    def _invalidate_token(self, jti: str) -> bool:
        """Mark token as inactive in Redis"""
        key = f"token_metadata:{jti}"
        result = self.redis_client.hset(key, "active", "false")
        return bool(result)

    def close(self):
        """Close Redis connections"""
        if self.redis_client:
            self.redis_client.close()
