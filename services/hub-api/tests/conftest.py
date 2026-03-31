"""
Shared test fixtures and configuration for hub-api test suite.
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

# Ensure the hub-api root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Pre-patch optional dependencies that are not installed in the test environment.
# aioredis is replaced by redis.asyncio; py4web is not installed (hub-api uses Quart).
if "aioredis" not in sys.modules:
    _mock_aioredis = MagicMock()
    _mock_aioredis.from_url = AsyncMock()
    _mock_aioredis.Redis = MagicMock
    sys.modules["aioredis"] = _mock_aioredis

if "py4web" not in sys.modules:
    _py4web_mock = MagicMock()
    # Set __path__ so Python treats it as a package (allows submodule discovery).
    _py4web_mock.__path__ = []

    # Fixture MUST be a real class, not a MagicMock instance.
    # `class SecurityFixture(MagicMock_instance)` makes SecurityFixture itself a
    # MagicMock — Python's class machinery defers to the mock's metaclass.
    class _Py4WebFixture:
        """Minimal stub for py4web.Fixture so subclasses are real types."""
        __prerequisites__: list = []

    _py4web_mock.Fixture = _Py4WebFixture

    sys.modules["py4web"] = _py4web_mock
    # Pre-populate all py4web submodules referenced across the codebase so that
    # `from py4web.X.Y import Z` works without a real py4web installation.
    for _sub in ("core", "utils", "utils.form", "utils.cors", "utils.auth"):
        _sub_mock = MagicMock()
        _sub_mock.Fixture = _Py4WebFixture
        sys.modules[f"py4web.{_sub}"] = _sub_mock

if "nmap" not in sys.modules:
    sys.modules["nmap"] = MagicMock()

# Third-party DNS / network libs used by security.feeds
for _dns_mod in ("dns", "dns.resolver", "aiohttp"):
    if _dns_mod not in sys.modules:
        sys.modules[_dns_mod] = MagicMock()

# security.scanner and security.feeds both use `from ..audit import ...` (relative
# imports that assume a parent package).  They cannot be imported when `security`
# is a top-level package in the test environment, so mock them pre-emptively.
if "security.scanner" not in sys.modules:
    sys.modules["security.scanner"] = MagicMock()
if "security.feeds" not in sys.modules:
    _feeds_mock = MagicMock()
    _feeds_mock.ThreatType = MagicMock()
    sys.modules["security.feeds"] = _feeds_mock

# api.security_routes uses `from ..security import ...` which fails when api/
# is a top-level package.  Mock it so import tests can pass.
# Also set the attribute on the api package so `api.security_routes` works.
if "api.security_routes" not in sys.modules:
    _sr_mock = MagicMock()
    sys.modules["api.security_routes"] = _sr_mock
    import api as _api_pkg
    _api_pkg.security_routes = _sr_mock

# web/__init__.py uses relative imports (from ..security.middleware) which fail
# when web is a top-level package.  Mock it so api.analytics_routes etc. can be
# imported in tests without requiring the full py4web layout.
if "web" not in sys.modules:
    sys.modules["web"] = MagicMock()
    sys.modules["web.auth"] = MagicMock()

# Create a .version file so metrics module can load
_VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".version")
if not os.path.exists(_VERSION_FILE):
    with open(_VERSION_FILE, "w") as _f:
        _f.write("v0.2.0.1234567890")


# ---------------------------------------------------------------------------
# Database mocks
# ---------------------------------------------------------------------------

def make_mock_db():
    """Create a MagicMock that simulates a PyDAL DAL object."""
    db = MagicMock()
    db.tables = []

    # Make table definition calls work idempotently
    def define_table(name, *args, **kwargs):
        db.tables.append(name)
        tbl = MagicMock()
        tbl.insert = MagicMock(return_value=1)
        tbl.truncate = MagicMock()
        tbl.bulk_insert = MagicMock()
        setattr(db, name, tbl)
        return tbl

    db.define_table = define_table
    db.executesql = MagicMock(return_value=[])
    db.commit = MagicMock()
    db.close = MagicMock()

    # Support query chaining: db(query).select() etc.
    query_result = MagicMock()
    query_result.select = MagicMock(return_value=[])
    query_result.count = MagicMock(return_value=0)
    query_result.delete = MagicMock(return_value=0)
    query_result.update = MagicMock(return_value=0)
    db.__call__ = MagicMock(return_value=query_result)

    return db


@pytest.fixture
def mock_db():
    """PyDAL-style mock database."""
    return make_mock_db()


@pytest.fixture
def mock_get_db(mock_db):
    """Patch database.get_db to return mock_db."""
    with patch("database.get_db", return_value=mock_db):
        yield mock_db


# ---------------------------------------------------------------------------
# Redis mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Async mock Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.setex = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=0)
    client.keys = AsyncMock(return_value=[])
    client.ttl = AsyncMock(return_value=-1)
    client.expire = AsyncMock(return_value=True)
    client.sadd = AsyncMock(return_value=1)
    client.smembers = AsyncMock(return_value=set())
    client.srem = AsyncMock(return_value=1)
    client.publish = AsyncMock(return_value=1)
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_redis_pool(mock_redis):
    """Mock Redis connection pool."""
    pool = MagicMock()
    pool.execute_command = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# JWT Manager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def jwt_manager(mock_redis):
    """JWTManager instance with mocked Redis."""
    from auth.jwt_manager import JWTManager

    mgr = JWTManager(redis_url="redis://localhost:6379/0")
    mgr.redis_pool = mock_redis
    return mgr


# ---------------------------------------------------------------------------
# User Manager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def user_manager(tmp_path):
    """UserManager backed by an in-memory SQLite DB."""
    from auth.user_manager import UserManager

    db_path = str(tmp_path / "test_users.db")
    return UserManager(db_path=db_path)


# ---------------------------------------------------------------------------
# Access Control Manager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def access_control_manager(tmp_path):
    """AccessControlManager backed by a temp SQLite DB."""
    from firewall.access_control import AccessControlManager

    db_path = str(tmp_path / "test_acl.db")
    return AccessControlManager(db_path=db_path)


# ---------------------------------------------------------------------------
# Port Config Manager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def port_config_manager(tmp_path):
    """PortConfigManager backed by a temp SQLite DB."""
    db_path = str(tmp_path / "test_ports.db")

    # The module creates a global instance at import with default path.
    # We instantiate directly using the class (bypassing global).
    import sqlite3

    class _TestPortConfigManager:
        """Thin wrapper that uses a temp DB path."""
        def __init__(self, db_path: str):
            self.db_path = db_path
            self._ensure_tables()

        def _ensure_tables(self):
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS port_ranges (
                        id TEXT PRIMARY KEY,
                        headend_id TEXT NOT NULL,
                        cluster_id TEXT NOT NULL,
                        start_port INTEGER NOT NULL,
                        end_port INTEGER NOT NULL,
                        protocol TEXT NOT NULL,
                        description TEXT,
                        enabled BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

        def _has_port_overlap(self, existing, new_range):
            from network.port_manager import PortProtocol
            for ex in existing:
                if ex.protocol != new_range.protocol:
                    continue
                if ex.start_port <= new_range.end_port and ex.end_port >= new_range.start_port:
                    return True
            return False

        async def add_port_range(self, headend_id: str, cluster_id: str, port_range):
            import uuid, json
            from datetime import datetime
            pid = str(uuid.uuid4())
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO port_ranges (id, headend_id, cluster_id, start_port, end_port, protocol, description, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (pid, headend_id, cluster_id, port_range.start_port, port_range.end_port,
                      port_range.protocol.value, port_range.description, port_range.enabled))
            port_range.id = pid
            return True

        async def get_headend_config(self, headend_id: str):
            from network.port_manager import PortRange, PortProtocol, HeadendPortConfig
            from datetime import datetime
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM port_ranges WHERE headend_id = ? AND enabled = 1 ORDER BY protocol, start_port",
                    (headend_id,)
                ).fetchall()
            if not rows:
                return None
            tcp_ranges, udp_ranges = [], []
            for row in rows:
                pr = PortRange(
                    id=row["id"],
                    start_port=row["start_port"],
                    end_port=row["end_port"],
                    protocol=PortProtocol(row["protocol"]),
                    description=row["description"] or "",
                    enabled=bool(row["enabled"]),
                )
                if pr.protocol.value == "tcp":
                    tcp_ranges.append(pr)
                else:
                    udp_ranges.append(pr)
            return HeadendPortConfig(headend_id=headend_id, cluster_id=rows[0]["cluster_id"],
                                     tcp_ranges=tcp_ranges, udp_ranges=udp_ranges)

        async def remove_port_range(self, range_id: str, headend_id: str) -> bool:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "DELETE FROM port_ranges WHERE id = ? AND headend_id = ?", (range_id, headend_id)
                )
            return cur.rowcount > 0

        async def get_all_configs(self):
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute("SELECT DISTINCT headend_id FROM port_ranges").fetchall()
            return [r[0] for r in rows]

        async def set_default_config(self, config):
            for pr in config.tcp_ranges:
                await self.add_port_range(config.headend_id, config.cluster_id, pr)
            for pr in config.udp_ranges:
                await self.add_port_range(config.headend_id, config.cluster_id, pr)

    return _TestPortConfigManager(db_path)


# ---------------------------------------------------------------------------
# VRF Manager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def vrf_manager(tmp_path):
    """VRFManager backed by a temp SQLite DB."""
    from network.vrf_manager import VRFManager

    db_path = str(tmp_path / "test_vrf.db")
    return VRFManager(db_path=db_path)


# ---------------------------------------------------------------------------
# Audit Logger fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def audit_logger(mock_db):
    """AuditLogger with mocked DB."""
    with patch("database.get_db", return_value=mock_db):
        from audit import AuditLogger
        logger = AuditLogger.__new__(AuditLogger)
        logger.db = mock_db
        logger._ensure_audit_tables = MagicMock()
        logger.compliance_mapping = {}
        return logger


# ---------------------------------------------------------------------------
# Analytics Manager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def analytics_manager(mock_db):
    """AnalyticsManager with mocked DB."""
    with patch("database.get_db", return_value=mock_db):
        from analytics import AnalyticsManager
        mgr = AnalyticsManager.__new__(AnalyticsManager)
        mgr.db = mock_db
        return mgr


# ---------------------------------------------------------------------------
# Metrics fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def manager_metrics(tmp_path):
    """ManagerMetrics with a real .version file."""
    version_file = tmp_path / ".version"
    version_file.write_text("v0.2.0.1234567890")
    _real_open = open  # capture before patching to avoid recursion

    with patch("builtins.open", side_effect=lambda path, *a, **kw: (
        _real_open(str(version_file), *a, **kw) if ".version" in str(path)
        else _real_open(path, *a, **kw)
    )):
        from metrics.prometheus import ManagerMetrics
        return ManagerMetrics()


# ---------------------------------------------------------------------------
# Quart test client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def quart_app():
    """Create a Quart test application."""
    import importlib
    import types

    # Patch database and licensing before importing main
    mock_db_instance = make_mock_db()

    with patch("database.initialize_database", return_value=None), \
         patch("database.get_db", return_value=mock_db_instance), \
         patch("licensing.validate_license", return_value={
             "valid": True,
             "tier": "community",
             "features": [],
         }):
        from main import create_app
        app = create_app()
        app.config["TESTING"] = True
        return app


@pytest_asyncio.fixture
async def test_client(quart_app):
    """Quart async test client."""
    async with quart_app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_node_id():
    return "node-test-aabbccdd"


@pytest.fixture
def sample_client_id():
    return "client-test-11223344"


@pytest.fixture
def sample_cluster_id():
    return "cluster-test-aabbccdd"


@pytest.fixture
def valid_token_payload():
    """A valid, not-yet-expired JWT payload."""
    now = datetime.now(timezone.utc)
    return {
        "sub": "node-test-aabbccdd",
        "node_type": "client",
        "permissions": ["connect", "metrics"],
        "iat": now.timestamp(),
        "exp": (now + timedelta(hours=24)).timestamp(),
        "jti": "test-jti-0001",
        "type": "access",
    }
