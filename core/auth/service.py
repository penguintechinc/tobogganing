"""Unified authentication service with bcrypt, RS256 JWT, and TOTP MFA."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import bcrypt
import pyotp
from typing import TYPE_CHECKING

from core.auth.jwt import decode_token, encode_access_token
from core.config import Config
from core.crypto.keys import KeyProvider
from core.crypto.secrets import decrypt_secret, encrypt_secret

if TYPE_CHECKING:
    from penguin_dal import DB


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

    def authenticate(
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
            user = self.db.users.select(email=email).first()
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
                    mfa_tok = hashlib.sha256(
                        (user.id + str(uuid.uuid4())).encode()
                    ).hexdigest()
                    return AuthResult(mfa_required=True, mfa_token=mfa_tok)

                # Decrypt and verify TOTP token
                try:
                    decrypted_secret = decrypt_secret(user.mfa_secret)
                except ValueError as e:
                    return AuthResult(success=False, error=f"MFA verification error: {e}")

                totp = pyotp.TOTP(decrypted_secret)
                if not totp.verify(mfa_token):
                    return AuthResult(success=False, error="Invalid MFA token")

            # Generate tokens
            access_token = self._generate_access_token(user)
            refresh_token = self._generate_and_store_refresh_token(user.id)

            return AuthResult(
                success=True,
                access_token=access_token,
                refresh_token=refresh_token,
            )
        except Exception as e:
            return AuthResult(success=False, error=f"Authentication failed: {str(e)}")

    def refresh_access_token(self, refresh_token: str) -> AuthResult:
        """
        Refresh an access token using a refresh token.

        Args:
            refresh_token: The refresh token string.

        Returns:
            AuthResult with new access token or error.
        """
        try:
            # Query refresh token
            rt_record = self.db.refresh_tokens.select(token=refresh_token).first()
            if not rt_record or rt_record.revoked:
                return AuthResult(success=False, error="Invalid or revoked refresh token")

            # Verify expiration
            import time

            if rt_record.expires_at < int(time.time()):
                return AuthResult(success=False, error="Refresh token expired")

            # Get user
            user = self.db.users.select(id=rt_record.user_id).first()
            if not user or not user.is_active:
                return AuthResult(success=False, error="User not found or inactive")

            # Generate new access token
            access_token = self._generate_access_token(user)

            return AuthResult(success=True, access_token=access_token)
        except Exception as e:
            return AuthResult(success=False, error=f"Token refresh failed: {str(e)}")

    def revoke_tokens(self, user_id: str) -> bool:
        """
        Revoke all refresh tokens for a user.

        Args:
            user_id: The user ID.

        Returns:
            True if revocation successful, False otherwise.
        """
        try:
            # Mark all refresh tokens as revoked
            self.db.refresh_tokens.update(
                user_id=user_id,
                revoked=True,
            )
            return True
        except Exception:
            return False

    def setup_mfa(self, user_id: str) -> tuple[str, list[str]]:
        """
        Set up TOTP MFA for a user.

        Returns the secret and backup codes.

        Args:
            user_id: The user ID.

        Returns:
            Tuple of (secret, backup_codes).
        """
        user = self.db.users.select(id=user_id).first()
        if not user:
            raise ValueError("User not found")

        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Generate backup codes (in a real implementation, these would be hashed)
        backup_codes = [hashlib.sha256(f"{secret}:{i}".encode()).hexdigest()[:8] for i in range(10)]

        return secret, backup_codes

    def verify_and_enable_mfa(
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
            # Verify the token
            totp = pyotp.TOTP(secret)
            if not totp.verify(mfa_token):
                return False

            # Update user record
            user = self.db.users.select(id=user_id).first()
            if not user:
                return False

            # Encrypt secret before storing
            encrypted_secret = encrypt_secret(secret)

            self.db.users.update(
                id=user_id,
                mfa_enabled=True,
                mfa_secret=encrypted_secret,
            )
            return True
        except Exception:
            return False

    def disable_mfa(self, user_id: str) -> bool:
        """
        Disable MFA for a user.

        Args:
            user_id: The user ID.

        Returns:
            True if MFA disabled successfully, False otherwise.
        """
        try:
            self.db.users.update(
                id=user_id,
                mfa_enabled=False,
                mfa_secret=None,
            )
            return True
        except Exception:
            return False

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """
        Retrieve a user by ID.

        Args:
            user_id: The user ID.

        Returns:
            User record as dict, or None if not found.
        """
        try:
            user = self.db.users.select(id=user_id).first()
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
        except Exception:
            return None

    def _generate_access_token(self, user: Any) -> str:
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

        return encode_access_token(
            claims,
            self.key_provider,
            ttl_hours=self.config.jwt_expiration_hours,
        )

    def _generate_and_store_refresh_token(self, user_id: str) -> str:
        """
        Generate and store a refresh token.

        Args:
            user_id: The user ID.

        Returns:
            The refresh token string.
        """
        import time

        refresh_token = hashlib.sha256(
            (user_id + os.urandom(32).hex()).encode()
        ).hexdigest()

        # Store in database (expires in 30 days)
        expires_at = int(time.time()) + (30 * 24 * 3600)

        self.db.refresh_tokens.insert(
            user_id=user_id,
            token=refresh_token,
            expires_at=expires_at,
            revoked=False,
        )

        return refresh_token
