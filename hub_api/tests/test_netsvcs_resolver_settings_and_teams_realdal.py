"""Real-DAL tests for s174: resolver-settings REST API and zone allowed_teams.

Drives the real blueprints against a migrated real_dal (migrations 0029/0030),
including cross-tenant isolation and scope enforcement.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from penguin_dal import AsyncDB
from quart import Quart

URL = "/api/v1/netsvcs/resolver-settings"
TEAM_A = str(uuid4())
TEAM_B = str(uuid4())


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Test app with the netsvcs module registered."""
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.modules.netsvcs import module as netsvcs_module
    from hub_api.registry import ModuleContext

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = "default"
    app.registry.register(netsvcs_module())
    app.registry.apply_to(
        app, ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    )
    return app


@pytest_asyncio.fixture
async def rapp(app_with_netsvcs: Quart, real_dal: AsyncDB, monkeypatch: Any) -> Quart:
    """Point every get_db() the blueprints use at real_dal."""
    import hub_api.app
    import hub_api.modules.netsvcs.api.resolver_settings as rs
    import hub_api.modules.netsvcs.api.zones as zones

    getter = lambda: real_dal  # noqa: E731
    monkeypatch.setattr("hub_api.db.get_db", getter)
    monkeypatch.setattr(hub_api.app, "get_db", getter)
    monkeypatch.setattr(zones, "get_db", getter)
    monkeypatch.setattr(rs, "get_db", getter)
    app_with_netsvcs.db = real_dal
    return app_with_netsvcs


async def _token(app: Quart, tenant: str, scope: str = "dns:read dns:write") -> dict[str, str]:
    """Bearer header for a tenant/scope."""
    from hub_api.auth.jwt import encode_access_token

    claims = {
        "sub": "u",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": tenant,
        "scope": scope,
    }
    tok = await encode_access_token(claims, app.config["KEY_PROVIDER"], ttl_hours=1)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(autouse=True)
def _flags_on() -> Any:
    """Enable netsvcs feature flags."""
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True) as m:
        yield m


@pytest.mark.asyncio
async def test_get_returns_defaults_then_put_persists(rapp: Quart) -> None:
    """GET defaults; PUT partial update persists, bumps version, GET reflects it."""
    from hub_api.modules.netsvcs.managers.config_service import (
        DEFAULT_RESOLVER_SETTINGS,
        ConfigService,
    )

    tenant = f"t-{uuid4()}"
    h = await _token(rapp, tenant)
    c = rapp.test_client()
    r = await c.get(URL, headers=h)
    assert r.status_code == 200
    assert await r.get_json() == DEFAULT_RESOLVER_SETTINGS

    before = await ConfigService(rapp.db, tenant).get_config_version()
    r = await c.put(URL, headers=h, json={"cache_ttl": 60, "enable_dnssec": True})
    assert r.status_code == 200
    body = await r.get_json()
    assert body["cache_ttl"] == 60 and body["enable_dnssec"] is True
    assert body["log_queries"] is True
    assert await ConfigService(rapp.db, tenant).get_config_version() == before + 1

    r = await c.get(URL, headers=h)
    assert (await r.get_json())["cache_ttl"] == 60


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{}, {"cache_ttl": -1}, {"cache_ttl": 86401}, {"cache_max_entries": 10_000_001}],
)
async def test_put_rejects_invalid(rapp: Quart, payload: dict[str, Any]) -> None:
    """Empty body and out-of-range values are 400 and write nothing."""
    tenant = f"t-{uuid4()}"
    h = await _token(rapp, tenant)
    c = rapp.test_client()
    r = await c.put(URL, headers=h, json=payload)
    assert r.status_code == 400
    rows = await rapp.db(rapp.db.dns_resolver_settings.tenant == tenant).select()
    assert rows.first() is None


@pytest.mark.asyncio
async def test_put_rejects_wrong_type(rapp: Quart) -> None:
    """quart-schema request validation rejects a non-bool for a bool field."""
    h = await _token(rapp, f"t-{uuid4()}")
    r = await rapp.test_client().put(URL, headers=h, json={"cache_enabled": "nope"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cross_tenant_isolation(rapp: Quart) -> None:
    """Tenant B never sees or alters tenant A's settings; tenant comes from JWT only."""
    ta, tb = f"a-{uuid4()}", f"b-{uuid4()}"
    ha, hb = await _token(rapp, ta), await _token(rapp, tb)
    c = rapp.test_client()
    assert (await c.put(URL, headers=ha, json={"cache_ttl": 42})).status_code == 200
    # B tries to smuggle A's tenant in the body: unknown field ignored/rejected,
    # never applied to A.
    await c.put(URL, headers=hb, json={"cache_ttl": 7, "tenant": ta})
    a = await (await c.get(URL, headers=ha)).get_json()
    b = await (await c.get(URL, headers=hb)).get_json()
    assert a["cache_ttl"] == 42
    assert b["cache_ttl"] in (7, 300)


@pytest.mark.asyncio
async def test_scope_enforced(rapp: Quart) -> None:
    """dns:read cannot PUT; no token is denied."""
    c = rapp.test_client()
    ro = await _token(rapp, f"t-{uuid4()}", scope="dns:read")
    assert (await c.get(URL, headers=ro)).status_code == 200
    assert (await c.put(URL, headers=ro, json={"cache_ttl": 5})).status_code == 403
    assert (await c.get(URL)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_feature_flag_off_blocks(rapp: Quart, _flags_on: MagicMock) -> None:
    """Flag OFF denies access."""
    _flags_on.return_value = False
    h = await _token(rapp, f"t-{uuid4()}")
    r = await rapp.test_client().get(URL, headers=h)
    assert r.status_code >= 400


@pytest.mark.asyncio
async def test_zone_allowed_teams_roundtrip_and_config(rapp: Quart) -> None:
    """allowed_teams persists via API and reaches the resolver config DTO + proto."""
    from hub_api.modules.netsvcs.grpc.server import ManagerServicer
    from hub_api.modules.netsvcs.managers.config_service import ConfigService

    tenant = f"t-{uuid4()}"
    h = await _token(rapp, tenant)
    c = rapp.test_client()
    r = await c.post(
        "/api/v1/netsvcs/zones",
        headers=h,
        json={
            "name": "corp.internal",
            "visibility": "restricted",
            "allowed_teams": [TEAM_A, TEAM_A],
        },
    )
    assert r.status_code == 201
    zone = await r.get_json()
    assert zone["allowed_teams"] == [TEAM_A]

    r = await c.put(
        f"/api/v1/netsvcs/zones/{zone['id']}", headers=h, json={"allowed_teams": [TEAM_A, TEAM_B]}
    )
    assert r.status_code == 200
    assert (await r.get_json())["allowed_teams"] == [TEAM_A, TEAM_B]

    got = await (await c.get(f"/api/v1/netsvcs/zones/{zone['id']}", headers=h)).get_json()
    assert got["allowed_teams"] == [TEAM_A, TEAM_B]

    cfg = await ConfigService(rapp.db, tenant).get_server_config()
    assert cfg.zones[0].allowed_teams == [TEAM_A, TEAM_B]
    proto = ManagerServicer(rapp.db, None, None)._dto_to_proto_config(cfg)
    assert list(proto.zones[0].allowed_teams) == [TEAM_A, TEAM_B]

    # Other tenant sees none of it.
    other = await _token(rapp, f"o-{uuid4()}")
    lst = await (await c.get("/api/v1/netsvcs/zones", headers=other)).get_json()
    assert lst["zones"] == []
    assert (await c.get(f"/api/v1/netsvcs/zones/{zone['id']}", headers=other)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("teams", [["team-a"], [123], "notalist"])
async def test_zone_allowed_teams_rejects_non_uuid(rapp: Quart, teams: list[Any]) -> None:
    """Team references must be UUIDs, never names."""
    h = await _token(rapp, f"t-{uuid4()}")
    r = await rapp.test_client().post(
        "/api/v1/netsvcs/zones",
        headers=h,
        json={"name": f"z{uuid4().hex[:6]}.com", "allowed_teams": teams},
    )
    assert r.status_code == 400


def test_proto_carries_allowed_teams() -> None:
    """The gRPC DNSZone message round-trips allowed_teams."""
    from proto.netsvcs.v1 import manager_pb2

    z = manager_pb2.DNSZone(id="z", name="n", visibility="internal", allowed_teams=[TEAM_A])
    assert list(manager_pb2.DNSZone.FromString(z.SerializeToString()).allowed_teams) == [TEAM_A]
