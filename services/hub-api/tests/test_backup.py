"""
Tests for backup/__init__.py — BackupManager and S3Config.

backup/__init__.py does NOT create a module-level instance (unlike audit),
so we can import it cleanly after patching `database.get_db`.
"""
import gzip
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call, mock_open

import pytest

# ---------------------------------------------------------------------------
# Pre-patch: database must be patchable before backup is imported.
# backup/__init__.py imports from database at module load time, so we patch
# database.get_db and database.get_database_uri before the first import.
# penguin_dal is a real installed package — do NOT mock it at module level.
# ---------------------------------------------------------------------------

_mock_db_pre = MagicMock()
_mock_db_pre.tables = {}
_mock_db_pre.commit = MagicMock()

# Ensure backup is imported with mocked database
if "backup" not in sys.modules:
    with patch("database.get_db", return_value=_mock_db_pre), \
         patch("database.get_database_uri", return_value="postgresql://user:pass@localhost/db"):
        from backup import BackupManager, S3Config, backup_cli
else:
    from backup import BackupManager, S3Config, backup_cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db(tables=None):
    """Build a mock database whose .tables is a dict of {name: sa_table_mock}."""
    db = MagicMock()

    if tables is None:
        tables = {}

    # Build per-table SA table mocks
    sa_tables = {}
    for tname in tables:
        sa_tbl = MagicMock()
        sa_tbl.columns = MagicMock()
        sa_tbl.columns.keys = MagicMock(return_value=list(tables[tname]))
        # Make columns[field].type behave like a string
        def _make_col(col_names):
            col_dict = {}
            for cn in col_names:
                col_mock = MagicMock()
                col_mock.type = MagicMock()
                col_mock.type.__str__ = lambda self: "VARCHAR"
                col_dict[cn] = col_mock
            return col_dict
        col_dict = _make_col(tables[tname])
        sa_tbl.columns.__getitem__ = lambda self, k, d=col_dict: d[k]
        sa_tables[tname] = sa_tbl

    db.tables = sa_tables

    # table proxy: db.<table_name>
    for tname in tables:
        tbl_proxy = MagicMock()
        tbl_proxy.insert = MagicMock(return_value=1)
        setattr(db, tname, tbl_proxy)

    # db(query).select() / .delete()
    query_result = MagicMock()
    query_result.select = MagicMock(return_value=[])
    query_result.delete = MagicMock(return_value=0)
    db.__call__ = MagicMock(return_value=query_result)
    db.commit = MagicMock()
    return db


def _make_manager(tmp_path, s3_enabled=False):
    """Create a BackupManager pointing at a temp directory, S3 off by default."""
    with patch.dict(os.environ, {"BACKUP_S3_ENABLED": "true" if s3_enabled else "false"}, clear=False):
        mgr = BackupManager.__new__(BackupManager)
        mgr.backup_dir = Path(tmp_path)
        mgr.s3_config = S3Config()
        mgr.s3_client = None
    return mgr


# ---------------------------------------------------------------------------
# S3Config tests
# ---------------------------------------------------------------------------

class TestS3Config:
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove relevant env vars to get defaults
            keys = [
                "BACKUP_S3_ENABLED", "BACKUP_S3_ENDPOINT_URL", "BACKUP_S3_BUCKET",
                "BACKUP_S3_REGION", "BACKUP_S3_ACCESS_KEY", "BACKUP_S3_SECRET_KEY",
                "BACKUP_S3_PREFIX", "BACKUP_S3_USE_SSL", "BACKUP_S3_VERIFY_SSL",
            ]
            env_overrides = {k: "" for k in keys}
            env_overrides["BACKUP_S3_ENABLED"] = "false"
            env_overrides["BACKUP_S3_BUCKET"] = "tobogganing-backups"
            env_overrides["BACKUP_S3_REGION"] = "us-east-1"
            env_overrides["BACKUP_S3_PREFIX"] = "backups/"
            env_overrides["BACKUP_S3_USE_SSL"] = "true"
            env_overrides["BACKUP_S3_VERIFY_SSL"] = "true"
            with patch.dict(os.environ, env_overrides):
                cfg = S3Config()
        assert cfg.enabled is False
        assert cfg.bucket == "tobogganing-backups"
        assert cfg.region == "us-east-1"
        assert cfg.prefix == "backups/"
        assert cfg.use_ssl is True
        assert cfg.verify_ssl is True

    def test_enabled_from_env(self):
        with patch.dict(os.environ, {"BACKUP_S3_ENABLED": "true"}):
            cfg = S3Config()
        assert cfg.enabled is True

    def test_custom_bucket_and_region(self):
        with patch.dict(os.environ, {"BACKUP_S3_BUCKET": "my-bucket", "BACKUP_S3_REGION": "eu-west-1"}):
            cfg = S3Config()
        assert cfg.bucket == "my-bucket"
        assert cfg.region == "eu-west-1"

    def test_ssl_disabled(self):
        with patch.dict(os.environ, {"BACKUP_S3_USE_SSL": "false", "BACKUP_S3_VERIFY_SSL": "false"}):
            cfg = S3Config()
        assert cfg.use_ssl is False
        assert cfg.verify_ssl is False

    def test_access_key_secret_key(self):
        with patch.dict(os.environ, {"BACKUP_S3_ACCESS_KEY": "AKID", "BACKUP_S3_SECRET_KEY": "secret"}):
            cfg = S3Config()
        assert cfg.access_key == "AKID"
        assert cfg.secret_key == "secret"

    def test_endpoint_url(self):
        with patch.dict(os.environ, {"BACKUP_S3_ENDPOINT_URL": "http://minio:9000"}):
            cfg = S3Config()
        assert cfg.endpoint_url == "http://minio:9000"


# ---------------------------------------------------------------------------
# BackupManager.__init__ tests
# ---------------------------------------------------------------------------

class TestBackupManagerInit:
    def test_creates_backup_dir(self, tmp_path):
        target = tmp_path / "new_subdir"
        with patch.dict(os.environ, {"BACKUP_S3_ENABLED": "false"}):
            mgr = BackupManager(backup_dir=str(target))
        assert target.exists()

    def test_s3_disabled_no_client(self, tmp_path):
        with patch.dict(os.environ, {"BACKUP_S3_ENABLED": "false"}):
            mgr = BackupManager(backup_dir=str(tmp_path))
        assert mgr.s3_client is None

    def test_s3_enabled_calls_init(self, tmp_path):
        with patch.dict(os.environ, {"BACKUP_S3_ENABLED": "true"}):
            with patch.object(BackupManager, "_init_s3_client") as mock_init:
                mgr = BackupManager(backup_dir=str(tmp_path))
                mock_init.assert_called_once()

    def test_s3_unavailable_raises(self, tmp_path):
        with patch.dict(os.environ, {"BACKUP_S3_ENABLED": "true"}):
            with patch("backup.S3_AVAILABLE", False):
                with pytest.raises(ImportError, match="boto3"):
                    mgr = BackupManager(backup_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# BackupManager._init_s3_client tests
# ---------------------------------------------------------------------------

class TestInitS3Client:
    def test_init_with_credentials(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.access_key = "AKID"
        mgr.s3_config.secret_key = "SECRET"
        mgr.s3_config.endpoint_url = None
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("backup.S3_AVAILABLE", True), \
             patch("backup.boto3") as mock_boto3, \
             patch.object(mgr, "_ensure_s3_bucket"):
            mock_boto3.Session.return_value = mock_session
            mgr._init_s3_client()

        assert mgr.s3_client == mock_client
        mock_boto3.Session.assert_called_once_with(
            aws_access_key_id="AKID",
            aws_secret_access_key="SECRET"
        )

    def test_init_without_credentials(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.access_key = None
        mgr.s3_config.secret_key = None
        mgr.s3_config.endpoint_url = None
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("backup.S3_AVAILABLE", True), \
             patch("backup.boto3") as mock_boto3, \
             patch.object(mgr, "_ensure_s3_bucket"):
            mock_boto3.Session.return_value = mock_session
            mgr._init_s3_client()

        mock_boto3.Session.assert_called_once_with()

    def test_init_with_endpoint_url(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.access_key = None
        mgr.s3_config.secret_key = None
        mgr.s3_config.endpoint_url = "http://minio:9000"
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("backup.S3_AVAILABLE", True), \
             patch("backup.boto3") as mock_boto3, \
             patch.object(mgr, "_ensure_s3_bucket"):
            mock_boto3.Session.return_value = mock_session
            mgr._init_s3_client()

        call_kwargs = mock_session.client.call_args[1]
        assert call_kwargs["endpoint_url"] == "http://minio:9000"

    def test_s3_not_available_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with patch("backup.S3_AVAILABLE", False):
            with pytest.raises(ImportError):
                mgr._init_s3_client()

    def test_no_credentials_error_reraises(self, tmp_path):
        from botocore.exceptions import NoCredentialsError
        mgr = _make_manager(tmp_path)
        mgr.s3_config.access_key = None
        mgr.s3_config.secret_key = None
        mgr.s3_config.endpoint_url = None

        with patch("backup.S3_AVAILABLE", True), \
             patch("backup.boto3") as mock_boto3:
            mock_boto3.Session.side_effect = NoCredentialsError()
            with pytest.raises(NoCredentialsError):
                mgr._init_s3_client()

    def test_generic_exception_reraises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.access_key = None
        mgr.s3_config.secret_key = None
        mgr.s3_config.endpoint_url = None

        with patch("backup.S3_AVAILABLE", True), \
             patch("backup.boto3") as mock_boto3:
            mock_boto3.Session.side_effect = RuntimeError("connection refused")
            with pytest.raises(RuntimeError):
                mgr._init_s3_client()


# ---------------------------------------------------------------------------
# BackupManager._ensure_s3_bucket tests
# ---------------------------------------------------------------------------

class TestEnsureS3Bucket:
    def test_bucket_exists(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()
        mgr.s3_client.head_bucket.return_value = {}
        # Should not raise
        mgr._ensure_s3_bucket()
        mgr.s3_client.head_bucket.assert_called_once()

    def test_bucket_not_found_creates_us_east_1(self, tmp_path):
        from botocore.exceptions import ClientError
        mgr = _make_manager(tmp_path)
        mgr.s3_config.region = "us-east-1"
        mgr.s3_config.bucket = "my-bucket"
        mgr.s3_client = MagicMock()
        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mgr.s3_client.head_bucket.side_effect = ClientError(error_response, "HeadBucket")
        mgr._ensure_s3_bucket()
        mgr.s3_client.create_bucket.assert_called_once_with(Bucket="my-bucket")

    def test_bucket_not_found_creates_other_region(self, tmp_path):
        from botocore.exceptions import ClientError
        mgr = _make_manager(tmp_path)
        mgr.s3_config.region = "eu-west-1"
        mgr.s3_config.bucket = "my-bucket"
        mgr.s3_client = MagicMock()
        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mgr.s3_client.head_bucket.side_effect = ClientError(error_response, "HeadBucket")
        mgr._ensure_s3_bucket()
        mgr.s3_client.create_bucket.assert_called_once_with(
            Bucket="my-bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"}
        )

    def test_create_bucket_error_reraises(self, tmp_path):
        from botocore.exceptions import ClientError
        mgr = _make_manager(tmp_path)
        mgr.s3_config.region = "us-east-1"
        mgr.s3_config.bucket = "my-bucket"
        mgr.s3_client = MagicMock()
        not_found = ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket")
        create_error = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "CreateBucket")
        mgr.s3_client.head_bucket.side_effect = not_found
        mgr.s3_client.create_bucket.side_effect = create_error
        with pytest.raises(ClientError):
            mgr._ensure_s3_bucket()

    def test_non_404_error_reraises(self, tmp_path):
        from botocore.exceptions import ClientError
        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()
        error_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
        mgr.s3_client.head_bucket.side_effect = ClientError(error_response, "HeadBucket")
        with pytest.raises(ClientError):
            mgr._ensure_s3_bucket()


# ---------------------------------------------------------------------------
# BackupManager._sanitize_db_uri tests
# ---------------------------------------------------------------------------

class TestSanitizeDbUri:
    def test_removes_password(self, tmp_path):
        mgr = _make_manager(tmp_path)
        uri = "postgresql://myuser:mysecret@localhost:5432/mydb"
        result = mgr._sanitize_db_uri(uri)
        assert "mysecret" not in result
        assert "***" in result

    def test_no_credentials_unchanged(self, tmp_path):
        mgr = _make_manager(tmp_path)
        uri = "sqlite:///./test.db"
        result = mgr._sanitize_db_uri(uri)
        # No credentials to strip; result keeps the URI intact
        assert "sqlite" in result

    def test_various_credentials(self, tmp_path):
        mgr = _make_manager(tmp_path)
        uri = "mysql://admin:p@ssw0rd!@db.example.com/prod"
        result = mgr._sanitize_db_uri(uri)
        assert "p@ssw0rd!" not in result


# ---------------------------------------------------------------------------
# BackupManager._calculate_checksum tests
# ---------------------------------------------------------------------------

class TestCalculateChecksum:
    def test_returns_sha256_hex(self, tmp_path):
        mgr = _make_manager(tmp_path)
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        result = mgr._calculate_checksum(f)
        import hashlib
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_different_files_different_checksum(self, tmp_path):
        mgr = _make_manager(tmp_path)
        f1 = tmp_path / "f1.bin"
        f2 = tmp_path / "f2.bin"
        f1.write_bytes(b"content one")
        f2.write_bytes(b"content two")
        assert mgr._calculate_checksum(f1) != mgr._calculate_checksum(f2)

    def test_empty_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        result = mgr._calculate_checksum(f)
        import hashlib
        assert result == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# BackupManager._encrypt_file / _decrypt_file tests (placeholder stubs)
# ---------------------------------------------------------------------------

class TestEncryptDecryptPlaceholders:
    def test_encrypt_returns_same_path(self, tmp_path):
        mgr = _make_manager(tmp_path)
        f = tmp_path / "data.json.gz"
        f.write_bytes(b"data")
        result = mgr._encrypt_file(f, "secret")
        assert result == f

    def test_decrypt_returns_same_path(self, tmp_path):
        mgr = _make_manager(tmp_path)
        f = tmp_path / "data.json.gz.enc"
        f.write_bytes(b"data")
        result = mgr._decrypt_file(f, "secret")
        assert result == f


# ---------------------------------------------------------------------------
# BackupManager.create_backup tests
# ---------------------------------------------------------------------------

class TestCreateBackup:
    def _setup_db_for_backup(self, rows=None):
        """Build a mock db with a 'hosts' table that returns specified rows."""
        if rows is None:
            rows = []
        db = MagicMock()
        sa_tbl = MagicMock()
        sa_tbl.columns = MagicMock()
        sa_tbl.columns.keys = MagicMock(return_value=["id", "name", "created_at"])
        db.tables = {"hosts": sa_tbl}
        # db(query).select() returns rows — use return_value (not __call__) on MagicMock
        query_result = MagicMock()
        query_result.select = MagicMock(return_value=rows)
        db.return_value = query_result
        db.commit = MagicMock()
        return db

    def _make_row(self, data):
        row = MagicMock()
        row.get = MagicMock(side_effect=lambda k: data.get(k))
        return row

    def test_create_uncompressed_no_s3(self, tmp_path):
        db = self._setup_db_for_backup(
            rows=[self._make_row({"id": 1, "name": "host1", "created_at": None})]
        )
        mgr = _make_manager(tmp_path)

        mock_query_cls = MagicMock()
        mock_query_cls.return_value = MagicMock()

        with patch("database.get_db", return_value=db), \
             patch("database.get_database_uri", return_value="sqlite:///test.db"), \
             patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", mock_query_cls):
            meta = mgr.create_backup(backup_name="test_backup_001", compress=False)

        assert meta["backup_name"] == "test_backup_001"
        assert meta["compressed"] is False
        assert meta["encrypted"] is False
        assert "checksum" in meta
        assert meta["s3_info"] is None
        backup_file = Path(meta["file_path"])
        assert backup_file.exists()

    def test_create_compressed(self, tmp_path):
        db = self._setup_db_for_backup(rows=[])
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()):
            meta = mgr.create_backup(backup_name="compressed_backup", compress=True)

        assert meta["compressed"] is True
        backup_file = Path(meta["file_path"])
        assert backup_file.suffix == ".gz"
        assert backup_file.exists()
        # Verify it is actually gzip
        with gzip.open(backup_file, "rb") as f:
            content = json.loads(f.read())
        assert "metadata" in content
        assert "data" in content

    def test_create_auto_name(self, tmp_path):
        db = self._setup_db_for_backup(rows=[])
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()):
            meta = mgr.create_backup(compress=False)

        assert meta["backup_name"].startswith("tobogganing_backup_")

    def test_create_encrypt_without_key_raises(self, tmp_path):
        db = self._setup_db_for_backup(rows=[])
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()):
            with pytest.raises(ValueError, match="Encryption key"):
                mgr.create_backup(backup_name="enc_backup", encrypt=True, encryption_key=None)

    def test_create_with_encryption_key(self, tmp_path):
        db = self._setup_db_for_backup(rows=[])
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()):
            meta = mgr.create_backup(
                backup_name="enc_backup", compress=False,
                encrypt=True, encryption_key="mysecret"
            )

        assert meta["encrypted"] is True

    def test_create_with_datetime_row_values(self, tmp_path):
        """datetime values in rows must be serialised to isoformat strings."""
        now = datetime(2025, 1, 15, 12, 0, 0)
        row = MagicMock()
        row.get = MagicMock(side_effect=lambda k: now if k == "created_at" else k)
        db = self._setup_db_for_backup(rows=[row])
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()):
            meta = mgr.create_backup(backup_name="dt_backup", compress=False)

        backup_file = Path(meta["file_path"])
        with open(backup_file) as f:
            data = json.load(f)
        row_data = data["data"]["hosts"][0]
        assert row_data["created_at"] == now.isoformat()

    def test_create_uploads_to_s3_when_forced(self, tmp_path):
        db = self._setup_db_for_backup(rows=[])
        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()

        fake_s3_info = {"bucket": "b", "s3_key": "k", "etag": "e", "size_bytes": 10, "uploaded_at": "now"}
        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()), \
             patch.object(mgr, "_upload_backup_to_s3", return_value=fake_s3_info) as mock_upload, \
             patch.object(mgr, "_upload_metadata_to_s3") as mock_meta_upload:
            meta = mgr.create_backup(backup_name="s3_backup", compress=False, upload_to_s3=True)

        assert meta["s3_info"] == fake_s3_info
        mock_upload.assert_called_once()
        mock_meta_upload.assert_called_once()

    def test_create_skips_s3_when_upload_false(self, tmp_path):
        db = self._setup_db_for_backup(rows=[])
        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()), \
             patch.object(mgr, "_upload_backup_to_s3") as mock_upload:
            meta = mgr.create_backup(backup_name="no_s3_backup", compress=False, upload_to_s3=False)

        mock_upload.assert_not_called()
        assert meta["s3_info"] is None

    def test_create_metadata_file_written(self, tmp_path):
        db = self._setup_db_for_backup(rows=[])
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()):
            meta = mgr.create_backup(backup_name="meta_test", compress=False)

        backup_file = Path(meta["file_path"])
        meta_file = backup_file.with_suffix(".meta")
        assert meta_file.exists()

    def test_create_empty_tables(self, tmp_path):
        """Backup with no tables results in empty data dict."""
        db = MagicMock()
        db.tables = {}
        db.commit = MagicMock()
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch("backup.get_database_uri", return_value="sqlite:///test.db"), \
             patch("penguin_dal.query.Query", MagicMock()):
            meta = mgr.create_backup(backup_name="empty_backup", compress=False)

        assert meta["table_count"] == 0
        assert meta["total_rows"] == 0

    def test_create_raises_on_db_error(self, tmp_path):
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", side_effect=RuntimeError("Database not initialized.")):
            with pytest.raises(RuntimeError, match="Database not initialized"):
                mgr.create_backup(backup_name="fail_backup")


# ---------------------------------------------------------------------------
# BackupManager.restore_backup tests
# ---------------------------------------------------------------------------

class TestRestoreBackup:
    def _write_backup_file(self, tmp_path, name, data, compress=False):
        """Write a backup JSON (or .gz) file and return its path."""
        json_str = json.dumps(data)
        if compress:
            fpath = tmp_path / f"{name}.json.gz"
            with gzip.open(fpath, "wb") as f:
                f.write(json_str.encode("utf-8"))
        else:
            fpath = tmp_path / f"{name}.json"
            fpath.write_text(json_str)
        return fpath

    def _valid_backup_data(self):
        return {
            "metadata": {"version": "1.0", "tables": []},
            "data": {}
        }

    def test_restore_plain_json(self, tmp_path):
        data = self._valid_backup_data()
        fpath = self._write_backup_file(tmp_path, "restore_test", data, compress=False)

        db = MagicMock()
        db.tables = {}

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            stats = mgr.restore_backup(str(fpath), verify_checksum=False)

        assert stats["total_rows_restored"] == 0
        assert "completed_at" in stats

    def test_restore_gzip(self, tmp_path):
        data = self._valid_backup_data()
        fpath = self._write_backup_file(tmp_path, "gz_restore", data, compress=True)

        db = MagicMock()
        db.tables = {}

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            stats = mgr.restore_backup(str(fpath), verify_checksum=False)

        assert stats["total_rows_restored"] == 0

    def test_restore_missing_file_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.restore_backup("/nonexistent/path/backup.json", verify_checksum=False)

    def test_restore_invalid_format_raises(self, tmp_path):
        """Backup file missing 'metadata' or 'data' key should raise ValueError."""
        fpath = tmp_path / "bad.json"
        fpath.write_text(json.dumps({"wrong": "format"}))

        db = MagicMock()
        db.tables = {}

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            with pytest.raises(ValueError, match="Invalid backup file format"):
                mgr.restore_backup(str(fpath), verify_checksum=False)

    def test_restore_checksum_mismatch_raises(self, tmp_path):
        data = self._valid_backup_data()
        fpath = self._write_backup_file(tmp_path, "cs_test", data, compress=False)

        # Write a metadata file with wrong checksum
        meta_file = fpath.with_suffix(".meta")
        meta_file.write_text(json.dumps({"checksum": "badchecksum0000"}))

        db = MagicMock()
        db.tables = {}

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            with pytest.raises(ValueError, match="checksum"):
                mgr.restore_backup(str(fpath), verify_checksum=True)

    def test_restore_checksum_match_succeeds(self, tmp_path):
        data = self._valid_backup_data()
        fpath = self._write_backup_file(tmp_path, "cs_ok", data, compress=False)

        import hashlib
        checksum = hashlib.sha256(fpath.read_bytes()).hexdigest()
        meta_file = fpath.with_suffix(".meta")
        meta_file.write_text(json.dumps({"checksum": checksum}))

        db = MagicMock()
        db.tables = {}

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            stats = mgr.restore_backup(str(fpath), verify_checksum=True)

        assert stats["total_rows_restored"] == 0

    def test_restore_skips_unknown_tables(self, tmp_path):
        """Tables in backup that don't exist in current schema are skipped with an error note."""
        data = {
            "metadata": {"version": "1.0"},
            "data": {"missing_table": [{"id": 1}]}
        }
        fpath = self._write_backup_file(tmp_path, "skip_test", data, compress=False)

        db = MagicMock()
        db.tables = {}  # No tables in current schema

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            stats = mgr.restore_backup(str(fpath), verify_checksum=False)

        assert any("missing_table" in e for e in stats["errors"])
        assert stats["total_rows_restored"] == 0

    def test_restore_inserts_rows(self, tmp_path):
        """Rows in backup that match current schema are inserted."""
        data = {
            "metadata": {"version": "1.0"},
            "data": {"hosts": [{"id": 1, "name": "host1"}]}
        }
        fpath = self._write_backup_file(tmp_path, "rows_test", data, compress=False)

        # Build db with 'hosts' table
        db = MagicMock()
        sa_tbl = MagicMock()
        sa_tbl.columns = MagicMock()
        sa_tbl.columns.keys = MagicMock(return_value=["id", "name"])
        col_id = MagicMock()
        col_id.type = MagicMock()
        col_id.type.__str__ = lambda self: "INTEGER"
        col_name = MagicMock()
        col_name.type = MagicMock()
        col_name.type.__str__ = lambda self: "VARCHAR"
        col_dict = {"id": col_id, "name": col_name}
        sa_tbl.columns.__getitem__ = lambda self, k, d=col_dict: d[k]
        db.tables = {"hosts": sa_tbl}

        hosts_proxy = MagicMock()
        hosts_proxy.insert = MagicMock(return_value=1)
        db.hosts = hosts_proxy

        query_result = MagicMock()
        query_result.delete = MagicMock(return_value=0)
        db.return_value = query_result
        db.commit = MagicMock()

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            stats = mgr.restore_backup(str(fpath), verify_checksum=False)

        assert stats["total_rows_restored"] == 1
        hosts_proxy.insert.assert_called_once_with(id=1, name="host1")

    def test_restore_converts_datetime_strings(self, tmp_path):
        """Datetime strings in DATETIME columns must be converted to datetime objects."""
        data = {
            "metadata": {"version": "1.0"},
            "data": {"events": [{"id": 1, "created_at": "2025-01-15T12:00:00"}]}
        }
        fpath = self._write_backup_file(tmp_path, "dt_restore", data, compress=False)

        db = MagicMock()
        sa_tbl = MagicMock()
        sa_tbl.columns = MagicMock()
        sa_tbl.columns.keys = MagicMock(return_value=["id", "created_at"])
        col_id = MagicMock()
        col_id.type = MagicMock()
        col_id.type.__str__ = lambda self: "INTEGER"
        col_dt = MagicMock()
        col_dt.type = MagicMock()
        col_dt.type.__str__ = lambda self: "DATETIME"
        col_dict = {"id": col_id, "created_at": col_dt}
        sa_tbl.columns.__getitem__ = lambda self, k, d=col_dict: d[k]
        db.tables = {"events": sa_tbl}

        events_proxy = MagicMock()
        events_proxy.insert = MagicMock(return_value=1)
        db.events = events_proxy

        query_result = MagicMock()
        query_result.delete = MagicMock(return_value=0)
        db.return_value = query_result

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            stats = mgr.restore_backup(str(fpath), verify_checksum=False)

        call_kwargs = events_proxy.insert.call_args[1]
        assert isinstance(call_kwargs["created_at"], datetime)

    def test_restore_drops_unknown_columns(self, tmp_path):
        """Columns in backup that don't exist in current schema are dropped."""
        data = {
            "metadata": {"version": "1.0"},
            "data": {"hosts": [{"id": 1, "name": "h1", "deprecated_field": "x"}]}
        }
        fpath = self._write_backup_file(tmp_path, "col_drop", data, compress=False)

        db = MagicMock()
        sa_tbl = MagicMock()
        sa_tbl.columns = MagicMock()
        sa_tbl.columns.keys = MagicMock(return_value=["id", "name"])
        col_id = MagicMock()
        col_id.type = MagicMock()
        col_id.type.__str__ = lambda self: "INTEGER"
        col_name = MagicMock()
        col_name.type = MagicMock()
        col_name.type.__str__ = lambda self: "VARCHAR"
        col_dict = {"id": col_id, "name": col_name}
        sa_tbl.columns.__getitem__ = lambda self, k, d=col_dict: d[k]
        db.tables = {"hosts": sa_tbl}

        hosts_proxy = MagicMock()
        db.hosts = hosts_proxy

        query_result = MagicMock()
        query_result.delete = MagicMock(return_value=0)
        db.return_value = query_result

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            mgr.restore_backup(str(fpath), verify_checksum=False)

        call_kwargs = hosts_proxy.insert.call_args[1]
        assert "deprecated_field" not in call_kwargs

    def test_restore_decrypt_without_key_raises(self, tmp_path):
        data = self._valid_backup_data()
        fpath = self._write_backup_file(tmp_path, "dec_test", data, compress=False)

        mgr = _make_manager(tmp_path)
        with pytest.raises(ValueError, match="Decryption key"):
            mgr.restore_backup(str(fpath), decrypt=True, decryption_key=None, verify_checksum=False)

    def test_restore_from_s3(self, tmp_path):
        """restore_backup with from_s3=True should download from S3 first."""
        data = self._valid_backup_data()
        fpath = self._write_backup_file(tmp_path, "s3_restore", data, compress=False)

        db = MagicMock()
        db.tables = {}

        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()

        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()), \
             patch.object(mgr, "_download_backup_from_s3", return_value=fpath) as mock_dl:
            stats = mgr.restore_backup("s3://bucket/key", from_s3=True, verify_checksum=False)

        mock_dl.assert_called_once_with("s3://bucket/key")
        assert stats["total_rows_restored"] == 0

    def test_restore_metadata_without_checksum_key(self, tmp_path):
        """Metadata file exists but has no 'checksum' key — checksum verification skipped."""
        data = {"metadata": {"version": "1.0"}, "data": {}}
        fpath = self._write_backup_file(tmp_path, "no_cs_meta", data, compress=False)

        # Write metadata without checksum key
        meta_file = fpath.with_suffix(".meta")
        meta_file.write_text(json.dumps({"backup_name": "no_cs_meta", "created_at": "2025-01-01"}))

        db = MagicMock()
        db.tables = {}

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db):
            stats = mgr.restore_backup(str(fpath), verify_checksum=True)

        # Should succeed without raising checksum error
        assert stats["total_rows_restored"] == 0

    def test_restore_table_error_recorded(self, tmp_path):
        """Errors during table restore are recorded in stats, not raised."""
        data = {
            "metadata": {"version": "1.0"},
            "data": {"hosts": [{"id": 1}]}
        }
        fpath = self._write_backup_file(tmp_path, "err_restore", data, compress=False)

        db = MagicMock()
        sa_tbl = MagicMock()
        sa_tbl.columns = MagicMock()
        sa_tbl.columns.keys = MagicMock(return_value=["id"])
        col_id = MagicMock()
        col_id.type = MagicMock()
        col_id.type.__str__ = lambda self: "INTEGER"
        sa_tbl.columns.__getitem__ = lambda self, k: col_id
        db.tables = {"hosts": sa_tbl}

        hosts_proxy = MagicMock()
        hosts_proxy.insert = MagicMock(side_effect=Exception("insert error"))
        db.hosts = hosts_proxy

        query_result = MagicMock()
        query_result.delete = MagicMock(return_value=0)
        db.return_value = query_result

        mgr = _make_manager(tmp_path)
        with patch("backup.get_db", return_value=db), \
             patch("penguin_dal.query.Query", MagicMock()):
            stats = mgr.restore_backup(str(fpath), verify_checksum=False)

        assert any("hosts" in e for e in stats["errors"])


# ---------------------------------------------------------------------------
# BackupManager.list_backups tests
# ---------------------------------------------------------------------------

class TestListBackups:
    def test_list_local_backups(self, tmp_path):
        mgr = _make_manager(tmp_path)

        # Write two metadata files
        meta1 = {"backup_name": "backup_001", "created_at": "2025-01-01T00:00:00"}
        meta2 = {"backup_name": "backup_002", "created_at": "2025-01-02T00:00:00"}
        (tmp_path / "backup_001.meta").write_text(json.dumps(meta1))
        (tmp_path / "backup_002.meta").write_text(json.dumps(meta2))

        result = mgr.list_backups(include_s3=False)
        names = {b["backup_name"] for b in result}
        assert names == {"backup_001", "backup_002"}

    def test_list_skips_bad_meta_files(self, tmp_path):
        mgr = _make_manager(tmp_path)
        (tmp_path / "corrupt.meta").write_text("not json {{{{")

        result = mgr.list_backups(include_s3=False)
        # Corrupt file is skipped; no exception raised
        assert result == []

    def test_list_deduplicates_preferring_s3(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()

        # Local backup
        meta = {"backup_name": "shared_backup", "created_at": "2025-01-01T00:00:00"}
        (tmp_path / "shared_backup.meta").write_text(json.dumps(meta))

        s3_backup_list = [
            {
                "backup_name": "shared_backup",
                "filename": "shared_backup.json",
                "s3_key": "backups/shared_backup/shared_backup.json",
                "size_bytes": 100,
                "last_modified": "2025-01-01T01:00:00",
                "storage_class": "STANDARD"
            }
        ]
        from botocore.exceptions import ClientError
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}
        mgr.s3_client.get_object = MagicMock(
            side_effect=ClientError(error_response, "GetObject")
        )

        with patch.object(mgr, "list_s3_backups", return_value=s3_backup_list):
            result = mgr.list_backups(include_s3=True)

        # Should have only one entry for shared_backup
        matching = [b for b in result if b.get("backup_name") == "shared_backup"]
        assert len(matching) == 1

    def test_list_no_s3_client_skips_s3(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_client = None

        (tmp_path / "local.meta").write_text(json.dumps({"backup_name": "local", "created_at": ""}))

        result = mgr.list_backups(include_s3=True)
        assert len(result) == 1
        assert result[0]["backup_name"] == "local"

    def test_list_s3_with_metadata(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()
        mgr.s3_config.bucket = "my-bucket"
        mgr.s3_config.prefix = "backups/"

        s3_backup_list = [
            {
                "backup_name": "s3_only_backup",
                "filename": "s3_only_backup.json",
                "s3_key": "backups/s3_only_backup/s3_only_backup.json",
                "size_bytes": 200,
                "last_modified": "2025-02-01T00:00:00",
                "storage_class": "STANDARD"
            }
        ]

        full_meta = {"backup_name": "s3_only_backup", "created_at": "2025-02-01T00:00:00", "size_bytes": 200}
        meta_body = MagicMock()
        meta_body.read.return_value = json.dumps(full_meta).encode("utf-8")
        mgr.s3_client.get_object = MagicMock(return_value={"Body": meta_body})

        with patch.object(mgr, "list_s3_backups", return_value=s3_backup_list):
            result = mgr.list_backups(include_s3=True)

        s3_entries = [b for b in result if b.get("storage_location") == "s3"]
        assert len(s3_entries) == 1
        assert s3_entries[0]["backup_name"] == "s3_only_backup"


# ---------------------------------------------------------------------------
# BackupManager.delete_backup tests
# ---------------------------------------------------------------------------

class TestDeleteBackup:
    def test_delete_existing_backup(self, tmp_path):
        mgr = _make_manager(tmp_path)

        # Create a fake backup file
        backup_file = tmp_path / "my_backup.json"
        backup_file.write_text("{}")
        meta_file = tmp_path / "my_backup.meta"
        meta_file.write_text("{}")

        result = mgr.delete_backup("my_backup")
        assert result is True
        assert not backup_file.exists()
        assert not meta_file.exists()

    def test_delete_nonexistent_returns_false(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.delete_backup("nonexistent_backup")
        assert result is False

    def test_delete_only_matching_files(self, tmp_path):
        mgr = _make_manager(tmp_path)

        keep_file = tmp_path / "other_backup.json"
        keep_file.write_text("{}")
        del_file = tmp_path / "target_backup.json"
        del_file.write_text("{}")

        mgr.delete_backup("target_backup")
        assert keep_file.exists()
        assert not del_file.exists()


# ---------------------------------------------------------------------------
# BackupManager.schedule_backup tests
# ---------------------------------------------------------------------------

class TestScheduleBackup:
    def test_returns_schedule_id(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.schedule_backup("0 2 * * *")
        assert result.startswith("schedule_")

    def test_kwargs_accepted(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.schedule_backup("*/5 * * * *", compress=True, encrypt=False)
        assert result.startswith("schedule_")


# ---------------------------------------------------------------------------
# BackupManager S3 upload/download/list/delete tests
# ---------------------------------------------------------------------------

class TestS3Operations:
    def test_upload_backup_to_s3(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()

        head_response = {"ETag": '"abc123"', "ContentLength": 500}
        mgr.s3_client.head_object.return_value = head_response

        backup_file = tmp_path / "backup.json"
        backup_file.write_text('{"data": "test"}')

        result = mgr._upload_backup_to_s3(backup_file, "backup")

        assert result["bucket"] == "test-bucket"
        assert "s3_key" in result
        assert result["etag"] == "abc123"
        mgr.s3_client.upload_fileobj.assert_called_once()

    def test_upload_backup_to_s3_raises_on_error(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()
        mgr.s3_client.upload_fileobj.side_effect = Exception("upload failed")

        backup_file = tmp_path / "backup.json"
        backup_file.write_text("{}")

        with pytest.raises(Exception, match="upload failed"):
            mgr._upload_backup_to_s3(backup_file, "backup")

    def test_upload_metadata_to_s3(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()

        meta_file = tmp_path / "backup.meta"
        meta_file.write_text('{"backup_name": "backup"}')

        mgr._upload_metadata_to_s3(meta_file, "backup")
        mgr.s3_client.upload_fileobj.assert_called_once()

    def test_upload_metadata_to_s3_warning_on_error(self, tmp_path):
        """Metadata upload failure logs a warning but does not raise."""
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()
        mgr.s3_client.upload_fileobj.side_effect = Exception("s3 error")

        meta_file = tmp_path / "backup.meta"
        meta_file.write_text("{}")

        # Should not raise
        mgr._upload_metadata_to_s3(meta_file, "backup")

    def test_download_backup_from_s3(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_client = MagicMock()

        result = mgr._download_backup_from_s3("backups/backup/backup.json")

        mgr.s3_client.download_file.assert_called_once()
        assert isinstance(result, Path)

    def test_download_backup_from_s3_raises_on_error(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_client = MagicMock()
        mgr.s3_client.download_file.side_effect = Exception("download error")

        with pytest.raises(Exception, match="download error"):
            mgr._download_backup_from_s3("backups/backup/backup.json")

    def test_list_s3_backups_no_client(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_client = None
        result = mgr.list_s3_backups()
        assert result == []

    def test_list_s3_backups_with_results(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()

        # Simulate paginator
        page = {
            "Contents": [
                {
                    "Key": "backups/backup_001/backup_001.json",
                    "Size": 1024,
                    "LastModified": datetime(2025, 1, 1, 12, 0, 0),
                    "StorageClass": "STANDARD"
                },
                {
                    "Key": "backups/backup_001/",  # directory, should be skipped
                    "Size": 0,
                    "LastModified": datetime(2025, 1, 1, 0, 0, 0),
                    "StorageClass": "STANDARD"
                },
                {
                    "Key": "backups/backup_001/backup_001.meta",  # .meta, should be skipped
                    "Size": 100,
                    "LastModified": datetime(2025, 1, 1, 12, 0, 0),
                    "StorageClass": "STANDARD"
                }
            ]
        }
        paginator = MagicMock()
        paginator.paginate.return_value = [page]
        mgr.s3_client.get_paginator.return_value = paginator

        result = mgr.list_s3_backups()
        assert len(result) == 1
        assert result[0]["backup_name"] == "backup_001"
        assert result[0]["filename"] == "backup_001.json"

    def test_list_s3_backups_empty_page(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()

        page = {}  # No 'Contents' key
        paginator = MagicMock()
        paginator.paginate.return_value = [page]
        mgr.s3_client.get_paginator.return_value = paginator

        result = mgr.list_s3_backups()
        assert result == []

    def test_list_s3_backups_error_returns_empty(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()
        mgr.s3_client.get_paginator.side_effect = Exception("s3 error")

        result = mgr.list_s3_backups()
        assert result == []

    def test_delete_s3_backup_no_client(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_client = None
        result = mgr.delete_s3_backup("some_backup")
        assert result is False

    def test_delete_s3_backup_no_contents(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()
        mgr.s3_client.list_objects_v2.return_value = {}  # No Contents

        result = mgr.delete_s3_backup("empty_backup")
        assert result is False

    def test_delete_s3_backup_success(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()
        mgr.s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "backups/my_backup/my_backup.json"},
                {"Key": "backups/my_backup/my_backup.meta"},
            ]
        }

        result = mgr.delete_s3_backup("my_backup")
        assert result is True
        mgr.s3_client.delete_objects.assert_called_once()

    def test_delete_s3_backup_error_returns_false(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()
        mgr.s3_client.list_objects_v2.side_effect = Exception("s3 error")

        result = mgr.delete_s3_backup("some_backup")
        assert result is False


# ---------------------------------------------------------------------------
# backup_cli tests
# ---------------------------------------------------------------------------

class TestBackupCli:
    def _run_cli(self, args, mgr=None):
        """Run backup_cli with given argv, optionally injecting a mock manager."""
        if mgr is None:
            mgr = MagicMock()

        with patch("sys.argv", ["backup"] + args), \
             patch("backup.BackupManager", return_value=mgr):
            backup_cli()

    def test_cli_create(self, tmp_path, capsys):
        mgr = MagicMock()
        mgr.create_backup.return_value = {"file_path": "/tmp/backup.json", "s3_info": None}
        self._run_cli(["create", "--name", "test", "--compress"], mgr)
        mgr.create_backup.assert_called_once()

    def test_cli_create_with_s3(self, tmp_path, capsys):
        mgr = MagicMock()
        mgr.create_backup.return_value = {
            "file_path": "/tmp/backup.json",
            "s3_info": {"s3_key": "backups/test/test.json"}
        }
        self._run_cli(["create", "--name", "test", "--s3"], mgr)
        out = capsys.readouterr().out
        assert "backups/test/test.json" in out

    def test_cli_restore(self, capsys):
        mgr = MagicMock()
        mgr.restore_backup.return_value = {"total_rows_restored": 42, "errors": []}
        self._run_cli(["restore", "/tmp/backup.json"], mgr)
        out = capsys.readouterr().out
        assert "42" in out

    def test_cli_list_all(self, capsys):
        mgr = MagicMock()
        mgr.list_backups.return_value = [
            {"backup_name": "b1", "created_at": "2025-01-01", "storage_location": "local"}
        ]
        self._run_cli(["list"], mgr)
        out = capsys.readouterr().out
        assert "b1" in out

    def test_cli_list_local_only(self, capsys):
        mgr = MagicMock()
        mgr.list_backups.return_value = []
        self._run_cli(["list", "--local-only"], mgr)
        mgr.list_backups.assert_called_once_with(include_s3=False)

    def test_cli_list_s3_only(self, capsys):
        mgr = MagicMock()
        mgr.list_s3_backups.return_value = []
        self._run_cli(["list", "--s3-only"], mgr)
        mgr.list_s3_backups.assert_called_once()

    def test_cli_delete_local(self, capsys):
        mgr = MagicMock()
        mgr.delete_backup.return_value = True
        self._run_cli(["delete", "old_backup"], mgr)
        out = capsys.readouterr().out
        assert "deleted" in out.lower()

    def test_cli_delete_local_not_found(self, capsys):
        mgr = MagicMock()
        mgr.delete_backup.return_value = False
        self._run_cli(["delete", "ghost_backup"], mgr)
        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_cli_delete_s3(self, capsys):
        mgr = MagicMock()
        mgr.delete_s3_backup.return_value = True
        self._run_cli(["delete", "old_backup", "--from-s3"], mgr)
        mgr.delete_s3_backup.assert_called_once_with("old_backup")

    def test_cli_delete_s3_not_found(self, capsys):
        mgr = MagicMock()
        mgr.delete_s3_backup.return_value = False
        self._run_cli(["delete", "ghost_backup", "--from-s3"], mgr)
        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_cli_s3_status_disabled(self, capsys):
        mgr = MagicMock()
        mgr.s3_config.enabled = False
        self._run_cli(["s3-status"], mgr)
        out = capsys.readouterr().out
        assert "False" in out

    def test_cli_s3_status_enabled(self, capsys):
        mgr = MagicMock()
        mgr.s3_config.enabled = True
        mgr.s3_config.bucket = "my-bucket"
        mgr.s3_config.region = "us-east-1"
        mgr.s3_config.endpoint_url = None
        mgr.s3_client = MagicMock()
        mgr.s3_client.head_bucket.return_value = {}
        self._run_cli(["s3-status"], mgr)
        out = capsys.readouterr().out
        assert "my-bucket" in out

    def test_cli_s3_status_connection_fail(self, capsys):
        from botocore.exceptions import ClientError
        mgr = MagicMock()
        mgr.s3_config.enabled = True
        mgr.s3_config.bucket = "my-bucket"
        mgr.s3_config.region = "us-east-1"
        mgr.s3_config.endpoint_url = None
        mgr.s3_client = MagicMock()
        error = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadBucket")
        mgr.s3_client.head_bucket.side_effect = error
        self._run_cli(["s3-status"], mgr)
        out = capsys.readouterr().out
        assert "Failed" in out or "failed" in out or "✗" in out

    def test_cli_no_command_prints_help(self, capsys):
        mgr = MagicMock()
        # No subcommand given → falls through to parser.print_help()
        self._run_cli([], mgr)
        # Should not raise; no command is invoked on mgr
        mgr.create_backup.assert_not_called()

    def test_cli_restore_from_s3(self, capsys):
        mgr = MagicMock()
        mgr.restore_backup.return_value = {"total_rows_restored": 5}
        self._run_cli(["restore", "s3://bucket/key", "--from-s3"], mgr)
        call_kwargs = mgr.restore_backup.call_args[1]
        assert call_kwargs.get("from_s3") is True

    def test_cli_create_with_encrypt(self, capsys):
        mgr = MagicMock()
        mgr.create_backup.return_value = {"file_path": "/tmp/enc.json.enc", "s3_info": None}
        self._run_cli(["create", "--name", "enc_test", "--encrypt"], mgr)
        call_kwargs = mgr.create_backup.call_args[1]
        assert call_kwargs.get("encrypt") is True


# ---------------------------------------------------------------------------
# Additional edge-case tests for 100% coverage
# ---------------------------------------------------------------------------

class TestAdditionalCoverage:
    def _write_backup_file(self, tmp_path, name, data, compress=False):
        json_str = json.dumps(data)
        if compress:
            fpath = tmp_path / f"{name}.json.gz"
            with gzip.open(fpath, "wb") as f:
                f.write(json_str.encode("utf-8"))
        else:
            fpath = tmp_path / f"{name}.json"
            fpath.write_text(json_str)
        return fpath

    def test_restore_decrypt_with_key_succeeds(self, tmp_path):
        """Decrypt path: decrypt=True with key provided calls _decrypt_file."""
        data = {"metadata": {"version": "1.0"}, "data": {}}
        fpath = self._write_backup_file(tmp_path, "dec_ok", data, compress=False)

        db = MagicMock()
        db.tables = {}
        mgr = _make_manager(tmp_path)

        with patch("backup.get_db", return_value=db), \
             patch.object(mgr, "_decrypt_file", return_value=fpath) as mock_dec:
            stats = mgr.restore_backup(
                str(fpath), decrypt=True, decryption_key="secret_key", verify_checksum=False
            )
        mock_dec.assert_called_once_with(fpath, "secret_key")
        assert stats["total_rows_restored"] == 0

    def test_restore_from_s3_with_decrypt(self, tmp_path):
        """from_s3=True + decrypt=True: download first, then decrypt."""
        data = {"metadata": {"version": "1.0"}, "data": {}}
        fpath = self._write_backup_file(tmp_path, "s3_dec", data, compress=False)

        db = MagicMock()
        db.tables = {}
        mgr = _make_manager(tmp_path)
        mgr.s3_client = MagicMock()

        with patch("backup.get_db", return_value=db), \
             patch.object(mgr, "_download_backup_from_s3", return_value=fpath), \
             patch.object(mgr, "_decrypt_file", return_value=fpath) as mock_dec:
            stats = mgr.restore_backup(
                "s3://bucket/key", from_s3=True,
                decrypt=True, decryption_key="key123", verify_checksum=False
            )
        mock_dec.assert_called_once()

    def test_delete_backup_unlink_error_logged(self, tmp_path):
        """If file.unlink() raises, the error is logged and deleted=False returned."""
        mgr = _make_manager(tmp_path)
        # Create a file matching the pattern
        f = tmp_path / "broken_backup.json"
        f.write_text("{}")

        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            result = mgr.delete_backup("broken_backup")

        # deleted remains False because the unlink failed
        assert result is False

    def test_list_s3_backups_sorted_descending(self, tmp_path):
        """list_s3_backups returns entries sorted newest first."""
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()

        page = {
            "Contents": [
                {
                    "Key": "backups/backup_older/backup_older.json",
                    "Size": 100,
                    "LastModified": datetime(2025, 1, 1),
                    "StorageClass": "STANDARD"
                },
                {
                    "Key": "backups/backup_newer/backup_newer.json",
                    "Size": 200,
                    "LastModified": datetime(2025, 6, 1),
                    "StorageClass": "STANDARD"
                }
            ]
        }
        paginator = MagicMock()
        paginator.paginate.return_value = [page]
        mgr.s3_client.get_paginator.return_value = paginator

        result = mgr.list_s3_backups()
        assert len(result) == 2
        assert result[0]["backup_name"] == "backup_newer"

    def test_cli_s3_status_no_s3_client(self, capsys):
        """s3-status with enabled=True but s3_client=None skips connection test."""
        mgr = MagicMock()
        mgr.s3_config.enabled = True
        mgr.s3_config.bucket = "my-bucket"
        mgr.s3_config.region = "us-east-1"
        mgr.s3_config.endpoint_url = "http://minio:9000"
        mgr.s3_client = None

        with patch("sys.argv", ["backup", "s3-status"]), \
             patch("backup.BackupManager", return_value=mgr):
            backup_cli()

        out = capsys.readouterr().out
        assert "my-bucket" in out
        assert "Connected: False" in out

    def test_list_s3_backups_skips_single_part_key(self, tmp_path):
        """S3 keys with no subdirectory structure (only 1 part) are skipped."""
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()

        page = {
            "Contents": [
                {
                    # This key, after stripping prefix, has only 1 part (no /)
                    "Key": "backups/orphaned_file.json",
                    "Size": 50,
                    "LastModified": datetime(2025, 3, 1),
                    "StorageClass": "STANDARD"
                },
                {
                    # This one has proper 2-part structure and should be included
                    "Key": "backups/proper_backup/proper_backup.json",
                    "Size": 100,
                    "LastModified": datetime(2025, 3, 2),
                    "StorageClass": "STANDARD"
                }
            ]
        }
        paginator = MagicMock()
        paginator.paginate.return_value = [page]
        mgr.s3_client.get_paginator.return_value = paginator

        result = mgr.list_s3_backups()
        # Only the properly structured backup should be returned
        assert len(result) == 1
        assert result[0]["backup_name"] == "proper_backup"

    def test_delete_s3_backup_empty_contents_returns_false(self, tmp_path):
        """delete_s3_backup returns False when Contents list is empty after filtering."""
        mgr = _make_manager(tmp_path)
        mgr.s3_config.bucket = "test-bucket"
        mgr.s3_config.prefix = "backups/"
        mgr.s3_client = MagicMock()
        # Contents is present but empty list
        mgr.s3_client.list_objects_v2.return_value = {
            "Contents": []
        }

        result = mgr.delete_s3_backup("empty_contents_backup")
        # objects_to_delete will be [] so the if branch is False → returns False
        assert result is False
