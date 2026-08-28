"""Shared fixtures for the perftest coverage-backfill test package (squawk-P5).

Provides real-DAL-backed Quart apps for the three WaddlePerf modules
(perftest_cluster, perftest_c2c, perftest_client) with all feature flags
force-enabled and a Professional license grant, plus write/read-only JWTs.
Mirrors the patterns already established in ``test_wpc_scheduled_tests.py``
and ``test_c2c_api_runs.py`` so tests here compose with the rest of the suite.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from quart import Quart


@pytest_asyncio.fixture
async def app_all_perftest_realdal(real_dal: Any, monkeypatch: Any) -> Quart:
    """Quart app with all three WaddlePerf modules mounted on a real DAL.

    All ``perftest.cluster`` / ``perftest.client`` / ``perftest.c2c`` feature
    flags are force-enabled and the license tier is pinned to professional so
    both community and professional-gated code paths are reachable.

    Args:
        real_dal: Real AsyncDB fixture (migrated temp sqlite) from conftest.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        Quart app with perftest_cluster, perftest_client, and perftest_c2c
        modules registered against a real database.
    """
    import hub_api.app as app_module
    import hub_api.db
    from hub_api.app import create_app
    from hub_api.crypto import InAppKeyProvider, generate_rsa_key_pair
    from hub_api.registry import ModuleContext

    test_app = create_app()
    test_app.config["TESTING"] = True

    private_pem, public_pem = generate_rsa_key_pair()
    provider = InAppKeyProvider(private_pem, public_pem)
    test_app.config["KEY_PROVIDER"] = provider

    get_db_func = lambda: real_dal  # noqa: E731
    monkeypatch.setattr(hub_api.db, "get_db", get_db_func)
    monkeypatch.setattr(app_module, "get_db", get_db_func)

    # Patch get_db in every API module that imports it directly (module-level
    # `from hub_api.db import get_db` binds a local name that monkeypatching
    # hub_api.db.get_db alone would not reach).
    api_modules_with_get_db = [
        "hub_api.modules.perftest_cluster.api.tests",
        "hub_api.modules.perftest_cluster.api.scheduled_tests",
        "hub_api.modules.perftest_cluster.api.alerts",
        "hub_api.modules.perftest_cluster.api.autoperf",
        "hub_api.modules.perftest_cluster.api.auto_checkins",
        "hub_api.modules.perftest_cluster.api.devices",
        "hub_api.modules.perftest_cluster.api.enrollment",
        "hub_api.modules.perftest_cluster.api.org_units",
        "hub_api.modules.perftest_cluster.api.stats",
        "hub_api.modules.perftest_cluster.api.live_test",
        "hub_api.modules.perftest_client.api.client_config",
        "hub_api.modules.perftest_client.api.schedules",
        "hub_api.modules.perftest_c2c.api.endpoints",
        "hub_api.modules.perftest_c2c.api.matrix",
        "hub_api.modules.perftest_c2c.api.runs",
        "hub_api.modules.perftest_c2c.api.regions",
        "hub_api.modules.perftest_c2c.api.recurring",
    ]
    import importlib

    for mod_name in api_modules_with_get_db:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "get_db"):
            monkeypatch.setattr(mod, "get_db", get_db_func)

    # Force all perftest.* feature flags on.
    import shared.licensing.entitlements

    original_flag_on = shared.licensing.entitlements._flag_on

    def mock_flag_on(flag_key: str, distinct_id: str = "system") -> bool:
        if flag_key.startswith("tobogganing.perftest."):
            return True
        return original_flag_on(flag_key, distinct_id)

    monkeypatch.setattr(shared.licensing.entitlements, "_flag_on", mock_flag_on)

    # Pin license tier to professional so tier-gated branches (webhook alert
    # channels, enrollment >5 devices, c2c) are exercised.
    import hub_api.entitlements.gate

    monkeypatch.setattr(hub_api.entitlements.gate, "_licensed_tier", lambda: "professional")

    from hub_api.modules.perftest_c2c import module as c2c_module
    from hub_api.modules.perftest_client import module as wpcl_module
    from hub_api.modules.perftest_cluster import module as wpc_module

    test_app.registry.register(wpc_module())
    test_app.registry.register(wpcl_module())
    test_app.registry.register(c2c_module())

    ctx = ModuleContext(config=test_app.config_obj, db=real_dal, key_provider=provider)
    test_app.registry.apply_to(test_app, ctx)

    return test_app


@pytest_asyncio.fixture
async def pf_write_token(app_all_perftest_realdal: Quart) -> str:
    """JWT with wildcard write/read scope for the combined perftest app.

    Args:
        app_all_perftest_realdal: App fixture providing the key provider.

    Returns:
        Encoded JWT with ``*:*`` scope.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_all_perftest_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:*",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest_asyncio.fixture
async def pf_readonly_token(app_all_perftest_realdal: Quart) -> str:
    """JWT with wildcard read-only scope for the combined perftest app.

    Args:
        app_all_perftest_realdal: App fixture providing the key provider.

    Returns:
        Encoded JWT with ``*:read`` scope.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_all_perftest_realdal.config["KEY_PROVIDER"]
    claims = {
        "sub": "test-user-ro",
        "iss": "test-app",
        "aud": "test-app",
        "tenant": "test-tenant",
        "scope": "*:read",
    }
    return await encode_access_token(claims, provider, ttl_hours=1)


@pytest_asyncio.fixture
async def pf_token_factory(app_all_perftest_realdal: Quart) -> Any:
    """Factory fixture to mint JWTs with arbitrary scope/tenant for the combined app.

    Args:
        app_all_perftest_realdal: App fixture providing the key provider.

    Returns:
        Async callable ``(scope: str, tenant: str = "test-tenant") -> str``.
    """
    from hub_api.auth.jwt import encode_access_token

    provider = app_all_perftest_realdal.config["KEY_PROVIDER"]

    async def _make(scope: str, tenant: str = "test-tenant", sub: str = "test-user") -> str:
        claims = {
            "sub": sub,
            "iss": "test-app",
            "aud": "test-app",
            "tenant": tenant,
            "scope": scope,
        }
        return await encode_access_token(claims, provider, ttl_hours=1)

    return _make
