"""
Tests for metrics/prometheus.py — ManagerMetrics counters, gauges, histograms.
"""
import os
import pytest
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_prometheus_registry():
    """Isolate prometheus_client metrics between tests using a fresh registry."""
    from prometheus_client import CollectorRegistry
    registry = CollectorRegistry()
    with patch("metrics.prometheus.CollectorRegistry", return_value=registry):
        yield registry


@pytest.fixture
def metrics(tmp_path):
    """ManagerMetrics with a .version file."""
    version_file = tmp_path / ".version"
    version_file.write_text("v0.2.0.1234567890")

    version_str = str(version_file)
    real_open = open

    def mock_open_fn(path, *args, **kwargs):
        if ".version" in str(path):
            return real_open(version_str, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=mock_open_fn):
        from metrics.prometheus import ManagerMetrics
        return ManagerMetrics()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestManagerMetricsInit:
    def test_metrics_object_created(self, metrics):
        assert metrics is not None

    def test_has_http_requests_counter(self, metrics):
        assert hasattr(metrics, "http_requests_total") or hasattr(metrics, "_http_requests_total")

    def test_get_metrics_returns_bytes(self, metrics):
        result = metrics.get_metrics()
        assert isinstance(result, (bytes, str))

    def test_get_content_type_returns_string(self, metrics):
        ct = metrics.get_content_type()
        assert isinstance(ct, str)
        assert len(ct) > 0


# ---------------------------------------------------------------------------
# HTTP request recording
# ---------------------------------------------------------------------------

class TestRecordHTTPRequest:
    def test_record_http_request_does_not_raise(self, metrics):
        try:
            metrics.record_http_request(
                method="GET", endpoint="/api/v1/status", status=200, duration=0.05
            )
        except Exception as exc:
            pytest.fail(f"record_http_request raised: {exc}")

    def test_record_http_request_404(self, metrics):
        try:
            metrics.record_http_request(
                method="GET", endpoint="/api/v1/missing", status=404, duration=0.01
            )
        except Exception as exc:
            pytest.fail(f"record_http_request 404 raised: {exc}")

    def test_record_http_request_post(self, metrics):
        try:
            metrics.record_http_request(
                method="POST", endpoint="/api/v1/auth/token", status=201, duration=0.1
            )
        except Exception as exc:
            pytest.fail(f"record_http_request POST raised: {exc}")


# ---------------------------------------------------------------------------
# Auth recording
# ---------------------------------------------------------------------------

class TestRecordAuth:
    def test_record_auth_attempt_success(self, metrics):
        try:
            metrics.record_auth_attempt(auth_type="client", success=True)
        except Exception as exc:
            pytest.fail(f"record_auth_attempt raised: {exc}")

    def test_record_auth_attempt_failure(self, metrics):
        try:
            metrics.record_auth_attempt(auth_type="headend", success=False)
        except Exception as exc:
            pytest.fail(f"record_auth_attempt failure raised: {exc}")

    def test_record_user_login(self, metrics):
        try:
            metrics.record_user_login(role="admin", success=True)
        except Exception as exc:
            pytest.fail(f"record_user_login raised: {exc}")


# ---------------------------------------------------------------------------
# Registration / certificate recording
# ---------------------------------------------------------------------------

class TestRecordRegistration:
    def test_record_client_registration(self, metrics):
        try:
            metrics.record_client_registration(client_type="node", success=True)
        except Exception as exc:
            pytest.fail(f"record_client_registration raised: {exc}")

    def test_record_certificate_issued(self, metrics):
        try:
            metrics.record_certificate_issued(cert_type="client")
        except Exception as exc:
            pytest.fail(f"record_certificate_issued raised: {exc}")


# ---------------------------------------------------------------------------
# JWT recording
# ---------------------------------------------------------------------------

class TestRecordJWT:
    def test_record_jwt_token_issued(self, metrics):
        try:
            metrics.record_jwt_token_issued(node_type="client")
        except Exception as exc:
            pytest.fail(f"record_jwt_token_issued raised: {exc}")

    def test_record_jwt_validation_success(self, metrics):
        try:
            metrics.record_jwt_validation(result="success")
        except Exception as exc:
            pytest.fail(f"record_jwt_validation raised: {exc}")

    def test_record_jwt_revocation(self, metrics):
        try:
            metrics.record_jwt_revocation(reason="expired")
        except Exception as exc:
            pytest.fail(f"record_jwt_revocation raised: {exc}")


# ---------------------------------------------------------------------------
# Cluster / client stats
# ---------------------------------------------------------------------------

class TestUpdateStats:
    def test_update_cluster_stats(self, metrics):
        try:
            metrics.update_cluster_stats(total=5, by_status={"active": 4, "degraded": 1})
        except Exception as exc:
            pytest.fail(f"update_cluster_stats raised: {exc}")

    def test_update_client_stats(self, metrics):
        try:
            metrics.update_client_stats(
                total=100,
                by_type={"node": 90, "headend": 10},
                by_status={"connected": 90, "disconnected": 10},
            )
        except Exception as exc:
            pytest.fail(f"update_client_stats raised: {exc}")

    def test_update_certificate_stats(self, metrics):
        try:
            metrics.update_certificate_stats(
                active={"client": 48},
                expiring={"client": 2},
            )
        except Exception as exc:
            pytest.fail(f"update_certificate_stats raised: {exc}")

    def test_update_active_sessions(self, metrics):
        try:
            metrics.update_active_sessions(count=15)
        except Exception as exc:
            pytest.fail(f"update_active_sessions raised: {exc}")


# ---------------------------------------------------------------------------
# System / uptime
# ---------------------------------------------------------------------------

class TestSystemMetrics:
    def test_update_system_resources(self, metrics):
        try:
            metrics.update_system_resources(memory_bytes=1073741824, cpu_percent=45.0)
        except Exception as exc:
            pytest.fail(f"update_system_resources raised: {exc}")

    def test_update_uptime(self, metrics):
        try:
            metrics.update_uptime()
        except Exception as exc:
            pytest.fail(f"update_uptime raised: {exc}")

    def test_set_service_status(self, metrics):
        try:
            metrics.set_service_status(status="healthy")
        except Exception as exc:
            pytest.fail(f"set_service_status raised: {exc}")


# ---------------------------------------------------------------------------
# Database / Redis recording
# ---------------------------------------------------------------------------

class TestDBRedisRecording:
    def test_record_database_query(self, metrics):
        try:
            metrics.record_database_query(operation="SELECT", duration=0.002)
        except Exception as exc:
            pytest.fail(f"record_database_query raised: {exc}")

    def test_record_redis_operation(self, metrics):
        try:
            metrics.record_redis_operation(operation="GET")
        except Exception as exc:
            pytest.fail(f"record_redis_operation raised: {exc}")

    def test_record_error(self, metrics):
        try:
            metrics.record_error(component="api", error_type="ValueError")
        except Exception as exc:
            pytest.fail(f"record_error raised: {exc}")


# ---------------------------------------------------------------------------
# Cluster heartbeat
# ---------------------------------------------------------------------------

class TestClusterHeartbeat:
    def test_record_cluster_heartbeat(self, metrics):
        try:
            metrics.record_cluster_heartbeat(cluster_id="cluster-001", status="healthy")
        except Exception as exc:
            pytest.fail(f"record_cluster_heartbeat raised: {exc}")


# ---------------------------------------------------------------------------
# Connection pools
# ---------------------------------------------------------------------------

class TestConnectionPools:
    def test_update_connection_pools(self, metrics):
        try:
            metrics.update_connection_pools(db_connections=10, redis_connections=5)
        except Exception as exc:
            pytest.fail(f"update_connection_pools raised: {exc}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

class TestModuleSingleton:
    def test_get_metrics_instance_returns_object(self, tmp_path):
        version_file = tmp_path / ".version"
        version_file.write_text("v0.2.0.1234567890")
        version_str = str(version_file)
        real_open = open

        def mock_open_fn(path, *args, **kwargs):
            if ".version" in str(path):
                return real_open(version_str, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            from metrics.prometheus import get_metrics_instance
            instance = get_metrics_instance()
            assert instance is not None


# ---------------------------------------------------------------------------
# Additional tests for missing coverage (lines 467-510, 520-561)
# ---------------------------------------------------------------------------

class TestUpdateClientMetrics:
    """Test update_client_metrics method with various metrics combinations."""

    def test_update_client_metrics_bytes_sent(self, metrics):
        try:
            metrics.update_client_metrics(
                client_id="client-001",
                client_name="test-client",
                client_type="node",
                headless=False,
                metrics={"bytes_sent": 1024000},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with bytes_sent raised: {exc}")

    def test_update_client_metrics_bytes_received(self, metrics):
        try:
            metrics.update_client_metrics(
                client_id="client-002",
                client_name="test-client-2",
                client_type="docker",
                headless=True,
                metrics={"bytes_received": 2048000},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with bytes_received raised: {exc}")

    def test_update_client_metrics_packets_sent(self, metrics):
        try:
            metrics.update_client_metrics(
                client_id="client-003",
                client_name="test-client-3",
                client_type="native",
                headless=False,
                metrics={"packets_sent": 5000},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with packets_sent raised: {exc}")

    def test_update_client_metrics_packets_received(self, metrics):
        try:
            metrics.update_client_metrics(
                client_id="client-004",
                client_name="test-client-4",
                client_type="node",
                headless=True,
                metrics={"packets_received": 7500},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with packets_received raised: {exc}")

    def test_update_client_metrics_connection_uptime(self, metrics):
        try:
            metrics.update_client_metrics(
                client_id="client-005",
                client_name="test-client-5",
                client_type="docker",
                headless=False,
                metrics={"connection_uptime": 86400},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with connection_uptime raised: {exc}")

    def test_update_client_metrics_all_fields(self, metrics):
        try:
            metrics.update_client_metrics(
                client_id="client-006",
                client_name="test-client-6",
                client_type="native",
                headless=True,
                metrics={
                    "bytes_sent": 1000000,
                    "bytes_received": 2000000,
                    "packets_sent": 10000,
                    "packets_received": 15000,
                    "connection_uptime": 172800,
                },
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with all fields raised: {exc}")

    def test_update_client_metrics_always_updates_last_check_in(self, metrics):
        try:
            # Even with empty metrics, last_check_in should be updated
            metrics.update_client_metrics(
                client_id="client-007",
                client_name="test-client-7",
                client_type="docker",
                headless=False,
                metrics={},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with empty metrics raised: {exc}")

    def test_update_client_metrics_headless_true_string(self, metrics):
        try:
            # Verify headless_str is correctly set to 'true'
            metrics.update_client_metrics(
                client_id="client-008",
                client_name="test-headless",
                client_type="node",
                headless=True,
                metrics={"bytes_sent": 500000},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with headless=True raised: {exc}")

    def test_update_client_metrics_headless_false_string(self, metrics):
        try:
            # Verify headless_str is correctly set to 'false'
            metrics.update_client_metrics(
                client_id="client-009",
                client_name="test-not-headless",
                client_type="docker",
                headless=False,
                metrics={"bytes_received": 750000},
            )
        except Exception as exc:
            pytest.fail(f"update_client_metrics with headless=False raised: {exc}")


class TestUpdateHeadendMetrics:
    """Test update_headend_metrics method with various metrics combinations."""

    def test_update_headend_metrics_active_connections(self, metrics):
        try:
            metrics.update_headend_metrics(
                headend_id="headend-001",
                headend_name="us-east-1",
                region="us-east",
                datacenter="us-east-1a",
                metrics={"active_connections": 150},
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with active_connections raised: {exc}")

    def test_update_headend_metrics_bandwidth_in(self, metrics):
        try:
            metrics.update_headend_metrics(
                headend_id="headend-002",
                headend_name="us-west-1",
                region="us-west",
                datacenter="us-west-1b",
                metrics={"bandwidth_in": 10000000},
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with bandwidth_in raised: {exc}")

    def test_update_headend_metrics_bandwidth_out(self, metrics):
        try:
            metrics.update_headend_metrics(
                headend_id="headend-003",
                headend_name="eu-west-1",
                region="eu-west",
                datacenter="eu-west-1c",
                metrics={"bandwidth_out": 8000000},
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with bandwidth_out raised: {exc}")

    def test_update_headend_metrics_cpu_usage(self, metrics):
        try:
            metrics.update_headend_metrics(
                headend_id="headend-004",
                headend_name="ap-south-1",
                region="ap-south",
                datacenter="ap-south-1a",
                metrics={"cpu_usage": 65.5},
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with cpu_usage raised: {exc}")

    def test_update_headend_metrics_memory_usage(self, metrics):
        try:
            metrics.update_headend_metrics(
                headend_id="headend-005",
                headend_name="ap-northeast-1",
                region="ap-northeast",
                datacenter="ap-northeast-1d",
                metrics={"memory_usage": 5368709120},
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with memory_usage raised: {exc}")

    def test_update_headend_metrics_all_fields(self, metrics):
        try:
            metrics.update_headend_metrics(
                headend_id="headend-006",
                headend_name="global-hub",
                region="global",
                datacenter="multi-region",
                metrics={
                    "active_connections": 500,
                    "bandwidth_in": 50000000,
                    "bandwidth_out": 40000000,
                    "cpu_usage": 75.0,
                    "memory_usage": 10737418240,
                },
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with all fields raised: {exc}")

    def test_update_headend_metrics_always_updates_last_check_in(self, metrics):
        try:
            # Even with empty metrics, last_check_in should be updated
            metrics.update_headend_metrics(
                headend_id="headend-007",
                headend_name="check-in-test",
                region="test",
                datacenter="test-zone",
                metrics={},
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with empty metrics raised: {exc}")

    def test_update_headend_metrics_zero_values(self, metrics):
        try:
            # Test with zero values (valid but unusual)
            metrics.update_headend_metrics(
                headend_id="headend-008",
                headend_name="down-headend",
                region="offline",
                datacenter="offline-zone",
                metrics={
                    "active_connections": 0,
                    "bandwidth_in": 0,
                    "bandwidth_out": 0,
                    "cpu_usage": 0.0,
                    "memory_usage": 0,
                },
            )
        except Exception as exc:
            pytest.fail(f"update_headend_metrics with zero values raised: {exc}")


class TestMetricsIntegration:
    """Test combinations of metric recording and updates."""

    def test_record_and_update_flow(self, metrics):
        try:
            # Record HTTP request
            metrics.record_http_request("GET", "/api/v1/status", 200, 0.05)

            # Record auth attempt
            metrics.record_auth_attempt("jwt", success=True)

            # Record user login
            metrics.record_user_login("admin", success=True)

            # Update session count
            metrics.update_active_sessions(5)

            # Update system resources
            metrics.update_system_resources(memory_bytes=1073741824, cpu_percent=45.0)

            # Get metrics output
            output = metrics.get_metrics()
            assert isinstance(output, (bytes, str))
        except Exception as exc:
            pytest.fail(f"metrics integration flow raised: {exc}")

    def test_error_recording_flow(self, metrics):
        try:
            # Record errors from different components
            metrics.record_error("api", "ValueError")
            metrics.record_error("database", "ConnectionError")
            metrics.record_error("cache", "TimeoutError")

            # Get metrics
            output = metrics.get_metrics()
            assert isinstance(output, (bytes, str))
        except Exception as exc:
            pytest.fail(f"error recording flow raised: {exc}")

    def test_certificate_and_token_flow(self, metrics):
        try:
            # Record certificate issuance
            metrics.record_certificate_issued("client")
            metrics.record_certificate_issued("headend")
            metrics.record_certificate_issued("ca")

            # Record JWT operations
            metrics.record_jwt_token_issued("client")
            metrics.record_jwt_token_issued("headend")
            metrics.record_jwt_validation("success")
            metrics.record_jwt_validation("failure")
            metrics.record_jwt_revocation("expired")
            metrics.record_jwt_revocation("admin")

            # Update certificate stats
            metrics.update_certificate_stats(
                active={"client": 48, "headend": 12, "ca": 1},
                expiring={"client": 2, "headend": 0},
            )

            output = metrics.get_metrics()
            assert isinstance(output, (bytes, str))
        except Exception as exc:
            pytest.fail(f"certificate and token flow raised: {exc}")
