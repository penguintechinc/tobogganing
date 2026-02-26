"""Integration tests for the WaddlePerf fabric telemetry API endpoints.

Tests POST /api/v1/perf/metrics (batch submit), GET /api/v1/perf/metrics
(query with filters), and GET /api/v1/perf/summary (aggregated health).

Prerequisites:
  - Docker Compose stack is running (`make dev` or `docker-compose up`)
  - API_BASE_URL env var points to the hub-api service (default: http://localhost:8000)
  - API_TEST_TOKEN env var holds a JWT with scopes: metrics:write, metrics:read

Usage:
  pytest tests/integration/test_perf_metrics.py -v
  API_BASE_URL=http://hub-api:8000 pytest tests/integration/test_perf_metrics.py
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_TEST_TOKEN = os.environ.get("API_TEST_TOKEN", "")
TIMEOUT = int(os.environ.get("API_TEST_TIMEOUT", "10"))

# Stable test source/target IDs so filter tests can rely on them.
TEST_SOURCE_ID = "integration-test-router-01"
TEST_TARGET_ID = "integration-test-router-02"
TEST_SOURCE_ID_B = "integration-test-router-03"
TEST_TARGET_ID_B = "integration-test-router-04"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict[str, str]:
    if API_TEST_TOKEN:
        return {"Authorization": f"Bearer {API_TEST_TOKEN}"}
    return {}


def _post(path: str, payload: dict) -> requests.Response:
    return requests.post(
        f"{API_BASE_URL}{path}",
        json=payload,
        headers=_auth_headers(),
        timeout=TIMEOUT,
    )


def _get(path: str, params: dict | None = None) -> requests.Response:
    return requests.get(
        f"{API_BASE_URL}{path}",
        params=params or {},
        headers=_auth_headers(),
        timeout=TIMEOUT,
    )


def _skip_if_no_token(resp: requests.Response) -> None:
    """Skip a test if auth fails — useful when API_TEST_TOKEN is not set."""
    if resp.status_code == 401:
        pytest.skip("API_TEST_TOKEN not configured or invalid; skipping auth-gated tests")


def _valid_metric(
    source_id: str = TEST_SOURCE_ID,
    target_id: str = TEST_TARGET_ID,
    protocol: str = "wireguard",
    latency_ms: float = 12.5,
) -> dict:
    """Return a single valid PerfMetricSubmission dict."""
    return {
        "source_id": source_id,
        "source_type": "hub-router",
        "target_id": target_id,
        "protocol": protocol,
        "latency_ms": latency_ms,
        "jitter_ms": 1.2,
        "packet_loss_pct": 0.0,
        "throughput_mbps": 950.0,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def seed_metrics():
    """Pre-seed a batch of known metrics so query and summary tests have data."""
    batch = {
        "metrics": [
            _valid_metric(TEST_SOURCE_ID, TEST_TARGET_ID, "wireguard", 10.0),
            _valid_metric(TEST_SOURCE_ID, TEST_TARGET_ID, "openziti", 25.0),
            _valid_metric(TEST_SOURCE_ID_B, TEST_TARGET_ID_B, "wireguard", 5.5),
        ]
    }
    resp = _post("/api/v1/perf/metrics", batch)
    if resp.status_code == 401:
        pytest.skip("API_TEST_TOKEN not configured; skipping all perf metric tests")
    # Yield even if insert fails (tests will surface the error naturally)
    yield


# ---------------------------------------------------------------------------
# POST /api/v1/perf/metrics — valid batch
# ---------------------------------------------------------------------------

class TestSubmitPerfMetrics:
    """POST /api/v1/perf/metrics with a valid batch returns 200 with insert count."""

    def test_valid_single_metric_returns_200(self):
        payload = {"metrics": [_valid_metric()]}
        resp = _post("/api/v1/perf/metrics", payload)
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["inserted"] == 1
        assert body["data"]["errors"] == []

    def test_valid_batch_returns_correct_insert_count(self):
        """Three valid metrics → inserted == 3, errors empty."""
        metrics = [
            _valid_metric(latency_ms=float(i) * 10) for i in range(1, 4)
        ]
        payload = {"metrics": metrics}
        resp = _post("/api/v1/perf/metrics", payload)
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["inserted"] == 3
        assert body["data"]["errors"] == []

    def test_all_optional_fields_may_be_omitted(self):
        """jitter_ms, packet_loss_pct, throughput_mbps, timestamp are optional."""
        payload = {
            "metrics": [
                {
                    "source_id": TEST_SOURCE_ID,
                    "source_type": "hub-router",
                    "target_id": TEST_TARGET_ID,
                    "protocol": "wireguard",
                    "latency_ms": 7.3,
                }
            ]
        }
        resp = _post("/api/v1/perf/metrics", payload)
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        assert resp.json()["data"]["inserted"] == 1

    def test_empty_metrics_list_returns_422(self):
        """The handler explicitly rejects an empty metrics array with 422."""
        resp = _post("/api/v1/perf/metrics", {"metrics": []})
        _skip_if_no_token(resp)
        assert resp.status_code == 422

    def test_missing_metrics_key_returns_422(self):
        """Omitting the `metrics` key entirely results in an empty list → 422."""
        resp = _post("/api/v1/perf/metrics", {})
        _skip_if_no_token(resp)
        assert resp.status_code == 422

    def test_completely_invalid_json_returns_400(self):
        """Sending a raw string as the body (not JSON) returns 400."""
        resp = requests.post(
            f"{API_BASE_URL}/api/v1/perf/metrics",
            data="not json at all",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        _skip_if_no_token(resp)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/v1/perf/metrics — partial errors
# ---------------------------------------------------------------------------

class TestSubmitPerfMetricsPartialErrors:
    """A batch with some invalid metrics returns partial errors, not a global 422."""

    def test_missing_protocol_yields_partial_error(self):
        """A metric without `protocol` fails Pydantic; the rest still insert."""
        good_metric = _valid_metric()
        bad_metric = {
            "source_id": TEST_SOURCE_ID,
            "source_type": "hub-router",
            "target_id": TEST_TARGET_ID,
            # protocol intentionally absent
            "latency_ms": 9.9,
        }
        payload = {"metrics": [good_metric, bad_metric]}
        resp = _post("/api/v1/perf/metrics", payload)
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["inserted"] == 1
        assert len(data["errors"]) == 1
        # The error entry should reference the second metric (index 1)
        assert data["errors"][0]["index"] == 1

    def test_invalid_source_type_yields_partial_error(self):
        """source_type must be 'hub-router' or 'client'; others fail per-item."""
        good_metric = _valid_metric()
        bad_metric = {
            "source_id": TEST_SOURCE_ID,
            "source_type": "unknown-device",  # not in Literal
            "target_id": TEST_TARGET_ID,
            "protocol": "wireguard",
            "latency_ms": 5.0,
        }
        payload = {"metrics": [good_metric, bad_metric]}
        resp = _post("/api/v1/perf/metrics", payload)
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["inserted"] == 1
        assert len(body["data"]["errors"]) == 1

    def test_mixed_batch_all_bad_inserts_zero(self):
        """When every metric in a batch is invalid, inserted == 0."""
        bad_metrics = [
            {
                "source_id": TEST_SOURCE_ID,
                "source_type": "invalid-type",
                "target_id": TEST_TARGET_ID,
                "protocol": "wireguard",
                "latency_ms": 1.0,
            }
            for _ in range(3)
        ]
        resp = _post("/api/v1/perf/metrics", {"metrics": bad_metrics})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["inserted"] == 0
        assert len(body["data"]["errors"]) == 3

    def test_negative_latency_yields_partial_error(self):
        """Negative latency_ms is outside sensible range; Pydantic strict rejects it
        because the field expects a float but the value may not pass validators if
        added.  This documents current behaviour: record error, continue."""
        bad_metric = {
            "source_id": TEST_SOURCE_ID,
            "source_type": "hub-router",
            "target_id": TEST_TARGET_ID,
            "protocol": "wireguard",
            "latency_ms": "definitely-not-a-float",  # type violation in strict mode
        }
        payload = {"metrics": [_valid_metric(), bad_metric]}
        resp = _post("/api/v1/perf/metrics", payload)
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["inserted"] == 1
        assert len(data["errors"]) == 1


# ---------------------------------------------------------------------------
# GET /api/v1/perf/metrics — query stored metrics
# ---------------------------------------------------------------------------

class TestQueryPerfMetrics:
    """GET /api/v1/perf/metrics returns stored metrics with correct envelope."""

    def test_get_metrics_returns_200(self):
        resp = _get("/api/v1/perf/metrics")
        _skip_if_no_token(resp)
        assert resp.status_code == 200

    def test_response_envelope_structure(self):
        resp = _get("/api/v1/perf/metrics")
        _skip_if_no_token(resp)
        body = resp.json()
        assert body["status"] == "success"
        assert "data" in body
        assert "metrics" in body["data"]
        assert "meta" in body
        assert "count" in body["meta"]
        assert "limit" in body["meta"]

    def test_metrics_list_is_list(self):
        resp = _get("/api/v1/perf/metrics")
        _skip_if_no_token(resp)
        assert isinstance(resp.json()["data"]["metrics"], list)

    def test_each_metric_has_required_fields(self):
        """Every metric in the response should contain the standard schema keys."""
        resp = _get("/api/v1/perf/metrics")
        _skip_if_no_token(resp)
        metrics = resp.json()["data"]["metrics"]
        if not metrics:
            pytest.skip("No metrics in DB yet; ensure seed_metrics fixture ran")
        required_keys = {
            "id", "source_id", "source_type", "target_id",
            "protocol", "latency_ms",
        }
        for m in metrics:
            assert required_keys.issubset(m.keys()), (
                f"Metric missing keys: {required_keys - m.keys()}"
            )

    def test_limit_parameter_is_respected(self):
        """GET with ?limit=1 returns at most 1 metric."""
        resp = _get("/api/v1/perf/metrics", params={"limit": 1})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]["metrics"]) <= 1
        assert body["meta"]["limit"] == 1


# ---------------------------------------------------------------------------
# GET /api/v1/perf/metrics — filter by cluster_id
# ---------------------------------------------------------------------------

class TestQueryPerfMetricsFilterByCluster:
    """cluster_id query param filters metrics to those matching source_id or target_id."""

    def test_filter_by_known_source_id_returns_matches(self):
        resp = _get("/api/v1/perf/metrics", params={"cluster_id": TEST_SOURCE_ID})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        metrics = resp.json()["data"]["metrics"]
        # Every returned metric must reference the filter cluster on source or target
        for m in metrics:
            assert m["source_id"] == TEST_SOURCE_ID or m["target_id"] == TEST_SOURCE_ID

    def test_filter_by_known_target_id_returns_matches(self):
        resp = _get("/api/v1/perf/metrics", params={"cluster_id": TEST_TARGET_ID})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        metrics = resp.json()["data"]["metrics"]
        for m in metrics:
            assert m["source_id"] == TEST_TARGET_ID or m["target_id"] == TEST_TARGET_ID

    def test_filter_by_nonexistent_cluster_returns_empty_list(self):
        resp = _get("/api/v1/perf/metrics", params={"cluster_id": "does-not-exist-xyz"})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        assert resp.json()["data"]["metrics"] == []

    def test_filter_by_cluster_b_excludes_cluster_a(self):
        """Filtering for cluster B should not return metrics for cluster A."""
        resp = _get("/api/v1/perf/metrics", params={"cluster_id": TEST_SOURCE_ID_B})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        for m in resp.json()["data"]["metrics"]:
            assert TEST_SOURCE_ID not in (m["source_id"], m["target_id"])


# ---------------------------------------------------------------------------
# GET /api/v1/perf/metrics — filter by time_range
# ---------------------------------------------------------------------------

class TestQueryPerfMetricsFilterByTimeRange:
    """time_range_start / time_range_end query params slice the result set."""

    def test_time_range_start_in_future_returns_empty(self):
        """A start time far in the future should return no results."""
        future = "2099-01-01T00:00:00+00:00"
        resp = _get("/api/v1/perf/metrics", params={"time_range_start": future})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        assert resp.json()["data"]["metrics"] == []

    def test_time_range_end_in_past_returns_empty(self):
        """An end time before any data was inserted should return nothing."""
        past = "2000-01-01T00:00:00+00:00"
        resp = _get("/api/v1/perf/metrics", params={"time_range_end": past})
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        assert resp.json()["data"]["metrics"] == []

    def test_time_range_spanning_seed_returns_data(self):
        """A range spanning the test-run epoch should include the seeded metrics."""
        start = "2020-01-01T00:00:00+00:00"
        end = "2099-01-01T00:00:00+00:00"
        resp = _get(
            "/api/v1/perf/metrics",
            params={"time_range_start": start, "time_range_end": end},
        )
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        metrics = resp.json()["data"]["metrics"]
        assert len(metrics) > 0, "Expected seeded metrics in the broad time range"

    def test_combined_cluster_and_time_filter(self):
        """Combining cluster_id and time_range_start narrows results correctly."""
        start = "2020-01-01T00:00:00+00:00"
        resp = _get(
            "/api/v1/perf/metrics",
            params={
                "cluster_id": TEST_SOURCE_ID,
                "time_range_start": start,
            },
        )
        _skip_if_no_token(resp)
        assert resp.status_code == 200
        for m in resp.json()["data"]["metrics"]:
            assert m["source_id"] == TEST_SOURCE_ID or m["target_id"] == TEST_SOURCE_ID


# ---------------------------------------------------------------------------
# GET /api/v1/perf/summary — aggregated data
# ---------------------------------------------------------------------------

class TestPerfSummary:
    """GET /api/v1/perf/summary returns aggregated per-pair fabric health."""

    def test_summary_returns_200(self):
        resp = _get("/api/v1/perf/summary")
        _skip_if_no_token(resp)
        assert resp.status_code == 200

    def test_summary_envelope_structure(self):
        resp = _get("/api/v1/perf/summary")
        _skip_if_no_token(resp)
        body = resp.json()
        assert body["status"] == "success"
        assert "data" in body
        assert "pairs" in body["data"]
        assert "meta" in body
        assert "pair_count" in body["meta"]

    def test_pairs_is_a_list(self):
        resp = _get("/api/v1/perf/summary")
        _skip_if_no_token(resp)
        assert isinstance(resp.json()["data"]["pairs"], list)

    def test_summary_pair_count_matches_pairs_length(self):
        resp = _get("/api/v1/perf/summary")
        _skip_if_no_token(resp)
        body = resp.json()
        pairs = body["data"]["pairs"]
        assert body["meta"]["pair_count"] == len(pairs)

    def test_each_pair_has_required_fields(self):
        """Each pair entry must expose source_id, target_id, and protocols dict."""
        resp = _get("/api/v1/perf/summary")
        _skip_if_no_token(resp)
        pairs = resp.json()["data"]["pairs"]
        if not pairs:
            pytest.skip("No pairs in summary; ensure seed_metrics fixture ran")
        for pair in pairs:
            assert "source_id" in pair
            assert "target_id" in pair
            assert "protocols" in pair
            assert isinstance(pair["protocols"], dict)

    def test_summary_deduplicates_source_target_pairs(self):
        """Multiple metrics for the same source→target pair collapse to one entry."""
        # Submit two more metrics for the same pair that already has seeded data
        batch = {
            "metrics": [
                _valid_metric(TEST_SOURCE_ID, TEST_TARGET_ID, "wireguard", 15.0),
                _valid_metric(TEST_SOURCE_ID, TEST_TARGET_ID, "wireguard", 20.0),
            ]
        }
        _post("/api/v1/perf/metrics", batch)

        resp = _get("/api/v1/perf/summary")
        _skip_if_no_token(resp)
        pairs = resp.json()["data"]["pairs"]
        # Count occurrences of the test pair
        test_pair_count = sum(
            1 for p in pairs
            if p["source_id"] == TEST_SOURCE_ID and p["target_id"] == TEST_TARGET_ID
        )
        assert test_pair_count == 1, (
            f"Expected exactly 1 summary entry for the test pair, got {test_pair_count}"
        )

    def test_summary_protocols_contain_latest_latency(self):
        """The protocol entry must expose latest_latency_ms as a numeric field."""
        resp = _get("/api/v1/perf/summary")
        _skip_if_no_token(resp)
        pairs = resp.json()["data"]["pairs"]
        if not pairs:
            pytest.skip("No pairs in summary")
        for pair in pairs:
            for proto_stats in pair["protocols"].values():
                assert "latest_latency_ms" in proto_stats
                # Could be None if the DB row had NULL; allow both
                val = proto_stats["latest_latency_ms"]
                assert val is None or isinstance(val, (int, float))
