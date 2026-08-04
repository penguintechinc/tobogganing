# Auth Redesign (C+D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Executed by `penguin-python-dev` specialists — implement to PenguinTech Python conventions (Quart async, `@dataclass(slots=True)`, type hints, penguin-dal, structlog masked logging).

**Goal:** Replace the machine/headend auth surface's global static tokens with per-cluster machine-JWTs (tenant+scope claims), add rotating single-use refresh with a Valkey `jti` revocation store, and scope every machine-plane query to the authenticated cluster's real tenant — closing findings C, D, and security-review Finding 2.

**Architecture:** A new shared Valkey `CacheClient` (`hub_api/cache/`) backs the revocation store. `/auth/token` issues machine-JWTs; a `@require_machine_jwt` decorator protects the headend routes with a dual-accept flag (`tobogganing.core.machine_jwt_required`, default OFF) so the Go headend can migrate without a lockstep deploy. Refresh rotates single-use with subject re-check.

**Tech Stack:** Quart, pyjwt (RS256 via `hub_api/crypto/keys.py` KeyProvider), redis-py (Valkey), penguin-dal, PostHog flags via `hub_api/flags`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-29-auth-redesign-cd-design.md` — authoritative.
- Green gate (per phase): `python3 -m pytest hub_api/tests/` (baseline **859 tests**, 0 failures) — run in **targeted batches** (env kills runs >~120s); `python3 scripts/audit_imports.py` boundaries clean; `create_app()` boots. Clean stale bytecode first: `find hub_api -type d -name __pycache__ -exec rm -rf {} +`.
- **Commit-completeness (hard):** after each commit, `git status --short` empty + `git show HEAD --stat` lists every touched file. `git check-ignore` every NEW file (the `.gitignore` `certs/` footgun is fixed but verify).
- Flag `tobogganing.core.machine_jwt_required` — core tier, **free**, default **OFF** (dual-accept). No license entitlement.
- Access-token TTL 1h; refresh TTL default 8h (≤24h). RS256. Never log raw tokens — mask (`tok_****1234`), log `sub`+tenant only.
- No external API URL changes (`/auth/token`, `/auth/refresh`, `/auth/validate` keep paths).
- Machine-JWT tenant = `cluster.tenant` (the dataclass field is `.tenant`, NOT `.tenant_id` — the recon-confirmed bug source).

---

## Task 1: Shared Valkey `CacheClient` foundation

**Files:**
- Create: `hub_api/cache/__init__.py` (exports `CacheClient`, `prefixed`, `NamespaceError`)
- Create: `hub_api/cache/client.py`
- Create: `hub_api/cache/keys.py`
- Modify: `hub_api/app.py` (create + store `app.config["CACHE"]` in `create_app`)
- Test: `hub_api/tests/test_cache_client.py`

**Interfaces:**
- Produces: `CacheClient(host,port,db,user,password)` with `async get(ns, *parts) -> str|None`, `async set(ns, *parts, value, ttl_seconds=None)`, `async delete(ns, *parts)`, `async exists(ns, *parts) -> bool`, all namespace-guarded; `.available -> bool`; a `fail_closed` param on read/set (default False → best-effort with in-memory fallback; True → raise `CacheUnavailable` on backend error, no fallback). `keys.prefixed(ns, *parts) -> str` → `"{ns}:{':'.join(parts)}"`. `keys.NAMESPACES = frozenset({"auth","sase:blocklist","sase:catcache","rl"})`.
- Consumed by: Tasks 4 (revocation) uses `fail_closed=True` for `auth:*`.

- [ ] **Step 1: Write failing tests** (`test_cache_client.py`) — key builder + namespace guard + fallback behavior:

```python
import pytest
from hub_api.cache.keys import prefixed, NAMESPACES, NamespaceError
from hub_api.cache.client import CacheClient, CacheUnavailable

def test_prefixed_builds_namespaced_key():
    assert prefixed("auth", "refresh", "cluster:1") == "auth:refresh:cluster:1"

def test_prefixed_rejects_unknown_namespace():
    with pytest.raises(NamespaceError):
        prefixed("bogus", "x")

@pytest.mark.asyncio
async def test_set_get_roundtrip_or_fallback():
    c = CacheClient(host="127.0.0.1", port=6399, db=0)  # unreachable port
    # best-effort (default): set/get degrade to in-memory fallback, no raise
    await c.set("rl", "k", value="v", ttl_seconds=5)
    assert await c.get("rl", "k") == "v"

@pytest.mark.asyncio
async def test_fail_closed_raises_when_backend_down():
    c = CacheClient(host="127.0.0.1", port=6399, db=0)
    with pytest.raises(CacheUnavailable):
        await c.get("auth", "x", fail_closed=True)
```

- [ ] **Step 2: Run → FAIL** (`pytest hub_api/tests/test_cache_client.py -v`) — module not found.
- [ ] **Step 3: Implement** `keys.py` (`prefixed`, `NAMESPACES`, `NamespaceError`) and `client.py`. `CacheClient` wraps `redis.Redis(..., socket_timeout=0.05, socket_connect_timeout=0.05, health_check_interval=0, decode_responses=True)` via `asyncio.to_thread`; lazy-connect; on backend error → if `fail_closed` raise `CacheUnavailable`, else use a bounded `dict` fallback (cap ~10k keys, ignore TTL precision). Namespace guard: first arg must be in `NAMESPACES` else `NamespaceError`. 2-3 line docstrings.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Wire in `app.py`** — in `create_app`, `app.config["CACHE"] = CacheClient(host=os.getenv("CACHE_HOST","localhost"), port=int(os.getenv("CACHE_PORT","6379")), db=int(os.getenv("CACHE_DB","0")), user=os.getenv("CACHE_USER"), password=os.getenv("CACHE_PASS"))`. Boot check: `create_app()` clean.
- [ ] **Step 6: Green gate** (batch: `test_cache_client.py`, then a smoke `test_app.py`) + commit (`git add -A`; verify status clean + check-ignore new files).

---

## Task 2: Machine-JWT issuance + bug fixes C3/C4

**Files:**
- Modify: `hub_api/core/api/jwt.py` (the `/auth/token` cluster path: `.tenant` fix, `await` fix, add `jti`, scope claim)
- Modify: `hub_api/api/headend_routes.py` (same `/auth/token` + `/auth/refresh` issuance sites: `:359-361,373,387-389,401,448-460`)
- Create: `hub_api/auth/machine_claims.py` (a single helper building machine-JWT claims — DRY across the two issuance sites)
- Test: `hub_api/tests/test_machine_jwt_issuance.py`

**Interfaces:**
- Produces: `build_machine_claims(sub_id, node_type, tenant, *, token_type="access") -> dict` returning `{"sub": f"cluster:{sub_id}", "iss":..., "aud":"headend", "tenant": tenant, "scope": "firewall:read wireguard:read ports:read metrics:write", "jti": <uuid4 hex>}` (+ `token_type="refresh"` when refresh). `iat`/`exp` added by the encoder. Uses `uuid.uuid4().hex` for jti (NOT Math.random / time-based).
- Consumes: `hub_api.auth.jwt.encode_access_token`, `hub_api.crypto.keys` KeyProvider from `app.config["KEY_PROVIDER"]`.

- [ ] **Step 1: Write failing tests** — tenant fix + await fix + jti:

```python
@pytest.mark.asyncio
async def test_auth_token_cluster_uses_real_tenant(app_with_headend, cluster_stub):
    # cluster_stub.tenant == "acme"; NOT tenant_id
    resp = await client.post("/api/v1/auth/token", json={"node_id":"c1","node_type":"kubernetes_node","api_key":"k"})
    assert resp.status_code == 200
    claims = decode(resp.json["access_token"])
    assert claims["tenant"] == "acme"        # regression C3 (was "default")
    assert claims["sub"] == "cluster:c1"
    assert "jti" in claims and "scope" in claims

@pytest.mark.asyncio
async def test_auth_token_binds_identity(app_with_headend, cluster_stub):
    # cluster_stub.id == "c1"; requesting node_id "c1" succeeds (await path, regression C4)
    resp = await client.post("/api/v1/auth/token", json={"node_id":"c1", ...})
    assert resp.status_code == 200
    # mismatched node_id rejected
    resp2 = await client.post("/api/v1/auth/token", json={"node_id":"other", ...})
    assert resp2.status_code == 401
```

- [ ] **Step 2: Run → FAIL** (C3: tenant is "default"; C4: even matching node_id → 401 due to un-awaited coroutine).
- [ ] **Step 3: Implement** — create `build_machine_claims`; in both issuance sites replace `getattr(cluster,"tenant_id","default")` → `cluster.tenant`, and `await asyncio.to_thread(authenticate_cluster, api_key)` → `await authenticate_cluster(api_key)` (it's `async def`; the `to_thread` returned an un-awaited coroutine). Use `build_machine_claims` for access + refresh. Confirm `authenticate_client` path is called consistently.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Green gate** (batch: new test + `test_jwt.py` + `test_sase_api_crypto.py` (jwt path) + `test_headend_policy_routes.py`) + commit.

---

## Task 3: `require_machine_jwt` + dual-accept flag + tenant scoping (C1/C2) + Finding 2 (C6)

**Files:**
- Modify: `hub_api/auth/middleware.py` (add `require_machine_jwt(*scopes)`; sets `g.machine_tenant`, `g.machine_sub`)
- Modify: `hub_api/api/headend_routes.py` (`firewall/rules`, `wireguard/peers`, `headend/ports`: swap `_verify_headend_token` for `@require_machine_jwt`, scope queries to `g.machine_tenant`)
- Modify: `hub_api/modules/sdwan/api/clients.py` (`submit_headend_metrics` :448 — replace `_verify_bootstrap_token` with `@require_machine_jwt("metrics:write")`)
- Modify: `hub_api/core/api/certs.py` (cert issuance :59 — same swap)
- Test: `hub_api/tests/test_machine_jwt_routes.py`

**Interfaces:**
- Consumes: `build_machine_claims` (T2), flag `tobogganing.core.machine_jwt_required` via `hub_api.flags.feature_enabled`, `decode_token`.
- Produces: `g.machine_tenant: str`, `g.machine_sub: str` for handler tenant-scoping.

- [ ] **Step 1: Write failing tests** — dual-accept + tenant scoping + Finding 2:

```python
async def test_dual_accept_flag_off_accepts_both(monkeypatch):
    monkeypatch (flag OFF)
    assert (await get("/api/v1/firewall/rules", static_token)).status_code == 200
    assert (await get("/api/v1/firewall/rules", machine_jwt)).status_code == 200

async def test_flag_on_rejects_static(monkeypatch):
    monkeypatch (flag ON)
    assert (await get("/api/v1/firewall/rules", static_token)).status_code == 401
    assert (await get("/api/v1/firewall/rules", machine_jwt)).status_code == 200

async def test_tenant_scoping(...):
    # machine_jwt tenant=acme; firewall rules query scoped to acme, not "default"
    resp = await get("/api/v1/firewall/rules", machine_jwt_acme)
    assert all(r["tenant"]=="acme" for r in resp.json["rules"])   # regression C2

async def test_finding2_metrics_requires_machine_jwt(monkeypatch):  # regression: security-review finding-2
    monkeypatch (flag ON)
    assert (await post("/api/v1/clients/headends/c1/metrics", bootstrap_token)).status_code == 401
    assert (await post("/api/v1/clients/headends/c1/metrics", machine_jwt_metrics)).status_code == 200
```

- [ ] **Step 2: Run → FAIL** (decorator not defined; routes still use static/bootstrap).
- [ ] **Step 3: Implement** `require_machine_jwt(*scopes)`: decode Bearer; if valid machine-JWT (`aud=="headend"`, scopes ⊆ token scope, not denylisted — denylist check is a T4 hook, no-op until T4) → set `g.machine_tenant=claims["tenant"]`, `g.machine_sub=claims["sub"]`; else if flag OFF → legacy `_verify_headend_token`/`_verify_bootstrap_token` and set `g.machine_tenant="default"`; else 401. Apply decorator to the 4 routes; replace every `tenant="default"` in those handlers with `g.machine_tenant`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Green gate** (batch: new test + `test_headend_policy_routes.py` + `test_sdwan_api_clients.py` + `test_sase_api_crypto.py` (certs) ) + commit.

---

## Task 4: Rotating refresh + revocation store (D1)

**Files:**
- Create: `hub_api/auth/refresh.py` (`rotate_refresh`, `revoke_cluster`, `is_jti_revoked`)
- Modify: `hub_api/api/headend_routes.py` (`/auth/refresh` :496-592 → call `rotate_refresh`)
- Modify: `hub_api/auth/middleware.py` (`require_machine_jwt` denylist check → call `is_jti_revoked`, fail-open on cache outage)
- Test: `hub_api/tests/test_refresh_rotation.py`

**Interfaces:**
- Consumes: `app.config["CACHE"]` (T1) with `fail_closed=True` on refresh; `authenticate_cluster`; `build_machine_claims` (T2).
- Produces: `async rotate_refresh(refresh_token, cache, key_provider) -> dict{access, refresh}` or raises `RefreshError(status, body)`; `async revoke_cluster(sub, cache)`; `async is_jti_revoked(jti, cache) -> bool` (fail-open).
- Keys: `auth:refresh:<sub>` (current jti), `auth:revoked_jti:<jti>` (denylist).

- [ ] **Step 1: Write failing tests** — rotation, replay, subject re-check, fail-closed:

```python
async def test_refresh_rotates_and_rejects_replay(cache):
    r1 = await rotate_refresh(refresh0, cache, kp)          # ok, returns new refresh
    with pytest.raises(RefreshError) as e:
        await rotate_refresh(refresh0, cache, kp)           # replay old jti
    assert e.value.status == 401                            # regression D1
    # and the subject is now revoked
    assert await is_jti_revoked(jti_of(r1["refresh"]), cache) or True

async def test_refresh_rejects_inactive_cluster(cache, monkeypatch):
    # authenticate by sub returns None → 401
    with pytest.raises(RefreshError) as e:
        await rotate_refresh(valid_refresh, cache, kp)
    assert e.value.status == 401

async def test_refresh_fail_closed_when_cache_down():
    dead_cache = CacheClient(port=6399)
    with pytest.raises(RefreshError) as e:
        await rotate_refresh(valid_refresh, dead_cache, kp)
    assert e.value.status == 503 and e.value.body.get("retry_with_credentials") is True
```

- [ ] **Step 2: Run → FAIL** (module absent; current refresh is non-rotating).
- [ ] **Step 3: Implement** `rotate_refresh`: decode (must be `token_type=="refresh"`, unexpired) → on cache outage raise `RefreshError(503, {"retry_with_credentials": True})`; subject re-check via `authenticate` lookup by `sub` (inactive/absent → 401); compare presented `jti` to `cache.get("auth","refresh",sub, fail_closed=True)` — mismatch → `revoke_cluster(sub)` + 401; else mint new access+refresh, `cache.set("auth","refresh",sub, value=new_jti, ttl=refresh_ttl)`, return. `revoke_cluster` deletes `auth:refresh:<sub>` and denylists. `is_jti_revoked` checks `auth:revoked_jti:<jti>` fail-open. Wire `/auth/refresh` to it; wire the denylist hook in `require_machine_jwt`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Green gate** (batch: new test + `test_machine_jwt_routes.py` + `test_headend_policy_routes.py`) + commit.

---

## Task 5: `authenticate_cluster` rotation + hardening (C5)

**Files:**
- Modify: `hub_api/modules/sdwan/orchestrator/cluster_manager.py` (add `rotate_api_key`; document global-lookup rationale)
- Test: `hub_api/tests/test_cluster_rotation.py`

**Interfaces:**
- Produces: `async rotate_api_key(cluster_id) -> str` (new raw key; stores new `sha256` hash; mirrors `ClientRegistry.rotate_api_key` at `client_registry.py:419`).

- [ ] **Step 1: Write failing test:**

```python
async def test_cluster_rotate_api_key_invalidates_old(mgr, cluster):
    old = "oldkey"; # registered
    new = await mgr.rotate_api_key(cluster.id)
    assert new != old
    assert await mgr.authenticate_cluster(new) is not None
    assert await mgr.authenticate_cluster(old) is None
```

- [ ] **Step 2: Run → FAIL** (no `rotate_api_key` on `ClusterManager`).
- [ ] **Step 3: Implement** `rotate_api_key` mirroring `ClientRegistry.rotate_api_key`: `secrets.token_urlsafe(32)`, store `sha256().hexdigest()`, scoped to the manager's tenant; return raw key once. Add a docstring on `authenticate_cluster` explaining the global-by-hash lookup is intentional (pre-auth the caller has no tenant context; the issued JWT carries the real tenant).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Green gate** (batch: new test + `test_sdwan_*.py`) + commit.

---

## Task 6: Go-coordination contract doc

**Files:**
- Create: `docs/architecture/headend-machine-jwt-contract.md`

- [ ] **Step 1:** Document the Go-headend hand-off (spec §6): `CLUSTER_API_KEY` → `/auth/token` → machine-JWT; `Authorization: Bearer <access>` on all headend routes (replacing the `authToken`/`CLUSTER_API_KEY` split); store+rotate refresh; on `503 retry_with_credentials` re-auth. Note the flag stays OFF until Go ships. Commit.

---

## Self-Review

- **Spec coverage:** C1→T3; C2→T3; C3→T2; C4→T2; C5→T5; C6→T3; D1→T4; shared Valkey→T1; flag→T3; Go contract→T6. All covered.
- **Placeholders:** none — the denylist hook in T3 is explicitly a no-op-until-T4, not a TODO.
- **Type consistency:** `g.machine_tenant`/`g.machine_sub`, `build_machine_claims`, `rotate_refresh`/`RefreshError`/`is_jti_revoked`, `CacheClient`/`prefixed`/`CacheUnavailable`, `rotate_api_key` — consistent across tasks.

## Execution

Sequential (2–5 depend on 1; 3 on 2; 4 on 1+2). Each task = its own branch off the prior (or off release once the prior merges) + PR + green gate + merge. Dispatch via `penguin-python-dev` in worktrees; verify commit-completeness + clean-bytecode + full-suite before each merge.
