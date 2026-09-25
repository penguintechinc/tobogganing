# Phase 1: Quart Core + Module Framework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stand up a new Quart `core/` control plane with a formal module registry/contract, tenant+scope middleware, PostHog flags, license entitlement + usage metering, and unified auth (RS256 JWT via a pluggable key provider, bcrypt, TOTP MFA) — proven end-to-end by one trivial registered demo module. No product features yet.

**Architecture:** `core/` is a fresh Quart app factory seeded from WaddlePerf `services/unified-api` (`create_app` shape, penguin-dal `build_db_uri`+reflection wiring, `AuthService`, flat `@dataclass` config, fully-mocked test harness), with the rough edges fixed: one JWT path, tenant-first + scope authz middleware, module autodiscovery via an explicit registry, SQLAlchemy+Alembic as the schema authority (not reflection-only), posthog added, phantom gRPC/unused deps dropped. Data-plane Go engines are untouched this phase.

**Tech Stack:** Python 3.12 (Quart 0.20, hypercorn, penguin-dal[quart], SQLAlchemy 2 + Alembic, PyJWT RS256, bcrypt, pyotp, qrcode, posthog, penguin-aaa/penguin-licensing), pytest (asyncio, 90% gate).

## Global Constraints

- New feature branch `feature/phase-1-quart-core` off `release/v1.2.X`. Commit per task. PR into `release/v1.2.X` at the end.
- Quart only (no Flask/Flask-Security-Too — replace the `users.py` flask_security pattern). hypercorn server. `async def` routes.
- penguin-dal for ALL runtime queries; SQLAlchemy + Alembic are the sole schema authority (no reflection-only). `DB_TYPE` selects postgresql/mysql/sqlite.
- `@dataclass(slots=True)` for config and data structures. Type hints on every function; `mypy --strict` target. No bare `except`.
- Auth: tenant claim mandatory (reject if missing, 403); tenant middleware runs BEFORE scope checks; authz decisions on `scope` only, never role names. JWT signed RS256 via the key provider (persistent key, `kid` header), not HS256.
- Every module feature declares a PostHog flag `tobogganing.{module}.{feature}` (default OFF) + optional license tier. Gates degrade to last-known-cached values; never crash on flag/license outage.
- Metering never blocks a request (cache + retry).
- API paths `/api/v{major}/{module}/…`. Responses include `meta.version` + `meta.timestamp`.
- Docker: `python:3.13-slim-bookworm@sha256:<digest>` (or 3.12 while migrating), non-root, hypercorn, native healthcheck. pip via `uv pip compile --generate-hashes`.
- Do NOT modify `services/hub-api` in this phase (it keeps running until Phase 2 ports SASE).

## File Structure

```
core/
  __init__.py
  app.py                     # create_app factory + main() hypercorn entrypoint
  config.py                  # @dataclass(slots=True) Config, env-driven, build_db_uri
  db/
    __init__.py              # init_dal/get_db re-export (penguin-dal quart_ext)
    base.py                  # SQLAlchemy declarative Base + naming convention
    session.py               # engine/metadata for Alembic (schema authority)
  crypto/
    __init__.py
    keys.py                  # KeyProvider protocol, InAppKeyProvider, build_key_provider; AWS/GCP stubs raise NotImplementedError (Phase 4b)
  auth/
    __init__.py
    service.py               # AuthService: bcrypt, RS256 JWT (via KeyProvider), TOTP MFA — ported from unified-api auth_service.py
    jwt.py                   # encode/decode RS256 with kid; single validate path
    middleware.py            # tenant-first + scope decorators (require_scope, require_tenant)
  flags/
    __init__.py              # feature_enabled(...) — thin re-export/extension of shared/licensing/entitlements
  entitlements/
    __init__.py
    gate.py                  # tier gating (community/professional/enterprise) on top of flags
    metering.py              # UsageReporter: seats (identities) + nodes + per-feature; keepalive; never blocks
  registry/
    __init__.py
    contract.py              # ModuleContract dataclass/Protocol + ModuleContext
    registry.py              # ModuleRegistry: register(module), apply_to(app), collect nav/flags/migrations/health
  modules/
    __init__.py
    ping/                    # trivial demo module proving the contract
      __init__.py            # module() -> ModuleContract
      routes.py              # GET /api/v1/ping (flag-gated), GET /api/v1/ping/pro (Professional-gated)
  alembic/                   # migrations dir
    env.py
    versions/0001_core_baseline.py   # users identity table + core tables
  alembic.ini
  requirements.in / requirements.txt
  Dockerfile
  tests/
    conftest.py              # mocked penguin-dal harness (adapted from unified-api conftest)
    test_config.py test_keys.py test_jwt.py test_middleware.py
    test_registry.py test_flags.py test_metering.py test_auth_service.py
    test_ping_module.py test_app.py
```

---

### Task 1: Core config + app factory skeleton

**Files:** Create `core/__init__.py`, `core/config.py`, `core/app.py`, `core/db/__init__.py`, `core/tests/conftest.py`, `core/tests/test_config.py`, `core/tests/test_app.py`.

**Interfaces:**
- Produces: `Config` (`@dataclass(slots=True)`) with DB_*, JWT_*, CORS_ORIGINS, POSTHOG_KEY/HOST, LICENSE_KEY, PRODUCT_NAME, LOG_LEVEL fields + `build_db_uri(cfg) -> str` (mysql+aiomysql / postgresql+asyncpg / sqlite+aiosqlite, from `DB_TYPE`); `create_app(config: Config | None = None) -> Quart`.

- [ ] **Step 1: Failing test for config + health**

```python
# core/tests/test_config.py
from core.config import Config, build_db_uri
def test_build_db_uri_sqlite(monkeypatch):
    cfg = Config(db_type="sqlite", db_name=":memory:")
    assert build_db_uri(cfg).startswith("sqlite+aiosqlite:")
def test_build_db_uri_postgres():
    cfg = Config(db_type="postgresql", db_host="h", db_name="d", db_user="u", db_pass="p")
    assert build_db_uri(cfg).startswith("postgresql+asyncpg://u:p@h")
```
```python
# core/tests/test_app.py
import pytest
from core.app import create_app
@pytest.mark.asyncio
async def test_health_ok():
    app = create_app()
    client = app.test_client()
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)
```

- [ ] **Step 2: Run to verify fail** — `cd core && python3 -m pytest tests/test_config.py tests/test_app.py -q` → FAIL (import errors).

- [ ] **Step 3: Implement `core/config.py`** (adapt unified-api `config.py` to `@dataclass(slots=True)`, add PostHog/License fields, single `build_db_uri` — drop the divergent `get_db_uri`). Concrete code:

```python
# core/config.py
from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(slots=True)
class Config:
    db_type: str = os.getenv("DB_TYPE", "sqlite")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "tobogganing")
    db_pass: str = os.getenv("DB_PASS", "")
    db_name: str = os.getenv("DB_NAME", "tobogganing")
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    jwt_expiration_hours: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    posthog_key: str = os.getenv("POSTHOG_KEY", "")
    posthog_host: str = os.getenv("POSTHOG_HOST", "https://license.penguintech.io")
    license_key: str = os.getenv("LICENSE_KEY", "")
    product_name: str = os.getenv("PRODUCT_NAME", "tobogganing")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

def build_db_uri(cfg: Config) -> str:
    if cfg.db_type == "mysql":
        return f"mysql+aiomysql://{cfg.db_user}:{cfg.db_pass}@{cfg.db_host}:{cfg.db_port}/{cfg.db_name}"
    if cfg.db_type in ("postgresql", "postgres"):
        return f"postgresql+asyncpg://{cfg.db_user}:{cfg.db_pass}@{cfg.db_host}:{cfg.db_port}/{cfg.db_name}"
    return f"sqlite+aiosqlite:///{cfg.db_name}"
```

- [ ] **Step 4: Implement `core/app.py`** — `create_app` following the unified-api factory shape (config → CORS → init_dal → before_serving services → register blueprints via the registry (Task 6) → `/health` + JSON error handlers), plus `main()` running hypercorn on :5000. For this task, register no modules yet; `/health` returns 200 with `{"status":"healthy"}` (DB check wired in Task 2). Provide `core/db/__init__.py` re-exporting `init_dal, get_db` from `penguin_dal.quart_ext` (guard import so tests can run without a live DB — see conftest mocks).

- [ ] **Step 5: Implement `core/tests/conftest.py`** — adapt unified-api `tests/conftest.py` mocked penguin-dal harness (`make_mock_row`, `mock_db`, `app` fixture patching `core.db.init_dal/get_db`).

- [ ] **Step 6: Run tests** → `cd core && python3 -m pytest tests/test_config.py tests/test_app.py -q` → PASS.

- [ ] **Step 7: Commit** — `git add core/ && git commit -m "feat(core): Quart app factory + config skeleton"`.

---

### Task 2: penguin-dal wiring + Alembic baseline (schema authority)

**Files:** `core/db/base.py`, `core/db/session.py`, `core/alembic.ini`, `core/alembic/env.py`, `core/alembic/versions/0001_core_baseline.py`, `core/tests/test_database.py`.

**Interfaces:** Produces the SQLAlchemy `Base`, a `users` identity table (UUID PK, email/username/password_hash/is_active/mfa_enabled/mfa_secret/tenant), `refresh_tokens`, `password_reset_tokens` — the single identity table per spec, referenced by UUID elsewhere.

- [ ] **Step 1: Failing test** — assert `0001_core_baseline` upgrade creates the `users` table with a `tenant` column on a sqlite test DB (use Alembic's `command.upgrade` against `sqlite:///:memory:` file). 
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `Base` (with naming convention), the SQLAlchemy table models for `users`/`refresh_tokens`/`password_reset_tokens` (columns matching what unified-api `AuthService` queries: `users.email/username/password_hash/is_active/mfa_enabled/mfa_secret`, plus mandatory `tenant` and UUID `id`), `alembic/env.py` targeting `Base.metadata` and `build_db_uri`, and the `0001_core_baseline` revision (`create_all`-equivalent via `op.create_table`). No `alembic upgrade` on app startup (create_all is fine, migrations are manual/Job).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Wire `/health` DB check** in `core/app.py` (SELECT 1 via the DAL; 503 on failure) and update `test_app.py` to accept the mocked-DB 200.
- [ ] **Step 6: Commit** — `feat(core): SQLAlchemy Base + Alembic baseline with users identity table`.

---

### Task 3: Pluggable key provider (RS256) in core/crypto

**Files:** `core/crypto/__init__.py`, `core/crypto/keys.py`, `core/tests/test_keys.py`.

**Interfaces:** Produces `KeyProvider` protocol (`private_pem`, `public_pem`, `kid`), `InAppKeyProvider`, `build_key_provider()` (env `JWT_PRIVATE_KEY_PEM`/`JWT_PRIVATE_KEY_PATH`), and `AwsKmsKeyProvider`/`GcpKmsKeyProvider` **stubs** that raise `NotImplementedError("wired in Phase 4b")`.

- [ ] **Step 1: Failing test** — same shape as Phase 0's `test_keys.py` (generate valid PEM pair; env-loaded PEM stable across two providers), plus `kid` is a stable non-empty string derived from the public key; and `AwsKmsKeyProvider().private_pem` raises `NotImplementedError`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — port Phase 0 `services/hub-api/auth/keys.py` into `core/crypto/keys.py`, add a `kid` property (`sha256(public_pem)[:16].hex()`), and add the two KMS stub classes.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(core): RS256 key provider (in-app) with KMS stubs for Phase 4b`.

---

### Task 4: Unified auth service (bcrypt, RS256 JWT, TOTP MFA)

**Files:** `core/auth/__init__.py`, `core/auth/jwt.py`, `core/auth/service.py`, `core/tests/test_jwt.py`, `core/tests/test_auth_service.py`.

**Interfaces:** Produces `encode_access_token(claims, key_provider, ttl) -> str` / `decode_token(token, key_provider) -> dict|None` (RS256, `kid` header, verifies `iss/aud/exp`, requires `tenant` claim); `AuthService(db, config, key_provider)` with `authenticate`, `refresh_access_token`, `revoke_tokens`, `setup_mfa`, `verify_and_enable_mfa`, `disable_mfa`, `get_user_by_id` (ported from unified-api `services/auth_service.py`, switched HS256→RS256-via-jwt.py, and every issued token carries `sub`, `iss`, `aud`, `iat`, `exp`, `scope`, `tenant`, `teams`, `roles`).

- [ ] **Step 1: Failing tests** — `test_jwt.py`: round-trip encode/decode returns claims incl. `tenant`; a token missing `tenant` → `decode_token` returns None; tampered token → None. `test_auth_service.py`: `authenticate` with the mocked DB returns access+refresh on valid creds; wrong password → failure; `mfa_enabled` user without `mfa_token` → `mfa_required`; TOTP verified path issues tokens (mock `pyotp`).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `core/auth/jwt.py` (RS256 with the key provider, kid header, standard claims, tenant required) and port `core/auth/service.py` from `waddleperf/services/unified-api/services/auth_service.py` with these changes: use `core.auth.jwt` for encode/decode (delete the inline HS256 path), include full standard claim set (add `scope`/`tenant`/`teams`/`roles` from the user row — default `scope` from role bundle), keep bcrypt + pyotp TOTP as-is, keep refresh-token persistence via penguin-dal. Store `mfa_secret` column as-is for now (encrypt-at-rest is a Phase 4b/follow-up note).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(core): unified AuthService (bcrypt, RS256 JWT, TOTP MFA)`.

---

### Task 5: Tenant-first + scope authz middleware

**Files:** `core/auth/middleware.py`, `core/tests/test_middleware.py`.

**Interfaces:** Produces `require_tenant(func)` (rejects 403 if no valid `tenant` claim; runs first), `require_scope(*scopes)(func)` (403 unless token `scope` set ⊇ required; never branches on role names), and a helper `current_claims()` reading the validated token from request context. Scope bundles (`admin`/`maintainer`/`viewer`) expand at token issuance (Task 4), middleware checks scopes only.

- [ ] **Step 1: Failing tests** — a handler wrapped in `require_tenant` returns 403 when the token lacks `tenant`; `require_scope("clusters:read")` returns 403 for a `viewer`-without-that-scope token and 200 when the scope is present; tenant middleware must reject before scope logic runs (assert order via a handler that would 500 if scope ran first).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the decorators using `core.auth.jwt.decode_token` + the key provider from `current_app`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(core): tenant-first + scope-based authz middleware`.

---

### Task 6: Module registry + contract

**Files:** `core/registry/__init__.py`, `core/registry/contract.py`, `core/registry/registry.py`, `core/tests/test_registry.py`. Modify `core/app.py` to build a registry and apply it.

**Interfaces:**
- Produces `ModuleContract` (`@dataclass(slots=True)`: `name: str`, `blueprints: list[Blueprint]`, `nav: list[NavEntry]`, `flags: list[str]`, `entitlements: list[Entitlement]`, `migrations: list[str]`, `health: Callable | None`), `ModuleContext` (gives modules `config`, `db` accessor, `key_provider`), `NavEntry`, `Entitlement(feature, tier)`.
- `ModuleRegistry.register(contract)`, `.apply_to(app, ctx)` (registers blueprints under `/api/v{major}/{name}`, collects nav/flags/entitlements, wires health), `.declared_flags()`, `.nav_manifest()`.

- [ ] **Step 1: Failing test** — register a fake contract with one blueprint + one declared flag; `apply_to(app)` mounts its route and `registry.declared_flags()` contains `tobogganing.fake.thing`; nav manifest lists the entry.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `contract.py` (dataclasses/Protocol) and `registry.py`; update `create_app` to instantiate `ModuleRegistry`, import module `module()` factories from an explicit list (autodiscovery = iterate `core.modules.__all__`), and `apply_to(app, ctx)`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(core): module registry + contract`.

---

### Task 7: core/flags + core/entitlements gate

**Files:** `core/flags/__init__.py`, `core/entitlements/__init__.py`, `core/entitlements/gate.py`, `core/tests/test_flags.py`. Reuse `shared/licensing/entitlements.py` (Phase 0).

**Interfaces:** Produces `core.flags.feature_enabled(module, feature, distinct_id="system", licensed=False)` (re-export/extend the Phase 0 `shared/licensing/entitlements.feature_enabled`), and `core.entitlements.gate.require_tier(tier)` / `tier_of(feature) -> Tier` mapping features to `community|professional|enterprise` from the module `Entitlement` declarations. `require_feature(module, feature)` decorator → 402 when the flag is off or the tier isn't licensed, with cached graceful degradation.

- [ ] **Step 1: Failing test** — `feature_enabled` off → False; a `require_feature`-wrapped handler returns 402 when flag off, 200 when on; a Professional feature returns 402 without entitlement (monkeypatch `_licensed`), 200 with it; on simulated PostHog error, falls back to cached value.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** thin wrappers over `shared/licensing/entitlements.py`; `gate.py` reads the registry's declared `Entitlement`s to know each feature's tier.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(core): flags + tier entitlement gate over shared licensing`.

---

### Task 8: Usage metering (seats + nodes + per-feature)

**Files:** `core/entitlements/metering.py`, `core/tests/test_metering.py`.

**Interfaces:** Produces `UsageReporter(db, license_client)` with `snapshot() -> Usage` (`seats`: count of distinct active identities in `users`; `nodes`: count of registered clusters/headends/testservers — for Phase 1 read from a `nodes` count hook or return 0 with a TODO until Phase 3 tables exist; `features`: set of enabled Enterprise features), and `report()` that calls the license client keepalive with the usage payload. `report()` must be non-blocking/best-effort: catch all errors, log, cache last snapshot; never raise into a request path. A `@app.before_serving` task schedules hourly `report()` (supercronic in prod; in-process timer acceptable here).

- [ ] **Step 1: Failing test** — `snapshot()` counts seats from a mocked `users` rowset; `report()` swallows a license-client exception and returns False without raising; per-feature set reflects declared Enterprise entitlements that are enabled.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `Usage` (`@dataclass(slots=True)`), `UsageReporter`; seat = distinct identity (human or machine/AI) per the spec. Node count via an injected callable (defaults to 0 in Phase 1) so Phase 3 can supply the real tally.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(core): usage metering reporter (seats/nodes/features), non-blocking`.

---

### Task 9: Trivial demo module (proves the contract)

**Files:** `core/modules/__init__.py`, `core/modules/ping/__init__.py`, `core/modules/ping/routes.py`, `core/tests/test_ping_module.py`.

**Interfaces:** `core.modules.ping.module() -> ModuleContract` with a blueprint exposing `GET /api/v1/ping` (gated by flag `tobogganing.ping.enabled`, returns `{"pong": true}` with `meta`) and `GET /api/v1/ping/pro` (Professional-gated via `require_feature`), declaring both flags and one Professional `Entitlement`, plus a `nav` entry and a `health` hook. `core.modules.__all__ = ["ping"]`.

- [ ] **Step 1: Failing test** — with the flag ON (monkeypatched), `GET /api/v1/ping` → 200 `{"pong": true}`; with it OFF → 402/404 per gate; `/api/v1/ping/pro` → 402 without Professional entitlement, 200 with it; the registry's `declared_flags()` includes `tobogganing.ping.enabled`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the ping module using `require_feature` + `require_tenant`; register it via the registry in `create_app`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(core): ping demo module proving the registry/flag/entitlement contract`.

---

### Task 10: Packaging — requirements, Dockerfile, entrypoint, full suite

**Files:** `core/requirements.in`, `core/requirements.txt`, `core/Dockerfile`, `core/tests/` (ensure coverage), `core/__main__.py` (or `main()` in app.py).

- [ ] **Step 1:** Author `core/requirements.in` (quart==0.20.0, quart-cors, hypercorn==0.17.3, penguin-dal[quart,postgres,mysql], SQLAlchemy==2.0.*, alembic, PyJWT, bcrypt, pyotp, qrcode, posthog==3.7.0, penguin-aaa, penguin-licensing, python-dotenv, structlog; test: pytest, pytest-asyncio, pytest-cov). Drop Flask-Security-Too, gunicorn, phantom grpc extra.
- [ ] **Step 2:** `uv pip compile requirements.in --generate-hashes -o requirements.txt`; verify hashes.
- [ ] **Step 3:** `core/Dockerfile` — multi-stage `python:3.13-slim-bookworm@sha256:<digest>` (uv install), non-root `appuser`, `CMD ["hypercorn","core.app:app","--bind","0.0.0.0:5000"]`, native healthcheck hitting `/health`.
- [ ] **Step 4:** Run the FULL core suite with coverage: `cd core && python3 -m pytest --cov=core --cov-report=term-missing --cov-fail-under=90 -q` → PASS ≥90%. Add tests where coverage is short.
- [ ] **Step 5:** `mypy --strict core` (fix types) and `flake8 core --select=E999,E722,F401`.
- [ ] **Step 6: Commit** — `chore(core): hashed requirements, bookworm Dockerfile, 90% coverage gate`.

---

## Self-Review

- **Spec coverage (Phase 1 bullets):** Quart core app factory (T1), penguin-dal + Alembic baseline (T2), pluggable RS256 key provider (T3), unified auth bcrypt/JWT/TOTP (T4), tenant+scope middleware (T5), module registry + contract (T6), core/flags (T7), core/entitlements tiers + metering (T7, T8), one trivial registered module proving the contract (T9), packaging/coverage (T10). All Phase 1 spec items mapped.
- **Deferred-with-note (not silent):** node-count metering returns 0 via an injected callable until Phase 3 supplies the tables (T8); `mfa_secret` at-rest encryption noted for Phase 4b (T4). Both are explicit TODOs, not gaps.
- **Placeholder scan:** framework code is concrete; ports name the exact source file + required adaptations (T4 auth, T1 config, conftest) rather than re-quoting hundreds of lines — legitimate for a port. No "handle edge cases"/TBD.
- **Type consistency:** `Config`/`build_db_uri` (T1) consumed by app + auth; `KeyProvider` (T3) consumed by `jwt.py`/`AuthService` (T4) + middleware (T5); `ModuleContract`/`Entitlement` (T6) consumed by flags/gate (T7) + ping (T9) + registry nav; `feature_enabled(module, feature, distinct_id, licensed)` signature identical to Phase 0.

## Execution Handoff

Subagent-driven, penguin-python-dev per task, sequential where files overlap (app.py touched by T1/T2/T6; registry chain), commit per task, PR into `release/v1.2.X` when the full suite is ≥90% green.
