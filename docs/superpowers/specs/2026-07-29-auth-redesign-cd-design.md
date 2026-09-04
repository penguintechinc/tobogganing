# Auth Redesign (Findings C + D) — Design Spec

**Date**: 2026-07-29
**Status**: Design approved; ready for implementation plan
**Cross-references**:
- Hub topology spec §8 #11 (headend-auth-redesign / finding C), #12 (refresh-rotation / finding D), §10 (enrollment model): `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md`
- Security review Finding 2 (`submit_headend_metrics` bootstrap token)

## Goal

Replace the machine/headend auth surface's global static tokens with **per-cluster machine-JWTs carrying tenant + scope claims**, add **rotating single-use refresh tokens with a `jti` revocation store**, and scope every machine-plane query to the authenticated cluster's real tenant. This closes the two production-gating security findings (C + D) and security-review Finding 2. It also introduces a **shared Valkey client** that the SASE security layer reuses.

**Production gate**: findings C + D MUST land before the Quart brain serves production traffic.

## Current-state problems (from recon)

| # | Problem | Location |
|---|---------|----------|
| C1 | `firewall/rules`, `wireguard/peers`, `headend/ports` gated by one global static `HEADEND_API_TOKEN`, bypassing the OIDC tenant/scope model | `hub_api/api/headend_routes.py:147,209,747` |
| C2 | Those queries hardcode `tenant="default"` — no per-tenant scoping | `headend_routes.py:160,220,754` |
| C3 | Machine-JWT tenant read from nonexistent `cluster.tenant_id` attr → always `"default"` (the field is `.tenant`) | `headend_routes.py:373,401`; `core/api/jwt.py:115,143` |
| C4 | `asyncio.to_thread(authenticate_cluster, …)` on an **async** function returns an un-awaited coroutine → identity check `getattr(cluster,"id")==node_id` can never pass on this path | `headend_routes.py:359-361,387-389` |
| C5 | `authenticate_cluster` is a **global** hash lookup (not tenant-scoped) and has no rotation method | `sdwan/orchestrator/cluster_manager.py:108-164` |
| C6 (Finding 2) | `submit_headend_metrics` authenticates with the shared `ENROLLMENT_BOOTSTRAP_TOKEN`; `cluster.id==headend_id` guard is tautological | `sdwan/api/clients.py:448-493` |
| D1 | Refresh JWT is a non-rotating 24h token with no `jti`, no store, no revocation, no subject re-check → replayable; a revoked cluster keeps working | `headend_routes.py:496-592` |

## Decisions (locked)

1. **Mechanism**: per-cluster machine-JWT (spec §8 #11). SPIFFE/SPIRE remains the longer-term §8 #4 target — out of scope here.
2. **Transition**: dual-accept behind flag `tobogganing.core.machine_jwt_required` (**default OFF = accept legacy static token OR machine-JWT**; flip **ON** = machine-JWT only). No lockstep deploy with the Go headend.
3. **Revocation store**: **Valkey** (TTL-native, O(1)); the new shared client. **Fail-closed** on Valkey unavailability at refresh — the client falls back to re-authenticating with its `CLUSTER_API_KEY` (DB-backed, always available), so no hard outage.
4. **Scope boundary**: machine/headend auth only. The DB-backed **user** refresh path (also non-rotating) is a documented follow-up, NOT in this slice.

## Components

### 1. Shared Valkey client — `hub_api/cache/`

New package: a single async-friendly Valkey client the whole app shares, replacing the fragmented `redis.Redis(db=1)` / `db=2` instantiation.

- `hub_api/cache/client.py`: `CacheClient` — config from env (`CACHE_HOST`, `CACHE_PORT`, `CACHE_USER`, `CACHE_PASS`, `CACHE_DB`), a connection pool, `async` get/set/delete/exists/expire wrappers over `redis.Redis` via `asyncio.to_thread` with a short socket timeout (mirror the live-test limiter: 10-50ms, health_check_interval=0), and a **first-failure short-circuit to a bounded in-memory fallback** for non-security caches.
- `hub_api/cache/keys.py`: key-prefix helper enforcing per-service ACL namespaces. Canonical prefixes: `auth:*` (this slice), `sase:blocklist:*`, `sase:catcache:*` (future SASE), `rl:*` (rate-limit). A `prefixed(namespace, *parts)` builder; a `require_namespace` guard so a caller can only touch its declared prefix.
- Wired once in `app.py` via `app.config["CACHE"]`, created at `create_app()`.
- **Security-cache reads (revocation) do NOT use the in-memory fallback** — they fail-closed (see §3). The fallback is only for best-effort caches.
- Migrating existing `protection/` + live-test consumers onto this client is a **noted follow-up**, not part of this slice (they keep working as-is).
- Helm: recommend Valkey AOF persistence + a per-service ACL user with `~auth:*` key pattern for the brain.

### 2. Machine-JWT issuance — `hub_api/core/api/jwt.py` + `headend_routes.py`

`POST /api/v1/auth/token` (cluster/headend path): authenticate with `CLUSTER_API_KEY`, issue:
- **Access JWT** (1h): `sub="cluster:<id>"`, `iss`, `aud="headend"`, `tenant=<cluster.tenant>` (FIX C3: read `.tenant`, not `.tenant_id`), `scope="firewall:read wireguard:read ports:read metrics:write"`, `iat`, `exp`, `jti`.
- **Refresh JWT** (short, default 8h — configurable; ≤24h per standards): `token_type="refresh"`, `sub`, `tenant`, `aud`, `jti`, `exp`.
- FIX C4: `await authenticate_cluster(...)` directly (it is async); remove the `asyncio.to_thread` wrapper on the coroutine. Bind `cluster.id==node_id` (the existing A-fix) — which now actually runs.
- **Scope set derives from `node_type` (least-privilege — corrected after commit security review; a single union bundle was over-permissive):**
  - clusters (`kubernetes_node`/`raw_compute`/`headend`) → `firewall:read wireguard:read ports:read metrics:write certs:issue` (clusters are the cert issuers)
  - clients (`client_docker`/`client_native`) → `wireguard:read` (minimal; NO `certs:issue`/`firewall`/`ports`/`metrics`)

### 3. Rotating refresh + revocation — `hub_api/auth/refresh.py` (new) + Valkey

`POST /api/v1/auth/refresh`:
1. Decode refresh JWT (must be valid RS256, `token_type=="refresh"`, unexpired).
2. **Subject re-check** (FIX D1): `authenticate`-lookup the cluster by `sub`; reject if it no longer exists or is inactive.
3. **Single-use rotation**: Valkey key `auth:refresh:<sub>` holds the *current* valid refresh `jti`. If the presented `jti` != stored → **reject** (superseded/replayed) and revoke the whole subject (defence-in-depth: a replay implies compromise). On success, mint a new refresh JWT, `SET auth:refresh:<sub> = new_jti` (TTL = refresh exp), and return new access + refresh.
4. **Revocation denylist**: `auth:revoked_jti:<jti>` (TTL = token remaining life). Checked on every refresh AND on access-token validation for `aud=headend` tokens. A `revoke_cluster(sub)` admin op deletes `auth:refresh:<sub>` and denylists outstanding jtis.
5. **Fail-closed**: if Valkey is unreachable during a refresh, return `503` with `retry_with_credentials=true`; the client re-auths at `/auth/token` with its `CLUSTER_API_KEY`. Access-token validation (per-request) stays stateless EXCEPT an optional denylist check that fail-*opens* on Valkey outage for availability (access tokens are already short-lived; refresh is the control point). This asymmetry is deliberate: revocation is enforced hard at refresh (every ≤1h), soft at per-request validation.

### 4. Route protection + dual-accept — `hub_api/auth/middleware.py`

New decorator `@require_machine_jwt(*scopes)`:
- Extract Bearer token. Try machine-JWT decode first: valid + `aud=="headend"` + required scopes present + not denylisted → set `g.machine_tenant`, `g.machine_sub`; proceed.
- If not a valid machine-JWT AND flag `tobogganing.core.machine_jwt_required` is **OFF** → legacy fallback, but **each legacy token is bound to a fixed scope allowlist and `required_scopes` is enforced against it** (corrected after commit security review — a bare "accept either static token for any route" was a privilege-escalation window): `HEADEND_API_TOKEN → {firewall:read, wireguard:read, ports:read, metrics:write}`, `ENROLLMENT_BOOTSTRAP_TOKEN → {certs:issue}`. `required_scopes ⊄ allowlist` → 403. Set `g.machine_tenant="default"` (legacy). Net effect: a headend token can NOT issue certs; a bootstrap token can NOT read firewall.
- If flag **ON** → legacy path disabled; static token → 401.
- Applied to: `firewall/rules`, `wireguard/peers`, `headend/ports` (`headend_routes.py`), `submit_headend_metrics` (FIX C6 — replaces bootstrap), cert issuance (`core/api/certs.py`).
- **Every query in these handlers is scoped to `g.machine_tenant`** (FIX C2), not `"default"`.

### 5. `authenticate_cluster` hardening — `sdwan/orchestrator/cluster_manager.py`

- Add `rotate_api_key(cluster_id)` (parity with `ClientRegistry.rotate_api_key`).
- Keep the global-by-hash lookup (the key IS the identity), but the issued JWT now carries the cluster's real `.tenant`, so downstream scoping is correct even though the *lookup* is global. Document why the lookup stays global (bootstrap: the caller has no tenant context until authenticated).

### 6. Go-headend coordination contract (documented; separate session)

The Go headend must: (a) exchange its `CLUSTER_API_KEY` at `/auth/token` for a machine-JWT; (b) send `Authorization: Bearer <access-jwt>` on all headend routes (replacing the `authToken`/`CLUSTER_API_KEY` split — spec §8 #11); (c) store the rotated refresh token and refresh before access expiry; (d) on a `503 retry_with_credentials`, re-auth with `CLUSTER_API_KEY`. The flag stays OFF until the Go headend ships this.

## Flags & entitlements

- `tobogganing.core.machine_jwt_required` — core, **free** (security infra, not licensed). Default **OFF** (dual-accept). Flip ON post-Go-cutover.
- No new license entitlement (auth is core).

## Error handling

- Invalid/expired machine-JWT → 401. Missing scope → 403. Tenant mismatch (token tenant ≠ resource tenant, once resources carry tenant) → 403.
- Refresh with superseded jti → 401 + subject revoked. Refresh for inactive/absent cluster → 401. Valkey down at refresh → 503 `retry_with_credentials`.
- All auth failures logged with masked token + `sub` + resolved tenant (never the raw token).

## Testing

- **Issuance**: `/auth/token` cluster path issues access+refresh with `tenant=<real>` (regression for C3), `jti` present; the `await` path binds `id==node_id` (regression for C4 — mock returns a real object, assert 200; previously the coroutine bug → 401).
- **Dual-accept**: flag OFF → static token accepted AND machine-JWT accepted; flag ON → static token → 401, machine-JWT → 200.
- **Tenant scoping**: a machine-JWT for tenant A cannot read tenant B's firewall rules/peers (cross-tenant → empty/403) (regression for C2).
- **Refresh rotation**: refresh returns a new refresh jti; replaying the old jti → 401 + subject revoked (regression for D1); refresh for a deleted/inactive cluster → 401.
- **Revocation**: `revoke_cluster` → subsequent refresh 401; denylisted access jti rejected at refresh.
- **Fail-closed**: Valkey unreachable at refresh → 503 `retry_with_credentials`.
- **Finding 2**: `submit_headend_metrics` with a bootstrap token (flag ON) → 401; with a valid `metrics:write` machine-JWT → 200 (regression: `# regression: security-review finding-2`).
- **Cache client**: key-prefix guard rejects a cross-namespace write; in-memory fallback engages for best-effort caches but NOT for revocation reads.

## Sequencing (for the plan)

1. Shared Valkey client (`hub_api/cache/`) — foundation, no behavior change.
2. Machine-JWT issuance + bug fixes C3/C4 (`/auth/token`, `core/api/jwt.py`).
3. `require_machine_jwt` decorator + dual-accept flag + tenant scoping (C1/C2) on the 3 headend routes + Finding 2 (C6).
4. Rotating refresh + revocation store (D1) on Valkey.
5. `authenticate_cluster` rotation + hardening (C5).

Each is a separate PR into the release branch; 2–5 depend on 1; 3 depends on 2; 4 depends on 1+2. The Go contract (§6) is documented, not implemented here.

## Notes

- No external API URL changes. `/auth/token`, `/auth/refresh`, `/auth/validate` keep their paths; response bodies gain `jti`/rotated refresh.
- Backward compatible while the flag is OFF — the data plane keeps working on the static token until Go cuts over.
- Follow-up (not this slice): unify/rotate the DB-backed user refresh path; migrate `protection/`+live-test onto the shared cache client.
