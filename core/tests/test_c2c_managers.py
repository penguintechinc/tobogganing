"""Tests for C2C manager classes (endpoint, run, matrix)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import json
import pytest

from core.modules.waddleperf_c2c.services.endpoint_manager import (
    EndpointManager,
    authenticate_node_global,
)
from core.modules.waddleperf_c2c.services.run_manager import RunManager
from core.modules.waddleperf_c2c.services.matrix_service import MatrixService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock DAL instance."""
    return MagicMock()


@pytest.fixture
def tenant_id() -> str:
    """Test tenant ID."""
    return "test-tenant-1"


# ============================================================================
# EndpointManager Tests
# ============================================================================

class TestEndpointManager:
    """Tests for EndpointManager."""

    def test_list_endpoints_empty(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test list_endpoints returns empty list when no endpoints."""
        mock_db.c2c_endpoints.select.return_value = None
        manager = EndpointManager(mock_db, tenant_id)

        result = manager.list_endpoints()

        assert result == []
        mock_db.c2c_endpoints.select.assert_called_once_with(tenant=tenant_id)

    def test_list_endpoints_single(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test list_endpoints returns single endpoint."""
        endpoint = MagicMock()
        endpoint.id = "ep-1"
        endpoint.tenant = tenant_id
        endpoint.region = "us-east-1"
        endpoint.name = "endpoint-1"
        endpoint.engine_url = "http://engine1"
        endpoint.target = "target1"
        endpoint.api_key_hash = "hash1"
        endpoint.enabled = True
        endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.select.return_value = endpoint

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.list_endpoints()

        assert len(result) == 1
        assert result[0]["id"] == "ep-1"
        assert result[0]["region"] == "us-east-1"
        assert result[0]["name"] == "endpoint-1"
        assert result[0]["enabled"] is True

    def test_list_endpoints_multiple(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test list_endpoints returns multiple endpoints."""
        ep1 = MagicMock()
        ep1.id = "ep-1"
        ep1.tenant = tenant_id
        ep1.region = "us-east-1"
        ep1.name = "endpoint-1"
        ep1.engine_url = "http://engine1"
        ep1.target = "target1"
        ep1.api_key_hash = "hash1"
        ep1.enabled = True
        ep1.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        ep1.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        ep2 = MagicMock()
        ep2.id = "ep-2"
        ep2.tenant = tenant_id
        ep2.region = "us-west-1"
        ep2.name = "endpoint-2"
        ep2.engine_url = "http://engine2"
        ep2.target = "target2"
        ep2.api_key_hash = "hash2"
        ep2.enabled = False
        ep2.created_at = datetime(2026, 7, 1, 11, 0, 0, tzinfo=timezone.utc)
        ep2.updated_at = datetime(2026, 7, 1, 11, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.select.return_value = [ep1, ep2]

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.list_endpoints()

        assert len(result) == 2
        assert result[0]["id"] == "ep-1"
        assert result[1]["id"] == "ep-2"
        assert result[1]["enabled"] is False

    def test_list_endpoints_enabled_only(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test list_endpoints with enabled_only filter."""
        endpoint = MagicMock()
        endpoint.id = "ep-1"
        endpoint.tenant = tenant_id
        endpoint.region = "us-east-1"
        endpoint.name = "endpoint-1"
        endpoint.engine_url = "http://engine1"
        endpoint.target = "target1"
        endpoint.api_key_hash = "hash1"
        endpoint.enabled = True
        endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.select.return_value = [endpoint]

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.list_endpoints(enabled_only=True)

        assert len(result) == 1
        mock_db.c2c_endpoints.select.assert_called_once_with(
            tenant=tenant_id, enabled=True
        )

    def test_get_endpoint_found(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test get_endpoint returns endpoint if found."""
        endpoint = MagicMock()
        endpoint.id = "ep-1"
        endpoint.tenant = tenant_id
        endpoint.region = "us-east-1"
        endpoint.name = "endpoint-1"
        endpoint.engine_url = "http://engine1"
        endpoint.target = "target1"
        endpoint.api_key_hash = "hash1"
        endpoint.enabled = True
        endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.select.return_value = endpoint

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.get_endpoint("ep-1")

        assert result is not None
        assert result["id"] == "ep-1"
        mock_db.c2c_endpoints.select.assert_called_once_with(
            id="ep-1", tenant=tenant_id
        )

    def test_get_endpoint_not_found(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test get_endpoint returns None if not found."""
        mock_db.c2c_endpoints.select.return_value = None

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.get_endpoint("nonexistent")

        assert result is None

    def test_get_endpoint_tenant_isolation(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test get_endpoint is tenant-scoped."""
        manager = EndpointManager(mock_db, tenant_id)
        manager.get_endpoint("ep-1")

        mock_db.c2c_endpoints.select.assert_called_once_with(
            id="ep-1", tenant=tenant_id
        )

    def test_create_endpoint_with_generated_key(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test create_endpoint generates api_key if not provided."""
        mock_db.c2c_endpoints.select.return_value = None

        endpoint = MagicMock()
        endpoint.id = "ep-1"
        endpoint.tenant = tenant_id
        endpoint.region = "us-east-1"
        endpoint.name = "endpoint-1"
        endpoint.engine_url = "http://engine1"
        endpoint.target = "target1"
        endpoint.api_key_hash = "somehash"
        endpoint.enabled = True
        endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.create.return_value = endpoint

        manager = EndpointManager(mock_db, tenant_id)
        result, raw_key = manager.create_endpoint(
            region="us-east-1",
            name="endpoint-1",
            engine_url="http://engine1",
            target="target1",
        )

        assert result["id"] == "ep-1"
        assert raw_key is not None
        assert len(raw_key) > 20

    def test_create_endpoint_with_provided_key(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test create_endpoint uses provided api_key."""
        mock_db.c2c_endpoints.select.return_value = None

        endpoint = MagicMock()
        endpoint.id = "ep-1"
        endpoint.tenant = tenant_id
        endpoint.region = "us-east-1"
        endpoint.name = "endpoint-1"
        endpoint.engine_url = "http://engine1"
        endpoint.target = "target1"
        endpoint.api_key_hash = "provided_hash"
        endpoint.enabled = True
        endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.create.return_value = endpoint

        manager = EndpointManager(mock_db, tenant_id)
        result, raw_key = manager.create_endpoint(
            region="us-east-1",
            name="endpoint-1",
            engine_url="http://engine1",
            target="target1",
            api_key="my-custom-key",
        )

        assert result["id"] == "ep-1"
        assert raw_key is None

    def test_create_endpoint_duplicate_raises(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test create_endpoint raises ValueError on duplicate (tenant, region, name)."""
        existing = MagicMock()
        mock_db.c2c_endpoints.select.return_value = existing

        manager = EndpointManager(mock_db, tenant_id)

        with pytest.raises(ValueError, match="already exists"):
            manager.create_endpoint(
                region="us-east-1",
                name="endpoint-1",
                engine_url="http://engine1",
                target="target1",
            )

    def test_update_endpoint_success(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test update_endpoint successfully updates allowed fields."""
        existing = MagicMock()
        existing.id = "ep-1"
        existing.tenant = tenant_id

        updated = MagicMock()
        updated.id = "ep-1"
        updated.tenant = tenant_id
        updated.region = "us-east-1"
        updated.name = "updated-name"
        updated.engine_url = "http://engine-new"
        updated.target = "target-new"
        updated.api_key_hash = "hash1"
        updated.enabled = False
        updated.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        updated.updated_at = datetime(2026, 7, 1, 11, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.select.side_effect = [existing, updated]

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.update_endpoint(
            "ep-1", name="updated-name", enabled=False
        )

        assert result is not None
        assert result["name"] == "updated-name"
        assert result["enabled"] is False

    def test_update_endpoint_not_found(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test update_endpoint returns None if endpoint not found."""
        mock_db.c2c_endpoints.select.return_value = None

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.update_endpoint("nonexistent", name="new-name")

        assert result is None

    def test_delete_endpoint_success(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test delete_endpoint successfully deletes endpoint."""
        existing = MagicMock()
        mock_db.c2c_endpoints.select.return_value = existing

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.delete_endpoint("ep-1")

        assert result is True
        mock_db.c2c_endpoints.delete.assert_called_once_with(
            id="ep-1", tenant=tenant_id
        )

    def test_delete_endpoint_not_found(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test delete_endpoint returns False if endpoint not found."""
        mock_db.c2c_endpoints.select.return_value = None

        manager = EndpointManager(mock_db, tenant_id)
        result = manager.delete_endpoint("nonexistent")

        assert result is False


# ============================================================================
# authenticate_node_global Tests
# ============================================================================

class TestAuthenticateNodeGlobal:
    """Tests for authenticate_node_global function."""

    def test_authenticate_node_global_success(
        self, mock_db: MagicMock
    ) -> None:
        """Test authenticate_node_global returns endpoint and tenant on success."""
        import hashlib

        test_key = "test-key-12345"
        test_key_hash = hashlib.sha256(test_key.encode()).hexdigest()

        endpoint = MagicMock()
        endpoint.id = "ep-1"
        endpoint.tenant = "some-tenant"
        endpoint.region = "us-east-1"
        endpoint.name = "endpoint-1"
        endpoint.engine_url = "http://engine1"
        endpoint.target = "target1"
        endpoint.api_key_hash = test_key_hash
        endpoint.enabled = True
        endpoint.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        endpoint.updated_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_endpoints.select.return_value = endpoint

        result = authenticate_node_global(mock_db, test_key)

        assert result is not None
        endpoint_dict, tenant = result
        assert endpoint_dict["id"] == "ep-1"
        assert tenant == "some-tenant"

    def test_authenticate_node_global_invalid_key(
        self, mock_db: MagicMock
    ) -> None:
        """Test authenticate_node_global returns None for invalid key."""
        mock_db.c2c_endpoints.select.return_value = None

        result = authenticate_node_global(mock_db, "invalid-key")

        assert result is None

    def test_authenticate_node_global_disabled_endpoint(
        self, mock_db: MagicMock
    ) -> None:
        """Test authenticate_node_global returns None if endpoint disabled."""
        endpoint = MagicMock()
        endpoint.id = "ep-1"
        endpoint.tenant = "some-tenant"
        endpoint.enabled = False
        endpoint.api_key_hash = "somehash"

        mock_db.c2c_endpoints.select.return_value = endpoint

        result = authenticate_node_global(mock_db, "test-key")

        assert result is None


# ============================================================================
# RunManager Tests
# ============================================================================

class TestRunManager:
    """Tests for RunManager."""

    def test_create_run_success(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test create_run creates run and generates pairs."""
        ep1 = MagicMock()
        ep1.id = "ep-1"
        ep1.region = "us-east-1"

        ep2 = MagicMock()
        ep2.id = "ep-2"
        ep2.region = "us-west-1"

        mock_db.c2c_endpoints.select.return_value = [ep1, ep2]

        run = MagicMock()
        run.id = "run-1"
        run.tenant = tenant_id
        run.status = "pending"
        run.test_types = json.dumps(["latency", "throughput"])
        run.total_pairs = 4
        run.completed_pairs = 0
        run.failed_pairs = 0
        run.created_by = "user-1"
        run.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        run.started_at = None
        run.completed_at = None

        mock_db.c2c_matrix_runs.create.return_value = run

        manager = RunManager(mock_db, tenant_id)
        run_dict, pairs = manager.create_run(
            test_types=["latency", "throughput"],
            created_by="user-1",
        )

        assert run_dict["id"] == "run-1"
        assert run_dict["total_pairs"] == 4
        # 2 endpoints -> 2 permutations (1->2, 2->1) * 2 test types = 4 pairs
        assert len(pairs) == 4

    def test_create_run_insufficient_endpoints(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test create_run raises ValueError with <2 endpoints."""
        ep1 = MagicMock()
        ep1.id = "ep-1"

        mock_db.c2c_endpoints.select.return_value = [ep1]

        manager = RunManager(mock_db, tenant_id)

        with pytest.raises(ValueError, match="need at least 2"):
            manager.create_run(test_types=["latency"])

    def test_create_run_with_endpoint_ids_filter(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test create_run filters endpoints by endpoint_ids."""
        ep1 = MagicMock()
        ep1.id = "ep-1"
        ep1.region = "us-east-1"

        ep2 = MagicMock()
        ep2.id = "ep-2"
        ep2.region = "us-west-1"

        ep3 = MagicMock()
        ep3.id = "ep-3"
        ep3.region = "eu-west-1"

        mock_db.c2c_endpoints.select.return_value = [ep1, ep2, ep3]

        run = MagicMock()
        run.id = "run-1"
        run.tenant = tenant_id
        run.status = "pending"
        run.test_types = json.dumps(["latency"])
        run.total_pairs = 2
        run.completed_pairs = 0
        run.failed_pairs = 0
        run.created_by = None
        run.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        run.started_at = None
        run.completed_at = None

        mock_db.c2c_matrix_runs.create.return_value = run

        manager = RunManager(mock_db, tenant_id)
        run_dict, pairs = manager.create_run(
            test_types=["latency"],
            endpoint_ids=["ep-1", "ep-2"],
        )

        # Should only use ep-1 and ep-2
        assert len(pairs) == 2

    def test_get_run_found(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test get_run returns run if found."""
        run = MagicMock()
        run.id = "run-1"
        run.tenant = tenant_id
        run.status = "pending"
        run.test_types = json.dumps(["latency"])
        run.total_pairs = 2
        run.completed_pairs = 0
        run.failed_pairs = 0
        run.created_by = "user-1"
        run.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        run.started_at = None
        run.completed_at = None

        mock_db.c2c_matrix_runs.select.return_value = run

        manager = RunManager(mock_db, tenant_id)
        result = manager.get_run("run-1")

        assert result is not None
        assert result["id"] == "run-1"

    def test_get_run_not_found(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test get_run returns None if not found."""
        mock_db.c2c_matrix_runs.select.return_value = None

        manager = RunManager(mock_db, tenant_id)
        result = manager.get_run("nonexistent")

        assert result is None

    def test_list_runs(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test list_runs returns all runs for tenant."""
        run1 = MagicMock()
        run1.id = "run-1"
        run1.tenant = tenant_id
        run1.status = "completed"
        run1.test_types = json.dumps(["latency"])
        run1.total_pairs = 2
        run1.completed_pairs = 2
        run1.failed_pairs = 0
        run1.created_by = "user-1"
        run1.created_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        run1.started_at = datetime(2026, 7, 1, 10, 1, 0, tzinfo=timezone.utc)
        run1.completed_at = datetime(2026, 7, 1, 10, 2, 0, tzinfo=timezone.utc)

        run2 = MagicMock()
        run2.id = "run-2"
        run2.tenant = tenant_id
        run2.status = "pending"
        run2.test_types = json.dumps(["throughput"])
        run2.total_pairs = 2
        run2.completed_pairs = 0
        run2.failed_pairs = 0
        run2.created_by = "user-2"
        run2.created_at = datetime(2026, 7, 1, 11, 0, 0, tzinfo=timezone.utc)
        run2.started_at = None
        run2.completed_at = None

        mock_db.c2c_matrix_runs.select.return_value = [run1, run2]

        manager = RunManager(mock_db, tenant_id)
        result = manager.list_runs()

        assert len(result) == 2
        assert result[0]["id"] == "run-1"
        assert result[1]["id"] == "run-2"

    def test_mark_running(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test mark_running updates run status."""
        manager = RunManager(mock_db, tenant_id)
        manager.mark_running("run-1")

        call_kwargs = mock_db.c2c_matrix_runs.update.call_args[1]
        assert call_kwargs["status"] == "running"
        assert call_kwargs["started_at"] is not None

    def test_mark_complete(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test mark_complete updates run status."""
        manager = RunManager(mock_db, tenant_id)
        manager.mark_complete("run-1")

        call_kwargs = mock_db.c2c_matrix_runs.update.call_args[1]
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["completed_at"] is not None

    def test_record_pair_result_new(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test record_pair_result creates new result and increments counters."""
        # First call returns None (new result)
        mock_db.c2c_pair_results.select.return_value = None

        run = MagicMock()
        run.id = "run-1"
        run.tenant = tenant_id
        run.completed_pairs = 0
        run.total_pairs = 4
        run.failed_pairs = 0

        mock_db.c2c_matrix_runs.select.return_value = run

        pair_result = MagicMock()
        pair_result.id = "result-1"
        pair_result.tenant = tenant_id
        pair_result.run_id = "run-1"
        pair_result.source_endpoint_id = "ep-1"
        pair_result.dest_endpoint_id = "ep-2"
        pair_result.source_region = "us-east-1"
        pair_result.dest_region = "us-west-1"
        pair_result.test_type = "latency"
        pair_result.status = "success"
        pair_result.latency_ms = 42.5
        pair_result.throughput = None
        pair_result.loss_pct = None
        pair_result.test_output = "test output"
        pair_result.measured_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_pair_results.create.return_value = pair_result

        manager = RunManager(mock_db, tenant_id)
        result = manager.record_pair_result(
            run_id="run-1",
            source_id="ep-1",
            dest_id="ep-2",
            source_region="us-east-1",
            dest_region="us-west-1",
            test_type="latency",
            status="success",
            latency_ms=42.5,
        )

        assert result["id"] == "result-1"
        # Verify counters incremented
        update_call = mock_db.c2c_matrix_runs.update.call_args_list[0]
        assert update_call[1]["completed_pairs"] == 1
        assert update_call[1]["failed_pairs"] == 0

    def test_record_pair_result_idempotent(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test record_pair_result is idempotent."""
        existing = MagicMock()
        existing.id = "result-1"
        existing.tenant = tenant_id
        existing.run_id = "run-1"
        existing.source_endpoint_id = "ep-1"
        existing.dest_endpoint_id = "ep-2"
        existing.source_region = "us-east-1"
        existing.dest_region = "us-west-1"
        existing.test_type = "latency"
        existing.status = "success"
        existing.latency_ms = 42.5
        existing.throughput = None
        existing.loss_pct = None
        existing.test_output = "output"
        existing.measured_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_pair_results.select.return_value = existing

        manager = RunManager(mock_db, tenant_id)
        result = manager.record_pair_result(
            run_id="run-1",
            source_id="ep-1",
            dest_id="ep-2",
            source_region="us-east-1",
            dest_region="us-west-1",
            test_type="latency",
            status="success",
            latency_ms=42.5,
        )

        # Should NOT call create or update
        assert result["id"] == "result-1"
        mock_db.c2c_pair_results.create.assert_not_called()
        mock_db.c2c_matrix_runs.update.assert_not_called()

    def test_record_pair_result_failed_status(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test record_pair_result increments failed_pairs for failed status."""
        mock_db.c2c_pair_results.select.return_value = None

        run = MagicMock()
        run.id = "run-1"
        run.tenant = tenant_id
        run.completed_pairs = 0
        run.total_pairs = 2
        run.failed_pairs = 0

        mock_db.c2c_matrix_runs.select.return_value = run

        pair_result = MagicMock()
        pair_result.id = "result-1"
        pair_result.tenant = tenant_id
        pair_result.run_id = "run-1"
        pair_result.source_endpoint_id = "ep-1"
        pair_result.dest_endpoint_id = "ep-2"
        pair_result.source_region = "us-east-1"
        pair_result.dest_region = "us-west-1"
        pair_result.test_type = "latency"
        pair_result.status = "failed"
        pair_result.latency_ms = None
        pair_result.throughput = None
        pair_result.loss_pct = None
        pair_result.test_output = "error output"
        pair_result.measured_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_pair_results.create.return_value = pair_result

        manager = RunManager(mock_db, tenant_id)
        result = manager.record_pair_result(
            run_id="run-1",
            source_id="ep-1",
            dest_id="ep-2",
            source_region="us-east-1",
            dest_region="us-west-1",
            test_type="latency",
            status="failed",
        )

        # Verify failed_pairs incremented
        update_call = mock_db.c2c_matrix_runs.update.call_args_list[0]
        assert update_call[1]["failed_pairs"] == 1

    def test_enqueue_run_with_dispatch(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test enqueue_run calls dispatch for each pair."""
        dispatch_mock = MagicMock()

        manager = RunManager(mock_db, tenant_id)
        pairs = [
            ("ep-1", "ep-2", "latency"),
            ("ep-2", "ep-1", "latency"),
        ]
        count = manager.enqueue_run("run-1", pairs, dispatch=dispatch_mock)

        assert count == 2
        assert dispatch_mock.call_count == 2

        # Verify dispatch called with correct kwargs
        calls = dispatch_mock.call_args_list
        assert calls[0][1]["run_id"] == "run-1"
        assert calls[0][1]["tenant"] == tenant_id
        assert calls[0][1]["source_id"] == "ep-1"
        assert calls[0][1]["dest_id"] == "ep-2"
        assert calls[0][1]["test_type"] == "latency"


# ============================================================================
# MatrixService Tests
# ============================================================================

class TestMatrixService:
    """Tests for MatrixService."""

    def test_latest_matrix_empty(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test latest_matrix returns empty grid when no results."""
        mock_db.c2c_pair_results.select.return_value = None

        service = MatrixService(mock_db, tenant_id)
        result = service.latest_matrix("latency")

        assert result["test_type"] == "latency"
        assert result["regions"] == []
        assert result["cells"] == []

    def test_latest_matrix_single_result(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test latest_matrix builds grid with single result."""
        pair_result = MagicMock()
        pair_result.source_region = "us-east-1"
        pair_result.dest_region = "us-west-1"
        pair_result.status = "success"
        pair_result.latency_ms = 42.5
        pair_result.throughput = None
        pair_result.loss_pct = None
        pair_result.measured_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_pair_results.select.return_value = [pair_result]

        service = MatrixService(mock_db, tenant_id)
        result = service.latest_matrix("latency")

        assert len(result["regions"]) == 2
        assert "us-east-1" in result["regions"]
        assert "us-west-1" in result["regions"]
        assert len(result["cells"]) == 1
        assert result["cells"][0]["source"] == "us-east-1"
        assert result["cells"][0]["dest"] == "us-west-1"

    def test_latest_matrix_multiple_results_keeps_latest(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test latest_matrix keeps only latest result per pair."""
        result1 = MagicMock()
        result1.source_region = "us-east-1"
        result1.dest_region = "us-west-1"
        result1.status = "success"
        result1.latency_ms = 42.5
        result1.throughput = None
        result1.loss_pct = None
        result1.measured_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        result2 = MagicMock()
        result2.source_region = "us-east-1"
        result2.dest_region = "us-west-1"
        result2.status = "success"
        result2.latency_ms = 50.0
        result2.throughput = None
        result2.loss_pct = None
        result2.measured_at = datetime(2026, 7, 1, 10, 1, 0, tzinfo=timezone.utc)

        mock_db.c2c_pair_results.select.return_value = [result1, result2]

        service = MatrixService(mock_db, tenant_id)
        result = service.latest_matrix("latency")

        assert len(result["cells"]) == 1
        assert result["cells"][0]["latency_ms"] == 50.0

    def test_run_matrix(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test run_matrix builds grid for a specific run."""
        result1 = MagicMock()
        result1.source_region = "us-east-1"
        result1.dest_region = "us-west-1"
        result1.test_type = "latency"
        result1.status = "success"
        result1.latency_ms = 42.5
        result1.throughput = None
        result1.loss_pct = None
        result1.measured_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        result2 = MagicMock()
        result2.source_region = "us-west-1"
        result2.dest_region = "us-east-1"
        result2.test_type = "throughput"
        result2.status = "success"
        result2.latency_ms = None
        result2.throughput = 100.0
        result2.loss_pct = None
        result2.measured_at = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_db.c2c_pair_results.select.return_value = [result1, result2]

        service = MatrixService(mock_db, tenant_id)
        result = service.run_matrix("run-1")

        assert result["run_id"] == "run-1"
        assert len(result["regions"]) == 2
        assert set(result["test_types"]) == {"latency", "throughput"}
        assert len(result["cells"]) == 2

    def test_trends(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test trends returns recent pair results."""
        results = [
            MagicMock(
                measured_at=datetime(2026, 7, 1, 10, i, 0, tzinfo=timezone.utc),
                latency_ms=40.0 + i,
                throughput=None,
                loss_pct=None,
                status="success",
            )
            for i in range(5)
        ]

        mock_db.c2c_pair_results.select.return_value = results

        service = MatrixService(mock_db, tenant_id)
        trend_results = service.trends(
            source_region="us-east-1",
            dest_region="us-west-1",
            test_type="latency",
            window=5,
        )

        assert len(trend_results) == 5
        assert trend_results[0]["latency_ms"] == 40.0
        assert trend_results[-1]["latency_ms"] == 44.0

    def test_trends_window_limit(
        self, mock_db: MagicMock, tenant_id: str
    ) -> None:
        """Test trends respects window parameter."""
        results = [
            MagicMock(
                measured_at=datetime(2026, 7, 1, 10, i, 0, tzinfo=timezone.utc),
                latency_ms=40.0 + i,
                throughput=None,
                loss_pct=None,
                status="success",
            )
            for i in range(10)
        ]

        mock_db.c2c_pair_results.select.return_value = results

        service = MatrixService(mock_db, tenant_id)
        trend_results = service.trends(
            source_region="us-east-1",
            dest_region="us-west-1",
            test_type="latency",
            window=3,
        )

        assert len(trend_results) == 3
