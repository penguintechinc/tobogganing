"""Integration tests for Pydantic-validated API endpoints.

These tests exercise the hub-api policy and client registration endpoints
against a live Docker Compose environment.  They validate that the Pydantic
schemas correctly accept well-formed payloads and reject invalid ones with
HTTP 422 and structured error details.

Prerequisites:
  - Docker Compose stack is running (`make dev` or `docker-compose up`)
  - API_BASE_URL env var points to the hub-api service (default: http://localhost:8000)
  - API_TEST_TOKEN env var holds a JWT with scope covering:
      policies:write, policies:read, clients:write

Usage:
  pytest tests/integration/test_pydantic_api.py -v
  API_BASE_URL=http://hub-api:8000 pytest tests/integration/test_pydantic_api.py
"""

from __future__ import annotations

import os

import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")

# A JWT issued by the hub-api with broad scopes for integration testing.
# In a real CI environment this would be minted by a fixture or test-mode
# endpoint.  Set API_TEST_TOKEN in your environment or .env file.
API_TEST_TOKEN = os.environ.get("API_TEST_TOKEN", "")

TIMEOUT = int(os.environ.get("API_TEST_TIMEOUT", "10"))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict[str, str]:
    """Return Authorization header if a token is configured."""
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


def _put(path: str, payload: dict) -> requests.Response:
    return requests.put(
        f"{API_BASE_URL}{path}",
        json=payload,
        headers=_auth_headers(),
        timeout=TIMEOUT,
    )


def _get(path: str, params: dict | None = None) -> requests.Response:
    return requests.get(
        f"{API_BASE_URL}{path}",
        params=params,
        headers=_auth_headers(),
        timeout=TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def created_policy_id(request) -> int:
    """Create a valid policy rule and return its ID for use in later tests."""
    payload = {
        "name": "integration-test-allow-web",
        "action": "allow",
        "priority": 100,
        "scope": "both",
        "direction": "inbound",
        "protocol": "tcp",
        "src_cidrs": ["10.0.0.0/8"],
        "ports": ["80", "443"],
        "enabled": True,
    }
    resp = _post("/api/v1/policies", payload)
    # If auth is not set up, tests may return 401 — skip rather than fail.
    if resp.status_code == 401:
        pytest.skip("API_TEST_TOKEN not configured or invalid; skipping auth-gated tests")
    assert resp.status_code == 201, f"Setup: expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    policy_id = data["data"]["id"]
    yield policy_id
    # Teardown: best-effort delete
    requests.delete(
        f"{API_BASE_URL}/api/v1/policies/{policy_id}",
        headers=_auth_headers(),
        timeout=TIMEOUT,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/policies — valid payload
# ---------------------------------------------------------------------------

class TestCreatePolicyValid:
    """POST /api/v1/policies with fully-valid JSON returns 201 with validated data."""

    def test_minimal_required_fields_returns_201(self):
        """Only `name` is required; all other fields have sensible defaults."""
        payload = {"name": "integration-test-minimal"}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "success"
        assert "data" in body
        assert body["data"]["name"] == "integration-test-minimal"
        # Cleanup
        requests.delete(
            f"{API_BASE_URL}/api/v1/policies/{body['data']['id']}",
            headers=_auth_headers(),
            timeout=TIMEOUT,
        )

    def test_full_valid_payload_returns_201_with_all_fields(self):
        """Full payload round-trips correctly and all fields appear in response."""
        payload = {
            "name": "integration-test-full",
            "description": "Created by integration test",
            "action": "deny",
            "priority": 50,
            "scope": "wireguard",
            "direction": "outbound",
            "protocol": "udp",
            "src_cidrs": ["192.168.1.0/24", "10.10.0.0/16"],
            "dst_cidrs": ["0.0.0.0/0"],
            "ports": ["53", "123", "500-600"],
            "domains": ["example.com", "*.internal.corp"],
            "users": ["alice@example.com"],
            "groups": ["vpn-users"],
            "identity_provider": "oidc",
            "enabled": False,
        }
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 201
        body = resp.json()
        data = body["data"]
        assert data["action"] == "deny"
        assert data["priority"] == 50
        assert data["protocol"] == "udp"
        assert data["enabled"] is False
        # Cleanup
        requests.delete(
            f"{API_BASE_URL}/api/v1/policies/{data['id']}",
            headers=_auth_headers(),
            timeout=TIMEOUT,
        )

    def test_response_envelope_structure(self):
        """Response must follow {status, data, ...} envelope convention."""
        payload = {"name": "integration-test-envelope-check"}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 201
        body = resp.json()
        assert "status" in body
        assert "data" in body
        assert body["status"] == "success"
        # Cleanup
        requests.delete(
            f"{API_BASE_URL}/api/v1/policies/{body['data']['id']}",
            headers=_auth_headers(),
            timeout=TIMEOUT,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/policies — missing required field → 422
# ---------------------------------------------------------------------------

class TestCreatePolicyMissingFields:
    """POST /api/v1/policies with missing required fields returns 422."""

    def test_empty_body_returns_422(self):
        """An empty JSON object is missing `name` (required) → 422."""
        resp = _post("/api/v1/policies", {})
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422
        body = resp.json()
        assert "details" in body or "error" in body

    def test_null_name_returns_422(self):
        """name=null violates strict-mode — Pydantic rejects it."""
        resp = _post("/api/v1/policies", {"name": None})
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    def test_422_body_contains_pydantic_detail_list(self):
        """422 response body must include a `details` list of Pydantic errors."""
        resp = _post("/api/v1/policies", {})
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422
        body = resp.json()
        # The handler wraps Pydantic errors in {"error": ..., "details": [...]}
        assert "details" in body
        assert isinstance(body["details"], list)
        assert len(body["details"]) > 0


# ---------------------------------------------------------------------------
# POST /api/v1/policies — invalid CIDR → 422
# ---------------------------------------------------------------------------

class TestCreatePolicyInvalidCidr:
    """POST /api/v1/policies with bad CIDR notation in src_cidrs/dst_cidrs → 422."""

    def test_invalid_src_cidr_returns_422(self):
        """'not-a-cidr' is not valid CIDR notation → field_validator raises."""
        payload = {
            "name": "integration-test-bad-cidr",
            "src_cidrs": ["not-a-cidr"],
        }
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422
        body = resp.json()
        assert "details" in body

    def test_invalid_dst_cidr_returns_422(self):
        """Malformed mask in dst_cidrs → 422."""
        payload = {
            "name": "integration-test-bad-dst-cidr",
            "dst_cidrs": ["10.0.0.0/999"],
        }
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    def test_host_ip_without_mask_is_accepted(self):
        """A bare host IP without prefix is coerced to /32 by ipaddress — accepted."""
        payload = {
            "name": "integration-test-host-ip-cidr",
            "src_cidrs": ["192.168.1.1"],
        }
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        # ipaddress.ip_network("192.168.1.1", strict=False) succeeds → 201
        assert resp.status_code == 201
        requests.delete(
            f"{API_BASE_URL}/api/v1/policies/{resp.json()['data']['id']}",
            headers=_auth_headers(),
            timeout=TIMEOUT,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/policies — invalid port range → 422
# ---------------------------------------------------------------------------

class TestCreatePolicyInvalidPortRange:
    """POST /api/v1/policies with invalid port values → 422."""

    def test_port_zero_returns_422(self):
        """Port 0 is outside the valid range 1-65535."""
        payload = {"name": "integration-test-port-zero", "ports": ["0"]}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    def test_port_above_max_returns_422(self):
        """Port 65536 exceeds the 16-bit maximum."""
        payload = {"name": "integration-test-port-max", "ports": ["65536"]}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    def test_inverted_range_returns_422(self):
        """A range where start > end is semantically invalid."""
        payload = {"name": "integration-test-inverted-range", "ports": ["8080-80"]}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    def test_valid_port_range_is_accepted(self):
        """A well-formed range like '8000-8080' should be accepted."""
        payload = {"name": "integration-test-valid-range", "ports": ["8000-8080"]}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 201
        requests.delete(
            f"{API_BASE_URL}/api/v1/policies/{resp.json()['data']['id']}",
            headers=_auth_headers(),
            timeout=TIMEOUT,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/policies — invalid protocol → 422
# ---------------------------------------------------------------------------

class TestCreatePolicyInvalidProtocol:
    """POST /api/v1/policies with an unrecognised protocol literal → 422."""

    def test_unsupported_protocol_returns_422(self):
        """Protocol 'ftp' is not in the allowed Literal set."""
        payload = {"name": "integration-test-bad-proto", "protocol": "ftp"}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    def test_uppercase_protocol_rejected_in_strict_mode(self):
        """Strict mode means 'TCP' (uppercase) is not the literal 'tcp'."""
        payload = {"name": "integration-test-upper-proto", "protocol": "TCP"}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    @pytest.mark.parametrize("proto", ["tcp", "udp", "icmp", "any"])
    def test_valid_protocols_are_accepted(self, proto: str):
        """Each of the four allowed protocol literals must be accepted."""
        payload = {"name": f"integration-test-proto-{proto}", "protocol": proto}
        resp = _post("/api/v1/policies", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 201
        requests.delete(
            f"{API_BASE_URL}/api/v1/policies/{resp.json()['data']['id']}",
            headers=_auth_headers(),
            timeout=TIMEOUT,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/clusters/register — valid cluster → 200/201
# ---------------------------------------------------------------------------

class TestClusterRegistration:
    """POST /api/v1/clusters/register exercises ClusterRegisterRequest schema."""

    def test_valid_cluster_registration_returns_success(self):
        """A well-formed cluster payload should be accepted and return cluster_id."""
        payload = {
            "name": "integration-test-cluster",
            "region": "us-east-1",
            "datacenter": "dc-test-01",
            "headend_url": "https://headend.integration.test:8443",
        }
        resp = _post("/api/v1/clusters/register", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        # The route returns 200 (not 201) per the source
        assert resp.status_code in (200, 201, 503), (
            f"Expected 200/201 or 503 (no clusters), got {resp.status_code}: {resp.text}"
        )
        if resp.status_code in (200, 201):
            body = resp.json()
            assert "cluster_id" in body
            assert body.get("status") == "registered"

    def test_missing_headend_url_returns_422(self):
        """headend_url is required; omitting it returns 422."""
        payload = {
            "name": "integration-test-cluster-nourl",
            "region": "us-west-2",
            "datacenter": "dc-test-02",
        }
        resp = _post("/api/v1/clusters/register", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422

    def test_invalid_headend_url_scheme_returns_422(self):
        """headend_url must start with http:// or https://; ftp:// is rejected."""
        payload = {
            "name": "integration-test-cluster-badurl",
            "region": "eu-west-1",
            "datacenter": "dc-test-03",
            "headend_url": "ftp://badscheme.example.com:8443",
        }
        resp = _post("/api/v1/clusters/register", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422
        body = resp.json()
        assert "details" in body


# ---------------------------------------------------------------------------
# POST /api/v1/clients/register — invalid type → 422
# ---------------------------------------------------------------------------

class TestClientRegistration:
    """POST /api/v1/clients/register exercises ClientRegisterRequest schema."""

    def test_invalid_client_type_returns_422(self):
        """type='browser' is not in the allowed Literal set → 422."""
        payload = {
            "name": "integration-test-bad-client",
            "type": "browser",
            "public_key": "dGVzdC1rZXk=",
        }
        resp = _post("/api/v1/clients/register", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422
        body = resp.json()
        assert "details" in body

    @pytest.mark.parametrize("client_type", [
        "native", "docker", "mobile", "client_native", "client_docker",
    ])
    def test_valid_client_types_pass_validation(self, client_type: str):
        """Each allowed type literal should pass schema validation.

        The response may be 503 (no available cluster) in test environments
        without live headends, but must not be 422.
        """
        payload = {
            "name": f"integration-test-client-{client_type}",
            "type": client_type,
            "public_key": "dGVzdC1wdWJsaWMta2V5LWZvci10ZXN0aW5n",
        }
        resp = _post("/api/v1/clients/register", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        # 422 means schema rejection; anything else means schema passed
        assert resp.status_code != 422, (
            f"Unexpected 422 for valid client_type={client_type!r}: {resp.text}"
        )

    def test_missing_public_key_returns_422(self):
        """public_key is required by the schema → 422 when absent."""
        payload = {
            "name": "integration-test-no-pubkey",
            "type": "native",
        }
        resp = _post("/api/v1/clients/register", payload)
        if resp.status_code == 401:
            pytest.skip("No API_TEST_TOKEN configured")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/v1/policies/<id> — partial update → 200
# ---------------------------------------------------------------------------

class TestUpdatePolicy:
    """PUT /api/v1/policies/<id> with partial fields exercises PolicyRuleUpdateRequest."""

    def test_partial_update_with_enabled_field_returns_200(self, created_policy_id: int):
        """Disabling an existing policy with only {enabled: false} returns 200."""
        resp = _put(f"/api/v1/policies/{created_policy_id}", {"enabled": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["enabled"] is False

    def test_partial_update_with_priority_returns_200(self, created_policy_id: int):
        """Updating only the priority field returns 200 with the new value."""
        resp = _put(f"/api/v1/policies/{created_policy_id}", {"priority": 999})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["priority"] == 999

    def test_partial_update_with_valid_cidrs_returns_200(self, created_policy_id: int):
        """Replacing src_cidrs on an existing policy returns 200."""
        resp = _put(
            f"/api/v1/policies/{created_policy_id}",
            {"src_cidrs": ["172.16.0.0/12"]},
        )
        assert resp.status_code == 200

    def test_partial_update_with_invalid_cidr_returns_422(self, created_policy_id: int):
        """PUT with a bad CIDR string should still return 422 from Pydantic."""
        resp = _put(
            f"/api/v1/policies/{created_policy_id}",
            {"src_cidrs": ["not-valid"]},
        )
        assert resp.status_code == 422

    def test_partial_update_with_invalid_action_returns_422(self, created_policy_id: int):
        """PUT with action='forward' (not in Literal) should return 422."""
        resp = _put(
            f"/api/v1/policies/{created_policy_id}",
            {"action": "forward"},
        )
        assert resp.status_code == 422

    def test_empty_update_body_returns_200_unchanged(self, created_policy_id: int):
        """An empty update dict is valid (no-op); should return 200."""
        resp = _put(f"/api/v1/policies/{created_policy_id}", {})
        assert resp.status_code == 200
