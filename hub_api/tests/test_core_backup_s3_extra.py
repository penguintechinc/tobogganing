"""Additional coverage for hub_api.core.backup.s3: bucket lifecycle and remaining
S3Manager operations (metadata, download, delete) plus init error branches.

test_core_backup.py covers S3Config.from_env(), basic init, upload_backup, and
list_backups; this file fills in _ensure_bucket/_create_bucket, upload_metadata,
download_backup, delete_backup, get_metadata, and _init_client error paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from hub_api.core.backup.s3 import S3_AVAILABLE, S3Config, S3Manager


def _config(**overrides: object) -> S3Config:
    """Build an S3Config with sane defaults, overridable per test."""
    base = dict(
        enabled=True,
        endpoint_url=None,
        bucket="test-bucket",
        region="us-east-1",
        access_key="key",
        secret_key="secret",
        prefix="backups/",
        use_ssl=True,
        verify_ssl=True,
    )
    base.update(overrides)
    return S3Config(**base)  # type: ignore[arg-type]


class TestInitClientErrors:
    """Tests for S3Manager._init_client() error branches."""

    def test_boto3_unavailable_raises_import_error(self) -> None:
        """__init__ raises ImportError when S3_AVAILABLE is False."""
        with patch("hub_api.core.backup.s3.S3_AVAILABLE", False):
            with pytest.raises(ImportError, match="boto3 required"):
                S3Manager(_config())

    @patch("hub_api.core.backup.s3.boto3")
    def test_no_credentials_error_reraises(self, mock_boto3: MagicMock) -> None:
        """__init__ propagates NoCredentialsError from boto3.Session()."""
        mock_boto3.Session.side_effect = NoCredentialsError()
        with pytest.raises(NoCredentialsError):
            S3Manager(_config())

    @patch("hub_api.core.backup.s3.boto3")
    def test_generic_init_error_reraises(self, mock_boto3: MagicMock) -> None:
        """__init__ propagates unexpected exceptions from client construction."""
        mock_boto3.Session.side_effect = RuntimeError("network down")
        with pytest.raises(RuntimeError, match="network down"):
            S3Manager(_config())

    @patch("hub_api.core.backup.s3.boto3")
    def test_endpoint_url_passed_through(self, mock_boto3: MagicMock) -> None:
        """__init__ passes a custom endpoint_url into the client config."""
        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client

        S3Manager(_config(endpoint_url="https://minio.local"))

        _, kwargs = mock_boto3.Session.return_value.client.call_args
        assert kwargs["endpoint_url"] == "https://minio.local"


class TestEnsureBucket:
    """Tests for S3Manager._ensure_bucket() / _create_bucket()."""

    @patch("hub_api.core.backup.s3.boto3")
    def test_bucket_exists_no_create(self, mock_boto3: MagicMock) -> None:
        """_ensure_bucket() does nothing when head_bucket() succeeds."""
        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client

        S3Manager(_config())

        mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")
        mock_client.create_bucket.assert_not_called()

    @patch("hub_api.core.backup.s3.boto3")
    def test_bucket_missing_creates_us_east_1(self, mock_boto3: MagicMock) -> None:
        """_ensure_bucket() creates the bucket (no LocationConstraint) for us-east-1."""
        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client
        mock_client.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadBucket")

        S3Manager(_config(region="us-east-1"))

        mock_client.create_bucket.assert_called_once_with(Bucket="test-bucket")

    @patch("hub_api.core.backup.s3.boto3")
    def test_bucket_missing_creates_with_location_constraint(self, mock_boto3: MagicMock) -> None:
        """_ensure_bucket() creates the bucket with LocationConstraint outside us-east-1."""
        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client
        mock_client.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadBucket")

        S3Manager(_config(region="eu-west-1"))

        mock_client.create_bucket.assert_called_once_with(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )

    @patch("hub_api.core.backup.s3.boto3")
    def test_bucket_access_error_reraises(self, mock_boto3: MagicMock) -> None:
        """_ensure_bucket() re-raises non-404 ClientErrors."""
        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client
        mock_client.head_bucket.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadBucket")

        with pytest.raises(ClientError):
            S3Manager(_config())

    @patch("hub_api.core.backup.s3.boto3")
    def test_create_bucket_failure_reraises(self, mock_boto3: MagicMock) -> None:
        """_create_bucket() re-raises ClientError from create_bucket()."""
        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client
        mock_client.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadBucket")
        mock_client.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "500"}}, "CreateBucket"
        )

        with pytest.raises(ClientError):
            S3Manager(_config())


def _make_manager(mock_boto3: MagicMock) -> tuple[S3Manager, MagicMock]:
    """Build an S3Manager with a mocked client, returning (manager, mock_client)."""
    mock_client = MagicMock()
    mock_boto3.Session.return_value.client.return_value = mock_client
    manager = S3Manager(_config())
    return manager, mock_client


class TestUploadMetadata:
    """Tests for S3Manager.upload_metadata()."""

    @patch("hub_api.core.backup.s3.boto3")
    def test_upload_metadata_success(self, mock_boto3: MagicMock, tmp_path: Path) -> None:
        """upload_metadata() uploads the metadata file via upload_fileobj()."""
        manager, mock_client = _make_manager(mock_boto3)
        meta_file = tmp_path / "backup.meta"
        meta_file.write_text("{}")

        manager.upload_metadata(meta_file, "backup1")

        mock_client.upload_fileobj.assert_called_once()

    @patch("hub_api.core.backup.s3.boto3")
    def test_upload_metadata_no_client_noop(self, mock_boto3: MagicMock, tmp_path: Path) -> None:
        """upload_metadata() is a no-op when no client is configured."""
        manager = S3Manager(_config(enabled=False))
        meta_file = tmp_path / "backup.meta"
        meta_file.write_text("{}")

        manager.upload_metadata(meta_file, "backup1")  # should not raise

    @patch("hub_api.core.backup.s3.boto3")
    def test_upload_metadata_failure_logged_not_raised(
        self, mock_boto3: MagicMock, tmp_path: Path
    ) -> None:
        """upload_metadata() swallows exceptions (best-effort)."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.upload_fileobj.side_effect = RuntimeError("upload failed")
        meta_file = tmp_path / "backup.meta"
        meta_file.write_text("{}")

        manager.upload_metadata(meta_file, "backup1")  # should not raise


class TestUploadBackupFailure:
    """Tests for S3Manager.upload_backup() error path."""

    @patch("hub_api.core.backup.s3.boto3")
    def test_upload_backup_no_client_raises(self, mock_boto3: MagicMock, tmp_path: Path) -> None:
        """upload_backup() raises RuntimeError when no client is configured."""
        manager = S3Manager(_config(enabled=False))
        test_file = tmp_path / "b.json"
        test_file.write_text("{}")

        with pytest.raises(RuntimeError, match="S3 client not initialized"):
            manager.upload_backup(test_file, "b")

    @patch("hub_api.core.backup.s3.boto3")
    def test_upload_backup_failure_reraises(self, mock_boto3: MagicMock, tmp_path: Path) -> None:
        """upload_backup() re-raises on unexpected upload failures."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.upload_fileobj.side_effect = RuntimeError("network error")
        test_file = tmp_path / "b.json"
        test_file.write_text("{}")

        with pytest.raises(RuntimeError, match="network error"):
            manager.upload_backup(test_file, "b")


class TestDownloadBackup:
    """Tests for S3Manager.download_backup()."""

    @patch("hub_api.core.backup.s3.boto3")
    def test_download_backup_no_client_raises(self, mock_boto3: MagicMock) -> None:
        """download_backup() raises RuntimeError when no client is configured."""
        manager = S3Manager(_config(enabled=False))
        with pytest.raises(RuntimeError, match="S3 client not initialized"):
            manager.download_backup("backups/b/b.json")

    @patch("hub_api.core.backup.s3.boto3")
    def test_download_backup_success(self, mock_boto3: MagicMock) -> None:
        """download_backup() downloads to a temp file and returns its path."""
        manager, mock_client = _make_manager(mock_boto3)

        result = manager.download_backup("backups/b/b.json")

        mock_client.download_file.assert_called_once()
        assert result.suffix == ".backup"

    @patch("hub_api.core.backup.s3.boto3")
    def test_download_backup_failure_reraises(self, mock_boto3: MagicMock) -> None:
        """download_backup() re-raises unexpected download failures."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.download_file.side_effect = RuntimeError("download failed")

        with pytest.raises(RuntimeError, match="download failed"):
            manager.download_backup("backups/b/b.json")


class TestListBackupsEdgeCases:
    """Additional list_backups() branches."""

    @patch("hub_api.core.backup.s3.boto3")
    def test_list_backups_no_client_returns_empty(self, mock_boto3: MagicMock) -> None:
        """list_backups() returns [] when no client is configured."""
        manager = S3Manager(_config(enabled=False))
        assert manager.list_backups() == []

    @patch("hub_api.core.backup.s3.boto3")
    def test_list_backups_skips_meta_and_dir_keys(self, mock_boto3: MagicMock) -> None:
        """list_backups() skips '.meta' files and directory-marker keys."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "backups/b1/b1.meta",
                        "Size": 1,
                        "LastModified": MagicMock(isoformat=lambda: "x"),
                    },
                    {
                        "Key": "backups/b1/",
                        "Size": 0,
                        "LastModified": MagicMock(isoformat=lambda: "x"),
                    },
                    {
                        "Key": "backups/b1/b1.json.gz",
                        "Size": 100,
                        "LastModified": MagicMock(isoformat=lambda: "2026-01-01"),
                    },
                ]
            }
        ]

        backups = manager.list_backups()

        assert len(backups) == 1
        assert backups[0]["backup_name"] == "b1"

    @patch("hub_api.core.backup.s3.boto3")
    def test_list_backups_exception_returns_empty(self, mock_boto3: MagicMock) -> None:
        """list_backups() returns [] on unexpected pagination errors."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.get_paginator.side_effect = RuntimeError("boom")

        assert manager.list_backups() == []


class TestDeleteBackup:
    """Tests for S3Manager.delete_backup()."""

    @patch("hub_api.core.backup.s3.boto3")
    def test_delete_backup_no_client_returns_false(self, mock_boto3: MagicMock) -> None:
        """delete_backup() returns False when no client is configured."""
        manager = S3Manager(_config(enabled=False))
        assert manager.delete_backup("b1") is False

    @patch("hub_api.core.backup.s3.boto3")
    def test_delete_backup_no_objects_returns_false(self, mock_boto3: MagicMock) -> None:
        """delete_backup() returns False when list_objects_v2 finds nothing."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.list_objects_v2.return_value = {}

        assert manager.delete_backup("b1") is False

    @patch("hub_api.core.backup.s3.boto3")
    def test_delete_backup_success(self, mock_boto3: MagicMock) -> None:
        """delete_backup() deletes all matching objects and returns True."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.list_objects_v2.return_value = {
            "Contents": [{"Key": "backups/b1/b1.json"}, {"Key": "backups/b1/b1.meta"}]
        }

        result = manager.delete_backup("b1")

        assert result is True
        mock_client.delete_objects.assert_called_once()

    @patch("hub_api.core.backup.s3.boto3")
    def test_delete_backup_exception_returns_false(self, mock_boto3: MagicMock) -> None:
        """delete_backup() returns False on unexpected errors."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.list_objects_v2.side_effect = RuntimeError("boom")

        assert manager.delete_backup("b1") is False


class TestGetMetadata:
    """Tests for S3Manager.get_metadata()."""

    @patch("hub_api.core.backup.s3.boto3")
    def test_get_metadata_no_client_returns_none(self, mock_boto3: MagicMock) -> None:
        """get_metadata() returns None when no client is configured."""
        manager = S3Manager(_config(enabled=False))
        assert manager.get_metadata("b1") is None

    @patch("hub_api.core.backup.s3.boto3")
    def test_get_metadata_success(self, mock_boto3: MagicMock) -> None:
        """get_metadata() parses and returns the JSON metadata body."""
        manager, mock_client = _make_manager(mock_boto3)
        body_mock = MagicMock()
        body_mock.read.return_value = b'{"backup_name": "b1"}'
        mock_client.get_object.return_value = {"Body": body_mock}

        result = manager.get_metadata("b1")

        assert result == {"backup_name": "b1"}

    @patch("hub_api.core.backup.s3.boto3")
    def test_get_metadata_client_error_returns_none(self, mock_boto3: MagicMock) -> None:
        """get_metadata() returns None when the object doesn't exist (ClientError)."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )

        assert manager.get_metadata("b1") is None

    @patch("hub_api.core.backup.s3.boto3")
    def test_get_metadata_unexpected_error_returns_none(self, mock_boto3: MagicMock) -> None:
        """get_metadata() returns None on unexpected exceptions."""
        manager, mock_client = _make_manager(mock_boto3)
        mock_client.get_object.side_effect = RuntimeError("boom")

        assert manager.get_metadata("b1") is None


def test_s3_available_flag_reflects_import() -> None:
    """S3_AVAILABLE is True in this environment (boto3 is installed)."""
    assert S3_AVAILABLE is True
