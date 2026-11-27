"""Tests for tenant-scoped backup CLI and real scheduler-backed schedule_backup."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.core.backup import tasks as backup_tasks
from hub_api.core.backup.cli import backup_cli
from hub_api.core.backup.manager import BackupManager
from hub_api.scheduler.registry import clear_handlers, handler_for


def _run_cli(argv: list[str], mgr: MagicMock) -> None:
    """Run backup_cli with a patched BackupManager."""
    with (
        patch.object(sys, "argv", ["backup_cli", *argv]),
        patch("hub_api.core.backup.cli.BackupManager", return_value=mgr),
    ):
        backup_cli(MagicMock())


class TestCliTenantScope:
    """--tenant-id is passed through to create/restore."""

    def test_create_with_tenant(self) -> None:
        """Create forwards --tenant-id."""
        mgr = MagicMock()
        mgr.create_backup = AsyncMock(return_value={"file_path": "/b/x"})
        _run_cli(["create", "--tenant-id", "t-1"], mgr)
        assert mgr.create_backup.await_args.kwargs["tenant_id"] == "t-1"

    def test_create_default_whole_db(self) -> None:
        """Create without --tenant-id is whole-DB."""
        mgr = MagicMock()
        mgr.create_backup = AsyncMock(return_value={"file_path": "/b/x"})
        _run_cli(["create"], mgr)
        assert mgr.create_backup.await_args.kwargs["tenant_id"] is None

    def test_restore_with_tenant(self) -> None:
        """Restore forwards --tenant-id."""
        mgr = MagicMock()
        mgr.restore_backup = AsyncMock(return_value={"total_rows_restored": 3})
        _run_cli(["restore", "p.json", "--tenant-id", "t-2"], mgr)
        assert mgr.restore_backup.await_args.kwargs["tenant_id"] == "t-2"


def _manager(tmp_path: Path) -> tuple[BackupManager, MagicMock]:
    """Build a BackupManager over a mock DB with a scheduled_jobs table."""
    db = MagicMock()
    db.tables = []
    db.scheduled_jobs.async_insert = AsyncMock()
    with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
        return BackupManager(db, backup_dir=str(tmp_path)), db


@pytest.mark.asyncio
class TestScheduleBackup:
    """schedule_backup persists a real scheduled job and registers its handler."""

    async def test_registers_job_and_handler(self, tmp_path: Path) -> None:
        """A scheduled_jobs row is inserted and the sweep handler resolves."""
        clear_handlers()
        mgr, db = _manager(tmp_path)
        job_id = await mgr.schedule_backup("t-1", 3600, compress=True)
        kw = db.scheduled_jobs.async_insert.await_args.kwargs
        assert kw["id"] == job_id
        assert kw["tenant"] == "t-1"
        assert kw["module"] == "core_backup"
        assert kw["job_type"] == "create_backup"
        assert kw["interval_seconds"] == 3600
        assert json.loads(kw["payload"]) == {"compress": True}
        assert handler_for("core_backup", "create_backup") == backup_tasks.BACKUP_TASK_NAME

    @pytest.mark.parametrize(
        ("tenant", "interval", "kwargs", "msg"),
        [
            ("", 3600, {}, "tenant_id is required"),
            ("t", 3600, {"encryption_key": "x"}, "must not be persisted"),
            ("t", 3600, {"bogus": 1}, "unsupported"),
            ("t", 5, {}, "at least 30"),
        ],
    )
    async def test_rejects_invalid(
        self, tmp_path: Path, tenant: str, interval: int, kwargs: dict[str, Any], msg: str
    ) -> None:
        """Invalid requests raise loudly and persist nothing."""
        mgr, db = _manager(tmp_path)
        with pytest.raises(ValueError, match=msg):
            await mgr.schedule_backup(tenant, interval, **kwargs)
        db.scheduled_jobs.async_insert.assert_not_called()


@pytest.mark.asyncio
class TestRunScheduledBackup:
    """Worker task runs a tenant-scoped backup."""

    async def test_runs_tenant_scoped(self) -> None:
        """Payload options and tenant reach create_backup."""
        with patch("hub_api.core.backup.manager.BackupManager") as cls:
            cls.return_value.create_backup = AsyncMock(return_value={"ok": 1})
            out = await backup_tasks._run_scheduled_backup_async(
                "t-1", json.dumps({"compress": False}), db=MagicMock()
            )
        assert out == {"ok": 1}
        kw = cls.return_value.create_backup.await_args.kwargs
        assert kw["tenant_id"] == "t-1"
        assert kw["compress"] is False

    async def test_encrypt_uses_env_key(self) -> None:
        """Encryption key comes from env, never the payload."""
        with (
            patch("hub_api.core.backup.manager.BackupManager") as cls,
            patch.dict("os.environ", {"BACKUP_ENCRYPTION_KEY": "k"}),
        ):
            cls.return_value.create_backup = AsyncMock(return_value={})
            await backup_tasks._run_scheduled_backup_async("t", {"encrypt": True}, db=MagicMock())
        assert cls.return_value.create_backup.await_args.kwargs["encryption_key"] == "k"

    async def test_encrypt_without_key_fails(self) -> None:
        """Encrypt without env key fails loudly."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="BACKUP_ENCRYPTION_KEY"):
                await backup_tasks._run_scheduled_backup_async(
                    "t", {"encrypt": True}, db=MagicMock()
                )

    async def test_missing_tenant_fails(self) -> None:
        """Empty tenant is rejected."""
        with pytest.raises(ValueError, match="requires a tenant"):
            await backup_tasks._run_scheduled_backup_async("", {}, db=MagicMock())

    async def test_builds_db_when_none(self) -> None:
        """A DAL is built from config when none is injected."""
        fake_db = MagicMock()
        fake_db.reflect = AsyncMock()
        with (
            patch("penguin_dal.AsyncDB", return_value=fake_db),
            patch("hub_api.config.build_db_uri", return_value="sqlite://"),
            patch("hub_api.core.backup.manager.BackupManager") as cls,
        ):
            cls.return_value.create_backup = AsyncMock(return_value={})
            await backup_tasks._run_scheduled_backup_async("t", None)
        fake_db.reflect.assert_awaited_once()


def test_celery_entry_point() -> None:
    """Celery task delegates to the async runner with tenant and payload."""
    with patch.object(
        backup_tasks, "_run_scheduled_backup_async", new=AsyncMock(return_value={"r": 1})
    ) as run:
        fn = getattr(backup_tasks.run_scheduled_backup, "run", backup_tasks.run_scheduled_backup)
        assert fn("jid-12345678", "t", "core_backup", "create_backup", "{}") == {"r": 1}
    run.assert_awaited_once_with("t", "{}")
