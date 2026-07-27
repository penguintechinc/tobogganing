"""User and session manager for authentication."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

import bcrypt
import structlog

logger = structlog.get_logger()


class UserRole(Enum):
    """User role enumeration."""

    ADMIN = "admin"
    REPORTER = "reporter"


@dataclass(slots=True)
class User:
    """User data structure."""

    id: str
    username: str
    email: str
    role: UserRole
    tenant: str
    created_at: datetime
    is_active: bool = True
    password_hash: str | None = None  # Not included in API responses


@dataclass(slots=True)
class Session:
    """Session data structure."""

    id: str
    user_id: str
    tenant: str
    token: str
    created_at: datetime
    expires_at: datetime


class UserManager:
    """Manages user authentication and authorization via penguin-dal."""

    def __init__(self, db: Any, session_timeout_hours: int = 8) -> None:
        """Initialize user manager with a DAL instance.

        Args:
            db: penguin-dal DAL instance for database operations.
            session_timeout_hours: Session expiration time in hours.

        Raises:
            ValueError: If db is None.
        """
        if db is None:
            raise ValueError("Database instance cannot be None")
        self.db = db
        self.session_timeout_hours = session_timeout_hours

    async def authenticate(self, username: str, password: str, tenant: str) -> User | None:
        """Authenticate user with username/password.

        Args:
            username: Username to authenticate.
            password: Plain text password to verify.
            tenant: Tenant ID for scoping.

        Returns:
            User object if authentication successful, None otherwise.
        """
        try:
            rowset = await self.db(
                (self.db.users.username == username)
                & (self.db.users.tenant == tenant)
                & (self.db.users.is_active == True)  # noqa: E712
            ).select()

            user_row = rowset.first()
            if not user_row:
                logger.warning(
                    "authentication_failed",
                    username=username,
                    tenant=tenant,
                    reason="user_not_found",
                )
                return None

            # Verify password
            if not bcrypt.checkpw(
                password.encode("utf-8"),
                user_row.password_hash.encode("utf-8"),
            ):
                logger.warning(
                    "authentication_failed",
                    username=username,
                    tenant=tenant,
                    reason="invalid_password",
                )
                return None

            # Note: last_login column doesn't exist in schema; skip update

            user = User(
                id=user_row.id,
                username=user_row.username,
                email=user_row.email,
                role=UserRole(user_row.role or "reporter"),
                tenant=user_row.tenant,
                created_at=user_row.created_at,
                is_active=bool(user_row.is_active),
                password_hash=None,
            )

            logger.info(
                "user_authenticated",
                user_id=user.id,
                username=username,
                tenant=tenant,
                role=user.role.value,
            )
            return user

        except Exception as e:
            logger.error(
                "authentication_error",
                username=username,
                tenant=tenant,
                error=str(e),
            )
            return None

    async def create_session(
        self, user: User, user_agent: str | None = None, ip_address: str | None = None
    ) -> Session:
        """Create new session for authenticated user.

        Args:
            user: User object to create session for.
            user_agent: Optional user agent string.
            ip_address: Optional IP address.

        Returns:
            Session object.

        Raises:
            Exception: If session creation fails.
        """
        session_id = str(uuid4())
        token = secrets.token_urlsafe(32)
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(hours=self.session_timeout_hours)

        try:
            await self.db.sessions.async_insert(
                id=session_id,
                user_id=user.id,
                tenant=user.tenant,
                token=token,
                created_at=created_at,
                expires_at=expires_at,
            )

            session = Session(
                id=session_id,
                user_id=user.id,
                tenant=user.tenant,
                token=token,
                created_at=created_at,
                expires_at=expires_at,
            )

            logger.info(
                "session_created",
                session_id=session_id[:8],
                user_id=user.id,
                tenant=user.tenant,
                expires_at=expires_at.isoformat(),
            )
            return session

        except Exception as e:
            logger.error(
                "session_creation_error",
                user_id=user.id,
                tenant=user.tenant,
                error=str(e),
            )
            raise

    async def validate_session(self, token: str, tenant: str) -> User | None:
        """Validate session and return user if valid.

        Args:
            token: Session token to validate.
            tenant: Tenant ID for scoping (cross-tenant isolation).

        Returns:
            User object if session is valid, None otherwise.
        """
        try:
            rowset = await self.db(
                (self.db.sessions.token == token)
                & (self.db.sessions.tenant == tenant)
            ).select()
            session_row = rowset.first()

            if not session_row:
                return None

            # Check if session is expired
            if session_row.expires_at < datetime.utcnow():
                await self.db(self.db.sessions.id == session_row.id).delete()
                logger.debug(
                    "session_expired",
                    session_id=session_row.id[:8],
                    token=token[:8],
                )
                return None

            # Fetch user for this session
            user_rowset = await self.db(
                (self.db.users.id == session_row.user_id)
                & (self.db.users.tenant == session_row.tenant)
                & (self.db.users.is_active == True)  # noqa: E712
            ).select()

            user_row = user_rowset.first()
            if not user_row:
                return None

            user = User(
                id=user_row.id,
                username=user_row.username,
                email=user_row.email,
                role=UserRole(user_row.role or "reporter"),
                tenant=user_row.tenant,
                created_at=user_row.created_at,
                is_active=bool(user_row.is_active),
                password_hash=None,
            )

            return user

        except Exception as e:
            logger.error(
                "session_validation_error",
                token=token[:8],
                error=str(e),
            )
            return None

    async def logout(self, token: str, tenant: str) -> bool:
        """Invalidate session (logout).

        Args:
            token: Session token to invalidate.
            tenant: Tenant ID for scoping (cross-tenant isolation).

        Returns:
            True if logout successful, False otherwise.
        """
        try:
            rowset = await self.db(
                (self.db.sessions.token == token)
                & (self.db.sessions.tenant == tenant)
            ).select()
            session_row = rowset.first()

            if not session_row:
                logger.debug("logout_failed", token=token[:8], reason="session_not_found")
                return False

            await self.db(self.db.sessions.id == session_row.id).delete()

            logger.info(
                "session_invalidated",
                session_id=session_row.id[:8],
                user_id=session_row.user_id,
                tenant=session_row.tenant,
            )
            return True

        except Exception as e:
            logger.error(
                "logout_error",
                token=token[:8],
                error=str(e),
            )
            return False

    async def cleanup_expired_sessions(self, tenant: str) -> int:
        """Remove expired sessions from database.

        Args:
            tenant: Tenant ID for scoping.

        Returns:
            Count of deleted sessions.
        """
        try:
            rowset = await self.db(
                (self.db.sessions.expires_at < datetime.utcnow())
                & (self.db.sessions.tenant == tenant)
            ).select()

            deleted_count = 0
            for session_row in rowset:
                await self.db(self.db.sessions.id == session_row.id).delete()
                deleted_count += 1

            if deleted_count > 0:
                logger.info(
                    "expired_sessions_cleaned",
                    tenant=tenant,
                    count=deleted_count,
                )

            return deleted_count

        except Exception as e:
            logger.error(
                "session_cleanup_error",
                tenant=tenant,
                error=str(e),
            )
            return 0

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        tenant: str,
        role: UserRole = UserRole.REPORTER,
    ) -> User:
        """Create new user.

        Args:
            username: Unique username.
            email: Unique email address.
            password: Plain text password to hash.
            tenant: Tenant ID for scoping.
            role: User role (default: REPORTER).

        Returns:
            User object.

        Raises:
            ValueError: If username or email already exists.
            Exception: If creation fails.
        """
        try:
            user_id = str(uuid4())
            password_hash = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")

            await self.db.users.async_insert(
                id=user_id,
                username=username,
                email=email,
                password_hash=password_hash,
                role=role.value,
                tenant=tenant,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                mfa_enabled=False,
            )

            user = User(
                id=user_id,
                username=username,
                email=email,
                role=role,
                tenant=tenant,
                created_at=datetime.utcnow(),
                is_active=True,
            )

            logger.info(
                "user_created",
                user_id=user_id,
                username=username,
                email=email,
                tenant=tenant,
                role=role.value,
            )
            return user

        except Exception as e:
            if "unique" in str(e).lower():
                logger.error(
                    "user_creation_failed",
                    username=username,
                    email=email,
                    tenant=tenant,
                    reason="duplicate_username_or_email",
                )
                raise ValueError("Username or email already exists")
            logger.error(
                "user_creation_error",
                username=username,
                email=email,
                tenant=tenant,
                error=str(e),
            )
            raise

    async def list_users(self, tenant: str) -> list[User]:
        """List all users in a tenant.

        Args:
            tenant: Tenant ID for scoping.

        Returns:
            List of User objects.
        """
        try:
            rowset = await self.db(self.db.users.tenant == tenant).select(
                orderby=self.db.users.created_at
            )

            users: list[User] = []
            for row in rowset:
                user = User(
                    id=row.id,
                    username=row.username,
                    email=row.email,
                    role=UserRole(row.role or "reporter"),
                    tenant=row.tenant,
                    created_at=row.created_at,
                    is_active=bool(row.is_active),
                )
                users.append(user)

            return users

        except Exception as e:
            logger.error(
                "list_users_error",
                tenant=tenant,
                error=str(e),
            )
            return []

    async def update_user_status(self, user_id: str, tenant: str, is_active: bool) -> bool:
        """Enable/disable user.

        Args:
            user_id: User ID to update.
            tenant: Tenant ID for scoping.
            is_active: Whether user should be active.

        Returns:
            True if update successful, False otherwise.
        """
        try:
            rowset = await self.db(
                (self.db.users.id == user_id)
                & (self.db.users.tenant == tenant)
            ).select()

            if not rowset.first():
                logger.warning(
                    "update_user_status_failed",
                    user_id=user_id,
                    tenant=tenant,
                    reason="user_not_found",
                )
                return False

            await self.db(
                (self.db.users.id == user_id)
                & (self.db.users.tenant == tenant)
            ).update(is_active=is_active)

            # Invalidate all sessions if disabling user
            if not is_active:
                await self.db(
                    (self.db.sessions.user_id == user_id)
                    & (self.db.sessions.tenant == tenant)
                ).delete()

            logger.info(
                "user_status_updated",
                user_id=user_id,
                tenant=tenant,
                is_active=is_active,
            )
            return True

        except Exception as e:
            logger.error(
                "update_user_status_error",
                user_id=user_id,
                tenant=tenant,
                error=str(e),
            )
            return False

    def has_permission(self, user: User, permission: str) -> bool:
        """Check if user has specific permission.

        Args:
            user: User object to check.
            permission: Permission string to check.

        Returns:
            True if user has permission, False otherwise.
        """
        if user.role == UserRole.ADMIN:
            return True

        if user.role == UserRole.REPORTER:
            # Reporter has read-only permissions
            reporter_permissions = {
                "view_dashboard",
                "view_metrics",
                "view_clients",
                "view_clusters",
                "view_status",
                "view_rules",
            }
            return permission in reporter_permissions

        return False

    def require_permission(self, user: User, permission: str) -> None:
        """Require specific permission, raise error if denied.

        Args:
            user: User object to check.
            permission: Permission string to require.

        Raises:
            PermissionError: If user lacks permission.
        """
        if not self.has_permission(user, permission):
            logger.warning(
                "permission_denied",
                user_id=user.id,
                username=user.username,
                permission=permission,
            )
            raise PermissionError(f"User {user.username} lacks permission: {permission}")
