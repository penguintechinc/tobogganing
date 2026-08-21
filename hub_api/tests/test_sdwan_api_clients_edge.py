"""Edge-case and error-path coverage for the SDWAN clients API blueprint."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.modules.sdwan.orchestrator.client_registry import Client
from hub_api.modules.sdwan.orchestrator.cluster_manager import Cluster


def _client_obj(**overrides: Any) -> Client:
    """Build a Client dataclass instance with sane defaults for tests.

    Args:
        overrides: Fields to override on the default Client.

    Returns:
        A Client instance.
    """
    defaults: dict[str, Any] = dict(
        id="client-1",
        name="test-client",
        type="docker",
        cluster_id="cluster-1",
        api_key_hash="hash",
        public_key="-----BEGIN PUBLIC KEY-----",
        ip_address="10.0.0.1",
        status="active",
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        tenant="default",
        metadata={},
    )
    defaults.update(overrides)
    return Client(**defaults)


def _cluster_obj(**overrides: Any) -> Cluster:
    """Build a Cluster dataclass instance with sane defaults for tests.

    Args:
        overrides: Fields to override on the default Cluster.

    Returns:
        A Cluster instance.
    """
    defaults: dict[str, Any] = dict(
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


# --- POST /clients (register_client) ----------------------------------------


@pytest.mark.asyncio
async def test_register_client_missing_field(app_with_sase: Quart, bootstrap_token: str) -> None:
    """Missing required field returns 400."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sdwan/clients",
        json={"name": "test-client", "type": "docker"},
        headers={"Authorization": f"Bearer {bootstrap_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Missing required field" in data["error"]


@pytest.mark.asyncio
async def test_register_client_invalid_type(app_with_sase: Quart, bootstrap_token: str) -> None:
    """Invalid client type returns 400."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sdwan/clients",
        json={"name": "c", "type": "bogus", "public_key": "key"},
        headers={"Authorization": f"Bearer {bootstrap_token}"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["error"] == "Invalid client type"


@pytest.mark.asyncio
async def test_register_client_tenant_mismatch(app_with_sase: Quart, bootstrap_token: str) -> None:
    """Tenant in request body that doesn't match server config returns 403."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    response = await client.post(
        "/api/v1/sdwan/clients",
        json={
            "name": "c",
            "type": "docker",
            "public_key": "key",
            "tenant": "some-other-tenant",
        },
        headers={"Authorization": f"Bearer {bootstrap_token}"},
    )

    assert response.status_code == 403
    data = await response.get_json()
    assert data["error"] == "tenant mismatch"


@pytest.mark.asyncio
async def test_register_client_no_available_clusters(
    app_with_sase: Quart, bootstrap_token: str
) -> None:
    """No optimal cluster available returns 503."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClusterManager") as mock_cluster_class:
        mock_cluster_mgr = AsyncMock()
        mock_cluster_class.return_value = mock_cluster_mgr
        mock_cluster_mgr.initialize = AsyncMock()
        mock_cluster_mgr.get_optimal_cluster = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/sdwan/clients",
            json={"name": "c", "type": "docker", "public_key": "key"},
            headers={"Authorization": f"Bearer {bootstrap_token}"},
        )

        assert response.status_code == 503
        data = await response.get_json()
        assert data["error"] == "No available clusters"


@pytest.mark.asyncio
async def test_register_client_exception(app_with_sase: Quart, bootstrap_token: str) -> None:
    """Unexpected exception during registration returns 500."""
    os.environ["ENROLLMENT_BOOTSTRAP_TOKEN"] = bootstrap_token
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClusterManager") as mock_cluster_class:
        mock_cluster_class.side_effect = RuntimeError("boom")

        response = await client.post(
            "/api/v1/sdwan/clients",
            json={"name": "c", "type": "docker", "public_key": "key"},
            headers={"Authorization": f"Bearer {bootstrap_token}"},
        )

        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"


# --- GET /clients/<client_id>/config -----------------------------------------


@pytest.mark.asyncio
async def test_get_client_config_no_auth_header(app_with_sase: Quart) -> None:
    """Missing Authorization header returns 401."""
    client = app_with_sase.test_client()

    response = await client.get("/api/v1/sdwan/clients/client-1/config")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_client_config_unauthorized(app_with_sase: Quart) -> None:
    """authenticate_client returning None returns 401."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()
        mock_client_registry.authenticate_client = AsyncMock(return_value=None)

        response = await client.get(
            "/api/v1/sdwan/clients/client-1/config",
            headers={"Authorization": "Bearer bad-key"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_client_config_cluster_not_available(app_with_sase: Quart) -> None:
    """Client authenticates but cluster lookup returns None -> 503."""
    client = app_with_sase.test_client()

    with (
        patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class,
        patch("hub_api.modules.sdwan.api.clients.ClusterManager") as mock_cluster_class,
    ):
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()
        mock_client_registry.authenticate_client = AsyncMock(return_value=_client_obj())

        mock_cluster_mgr = AsyncMock()
        mock_cluster_class.return_value = mock_cluster_mgr
        mock_cluster_mgr.initialize = AsyncMock()
        mock_cluster_mgr.get_cluster = AsyncMock(return_value=None)

        response = await client.get(
            "/api/v1/sdwan/clients/client-1/config",
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 503
        data = await response.get_json()
        assert data["error"] == "Cluster not available"


@pytest.mark.asyncio
async def test_get_client_config_exception(app_with_sase: Quart) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_class.side_effect = RuntimeError("boom")

        response = await client.get(
            "/api/v1/sdwan/clients/client-1/config",
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500


# --- PUT /clients/<client_id>/tunnel-config ----------------------------------


@pytest.mark.asyncio
async def test_update_tunnel_config_no_auth_header(app_with_sase: Quart) -> None:
    """Missing auth header returns 401."""
    client = app_with_sase.test_client()

    response = await client.put(
        "/api/v1/sdwan/clients/client-1/tunnel-config",
        json={"tunnel_mode": "full"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_tunnel_config_invalid_mode(app_with_sase: Quart) -> None:
    """Invalid tunnel_mode returns 400."""
    client = app_with_sase.test_client()

    response = await client.put(
        "/api/v1/sdwan/clients/client-1/tunnel-config",
        json={"tunnel_mode": "bogus"},
        headers={"Authorization": "Bearer key"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Invalid tunnel_mode" in data["error"]


@pytest.mark.asyncio
async def test_update_tunnel_config_routes_not_list(app_with_sase: Quart) -> None:
    """split_tunnel_routes that isn't a list returns 400."""
    client = app_with_sase.test_client()

    response = await client.put(
        "/api/v1/sdwan/clients/client-1/tunnel-config",
        json={"tunnel_mode": "split", "split_tunnel_routes": "not-a-list"},
        headers={"Authorization": "Bearer key"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "must be a list" in data["error"]


@pytest.mark.asyncio
async def test_update_tunnel_config_route_not_string(app_with_sase: Quart) -> None:
    """A non-string route entry returns 400."""
    client = app_with_sase.test_client()

    response = await client.put(
        "/api/v1/sdwan/clients/client-1/tunnel-config",
        json={"tunnel_mode": "split", "split_tunnel_routes": [123]},
        headers={"Authorization": "Bearer key"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Invalid route format" in data["error"]


@pytest.mark.asyncio
async def test_update_tunnel_config_invalid_route_format(app_with_sase: Quart) -> None:
    """A route that's neither IP/CIDR nor domain returns 400."""
    client = app_with_sase.test_client()

    response = await client.put(
        "/api/v1/sdwan/clients/client-1/tunnel-config",
        json={"tunnel_mode": "split", "split_tunnel_routes": ["!!!not-valid!!!"]},
        headers={"Authorization": "Bearer key"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert "Invalid route" in data["error"]


@pytest.mark.asyncio
async def test_update_tunnel_config_unauthorized(app_with_sase: Quart) -> None:
    """authenticate_client returning None returns 401."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()
        mock_client_registry.authenticate_client = AsyncMock(return_value=None)

        response = await client.put(
            "/api/v1/sdwan/clients/client-1/tunnel-config",
            json={"tunnel_mode": "full"},
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_tunnel_config_update_failed(app_with_sase: Quart) -> None:
    """update_client_status returning False returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()
        mock_client_registry.authenticate_client = AsyncMock(return_value=_client_obj())
        mock_client_registry.update_client_status = AsyncMock(return_value=False)

        response = await client.put(
            "/api/v1/sdwan/clients/client-1/tunnel-config",
            json={"tunnel_mode": "full"},
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Failed to update configuration"


@pytest.mark.asyncio
async def test_update_tunnel_config_exception(app_with_sase: Quart) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_class.side_effect = RuntimeError("boom")

        response = await client.put(
            "/api/v1/sdwan/clients/client-1/tunnel-config",
            json={"tunnel_mode": "full"},
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500


# --- POST /clients/<client_id>/rotate-key ------------------------------------


@pytest.mark.asyncio
async def test_rotate_client_key_no_auth_header(app_with_sase: Quart) -> None:
    """Missing auth header returns 401."""
    client = app_with_sase.test_client()

    response = await client.post("/api/v1/sdwan/clients/client-1/rotate-key")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rotate_client_key_unauthorized(app_with_sase: Quart) -> None:
    """authenticate_client returning None returns 401."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()
        mock_client_registry.authenticate_client = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/sdwan/clients/client-1/rotate-key",
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_rotate_client_key_failed(app_with_sase: Quart) -> None:
    """rotate_api_key returning None returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()
        mock_client_registry.authenticate_client = AsyncMock(return_value=_client_obj())
        mock_client_registry.rotate_api_key = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/sdwan/clients/client-1/rotate-key",
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Failed to rotate key"


@pytest.mark.asyncio
async def test_rotate_client_key_exception(app_with_sase: Quart) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_class.side_effect = RuntimeError("boom")

        response = await client.post(
            "/api/v1/sdwan/clients/client-1/rotate-key",
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500


# --- POST /clients/<client_id>/metrics ---------------------------------------


@pytest.mark.asyncio
async def test_submit_client_metrics_no_auth_header(app_with_sase: Quart) -> None:
    """Missing auth header returns 401."""
    client = app_with_sase.test_client()

    response = await client.post("/api/v1/sdwan/clients/client-1/metrics", json={"metrics": {}})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_submit_client_metrics_unauthorized(app_with_sase: Quart) -> None:
    """authenticate_client returning None returns 401."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_registry = AsyncMock()
        mock_client_class.return_value = mock_client_registry
        mock_client_registry.initialize = AsyncMock()
        mock_client_registry.authenticate_client = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/sdwan/clients/client-1/metrics",
            json={"metrics": {}},
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
async def test_submit_client_metrics_exception(app_with_sase: Quart) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_class.side_effect = RuntimeError("boom")

        response = await client.post(
            "/api/v1/sdwan/clients/client-1/metrics",
            json={"metrics": {}},
            headers={"Authorization": "Bearer key"},
        )

        assert response.status_code == 500


# --- POST /clients/headends/<headend_id>/metrics -----------------------------


@pytest_asyncio.fixture
async def machine_jwt_metrics(app_with_sase: Quart) -> str:
    """Generate a valid machine-JWT with metrics:write scope for tenant 'default'.

    Args:
        app_with_sase: App with key provider configured.

    Returns:
        Encoded machine-JWT token.
    """
    provider = app_with_sase.config["KEY_PROVIDER"]

    claims = build_machine_claims(
        sub_id="cluster-1",
        node_type="kubernetes_node",
        tenant="default",
        iss="tobogganing",
        aud="headend",
    )

    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest.mark.asyncio
async def test_submit_headend_metrics_success(
    app_with_sase: Quart, machine_jwt_metrics: str
) -> None:
    """Valid machine-JWT and matching cluster ID returns 200."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClusterManager") as mock_cluster_class:
        mock_cluster_mgr = AsyncMock()
        mock_cluster_class.return_value = mock_cluster_mgr
        mock_cluster_mgr.initialize = AsyncMock()
        mock_cluster_mgr.get_cluster = AsyncMock(
            return_value=_cluster_obj(id="cluster-1", tenant="default")
        )

        response = await client.post(
            "/api/v1/sdwan/clients/headends/cluster-1/metrics",
            json={"cpu": 10},
            headers={"Authorization": f"Bearer {machine_jwt_metrics}"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "metrics_received"


@pytest.mark.asyncio
async def test_submit_headend_metrics_cluster_not_found(
    app_with_sase: Quart, machine_jwt_metrics: str
) -> None:
    """Unknown cluster returns 401."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClusterManager") as mock_cluster_class:
        mock_cluster_mgr = AsyncMock()
        mock_cluster_class.return_value = mock_cluster_mgr
        mock_cluster_mgr.initialize = AsyncMock()
        mock_cluster_mgr.get_cluster = AsyncMock(return_value=None)

        response = await client.post(
            "/api/v1/sdwan/clients/headends/cluster-1/metrics",
            json={"cpu": 10},
            headers={"Authorization": f"Bearer {machine_jwt_metrics}"},
        )

        assert response.status_code == 401
        data = await response.get_json()
        assert "cluster not found" in data["error"]


@pytest.mark.asyncio
async def test_submit_headend_metrics_id_mismatch(
    app_with_sase: Quart, machine_jwt_metrics: str
) -> None:
    """Cluster ID mismatch returns 401."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClusterManager") as mock_cluster_class:
        mock_cluster_mgr = AsyncMock()
        mock_cluster_class.return_value = mock_cluster_mgr
        mock_cluster_mgr.initialize = AsyncMock()
        mock_cluster_mgr.get_cluster = AsyncMock(
            return_value=_cluster_obj(id="different-cluster", tenant="default")
        )

        response = await client.post(
            "/api/v1/sdwan/clients/headends/cluster-1/metrics",
            json={"cpu": 10},
            headers={"Authorization": f"Bearer {machine_jwt_metrics}"},
        )

        assert response.status_code == 401
        data = await response.get_json()
        assert "cluster ID mismatch" in data["error"]


@pytest.mark.asyncio
async def test_submit_headend_metrics_exception(
    app_with_sase: Quart, machine_jwt_metrics: str
) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClusterManager") as mock_cluster_class:
        mock_cluster_class.side_effect = RuntimeError("boom")

        response = await client.post(
            "/api/v1/sdwan/clients/headends/cluster-1/metrics",
            json={"cpu": 10},
            headers={"Authorization": f"Bearer {machine_jwt_metrics}"},
        )

        assert response.status_code == 500


# --- GET /clients (list_clients) ---------------------------------------------


@pytest.mark.asyncio
async def test_list_clients_exception(app_with_sase: Quart, valid_tenant_token: str) -> None:
    """Unexpected exception returns 500."""
    client = app_with_sase.test_client()

    with patch("hub_api.modules.sdwan.api.clients.ClientRegistry") as mock_client_class:
        mock_client_class.side_effect = RuntimeError("boom")

        with patch("hub_api.entitlements.gate.feature_enabled") as mock_flag:
            mock_flag.return_value = True

            response = await client.get(
                "/api/v1/sdwan/clients",
                headers={"Authorization": f"Bearer {valid_tenant_token}"},
            )

            assert response.status_code == 500
