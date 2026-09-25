"""Additional coverage for hub_api.core.auth: init validation and error paths.

test_core_user_manager.py already covers the happy paths; this file fills in
the exception handlers and not-found branches across UserManager.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from hub_api.core.auth import User, UserManager, UserRole
from hub_api.tests.conftest import make_mock_row, make_mock_rowset


@pytest.fixture
def mock_user_db() -> MagicMock:
    """Create a mock DAL with users and sessions table support.

    Returns:
        Mock database object.
    """
    db = MagicMock()

    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=make_mock_rowset([]))
    query_proxy.update = AsyncMock(return_value=None)
    query_proxy.delete = AsyncMock(return_value=None)
    query_proxy.__and__ = MagicMock(return_value=query_proxy)
    query_proxy.__or__ = MagicMock(return_value=query_proxy)
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    def make_comparable_field() -> MagicMock:
        field_mock = MagicMock()
        field_mock.__eq__ = MagicMock(return_value=query_proxy)
        field_mock.__lt__ = MagicMock(return_value=query_proxy)
        return field_mock

    users_table = MagicMock()
    users_table.async_insert = AsyncMock(return_value=1)
    users_table.id = make_comparable_field()
    users_table.tenant = make_comparable_field()
    db.users = users_table

    sessions_table = MagicMock()
    sessions_table.async_insert = AsyncMock(return_value=1)
    sessions_table.id = make_comparable_field()
    sessions_table.tenant = make_comparable_field()
    sessions_table.token = make_comparable_field()
    sessions_table.user_id = make_comparable_field()
    sessions_table.expires_at = make_comparable_field()
    db.sessions = sessions_table

    return db


def test_init_raises_on_none_db() -> None:
    """UserManager() with db=None raises ValueError."""
    with pytest.raises(ValueError, match="Database instance cannot be None"):
        UserManager(None)


@pytest.mark.asyncio
async def test_authenticate_swallows_exception(mock_user_db: MagicMock) -> None:
    """authenticate() returns None when the DB query raises."""
    mock_user_db.return_value.select = AsyncMock(side_effect=RuntimeError("db down"))

    manager = UserManager(mock_user_db)
    result = await manager.authenticate("alice", "pw", "tenant-a")

    assert result is None


@pytest.mark.asyncio
async def test_create_session_raises_on_db_error(mock_user_db: MagicMock) -> None:
    """create_session() re-raises when async_insert fails."""
    mock_user_db.sessions.async_insert = AsyncMock(side_effect=RuntimeError("insert failed"))
    user = User(
        id="u1",
        username="alice",
        email="alice@example.com",
        role=UserRole.REPORTER,
        tenant="tenant-a",
        created_at=datetime.utcnow(),
    )

    manager = UserManager(mock_user_db)
    with pytest.raises(RuntimeError, match="insert failed"):
        await manager.create_session(user)


@pytest.mark.asyncio
async def test_validate_session_user_not_found(mock_user_db: MagicMock) -> None:
    """validate_session() returns None when the session's user no longer exists."""
    session_row = make_mock_row(
        {
            "id": "s1",
            "user_id": "u1",
            "tenant": "tenant-a",
            "token": "tok",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        }
    )

    call_count = {"n": 0}

    async def select_side_effect(*args: object, **kwargs: object) -> MagicMock:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return make_mock_rowset([session_row])
        return make_mock_rowset([])  # user lookup returns empty

    mock_user_db.return_value.select = AsyncMock(side_effect=select_side_effect)

    manager = UserManager(mock_user_db)
    result = await manager.validate_session("tok", "tenant-a")

    assert result is None


@pytest.mark.asyncio
async def test_validate_session_swallows_exception(mock_user_db: MagicMock) -> None:
    """validate_session() returns None when the DB query raises."""
    mock_user_db.return_value.select = AsyncMock(side_effect=RuntimeError("db down"))

    manager = UserManager(mock_user_db)
    result = await manager.validate_session("tok", "tenant-a")

    assert result is None


@pytest.mark.asyncio
async def test_logout_session_not_found(mock_user_db: MagicMock) -> None:
    """logout() returns False when the session token is not found."""
    mock_user_db.return_value.select = AsyncMock(return_value=make_mock_rowset([]))

    manager = UserManager(mock_user_db)
    result = await manager.logout("nonexistent-token", "tenant-a")

    assert result is False


@pytest.mark.asyncio
async def test_logout_swallows_exception(mock_user_db: MagicMock) -> None:
    """logout() returns False when the DB query raises."""
    mock_user_db.return_value.select = AsyncMock(side_effect=RuntimeError("db down"))

    manager = UserManager(mock_user_db)
    result = await manager.logout("tok", "tenant-a")

    assert result is False


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_swallows_exception(mock_user_db: MagicMock) -> None:
    """cleanup_expired_sessions() returns 0 when the DB query raises."""
    mock_user_db.return_value.select = AsyncMock(side_effect=RuntimeError("db down"))

    manager = UserManager(mock_user_db)
    result = await manager.cleanup_expired_sessions("tenant-a")

    assert result == 0


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_deletes_each(mock_user_db: MagicMock) -> None:
    """cleanup_expired_sessions() deletes each expired session row and counts them."""
    expired_rows = [
        make_mock_row({"id": "s1"}),
        make_mock_row({"id": "s2"}),
    ]
    mock_user_db.return_value.select = AsyncMock(return_value=make_mock_rowset(expired_rows))

    manager = UserManager(mock_user_db)
    result = await manager.cleanup_expired_sessions("tenant-a")

    assert result == 2


@pytest.mark.asyncio
async def test_create_user_duplicate_raises_value_error(mock_user_db: MagicMock) -> None:
    """create_user() converts a 'unique' DB error into ValueError."""
    mock_user_db.users.async_insert = AsyncMock(
        side_effect=Exception("UNIQUE constraint failed: users.email")
    )

    manager = UserManager(mock_user_db)
    with pytest.raises(ValueError, match="Username or email already exists"):
        await manager.create_user("alice", "alice@example.com", "pw", "tenant-a")


@pytest.mark.asyncio
async def test_create_user_generic_error_reraises(mock_user_db: MagicMock) -> None:
    """create_user() re-raises non-uniqueness DB errors as-is."""
    mock_user_db.users.async_insert = AsyncMock(side_effect=RuntimeError("connection reset"))

    manager = UserManager(mock_user_db)
    with pytest.raises(RuntimeError, match="connection reset"):
        await manager.create_user("alice", "alice@example.com", "pw", "tenant-a")


@pytest.mark.asyncio
async def test_list_users_swallows_exception(mock_user_db: MagicMock) -> None:
    """list_users() returns an empty list when the DB query raises."""
    mock_user_db.return_value.select = AsyncMock(side_effect=RuntimeError("db down"))

    manager = UserManager(mock_user_db)
    result = await manager.list_users("tenant-a")

    assert result == []


@pytest.mark.asyncio
async def test_update_user_status_not_found(mock_user_db: MagicMock) -> None:
    """update_user_status() returns False when the target user isn't found."""
    mock_user_db.return_value.select = AsyncMock(return_value=make_mock_rowset([]))

    manager = UserManager(mock_user_db)
    result = await manager.update_user_status("nonexistent", "tenant-a", False)

    assert result is False


@pytest.mark.asyncio
async def test_update_user_status_swallows_exception(mock_user_db: MagicMock) -> None:
    """update_user_status() returns False when the DB query raises."""
    mock_user_db.return_value.select = AsyncMock(side_effect=RuntimeError("db down"))

    manager = UserManager(mock_user_db)
    result = await manager.update_user_status("u1", "tenant-a", True)

    assert result is False


@pytest.mark.asyncio
async def test_update_user_status_disabling_invalidates_sessions(
    mock_user_db: MagicMock,
) -> None:
    """update_user_status(is_active=False) also deletes the user's sessions."""
    user_row = make_mock_row({"id": "u1"})
    mock_user_db.return_value.select = AsyncMock(return_value=make_mock_rowset([user_row]))

    manager = UserManager(mock_user_db)
    result = await manager.update_user_status("u1", "tenant-a", False)

    assert result is True
    mock_user_db.return_value.delete.assert_called()
