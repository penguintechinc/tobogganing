"""Contract tests for the waddleperf_c2c module.

These lock in the module wiring: Professional-tier entitlements resolve
through the registry (a key-format mismatch would silently downgrade the
gate to community), blueprints mount under the module base path, the
module is autodiscovered, and the tier gate returns 402 when unlicensed.
"""
from __future__ import annotations

from typing import Any

import pytest
from quart import Quart

from core.entitlements.gate import tier_of
from core.modules.waddleperf_c2c import module as c2c_module


C2C_FEATURES = ["endpoints", "runs", "matrix"]


def test_c2c_registered_in_module_autodiscovery() -> None:
    """waddleperf_c2c is listed for autodiscovery in core.modules."""
    import core.modules

    assert "waddleperf_c2c" in core.modules.__all__


def test_contract_entitlements_are_professional() -> None:
    """Every c2c feature entitlement is keyed '{module}.{feature}' at Professional tier.

    Regression guard: the gate looks up entitlements by ``waddleperf_c2c.<feature>``
    (no ``tobogganing.`` prefix). A prefixed key misses the registry and
    ``tier_of`` falls back to community, silently defeating the paid gate.
    """
    contract = c2c_module()
    keys = {e.feature: e.tier.lower() for e in contract.entitlements}
    for feature in C2C_FEATURES:
        key = f"waddleperf_c2c.{feature}"
        assert key in keys, f"missing entitlement {key}; got {sorted(keys)}"
        assert keys[key] == "professional", f"{key} must be professional"


def test_contract_flags_and_migrations() -> None:
    """Flags carry the tobogganing prefix; migrations reference 0014/0015."""
    contract = c2c_module()
    for feature in C2C_FEATURES:
        assert f"tobogganing.waddleperf_c2c.{feature}" in contract.flags
    assert contract.migrations == ["0014", "0015", "0020"]


def test_tier_of_resolves_professional_via_registry(app_with_c2c: Quart) -> None:
    """The registry resolves each c2c feature to the professional tier."""
    registry = app_with_c2c.registry
    for feature in C2C_FEATURES:
        assert tier_of(f"waddleperf_c2c.{feature}", registry) == "professional"


def test_c2c_blueprints_mounted(app_with_c2c: Quart) -> None:
    """Blueprints mount under /api/v1/waddleperf_c2c/{endpoints,runs,matrix}."""
    rules = {r.rule for r in app_with_c2c.url_map.iter_rules()}
    joined = "\n".join(sorted(rules))
    assert "/api/v1/waddleperf_c2c/endpoints" in joined
    assert "/api/v1/waddleperf_c2c/runs" in joined
    assert "/api/v1/waddleperf_c2c/matrix" in joined


@pytest.mark.asyncio
async def test_unlicensed_professional_request_returns_402(
    app: Quart, mock_db: Any, monkeypatch: Any, request: Any
) -> None:
    """Flag ON + Professional tier but NO license → 402 from the tier gate.

    This exercises the real entitlement path (not the flag-off path), proving
    the paid gate actually fires when the entitlement resolves to professional.
    """
    from core.crypto import InAppKeyProvider, generate_rsa_key_pair
    from core.auth.jwt import encode_access_token
    from core.registry import ModuleContext
    import shared.licensing.entitlements

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    app.config["KEY_PROVIDER"] = provider

    # Flag ON for c2c, but licensing stays at its default (professional → False).
    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.waddleperf_c2c."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)
    # NOTE: deliberately do NOT patch _is_licensed_for_tier — unlicensed path.

    from core.modules.waddleperf_c2c import module as c2c_mod

    app.registry.register(c2c_mod())
    ctx = ModuleContext(config=app.config_obj, db=mock_db, key_provider=provider)
    app.registry.apply_to(app, ctx)

    token = await encode_access_token(
        {
            "sub": "u",
            "iss": "test-app",
            "aud": "test-app",
            "tenant": "test-tenant",
            "scope": "c2c:read c2c:write",
        },
        provider,
        ttl_hours=1,
    )

    client = app.test_client()
    resp = await client.get(
        "/api/v1/waddleperf_c2c/endpoints",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402
