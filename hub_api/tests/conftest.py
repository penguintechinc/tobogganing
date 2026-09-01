"""Shared pytest fixtures for core tests."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from quart import Quart


def make_mock_row(data: dict[str, Any]) -> MagicMock:
    """Create a mock row object that behaves like a penguin-dal row.

    Args:
        data: Dictionary of row data.

    Returns:
        Mock row object with attributes and as_dict method.
    """
    row = MagicMock()
    for key, value in data.items():
        setattr(row, key, value)
    row.as_dict.return_value = data
    return row


def make_mock_rowset(rows: list[Any]) -> MagicMock:
    """Create a mock rowset that supports .first() and iteration.

    Args:
        rows: List of mock row objects.

    Returns:
        Mock rowset with iteration support.
    """
    rowset = MagicMock()
    rowset.first.return_value = rows[0] if rows else None
    rowset.__iter__ = MagicMock(side_effect=lambda: iter(rows))
    rowset.__len__ = MagicMock(return_value=len(rows))
    return rowset


@pytest.fixture
def mock_db() -> MagicMock:
    """Provide a mock AsyncDB for testing without a real database.

    Returns:
        Mock database object simulating penguin-dal interface.
    """
    db = MagicMock()

    # Default: empty rowset for db(query).select()
    empty_rowset = make_mock_rowset([])
    query_proxy = MagicMock()
    query_proxy.select = AsyncMock(return_value=empty_rowset)
    query_proxy.count = AsyncMock(return_value=0)
    query_proxy.update = AsyncMock(return_value=None)
    query_proxy.delete = AsyncMock(return_value=None)
    db.__call__ = MagicMock(return_value=query_proxy)
    db.return_value = query_proxy

    # Mock field attributes that support penguin-dal comparison operators
    def make_comparable_field(field_name: str) -> MagicMock:
        """Create a mock field that supports comparison operators."""
        field_mock = MagicMock()
        field_mock.__eq__ = MagicMock(return_value=query_proxy)
        field_mock.__ne__ = MagicMock(return_value=query_proxy)
        field_mock.__lt__ = MagicMock(return_value=query_proxy)
        field_mock.__le__ = MagicMock(return_value=query_proxy)
        field_mock.__gt__ = MagicMock(return_value=query_proxy)
        field_mock.__ge__ = MagicMock(return_value=query_proxy)
        return field_mock

    # Make query_proxy support & and | operators for combined queries
    query_proxy.__and__ = MagicMock(return_value=query_proxy)
    query_proxy.__or__ = MagicMock(return_value=query_proxy)

    # Default table insert returns id=1 (or similar)
    for table_name in [
        "users",
        "refresh_tokens",
        "password_reset_tokens",
        "devices",
        "device_api_keys",
        "device_enrollment_secrets",
        "org_units",
        "perf_test_results",
        "test_schedules",
    ]:
        table_mock = MagicMock()
        table_mock.async_insert = AsyncMock(return_value=1)
        table_mock.id = make_comparable_field("id")
        table_mock.tenant = make_comparable_field("tenant")
        table_mock.device_id = make_comparable_field("device_id")
        table_mock.api_key_hash = make_comparable_field("api_key_hash")
        table_mock.secret_hash = make_comparable_field("secret_hash")
        table_mock.parent_id = make_comparable_field("parent_id")
        table_mock.org_unit_id = make_comparable_field("org_unit_id")
        table_mock.test_type = make_comparable_field("test_type")
        table_mock.status = make_comparable_field("status")
        setattr(db, table_name, table_mock)

    # Mock connection for health checks
    connection_mock = MagicMock()
    connection_mock.execute = MagicMock(return_value=MagicMock())
    db.connection = connection_mock

    return db


@pytest.fixture
def mock_config() -> MagicMock:
    """Test configuration object.

    Returns:
        Mock Config object with test values.
    """
    from hub_api.config import Config

    config = Config(
        db_type="sqlite",
        db_name=":memory:",
        db_host="localhost",
        db_port=5432,
        db_user="test",
        db_pass="test",
        db_pool_size=5,
        jwt_expiration_hours=24,
        cors_origins="http://localhost:3000",
        log_level="WARNING",
    )
    return config  # type: ignore[return-value]


@pytest.fixture
def app(mock_db: MagicMock) -> Quart:
    """Create a minimal Quart test application with mocked services.

    Args:
        mock_db: Mocked database fixture.

    Returns:
        Configured Quart test application.
    """
    from unittest.mock import MagicMock, patch

    import hub_api.db
    from hub_api.app import create_app

    # Patch init_dal and get_db
    with patch("hub_api.db.init_dal"), patch.object(hub_api.db, "get_db", return_value=mock_db):
        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.db = mock_db  # type: ignore[attr-defined]

        # Apply the patch to the app's context
        test_app.g = MagicMock()  # type: ignore[attr-defined]

        # Replace the get_db reference in the app module
        import hub_api.app as app_module

        app_module.get_db = lambda: mock_db  # type: ignore[assignment]

    return test_app


@pytest.fixture
def client(app: Quart) -> Any:
    """Quart async test client.

    Args:
        app: Quart test application.

    Returns:
        Async test client.
    """
    return app.test_client()


@pytest.fixture
def test_db_session() -> Any:
    """Provide a SQLAlchemy session for database tests.

    Creates an in-memory SQLite database with all migrations applied.

    Yields:
        SQLAlchemy session for database operations.
    """
    import tempfile
    from pathlib import Path

    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config as AlembicConfig
    from sqlalchemy.orm import sessionmaker

    # Create a temporary SQLite database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_uri = f"sqlite:///{db_path}"

        # Create an Alembic config pointing to the temp DB
        alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"
        alembic_cfg = AlembicConfig(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", db_uri)
        # Keep alembic's fileConfig() from disabling every already-created
        # logger session-wide (it silently breaks caplog in later tests).
        alembic_cfg.attributes["configure_logger"] = False

        # Set the script location to the migrations directory
        migrations_dir = Path(__file__).parent.parent / "migrations"
        alembic_cfg.set_main_option("script_location", str(migrations_dir))

        # Run migrations to create schema
        command.upgrade(alembic_cfg, "head")

        # Create engine and session
        engine = sa.create_engine(db_uri)
        Session = sessionmaker(bind=engine)
        session = Session()

        yield session

        # Cleanup
        session.close()
        engine.dispose()


@pytest_asyncio.fixture
async def real_dal() -> Any:
    """Provide a real penguin-dal AsyncDB backed by a migrated sqlite database.

    Builds the schema via ``alembic upgrade head`` (the schema authority, exactly
    as production does), then constructs an ``AsyncDB`` and reflects the tables.
    This is the anti-mock integration harness: managers exercised through this
    fixture hit a real database, so a wrong DAL API or schema mismatch fails the
    test instead of being hidden by a mock.

    Managers must supply all NOT NULL columns explicitly (e.g. created_at /
    updated_at) — penguin-dal reflection does not apply model-side Python
    defaults.

    Yields:
        A reflected AsyncDB instance bound to a temp migrated sqlite DB.
    """
    import tempfile
    from pathlib import Path

    from alembic import command
    from alembic.config import Config as AlembicConfig
    from penguin_dal import AsyncDB

    with tempfile.TemporaryDirectory() as tmpdir:
        db_uri = f"sqlite:///{Path(tmpdir) / 'test.db'}"

        alembic_cfg = AlembicConfig(str(Path(__file__).parent.parent / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_uri)
        alembic_cfg.set_main_option(
            "script_location", str(Path(__file__).parent.parent / "migrations")
        )
        # Keep alembic's fileConfig() from disabling every already-created
        # logger session-wide (it silently breaks caplog in later tests).
        alembic_cfg.attributes["configure_logger"] = False
        command.upgrade(alembic_cfg, "head")

        dal = AsyncDB(uri=db_uri)
        await dal.reflect()
        try:
            yield dal
        finally:
            await dal.close()


# SASE Module Test Fixtures


@pytest.fixture
def app_with_sase(app: Quart, mock_db: MagicMock) -> Quart:
    """Create a test app with SASE module registered.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.

    Returns:
        Quart app with SASE module and auth configured.
    """
    from hub_api.auth.jwt import encode_access_token
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Register SASE module via registry (combines module prefix + blueprint prefix)
    from hub_api.modules.sase import module as sase_module

    sase_contract = sase_module()
    app.registry.register(sase_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def valid_tenant_token(app_with_sase: Quart) -> str:
    """Generate a valid tenant JWT token.

    Args:
        app_with_sase: App with key provider.

    Returns:
        Encoded JWT token with tenant claim.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "clusters:read clients:read status:read wireguard:read wireguard:write",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def valid_write_token(app_with_sase: Quart) -> str:
    """Generate a valid JWT token with write scopes.

    Args:
        app_with_sase: App with key provider.

    Returns:
        Encoded JWT token with write scopes.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


# Removed pytest_collection_modifyitems - using canonical fixtures instead with real auth


@pytest.fixture
def bootstrap_token() -> str:
    """Get bootstrap/enrollment token.

    Returns:
        Bootstrap token matching env var.
    """
    return os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "test-bootstrap-token")


# WaddlePerf Cluster Module Test Fixtures


@pytest.fixture
def app_with_wpc(app: Quart, mock_db: MagicMock, monkeypatch: Any) -> Quart:
    """Create a test app with WaddlePerf Cluster module registered with REAL auth.

    Uses real auth middleware and decorators. Feature flags are enabled via
    monkeypatching the flag server to always return True for wpc features.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.
        monkeypatch: Pytest monkeypatch fixture for enabling flags.

    Returns:
        Quart app with WaddlePerf Cluster module and real auth working.
    """
    from hub_api.auth.jwt import encode_access_token
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Enable all wpc feature flags for tests (bypass flag server)
    import shared.licensing.entitlements

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.perftest.cluster.") or flag_key.startswith(
            "tobogganing.perftest.client."
        ):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    # Register WaddlePerf Cluster module via registry (REAL auth, no monkeypatch)
    from hub_api.modules.perftest_client import module as wpcl_module
    from hub_api.modules.perftest_cluster import module as wpc_module

    wpc_contract = wpc_module()
    wpcl_contract = wpcl_module()
    app.registry.register(wpc_contract)
    app.registry.register(wpcl_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def wpc_tenant_token(app_with_wpc: Quart) -> str:
    """Generate a valid tenant JWT token for WPC module with minimal scopes.

    Args:
        app_with_wpc: App with key provider.

    Returns:
        Encoded JWT token with tenant claim.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_wpc.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "org_units:read devices:read tests:read stats:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def wpc_write_token(app_with_wpc: Quart) -> str:
    """Generate a JWT token with full write scopes for WPC testing.

    Args:
        app_with_wpc: App with key provider.

    Returns:
        Encoded JWT token with write scopes.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_wpc.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def wpc_readonly_token(app_with_wpc: Quart) -> str:
    """Generate a JWT token with read-only scope for WPC testing.

    Args:
        app_with_wpc: App with key provider.

    Returns:
        Encoded JWT token with read-only scope.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_wpc.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "org_units:read devices:read tests:read stats:read schedules:read config:read version:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


# Cluster-to-Cluster (C2C) Module Test Fixtures


@pytest.fixture
def app_with_c2c(app: Quart, mock_db: MagicMock, monkeypatch: Any) -> Quart:
    """Create a test app with WaddlePerf C2C module registered with REAL auth.

    Uses real auth middleware and decorators. Feature flags are enabled via
    monkeypatching the flag server to always return True for c2c features.

    Args:
        app: Base test app fixture.
        mock_db: Mock database fixture.
        monkeypatch: Pytest monkeypatch fixture for enabling flags.

    Returns:
        Quart app with WaddlePerf C2C module and real auth working.
    """
    from hub_api.auth.jwt import encode_access_token
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    # Set up key provider for token generation in tests
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Enable all c2c feature flags for tests (bypass flag server)
    import shared.licensing.entitlements

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.perftest.c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    # Grant a Professional license for tests: c2c is Professional-tier, so the
    # tier gate would otherwise return 402. The unlicensed path is asserted
    # separately in test_c2c_contract.py.
    import hub_api.entitlements.gate

    monkeypatch.setattr(
        hub_api.entitlements.gate,
        "_licensed_tier",
        lambda: "professional",
    )

    # Register WaddlePerf C2C module via registry (REAL auth, no monkeypatch)
    from hub_api.modules.perftest_c2c import module as c2c_module

    c2c_contract = c2c_module()
    app.registry.register(c2c_contract)

    # Apply registry to wire blueprints
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def c2c_write_token(app_with_c2c: Quart) -> str:
    """Generate a JWT token with c2c write scopes for testing.

    Args:
        app_with_c2c: App with key provider.

    Returns:
        Encoded JWT token with write scopes.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_c2c.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read c2c:write",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token


@pytest_asyncio.fixture
async def c2c_readonly_token(app_with_c2c: Quart) -> str:
    """Generate a JWT token with c2c read-only scope for testing.

    Args:
        app_with_c2c: App with key provider.

    Returns:
        Encoded JWT token with read-only scope.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_c2c.config["KEY_PROVIDER"]

    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "c2c:read",
    }

    token = await encode_access_token(claims, provider, ttl_hours=1)
    return token
