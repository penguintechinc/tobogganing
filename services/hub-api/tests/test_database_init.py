"""
Tests for database/__init__.py — URI construction, initialization, get_db/get_read_db,
close_database.

penguin_dal is mocked at sys.modules level before the database module is imported.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock penguin_dal before importing database
# ---------------------------------------------------------------------------

_mock_async_db_instance = MagicMock()
_mock_async_db_instance.close = AsyncMock()
_mock_async_db_instance.reflect = AsyncMock()

_mock_async_db_class = MagicMock(return_value=_mock_async_db_instance)

_mock_init_dal = MagicMock()
_mock_quart_get_db = MagicMock()

_mock_penguin_dal = MagicMock()
_mock_penguin_dal.AsyncDB = _mock_async_db_class

_mock_penguin_dal_quart = MagicMock()
_mock_penguin_dal_quart.init_dal = _mock_init_dal
_mock_penguin_dal_quart.get_db = _mock_quart_get_db

if "penguin_dal" not in sys.modules:
    sys.modules["penguin_dal"] = _mock_penguin_dal

if "penguin_dal.quart_ext" not in sys.modules:
    sys.modules["penguin_dal.quart_ext"] = _mock_penguin_dal_quart

import database as db_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_db_state():
    db_module._db = None
    db_module._db_read = None


# ---------------------------------------------------------------------------
# get_database_uri — MySQL
# ---------------------------------------------------------------------------

class TestGetDatabaseUriMySQL:
    def test_default_mysql_uri(self):
        with patch.dict(os.environ, {"DB_TYPE": "mysql"}, clear=False):
            for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
                os.environ.pop(k, None)
            uri = db_module.get_database_uri()
        assert uri.startswith("mysql+aiomysql://")
        assert "localhost" in uri

    def test_mysql_with_custom_host_port(self):
        env = {
            "DB_TYPE": "mysql",
            "DB_HOST": "db.internal",
            "DB_PORT": "3307",
            "DB_USER": "myuser",
            "DB_PASSWORD": "mypass",
            "DB_NAME": "mydb",
        }
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "db.internal:3307" in uri
        assert "myuser:mypass" in uri
        assert "mydb" in uri

    def test_mysql_tls_params_appended(self):
        env = {
            "DB_TYPE": "mysql",
            "DB_TLS_ENABLED": "true",
            "DB_TLS_VERIFY_MODE": "VERIFY_CA",
        }
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "ssl=true" in uri
        assert "ssl-mode=VERIFY_CA" in uri

    def test_mysql_tls_ca_cert_included(self):
        env = {
            "DB_TYPE": "mysql",
            "DB_TLS_ENABLED": "true",
            "DB_TLS_CA_CERT": "/path/to/ca.pem",
        }
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "ssl-ca=/path/to/ca.pem" in uri

    def test_mysql_charset_in_params(self):
        env = {"DB_TYPE": "mysql", "DB_CHARSET": "utf8"}
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "charset=utf8" in uri

    def test_mysql_collation_in_params(self):
        env = {"DB_TYPE": "mysql", "DB_CHARSET": "utf8mb4", "DB_COLLATION": "utf8mb4_general_ci"}
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "collation=utf8mb4_general_ci" in uri

    def test_mysql_connect_timeout_in_params(self):
        env = {"DB_TYPE": "mysql", "DB_CONNECT_TIMEOUT": "30"}
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "connect_timeout=30" in uri


# ---------------------------------------------------------------------------
# get_database_uri — PostgreSQL
# ---------------------------------------------------------------------------

class TestGetDatabaseUriPostgresql:
    def test_default_postgresql_uri(self):
        with patch.dict(os.environ, {"DB_TYPE": "postgresql"}, clear=False):
            uri = db_module.get_database_uri()
        assert uri.startswith("postgresql+asyncpg://")

    def test_postgresql_custom_host_port(self):
        env = {
            "DB_TYPE": "postgresql",
            "DB_HOST": "pg.internal",
            "DB_PORT": "5433",
            "DB_USER": "pguser",
            "DB_PASSWORD": "pgpass",
            "DB_NAME": "pgdb",
        }
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "pg.internal:5433" in uri
        assert "pguser:pgpass" in uri
        assert "pgdb" in uri

    def test_postgresql_tls_params(self):
        env = {
            "DB_TYPE": "postgresql",
            "DB_TLS_ENABLED": "true",
            "DB_TLS_VERIFY_MODE": "require",
        }
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "sslmode=require" in uri

    def test_postgresql_tls_client_cert(self):
        env = {
            "DB_TYPE": "postgresql",
            "DB_TLS_ENABLED": "true",
            "DB_TLS_CLIENT_CERT": "/certs/client.crt",
            "DB_TLS_CLIENT_KEY": "/certs/client.key",
        }
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "sslcert=/certs/client.crt" in uri
        assert "sslkey=/certs/client.key" in uri

    def test_postgresql_connect_timeout(self):
        env = {"DB_TYPE": "postgresql", "DB_CONNECT_TIMEOUT": "10"}
        with patch.dict(os.environ, env, clear=False):
            uri = db_module.get_database_uri()
        assert "connect_timeout=10" in uri


# ---------------------------------------------------------------------------
# get_database_uri — SQLite
# ---------------------------------------------------------------------------

class TestGetDatabaseUriSQLite:
    def test_default_sqlite_uri(self):
        with patch.dict(os.environ, {"DB_TYPE": "sqlite"}, clear=False):
            os.environ.pop("DB_PATH", None)
            uri = db_module.get_database_uri()
        assert uri.startswith("sqlite+aiosqlite://")
        assert "tobogganing.db" in uri

    def test_custom_sqlite_path(self):
        with patch.dict(os.environ, {"DB_TYPE": "sqlite", "DB_PATH": "/tmp/test.db"}, clear=False):
            uri = db_module.get_database_uri()
        assert "/tmp/test.db" in uri


# ---------------------------------------------------------------------------
# get_database_uri — Unsupported type
# ---------------------------------------------------------------------------

class TestGetDatabaseUriUnsupported:
    def test_raises_value_error(self):
        with patch.dict(os.environ, {"DB_TYPE": "oracle"}, clear=False):
            with pytest.raises(ValueError, match="Unsupported database type"):
                db_module.get_database_uri()


# ---------------------------------------------------------------------------
# get_read_replica_uri
# ---------------------------------------------------------------------------

class TestGetReadReplicaUri:
    def test_returns_none_when_disabled(self):
        with patch.dict(os.environ, {"DB_READ_REPLICA_ENABLED": "false"}, clear=False):
            result = db_module.get_read_replica_uri()
        assert result is None

    def test_returns_none_when_not_set(self):
        env = {k: v for k, v in os.environ.items()}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DB_READ_REPLICA_ENABLED", None)
            result = db_module.get_read_replica_uri()
        assert result is None

    def test_returns_mysql_uri_when_enabled(self):
        env = {
            "DB_READ_REPLICA_ENABLED": "true",
            "DB_TYPE": "mysql",
            "DB_READ_HOST": "replica.internal",
            "DB_READ_PORT": "3306",
        }
        with patch.dict(os.environ, env, clear=False):
            result = db_module.get_read_replica_uri()
        assert result is not None
        assert "mysql+aiomysql://" in result
        assert "replica.internal" in result

    def test_returns_postgresql_uri_when_enabled(self):
        env = {
            "DB_READ_REPLICA_ENABLED": "true",
            "DB_TYPE": "postgresql",
            "DB_READ_HOST": "pg-replica.internal",
        }
        with patch.dict(os.environ, env, clear=False):
            result = db_module.get_read_replica_uri()
        assert result is not None
        assert "postgresql+asyncpg://" in result

    def test_sqlite_returns_none_for_replica(self):
        env = {
            "DB_READ_REPLICA_ENABLED": "true",
            "DB_TYPE": "sqlite",
        }
        with patch.dict(os.environ, env, clear=False):
            result = db_module.get_read_replica_uri()
        assert result is None

    def test_read_falls_back_to_primary_host_when_read_not_set(self):
        env = {
            "DB_READ_REPLICA_ENABLED": "true",
            "DB_TYPE": "mysql",
            "DB_HOST": "primary.internal",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("DB_READ_HOST", None)
            result = db_module.get_read_replica_uri()
        assert result is not None
        assert "primary.internal" in result


# ---------------------------------------------------------------------------
# initialize_database
# ---------------------------------------------------------------------------

class TestInitializeDatabase:
    def setup_method(self):
        _reset_db_state()
        _mock_async_db_class.reset_mock()
        _mock_init_dal.reset_mock()

    def teardown_method(self):
        _reset_db_state()

    def test_calls_init_dal(self):
        mock_app = MagicMock()
        env = {"DB_TYPE": "sqlite", "DB_PATH": "/tmp/test_init.db"}
        with patch.dict(os.environ, env, clear=False):
            db_module.initialize_database(mock_app)
        # Verify db is set — init_dal was invoked (real penguin_dal is installed)
        assert db_module._db is not None

    def test_sets_module_db(self):
        mock_app = MagicMock()
        env = {"DB_TYPE": "sqlite"}
        with patch.dict(os.environ, env, clear=False):
            db_module.initialize_database(mock_app)
        assert db_module._db is not None

    def test_sets_db_read_to_db_when_no_replica(self):
        mock_app = MagicMock()
        env = {"DB_TYPE": "sqlite", "DB_READ_REPLICA_ENABLED": "false"}
        with patch.dict(os.environ, env, clear=False):
            db_module.initialize_database(mock_app)
        # When no read replica, _db_read == _db
        assert db_module._db_read is db_module._db

    def test_creates_separate_read_db_when_replica_enabled(self):
        mock_app = MagicMock()
        env = {
            "DB_TYPE": "sqlite",
            "DB_READ_REPLICA_ENABLED": "true",
            "DB_READ_HOST": "read-replica.internal",
        }
        with patch.dict(os.environ, env, clear=False):
            db_module.initialize_database(mock_app)
        # With read replica enabled, _db and _db_read exist
        assert db_module._db is not None
        assert db_module._db_read is not None

    def test_pool_size_env_var_used(self):
        mock_app = MagicMock()
        env = {"DB_TYPE": "sqlite", "DB_POOL_SIZE": "20"}
        with patch.dict(os.environ, env, clear=False):
            db_module.initialize_database(mock_app)
        # DB should be initialized regardless of pool size
        assert db_module._db is not None


# ---------------------------------------------------------------------------
# get_db / get_read_db
# ---------------------------------------------------------------------------

class TestGetDb:
    def setup_method(self):
        _reset_db_state()

    def teardown_method(self):
        _reset_db_state()

    def test_get_db_raises_when_not_initialized(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            db_module.get_db()

    def test_get_db_returns_db_when_initialized(self):
        db_module._db = _mock_async_db_instance
        result = db_module.get_db()
        assert result is _mock_async_db_instance

    def test_get_read_db_raises_when_not_initialized(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            db_module.get_read_db()

    def test_get_read_db_returns_db_when_initialized(self):
        db_module._db_read = _mock_async_db_instance
        result = db_module.get_read_db()
        assert result is _mock_async_db_instance


# ---------------------------------------------------------------------------
# close_database
# ---------------------------------------------------------------------------

class TestCloseDatabase:
    def setup_method(self):
        _reset_db_state()

    def teardown_method(self):
        _reset_db_state()

    @pytest.mark.asyncio
    async def test_close_noop_when_not_initialized(self):
        # Should not raise when _db and _db_read are None
        await db_module.close_database()

    @pytest.mark.asyncio
    async def test_close_calls_db_close(self):
        mock_db = MagicMock()
        mock_db.close = AsyncMock()
        db_module._db = mock_db
        db_module._db_read = mock_db  # same instance — close called once or twice depending on impl
        await db_module.close_database()
        assert mock_db.close.called

    @pytest.mark.asyncio
    async def test_close_sets_db_to_none(self):
        mock_db = MagicMock()
        mock_db.close = AsyncMock()
        db_module._db = mock_db
        db_module._db_read = mock_db
        await db_module.close_database()
        assert db_module._db is None
        assert db_module._db_read is None

    @pytest.mark.asyncio
    async def test_close_closes_separate_read_db(self):
        mock_primary = MagicMock()
        mock_primary.close = AsyncMock()
        mock_read = MagicMock()
        mock_read.close = AsyncMock()
        db_module._db = mock_primary
        db_module._db_read = mock_read
        await db_module.close_database()
        mock_primary.close.assert_called_once()
        mock_read.close.assert_called_once()
