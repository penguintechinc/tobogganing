"""Edge-case and error-path coverage for the SDWAN clusters API blueprint."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from quart import Quart

from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster


def _cluster_obj(**overrides) -> Cluster:
    """Build a Cluster dataclass instance with sane defaults for tests.

    Args:
        overrides: Fields to override on the default Cluster.

    Returns:
        A Cluster instance.
    """
    defaults = dict(
        id="cluster-1",
        name="cluster-1",
        region="us-east-1",
        datacenter="dc1",
        headend_url="https://headend.example.com",
        status="active",
        last_heartbeat=datetime.now(timezone.utc),
        client_count=0,
        tenant="default",
    )
    defaults.update(overrides)
    return Cluster(**defaults)


# --- POST /clusters (register_cluster) ---------------------------------------


@pytest.mark.asyncio
async def test_register_cluster_missing_field(app_with_sase: Quart, bootstrap_token: str) -> None:
    """Missing required field returns 400."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sdwan/clusters",
        json={"name": "c", "region": "us-east-1"},
        headers={"Authorization": f"Bearer {bootstrap_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Missing required field" in data["error"]


@pytest.mark.asyncio
async def test_register_cluster_tenant_mismatch(app_with_sase: Quart, bootstrap_token: str) -> None:
    """Tenant in request body that doesn't match server config returns 403."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sdwan/clusters",
        json={
            "name": "c",
            "region": "us-east-1",
            "datacenter": "dc1",
            "headend_url": "https://headend.example.com",
            "tenant": "some-other-tenant",
        },
        headers={"Authorization": f"Bearer {bootstrap_token}"},
    )

    assert response.status_code == 403
    data = await response.get_json()
    assert data["error"] == "tenant mismatch"


@pytest.mark.asyncio
async def test_register_cluster_license_gate_over_5_nodes(
    app_with_sase: Quart, bootstrap_token: str
) -> None:
    """5+ active clusters returns 402 license-required."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.get_cluster_count = AsyncMock(return_value=5)

        response = await client.post(
            "/api/v1/sdwan/clusters",
            json={
                "name": "c",
                "region": "us-east-1",
                "datacenter": "dc1",
                "headend_url": "https://headend.example.com",
            },
            headers={"Authorization": f"Bearer {bootstrap_token}"},
        )

        assert response.status_code == 402
        data = await response.get_json()
        assert data["tier"] == "professional"


@pytest.mark.asyncio
async def test_register_cluster_exception(app_with_sase: Quart, bootstrap_token: str) -> None:
    """Unexpected exception during registration returns 500."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
        mock_manager_class.side_effect = RuntimeError("boom")

        response = await client.post(
            "/api/v1/sdwan/clusters",
            json={
                "name": "c",
                "region": "us-east-1",
                "datacenter": "dc1",
                "headend_url": "https://headend.example.com",
            },
            headers={"Authorization": f"Bearer {bootstrap_token}"},
        )

        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"


# --- POST /clusters/<cluster_id>/heartbeat -----------------------------------


@pytest.mark.asyncio
async def test_cluster_heartbeat_not_found(app_with_sase: Quart) -> None:
    """update_heartbeat returning False returns 404."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
        mock_mgr = AsyncMock()
        mock_manager_class.return_value = mock_mgr
        mock_mgr.initialize = AsyncMock()
        mock_mgr.authenticate_cluster = AsyncMock(
            return_value=_cluster_obj(id="cluster-1", tenant="test-tenant")
        )
        mock_mgr.update_heartbeat = AsyncMock(return_value=False)

        response = await client.post(
            "/api/v1/sdwan/clusters/cluster-1/heartbeat",
            json={"client_count": 5},
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 404
        data = await response.get_json()
        assert data["error"] == "Cluster not found"


@pytest.mark.asyncio
async def test_cluster_heartbeat_exception(app_with_sase: Quart) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
        mock_manager_class.side_effect = RuntimeError("boom")

        response = await client.post(
            "/api/v1/sdwan/clusters/cluster-1/heartbeat",
            json={"client_count": 5},
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500


# --- GET /clusters (list_clusters) -------------------------------------------


@pytest.mark.asyncio
async def test_list_clusters_exception(app_with_sase: Quart, valid_tenant_token: str) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
        mock_manager_class.side_effect = RuntimeError("boom")

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sdwan/clusters",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 500


# --- GET /clusters/<cluster_id>/headend-config -------------------------------


@pytest.mark.asyncio
async def test_get_headend_config_no_auth_header(app_with_sase: Quart) -> None:
    """Missing Authorization header returns 401."""
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/sdwan/clusters/cluster-1/headend-config")

    assert response.status_code == 401
    data = await response.get_json()
    assert data["error"] == "Unauthorized: API key required"


@pytest.mark.asyncio
async def test_get_headend_config_exception(app_with_sase: Quart) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clusters.ClusterManager") as mock_manager_class:
        mock_manager_class.side_effect = RuntimeError("boom")

        response = await client.get(
            "/api/v1/sdwan/clusters/cluster-1/headend-config",
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500
