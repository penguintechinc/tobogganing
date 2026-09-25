"""Exception-handler branch coverage for every netsvcs zones API route.

Every route in modules/netsvcs/api/zones.py wraps its body in
try/except Exception -> 500, but none of those handlers were ever
triggered by tests/test_netsvcs_zones.py (which only exercises success
and manager-returns-None branches). This file forces ZoneManager/
ConfigService methods to raise so each route's 500 path is covered.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart


@pytest.fixture
def app_with_netsvcs(app: Quart, mock_db: MagicMock) -> Quart:
    """Test app with netsvcs module registered."""
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider
    app.config["ENROLLMENT_TENANT"] = "default"

    from hub_api.modules.netsvcs import module as netsvcs_module

    netsvcs_contract = netsvcs_module()
    app.registry.register(netsvcs_contract)

    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    return app


@pytest_asyncio.fixture
async def tenant_token(app_with_netsvcs: Quart) -> str:
    from hub_api.auth.jwt import encode_access_token

    provider = app_with_netsvcs.config["KEY_PROVIDER"]
    claims = {
        "sub": "user-1",
        "iss": "tobogganing",
        "aud": "tobogganing",
        "tenant": "tenant-exc",
        "scope": "dns:read dns:write",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest.fixture(autouse=True)
def _feature_flag_on() -> object:
    with patch("hub_api.entitlements.gate.feature_enabled", return_value=True) as m:
        yield m


@pytest.mark.asyncio
async def test_list_zones_exception_returns_500(app_with_netsvcs: Quart, tenant_token: str) -> None:
    """list_zones() returns 500 when ZoneManager.list_zones() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.list_zones = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/zones", headers={"Authorization": f"Bearer {tenant_token}"}
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_create_zone_exception_returns_500(
    app_with_netsvcs: Quart, tenant_token: str
) -> None:
    """create_zone() returns 500 when ZoneManager.create_zone() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.create_zone = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.post(
            "/api/v1/netsvcs/zones",
            headers={"Authorization": f"Bearer {tenant_token}"},
            json={"name": "exc.com"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_zone_exception_returns_500(app_with_netsvcs: Quart, tenant_token: str) -> None:
    """get_zone() returns 500 when ZoneManager.get_zone() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.get_zone = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/zones/zone-1", headers={"Authorization": f"Bearer {tenant_token}"}
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_update_zone_exception_returns_500(
    app_with_netsvcs: Quart, tenant_token: str
) -> None:
    """update_zone() returns 500 when ZoneManager.update_zone() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.update_zone = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.put(
            "/api/v1/netsvcs/zones/zone-1",
            headers={"Authorization": f"Bearer {tenant_token}"},
            json={"name": "renamed.com"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_delete_zone_exception_returns_500(
    app_with_netsvcs: Quart, tenant_token: str
) -> None:
    """delete_zone() returns 500 when ZoneManager.delete_zone() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.delete_zone = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.delete(
            "/api/v1/netsvcs/zones/zone-1", headers={"Authorization": f"Bearer {tenant_token}"}
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_list_records_exception_returns_500(
    app_with_netsvcs: Quart, tenant_token: str
) -> None:
    """list_records() returns 500 when ZoneManager.list_records() raises (after get_zone ok)."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.get_zone = AsyncMock(return_value=MagicMock())
        mock_mgr.list_records = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.get(
            "/api/v1/netsvcs/zones/zone-1/records",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_create_record_exception_returns_500(
    app_with_netsvcs: Quart, tenant_token: str
) -> None:
    """create_record() returns 500 when ZoneManager.create_record() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.create_record = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.post(
            "/api/v1/netsvcs/zones/zone-1/records",
            headers={"Authorization": f"Bearer {tenant_token}"},
            json={"name": "www", "type": "A", "value": "1.2.3.4"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_update_record_exception_returns_500(
    app_with_netsvcs: Quart, tenant_token: str
) -> None:
    """update_record() returns 500 when ZoneManager.update_record() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.update_record = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.put(
            "/api/v1/netsvcs/zones/zone-1/records/record-1",
            headers={"Authorization": f"Bearer {tenant_token}"},
            json={"value": "5.6.7.8"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_delete_record_exception_returns_500(
    app_with_netsvcs: Quart, tenant_token: str
) -> None:
    """delete_record() returns 500 when ZoneManager.delete_record() raises."""
    client = app_with_netsvcs.test_client()
    with patch("hub_api.modules.netsvcs.api.zones.ZoneManager") as MockZM:
        mock_mgr = AsyncMock()
        mock_mgr.delete_record = AsyncMock(side_effect=RuntimeError("boom"))
        MockZM.return_value = mock_mgr

        response = await client.delete(
            "/api/v1/netsvcs/zones/zone-1/records/record-1",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )

    assert response.status_code == 500
