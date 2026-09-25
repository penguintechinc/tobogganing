"""Additional coverage for hub_api.core.backup.manager error/edge branches.

test_core_backup.py (mocked DB) and test_core_backup_isolation_realdal.py
(real DAL) cover the main create/restore tenant-isolation flows; this file
fills in encrypt/decrypt error paths, checksum verification, malformed backup
files, missing-file handling, S3-integrated create/restore, list/delete edge
cases, and schedule_backup().
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from hub_api.core.backup import BackupManager


@pytest_asyncio.fixture
async def backup_manager_and_dir(real_dal: Any) -> tuple[BackupManager, Path]:
    """BackupManager bound to a temporary backup directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = BackupManager(real_dal, backup_dir=tmpdir)
        yield manager, Path(tmpdir)


async def _seed_user(manager: BackupManager, tenant: str, user_id: str) -> None:
    """Insert a minimal user row for the given tenant."""
    now = datetime.now(timezone.utc)
    await manager.db.users.async_insert(
        id=user_id,
        username=f"user-{user_id}",
        email=f"{user_id}@example.com",
        password_hash="hash",
        tenant=tenant,
        created_at=now,
        updated_at=now,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_create_backup_auto_generates_name(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """create_backup() without an explicit name auto-generates a timestamped one."""
    manager, backup_dir = backup_manager_and_dir
    result = await manager.create_backup(compress=False)

    assert result["backup_name"].startswith("sasewaddle_backup_")
    assert Path(result["file_path"]).exists()


@pytest.mark.asyncio
async def test_create_backup_encrypt_without_key_raises(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """create_backup(encrypt=True) without encryption_key raises ValueError."""
    manager, _ = backup_manager_and_dir
    with pytest.raises(ValueError, match="Encryption key required"):
        await manager.create_backup(backup_name="enc_test", encrypt=True)


@pytest.mark.asyncio
async def test_create_backup_encrypt_round_trip(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """create_backup(encrypt=True) + restore_backup(decrypt=True) round-trips."""
    manager, _ = backup_manager_and_dir
    await _seed_user(manager, "tenant-a", "user-1")

    result = await manager.create_backup(
        backup_name="enc_backup", compress=True, encrypt=True, encryption_key="pw123"
    )
    assert result["file_path"].endswith(".enc")

    restore_result = await manager.restore_backup(
        backup_path=result["file_path"], decrypt=True, decryption_key="pw123"
    )
    assert restore_result["total_rows_restored"] >= 1


@pytest.mark.asyncio
async def test_restore_backup_file_not_found(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup() raises FileNotFoundError for a nonexistent local file."""
    manager, backup_dir = backup_manager_and_dir
    with pytest.raises(FileNotFoundError, match="Backup not found"):
        await manager.restore_backup(backup_path=str(backup_dir / "nope.json"))


@pytest.mark.asyncio
async def test_restore_backup_checksum_mismatch_raises(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup() raises ValueError when the stored checksum doesn't match."""
    manager, _ = backup_manager_and_dir
    result = await manager.create_backup(backup_name="checksum_test", compress=False)
    backup_file = Path(result["file_path"])

    # Tamper with the backup content after checksum was computed.
    backup_file.write_text(backup_file.read_text() + "\n// tampered")

    with pytest.raises(ValueError, match="Checksum verification failed"):
        await manager.restore_backup(backup_path=str(backup_file))


@pytest.mark.asyncio
async def test_restore_backup_decrypt_without_key_raises(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup(decrypt=True) without decryption_key raises ValueError."""
    manager, _ = backup_manager_and_dir
    result = await manager.create_backup(
        backup_name="need_key", compress=True, encrypt=True, encryption_key="pw"
    )
    with pytest.raises(ValueError, match="Decryption key required"):
        await manager.restore_backup(backup_path=result["file_path"], decrypt=True)


@pytest.mark.asyncio
async def test_restore_backup_invalid_format_raises(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup() raises ValueError for a JSON file missing metadata/data keys."""
    manager, backup_dir = backup_manager_and_dir
    bad_file = backup_dir / "malformed.json"
    bad_file.write_text(json.dumps({"not_metadata": True}))

    with pytest.raises(ValueError, match="Invalid backup format"):
        await manager.restore_backup(backup_path=str(bad_file), verify_checksum=False)


@pytest.mark.asyncio
async def test_restore_backup_scope_mismatch_logged_but_continues(
    backup_manager_and_dir: tuple[BackupManager, Path],
    capsys: pytest.CaptureFixture,
) -> None:
    """restore_backup() logs a scope mismatch warning but still restores."""
    manager, backup_dir = backup_manager_and_dir
    now = datetime.now(timezone.utc).isoformat()

    tenant_dir = backup_dir / "tenant-a"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    whole_db_backup = {
        "metadata": {"version": "1.0", "scope": "whole_db", "tables": []},
        "data": {
            "users": [
                {
                    "id": "user-x",
                    "username": "x",
                    "email": "x@example.com",
                    "password_hash": "h",
                    "tenant": "tenant-a",
                    "created_at": now,
                    "updated_at": now,
                    "is_active": True,
                }
            ]
        },
    }
    backup_file = tenant_dir / "mismatched.json"
    backup_file.write_text(json.dumps(whole_db_backup))

    capsys.readouterr()  # clear any prior output
    result = await manager.restore_backup(
        backup_path=str(backup_file), tenant_id="tenant-a", verify_checksum=False
    )
    captured = capsys.readouterr()

    assert result["total_rows_restored"] == 1
    assert "backup_scope_mismatch" in captured.out


@pytest.mark.asyncio
async def test_restore_backup_unknown_table_recorded_as_error(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup() records an error entry for tables that don't exist in the DB."""
    manager, backup_dir = backup_manager_and_dir

    backup_with_unknown_table = {
        "metadata": {"version": "1.0", "scope": "whole_db", "tables": []},
        "data": {
            "totally_made_up_table": [{"id": "x"}],
        },
    }
    backup_file = backup_dir / "unknown_table.json"
    backup_file.write_text(json.dumps(backup_with_unknown_table))

    result = await manager.restore_backup(backup_path=str(backup_file), verify_checksum=False)

    assert result["total_rows_restored"] == 0
    assert any("not found" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_get_tenant_column_returns_none_for_unknown_table(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """_get_tenant_column() returns None for a table name not in db.tables."""
    manager, _ = backup_manager_and_dir
    assert manager._get_tenant_column("not_a_real_table") is None


def test_schedule_backup_returns_id() -> None:
    """schedule_backup() returns a schedule_id string (placeholder implementation)."""
    mock_db = MagicMock()
    mock_db.tables = []
    manager = BackupManager(mock_db, backup_dir=tempfile.mkdtemp())

    schedule_id = manager.schedule_backup("0 0 * * *", compress=True)

    assert schedule_id.startswith("schedule_")


@pytest.mark.asyncio
class TestListAndDeleteEdgeCases:
    """Edge cases for list_backups() and delete_backup()."""

    async def test_list_backups_skips_corrupt_meta_file(
        self, backup_manager_and_dir: tuple[BackupManager, Path]
    ) -> None:
        """list_backups() logs a warning and skips unreadable .meta files."""
        manager, backup_dir = backup_manager_and_dir
        corrupt_meta = backup_dir / "corrupt.meta"
        corrupt_meta.write_text("not valid json{{{")

        backups = manager.list_backups(include_s3=False)

        assert backups == []

    async def test_list_backups_merges_s3_with_local_metadata(
        self, backup_manager_and_dir: tuple[BackupManager, Path]
    ) -> None:
        """list_backups() merges S3 listing entries with their S3 metadata when present."""
        manager, _ = backup_manager_and_dir
        fake_s3 = MagicMock()
        fake_s3.list_backups.return_value = [
            {
                "backup_name": "s3backup",
                "filename": "s3backup.json.gz",
                "last_modified": "2026-01-01T00:00:00",
            }
        ]
        fake_s3.get_metadata.return_value = {"backup_name": "s3backup", "table_count": 3}
        manager.s3_manager = fake_s3

        backups = manager.list_backups(include_s3=True)

        assert len(backups) == 1
        assert backups[0]["storage_location"] == "s3"
        assert backups[0]["table_count"] == 3

    async def test_list_backups_s3_without_metadata_uses_defaults(
        self, backup_manager_and_dir: tuple[BackupManager, Path]
    ) -> None:
        """list_backups() falls back to derived fields when S3 metadata is absent."""
        manager, _ = backup_manager_and_dir
        fake_s3 = MagicMock()
        fake_s3.list_backups.return_value = [
            {
                "backup_name": "s3backup2",
                "filename": "s3backup2.json.gz",
                "last_modified": "2026-01-01T00:00:00",
            }
        ]
        fake_s3.get_metadata.return_value = None
        manager.s3_manager = fake_s3

        backups = manager.list_backups(include_s3=True)

        assert len(backups) == 1
        assert backups[0]["compressed"] is True
        assert backups[0]["encrypted"] is False

    async def test_delete_backup_skips_symlink(
        self, backup_manager_and_dir: tuple[BackupManager, Path]
    ) -> None:
        """delete_backup() skips symlinked backup files rather than deleting them."""
        manager, backup_dir = backup_manager_and_dir
        real_file = backup_dir / "real_target.json"
        real_file.write_text("{}")
        symlink_backup = backup_dir / "symlinked.json"
        symlink_backup.symlink_to(real_file)

        deleted = manager.delete_backup("symlinked")

        # Symlinked backup file itself must not be unlinked.
        assert symlink_backup.exists()
        assert deleted is False

    async def test_delete_backup_with_s3_manager(
        self, backup_manager_and_dir: tuple[BackupManager, Path]
    ) -> None:
        """delete_backup(from_s3=True) delegates to s3_manager.delete_backup()."""
        manager, _ = backup_manager_and_dir
        fake_s3 = MagicMock()
        fake_s3.delete_backup.return_value = True
        manager.s3_manager = fake_s3

        result = manager.delete_backup("b1", from_s3=True)

        assert result is True
        fake_s3.delete_backup.assert_called_once_with("b1")


@pytest.mark.asyncio
async def test_create_backup_uploads_to_s3_when_configured(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """create_backup() uploads the backup + metadata to S3 when a manager is configured."""
    manager, _ = backup_manager_and_dir
    await _seed_user(manager, "tenant-a", "user-1")

    fake_s3 = MagicMock()
    fake_s3.upload_backup.return_value = {"s3_key": "backups/x/x.json", "bucket": "b"}
    manager.s3_manager = fake_s3

    result = await manager.create_backup(
        backup_name="s3_upload_test", compress=False, upload_to_s3=True
    )

    assert result["s3_info"]["s3_key"] == "backups/x/x.json"
    fake_s3.upload_backup.assert_called_once()
    fake_s3.upload_metadata.assert_called_once()


@pytest.mark.asyncio
async def test_create_backup_no_id_column_uses_first_column_fallback(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """create_backup() falls back to the first column when a table has no 'id' attr."""
    from unittest.mock import AsyncMock as AM

    manager, _ = backup_manager_and_dir
    manager.db = MagicMock()
    manager.db.tables = {"weird_table": MagicMock(c=MagicMock(keys=lambda: ["seq_no"]))}

    weird_table = MagicMock(spec=["seq_no"])
    weird_table.seq_no = MagicMock()
    row = MagicMock()
    row.as_dict.return_value = {"seq_no": 1}
    rowset = MagicMock()
    rowset.__iter__ = MagicMock(return_value=iter([row]))
    query_proxy = MagicMock()
    query_proxy.select = AM(return_value=rowset)
    manager.db.__call__ = MagicMock(return_value=query_proxy)
    manager.db.weird_table = weird_table

    result = await manager.create_backup(backup_name="no_id_table", compress=False)

    assert result["backup_name"] == "no_id_table"


@pytest.mark.asyncio
async def test_create_backup_unselectable_table_skipped(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """create_backup() skips (rather than fails) a table it can't construct a select for."""
    manager, _ = backup_manager_and_dir
    manager.db = MagicMock()
    manager.db.tables = {"empty_table": MagicMock(c=MagicMock(keys=lambda: []))}
    manager.db.empty_table = MagicMock(spec=[])  # no 'id' and no columns

    result = await manager.create_backup(backup_name="unselectable", compress=False)

    assert result["table_count"] == 0


@pytest.mark.asyncio
async def test_create_backup_per_table_exception_swallowed(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """create_backup() logs and continues when a single table's backup raises."""
    from unittest.mock import AsyncMock as AM

    manager, _ = backup_manager_and_dir
    manager.db = MagicMock()
    manager.db.tables = {"broken_table": MagicMock(c=MagicMock(keys=lambda: ["id"]))}
    broken_table = MagicMock()
    manager.db.broken_table = broken_table

    query_proxy = MagicMock()
    query_proxy.select = AM(side_effect=RuntimeError("query failed"))
    manager.db.__call__ = MagicMock(return_value=query_proxy)

    result = await manager.create_backup(backup_name="broken", compress=False)

    assert result["table_count"] == 0


@pytest.mark.asyncio
async def test_restore_backup_skips_shared_table_in_tenant_mode(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup(tenant_id=...) skips tables with no tenant column entirely."""
    manager, backup_dir = backup_manager_and_dir
    now = datetime.now(timezone.utc).isoformat()

    tenant_dir = backup_dir / "tenant-a"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    # "users" is a real table (via real_dal reflection) so it passes the
    # "table not found" check; _get_tenant_column() is force-overridden below
    # to simulate a shared/global table with no tenant column.
    backup_with_shared_table = {
        "metadata": {"version": "1.0", "scope": "tenant:tenant-a", "tables": []},
        "data": {
            "users": [
                {
                    "id": "user-x",
                    "username": "x",
                    "email": "x@example.com",
                    "password_hash": "h",
                    "tenant": "tenant-a",
                    "created_at": now,
                    "updated_at": now,
                    "is_active": True,
                }
            ],
        },
    }
    backup_file = tenant_dir / "shared.json"
    backup_file.write_text(json.dumps(backup_with_shared_table))

    with patch.object(BackupManager, "_get_tenant_column", return_value=None):
        result = await manager.restore_backup(
            backup_path=str(backup_file), tenant_id="tenant-a", verify_checksum=False
        )

    assert result["total_rows_restored"] == 0
    assert result["tables_restored"] == []


@pytest.mark.asyncio
async def test_restore_backup_invalid_datetime_string_kept_as_is(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup() keeps a malformed '_at'-suffixed field as the original string
    (datetime.fromisoformat's ValueError is caught and swallowed at that point), and
    the row-level insert failure that follows (SQLite rejects a non-datetime value in
    a datetime column) is itself caught by the per-table exception handler and
    recorded as an error rather than propagating.
    """
    manager, backup_dir = backup_manager_and_dir
    backup_with_bad_date = {
        "metadata": {"version": "1.0", "scope": "whole_db", "tables": []},
        "data": {
            "users": [
                {
                    "id": "user-bad-date",
                    "username": "x",
                    "email": "x@example.com",
                    "password_hash": "h",
                    "tenant": "tenant-a",
                    "created_at": "not-a-real-datetime",
                    "updated_at": "not-a-real-datetime",
                    "is_active": True,
                }
            ]
        },
    }
    backup_file = backup_dir / "bad_date.json"
    backup_file.write_text(json.dumps(backup_with_bad_date))

    # Should not raise despite the unparseable datetime string.
    result = await manager.restore_backup(backup_path=str(backup_file), verify_checksum=False)

    assert result["total_rows_restored"] == 0
    assert any("users" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_restore_backup_per_table_exception_recorded(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup() records a per-table error and continues on delete/insert failure.

    Uses a mocked db (rather than real_dal) since penguin-dal's AsyncDB
    returns fresh proxy objects per `db.<table>` attribute access, so
    patching an already-fetched table reference doesn't affect the handler's
    own internal lookup.
    """
    manager, backup_dir = backup_manager_and_dir
    backup_data = {
        "metadata": {"version": "1.0", "scope": "whole_db", "tables": []},
        "data": {
            "users": [
                {
                    "id": "user-1",
                    "username": "x",
                    "email": "x@example.com",
                    "password_hash": "h",
                    "tenant": "tenant-a",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "is_active": True,
                }
            ]
        },
    }
    backup_file = backup_dir / "insert_fail.json"
    backup_file.write_text(json.dumps(backup_data))

    mock_db = MagicMock()
    mock_db.tables = {"users": True}
    users_table = MagicMock(spec=["id", "async_insert"])
    users_table.async_insert = AsyncMock(side_effect=RuntimeError("insert failed"))
    mock_db.users = users_table
    query_proxy = MagicMock()
    query_proxy.delete = AsyncMock(return_value=None)
    # NOTE: a bare `mock_db.__call__ = MagicMock(...)` assignment does NOT
    # change how calling the mock instance behaves — Mock's own __call__
    # dispatches via `.return_value`, so that must be set too (matches the
    # authoritative pattern in tests/conftest.py's mock_db fixture).
    mock_db.__call__ = MagicMock(return_value=query_proxy)
    mock_db.return_value = query_proxy
    manager.db = mock_db

    result = await manager.restore_backup(backup_path=str(backup_file), verify_checksum=False)

    assert result["total_rows_restored"] == 0
    assert any("insert failed" in e for e in result["errors"])


def test_sanitize_db_uri_masks_credentials() -> None:
    """_sanitize_db_uri() masks user:pass in the URI when get_db_uri_fn is provided."""
    mock_db = MagicMock()
    mock_db.tables = []
    manager = BackupManager(
        mock_db,
        backup_dir=tempfile.mkdtemp(),
        get_db_uri_fn=lambda: "postgresql://admin:s3cr3t@dbhost/mydb",
    )

    sanitized = manager._sanitize_db_uri()

    assert "s3cr3t" not in sanitized
    assert "***:***@" in sanitized


def test_sanitize_db_uri_unknown_without_fn() -> None:
    """_sanitize_db_uri() returns 'unknown' when no get_db_uri_fn is configured."""
    mock_db = MagicMock()
    mock_db.tables = []
    manager = BackupManager(mock_db, backup_dir=tempfile.mkdtemp())

    assert manager._sanitize_db_uri() == "unknown"


@pytest.mark.asyncio
async def test_restore_backup_from_s3(
    backup_manager_and_dir: tuple[BackupManager, Path],
) -> None:
    """restore_backup(from_s3=True) downloads the backup via s3_manager first."""
    manager, backup_dir = backup_manager_and_dir
    await _seed_user(manager, "tenant-a", "user-1")

    local_result = await manager.create_backup(backup_name="for_s3_restore", compress=False)
    local_path = Path(local_result["file_path"])

    fake_s3 = MagicMock()
    fake_s3.download_backup.return_value = local_path
    manager.s3_manager = fake_s3

    result = await manager.restore_backup(
        backup_path="backups/for_s3_restore/for_s3_restore.json",
        from_s3=True,
        verify_checksum=False,
    )

    fake_s3.download_backup.assert_called_once()
    assert result["total_rows_restored"] >= 1
