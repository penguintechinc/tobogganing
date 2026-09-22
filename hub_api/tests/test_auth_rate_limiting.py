"""Integration tests for rate limiting on the pre-auth/machine-auth
credential endpoints: /api/v1/auth/login, /refresh-token, /logout
(hub_api/api/auth_routes.py) and /api/v1/auth/token, /refresh, /validate
(hub_api/api/headend_routes.py) -- security-audit 2026-09-21, Dim 3
(A04/A07): none of these had brute-force protection.

regression: no auth rate-limiting (security-audit 2026-09-21)

The limiters under test are module-level SlidingWindowRateLimiter
singletons that live for the whole test process, so each test below uses a
distinct X-Forwarded-For IP (and, where relevant, a distinct
account/api_key identifier) to avoid cross-test bucket collisions.
"""

from __future__ import annotations

import pytest
from quart import Quart

from hub_api.api import auth_routes as auth_routes_module
from hub_api.api import headend_routes as headend_routes_module


def _xff(ip_suffix: int) -> dict[str, str]:
    """Build an X-Forwarded-For header for a distinct test-scoped IP."""
    return {"X-Forwarded-For": f"198.51.100.{ip_suffix}"}


# ---------------------------------------------------------------------------
# /api/v1/auth/login -- dual bucket (IP + hashed account)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_under_limit_allowed(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) --
    under the limit, login requests reach the handler (401 for a bogus
    account, never 429)."""
    client = app.test_client()
    for i in range(auth_routes_module._LOGIN_MAX):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "under-limit-1@example.com", "password": "x"},
            headers=_xff(1),
        )
        assert resp.status_code != 429, f"call {i + 1} unexpectedly rate limited"


@pytest.mark.asyncio
async def test_login_over_limit_returns_429_with_retry_after(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    client = app.test_client()
    for _ in range(auth_routes_module._LOGIN_MAX):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "over-limit-1@example.com", "password": "x"},
            headers=_xff(2),
        )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "over-limit-1@example.com", "password": "x"},
        headers=_xff(2),
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    data = await resp.get_json()
    assert data["retry_after"] > 0


@pytest.mark.asyncio
async def test_login_same_ip_different_accounts_trips_ip_bucket(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- the
    IP bucket counts every attempt regardless of which account is
    targeted, so a spray across many accounts from one IP is still
    caught."""
    client = app.test_client()
    for i in range(auth_routes_module._LOGIN_MAX):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": f"spray-target-{i}@example.com", "password": "x"},
            headers=_xff(5),
        )
        assert resp.status_code != 429

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": "yet-another-target@example.com", "password": "x"},
        headers=_xff(5),
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_login_same_account_different_ips_trips_account_bucket(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- the
    account bucket counts every attempt against one account regardless of
    source IP, so a distributed spray against one account is still
    caught."""
    client = app.test_client()
    email = "distributed-target@example.com"
    for i in range(auth_routes_module._LOGIN_MAX):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "x"},
            headers=_xff(100 + i),
        )
        assert resp.status_code != 429

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "x"},
        headers=_xff(200),
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_login_rate_limit_response_shape_uniform(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- the
    429 body is the standard {error, retry_after} shape regardless of
    whether it was the IP or account bucket that tripped, so a caller
    cannot use the rate-limit response itself to infer account existence
    (security.md: differential limiting must not leak account existence)."""
    client = app.test_client()
    ip = _xff(300)
    email = "does-not-exist-shape-test@example.com"
    for _ in range(auth_routes_module._LOGIN_MAX):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "x"}, headers=ip)

    blocked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "x"}, headers=ip
    )
    assert blocked.status_code == 429
    body = await blocked.get_json()
    assert set(body.keys()) == {"error", "retry_after"}
    assert body["error"] == "Rate limit exceeded"


# ---------------------------------------------------------------------------
# /api/v1/auth/refresh-token, /api/v1/auth/logout -- IP-only bucket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_two_ips_limited_independently(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    client = app.test_client()

    for _ in range(auth_routes_module._REFRESH_MAX):
        resp = await client.post(
            "/api/v1/auth/refresh-token", json={"refresh_token": "bogus"}, headers=_xff(10)
        )
        assert resp.status_code != 429
    blocked = await client.post(
        "/api/v1/auth/refresh-token", json={"refresh_token": "bogus"}, headers=_xff(10)
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    # A different IP is unaffected by the first IP's exhausted bucket.
    other_ip = await client.post(
        "/api/v1/auth/refresh-token", json={"refresh_token": "bogus"}, headers=_xff(11)
    )
    assert other_ip.status_code != 429


@pytest.mark.asyncio
async def test_logout_over_limit_returns_429(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    client = app.test_client()
    ip = _xff(12)
    for _ in range(auth_routes_module._LOGOUT_MAX):
        await client.post("/api/v1/auth/logout", json={"refresh_token": "bogus"}, headers=ip)
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "bogus"}, headers=ip)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


# ---------------------------------------------------------------------------
# /api/v1/auth/token (machine), /refresh, /validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_machine_token_under_limit_allowed(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    client = app.test_client()
    for i in range(headend_routes_module._MACHINE_TOKEN_MAX):
        resp = await client.post(
            "/api/v1/auth/token",
            json={"node_id": "node-1", "node_type": "kubernetes_node", "api_key": "wrong"},
            headers=_xff(20),
        )
        assert resp.status_code != 429, f"call {i + 1} unexpectedly rate limited"


@pytest.mark.asyncio
async def test_machine_token_same_ip_different_api_keys_trips_ip_bucket(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- the
    IP bucket for /auth/token counts every attempt regardless of which
    api_key is guessed."""
    client = app.test_client()
    for i in range(headend_routes_module._MACHINE_TOKEN_MAX):
        resp = await client.post(
            "/api/v1/auth/token",
            json={
                "node_id": "node-1",
                "node_type": "kubernetes_node",
                "api_key": f"guess-{i}",
            },
            headers=_xff(21),
        )
        assert resp.status_code != 429

    blocked = await client.post(
        "/api/v1/auth/token",
        json={"node_id": "node-1", "node_type": "kubernetes_node", "api_key": "guess-final"},
        headers=_xff(21),
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.mark.asyncio
async def test_machine_token_same_api_key_different_ips_trips_key_bucket(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21) -- the
    hashed-api_key bucket counts every attempt at guessing one specific
    key regardless of source IP (distributed guessing is still caught);
    the raw api_key is never logged (security.md Token & Secret Hygiene)."""
    client = app.test_client()
    api_key = "distributed-guess-target"
    for i in range(headend_routes_module._MACHINE_TOKEN_MAX):
        resp = await client.post(
            "/api/v1/auth/token",
            json={"node_id": "node-1", "node_type": "kubernetes_node", "api_key": api_key},
            headers=_xff(120 + i),
        )
        assert resp.status_code != 429

    blocked = await client.post(
        "/api/v1/auth/token",
        json={"node_id": "node-1", "node_type": "kubernetes_node", "api_key": api_key},
        headers=_xff(220),
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_machine_refresh_over_limit_returns_429(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    client = app.test_client()
    ip = _xff(30)
    for _ in range(headend_routes_module._MACHINE_REFRESH_MAX):
        await client.post("/api/v1/auth/refresh", json={"refresh_token": "bogus"}, headers=ip)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "bogus"}, headers=ip)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_machine_validate_over_limit_returns_429(app: Quart) -> None:
    """regression: no auth rate-limiting (security-audit 2026-09-21)."""
    client = app.test_client()
    ip = _xff(31)
    for _ in range(headend_routes_module._MACHINE_VALIDATE_MAX):
        await client.post("/api/v1/auth/validate", headers={**ip, "Authorization": "Bearer bogus"})
    resp = await client.post(
        "/api/v1/auth/validate", headers={**ip, "Authorization": "Bearer bogus"}
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
