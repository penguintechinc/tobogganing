"""Tests for core/api/certs.py: helper functions and the /certs/certificates route."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.core.api.certs import _extract_bearer_token, _verify_enrollment_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair


class TestExtractBearerToken:
    """Tests for the local _extract_bearer_token helper."""

    def test_none_header(self) -> None:
        """None header returns None."""
        assert _extract_bearer_token(None) is None

    def test_non_bearer_header(self) -> None:
        """Non-Bearer header returns None."""
        assert _extract_bearer_token("Basic abc123") is None

    def test_empty_bearer_token(self) -> None:
        """Bearer header with only whitespace returns None."""
        assert _extract_bearer_token("Bearer    ") is None

    def test_valid_bearer_token(self) -> None:
        """Valid Bearer header returns the token."""
        assert _extract_bearer_token("Bearer abc123") == "abc123"


class TestVerifyEnrollmentToken:
    """Tests for the local _verify_enrollment_token helper."""

    def test_no_expected_env_var(self) -> None:
        """Returns False when ENROLLMENT_BOOTSTRAP_TOKEN is unset."""
        with patch.dict(os.environ, {}, clear=True):
            assert _verify_enrollment_token("anything") is False

    def test_none_token(self) -> None:
        """Returns False when token is None."""
        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "secret"}):
            assert _verify_enrollment_token(None) is False

    def test_matching_token(self) -> None:
        """Returns True on exact match."""
        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "secret"}):
            assert _verify_enrollment_token("secret") is True

    def test_mismatched_token(self) -> None:
        """Returns False on mismatch."""
        with patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "secret"}):
            assert _verify_enrollment_token("wrong") is False


@pytest.fixture
def app_with_certs(app: Quart) -> Quart:
    """App with a bootstrap token configured and cert feature gate open.

    Args:
        app: Base test app fixture.

    Returns:
        Quart app usable for POST /api/v1/certs/certificates.
    """
    return app


@pytest.fixture
def app_with_key_provider(app_with_certs: Quart) -> Quart:
    """App with a real KEY_PROVIDER, so tests can mint real machine-JWTs.

    Args:
        app_with_certs: Base certs-ready app fixture.

    Returns:
        Quart app with KEY_PROVIDER configured for JWT signing/verification.
    """
    private_pem, public_pem = generate_rsa_key_pair()
    app_with_certs.config["KEY_PROVIDER"] = InAppKeyProvider(private_pem, public_pem)
    return app_with_certs


async def _machine_jwt(app: Quart, *, sub_id: str, node_type: str, tenant: str) -> str:
    """Mint a real machine-JWT for the given node identity/tenant.

    Args:
        app: App with KEY_PROVIDER configured (app_with_key_provider).
        sub_id: Cluster or client id to embed in the `sub` claim.
        node_type: Node type (e.g. "kubernetes_node", "client_docker").
        tenant: Tenant claim.

    Returns:
        Encoded machine-JWT access token.
    """
    provider = app.config["KEY_PROVIDER"]
    claims = build_machine_claims(
        sub_id=sub_id,
        node_type=node_type,
        tenant=tenant,
        iss="tobogganing",
        aud="headend",
    )
    return await encode_access_token(claims, provider, ttl_hours=1)


def _flag_on() -> Any:
    """Context manager patching the feature gate to always allow."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=True)


def _bootstrap_headers() -> dict[str, str]:
    """Build Authorization header using the legacy bootstrap token allowlist."""
    return {"Authorization": "Bearer test-bootstrap-token"}


@contextmanager
def _with_registered_client(client_id: str, tenant: str = "default") -> Iterator[MagicMock]:
    """Patch ClientRegistry so `get_client(client_id)` resolves under `tenant`.

    Args:
        client_id: Client id the mocked registry should resolve.
        tenant: Tenant the mocked client belongs to.

    Yields:
        The patched ClientRegistry class mock.
    """
    with patch("hub_api.core.api.certs.ClientRegistry") as mock_cls:
        mock_cls.return_value.get_client = AsyncMock(
            return_value=MagicMock(id=client_id, tenant=tenant, cluster_id="cluster-x")
        )
        yield mock_cls


@contextmanager
def _with_registered_cluster(
    cluster_id: str, tenant: str = "default", headend_url: str | None = None
) -> Iterator[MagicMock]:
    """Patch ClusterManager so `get_cluster(cluster_id)` resolves under `tenant`.

    `headend_url` defaults to a deterministic per-cluster value so tests can
    assert the exact server-derived SAN (`_cluster_san_names` in certs.py)
    without needing to trust anything from the request body.

    Args:
        cluster_id: Cluster id the mocked manager should resolve.
        tenant: Tenant the mocked cluster belongs to.
        headend_url: Registered headend_url for the mocked cluster; defaults
            to "https://{cluster_id}.example.com".

    Yields:
        The patched ClusterManager class mock.
    """
    if headend_url is None:
        headend_url = f"https://{cluster_id}.example.com"
    with patch("hub_api.core.api.certs.ClusterManager") as mock_cls:
        mock_cls.return_value.get_cluster = AsyncMock(
            return_value=MagicMock(id=cluster_id, tenant=tenant, headend_url=headend_url)
        )
        yield mock_cls


@pytest.mark.asyncio
async def test_generate_certificate_invalid_type(app_with_certs: Quart) -> None:
    """POST /certs/certificates with invalid cert type returns 400."""
    client = app_with_certs.test_client()
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "bogus", "id": "node-1", "name": "test"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "Invalid certificate type" in data["error"]


@pytest.mark.asyncio
async def test_generate_certificate_missing_fields(app_with_certs: Quart) -> None:
    """POST /certs/certificates with missing id/name returns 400."""
    client = app_with_certs.test_client()
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "client"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "Missing required fields" in data["error"]


@pytest.mark.asyncio
async def test_generate_certificate_no_cert_manager(app_with_certs: Quart) -> None:
    """POST /certs/certificates without CERT_MANAGER configured returns 500."""
    client = app_with_certs.test_client()
    with (
        _flag_on(),
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}),
        _with_registered_client("node-1"),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "client", "id": "node-1", "name": "test"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 500
    data = await resp.get_json()
    assert data["error"] == "Internal server error"


@pytest.mark.asyncio
async def test_generate_client_certificate_success(app_with_certs: Quart) -> None:
    """POST /certs/certificates with type=client returns generated cert material."""
    cert_manager = MagicMock()
    cert_manager.generate_client_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with (
        _flag_on(),
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}),
        _with_registered_client("node-1"),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "client", "id": "node-1", "name": "test", "client_type": "docker"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["type"] == "client"
    assert data["certificates"]["key"] == "KEY_PEM"
    cert_manager.generate_client_certificate.assert_called_once_with("node-1", "test", "docker")


@pytest.mark.asyncio
async def test_generate_client_certificate_failure(app_with_certs: Quart) -> None:
    """POST /certs/certificates propagates a 500 when generation raises."""
    cert_manager = MagicMock()
    cert_manager.generate_client_certificate = AsyncMock(side_effect=RuntimeError("boom"))
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with (
        _flag_on(),
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}),
        _with_registered_client("node-1"),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "client", "id": "node-1", "name": "test"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 500
    data = await resp.get_json()
    assert data["error"] == "Failed to generate certificate"


@pytest.mark.asyncio
async def test_generate_headend_certificate_success(app_with_certs: Quart) -> None:
    """POST /certs/certificates with type=headend returns generated cert material."""
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with (
        _flag_on(),
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}),
        _with_registered_cluster("cluster-1"),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "headend",
                "id": "cluster-1",
                "name": "headend.local",
                "san_names": ["headend.local"],
            },
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["type"] == "headend"
    # SANs are server-derived from the cluster's own headend_url, never from
    # the request body's san_names — see test below for the regression proof.
    cert_manager.generate_headend_certificate.assert_called_once_with(
        "cluster-1", "headend.local", ["cluster-1.example.com"]
    )


@pytest.mark.asyncio
async def test_generate_headend_certificate_ignores_body_san_names(
    app_with_certs: Quart,
) -> None:
    """regression: cross-tenant cert issuance via SAN (security-audit 2026-09-22).

    Body `san_names` — whether a well-formed cross-tenant hostname, garbage,
    or a non-list — must never reach CertificateManager. Only the SAN derived
    from the caller's own registered cluster record is used.
    """
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with (
        _flag_on(),
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}),
        _with_registered_cluster("cluster-1", headend_url="https://cluster-1.example.com"),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "headend",
                "id": "cluster-1",
                "name": "headend.local",
                "san_names": "not-a-list",
            },
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 200
    cert_manager.generate_headend_certificate.assert_called_once_with(
        "cluster-1", "headend.local", ["cluster-1.example.com"]
    )


@pytest.mark.asyncio
async def test_generate_headend_certificate_failure(app_with_certs: Quart) -> None:
    """POST /certs/certificates for headend type propagates a 500 when generation raises."""
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(side_effect=RuntimeError("boom"))
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with (
        _flag_on(),
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}),
        _with_registered_cluster("cluster-1"),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "headend", "id": "cluster-1", "name": "headend.local"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 500


# regression: cross-tenant cert issuance (security-audit 2026-09-21) ---------
#
# POST /certs/certificates previously bound the cert CN/SANs to nothing but
# the request body, so any enrolled node (real machine-JWT or the legacy
# bootstrap token) could mint a fleet-CA-signed cert impersonating a node in
# a different tenant. The tests below exercise the fix in
# `_authorize_cert_identity`.


@pytest.mark.asyncio
async def test_generate_headend_certificate_same_tenant_self_success(
    app_with_key_provider: Quart,
) -> None:
    """A cluster's own machine-JWT requesting its own headend cert succeeds."""
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_key_provider.config["CERT_MANAGER"] = cert_manager

    token = await _machine_jwt(
        app_with_key_provider,
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="tenant-a",
    )

    client = app_with_key_provider.test_client()
    with _flag_on(), _with_registered_cluster("cluster-1", tenant="tenant-a"):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "headend",
                "id": "cluster-1",
                "name": "headend.local",
                # Body SANs are ignored — asserted below via the server-
                # derived value instead of this attacker-controllable input.
                "san_names": ["headend.local"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    cert_manager.generate_headend_certificate.assert_called_once_with(
        "cluster-1", "headend.local", ["cluster-1.example.com"]
    )


@pytest.mark.asyncio
async def test_generate_client_certificate_same_cluster_success(
    app_with_key_provider: Quart,
) -> None:
    """A cluster's machine-JWT minting a cert for its own managed client succeeds."""
    cert_manager = MagicMock()
    cert_manager.generate_client_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_key_provider.config["CERT_MANAGER"] = cert_manager

    token = await _machine_jwt(
        app_with_key_provider,
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="tenant-a",
    )

    client = app_with_key_provider.test_client()
    with (
        _flag_on(),
        patch("hub_api.core.api.certs.ClientRegistry") as mock_client_cls,
    ):
        mock_client_cls.return_value.get_client = AsyncMock(
            return_value=MagicMock(id="client-1", tenant="tenant-a", cluster_id="cluster-1")
        )
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "client", "id": "client-1", "name": "client-1", "client_type": "docker"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    cert_manager.generate_client_certificate.assert_called_once_with(
        "client-1", "client-1", "docker"
    )


@pytest.mark.asyncio
async def test_generate_headend_certificate_cross_tenant_forbidden(
    app_with_key_provider: Quart,
) -> None:
    """A machine-JWT for tenant-a cannot mint a headend cert naming a node
    from a different tenant — the tenant-scoped lookup finds nothing."""
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_key_provider.config["CERT_MANAGER"] = cert_manager

    token = await _machine_jwt(
        app_with_key_provider,
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="tenant-a",
    )

    client = app_with_key_provider.test_client()
    with (
        _flag_on(),
        patch("hub_api.core.api.certs.ClusterManager") as mock_cluster_cls,
    ):
        # Simulates the real DB behavior: get_cluster is scoped to the
        # caller's tenant, so a victim's cluster in tenant-b is invisible.
        mock_cluster_cls.return_value.get_cluster = AsyncMock(return_value=None)
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "headend",
                "id": "victim-headend",
                "name": "victim.example.com",
                "san_names": ["victim.example.com"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403
    data = await resp.get_json()
    assert "Forbidden" in data["error"]
    cert_manager.generate_headend_certificate.assert_not_called()


@pytest.mark.asyncio
async def test_generate_headend_certificate_subject_mismatch_forbidden(
    app_with_key_provider: Quart,
) -> None:
    """A cluster machine-JWT cannot mint a headend cert for a sibling cluster
    in its own tenant — CN must match the caller's own subject."""
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_key_provider.config["CERT_MANAGER"] = cert_manager

    token = await _machine_jwt(
        app_with_key_provider,
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="tenant-a",
    )

    client = app_with_key_provider.test_client()
    with _flag_on(), _with_registered_cluster("cluster-2", tenant="tenant-a"):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "headend", "id": "cluster-2", "name": "headend.local"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403
    cert_manager.generate_headend_certificate.assert_not_called()


@pytest.mark.asyncio
async def test_generate_certificate_bootstrap_token_unregistered_node_forbidden(
    app_with_certs: Quart,
) -> None:
    """Bootstrap-token callers (no per-node subject, only a shared secret)
    are still tenant+existence scoped — they cannot name a node id that was
    never registered under the enrollment tenant."""
    cert_manager = MagicMock()
    cert_manager.generate_client_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with (
        _flag_on(),
        patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}),
        patch("hub_api.core.api.certs.ClientRegistry") as mock_client_cls,
    ):
        mock_client_cls.return_value.get_client = AsyncMock(return_value=None)
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "client", "id": "node-1", "name": "test"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 403
    data = await resp.get_json()
    assert "Forbidden" in data["error"]
    cert_manager.generate_client_certificate.assert_not_called()


@pytest.mark.asyncio
async def test_generate_headend_certificate_cross_tenant_san_ignored(
    app_with_key_provider: Quart,
) -> None:
    """regression: cross-tenant cert issuance via SAN (security-audit 2026-09-22).

    A caller that legitimately owns `node_id` in its own tenant must not be
    able to get a fleet-CA-signed cert naming a DIFFERENT tenant's headend
    hostname as a SAN — TLS/mTLS peer identity is matched on SAN, so this is
    the actual impersonation vector even when the CN binding is correct.
    The body-supplied cross-tenant SAN must be silently discarded, not
    smuggled through, and the issued cert must only carry the caller's own
    registered hostname.
    """
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_key_provider.config["CERT_MANAGER"] = cert_manager

    token = await _machine_jwt(
        app_with_key_provider,
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="tenant-a",
    )

    client = app_with_key_provider.test_client()
    with (
        _flag_on(),
        _with_registered_cluster(
            "cluster-1", tenant="tenant-a", headend_url="https://cluster-1.tenant-a.internal"
        ),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "headend",
                "id": "cluster-1",
                "name": "headend.local",
                "san_names": ["headend.tenant-b.internal"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    # The attacker-supplied cross-tenant SAN never reaches CertificateManager
    # — only the caller's own registered hostname does.
    cert_manager.generate_headend_certificate.assert_called_once_with(
        "cluster-1", "headend.local", ["cluster-1.tenant-a.internal"]
    )
    for call in cert_manager.generate_headend_certificate.call_args_list:
        assert "headend.tenant-b.internal" not in call.args[2]


@pytest.mark.asyncio
async def test_generate_headend_certificate_no_authorized_sans_forbidden(
    app_with_key_provider: Quart,
) -> None:
    """regression: cross-tenant cert issuance via SAN (security-audit 2026-09-22).

    If the caller's own cluster record exposes no derivable hostname, fail
    closed (403) rather than issue a cert with no SAN / fall back to the
    request body.
    """
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_key_provider.config["CERT_MANAGER"] = cert_manager

    token = await _machine_jwt(
        app_with_key_provider,
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="tenant-a",
    )

    client = app_with_key_provider.test_client()
    with (
        _flag_on(),
        _with_registered_cluster("cluster-1", tenant="tenant-a", headend_url=""),
    ):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={
                "type": "headend",
                "id": "cluster-1",
                "name": "headend.local",
                "san_names": ["attacker-controlled.example.com"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403
    cert_manager.generate_headend_certificate.assert_not_called()
