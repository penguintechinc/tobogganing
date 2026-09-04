"""Seam 2 (P5-E2E/D): zone/record CRUD via the control-plane REST API ->
real gRPC GetConfig reflects the change; delete -> GetConfig no longer
returns it.

Regression: penguin-dal comma-syntax TypeError (``db(a, b)`` silently drops
the second condition — see test_netsvcs_isolation_realdal.py) — the
ConfigService/ZoneManager query path exercised here across the REST->gRPC
seam is the same `&`-chained-query path that bug class affects.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.modules.netsvcs.grpc.server import ENROLLMENT_TENANT
from proto.netsvcs.v1 import manager_pb2


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Test app with netsvcs module registered (mirrors test_netsvcs_zones.py)."""
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = ENROLLMENT_TENANT

    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def app_with_netsvcs_realdal(
    app_with_netsvcs: Quart, real_dal: AsyncDB, monkeypatch: Any
) -> Quart:
    """Swap ``get_db()`` -> ``real_dal`` everywhere the netsvcs REST routes import it."""
    get_db_func = lambda: real_dal  # noqa: E731

    monkeypatch.setattr("hub_api.db.get_db", get_db_func)

    import hub_api.app

    monkeypatch.setattr(hub_api.app, "get_db", get_db_func)

    import hub_api.modules.netsvcs.api.zones

    monkeypatch.setattr(hub_api.modules.netsvcs.api.zones, "get_db", get_db_func)

    app_with_netsvcs.db = real_dal
    return app_with_netsvcs


@pytest_asyncio.fixture
async def enrollment_tenant_token(app_with_netsvcs_realdal: Quart) -> str:
    """JWT for the shared resolver-fleet ("enrollment") tenant with dns:read/write."""
    provider = app_with_netsvcs_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "control-plane-operator",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": ENROLLMENT_TENANT,
        "scope": "dns:read dns:write",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest.mark.asyncio
async def test_zone_record_crud_reflected_in_grpc_getconfig_then_delete_removes_it(
    app_with_netsvcs_realdal: Quart,
    enrollment_tenant_token: str,
    manager_grpc_harness,
    real_dal: AsyncDB,
) -> None:
    """REST create -> real gRPC GetConfig sees it; REST delete -> GetConfig
    no longer returns it."""
    client = app_with_netsvcs_realdal.test_client()

    with (
        patch("hub_api.entitlements.gate.feature_enabled", return_value=True),
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
    ):
        # --- REST: create zone + record under the shared enrollment tenant ---
        zone_resp = await client.post(
            "/api/v1/netsvcs/zones",
            headers={"Authorization": f"Bearer {enrollment_tenant_token}"},
            json={"name": "seam2.example.com", "visibility": "public"},
        )
        assert zone_resp.status_code == 201
        zone_data = await zone_resp.get_json()
        zone_id = zone_data["id"]

        record_resp = await client.post(
            f"/api/v1/netsvcs/zones/{zone_id}/records",
            headers={"Authorization": f"Bearer {enrollment_tenant_token}"},
            json={"name": "api", "type": "A", "value": "203.0.113.9", "ttl": 120},
        )
        assert record_resp.status_code == 201

        # --- gRPC: GetConfig (real wire, ephemeral port) sees the new zone/record ---
        # Machine-JWT is minted with the gRPC harness's own key_provider (the
        # one ManagerServicer.GetConfig verifies against) — independent of
        # the REST app's human-operator key_provider used for zone CRUD above.
        server_id = "resolver-seam2-1"
        machine_claims = build_machine_claims(
            sub_id=server_id,
            node_type="dns_resolver",
            tenant=ENROLLMENT_TENANT,
            iss="tobogganing",
        )
        machine_jwt = await encode_access_token(
            machine_claims, manager_grpc_harness.key_provider, ttl_hours=1
        )

        response = await manager_grpc_harness.stub.GetConfig(
            manager_pb2.GetConfigRequest(api_version="v1", server_id=server_id),
            metadata=[("authorization", f"Bearer {machine_jwt}")],
        )
        zone_names = {z.name for z in response.config.zones}
        assert "seam2.example.com" in zone_names
        created_zone = next(z for z in response.config.zones if z.name == "seam2.example.com")
        assert {r.name for r in created_zone.records} == {"api"}
        assert created_zone.records[0].value == "203.0.113.9"

        # --- REST: delete the zone ---
        del_resp = await client.delete(
            f"/api/v1/netsvcs/zones/{zone_id}",
            headers={"Authorization": f"Bearer {enrollment_tenant_token}"},
        )
        assert del_resp.status_code == 200

        # --- gRPC: GetConfig no longer returns it ---
        response2 = await manager_grpc_harness.stub.GetConfig(
            manager_pb2.GetConfigRequest(api_version="v1", server_id=server_id),
            metadata=[("authorization", f"Bearer {machine_jwt}")],
        )
        zone_names2 = {z.name for z in response2.config.zones}
        assert "seam2.example.com" not in zone_names2
