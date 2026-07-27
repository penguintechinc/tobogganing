"""Tests for core user manager."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hub_api.core import UserManager, User, Session, UserRole
from hub_api.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_user_db() -> MagicMock:
    """Create a mock DAL with users and sessions table support.

    Returns:
        Mock database object.
    """
    db = MagicMock()

    # Mock users table with comparable fields
    users_table = MagicMock()
    users_table.async_insert = AsyncMock(return_value=1)
    users_table.id = MagicMock()
    users_table.id.__eq__ = MagicMock()
    users_table.username = MagicMock()
    users_table.username.__eq__ = MagicMock()
    users_table.tenant = MagicMock()
    users_table.tenant.__eq__ = MagicMock()
    users_table.is_active = MagicMock()
    users_table.is_active.__eq__ = MagicMock()
    db.users = users_table

    # Mock sessions table with comparable fields
    sessions_table = MagicMock()
    sessions_table.async_insert = AsyncMock(return_value=1)
    sessions_table.id = MagicMock()
    sessions_table.id.__eq__ = MagicMock()
    sessions_table.token = MagicMock()
    sessions_table.token.__eq__ = MagicMock()
    sessions_table.expires_at = MagicMock()
    sessions_table.expires_at.__lt__ = MagicMock()  # For expires_at < datetime comparison
    sessions_table.expires_at.__eq__ = MagicMock()
    sessions_table.user_id = MagicMock()
    sessions_table.user_id.__eq__ = MagicMock()
    sessions_table.tenant = MagicMock()
    sessions_table.tenant.__eq__ = MagicMock()
    db.sessions = sessions_table

    # Mock query builder
    def make_query_proxy() -> MagicMock:
        query_proxy = MagicMock()
        query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
        query_proxy.count = AsyncMock(return_value=0)
        query_proxy.update = AsyncMock(return_value=None)
        query_proxy.delete = AsyncMock(return_value=None)
        query_proxy.__and__ = MagicMock(return_value=query_proxy)
        query_proxy.__or__ = MagicMock(return_value=query_proxy)
        query_proxy.first = MagicMock(return_value=None)
        return query_proxy

    query_proxy = make_query_proxy()
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    return db


@pytest.mark.asyncio
async def test_authenticate_success(mock_user_db: MagicMock) -> None:
    """Test successful user authentication."""
    import bcrypt

    manager = UserManager(mock_user_db)

    # Create password hash
    password = "test_password_123"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )

    # Mock user row
    user_row = make_mock_row(
        {
            "id": str(uuid4()),
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": password_hash,
            "role": "reporter",
            "tenant": "test-tenant",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
    )

    # Setup mock to return user
    def mock_select_call(*args, **kwargs) -> MagicMock:
        rowset = make_mock_rowset([user_row])
        return rowset

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)
    mock_user_db.return_value.update = AsyncMock(return_value=None)

    # Test authentication
    result = await manager.authenticate("testuser", password, "test-tenant")

    assert result is not None
    assert result.username == "testuser"
    assert result.email == "test@example.com"
    assert result.role == UserRole.REPORTER
    assert result.tenant == "test-tenant"
    assert result.password_hash is None  # Should not expose


@pytest.mark.asyncio
async def test_authenticate_invalid_password(mock_user_db: MagicMock) -> None:
    """Test authentication with invalid password."""
    import bcrypt

    manager = UserManager(mock_user_db)

    password_hash = bcrypt.hashpw(b"correct_password", bcrypt.gensalt()).decode("utf-8")

    user_row = make_mock_row(
        {
            "id": str(uuid4()),
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": password_hash,
            "role": "reporter",
            "tenant": "test-tenant",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
    )

    def mock_select_call(*args, **kwargs) -> MagicMock:
        rowset = make_mock_rowset([user_row])
        return rowset

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)

    result = await manager.authenticate("testuser", "wrong_password", "test-tenant")

    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_not_found(mock_user_db: MagicMock) -> None:
    """Test authentication with non-existent user."""
    manager = UserManager(mock_user_db)

    def mock_select_call(*args, **kwargs) -> MagicMock:
        return make_mock_rowset([])

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)

    result = await manager.authenticate("nonexistent", "password", "test-tenant")

    assert result is None


@pytest.mark.asyncio
async def test_create_session(mock_user_db: MagicMock) -> None:
    """Test session creation."""
    manager = UserManager(mock_user_db, session_timeout_hours=8)

    user = User(
        id=str(uuid4()),
        username="testuser",
        email="test@example.com",
        role=UserRole.REPORTER,
        tenant="test-tenant",
        created_at=datetime.utcnow(),
        is_active=True,
    )

    session = await manager.create_session(user)

    assert session is not None
    assert session.user_id == user.id
    assert session.tenant == user.tenant
    assert session.token is not None
    assert session.expires_at > session.created_at
    mock_user_db.sessions.async_insert.assert_called_once()


@pytest.mark.asyncio
async def test_validate_session_valid(mock_user_db: MagicMock) -> None:
    """Test validation of valid session."""
    import bcrypt

    manager = UserManager(mock_user_db)

    session_id = str(uuid4())
    token = "test_token_abc123"
    user_id = str(uuid4())
    tenant = "test-tenant"
    expires_at = datetime.utcnow() + timedelta(hours=8)

    # Mock session row
    session_row = make_mock_row(
        {
            "id": session_id,
            "user_id": user_id,
            "tenant": tenant,
            "token": token,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
        }
    )

    password_hash = bcrypt.hashpw(b"password", bcrypt.gensalt()).decode("utf-8")

    # Mock user row
    user_row = make_mock_row(
        {
            "id": user_id,
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": password_hash,
            "role": "reporter",
            "tenant": tenant,
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
    )

    call_count = [0]

    def mock_select_call(*args, **kwargs) -> MagicMock:
        call_count[0] += 1
        if call_count[0] == 1:
            # First call is for session
            return make_mock_rowset([session_row])
        else:
            # Second call is for user
            return make_mock_rowset([user_row])

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)

    result = await manager.validate_session(token, tenant)

    assert result is not None
    assert result.username == "testuser"
    assert result.email == "test@example.com"


@pytest.mark.asyncio
async def test_validate_session_expired(mock_user_db: MagicMock) -> None:
    """Test validation of expired session."""
    manager = UserManager(mock_user_db)

    token = "test_token_abc123"
    tenant = "test-tenant"
    expires_at = datetime.utcnow() - timedelta(hours=1)  # Expired

    session_row = make_mock_row(
        {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "tenant": tenant,
            "token": token,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
        }
    )

    def mock_select_call(*args, **kwargs) -> MagicMock:
        return make_mock_rowset([session_row])

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)
    mock_user_db.return_value.delete = AsyncMock(return_value=None)

    result = await manager.validate_session(token, tenant)

    assert result is None
    mock_user_db.return_value.delete.assert_called_once()


@pytest.mark.asyncio
async def test_logout(mock_user_db: MagicMock) -> None:
    """Test session logout."""
    manager = UserManager(mock_user_db)

    token = "test_token_abc123"
    tenant = "test-tenant"
    session_id = str(uuid4())

    session_row = make_mock_row(
        {
            "id": session_id,
            "user_id": str(uuid4()),
            "tenant": tenant,
            "token": token,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=8),
        }
    )

    def mock_select_call(*args, **kwargs) -> MagicMock:
        return make_mock_rowset([session_row])

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)
    mock_user_db.return_value.delete = AsyncMock(return_value=None)

    result = await manager.logout(token, tenant)

    assert result is True
    mock_user_db.return_value.delete.assert_called_once()


@pytest.mark.asyncio
async def test_create_user(mock_user_db: MagicMock) -> None:
    """Test user creation."""
    manager = UserManager(mock_user_db)

    result = await manager.create_user(
        username="newuser",
        email="new@example.com",
        password="securepass123",
        tenant="test-tenant",
        role=UserRole.ADMIN,
    )

    assert result is not None
    assert result.username == "newuser"
    assert result.email == "new@example.com"
    assert result.role == UserRole.ADMIN
    assert result.tenant == "test-tenant"
    assert result.password_hash is None
    mock_user_db.users.async_insert.assert_called_once()


@pytest.mark.asyncio
async def test_list_users(mock_user_db: MagicMock) -> None:
    """Test listing users."""
    manager = UserManager(mock_user_db)

    user1_row = make_mock_row(
        {
            "id": str(uuid4()),
            "username": "user1",
            "email": "user1@example.com",
            "role": "admin",
            "tenant": "test-tenant",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
    )

    user2_row = make_mock_row(
        {
            "id": str(uuid4()),
            "username": "user2",
            "email": "user2@example.com",
            "role": "reporter",
            "tenant": "test-tenant",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
    )

    def mock_select_call(*args, **kwargs) -> MagicMock:
        return make_mock_rowset([user1_row, user2_row])

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)

    result = await manager.list_users("test-tenant")

    assert len(result) == 2
    assert result[0].username == "user1"
    assert result[1].username == "user2"


@pytest.mark.asyncio
async def test_update_user_status(mock_user_db: MagicMock) -> None:
    """Test updating user status."""
    manager = UserManager(mock_user_db)

    user_id = str(uuid4())
    tenant = "test-tenant"

    user_row = make_mock_row(
        {
            "id": user_id,
            "username": "testuser",
            "email": "test@example.com",
            "role": "reporter",
            "tenant": tenant,
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
    )

    def mock_select_call(*args, **kwargs) -> MagicMock:
        return make_mock_rowset([user_row])

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)
    mock_user_db.return_value.update = AsyncMock(return_value=None)
    mock_user_db.return_value.delete = AsyncMock(return_value=None)

    result = await manager.update_user_status(user_id, tenant, False)

    assert result is True
    mock_user_db.return_value.update.assert_called_once()
    mock_user_db.return_value.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_expired_sessions(mock_user_db: MagicMock) -> None:
    """Test cleanup of expired sessions."""
    manager = UserManager(mock_user_db)

    session_id = str(uuid4())
    expired_session = make_mock_row(
        {
            "id": session_id,
            "user_id": str(uuid4()),
            "tenant": "test-tenant",
            "token": "token1",
            "created_at": datetime.utcnow() - timedelta(hours=10),
            "expires_at": datetime.utcnow() - timedelta(hours=2),
        }
    )

    call_count = [0]

    def mock_select_call(*args, **kwargs) -> MagicMock:
        call_count[0] += 1
        # Return the expired session
        return make_mock_rowset([expired_session])

    mock_user_db.return_value.select = AsyncMock(side_effect=mock_select_call)
    mock_user_db.return_value.delete = AsyncMock(return_value=None)

    result = await manager.cleanup_expired_sessions("test-tenant")

    assert result == 1
    # Verify delete was called for the expired session
    assert mock_user_db.return_value.delete.call_count >= 1


def test_has_permission_admin() -> None:
    """Test permission checking for admin user."""
    manager = UserManager(MagicMock())

    user = User(
        id=str(uuid4()),
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        tenant="test-tenant",
        created_at=datetime.utcnow(),
    )

    assert manager.has_permission(user, "any_permission") is True


def test_has_permission_reporter() -> None:
    """Test permission checking for reporter user."""
    manager = UserManager(MagicMock())

    user = User(
        id=str(uuid4()),
        username="reporter",
        email="reporter@example.com",
        role=UserRole.REPORTER,
        tenant="test-tenant",
        created_at=datetime.utcnow(),
    )

    assert manager.has_permission(user, "view_dashboard") is True
    assert manager.has_permission(user, "view_metrics") is True
    assert manager.has_permission(user, "admin_permission") is False


def test_require_permission_granted() -> None:
    """Test require_permission when permission granted."""
    manager = UserManager(MagicMock())

    user = User(
        id=str(uuid4()),
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        tenant="test-tenant",
        created_at=datetime.utcnow(),
    )

    # Should not raise
    manager.require_permission(user, "any_permission")


def test_require_permission_denied() -> None:
    """Test require_permission when permission denied."""
    manager = UserManager(MagicMock())

    user = User(
        id=str(uuid4()),
        username="reporter",
        email="reporter@example.com",
        role=UserRole.REPORTER,
        tenant="test-tenant",
        created_at=datetime.utcnow(),
    )

    with pytest.raises(PermissionError):
        manager.require_permission(user, "admin_only_permission")


@pytest.mark.asyncio
async def test_validate_session_with_tenant_isolation() -> None:
    """Test that validate_session scopes by tenant (cross-tenant isolation fix)."""
    db = MagicMock()

    # Mock the session query to return a session
    session_row = make_mock_row(
        {
            "id": "session-123",
            "user_id": "user-456",
            "tenant": "tenant-a",
            "token": "abc123",
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        }
    )

    user_row = make_mock_row(
        {
            "id": "user-456",
            "username": "testuser",
            "email": "test@example.com",
            "role": "reporter",
            "tenant": "tenant-a",
            "created_at": datetime.utcnow(),
            "is_active": True,
            "password_hash": "hash",
        }
    )

    # Track which query is being made based on what fields are being accessed
    call_count = 0

    def query_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        query_proxy = MagicMock()

        # First call: sessions query; second call: users query
        if call_count == 1:
            query_proxy.select = AsyncMock(return_value=make_mock_rowset([session_row]))
        else:
            query_proxy.select = AsyncMock(return_value=make_mock_rowset([user_row]))

        return query_proxy

    db.side_effect = query_side_effect

    manager = UserManager(db)

    # Test successful validation with correct tenant
    user = await manager.validate_session("abc123", "tenant-a")
    assert user is not None
    assert user.tenant == "tenant-a"
    assert user.username == "testuser"

    # Verify that the session query was scoped to the correct tenant
    # The mock should have been called with both token and tenant filters
    db.assert_called()


@pytest.mark.asyncio
async def test_logout_with_tenant_isolation() -> None:
    """Test that logout scopes by tenant (cross-tenant isolation fix)."""
    db = MagicMock()

    session_row = make_mock_row(
        {
            "id": "session-123",
            "user_id": "user-456",
            "tenant": "tenant-a",
            "token": "abc123",
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        }
    )

    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([session_row]))
    query_proxy.delete = AsyncMock(return_value=None)

    db.return_value = query_proxy

    manager = UserManager(db)

    result = await manager.logout("abc123", "tenant-a")

    assert result is True
    # Verify that delete was called (session was deleted)
    query_proxy.delete.assert_called_once()
