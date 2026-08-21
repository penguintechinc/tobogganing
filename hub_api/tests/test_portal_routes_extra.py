"""Additional coverage for api/portal_routes.py: the manifest error-handling branch.

test_portal_manifest_api.py covers the token/role/flags happy paths; this file
covers get_manifest()'s top-level exception handler.
"""

from __future__ import annotations

import pytest
from quart import Quart

from hub_api.auth.jwt import encode_access_token
from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair


@pytest.mark.asyncio
async def test_manifest_unexpected_exception_returns_403(
    app: Quart, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /portal/manifest returns 403 when building the manifest raises unexpectedly."""
    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    claims = {
        "sub": "u1",
        "iss": "test",
        "aud": "test",
        "tenant": "t1",
        "role": "admin",
    }
    token = await encode_access_token(claims, provider, ttl_hours=1)

    def raise_error() -> None:
        raise RuntimeError("registry broken")

    monkeypatch.setattr(app.registry, "modules", raise_error)

    client = app.test_client()
    resp = await client.get(
        "/api/v1/portal/manifest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    data = await resp.get_json()
    assert data["error"] == "Unauthorized: invalid token"
