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
                method="GET", endpoint="/api/v1/status", status_code=200, duration=0.05
            )
        except Exception as exc:
            pytest.fail(f"record_http_request raised: {exc}")

    def test_record_http_request_404(self, metrics):
        try:
            metrics.record_http_request(
                method="GET", endpoint="/api/v1/missing", status_code=404, duration=0.01
            )
        except Exception as exc:
            pytest.fail(f"record_http_request 404 raised: {exc}")

    def test_record_http_request_post(self, metrics):
        try:
            metrics.record_http_request(
                method="POST", endpoint="/api/v1/auth/token", status_code=201, duration=0.1
            )
        except Exception as exc:
            pytest.fail(f"record_http_request POST raised: {exc}")


# ---------------------------------------------------------------------------
# Auth recording
# ---------------------------------------------------------------------------

class TestRecordAuth:
    def test_record_auth_attempt_success(self, metrics):
        try:
            metrics.record_auth_attempt(success=True, node_type="client")
        except Exception as exc:
            pytest.fail(f"record_auth_attempt raised: {exc}")

    def test_record_auth_attempt_failure(self, metrics):
        try:
            metrics.record_auth_attempt(success=False, node_type="headend")
        except Exception as exc:
            pytest.fail(f"record_auth_attempt failure raised: {exc}")

    def test_record_user_login(self, metrics):
        try:
            metrics.record_user_login(success=True, role="admin")
        except Exception as exc:
            pytest.fail(f"record_user_login raised: {exc}")


# ---------------------------------------------------------------------------
# Registration / certificate recording
# ---------------------------------------------------------------------------

class TestRecordRegistration:
    def test_record_client_registration(self, metrics):
        try:
            metrics.record_client_registration(cluster_id="cluster-001")
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
            metrics.record_jwt_validation(success=True)
        except Exception as exc:
            pytest.fail(f"record_jwt_validation raised: {exc}")

    def test_record_jwt_revocation(self, metrics):
        try:
            metrics.record_jwt_revocation()
        except Exception as exc:
            pytest.fail(f"record_jwt_revocation raised: {exc}")


# ---------------------------------------------------------------------------
# Cluster / client stats
# ---------------------------------------------------------------------------

class TestUpdateStats:
    def test_update_cluster_stats(self, metrics):
        try:
            metrics.update_cluster_stats(total=5, active=4, degraded=1)
        except Exception as exc:
            pytest.fail(f"update_cluster_stats raised: {exc}")

    def test_update_client_stats(self, metrics):
        try:
            metrics.update_client_stats(total=100, connected=90, disconnected=10)
        except Exception as exc:
            pytest.fail(f"update_client_stats raised: {exc}")

    def test_update_certificate_stats(self, metrics):
        try:
            metrics.update_certificate_stats(total=50, valid=48, expired=2)
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
            metrics.update_system_resources(cpu_percent=45.0, memory_percent=60.0)
        except Exception as exc:
            pytest.fail(f"update_system_resources raised: {exc}")

    def test_update_uptime(self, metrics):
        try:
            metrics.update_uptime(seconds=3600)
        except Exception as exc:
            pytest.fail(f"update_uptime raised: {exc}")

    def test_set_service_status(self, metrics):
        try:
            metrics.set_service_status(service="hub-api", healthy=True)
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
            metrics.record_redis_operation(operation="GET", duration=0.001)
        except Exception as exc:
            pytest.fail(f"record_redis_operation raised: {exc}")

    def test_record_error(self, metrics):
        try:
            metrics.record_error(error_type="ValueError", endpoint="/api/v1/test")
        except Exception as exc:
            pytest.fail(f"record_error raised: {exc}")


# ---------------------------------------------------------------------------
# Cluster heartbeat
# ---------------------------------------------------------------------------

class TestClusterHeartbeat:
    def test_record_cluster_heartbeat(self, metrics):
        try:
            metrics.record_cluster_heartbeat(cluster_id="cluster-001")
        except Exception as exc:
            pytest.fail(f"record_cluster_heartbeat raised: {exc}")


# ---------------------------------------------------------------------------
# Connection pools
# ---------------------------------------------------------------------------

class TestConnectionPools:
    def test_update_connection_pools(self, metrics):
        try:
            metrics.update_connection_pools(db_pool_size=10, redis_pool_size=5)
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
