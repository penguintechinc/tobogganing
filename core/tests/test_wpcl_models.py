"""Test TestSchedule model creation and schema."""
from __future__ import annotations

from uuid import uuid4
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.db.base import Base
from core.db.models import TestSchedule


@pytest.fixture
def test_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


def test_test_schedule_model_creates_table(test_engine) -> None:
    """Verify TestSchedule model creates the test_schedules table."""
    TestSchedule.__table__.create(test_engine, checkfirst=True)

    inspector = inspect(test_engine)
    tables = inspector.get_table_names()

    assert "test_schedules" in tables, "test_schedules table not created"


def test_test_schedule_table_structure(test_engine) -> None:
    """Verify test_schedules table has correct columns."""
    TestSchedule.__table__.create(test_engine, checkfirst=True)

    inspector = inspect(test_engine)
    columns = {col["name"]: col for col in inspector.get_columns("test_schedules")}

    # Verify columns exist
    expected_columns = {
        "id",
        "tenant",
        "org_unit_id",
        "test_type",
        "target",
        "interval_seconds",
        "enabled",
        "created_at",
        "updated_at",
    }
    actual_columns = set(columns.keys())
    assert (
        expected_columns == actual_columns
    ), f"Column mismatch. Expected {expected_columns}, got {actual_columns}"

    # Verify key properties
    assert columns["id"]["nullable"] is False, "id should not be nullable"
    assert columns["tenant"]["nullable"] is False, "tenant should not be nullable"
    assert columns["interval_seconds"]["nullable"] is False, "interval_seconds should not be nullable"
    assert columns["enabled"]["nullable"] is False, "enabled should not be nullable"
    assert columns["org_unit_id"]["nullable"] is True, "org_unit_id should be nullable"


def test_test_schedule_indexes(test_engine) -> None:
    """Verify test_schedules table has expected indexes from model.

    Note: Create_table() creates column-level indexes (index=True),
    but not the migration-defined composite index ix_test_schedules_tenant_ou.
    That index is created by the migration (0013_wpc_test_schedules.py).
    """
    TestSchedule.__table__.create(test_engine, checkfirst=True)

    inspector = inspect(test_engine)
    indexes = inspector.get_indexes("test_schedules")

    # Check for tenant index (created by Column(index=True) on tenant column)
    tenant_index_found = False

    for idx in indexes:
        if "tenant" in idx["column_names"]:
            tenant_index_found = True
            break

    assert tenant_index_found, "No tenant index found on tenant column"


def test_test_schedule_repr() -> None:
    """Verify TestSchedule __repr__ works correctly."""
    test_id = str(uuid4())
    ou_id = str(uuid4())

    schedule = TestSchedule(
        id=test_id,
        tenant="test-tenant",
        org_unit_id=ou_id,
        test_type="latency",
        target="example.com",
        interval_seconds=300,
        enabled=True,
    )

    repr_str = repr(schedule)
    assert "TestSchedule" in repr_str
    assert test_id in repr_str
    assert "test-tenant" in repr_str
    assert "latency" in repr_str


def test_test_schedule_base_metadata_included() -> None:
    """Verify TestSchedule is included in Base.metadata."""
    assert (
        "test_schedules" in Base.metadata.tables
    ), "test_schedules table not in Base.metadata"
    assert TestSchedule.__tablename__ == "test_schedules"
