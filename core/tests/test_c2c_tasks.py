"""Tests for WaddlePerf c2c Celery tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from core.modules.waddleperf_c2c.worker.tasks import (
    _execute_pair,
    _default_engine_factory,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock DAL instance."""
    return MagicMock()


@pytest.fixture
def run_id() -> str:
    """Test run ID."""
    return str(uuid4())


@pytest.fixture
def tenant_id() -> str:
    """Test tenant ID."""
    return "test-tenant-1"


@pytest.fixture
def source_endpoint() -> MagicMock:
    """Mock source endpoint DB object."""
    endpoint = MagicMock()
    endpoint.id = "src-1"
    endpoint.tenant = "test-tenant-1"
    endpoint.region = "us-east-1"
    endpoint.name = "source-1"
    endpoint.engine_url = "http://source.local:8080"
    endpoint.target = "source.local"
    endpoint.api_key_hash = "hash1"
    endpoint.enabled = True
    endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    return endpoint


@pytest.fixture
def dest_endpoint() -> MagicMock:
    """Mock destination endpoint DB object."""
    endpoint = MagicMock()
    endpoint.id = "dst-1"
    endpoint.tenant = "test-tenant-1"
    endpoint.region = "us-west-1"
    endpoint.name = "dest-1"
    endpoint.engine_url = "http://dest.local:8080"
    endpoint.target = "dest.local"
    endpoint.api_key_hash = "hash2"
    endpoint.enabled = True
    endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    return endpoint


@pytest.fixture
def mock_engine_client() -> AsyncMock:
    """Create a mock EngineClient."""
    engine = AsyncMock()
    engine.run_test = AsyncMock(
        return_value={
            "latency_ms": 42.5,
            "throughput": 1000.0,
            "loss_pct": 0.1,
            "output": "Test completed successfully",
        }
    )
    return engine


# ============================================================================
# Tests for _execute_pair
# ============================================================================


class TestExecutePair:
    """Tests for _execute_pair function."""

    def test_execute_pair_success(
        self,
        mock_db: MagicMock,
        run_id: str,
        tenant_id: str,
        source_endpoint: MagicMock,
        dest_endpoint: MagicMock,
        mock_engine_client: AsyncMock,
    ) -> None:
        """Test successful pair execution."""
        # Setup mock db responses
        mock_db.c2c_endpoints.select.side_effect = [
            source_endpoint,  # First call for source
            dest_endpoint,  # Second call for dest
        ]

        # Mock c2c_pair_results.select to return None (new result)
        pair_result = MagicMock()
        pair_result.id = "result-1"
        pair_result.run_id = run_id
        pair_result.source_endpoint_id = source_endpoint.id
        pair_result.dest_endpoint_id = dest_endpoint.id
        pair_result.status = "success"
        pair_result.latency_ms = 42.5
        pair_result.throughput = 1000.0
        pair_result.loss_pct = 0.1
        pair_result.test_output = "Test completed successfully"
        pair_result.measured_at = datetime.now(timezone.utc)

        mock_db.c2c_pair_results.select.return_value = None
        mock_db.c2c_pair_results.create.return_value = pair_result

        # Mock c2c_matrix_runs
        run = MagicMock()
        run.id = run_id
        run.completed_pairs = 0
        run.failed_pairs = 0
        run.total_pairs = 2
        mock_db.c2c_matrix_runs.select.return_value = run

        # Create engine factory
        def engine_factory(source):
            return mock_engine_client

        # Execute
        result = _execute_pair(
            run_id=run_id,
            tenant=tenant_id,
            source_id=source_endpoint.id,
            dest_id=dest_endpoint.id,
            test_type="http",
            db=mock_db,
            engine_factory=engine_factory,
        )

        # Verify result
        assert result["id"] == "result-1"
        assert result["status"] == "success"
        assert result["latency_ms"] == 42.5

        # Verify engine was called with correct args
        mock_engine_client.run_test.assert_called_once_with(
            "http", target=dest_endpoint.target
        )

        # Verify db was updated
        mock_db.c2c_pair_results.create.assert_called_once()

    def test_execute_pair_engine_error(
        self,
        mock_db: MagicMock,
        run_id: str,
        tenant_id: str,
        source_endpoint: MagicMock,
        dest_endpoint: MagicMock,
    ) -> None:
        """Test pair execution with engine error."""
        from core.modules.waddleperf_cluster.services.engine_client import EngineError

        # Setup mock db responses
        mock_db.c2c_endpoints.select.side_effect = [
            source_endpoint,
            dest_endpoint,
        ]

        # Mock pair results
        pair_result = MagicMock()
        pair_result.id = "result-1"
        pair_result.status = "failed"
        pair_result.test_output = "Engine error: Test failed"
        pair_result.measured_at = datetime.now(timezone.utc)

        mock_db.c2c_pair_results.select.return_value = None
        mock_db.c2c_pair_results.create.return_value = pair_result

        # Mock run
        run = MagicMock()
        run.id = run_id
        run.completed_pairs = 0
        run.failed_pairs = 0
        run.total_pairs = 2
        mock_db.c2c_matrix_runs.select.return_value = run

        # Create engine factory that raises
        def engine_factory(source):
            engine = AsyncMock()
            engine.run_test = AsyncMock(
                side_effect=EngineError("Test failed", status_code=500)
            )
            return engine

        # Execute
        result = _execute_pair(
            run_id=run_id,
            tenant=tenant_id,
            source_id=source_endpoint.id,
            dest_id=dest_endpoint.id,
            test_type="http",
            db=mock_db,
            engine_factory=engine_factory,
        )

        # Verify failed result
        assert result["status"] == "failed"
        assert "Engine error" in result["test_output"]

    def test_execute_pair_missing_source_endpoint(
        self,
        mock_db: MagicMock,
        run_id: str,
        tenant_id: str,
        dest_endpoint: MagicMock,
    ) -> None:
        """Test pair execution with missing source endpoint."""
        # Setup mock db responses (source returns None)
        mock_db.c2c_endpoints.select.return_value = None

        # Mock pair results
        pair_result = MagicMock()
        pair_result.id = "result-1"
        pair_result.status = "failed"
        pair_result.test_output = "Source endpoint not found"
        pair_result.measured_at = datetime.now(timezone.utc)

        mock_db.c2c_pair_results.select.return_value = None
        mock_db.c2c_pair_results.create.return_value = pair_result

        # Mock run
        run = MagicMock()
        run.id = run_id
        run.completed_pairs = 0
        run.failed_pairs = 0
        run.total_pairs = 2
        mock_db.c2c_matrix_runs.select.return_value = run

        # Execute
        result = _execute_pair(
            run_id=run_id,
            tenant=tenant_id,
            source_id="missing-src",
            dest_id=dest_endpoint.id,
            test_type="http",
            db=mock_db,
        )

        # Verify failed result
        assert result["status"] == "failed"
        assert "not found" in result["test_output"].lower()

    def test_execute_pair_missing_dest_endpoint(
        self,
        mock_db: MagicMock,
        run_id: str,
        tenant_id: str,
        source_endpoint: MagicMock,
    ) -> None:
        """Test pair execution with missing destination endpoint."""
        # Setup mock db responses (source ok, dest missing)
        mock_db.c2c_endpoints.select.side_effect = [
            source_endpoint,
            None,  # dest returns None
        ]

        # Mock pair results
        pair_result = MagicMock()
        pair_result.id = "result-1"
        pair_result.status = "failed"
        pair_result.test_output = "Destination endpoint not found"
        pair_result.measured_at = datetime.now(timezone.utc)

        mock_db.c2c_pair_results.select.return_value = None
        mock_db.c2c_pair_results.create.return_value = pair_result

        # Mock run
        run = MagicMock()
        run.id = run_id
        run.completed_pairs = 0
        run.failed_pairs = 0
        run.total_pairs = 2
        mock_db.c2c_matrix_runs.select.return_value = run

        # Execute
        result = _execute_pair(
            run_id=run_id,
            tenant=tenant_id,
            source_id=source_endpoint.id,
            dest_id="missing-dst",
            test_type="http",
            db=mock_db,
        )

        # Verify failed result
        assert result["status"] == "failed"
        assert "not found" in result["test_output"].lower()

    def test_execute_pair_idempotent(
        self,
        mock_db: MagicMock,
        run_id: str,
        tenant_id: str,
        source_endpoint: MagicMock,
        dest_endpoint: MagicMock,
    ) -> None:
        """Test that re-running the same pair is idempotent."""
        # Setup mock db responses
        mock_db.c2c_endpoints.select.side_effect = [
            source_endpoint,
            dest_endpoint,
        ]

        # Mock existing pair result (already recorded)
        existing_result = MagicMock()
        existing_result.id = "result-1"
        existing_result.status = "success"
        existing_result.latency_ms = 50.0
        existing_result.measured_at = datetime.now(timezone.utc)

        mock_db.c2c_pair_results.select.return_value = existing_result

        # Mock engine (should not be called due to idempotency check)
        def engine_factory(source):
            raise AssertionError("Engine should not be called if result already exists")

        # Execute
        result = _execute_pair(
            run_id=run_id,
            tenant=tenant_id,
            source_id=source_endpoint.id,
            dest_id=dest_endpoint.id,
            test_type="http",
            db=mock_db,
            engine_factory=engine_factory,
        )

        # Verify idempotent result (returned existing, didn't call create)
        assert result["id"] == "result-1"
        assert result["status"] == "success"
        mock_db.c2c_pair_results.create.assert_not_called()


# ============================================================================
# Tests for Celery Task Import and Structure
# ============================================================================


class TestCeleryTaskStructure:
    """Tests for Celery task setup and import safety."""

    def test_import_celery_app_without_broker(self) -> None:
        """Test importing celery_app without broker configured."""
        # This should not raise even without CELERY_BROKER_URL set
        from core.modules.waddleperf_c2c.worker import celery_app

        assert celery_app is not None

    def test_import_tasks_without_broker(self) -> None:
        """Test importing tasks module without broker configured."""
        # This should not raise
        from core.modules.waddleperf_c2c.worker import tasks

        assert tasks is not None
        assert hasattr(tasks, "run_pair")
        assert hasattr(tasks, "_execute_pair")

    def test_run_pair_has_delay_method(self) -> None:
        """Test that run_pair has .delay() and .apply_async() methods."""
        from core.modules.waddleperf_c2c.worker.tasks import run_pair

        # These should exist (either from Celery or the stub)
        assert hasattr(run_pair, "delay")
        assert hasattr(run_pair, "apply_async")

    @patch.dict("os.environ", {"CELERY_BROKER_URL": "redis://broker:6379/0"})
    def test_run_pair_with_broker_env(self) -> None:
        """Test run_pair task with broker env var set."""
        # Import after setting env
        from core.modules.waddleperf_c2c.worker.celery_app import celery_app

        # Task should have been registered
        assert celery_app is not None


# ============================================================================
# Tests for Utilities
# ============================================================================


class TestConvertUriToSync:
    """Tests for _convert_uri_to_sync utility."""

    def test_convert_postgresql_asyncpg_to_psycopg(self) -> None:
        """Test converting postgresql+asyncpg to postgresql+psycopg."""
        from core.modules.waddleperf_c2c.worker.tasks import _convert_uri_to_sync

        uri = "postgresql+asyncpg://user:pass@localhost:5432/db"
        result = _convert_uri_to_sync(uri)

        assert "postgresql+psycopg://" in result
        assert "asyncpg" not in result

    def test_convert_mysql_aiomysql_to_pymysql(self) -> None:
        """Test converting mysql+aiomysql to mysql+pymysql."""
        from core.modules.waddleperf_c2c.worker.tasks import _convert_uri_to_sync

        uri = "mysql+aiomysql://user:pass@localhost:3306/db"
        result = _convert_uri_to_sync(uri)

        assert "mysql+pymysql://" in result
        assert "aiomysql" not in result

    def test_convert_sqlite_aiosqlite_to_sync(self) -> None:
        """Test converting sqlite+aiosqlite to sqlite."""
        from core.modules.waddleperf_c2c.worker.tasks import _convert_uri_to_sync

        uri = "sqlite+aiosqlite:///test.db"
        result = _convert_uri_to_sync(uri)

        assert "sqlite:///" in result
        assert "aiosqlite" not in result


# ============================================================================
# Tests for Default Engine Factory
# ============================================================================


class TestDefaultEngineFactory:
    """Tests for _default_engine_factory."""

    def test_create_engine_client_from_endpoint(self) -> None:
        """Test creating an EngineClient from an endpoint."""
        endpoint = {
            "engine_url": "http://test.local:8080",
            "api_key_hash": "hash123",
        }

        client = _default_engine_factory(endpoint)

        # Should be an EngineClient instance
        from core.modules.waddleperf_cluster.services.engine_client import EngineClient

        assert isinstance(client, EngineClient)
        assert client.base_url == "http://test.local:8080"
        # api_key should be None (not recoverable from hash)
        assert client.api_key is None
