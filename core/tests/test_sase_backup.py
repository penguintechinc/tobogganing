"""Tests for SASE backup module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.modules.sase.backup import BackupManager, S3Config, S3Manager
from core.modules.sase.backup.crypto import decrypt_file, encrypt_file


def _create_backup_mock_db() -> MagicMock:
    """Create mock DAL for backup tests."""
    db = MagicMock()
    db.tables = ["users"]

    users_table = MagicMock()
    users_table.fields = ["id", "name"]

    query_proxy = MagicMock()
    query_proxy.select.return_value = []
    db.return_value = query_proxy
    db.__call__ = MagicMock(return_value=query_proxy)
    db.__getitem__.return_value = users_table
    db.commit = MagicMock()
    db.rollback = MagicMock()

    return db


class TestEncryption:
    """Test encryption and decryption."""

    def test_encrypt_decrypt_roundtrip(self, tmp_path: Path) -> None:
        """Test encrypt/decrypt roundtrip."""
        # Create test file
        test_file = tmp_path / "test.txt"
        original_data = b"Hello, World! This is secret data."
        test_file.write_bytes(original_data)

        # Encrypt
        key = "my_secret_password_123"
        encrypted_file = encrypt_file(test_file, key)

        assert encrypted_file.exists()
        assert encrypted_file.suffix == ".enc"
        assert not test_file.exists()

        # Decrypt
        decrypted_file = decrypt_file(encrypted_file, key)

        assert decrypted_file.exists()
        assert decrypted_file.suffix == ".txt"
        assert not encrypted_file.exists()

        # Verify
        decrypted_data = decrypted_file.read_bytes()
        assert decrypted_data == original_data

    def test_encrypt_missing_file(self, tmp_path: Path) -> None:
        """Test encrypt with missing file."""
        missing_file = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError):
            encrypt_file(missing_file, "key")

    def test_decrypt_invalid_key(self, tmp_path: Path) -> None:
        """Test decrypt with wrong key."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"Secret data")

        key = "correct_key"
        encrypted_file = encrypt_file(test_file, key)

        # Try to decrypt with wrong key
        with pytest.raises(Exception):
            decrypt_file(encrypted_file, "wrong_key")

    def test_encrypt_different_salts(self, tmp_path: Path) -> None:
        """Test that repeated encryptions produce different output (random salt)."""
        test_data = b"Same plaintext"
        key = "test_password"

        # Encrypt same data twice
        test_file1 = tmp_path / "test1.txt"
        test_file1.write_bytes(test_data)
        encrypted1 = encrypt_file(test_file1, key)
        encrypted1_bytes = encrypted1.read_bytes()

        test_file2 = tmp_path / "test2.txt"
        test_file2.write_bytes(test_data)
        encrypted2 = encrypt_file(test_file2, key)
        encrypted2_bytes = encrypted2.read_bytes()

        # Ciphertexts should differ (different salts)
        assert encrypted1_bytes != encrypted2_bytes

        # But both should decrypt to same plaintext
        decrypted1 = decrypt_file(encrypted1, key)
        decrypted2 = decrypt_file(encrypted2, key)

        assert decrypted1.read_bytes() == test_data
        assert decrypted2.read_bytes() == test_data


class TestS3Config:
    """Test S3 configuration."""

    def test_s3_config_from_env(self) -> None:
        """Test S3 config from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "BACKUP_S3_ENABLED": "true",
                "BACKUP_S3_BUCKET": "test-bucket",
                "BACKUP_S3_REGION": "eu-west-1",
            },
        ):
            config = S3Config.from_env()

            assert config.enabled is True
            assert config.bucket == "test-bucket"
            assert config.region == "eu-west-1"
            assert config.use_ssl is True

    def test_s3_config_defaults(self) -> None:
        """Test S3 config defaults."""
        with patch.dict("os.environ", {}, clear=True):
            config = S3Config.from_env()

            assert config.enabled is False
            assert config.bucket == "sasewaddle-backups"
            assert config.region == "us-east-1"


class TestBackupManagerLocal:
    """Test local backup operations."""

    @pytest.fixture
    def backup_mock_db(self) -> MagicMock:
        """Create mock DAL for backup tests."""
        db = MagicMock()
        db.tables = ["users", "widgets"]

        # Mock users table
        users_table = MagicMock()
        users_table.fields = ["id", "name", "email"]

        # Create mock rows
        mock_rows = []
        for row_data in [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ]:
            row = MagicMock()
            for key, value in row_data.items():
                setattr(row, key, value)
            row.__getitem__ = lambda self, k, d=row_data: d.get(k)
            mock_rows.append(row)

        # Mock select and query
        query_proxy = MagicMock()
        query_proxy.select.return_value = mock_rows
        db.return_value = query_proxy
        db.__call__ = MagicMock(return_value=query_proxy)
        db.__getitem__.return_value = users_table
        db.commit = MagicMock()
        db.rollback = MagicMock()

        return db

    def test_create_backup_local(self, tmp_path: Path, backup_mock_db: MagicMock) -> None:
        """Test local backup creation."""
        backup_dir = tmp_path / "backups"

        with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
            manager = BackupManager(backup_mock_db, backup_dir=str(backup_dir))

            # Create backup
            result = manager.create_backup(backup_name="test_backup", compress=False)

            assert result["backup_name"] == "test_backup"
            assert result["file_path"]
            assert result["compressed"] is False
            assert result["encrypted"] is False
            assert "checksum" in result

            # Verify files exist
            backup_file = Path(result["file_path"])
            assert backup_file.exists()
            assert backup_file.with_suffix(".meta").exists()

    def test_create_backup_compressed(self, tmp_path: Path, backup_mock_db: MagicMock) -> None:
        """Test compressed backup creation."""
        backup_dir = tmp_path / "backups"

        with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
            manager = BackupManager(backup_mock_db, backup_dir=str(backup_dir))
            result = manager.create_backup(backup_name="test_compressed", compress=True)

            assert result["compressed"] is True
            backup_file = Path(result["file_path"])
            assert backup_file.suffix == ".gz"

    def test_list_backups_local(self, tmp_path: Path, backup_mock_db: MagicMock) -> None:
        """Test listing local backups."""
        backup_dir = tmp_path / "backups"

        with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
            manager = BackupManager(backup_mock_db, backup_dir=str(backup_dir))

            # Create two backups
            manager.create_backup(backup_name="backup1", compress=False)
            manager.create_backup(backup_name="backup2", compress=False)

            # List backups
            backups = manager.list_backups(include_s3=False)

            assert len(backups) == 2
            names = [b["backup_name"] for b in backups]
            assert "backup1" in names
            assert "backup2" in names

    def test_delete_backup_local(self, tmp_path: Path, backup_mock_db: MagicMock) -> None:
        """Test local backup deletion."""
        backup_dir = tmp_path / "backups"

        with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
            manager = BackupManager(backup_mock_db, backup_dir=str(backup_dir))

            # Create backup
            manager.create_backup(backup_name="to_delete", compress=False)

            # Verify it exists
            backups = manager.list_backups(include_s3=False)
            assert len(backups) == 1

            # Delete
            deleted = manager.delete_backup("to_delete")
            assert deleted is True

            # Verify it's gone
            backups = manager.list_backups(include_s3=False)
            assert len(backups) == 0


class TestS3Manager:
    """Test S3 manager operations."""

    def test_s3_manager_init_disabled(self) -> None:
        """Test S3 manager when disabled."""
        config = S3Config(
            enabled=False,
            endpoint_url=None,
            bucket="test",
            region="us-east-1",
            access_key=None,
            secret_key=None,
            prefix="backups/",
            use_ssl=True,
            verify_ssl=True,
        )

        manager = S3Manager(config)
        assert manager.client is None

    @patch("core.modules.sase.backup.s3.boto3")
    def test_s3_manager_init_enabled(self, mock_boto3: MagicMock) -> None:
        """Test S3 manager when enabled."""
        config = S3Config(
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

        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client

        manager = S3Manager(config)
        assert manager.client is not None

    @patch("core.modules.sase.backup.s3.boto3")
    def test_s3_upload_backup(self, mock_boto3: MagicMock, tmp_path: Path) -> None:
        """Test S3 backup upload."""
        config = S3Config(
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

        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client
        mock_client.head_object.return_value = {
            "ETag": '"abc123"',
            "ContentLength": 1024,
        }

        manager = S3Manager(config)

        # Create test file
        test_file = tmp_path / "backup.json.gz"
        test_file.write_bytes(b"test data")

        result = manager.upload_backup(test_file, "test_backup")

        assert result["bucket"] == "test-bucket"
        assert result["etag"] == "abc123"
        assert result["size_bytes"] == 1024
        mock_client.upload_fileobj.assert_called_once()

    @patch("core.modules.sase.backup.s3.boto3")
    def test_s3_list_backups(self, mock_boto3: MagicMock) -> None:
        """Test S3 backup listing."""
        config = S3Config(
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

        mock_client = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_client

        # Mock paginator
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "backups/backup1/backup1.json.gz",
                        "Size": 1024,
                        "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
                    }
                ]
            }
        ]

        manager = S3Manager(config)
        backups = manager.list_backups()

        assert len(backups) == 1
        assert backups[0]["backup_name"] == "backup1"


class TestBackupRestore:
    """Test backup restore operations."""

    @pytest.fixture
    def backup_db(self, tmp_path: Path) -> tuple:
        """Create mock DB and backup data."""
        backup_data = {
            "metadata": {
                "version": "1.0",
                "created_at": "2026-01-01T00:00:00",
                "db_uri": "postgresql://localhost/testdb",
                "tables": [{"name": "users", "row_count": 1}],
            },
            "data": {
                "users": [{"id": 1, "name": "Test User", "email": "test@example.com"}]
            },
        }

        # Write backup file
        backup_file = tmp_path / "backup.json"
        backup_file.write_text(json.dumps(backup_data))

        # Create mock DB
        db = MagicMock()
        db.tables = ["users"]
        users_table = MagicMock()
        users_table.fields = ["id", "name", "email"]
        db.__getitem__.return_value = users_table

        return db, {"file": backup_file, "data": backup_data}

    def test_restore_backup_local(
        self, tmp_path: Path, backup_db: tuple[MagicMock, dict]
    ) -> None:
        """Test local backup restore."""
        db, backup_info = backup_db

        # Create metadata
        metadata_file = backup_info["file"].with_suffix(".meta")
        metadata = {
            "backup_name": "test",
            "checksum": "abc123",
            "compressed": False,
        }
        metadata_file.write_text(json.dumps(metadata))

        with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
            manager = BackupManager(db, backup_dir=str(tmp_path))

            # Mock checksum to pass verification
            with patch.object(manager, "_calculate_checksum", return_value="abc123"):
                result = manager.restore_backup(str(backup_info["file"]))

                assert result["total_rows_restored"] == 1
                assert len(result["tables_restored"]) == 1
                db.commit.assert_called()


class TestBackupScheduling:
    """Test backup scheduling."""

    def test_schedule_backup(self, tmp_path: Path) -> None:
        """Test backup scheduling."""
        db = _create_backup_mock_db()
        with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
            manager = BackupManager(db, backup_dir=str(tmp_path))

            schedule_id = manager.schedule_backup("0 2 * * *")

            assert schedule_id.startswith("schedule_")


def test_backup_checksum_verification(tmp_path: Path) -> None:
    """Test that backup checksum is calculated correctly."""
    db = _create_backup_mock_db()
    with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
        manager = BackupManager(db, backup_dir=str(tmp_path))
        result = manager.create_backup(backup_name="checksum_test", compress=False)

        # Checksum should be a valid hex string
        assert len(result["checksum"]) == 64
        assert all(c in "0123456789abcdef" for c in result["checksum"])


def test_backup_metadata_structure(tmp_path: Path) -> None:
    """Test that backup metadata has correct structure."""
    db = _create_backup_mock_db()
    with patch.dict("os.environ", {"BACKUP_S3_ENABLED": "false"}):
        manager = BackupManager(db, backup_dir=str(tmp_path))
        result = manager.create_backup(backup_name="metadata_test", compress=False)

        required_keys = [
            "backup_name",
            "file_path",
            "created_at",
            "compressed",
            "encrypted",
            "checksum",
            "size_bytes",
            "table_count",
            "total_rows",
        ]

        for key in required_keys:
            assert key in result, f"Missing key: {key}"
