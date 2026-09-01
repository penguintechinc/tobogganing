"""Unified authentication service with bcrypt, RS256 JWT, and TOTP MFA."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import bcrypt
import pyotp
import structlog

from hub_api.auth.jwt import encode_access_token
from hub_api.config import Config
from hub_api.crypto.keys import KeyProvider
from hub_api.crypto.secrets import decrypt_secret, encrypt_secret

logger = structlog.get_logger()


# Role to scope mapping
ROLE_SCOPES: dict[str, list[str]] = {
    "admin": ["*:read", "*:write", "*:admin"],
    "maintainer": ["*:read", "*:write"],
    "viewer": ["*:read"],
}


@dataclass(slots=True)
class AuthResult:
    """Result of an authentication attempt."""

    success: bool = False
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    mfa_required: bool = False
    mfa_token: Optional[str] = None
    error: Optional[str] = None


class AuthService:
    """
    Unified authentication service.

    Handles user authentication, JWT token generation, refresh tokens, and TOTP MFA.
    """

    def __init__(
        self,
        db: Any,
        config: Config,
        key_provider: KeyProvider,
    ) -> None:
        """
        Initialize the authentication service.

        Args:
            db: penguin-dal DB instance.
            config: Application configuration.
            key_provider: RS256 key provider for JWT signing.
        """
        self.db = db
        self.config = config
        self.key_provider = key_provider

    async def authenticate(
        self,
        email: str,
        password: str,
        mfa_token: Optional[str] = None,
    ) -> AuthResult:
        """
        Authenticate a user by email and password.

        If MFA is enabled and no valid mfa_token provided, returns mfa_required=True.

        Args:
            email: User email address.
            password: User password (plaintext).
            mfa_token: Optional TOTP token for MFA verification.

        Returns:
            AuthResult with access/refresh tokens or error details.
        """
        try:
            # Query user by email
            rowset = await self.db(self.db.users.email == email).select()
            user = rowset.first()
            if not user:
                return AuthResult(success=False, error="Invalid email or password")

            # Verify password
            if not bcrypt.checkpw(
                password.encode("utf-8"),
                user.password_hash.encode("utf-8"),
            ):
                return AuthResult(success=False, error="Invalid email or password")

            # Check if user is active
            if not user.is_active:
                return AuthResult(success=False, error="User account is inactive")

            # Handle MFA
            if user.mfa_enabled:
                if not mfa_token:
                    # Generate a temporary MFA token for the client to use
                    # (in a real implementation, this would be a short-lived token)
                    mfa_tok = hashlib.sha256((user.id + str(uuid4())).encode()).hexdigest()
                    return AuthResult(mfa_required=True, mfa_token=mfa_tok)

                # Decrypt and verify TOTP token
                try:
                    decrypted_secret = decrypt_secret(user.mfa_secret)
                except ValueError as e:
                    return AuthResult(success=False, error=f"MFA verification error: {e}")

                totp = pyotp.TOTP(decrypted_secret)
                if not totp.verify(mfa_token, valid_window=1):
                    return AuthResult(success=False, error="Invalid MFA token")

            # Generate tokens
            access_token = await self._generate_access_token(user)
            refresh_token = await self._generate_and_store_refresh_token(user.id)

            return AuthResult(
                success=True,
                access_token=access_token,
                refresh_token=refresh_token,
            )
        except Exception as e:
            logger.error("authentication_error", email=email, error=str(e))
            return AuthResult(success=False, error=f"Authentication failed: {str(e)}")

    async def refresh_access_token(self, refresh_token: str) -> AuthResult:
        """
        Refresh an access token using a refresh token, rotating it on every use.

        The presented refresh token is single-use: on success it is marked
        consumed (``revoked_at``) and a brand-new refresh token is minted and
        persisted in its place, mirroring the machine-JWT rotation semantics
        in ``auth/refresh.py``. If a caller presents a refresh token that was
        already consumed once (replay), this is treated as a compromise
        signal — ALL of the user's refresh tokens are revoked, forcing a full
        re-authentication (security-review finding HIGH-A).

        Args:
            refresh_token: The refresh token string.

        Returns:
            AuthResult with a new access token AND a new refresh token, or error.
        """
        try:
            # Query refresh token
            rowset = await self.db(self.db.refresh_tokens.token == refresh_token).select()
            rt_record = rowset.first()
            if not rt_record:
                return AuthResult(success=False, error="Invalid or revoked refresh token")

            # Replay detection: this token was already rotated once. Treat as
            # a compromise indicator and revoke the entire session family.
            if getattr(rt_record, "revoked_at", None) is not None:
                logger.warning(
                    "refresh_token_replay_detected",
                    user_id=rt_record.user_id,
                )
                await self.revoke_tokens(rt_record.user_id)
                return AuthResult(success=False, error="Invalid or revoked refresh token")

            # Verify expiration (handle both aware and naive datetimes)
            expires_at = rt_record.expires_at
            if isinstance(expires_at, str):
                # Parse from ISO format if stored as string
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            elif expires_at.tzinfo is None:
                # Assume UTC if naive
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at < datetime.now(timezone.utc):
                return AuthResult(success=False, error="Refresh token expired")

            # Get user
            user_rowset = await self.db(self.db.users.id == rt_record.user_id).select()
            user = user_rowset.first()
            if not user or not user.is_active:
                return AuthResult(success=False, error="User not found or inactive")

            # Single-use rotation: mark the presented token consumed, then
            # mint and persist a brand-new refresh token.
            await self.db(self.db.refresh_tokens.token == refresh_token).update(
                revoked_at=datetime.now(timezone.utc)
            )
            new_refresh_token = await self._generate_and_store_refresh_token(user.id)

            # Generate new access token
            access_token = await self._generate_access_token(user)

            return AuthResult(
                success=True,
                access_token=access_token,
                refresh_token=new_refresh_token,
            )
        except Exception as e:
            logger.error("token_refresh_error", error=str(e))
            return AuthResult(success=False, error=f"Token refresh failed: {str(e)}")

    async def revoke_tokens(self, user_id: str) -> bool:
        """
        Revoke all refresh tokens for a user.

        Args:
            user_id: The user ID.

        Returns:
            True if revocation successful, False otherwise.
        """
        try:
            # Delete all refresh tokens for the user
            await self.db(self.db.refresh_tokens.user_id == user_id).delete()
            return True
        except Exception as e:
            logger.error("token_revocation_error", user_id=user_id, error=str(e))
            return False

    async def setup_mfa(self, user_id: str) -> tuple[str, list[str]]:
        """
        Set up TOTP MFA for a user.

        Returns the secret and backup codes.

        Args:
            user_id: The user ID.

        Returns:
            Tuple of (secret, backup_codes).

        Raises:
            ValueError: If user not found.
        """
        rowset = await self.db(self.db.users.id == user_id).select()
        user = rowset.first()
        if not user:
            raise ValueError("User not found")

        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Generate backup codes (in a real implementation, these would be hashed)
        backup_codes = [hashlib.sha256(f"{secret}:{i}".encode()).hexdigest()[:8] for i in range(10)]

        return secret, backup_codes

    async def verify_and_enable_mfa(
        self,
        user_id: str,
        secret: str,
        mfa_token: str,
    ) -> bool:
        """
        Verify an MFA token and enable MFA for the user.

        Args:
            user_id: The user ID.
            secret: The TOTP secret.
            mfa_token: The TOTP token to verify.

        Returns:
            True if MFA enabled successfully, False otherwise.
        """
        try:
            # Verify the token with valid_window=1 to handle 30s window boundaries
            totp = pyotp.TOTP(secret)
            if not totp.verify(mfa_token, valid_window=1):
                return False

            # Update user record
            rowset = await self.db(self.db.users.id == user_id).select()
            user = rowset.first()
            if not user:
                return False

            # Encrypt secret before storing
            encrypted_secret = encrypt_secret(secret)

            await self.db(self.db.users.id == user_id).update(
                mfa_enabled=True,
                mfa_secret=encrypted_secret,
            )
            return True
        except Exception as e:
            logger.error("mfa_enable_error", user_id=user_id, error=str(e))
            return False

    async def disable_mfa(self, user_id: str) -> bool:
        """
        Disable MFA for a user.

        Args:
            user_id: The user ID.

        Returns:
            True if MFA disabled successfully, False otherwise.
        """
        try:
            await self.db(self.db.users.id == user_id).update(
                mfa_enabled=False,
                mfa_secret=None,
            )
            return True
        except Exception as e:
            logger.error("mfa_disable_error", user_id=user_id, error=str(e))
            return False

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """
        Retrieve a user by ID.

        Args:
            user_id: The user ID.

        Returns:
            User record as dict, or None if not found.
        """
        try:
            rowset = await self.db(self.db.users.id == user_id).select()
            user = rowset.first()
            if not user:
                return None
            return {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "is_active": user.is_active,
                "mfa_enabled": user.mfa_enabled,
                "tenant": user.tenant,
                "role": user.role,
                "teams": getattr(user, "teams", []),
            }
        except Exception as e:
            logger.error("get_user_error", user_id=user_id, error=str(e))
            return None

    async def _generate_access_token(self, user: Any) -> str:
        """
        Generate an access token for a user.

        Args:
            user: User record from database.

        Returns:
            Encoded JWT token.
        """
        # Derive scope from role
        role = getattr(user, "role", "viewer")
        scope = " ".join(ROLE_SCOPES.get(role, ROLE_SCOPES["viewer"]))

        teams = getattr(user, "teams", [])
        if isinstance(teams, str):
            teams = teams.split(",") if teams else []

        claims = {
            "sub": user.id,
            "iss": self.config.product_name,
            "aud": self.config.product_name,
            "tenant": user.tenant,
            "scope": scope,
            "teams": teams,
            "roles": [role],
        }

        return await encode_access_token(
            claims,
            self.key_provider,
            ttl_hours=self.config.jwt_expiration_hours,
        )

    async def _generate_and_store_refresh_token(self, user_id: str) -> str:
        """
        Generate and store a refresh token.

        Args:
            user_id: The user ID.

        Returns:
            The refresh token string.
        """
        from datetime import timedelta

        refresh_token = hashlib.sha256((user_id + os.urandom(32).hex()).encode()).hexdigest()

        # Store in database (expires in 30 days)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=30)

        await self.db.refresh_tokens.async_insert(
            id=str(uuid4()),
            user_id=user_id,
            token=refresh_token,
            expires_at=expires_at,
            created_at=now,
        )

        return refresh_token
