"""Shared pytest fixtures for core tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from quart import Quart


def make_mock_row(data: dict) -> MagicMock:
    """Create a mock row object that behaves like a penguin-dal row.

    Args:
        data: Dictionary of row data.

    Returns:
        Mock row object with attributes and as_dict method.
    """
    row = MagicMock()
    for key, value in data.items():
        setattr(row, key, value)
    row.as_dict.return_value = data
    return row


def make_mock_rowset(rows: list) -> MagicMock:
    """Create a mock rowset that supports .first() and iteration.

    Args:
        rows: List of mock row objects.

    Returns:
        Mock rowset with iteration support.
    """
    rowset = MagicMock()
    rowset.first.return_value = rows[0] if rows else None
    rowset.__iter__ = MagicMock(side_effect=lambda: iter(rows))
    rowset.__len__ = MagicMock(return_value=len(rows))
    return rowset


@pytest.fixture
def mock_db() -> MagicMock:
    """Provide a mock AsyncDB for testing without a real database.

    Returns:
        Mock database object simulating penguin-dal interface.
    """
    db = MagicMock()

    # Default: empty rowset for db(query).select()
    empty_rowset = make_mock_rowset([])
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=empty_rowset)
    query_proxy.count = AsyncMock(return_value=0)
    query_proxy.update = AsyncMock(return_value=None)
    query_proxy.delete = AsyncMock(return_value=None)
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    # Mock field attributes that support penguin-dal comparison operators
    def make_comparable_field(field_name: str) -> MagicMock:
        """Create a mock field that supports comparison operators."""
        field_mock = MagicMock()
        field_mock.__eq__ = MagicMock(return_value=query_proxy)
        field_mock.__ne__ = MagicMock(return_value=query_proxy)
        field_mock.__lt__ = MagicMock(return_value=query_proxy)
        field_mock.__le__ = MagicMock(return_value=query_proxy)
        field_mock.__gt__ = MagicMock(return_value=query_proxy)
        field_mock.__ge__ = MagicMock(return_value=query_proxy)
        return field_mock

    # Make query_proxy support & and | operators for combined queries
    query_proxy.__and__ = MagicMock(return_value=query_proxy)
    query_proxy.__or__ = MagicMock(return_value=query_proxy)

    # Default table insert returns id=1
    for table_name in [
        "users",
        "refresh_tokens",
        "password_reset_tokens",
    ]:
        table_mock = MagicMock()
        table_mock.async_insert = AsyncMock(return_value=1)
        table_mock.id = make_comparable_field("id")
        setattr(db, table_name, table_mock)

    return db


@pytest.fixture
def mock_config() -> MagicMock:
    """Test configuration object.

    Returns:
        Mock Config object with test values.
    """
    from core.config import Config

    config = Config(
        db_type="sqlite",
        db_name=":memory:",
        db_host="localhost",
        db_port=5432,
        db_user="test",
        db_pass="test",
        db_pool_size=5,
        jwt_expiration_hours=24,
        cors_origins="http://localhost:3000",
        log_level="WARNING",
    )
    return config  # type: ignore[return-value]


@pytest.fixture
def app(mock_db: MagicMock) -> Quart:
    """Create a minimal Quart test application with mocked services.

    Args:
        mock_db: Mocked database fixture.

    Returns:
        Configured Quart test application.
    """
    from unittest.mock import patch

    from core.app import create_app

    with patch("core.db.init_dal"), patch(
        "core.db.get_db", return_value=mock_db
    ):
        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.db = mock_db  # type: ignore[attr-defined]

    return test_app


@pytest.fixture
def client(app: Quart):
    """Quart async test client.

    Args:
        app: Quart test application.

    Returns:
        Async test client.
    """
    return app.test_client()
