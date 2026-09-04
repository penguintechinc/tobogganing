"""Tests for hub_api.core.backup.cli: argparse-driven backup CLI commands."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.core.backup.cli import backup_cli


def _run_cli(args: list[str], db: MagicMock) -> str:
    """Run backup_cli() with the given argv and capture stdout."""
    from io import StringIO

    old_argv = sys.argv
    old_stdout = sys.stdout
    sys.argv = ["backup_cli"] + args
    sys.stdout = StringIO()
    try:
        backup_cli(db)
        return sys.stdout.getvalue()
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout


@pytest.fixture
def mock_db() -> MagicMock:
    """Minimal mock DAL for CLI tests (BackupManager only touches backup_dir/tables)."""
    db = MagicMock()
    db.tables = {}
    return db


class TestCreateCommand:
    """Tests for `backup_cli create`."""

    def test_create_prints_backup_path(self, mock_db: MagicMock, tmp_path) -> None:
        """`create` invokes BackupManager.create_backup and prints the file path."""
        fake_manager = MagicMock()
        fake_manager.create_backup = AsyncMock(
            return_value={"file_path": str(tmp_path / "backup.json"), "s3_info": None}
        )
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["create", "--name", "mybackup"], mock_db)

        assert "Backup created" in output
        fake_manager.create_backup.assert_awaited_once()
        call_kwargs = fake_manager.create_backup.call_args.kwargs
        assert call_kwargs["tenant_id"] is None  # whole-DB only, per CLI contract

    def test_create_prints_s3_info_when_uploaded(self, mock_db: MagicMock) -> None:
        """`create --s3` prints the S3 key when upload metadata is present."""
        fake_manager = MagicMock()
        fake_manager.create_backup = AsyncMock(
            return_value={
                "file_path": "/backups/x.json",
                "s3_info": {"s3_key": "backups/x/x.json"},
            }
        )
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["create", "--s3"], mock_db)

        assert "Uploaded to S3" in output
        assert "backups/x/x.json" in output


class TestRestoreCommand:
    """Tests for `backup_cli restore`."""

    def test_restore_prints_row_count(self, mock_db: MagicMock) -> None:
        """`restore` invokes BackupManager.restore_backup and prints the row count."""
        fake_manager = MagicMock()
        fake_manager.restore_backup = AsyncMock(return_value={"total_rows_restored": 42})
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["restore", "/backups/x.json"], mock_db)

        assert "42 rows" in output
        fake_manager.restore_backup.assert_awaited_once()
        call_kwargs = fake_manager.restore_backup.call_args.kwargs
        assert call_kwargs["tenant_id"] is None


class TestListCommand:
    """Tests for `backup_cli list`."""

    def test_list_all_backups(self, mock_db: MagicMock) -> None:
        """`list` (no filters) lists both local and S3 backups."""
        fake_manager = MagicMock()
        fake_manager.list_backups.return_value = [
            {"backup_name": "b1", "created_at": "2026-01-01", "storage_location": "local"},
        ]
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["list"], mock_db)

        assert "b1" in output
        fake_manager.list_backups.assert_called_once_with(include_s3=True)

    def test_list_local_only(self, mock_db: MagicMock) -> None:
        """`list --local-only` excludes S3 backups."""
        fake_manager = MagicMock()
        fake_manager.list_backups.return_value = []
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            _run_cli(["list", "--local-only"], mock_db)

        fake_manager.list_backups.assert_called_once_with(include_s3=False)

    def test_list_s3_only_with_manager(self, mock_db: MagicMock) -> None:
        """`list --s3-only` uses s3_manager.list_backups() when S3 is configured."""
        fake_manager = MagicMock()
        fake_manager.s3_manager = MagicMock()
        fake_manager.s3_manager.list_backups.return_value = [
            {"backup_name": "s3backup", "created_at": "2026-01-01", "storage_location": "s3"}
        ]
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["list", "--s3-only"], mock_db)

        assert "s3backup" in output

    def test_list_s3_only_without_manager(self, mock_db: MagicMock) -> None:
        """`list --s3-only` prints nothing when S3 isn't configured."""
        fake_manager = MagicMock()
        fake_manager.s3_manager = None
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["list", "--s3-only"], mock_db)

        assert output.strip() == ""


class TestDeleteCommand:
    """Tests for `backup_cli delete`."""

    def test_delete_success(self, mock_db: MagicMock) -> None:
        """`delete` prints confirmation when the backup existed."""
        fake_manager = MagicMock()
        fake_manager.delete_backup.return_value = True
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["delete", "mybackup"], mock_db)

        assert "Backup deleted: mybackup" in output

    def test_delete_not_found(self, mock_db: MagicMock) -> None:
        """`delete` prints a not-found message when delete_backup() returns False."""
        fake_manager = MagicMock()
        fake_manager.delete_backup.return_value = False
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["delete", "missing"], mock_db)

        assert "Backup not found: missing" in output


class TestS3StatusCommand:
    """Tests for `backup_cli s3-status`."""

    def test_s3_status_disabled(self, mock_db: MagicMock) -> None:
        """`s3-status` prints disabled state without further details."""
        fake_manager = MagicMock()
        fake_manager.s3_config = MagicMock(enabled=False)
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["s3-status"], mock_db)

        assert "S3 Enabled: False" in output

    def test_s3_status_enabled_connection_success(self, mock_db: MagicMock) -> None:
        """`s3-status` reports a successful connection test when head_bucket succeeds."""
        fake_manager = MagicMock()
        fake_manager.s3_config = MagicMock(
            enabled=True, bucket="my-bucket", region="us-east-1", endpoint_url=None
        )
        fake_manager.s3_manager = MagicMock()
        fake_manager.s3_manager.client = MagicMock()
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["s3-status"], mock_db)

        assert "Bucket: my-bucket" in output
        assert "Connection Test" in output
        assert "Success" in output

    def test_s3_status_enabled_connection_failure(self, mock_db: MagicMock) -> None:
        """`s3-status` reports a failed connection test when head_bucket raises."""
        fake_manager = MagicMock()
        fake_manager.s3_config = MagicMock(
            enabled=True, bucket="my-bucket", region="us-east-1", endpoint_url="https://x"
        )
        fake_manager.s3_manager = MagicMock()
        fake_manager.s3_manager.client = MagicMock()
        fake_manager.s3_manager.client.head_bucket.side_effect = RuntimeError("no access")
        with patch("hub_api.core.backup.cli.BackupManager", return_value=fake_manager):
            output = _run_cli(["s3-status"], mock_db)

        assert "Connection Test" in output
        assert "Failed" in output


def test_cli_error_exits_1(mock_db: MagicMock, capsys: pytest.CaptureFixture) -> None:
    """backup_cli() prints an error and exits 1 when the async command raises."""
    with patch("hub_api.core.backup.cli.BackupManager", side_effect=RuntimeError("init failed")):
        with patch.object(sys, "argv", ["backup_cli", "create"]):
            with pytest.raises(SystemExit) as exc_info:
                backup_cli(mock_db)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "init failed" in captured.err
