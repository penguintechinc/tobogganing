"""Tests for C2C (cluster-to-cluster) models."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from pathlib import Path

from core.db.base import Base
from core.db.models import C2CEndpoint, C2CMatrixRun, C2CPairResult


@pytest.fixture(scope="function")
def sqlite_db(tmp_path: Path) -> sqlite3.Connection:
    """Create a temporary SQLite database with C2C tables only via SQLAlchemy."""
    db_path = tmp_path / f"test_c2c_{uuid4()}.db"

    # Create SQLAlchemy engine with fresh database file
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, echo=False)

    # Create only C2C tables (not all Base.metadata tables)
    c2c_tables = [
        Base.metadata.tables[name] for name in [
            "c2c_endpoints", "c2c_matrix_runs", "c2c_pair_results"
        ]
    ]

    for table in c2c_tables:
        table.create(engine, checkfirst=True)

    engine.dispose()

    # Open raw SQLite connection to the same database
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def test_c2c_endpoint_model_creation(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CEndpoint table is created with correct columns."""
    cursor = sqlite_db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='c2c_endpoints'")
    assert cursor.fetchone() is not None, "c2c_endpoints table not created"

    cursor.execute("PRAGMA table_info(c2c_endpoints)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    expected_columns = {
        "id", "tenant", "region", "name", "engine_url", "target",
        "api_key_hash", "enabled", "created_at", "updated_at"
    }
    assert expected_columns.issubset(columns.keys()), f"Missing columns: {expected_columns - columns.keys()}"


def test_c2c_endpoint_unique_constraint(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CEndpoint has unique constraint on (tenant, region, name)."""
    cursor = sqlite_db.cursor()
    tenant_id = "test-tenant-1"
    region = "us-east-1"
    name = "endpoint-1"

    endpoint_id_1 = str(uuid4())
    endpoint_id_2 = str(uuid4())
    now = datetime.utcnow().isoformat()

    cursor.execute(
        """INSERT INTO c2c_endpoints
           (id, tenant, region, name, engine_url, target, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (endpoint_id_1, tenant_id, region, name, "http://engine1", "target1", 1, now, now)
    )
    sqlite_db.commit()

    # Try to insert duplicate (same tenant, region, name)
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """INSERT INTO c2c_endpoints
               (id, tenant, region, name, engine_url, target, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (endpoint_id_2, tenant_id, region, name, "http://engine2", "target2", 1, now, now)
        )
        sqlite_db.commit()


def test_c2c_endpoint_indexes(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CEndpoint has expected indexes."""
    cursor = sqlite_db.cursor()
    cursor.execute("PRAGMA index_list(c2c_endpoints)")
    indexes = [row[1] for row in cursor.fetchall()]

    # Should have at least tenant and region indexes
    assert any("tenant" in idx.lower() for idx in indexes), "Missing tenant index"
    assert any("region" in idx.lower() for idx in indexes), "Missing region index"


def test_c2c_matrix_run_model_creation(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CMatrixRun table is created with correct columns."""
    cursor = sqlite_db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='c2c_matrix_runs'")
    assert cursor.fetchone() is not None, "c2c_matrix_runs table not created"

    cursor.execute("PRAGMA table_info(c2c_matrix_runs)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    expected_columns = {
        "id", "tenant", "status", "test_types", "total_pairs", "completed_pairs",
        "failed_pairs", "created_by", "created_at", "started_at", "completed_at"
    }
    assert expected_columns.issubset(columns.keys()), f"Missing columns: {expected_columns - columns.keys()}"


def test_c2c_matrix_run_creation(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CMatrixRun can be inserted with default status."""
    cursor = sqlite_db.cursor()
    run_id = str(uuid4())
    tenant_id = "test-tenant-1"
    now = datetime.utcnow().isoformat()

    cursor.execute(
        """INSERT INTO c2c_matrix_runs
           (id, tenant, status, total_pairs, completed_pairs, failed_pairs, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, tenant_id, "pending", 10, 0, 0, now)
    )
    sqlite_db.commit()

    cursor.execute("SELECT status FROM c2c_matrix_runs WHERE id = ?", (run_id,))
    result = cursor.fetchone()
    assert result is not None
    assert result[0] == "pending"


def test_c2c_pair_result_model_creation(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CPairResult table is created with correct columns."""
    cursor = sqlite_db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='c2c_pair_results'")
    assert cursor.fetchone() is not None, "c2c_pair_results table not created"

    cursor.execute("PRAGMA table_info(c2c_pair_results)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    expected_columns = {
        "id", "tenant", "run_id", "source_endpoint_id", "dest_endpoint_id",
        "source_region", "dest_region", "test_type", "status",
        "latency_ms", "throughput", "loss_pct", "test_output", "measured_at"
    }
    assert expected_columns.issubset(columns.keys()), f"Missing columns: {expected_columns - columns.keys()}"


def test_c2c_pair_result_unique_constraint(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CPairResult has unique constraint on (tenant, run_id, source_id, dest_id, test_type)."""
    cursor = sqlite_db.cursor()
    tenant_id = "test-tenant-1"
    run_id = str(uuid4())
    source_id = str(uuid4())
    dest_id = str(uuid4())
    test_type = "latency"

    result_id_1 = str(uuid4())
    result_id_2 = str(uuid4())
    now = datetime.utcnow().isoformat()

    cursor.execute(
        """INSERT INTO c2c_pair_results
           (id, tenant, run_id, source_endpoint_id, dest_endpoint_id,
            source_region, dest_region, test_type, status, measured_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (result_id_1, tenant_id, run_id, source_id, dest_id,
         "us-east-1", "us-west-1", test_type, "completed", now)
    )
    sqlite_db.commit()

    # Try to insert duplicate
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """INSERT INTO c2c_pair_results
               (id, tenant, run_id, source_endpoint_id, dest_endpoint_id,
                source_region, dest_region, test_type, status, measured_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (result_id_2, tenant_id, run_id, source_id, dest_id,
             "us-east-1", "us-west-1", test_type, "completed", now)
        )
        sqlite_db.commit()


def test_c2c_pair_result_indexes(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2CPairResult has expected indexes."""
    cursor = sqlite_db.cursor()
    cursor.execute("PRAGMA index_list(c2c_pair_results)")
    indexes = [row[1] for row in cursor.fetchall()]

    # Should have at least tenant and run_id indexes
    assert any("tenant" in idx.lower() for idx in indexes), "Missing tenant index"
    assert any("run_id" in idx.lower() for idx in indexes), "Missing run_id index"


def test_c2c_tenant_isolation(sqlite_db: sqlite3.Connection) -> None:
    """Verify C2C models support tenant isolation."""
    cursor = sqlite_db.cursor()

    # Insert endpoints for different tenants
    tenant1 = "tenant-1"
    tenant2 = "tenant-2"
    endpoint_id_1 = str(uuid4())
    endpoint_id_2 = str(uuid4())
    now = datetime.utcnow().isoformat()

    cursor.execute(
        """INSERT INTO c2c_endpoints
           (id, tenant, region, name, engine_url, target, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (endpoint_id_1, tenant1, "us-east-1", "ep1", "http://e1", "t1", 1, now, now)
    )
    cursor.execute(
        """INSERT INTO c2c_endpoints
           (id, tenant, region, name, engine_url, target, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (endpoint_id_2, tenant2, "us-east-1", "ep2", "http://e2", "t2", 1, now, now)
    )
    sqlite_db.commit()

    # Query by tenant
    cursor.execute("SELECT COUNT(*) FROM c2c_endpoints WHERE tenant = ?", (tenant1,))
    count_t1 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM c2c_endpoints WHERE tenant = ?", (tenant2,))
    count_t2 = cursor.fetchone()[0]

    assert count_t1 == 1, f"Expected 1 endpoint for tenant1, got {count_t1}"
    assert count_t2 == 1, f"Expected 1 endpoint for tenant2, got {count_t2}"
