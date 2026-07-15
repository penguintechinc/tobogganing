"""Integration tests for SASE backup isolation with real penguin-dal AsyncDB."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from core.modules.sase.backup import BackupManager


@pytest_asyncio.fixture
async def backup_manager_and_dir(real_dal: Any) -> tuple[BackupManager, Path]:
    """Create a backup manager with a temporary backup directory.

    Args:
        real_dal: Real async DAL instance from conftest fixture

    Yields:
        Tuple of (BackupManager, temp backup directory)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = BackupManager(real_dal, backup_dir=tmpdir)
        yield manager, Path(tmpdir)


@pytest.mark.asyncio
async def test_create_tenant_backup_isolation(real_dal: Any, backup_manager_and_dir: tuple[BackupManager, Path]) -> None:
    """Test that tenant-scoped backup includes only tenant's data and skips non-tenant tables.

    Args:
        real_dal: Real async DAL instance
        backup_manager_and_dir: Fixture providing manager and directory
    """
    manager, backup_dir = backup_manager_and_dir

    # Seed data for two tenants across multiple tenant-bearing tables
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Insert test data for tenant A into users table
    await manager.db.users.async_insert(
        id="user-a1",
        username="alice",
        email="alice@a.com",
        password_hash="hash1",
        tenant=tenant_a,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    # Insert test data for tenant B into users table
    await manager.db.users.async_insert(
        id="user-b1",
        username="bob",
        email="bob@b.com",
        password_hash="hash2",
        tenant=tenant_b,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    # Create tenant A backup
    backup_a = await manager.create_backup(
        backup_name="backup_tenant_a",
        compress=False,
        tenant_id=tenant_a,
    )

    assert backup_a["scope"] == f"tenant:{tenant_a}"

    # Verify backup file exists and contains only tenant A's data
    backup_file = Path(backup_a["file_path"])
    assert backup_file.exists()
    assert (backup_dir / tenant_a / "backup_tenant_a.json") == backup_file

    # Load and verify backup contents
    with open(backup_file) as f:
        backup_data = json.load(f)

    # Verify metadata
    assert backup_data["metadata"]["scope"] == f"tenant:{tenant_a}"

    # Verify only tenant A's user is in backup (tenant B's data excluded)
    users_in_backup = backup_data["data"].get("users", [])
    assert len(users_in_backup) == 1
    assert users_in_backup[0]["id"] == "user-a1"
    assert users_in_backup[0]["username"] == "alice"
    # Verify tenant B's user is NOT in the backup
    assert all(u["id"] != "user-b1" for u in users_in_backup)


@pytest.mark.asyncio
async def test_restore_tenant_backup_isolation(real_dal: Any, backup_manager_and_dir: tuple[BackupManager, Path]) -> None:
    """Test that tenant-scoped restore only updates tenant's rows, leaving other tenants' data intact.

    Args:
        real_dal: Real async DAL instance
        backup_manager_and_dir: Fixture providing manager and directory
    """
    manager, backup_dir = backup_manager_and_dir

    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Seed initial data for both tenants
    await manager.db.users.async_insert(
        id="user-a1",
        username="alice",
        email="alice@a.com",
        password_hash="hash1",
        tenant=tenant_a,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    await manager.db.users.async_insert(
        id="user-b1",
        username="bob",
        email="bob@b.com",
        password_hash="hash2",
        tenant=tenant_b,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    # Create tenant A backup
    backup_metadata = await manager.create_backup(
        backup_name="backup_a_v1",
        compress=False,
        tenant_id=tenant_a,
    )
    backup_file = Path(backup_metadata["file_path"])

    # Modify tenant A's data in database (simulate changed state)
    await manager.db(manager.db.users.id == "user-a1").update(email="alice.updated@a.com")

    # Verify modification was applied
    result = await manager.db(manager.db.users.id == "user-a1").select()
    modified_user = result.first()
    assert modified_user.email == "alice.updated@a.com"

    # Restore tenant A's backup (should revert alice's email)
    restore_result = await manager.restore_backup(
        backup_path=str(backup_file),
        tenant_id=tenant_a,
    )

    assert restore_result["total_rows_restored"] == 1

    # Verify tenant A's data was restored
    result_a = await manager.db(manager.db.users.id == "user-a1").select()
    restored_user_a = result_a.first()
    assert restored_user_a.email == "alice@a.com"

    # Verify tenant B's data was NOT touched
    result_b = await manager.db(manager.db.users.id == "user-b1").select()
    user_b = result_b.first()
    assert user_b.email == "bob@b.com"  # Should remain unchanged


@pytest.mark.asyncio
async def test_restore_fail_closed_tenant_authorization(
    real_dal: Any,
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """Test that restoring a backup from another tenant's directory is REJECTED.

    Args:
        real_dal: Real async DAL instance
        backup_manager_and_dir: Fixture providing manager and directory
    """
    manager, backup_dir = backup_manager_and_dir

    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Create a backup for tenant A
    await manager.db.users.async_insert(
        id="user-a1",
        username="alice",
        email="alice@a.com",
        password_hash="hash1",
        tenant=tenant_a,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    backup_metadata = await manager.create_backup(
        backup_name="backup_a",
        compress=False,
        tenant_id=tenant_a,
    )
    backup_file = Path(backup_metadata["file_path"])

    # Attempt to restore tenant A's backup as if it belonged to tenant B (should FAIL)
    with pytest.raises(ValueError, match="Path escapes backup directory"):
        await manager.restore_backup(
            backup_path=str(backup_file),
            tenant_id=tenant_b,  # Wrong tenant!
        )


@pytest.mark.asyncio
async def test_whole_db_backup_includes_all_tenants(
    real_dal: Any,
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """Test that whole-DB backup (tenant_id=None) includes data from all tenants.

    Args:
        real_dal: Real async DAL instance
        backup_manager_and_dir: Fixture providing manager and directory
    """
    manager, backup_dir = backup_manager_and_dir

    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Seed data for both tenants
    await manager.db.users.async_insert(
        id="user-a1",
        username="alice",
        email="alice@a.com",
        password_hash="hash1",
        tenant=tenant_a,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    await manager.db.users.async_insert(
        id="user-b1",
        username="bob",
        email="bob@b.com",
        password_hash="hash2",
        tenant=tenant_b,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    # Create whole-DB backup (tenant_id=None)
    backup_metadata = await manager.create_backup(
        backup_name="backup_whole_db",
        compress=False,
        tenant_id=None,
    )

    assert backup_metadata["scope"] == "whole_db"

    # Verify both tenants' data is in backup
    backup_file = Path(backup_metadata["file_path"])
    with open(backup_file) as f:
        backup_data = json.load(f)

    users_in_backup = backup_data["data"].get("users", [])
    assert len(users_in_backup) == 2
    user_ids = {u["id"] for u in users_in_backup}
    assert user_ids == {"user-a1", "user-b1"}


@pytest.mark.asyncio
async def test_whole_db_restore_replaces_all_data(
    real_dal: Any,
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """Test that whole-DB restore (tenant_id=None) replaces all tenant data.

    Args:
        real_dal: Real async DAL instance
        backup_manager_and_dir: Fixture providing manager and directory
    """
    manager, backup_dir = backup_manager_and_dir

    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Create and backup initial state
    await manager.db.users.async_insert(
        id="user-a1",
        username="alice",
        email="alice@a.com",
        password_hash="hash1",
        tenant=tenant_a,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    await manager.db.users.async_insert(
        id="user-b1",
        username="bob",
        email="bob@b.com",
        password_hash="hash2",
        tenant=tenant_b,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    backup_metadata = await manager.create_backup(
        backup_name="backup_whole_db_v1",
        compress=False,
        tenant_id=None,
    )
    backup_file = Path(backup_metadata["file_path"])

    # Add a third user (not in backup)
    await manager.db.users.async_insert(
        id="user-c1",
        username="charlie",
        email="charlie@c.com",
        password_hash="hash3",
        tenant="tenant-c",
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    # Verify backup has only 2 users before restore
    with open(backup_file) as f:
        backup_data_debug = json.load(f)
    assert len(backup_data_debug["data"]["users"]) == 2

    # Restore whole-DB backup (should delete charlie, keep alice and bob)
    restore_result = await manager.restore_backup(
        backup_path=str(backup_file),
        tenant_id=None,
    )

    assert restore_result["total_rows_restored"] == 2

    # Verify only backed-up users remain
    result_all = await manager.db(manager.db.users.id != None).select()  # noqa: E712
    all_users = list(result_all)
    user_ids = {u.id for u in all_users}
    assert user_ids == {"user-a1", "user-b1"}
    assert "user-c1" not in user_ids


@pytest.mark.asyncio
async def test_tenant_backup_restores_only_tenant_columns(
    real_dal: Any,
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """Test that tenant backup handles both 'tenant' and 'tenant_id' column names.

    This test focuses on the detection of tenant columns and correct filtering.

    Args:
        real_dal: Real async DAL instance
        backup_manager_and_dir: Fixture providing manager and directory
    """
    manager, backup_dir = backup_manager_and_dir

    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc)

    # Insert users with 'tenant' column
    await manager.db.users.async_insert(
        id="user-a1",
        username="alice",
        email="alice@a.com",
        password_hash="hash1",
        tenant=tenant_a,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    await manager.db.users.async_insert(
        id="user-b1",
        username="bob",
        email="bob@b.com",
        password_hash="hash2",
        tenant=tenant_b,
        created_at=now,
        updated_at=now,
        is_active=True,
    )

    # Create tenant A backup
    backup_metadata = await manager.create_backup(
        backup_name="backup_check_columns",
        compress=False,
        tenant_id=tenant_a,
    )

    # Verify tenant A's data only
    backup_file = Path(backup_metadata["file_path"])
    with open(backup_file) as f:
        backup_data = json.load(f)

    users_in_backup = backup_data["data"].get("users", [])
    assert len(users_in_backup) == 1
    assert users_in_backup[0]["id"] == "user-a1"


@pytest.mark.asyncio
async def test_tenant_restore_drops_foreign_tenant_rows_in_file(
    real_dal: Any,
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """Row-level fail-closed: a backup that (through tampering, a mis-scoped
    whole_db backup, or a bad S3 key) contains rows for OTHER tenants must never
    inject those rows when restored under a single tenant. Only the caller
    tenant's rows are written; foreign rows are counted and dropped.

    regression: backup restore tenant-isolation fail-open (commit review)
    """
    manager, backup_dir = backup_manager_and_dir

    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    now = datetime.now(timezone.utc).isoformat()

    # Hand-craft a backup file that lives UNDER tenant A's directory (so the
    # fail-closed path check passes) but whose payload contains a tenant B row.
    poisoned = {
        "metadata": {"version": "1.0", "scope": f"tenant:{tenant_a}", "tables": []},
        "data": {
            "users": [
                {
                    "id": "user-a1", "username": "alice", "email": "alice@a.com",
                    "password_hash": "h1", "tenant": tenant_a,
                    "created_at": now, "updated_at": now, "is_active": True,
                },
                {
                    # Foreign row — must be dropped, never injected into tenant B.
                    "id": "user-b-evil", "username": "mallory", "email": "m@b.com",
                    "password_hash": "h2", "tenant": tenant_b,
                    "created_at": now, "updated_at": now, "is_active": True,
                },
            ]
        },
    }
    tenant_dir = backup_dir / tenant_a
    tenant_dir.mkdir(parents=True, exist_ok=True)
    backup_file = tenant_dir / "poisoned.json"
    backup_file.write_text(json.dumps(poisoned))

    result = await manager.restore_backup(backup_path=str(backup_file), tenant_id=tenant_a)

    # Only tenant A's row was restored; the foreign row was dropped and counted.
    assert result["total_rows_restored"] == 1
    assert result["rows_skipped_foreign_tenant"] == 1

    rows = list(await manager.db(manager.db.users.id != None).select())  # noqa: E712
    ids = {r.id for r in rows}
    assert "user-a1" in ids
    assert "user-b-evil" not in ids  # foreign-tenant injection blocked
