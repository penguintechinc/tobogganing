"""Tests that tenant-scoped S3 backups never collide or leak across tenants."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub_api.core.backup import tasks as backup_tasks
from hub_api.core.backup.manager import BackupManager
from hub_api.core.backup.s3 import S3Config, S3Manager


def _s3(objects: list[str] | None = None) -> S3Manager:
    """Build an S3Manager with a mock client (no network)."""
    cfg = S3Config(
        enabled=True,
        endpoint_url=None,
        bucket="b",
        region="r",
        access_key=None,
        secret_key=None,
        prefix="backups/",
        use_ssl=True,
        verify_ssl=True,
    )
    mgr = S3Manager.__new__(S3Manager)
    mgr.config = cfg
    mgr.client = MagicMock()
    now = datetime.now(timezone.utc)
    pages = [{"Contents": [{"Key": k, "Size": 1, "LastModified": now} for k in (objects or [])]}]
    mgr.client.get_paginator.return_value.paginate.return_value = pages
    return mgr


def _manager(tmp_path: Path) -> BackupManager:
    """Build a BackupManager over a mock DB."""
    db = MagicMock()
    db.tables = []
    with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
        return BackupManager(db, backup_dir=str(tmp_path))


class TestS3TenantPrefix:
    """S3 key layout and filtering by tenant."""

    def test_same_name_two_tenants_no_collision(self, tmp_path: Path) -> None:
        """Identical backup names land under distinct tenant prefixes."""
        f = tmp_path / "n.json"
        f.write_text("{}")
        mgr = _s3()
        mgr.client.head_object.return_value = {"ETag": '"e"', "ContentLength": 2}
        a = mgr.upload_backup(f, "n", tenant_id="ta")["s3_key"]
        b = mgr.upload_backup(f, "n", tenant_id="tb")["s3_key"]
        assert a == "backups/ta/n/n.json"
        assert b == "backups/tb/n/n.json"
        mgr.upload_metadata(f, "n", tenant_id="ta")
        assert mgr.client.upload_fileobj.call_args.args[2] == "backups/ta/n/n.json"

    def test_untenanted_key_unchanged(self, tmp_path: Path) -> None:
        """Whole-DB backups live under the reserved _global prefix."""
        f = tmp_path / "w.json"
        f.write_text("{}")
        mgr = _s3()
        mgr.client.head_object.return_value = {"ETag": '"e"', "ContentLength": 2}
        assert mgr.upload_backup(f, "w")["s3_key"] == "backups/_global/w/w.json"

    def test_global_backup_not_visible_to_tenant_named_like_it(self) -> None:
        """Regression (s174): a whole-DB backup named like a tenant ID is not listed
        under that tenant, and whole-DB listing still finds it."""
        mgr = _s3(["backups/_global/ta/ta.json", "backups/ta/n/n.json"])
        mgr.client.get_paginator.return_value.paginate.side_effect = lambda Bucket, Prefix: [
            {
                "Contents": [
                    {"Key": k, "Size": 1, "LastModified": datetime.now(timezone.utc)}
                    for k in ["backups/_global/ta/ta.json", "backups/ta/n/n.json"]
                    if k.startswith(Prefix)
                ]
            }
        ]
        assert [o["s3_key"] for o in mgr.list_backups(tenant_id="ta")] == ["backups/ta/n/n.json"]
        assert [o["s3_key"] for o in mgr.list_backups()] == ["backups/_global/ta/ta.json"]
        assert not mgr.key_belongs_to_tenant("backups/_global/ta/ta.json", "ta")

    def test_tenant_id_with_reserved_underscore_rejected(self) -> None:
        """Tenant IDs starting with '_' cannot alias the reserved global prefix."""
        mgr = _s3()
        with pytest.raises(ValueError, match="reserved"):
            mgr.tenant_base("_global")

    def test_manager_rejects_underscore_tenant_id(self) -> None:
        """The manager's tenant validator rejects a leading underscore."""
        from hub_api.core.backup.manager import _validate_tenant_id

        with pytest.raises(ValueError, match="reserved"):
            _validate_tenant_id("_global")
        _validate_tenant_id("tenant-a")

    def test_list_filtered_to_tenant(self) -> None:
        """Tenant listing uses the tenant prefix and drops foreign keys."""
        mgr = _s3(["backups/ta/n/n.json", "backups/tb/n/n.json"])
        out = mgr.list_backups(tenant_id="ta")
        assert [o["s3_key"] for o in out] == ["backups/ta/n/n.json"]
        assert out[0]["backup_name"] == "n"
        paginate = mgr.client.get_paginator.return_value.paginate
        assert paginate.call_args.kwargs["Prefix"] == "backups/ta/"

    @pytest.mark.parametrize(
        ("key", "ok"),
        [
            ("backups/ta/n/n.json", True),
            ("backups/tb/n/n.json", False),
            ("backups/ta/../tb/n/n.json", False),
            ("backups/tab/n/n.json", False),
        ],
    )
    def test_key_belongs_to_tenant(self, key: str, ok: bool) -> None:
        """Prefix match is exact and rejects traversal."""
        assert _s3().key_belongs_to_tenant(key, "ta") is ok

    def test_delete_and_metadata_tenant_prefixed(self) -> None:
        """Delete and metadata lookups are scoped to the tenant prefix."""
        mgr = _s3()
        mgr.client.list_objects_v2.return_value = {}
        mgr.delete_backup("n", tenant_id="ta")
        assert mgr.client.list_objects_v2.call_args.kwargs["Prefix"] == "backups/ta/n/"
        mgr.client.get_object.return_value = {"Body": MagicMock(read=lambda: b'{"a": 1}')}
        assert mgr.get_metadata("n", tenant_id="ta") == {"a": 1}
        assert mgr.client.get_object.call_args.kwargs["Key"] == "backups/ta/n/n.meta"


@pytest.mark.asyncio
async def test_cross_tenant_s3_restore_refused(tmp_path: Path) -> None:
    """Restoring another tenant's S3 key raises and downloads nothing."""
    mgr = _manager(tmp_path)
    s3: Any = _s3()
    s3.download_backup = MagicMock()
    mgr.s3_manager = s3
    with pytest.raises(ValueError, match="outside the caller's tenant"):
        await mgr.restore_backup(backup_path="backups/tb/n/n.json", from_s3=True, tenant_id="ta")
    s3.download_backup.assert_not_called()


@pytest.mark.asyncio
async def test_scheduled_backup_names_unique() -> None:
    """Each scheduled run gets a job-prefixed unique backup name."""
    with patch("hub_api.core.backup.manager.BackupManager") as cls:
        cls.return_value.create_backup = AsyncMock(return_value={})
        await backup_tasks._run_scheduled_backup_async("t", {}, db=MagicMock(), job_id="j1")
        await backup_tasks._run_scheduled_backup_async("t", {}, db=MagicMock(), job_id="j1")
    names = [c.kwargs["backup_name"] for c in cls.return_value.create_backup.await_args_list]
    assert names[0] != names[1]
    assert all(n.startswith("sched_j1_") for n in names)


def test_manager_list_and_delete_pass_tenant(tmp_path: Path) -> None:
    """Manager list/delete forward tenant to S3."""
    mgr = _manager(tmp_path)
    s3 = MagicMock()
    s3.list_backups.return_value = []
    mgr.s3_manager = s3
    mgr.list_backups(include_s3=True, tenant_id="ta")
    s3.list_backups.assert_called_once_with(tenant_id="ta")
    mgr.delete_backup("n", from_s3=True, tenant_id="ta")
    s3.delete_backup.assert_called_once_with("n", tenant_id="ta")
