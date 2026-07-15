"""Tests for session-based authentication middleware."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart, jsonify, g

from core.auth.middleware import (
    clear_session_cookie,
    require_admin,
    require_permission,
    require_role,
    require_session_user,
    set_session_cookie,
)


@pytest.fixture
def app_with_dal() -> Quart:
    """Create a test app with mocked DAL."""
    app = Quart(__name__)
    app.config["TESTING"] = True

    # Mock DAL
    mock_dal = MagicMock()
    app.config["DAL"] = mock_dal

    return app


@pytest.fixture
def mock_user_row() -> MagicMock:
    """Create a mock user row."""
    user = MagicMock()
    user.id = "user-123"
    user.username = "testuser"
    user.email = "test@example.com"
    user.role = "reporter"
    user.tenant = "tenant-1"
    user.created_at = datetime.utcnow()
    user.is_active = True
    return user


@pytest.fixture
def mock_admin_row() -> MagicMock:
    """Create a mock admin user row."""
    user = MagicMock()
    user.id = "admin-123"
    user.username = "admin"
    user.email = "admin@example.com"
    user.role = "admin"
    user.tenant = "tenant-1"
    user.created_at = datetime.utcnow()
    user.is_active = True
    return user


@pytest.fixture
def mock_session_row() -> MagicMock:
    """Create a mock session row."""
    session = MagicMock()
    session.id = "session-123"
    session.user_id = "user-123"
    session.tenant = "tenant-1"
    session.token = "test-session-token"
    session.created_at = datetime.utcnow()
    session.expires_at = datetime.utcnow() + timedelta(hours=8)
    return session


@pytest.fixture
def mock_expired_session() -> MagicMock:
    """Create a mock expired session row."""
    session = MagicMock()
    session.id = "expired-session-123"
    session.user_id = "user-123"
    session.tenant = "tenant-1"
    session.token = "expired-token"
    session.created_at = datetime.utcnow() - timedelta(hours=10)
    session.expires_at = datetime.utcnow() - timedelta(hours=2)  # Expired
    return session


class TestRequireSessionUser:
    """Test the require_session_user decorator."""

    @pytest.mark.asyncio
    async def test_require_session_user_missing_cookie(self, app_with_dal: Quart) -> None:
        """Test that require_session_user returns 401 when cookie is missing."""

        @require_session_user
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                response = await handler()
                assert response[1] == 401

    @pytest.mark.asyncio
    async def test_require_session_user_invalid_cookie(self, app_with_dal: Quart) -> None:
        """Test that require_session_user returns 401 when cookie is invalid."""
        mock_dal = app_with_dal.config["DAL"]

        # Mock DAL to return no session
        mock_rowset = MagicMock()
        mock_rowset.first.return_value = None
        mock_dal.return_value.select.return_value = mock_rowset

        @require_session_user
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context(
                "/test",
                method="GET",
                headers={"Cookie": "sasewaddle_session=invalid-token"},
            ):
                response = await handler()
                assert response[1] == 401

    @pytest.mark.asyncio
    async def test_require_session_user_expired_session(
        self,
        app_with_dal: Quart,
        mock_expired_session: MagicMock,
    ) -> None:
        """Test that require_session_user returns 401 for expired session."""
        mock_dal = app_with_dal.config["DAL"]

        # Mock DAL to return expired session
        mock_rowset = MagicMock()
        mock_rowset.first.return_value = mock_expired_session
        mock_dal.return_value.select.return_value = mock_rowset

        # Mock delete for cleanup
        mock_dal.return_value.delete.return_value = None

        @require_session_user
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context(
                "/test",
                method="GET",
                headers={"Cookie": "sasewaddle_session=expired-token"},
            ):
                response = await handler()
                assert response[1] == 401

    @pytest.mark.asyncio
    async def test_require_session_user_valid_session(
        self,
        app_with_dal: Quart,
        mock_session_row: MagicMock,
        mock_user_row: MagicMock,
    ) -> None:
        """Test that require_session_user allows access with valid session."""
        mock_dal = app_with_dal.config["DAL"]

        # First call: get session row
        session_rowset = MagicMock()
        session_rowset.first.return_value = mock_session_row

        # Second call: get user row
        user_rowset = MagicMock()
        user_rowset.first.return_value = mock_user_row

        # Set up mock to return query proxies with async select
        query_proxy_1 = MagicMock()
        query_proxy_1.select = AsyncMock(return_value=session_rowset)

        query_proxy_2 = MagicMock()
        query_proxy_2.select = AsyncMock(return_value=user_rowset)

        # Mock dal(...) to return different query proxies
        mock_dal.side_effect = [query_proxy_1, query_proxy_2]

        @require_session_user
        async def handler() -> Any:
            # Check that g.user and g.tenant were set
            assert hasattr(g, "user")
            assert hasattr(g, "tenant")
            assert g.user["username"] == "testuser"
            assert g.tenant == "tenant-1"
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context(
                "/test",
                method="GET",
                headers={"Cookie": "sasewaddle_session=test-session-token"},
            ):
                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_session_user_tenant_isolation(
        self,
        app_with_dal: Quart,
        mock_session_row: MagicMock,
    ) -> None:
        """Test that require_session_user scopes queries to session tenant."""
        mock_dal = app_with_dal.config["DAL"]

        # Session exists but user not found in same tenant
        session_rowset = MagicMock()
        session_rowset.first.return_value = mock_session_row

        user_rowset = MagicMock()
        user_rowset.first.return_value = None  # User not found in tenant

        mock_dal.return_value.select.side_effect = [session_rowset, user_rowset]

        @require_session_user
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context(
                "/test",
                method="GET",
                headers={"Cookie": "sasewaddle_session=test-session-token"},
            ):
                response = await handler()
                # Should fail because user not found in that tenant
                assert response[1] == 401

    @pytest.mark.asyncio
    async def test_require_session_user_inactive_user(
        self,
        app_with_dal: Quart,
        mock_session_row: MagicMock,
        mock_user_row: MagicMock,
    ) -> None:
        """Test that require_session_user rejects inactive users."""
        mock_dal = app_with_dal.config["DAL"]
        mock_user_row.is_active = False  # Mark user as inactive

        session_rowset = MagicMock()
        session_rowset.first.return_value = mock_session_row

        user_rowset = MagicMock()
        user_rowset.first.return_value = None  # Query filters out inactive users

        mock_dal.return_value.select.side_effect = [session_rowset, user_rowset]

        @require_session_user
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context(
                "/test",
                method="GET",
                headers={"Cookie": "sasewaddle_session=test-session-token"},
            ):
                response = await handler()
                assert response[1] == 401


class TestRequireRole:
    """Test the require_role decorator."""

    @pytest.mark.asyncio
    async def test_require_role_no_session(self, app_with_dal: Quart) -> None:
        """Test that require_role returns 401 when session is not set."""

        @require_role("admin")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                response = await handler()
                assert response[1] == 401

    @pytest.mark.asyncio
    async def test_require_role_insufficient_role(self, app_with_dal: Quart) -> None:
        """Test that require_role returns 403 for insufficient role."""

        @require_role("admin")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                # Set reporter user in g
                g.user = {
                    "id": "user-123",
                    "username": "testuser",
                    "role": "reporter",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_role_correct_role(self, app_with_dal: Quart) -> None:
        """Test that require_role allows correct role."""

        @require_role("admin")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                g.user = {
                    "id": "admin-123",
                    "username": "admin",
                    "role": "admin",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_role_admin_bypasses(self, app_with_dal: Quart) -> None:
        """Test that admin role bypasses other role requirements."""

        @require_role("reporter")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                # Admin user accessing reporter-only endpoint
                g.user = {
                    "id": "admin-123",
                    "username": "admin",
                    "role": "admin",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 200


class TestRequirePermission:
    """Test the require_permission decorator."""

    @pytest.mark.asyncio
    async def test_require_permission_no_session(self, app_with_dal: Quart) -> None:
        """Test that require_permission returns 401 when session is not set."""

        @require_permission("view_dashboard")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                response = await handler()
                assert response[1] == 401

    @pytest.mark.asyncio
    async def test_require_permission_admin_has_all(self, app_with_dal: Quart) -> None:
        """Test that admin has all permissions."""

        @require_permission("edit_rules")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                g.user = {
                    "id": "admin-123",
                    "username": "admin",
                    "role": "admin",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_permission_reporter_read_only(
        self, app_with_dal: Quart
    ) -> None:
        """Test that reporter has only read permissions."""

        @require_permission("view_dashboard")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                g.user = {
                    "id": "user-123",
                    "username": "testuser",
                    "role": "reporter",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_permission_reporter_denied_write(
        self, app_with_dal: Quart
    ) -> None:
        """Test that reporter is denied write permissions."""

        @require_permission("edit_rules")
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                g.user = {
                    "id": "user-123",
                    "username": "testuser",
                    "role": "reporter",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 403


class TestRequireAdmin:
    """Test the require_admin decorator."""

    @pytest.mark.asyncio
    async def test_require_admin_session_admin(self, app_with_dal: Quart) -> None:
        """Test that require_admin allows session-authenticated admin."""

        @require_admin
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                g.user = {
                    "id": "admin-123",
                    "username": "admin",
                    "role": "admin",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 200

    @pytest.mark.asyncio
    async def test_require_admin_session_non_admin(self, app_with_dal: Quart) -> None:
        """Test that require_admin denies non-admin session."""

        @require_admin
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                g.user = {
                    "id": "user-123",
                    "username": "testuser",
                    "role": "reporter",
                    "tenant": "tenant-1",
                }

                response = await handler()
                assert response[1] == 403

    @pytest.mark.asyncio
    async def test_require_admin_no_auth(self, app_with_dal: Quart) -> None:
        """Test that require_admin denies requests with no auth."""

        @require_admin
        async def handler() -> Any:
            return jsonify({"success": True}), 200

        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                response = await handler()
                assert response[1] == 403


class TestSessionCookie:
    """Test session cookie helpers."""

    @pytest.mark.asyncio
    async def test_set_session_cookie_http(self, app_with_dal: Quart) -> None:
        """Test that set_session_cookie sets correct attributes (non-HTTPS)."""
        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                # Create a mock response
                resp = MagicMock()
                resp.set_cookie = MagicMock()

                set_session_cookie(resp, "test-token")

                # Verify set_cookie was called with correct arguments
                resp.set_cookie.assert_called_once()
                call_args = resp.set_cookie.call_args
                assert call_args[0][0] == "sasewaddle_session"
                assert call_args[0][1] == "test-token"

    @pytest.mark.asyncio
    async def test_clear_session_cookie(self, app_with_dal: Quart) -> None:
        """Test that clear_session_cookie clears the cookie."""
        async with app_with_dal.app_context():
            async with app_with_dal.test_request_context("/test", method="GET"):
                # Create a mock response
                resp = MagicMock()
                resp.set_cookie = MagicMock()

                clear_session_cookie(resp)

                # Verify set_cookie was called to clear the cookie
                resp.set_cookie.assert_called_once()
                call_args = resp.set_cookie.call_args
                assert call_args[0][0] == "sasewaddle_session"
                assert call_args[0][1] == ""
                assert call_args[1]["max_age"] == 0
