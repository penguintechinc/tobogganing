"""Tests for core/api/certs.py: helper functions and the /certs/certificates route."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart

from hub_api.core.api.certs import _extract_bearer_token, _verify_enrollment_token


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


def _flag_on() -> Any:
    """Context manager patching the feature gate to always allow."""
    return patch("hub_api.entitlements.gate.feature_enabled", return_value=True)


def _bootstrap_headers() -> dict[str, str]:
    """Build Authorization header using the legacy bootstrap token allowlist."""
    return {"Authorization": "Bearer test-bootstrap-token"}


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
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
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
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
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
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
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
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
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
    cert_manager.generate_headend_certificate.assert_called_once_with(
        "cluster-1", "headend.local", ["headend.local"]
    )


@pytest.mark.asyncio
async def test_generate_headend_certificate_bad_san_names_defaults_empty(
    app_with_certs: Quart,
) -> None:
    """POST /certs/certificates with non-list san_names defaults to empty list."""
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(
        return_value=("KEY_PEM", "CERT_PEM", "CA_PEM")
    )
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
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
        "cluster-1", "headend.local", []
    )


@pytest.mark.asyncio
async def test_generate_headend_certificate_failure(app_with_certs: Quart) -> None:
    """POST /certs/certificates for headend type propagates a 500 when generation raises."""
    cert_manager = MagicMock()
    cert_manager.generate_headend_certificate = AsyncMock(side_effect=RuntimeError("boom"))
    app_with_certs.config["CERT_MANAGER"] = cert_manager

    client = app_with_certs.test_client()
    with _flag_on(), patch.dict(os.environ, {"ENROLLMENT_BOOTSTRAP_TOKEN": "test-bootstrap-token"}):
        resp = await client.post(
            "/api/v1/certs/certificates",
            json={"type": "headend", "id": "cluster-1", "name": "headend.local"},
            headers=_bootstrap_headers(),
        )
    assert resp.status_code == 500
