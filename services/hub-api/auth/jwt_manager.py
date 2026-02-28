"""
JWT Token Management for Tobogganing Hub API
OIDC-compliant JWT generation, validation, and refresh (RFC 9068).
"""

import os
import base64
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import redis.asyncio as redis
import structlog
import uuid

logger = structlog.get_logger()


class JWTManager:
    """
    Async JWT token management for OIDC-compliant Tobogganing authentication.
    Produces RFC 9068 access tokens with tenant/team/role/scope claims.
    Supports high-throughput validation via Redis metadata cache.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        token_expiry_hours: int = 24,
        refresh_expiry_days: int = 7,
        secret_key: Optional[str] = None,
    ):
        self.redis_url = redis_url
        self.token_expiry = timedelta(hours=token_expiry_hours)
        self.refresh_expiry = timedelta(days=refresh_expiry_days)
        self.redis_pool = None
        self.issuer_url = os.getenv("OIDC_ISSUER_URL", "https://hub-api.tobogganing.io")

        # Generate RSA key pair for JWT signing
        if secret_key:
            self.secret_key = secret_key
        else:
            self._generate_rsa_keys()
    
    def _generate_rsa_keys(self):
        """Generate RSA-2048 private/public key pair for JWT signing."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        self.private_key = private_key
        self.public_key = private_key.public_key()

        # Deterministic kid derived from the public key modulus (first 8 bytes, hex)
        pub_numbers = self.public_key.public_numbers()
        n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, "big")
        self.kid = n_bytes[:8].hex()

        # Serialize for storage/transmission
        self.private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        self.public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    
    async def initialize(self):
        """Initialize Redis connection pool."""
        self.redis_pool = redis.ConnectionPool.from_url(
            self.redis_url,
            max_connections=100,
            decode_responses=True,
        )
        self.redis_client = redis.Redis(connection_pool=self.redis_pool)
        logger.info("jwt_manager_initialized", issuer=self.issuer_url)
    
    async def generate_token(
        self,
        subject: str,
        tenant: str,
        teams: list[str],
        roles: list[str],
        scopes: list[str],
        token_type: str = "access",
        attestation_confidence: int | None = None,
        attestation_method: str | None = None,
    ) -> dict[str, str]:
        """
        Generate OIDC-compliant access and refresh token pair (RFC 9068).

        Args:
            subject:    Unique subject identifier (user id, workload SPIFFE URI, etc.)
            tenant:     Tenant/organisation identifier
            teams:      List of team slugs the subject belongs to
            roles:      List of role names (e.g. ["admin", "viewer"])
            scopes:     OAuth2 scopes to embed (space-delimited per RFC 9068)
            token_type: Reserved; always "access" for this method

        Returns:
            Dict with access_token, refresh_token, expires_at, token_type
        """
        now = datetime.now(timezone.utc)
        access_expires = now + self.token_expiry
        refresh_expires = now + self.refresh_expiry

        access_jti = str(uuid.uuid4())
        refresh_jti = str(uuid.uuid4())

        # RFC 9068 / OIDC-compliant access token payload
        access_payload = {
            "sub": subject,
            "iss": self.issuer_url,
            "aud": ["tobogganing"],
            "scope": " ".join(scopes),  # space-delimited per RFC 9068
            "tenant": tenant,
            "teams": teams,
            "roles": roles,
            "iat": int(now.timestamp()),
            "exp": int(access_expires.timestamp()),
            "jti": access_jti,
            "type": "access",
        }

        # Optional attestation claims (from system fingerprint validation)
        if attestation_confidence is not None:
            access_payload["attest_conf"] = attestation_confidence
        if attestation_method is not None:
            access_payload["attest_method"] = attestation_method

        # Refresh token payload — minimal for security
        refresh_payload = {
            "sub": subject,
            "iss": self.issuer_url,
            "iat": int(now.timestamp()),
            "exp": int(refresh_expires.timestamp()),
            "jti": refresh_jti,
            "type": "refresh",
        }

        access_token = jwt.encode(access_payload, self.private_pem, algorithm="RS256")
        refresh_token = jwt.encode(refresh_payload, self.private_pem, algorithm="RS256")

        # Cache access token metadata (used by validate_token + refresh_token)
        await self._cache_token_metadata(access_jti, {
            "subject": subject,
            "tenant": tenant,
            "teams": ",".join(teams),
            "roles": ",".join(roles),
            "scopes": " ".join(scopes),
            "expires_at": access_expires.isoformat(),
            "active": "true",
        })

        # Cache refresh token metadata (links back to identity context)
        await self._cache_token_metadata(refresh_jti, {
            "subject": subject,
            "tenant": tenant,
            "teams": ",".join(teams),
            "roles": ",".join(roles),
            "scopes": " ".join(scopes),
            "type": "refresh",
            "expires_at": refresh_expires.isoformat(),
            "active": "true",
        })

        logger.info(
            "tokens_generated",
            subject=subject,
            tenant=tenant,
            roles=roles,
            scope_count=len(scopes),
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": access_expires.isoformat(),
            "token_type": "Bearer",
        }
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a JWT token and return its payload when valid.

        Checks (in order):
        1. JTI present in Redis cache and marked active
        2. RS256 signature verification
        3. iss matches self.issuer_url
        4. aud contains "tobogganing"

        The returned payload has `scope` normalised to a list.
        """
        jti: Optional[str] = None
        try:
            # Decode without verification to extract JTI for cache lookup
            unverified = jwt.decode(token, options={"verify_signature": False})
            jti = unverified.get("jti")

            if not jti:
                logger.warning("token_missing_jti")
                return None

            # Fast-path: Redis cache check before cryptographic verification
            cached_metadata = await self._get_cached_token_metadata(jti)
            if not cached_metadata or cached_metadata.get("active") != "true":
                logger.warning("token_not_active_in_cache", jti=jti)
                return None

            # Cryptographic verification with audience check
            payload = jwt.decode(
                token,
                self.public_pem,
                algorithms=["RS256"],
                audience="tobogganing",
            )

            # Issuer validation
            if payload.get("iss") != self.issuer_url:
                logger.warning(
                    "token_issuer_mismatch",
                    expected=self.issuer_url,
                    got=payload.get("iss"),
                )
                return None

            # Normalise scope: space-delimited string → list
            raw_scope = payload.get("scope", "")
            payload["scope"] = [s for s in raw_scope.split(" ") if s]

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("token_expired", jti=jti)
            if jti:
                await self._invalidate_token(jti)
            return None
        except jwt.InvalidTokenError as exc:
            logger.warning("token_invalid", error=str(exc))
            return None
    
    async def refresh_token(self, refresh_token_str: str) -> Optional[Dict[str, str]]:
        """
        Issue a new access+refresh token pair from a valid refresh token.

        Identity context (tenant, teams, roles, scopes) is reconstructed
        from the Redis metadata stored during the original generate_token() call.
        The consumed refresh token is invalidated to prevent replay.
        """
        # validate_token handles iss/aud/signature/cache checks
        jti: Optional[str] = None
        try:
            unverified = jwt.decode(
                refresh_token_str, options={"verify_signature": False}
            )
            jti = unverified.get("jti")
        except jwt.InvalidTokenError:
            return None

        if not jti:
            return None

        cached = await self._get_cached_token_metadata(jti)
        if not cached or cached.get("active") != "true" or cached.get("type") != "refresh":
            logger.warning("refresh_token_invalid_or_expired", jti=jti)
            return None

        # Verify signature fully before trusting cached identity data
        try:
            jwt.decode(
                refresh_token_str,
                self.public_pem,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
        except jwt.InvalidTokenError as exc:
            logger.warning("refresh_token_signature_invalid", error=str(exc))
            return None

        # Reconstruct identity from Redis metadata
        subject = cached.get("subject", "")
        tenant = cached.get("tenant", "")
        teams = [t for t in cached.get("teams", "").split(",") if t]
        roles = [r for r in cached.get("roles", "").split(",") if r]
        scopes = [s for s in cached.get("scopes", "").split(" ") if s]

        if not subject:
            logger.warning("refresh_token_missing_subject", jti=jti)
            return None

        # Invalidate consumed refresh token (one-time use)
        await self._invalidate_token(jti)

        logger.info(
            "refresh_token_consumed",
            jti=jti,
            subject=subject,
            tenant=tenant,
        )

        return await self.generate_token(
            subject=subject,
            tenant=tenant,
            teams=teams,
            roles=roles,
            scopes=scopes,
        )
    
    async def revoke_token(self, jti: str) -> bool:
        """Revoke a specific token by JTI."""
        return await self._invalidate_token(jti)

    async def revoke_all_tokens(self, subject: str) -> int:
        """
        Revoke all cached tokens for a subject by scanning Redis metadata keys.
        Matches on the 'subject' field stored in token metadata hashes.
        """
        pattern = "token_metadata:*"
        cursor = 0
        revoked = 0

        while True:
            cursor, keys = await self.redis_client.scan(
                cursor=cursor, match=pattern, count=500
            )
            if keys:
                pipe = self.redis_client.pipeline()
                for key in keys:
                    pipe.hgetall(key)
                results = await pipe.execute()

                revoke_pipe = self.redis_client.pipeline()
                for key, meta in zip(keys, results):
                    if meta.get("subject") == subject and meta.get("active") == "true":
                        revoke_pipe.hset(key, "active", "false")
                        revoked += 1
                if revoked:
                    await revoke_pipe.execute()

            if cursor == 0:
                break

        logger.info("tokens_revoked_for_subject", subject=subject, count=revoked)
        return revoked

    async def get_public_key(self) -> str:
        """Return PEM-encoded public key for downstream token validation."""
        return self.public_pem.decode("utf-8")

    def get_jwks(self) -> dict:
        """
        Return the JWKS (JSON Web Key Set) containing the RSA public key.

        The returned structure is suitable for serving at /.well-known/jwks.json
        and allows consumers to verify RS256-signed JWTs without out-of-band
        key distribution.
        """
        pub_numbers = self.public_key.public_numbers()

        def _b64url(n: int) -> str:
            """Encode an RSA integer as Base64url (no padding)."""
            byte_length = (n.bit_length() + 7) // 8
            raw = n.to_bytes(byte_length, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self.kid,
                    "n": _b64url(pub_numbers.n),
                    "e": _b64url(pub_numbers.e),
                }
            ]
        }
    
    async def _cache_token_metadata(self, jti: str, metadata: Dict[str, Any]):
        """
        Persist token metadata in Redis.

        Access token metadata stores: subject, tenant, teams, roles, scopes,
        expires_at, active.
        Refresh token metadata additionally stores: type="refresh".
        """
        key = f"token_metadata:{jti}"
        await self.redis_client.hset(key, mapping=metadata)

        ttl = (
            int(self.refresh_expiry.total_seconds())
            if metadata.get("type") == "refresh"
            else int(self.token_expiry.total_seconds())
        )
        await self.redis_client.expire(key, ttl)

    async def _get_cached_token_metadata(self, jti: str) -> Optional[Dict[str, Any]]:
        """Retrieve token metadata hash from Redis."""
        key = f"token_metadata:{jti}"
        return await self.redis_client.hgetall(key)

    async def _invalidate_token(self, jti: str) -> bool:
        """Mark a token as inactive in Redis (soft-revoke)."""
        key = f"token_metadata:{jti}"
        result = await self.redis_client.hset(key, "active", "false")
        logger.debug("token_invalidated", jti=jti)
        return bool(result)
    
    async def cleanup_expired_tokens(self):
        """
        Background task: remove token_metadata keys that Redis has already expired
        (TTL == -2 means the key no longer exists).
        Intended to be called periodically (e.g. every hour) to compact memory.
        """
        pattern = "token_metadata:*"
        cursor = 0
        total_removed = 0

        while True:
            cursor, keys = await self.redis_client.scan(
                cursor=cursor, match=pattern, count=1000
            )

            if keys:
                pipe = self.redis_client.pipeline()
                for key in keys:
                    pipe.ttl(key)
                ttls = await pipe.execute()

                expired_keys = [k for k, ttl in zip(keys, ttls) if ttl == -2]
                if expired_keys:
                    await self.redis_client.delete(*expired_keys)
                    total_removed += len(expired_keys)

            if cursor == 0:
                break

        logger.info("token_cleanup_completed", removed=total_removed)

    async def close(self):
        """Close Redis connections gracefully."""
        if self.redis_client:
            await self.redis_client.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()