"""Database and Alembic migration tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect


def test_alembic_0001_core_baseline_creates_users_table_with_tenant() -> None:
    """Test that the 0001_core_baseline migration creates the users table with tenant column."""
    # Create a temporary SQLite database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_uri = f"sqlite:///{db_path}"

        # Create an Alembic config pointing to the temp DB
        alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"
        assert (
            alembic_ini_path.exists()
        ), f"alembic.ini not found at {alembic_ini_path}"

        alembic_cfg = AlembicConfig(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", db_uri)

        # Set the script location to the migrations directory
        migrations_dir = Path(__file__).parent.parent / "migrations"
        alembic_cfg.set_main_option("script_location", str(migrations_dir))

        # Run the migration
        command.upgrade(alembic_cfg, "head")

        # Connect to the database and verify the table was created
        engine = sa.create_engine(db_uri)
        inspector = inspect(engine)

        # Check that users table exists
        tables = inspector.get_table_names()
        assert "users" in tables, f"users table not found. Tables: {tables}"

        # Check that users table has the tenant column
        columns = inspector.get_columns("users")
        column_names = {col["name"] for col in columns}
        assert "tenant" in column_names, (
            f"tenant column not found in users table. Columns: {column_names}"
        )

        # Verify other required columns are present
        required_columns = {
            "id",
            "email",
            "username",
            "password_hash",
            "is_active",
            "mfa_enabled",
            "mfa_secret",
            "tenant",
        }
        assert required_columns.issubset(
            column_names
        ), f"Missing required columns. Expected {required_columns}, got {column_names}"
