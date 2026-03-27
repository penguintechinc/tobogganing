"""
Tests for auth/user_manager.py — user CRUD, sessions, roles, permissions.
All UserManager methods are async.
"""
import pytest
from unittest.mock import MagicMock, patch

from auth.user_manager import UserManager, UserRole, User, Session


# ---------------------------------------------------------------------------
# Fixtures (user_manager from conftest uses tmp_path SQLite)
# ---------------------------------------------------------------------------

class TestUserManagerInit:
    @pytest.mark.asyncio
    async def test_creates_default_admin(self, user_manager):
        """Default admin user should exist after init."""
        users = await user_manager.list_users()
        admin_users = [u for u in users if u.role == UserRole.ADMIN]
        assert len(admin_users) >= 1

    def test_db_tables_created(self, user_manager):
        """SQLite tables should have been created."""
        import sqlite3
        conn = sqlite3.connect(user_manager.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cur.fetchall()}
        conn.close()
        assert "users" in tables
        assert "sessions" in tables


# ---------------------------------------------------------------------------
# User creation
# ---------------------------------------------------------------------------

class TestCreateUser:
    @pytest.mark.asyncio
    async def test_create_user_returns_user_object(self, user_manager):
        user = await user_manager.create_user(
            "alice", "alice@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        assert isinstance(user, User)
        assert user.username == "alice"

    @pytest.mark.asyncio
    async def test_created_user_has_correct_role(self, user_manager):
        user = await user_manager.create_user(
            "bob", "bob@example.com", "pass@W0rd!", UserRole.MAINTAINER
        )
        assert user.role == UserRole.MAINTAINER

    @pytest.mark.asyncio
    async def test_password_is_hashed(self, user_manager):
        await user_manager.create_user(
            "carol", "carol@example.com", "plaintext", UserRole.VIEWER
        )
        import sqlite3
        conn = sqlite3.connect(user_manager.db_path)
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("carol",)
        ).fetchone()
        conn.close()
        assert row is not None
        # The stored value should not be the plaintext password
        assert row[0] != "plaintext"

    @pytest.mark.asyncio
    async def test_duplicate_username_raises(self, user_manager):
        await user_manager.create_user(
            "dave", "dave@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        with pytest.raises(Exception):
            await user_manager.create_user(
                "dave", "dave2@example.com", "other@pass!", UserRole.VIEWER
            )

    @pytest.mark.asyncio
    async def test_user_active_by_default(self, user_manager):
        user = await user_manager.create_user(
            "eve", "eve@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        assert user.is_active is True


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_correct_credentials_return_user(self, user_manager):
        await user_manager.create_user(
            "frank", "frank@example.com", "mySecret1!", UserRole.VIEWER
        )
        result = await user_manager.authenticate("frank", "mySecret1!")
        assert result is not None
        assert result.username == "frank"

    @pytest.mark.asyncio
    async def test_wrong_password_returns_none(self, user_manager):
        await user_manager.create_user(
            "grace", "grace@example.com", "rightPass1!", UserRole.VIEWER
        )
        result = await user_manager.authenticate("grace", "wrongPass!")
        assert result is None

    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_none(self, user_manager):
        result = await user_manager.authenticate("nobody", "pass@W0rd!")
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_user_returns_none(self, user_manager):
        user = await user_manager.create_user(
            "henry", "henry@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        await user_manager.update_user_status(user.id, is_active=False)
        result = await user_manager.authenticate("henry", "pass@W0rd!")
        assert result is None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class TestSessions:
    @pytest.mark.asyncio
    async def test_create_session_returns_session_object(self, user_manager):
        await user_manager.create_user(
            "ivan", "ivan@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        user = await user_manager.authenticate("ivan", "pass@W0rd!")
        session = await user_manager.create_session(user, "127.0.0.1", "TestAgent/1.0")
        assert isinstance(session, Session)
        assert session.session_id is not None
        assert len(session.session_id) > 0

    @pytest.mark.asyncio
    async def test_validate_session_returns_user(self, user_manager):
        await user_manager.create_user(
            "julia", "julia@example.com", "pass@W0rd!", UserRole.MAINTAINER
        )
        user = await user_manager.authenticate("julia", "pass@W0rd!")
        session = await user_manager.create_session(user, "127.0.0.1", "TestAgent/1.0")
        validated = await user_manager.validate_session(session.session_id)
        assert validated is not None
        assert validated.username == "julia"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self, user_manager):
        result = await user_manager.validate_session("bogus-session-token-xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_logout_invalidates_session(self, user_manager):
        await user_manager.create_user(
            "kevin", "kevin@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        user = await user_manager.authenticate("kevin", "pass@W0rd!")
        session = await user_manager.create_session(user, "127.0.0.1", "TestAgent/1.0")
        await user_manager.logout(session.session_id)
        result = await user_manager.validate_session(session.session_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_does_not_raise(self, user_manager):
        try:
            await user_manager.cleanup_expired_sessions()
        except Exception as exc:
            pytest.fail(f"cleanup_expired_sessions raised: {exc}")


# ---------------------------------------------------------------------------
# User listing and management
# ---------------------------------------------------------------------------

class TestUserManagement:
    @pytest.mark.asyncio
    async def test_list_users_returns_list(self, user_manager):
        result = await user_manager.list_users()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_newly_created_user_in_list(self, user_manager):
        await user_manager.create_user(
            "lena", "lena@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        users = await user_manager.list_users()
        usernames = [u.username for u in users]
        assert "lena" in usernames

    @pytest.mark.asyncio
    async def test_update_user_status_deactivates(self, user_manager):
        user = await user_manager.create_user(
            "mike", "mike@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        await user_manager.update_user_status(user.id, is_active=False)
        result = await user_manager.authenticate("mike", "pass@W0rd!")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_user_status_reactivates(self, user_manager):
        user = await user_manager.create_user(
            "nina", "nina@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        await user_manager.update_user_status(user.id, is_active=False)
        await user_manager.update_user_status(user.id, is_active=True)
        result = await user_manager.authenticate("nina", "pass@W0rd!")
        assert result is not None


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class TestPermissions:
    @pytest.mark.asyncio
    async def test_admin_has_all_permissions(self, user_manager):
        await user_manager.create_user(
            "oscar", "oscar@example.com", "pass@W0rd!", UserRole.ADMIN
        )
        user = await user_manager.authenticate("oscar", "pass@W0rd!")
        # Admin has all perms
        assert user_manager.has_permission(user, "view_dashboard") is True
        assert user_manager.has_permission(user, "manage_clients") is True
        assert user_manager.has_permission(user, "any_permission") is True

    @pytest.mark.asyncio
    async def test_viewer_has_read_only(self, user_manager):
        await user_manager.create_user(
            "pete", "pete@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        user = await user_manager.authenticate("pete", "pass@W0rd!")
        assert user_manager.has_permission(user, "view_dashboard") is True
        assert user_manager.has_permission(user, "manage_clients") is False

    @pytest.mark.asyncio
    async def test_maintainer_has_write_not_admin(self, user_manager):
        await user_manager.create_user(
            "quinn", "quinn@example.com", "pass@W0rd!", UserRole.MAINTAINER
        )
        user = await user_manager.authenticate("quinn", "pass@W0rd!")
        assert user_manager.has_permission(user, "manage_clients") is True
        assert user_manager.has_permission(user, "manage_users") is False

    @pytest.mark.asyncio
    async def test_require_permission_raises_for_insufficient(self, user_manager):
        await user_manager.create_user(
            "rose", "rose@example.com", "pass@W0rd!", UserRole.VIEWER
        )
        user = await user_manager.authenticate("rose", "pass@W0rd!")
        with pytest.raises(PermissionError):
            user_manager.require_permission(user, "manage_clients")

    @pytest.mark.asyncio
    async def test_require_permission_passes_for_sufficient(self, user_manager):
        await user_manager.create_user(
            "sam", "sam@example.com", "pass@W0rd!", UserRole.ADMIN
        )
        user = await user_manager.authenticate("sam", "pass@W0rd!")
        # Should NOT raise
        user_manager.require_permission(user, "manage_clients")


# ---------------------------------------------------------------------------
# User dataclass
# ---------------------------------------------------------------------------

class TestUserDataclass:
    def test_user_role_enum_values(self):
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.VIEWER.value == "viewer"
        assert UserRole.MAINTAINER.value == "maintainer"

    def test_user_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(User)

    def test_session_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(Session)

    def test_session_has_session_id_field(self):
        import dataclasses
        fields = {f.name for f in dataclasses.fields(Session)}
        assert "session_id" in fields
        assert "user_id" in fields
        assert "expires_at" in fields
