"""Tests for the legacy whole-DB S3 prefix migration (``migrate-global-prefix``).

Uses an in-memory S3 fake (moto is not in the hashed requirements).
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hub_api.core.backup.cli import backup_cli
from hub_api.core.backup.s3 import S3Config, S3Manager

BUCKET = "bkt"


class FakeS3:
    """Minimal in-memory S3 client covering the calls the migration makes."""

    def __init__(self) -> None:
        """Start with an empty bucket."""
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:
        """Store an object."""
        self.objects[Key] = Body

    def get_paginator(self, _op: str) -> "FakeS3":
        """Return self as a single-page paginator."""
        return self

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        """List keys under Prefix as one page."""
        return [{"Contents": self._list(Prefix)}]

    def _list(self, prefix: str) -> list[dict[str, Any]]:
        """Build S3-shaped listing entries."""
        now = datetime.now(timezone.utc)
        return [
            {"Key": k, "Size": len(v), "LastModified": now}
            for k, v in sorted(self.objects.items())
            if k.startswith(prefix)
        ]

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        """Return the object body as a stream."""
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        """Return size and an MD5 ETag."""
        body = self.objects[Key]
        return {"ContentLength": len(body), "ETag": hashlib.md5(body).hexdigest()}  # noqa: S324

    def copy_object(self, Bucket: str, Key: str, CopySource: dict[str, str]) -> None:
        """Server-side copy."""
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_object(self, Bucket: str, Key: str) -> None:
        """Delete an object."""
        del self.objects[Key]


LEGACY = {"backups/w1/w1.json.gz", "backups/w1/w1.json.meta"}
UNTOUCHED = {
    "backups/ta/n/n.json",
    "backups/ta/n/n.json.meta",
    "backups/tb/tb/tb.json.meta",
    "backups/x/x.json.meta",
    "backups/_global/old/old.json",
}


def _meta(scope: str) -> bytes:
    """Encode a metadata document with the given scope."""
    return json.dumps({"scope": scope}).encode()


@pytest.fixture
def mgr() -> S3Manager:
    """S3Manager bound to a fake bucket seeded with legacy, tenant and odd keys."""
    c = FakeS3()
    c.objects.update(
        {
            "backups/w1/w1.json.gz": b"data",
            "backups/w1/w1.json.meta": _meta("whole_db"),
            "backups/ta/n/n.json": b"t",
            "backups/ta/n/n.json.meta": _meta("tenant:ta"),
            # Tenant whose backup shares the tenant's name: 3 segments, never moved.
            "backups/tb/tb/tb.json.meta": _meta("tenant:tb"),
            # Root-level folder with non-global scope stays.
            "backups/x/x.json.meta": _meta("tenant:x"),
            "backups/_global/old/old.json": b"g",
        }
    )
    m = S3Manager.__new__(S3Manager)
    m.config = S3Config(
        enabled=True,
        endpoint_url=None,
        bucket=BUCKET,
        region="us-east-1",
        access_key=None,
        secret_key=None,
        prefix="backups/",
        use_ssl=True,
        verify_ssl=True,
    )
    m.client = c
    return m


def _keys(m: S3Manager) -> set[str]:
    """All keys currently in the fake bucket."""
    return set(m.client.objects)


def test_dry_run_changes_nothing(mgr: S3Manager) -> None:
    """Dry run reports the legacy backup but moves nothing."""
    before = _keys(mgr)
    report = mgr.migrate_global_prefix(dry_run=True)
    assert report["backups"] == ["w1"]
    assert report["moved"] == 0
    assert report["examined"] == len(before)
    assert _keys(mgr) == before


def test_moves_only_global_and_is_idempotent(mgr: S3Manager) -> None:
    """Whole-DB objects move to _global/, tenant keys untouched, re-run is a no-op."""
    report = mgr.migrate_global_prefix()
    assert report["moved"] == 2
    keys = _keys(mgr)
    assert {"backups/_global/w1/w1.json.gz", "backups/_global/w1/w1.json.meta"} <= keys
    assert not keys & LEGACY
    assert UNTOUCHED <= keys
    assert mgr.client.objects["backups/_global/w1/w1.json.gz"] == b"data"
    again = mgr.migrate_global_prefix()
    assert again["moved"] == 0 and again["backups"] == []
    assert _keys(mgr) == keys
    assert {b["backup_name"] for b in mgr.list_backups()} == {"w1", "old"}


def test_verification_failure_keeps_source(mgr: S3Manager, monkeypatch: pytest.MonkeyPatch) -> None:
    """A size/ETag mismatch after copy raises and never deletes the source."""
    real_head = mgr.client.head_object

    def bad_head(Bucket: str, Key: str) -> dict[str, Any]:
        r = real_head(Bucket=Bucket, Key=Key)
        if Key.startswith("backups/_global/w1/"):
            r["ETag"] = "mismatch"
        return r

    monkeypatch.setattr(mgr.client, "head_object", bad_head)
    with pytest.raises(RuntimeError, match="verification failed"):
        mgr.migrate_global_prefix()
    assert LEGACY <= _keys(mgr)


def test_unreadable_metadata_is_skipped(mgr: S3Manager) -> None:
    """Corrupt metadata never classifies a folder as whole-DB."""
    mgr.client.objects["backups/w1/w1.json.meta"] = b"\xff not json"
    report = mgr.migrate_global_prefix()
    assert report["backups"] == [] and report["moved"] == 0
    assert LEGACY <= _keys(mgr)


def test_no_client_raises() -> None:
    """Migration fails loudly when S3 is not configured."""
    m = S3Manager.__new__(S3Manager)
    m.client = None
    with pytest.raises(RuntimeError):
        m.migrate_global_prefix()


def _run_cli(args: list[str], manager: MagicMock) -> str:
    """Run backup_cli with a patched BackupManager and capture stdout."""
    old_argv, old_stdout = sys.argv, sys.stdout
    sys.argv, sys.stdout = ["backup_cli", *args], io.StringIO()
    try:
        with patch("hub_api.core.backup.cli.BackupManager", return_value=manager):
            backup_cli(MagicMock())
        return sys.stdout.getvalue()
    finally:
        sys.argv, sys.stdout = old_argv, old_stdout


@pytest.mark.parametrize("dry", [True, False])
def test_cli_subcommand(mgr: S3Manager, dry: bool) -> None:
    """The CLI subcommand forwards --dry-run and prints the counts."""
    fake = MagicMock()
    fake.s3_manager = mgr
    out = _run_cli(["migrate-global-prefix", *(["--dry-run"] if dry else [])], fake)
    assert ("Would move 1" if dry else "Moved 1") in out
    assert ("backups/w1/w1.json.gz" in _keys(mgr)) is dry


def test_cli_without_s3_fails_loud(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exits non-zero when S3 is not configured."""
    fake = MagicMock()
    fake.s3_manager = None
    with pytest.raises(SystemExit) as exc:
        _run_cli(["migrate-global-prefix"], fake)
    assert exc.value.code == 1
    assert "S3 not configured" in capsys.readouterr().err
