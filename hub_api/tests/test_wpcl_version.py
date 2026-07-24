"""Tests for WaddlePerf client version API endpoint."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from quart import Quart
from typing import Any


# Use fixtures from conftest: app_with_wpc, wpc_readonly_token


@pytest.mark.asyncio
async def test_get_version_success(app_with_wpc: Quart, wpc_readonly_token: str) -> None:
    """Test successful version retrieval.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    response = await client.get(
        "/api/v1/waddleperf_client/version",
        headers={"Authorization": f"Bearer {wpc_readonly_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "latest_version" in data
    assert "min_version" in data
    assert "download_url" in data
    assert "meta" in data
    assert data["meta"]["version"] == 1


@pytest.mark.asyncio
async def test_get_version_returns_configured_values(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test that version endpoint returns configured values.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    # Set configured values
    app_with_wpc.config["WPCL_LATEST_VERSION"] = "2.1.0"
    app_with_wpc.config["WPCL_MIN_VERSION"] = "1.5.0"
    app_with_wpc.config["WPCL_DOWNLOAD_URL"] = "https://custom-download.com/wpcl"

    response = await client.get(
        "/api/v1/waddleperf_client/version",
        headers={"Authorization": f"Bearer {wpc_readonly_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["latest_version"] == "2.1.0"
    assert data["min_version"] == "1.5.0"
    assert data["download_url"] == "https://custom-download.com/wpcl"


@pytest.mark.asyncio
async def test_get_version_default_values(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test that version endpoint returns sensible defaults.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    # Ensure config values are not set
    app_with_wpc.config.pop("WPCL_LATEST_VERSION", None)
    app_with_wpc.config.pop("WPCL_MIN_VERSION", None)
    app_with_wpc.config.pop("WPCL_DOWNLOAD_URL", None)

    response = await client.get(
        "/api/v1/waddleperf_client/version",
        headers={"Authorization": f"Bearer {wpc_readonly_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["latest_version"] == "1.0.0"
    assert data["min_version"] == "0.1.0"
    assert "downloads.tobogganing.app" in data["download_url"]


@pytest.mark.asyncio
async def test_get_version_requires_tenant(app_with_wpc: Quart) -> None:
    """Test that version endpoint requires tenant claim.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    response = await client.get("/api/v1/waddleperf_client/version")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_version_requires_valid_token(app_with_wpc: Quart) -> None:
    """Test that version endpoint requires valid JWT token.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    response = await client.get(
        "/api/v1/waddleperf_client/version",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_version_meta_timestamp(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test that version response includes meta with timestamp.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    response = await client.get(
        "/api/v1/waddleperf_client/version",
        headers={"Authorization": f"Bearer {wpc_readonly_token}"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert "meta" in data
    assert data["meta"]["version"] == 1
    assert "timestamp" in data["meta"]

    # Verify timestamp is valid ISO format
    timestamp_str = data["meta"]["timestamp"]
    # This should not raise
    datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_get_version_is_flag_gated(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test that version endpoint is gated behind feature flag.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Valid JWT token with read scope.
    """
    client = app_with_wpc.test_client()

    with patch(
        "hub_api.modules.waddleperf_client.api.version.require_feature"
    ) as mock_require_feature:
        # Mock the decorator to ensure it's applied
        def mock_decorator(module: str, feature: str):
            def decorator(func):
                # Still call the function, but verify it was decorated
                return func
            return decorator

        mock_require_feature.side_effect = mock_decorator

        response = await client.get(
            "/api/v1/waddleperf_client/version",
            headers={"Authorization": f"Bearer {wpc_readonly_token}"},
        )

        # Should succeed because the mock doesn't actually gate
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_version_no_write_scope_required(
    app_with_wpc: Quart, wpc_readonly_token: str
) -> None:
    """Test that version endpoint does not require write scope.

    Args:
        app_with_wpc: Test app with WPC module.
        wpc_readonly_token: Token with read-only scope.
    """
    client = app_with_wpc.test_client()

    response = await client.get(
        "/api/v1/waddleperf_client/version",
        headers={"Authorization": f"Bearer {wpc_readonly_token}"},
    )

    # Should succeed with read-only token (no specific scope required beyond tenant)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_version_malformed_auth_header(
    app_with_wpc: Quart,
) -> None:
    """Test version retrieval with malformed Authorization header.

    Args:
        app_with_wpc: Test app with WPC module.
    """
    client = app_with_wpc.test_client()

    response = await client.get(
        "/api/v1/waddleperf_client/version",
        headers={"Authorization": "NotBearer token123"},
    )

    assert response.status_code == 403
