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


def test_user_email_unique_per_tenant(test_db_session: Any) -> None:
    """Test that email is unique per tenant (not globally)."""
    from hub_api.db.models import User
    from uuid import uuid4
    from datetime import datetime

    # Create two users with same email in different tenants
    user1 = User(
        id=str(uuid4()),
        email="user@example.com",
        username="user1",
        password_hash="hash1",
        tenant="tenant-a",
        is_active=True,
        mfa_enabled=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    user2 = User(
        id=str(uuid4()),
        email="user@example.com",
        username="user2",
        password_hash="hash2",
        tenant="tenant-b",
        is_active=True,
        mfa_enabled=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Both should be insertable (different tenants)
    test_db_session.add(user1)
    test_db_session.commit()

    test_db_session.add(user2)
    test_db_session.commit()

    # Verify both exist
    assert test_db_session.query(User).filter_by(email="user@example.com").count() == 2


def test_user_username_unique_per_tenant(test_db_session: Any) -> None:
    """Test that username is unique per tenant (not globally)."""
    from hub_api.db.models import User
    from uuid import uuid4
    from datetime import datetime

    # Create two users with same username in different tenants
    user1 = User(
        id=str(uuid4()),
        email="user1@example.com",
        username="testuser",
        password_hash="hash1",
        tenant="tenant-a",
        is_active=True,
        mfa_enabled=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    user2 = User(
        id=str(uuid4()),
        email="user2@example.com",
        username="testuser",
        password_hash="hash2",
        tenant="tenant-b",
        is_active=True,
        mfa_enabled=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Both should be insertable (different tenants)
    test_db_session.add(user1)
    test_db_session.commit()

    test_db_session.add(user2)
    test_db_session.commit()

    # Verify both exist
    assert test_db_session.query(User).filter_by(username="testuser").count() == 2


def test_vrf_name_unique_per_tenant(test_db_session: Any) -> None:
    """Test that VRF name is unique per tenant (not globally)."""
    from hub_api.db.models import VRF
    from uuid import uuid4
    from datetime import datetime

    # Create two VRFs with same name in different tenants
    vrf1 = VRF(
        id=str(uuid4()),
        tenant="tenant-a",
        name="prod-vrf",
        description="Production VRF",
        rd="65001:100",
        status="active",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    vrf2 = VRF(
        id=str(uuid4()),
        tenant="tenant-b",
        name="prod-vrf",
        description="Production VRF for tenant B",
        rd="65001:200",
        status="active",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Both should be insertable (different tenants)
    test_db_session.add(vrf1)
    test_db_session.commit()

    test_db_session.add(vrf2)
    test_db_session.commit()

    # Verify both exist
    assert test_db_session.query(VRF).filter_by(name="prod-vrf").count() == 2
