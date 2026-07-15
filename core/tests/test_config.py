from __future__ import annotations

import pytest
from core.config import Config, build_db_uri


def test_build_db_uri_sqlite() -> None:
    """Test SQLite URI construction."""
    cfg = Config(db_type="sqlite", db_name=":memory:")
    uri = build_db_uri(cfg)
    assert uri.startswith("sqlite+aiosqlite:")


def test_build_db_uri_postgres() -> None:
    """Test PostgreSQL URI construction."""
    cfg = Config(
        db_type="postgresql",
        db_host="h",
        db_name="d",
        db_user="u",
        db_pass="p"
    )
    uri = build_db_uri(cfg)
    assert uri.startswith("postgresql+asyncpg://u:p@h")


def test_build_db_uri_mysql() -> None:
    """Test MySQL URI construction."""
    cfg = Config(
        db_type="mysql",
        db_host="localhost",
        db_port=3306,
        db_name="testdb",
        db_user="root",
        db_pass="password"
    )
    uri = build_db_uri(cfg)
    assert uri.startswith("mysql+aiomysql://root:password@localhost:3306/testdb")
