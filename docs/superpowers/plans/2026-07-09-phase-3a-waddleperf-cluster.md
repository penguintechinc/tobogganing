# Phase 3a — WaddlePerf Cluster Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import WaddlePerf's network-performance control plane into tobogganing as the `waddleperf_cluster` module on the Quart `core/` framework, and import its Go test engine into `engines/testserver`.

**Architecture:** Port the Quart `services/unified-api` blueprints (orgs/OUs, devices, enrollment-secrets, tests, stats, live-test WebSocket) into `core/modules/waddleperf_cluster/`, all runtime DB on tenant-scoped penguin-dal, schema authored as fresh Alembic migrations under the single core `users` identity table. The Go `testServer` engine is imported as-is (REST, no gRPC) into `engines/testserver` as the data plane. Data plane stays Go; control plane is Quart-only.

**Tech Stack:** Quart + hypercorn, penguin-dal (runtime), SQLAlchemy 2 + Alembic (schema), PostHog flags + license entitlements, Go 1.25 (engine), pytest.

## Global Constraints
- Python 3.13; type hints on every function (`mypy --strict`); `@dataclass(slots=True)` for DTOs; no bare `except`; always `python3`.
- Every code file < 1000 lines (split god-files; test files too).
- All runtime DB via tenant-scoped penguin-dal (`get_db()`); SQLAlchemy/Alembic for schema ONLY. Never raw sqlite3/SQL DDL at runtime.
- **Single `users` identity table** — WaddlePerf `user`/`role` fold into core `users`; all other tables reference `user_id`/`tenant` by UUID. No PII outside `users`.
- **`organization` maps to the existing `tenant` dimension** — do NOT create an `organizations` table. `organization_unit` becomes a tenant-scoped `org_units` hierarchy table.
- Every feature behind a PostHog flag `tobogganing.waddleperf_cluster.{feature}` (default OFF) via `@require_feature("waddleperf_cluster", feature)`. Tier: perf tests + orgs/devices/enrollment = **community**; `>5 nodes per cluster` and `HA/orchestration` = **Professional** (license-gated entitlement + inline node-count check), mirroring the SASE `large_cluster` gate.
- Tenant-first auth: `@require_tenant` + `@require_scope(...)`; never trust tenant from request body; device/service credentials hashed at rest with `hmac.compare_digest` (reuse the SASE `ClientRegistry`/cluster-credential pattern).
- Clean-copy import: bring ONLY source. Do NOT import `testServer/testserver`, `testServer/waddleperf-testserver` (committed binaries), `.env`, `archive/`, `goClient/`, `managerServer/`, `webClient/` (Flask — dropped), or `docker-compose*.yml`.
- Module mounts at `/api/v1/waddleperf_cluster` via the registry (module prefix + each blueprint's own `url_prefix`), matching the SASE pattern.
- Go engine: Debian bookworm digest-pinned multi-stage Dockerfile, non-root (`NET_RAW` only if ICMP requires it — document as ROOT/cap EXCEPTION), native health binary, `go.sum` committed, deps pinned (no `@latest`).

---

## Source → Target Map

| WaddlePerf source | Target | Notes |
|---|---|---|
| `services/unified-api/app.py` (factory/registration) | (reference only) | Registration folds into `waddleperf_cluster` ModuleContract |
| `services/unified-api/routes/organizations.py` | `core/modules/waddleperf_cluster/api/org_units.py` | org→tenant; keep OU CRUD |
| `services/unified-api/routes/devices.py` | `core/modules/waddleperf_cluster/api/devices.py` | list/get/enroll + enrollment-secrets |
| `services/unified-api/routes/tests.py` (dead bp) | `core/modules/waddleperf_cluster/api/tests.py` | wire it live |
| `services/unified-api/routes/stats.py` (dead bp) | `core/modules/waddleperf_cluster/api/stats.py` | wire it live |
| `services/unified-api/websocket/test_runner.py` | `core/modules/waddleperf_cluster/api/live_test.py` | Quart `websocket`; proxy to engine |
| `services/unified-api/services/*.py` | `core/modules/waddleperf_cluster/services/*.py` | penguin-dal managers, tenant-scoped |
| `services/unified-api/models/*.py` (penguin-dal define_table) | `core/db/models.py` (SQLAlchemy) + Alembic | translate to SQLAlchemy; drop 2nd users table |
| `database/schema.sql`, `database/migrations/*.sql` | `core/migrations/versions/0010_*..` | author fresh Alembic; reconcile drift |
| `testServer/` (Go, REST) | `engines/testserver/` | import as-is minus binaries |
| `managerServer/`, `webClient/`, `archive/`, `goClient/` | — | dropped |

**Auth reconciliation:** WaddlePerf `routes/auth.py` duplicates login/refresh/MFA — the core already provides these (Phase 1 `AuthService` + SASE `jwt` blueprint). Do NOT port WaddlePerf auth; reuse core auth. Device/service `api_key` → hashed device credential (new `device_api_key_hash`).

## Target File Structure
```
engines/testserver/                     # Go REST engine (imported)
  cmd/testserver/main.go, internal/..., go.mod, go.sum, Dockerfile
core/modules/waddleperf_cluster/
  __init__.py                           # module() -> ModuleContract
  api/{org_units,devices,enrollment,tests,stats,live_test}.py   # Quart blueprints
  services/{org_unit_manager,device_manager,enrollment_manager,test_manager,stats_manager}.py
core/db/models.py                       # + OrgUnit, Device, DeviceEnrollmentSecret, PerfTestResult, ClientConfig, ServerKey, DeviceApiKey
core/migrations/versions/0010_*.py ...  # waddleperf schema
core/tests/test_wpc_*.py                # per-resource tests
```

---

## Task Group A — Import the Go testServer engine

### Task A1: Clean import of the engine source
**Files:**
- Create: `engines/testserver/` (copy of `~/code/waddleperf/testServer/` source tree)
- Exclude: `testserver`, `waddleperf-testserver` binaries, any `.env`, build artifacts

- [ ] **Step 1:** Copy `~/code/waddleperf/testServer/{cmd,internal,go.mod,go.sum}` into `engines/testserver/`, omitting the two committed binaries and any `.env`/artifacts. Verify with `git status` that no file ≥5MB is staged.
- [ ] **Step 2:** Update `go.mod` module path to `github.com/penguintechinc/tobogganing/engines/testserver`; run `gofmt`/`go mod tidy` inside a `golang:1.25-bookworm` container; ensure `go.sum` committed.
- [ ] **Step 3:** `docker run --rm -v $PWD/engines/testserver:/src -w /src golang:1.25-bookworm go build ./...` → builds clean. Fix import-path fallout only.
- [ ] **Step 4:** Commit `feat(wpc): import testServer REST engine into engines/testserver` (narrow add of the source tree only).

### Task A2: Engine Dockerfile + hardening
**Files:**
- Create: `engines/testserver/Dockerfile`, `engines/testserver/.dockerignore`
- Modify: `engines/testserver/cmd/testserver/main.go` only if a native health check binary is absent

- [ ] **Step 1:** Multi-stage Dockerfile: builder `golang:1.25-bookworm@sha256:<digest>`, runtime `debian:bookworm-slim@sha256:<digest>`, non-root user, `-ldflags="-X main.Version=..."`, native health probe (no curl). If ICMP raw sockets are required, add a documented `# ROOT EXCEPTION (approved): NET_RAW for ICMP` note and drop all other caps.
- [ ] **Step 2:** `.dockerignore` excludes tests, docs, `.git`.
- [ ] **Step 3:** `docker build engines/testserver` succeeds; image runs `/health` green. Commit `build(wpc): hardened bookworm Dockerfile for testserver engine`.

---

## Task Group B — Schema (Alembic under single `users`)

### Task B1: SQLAlchemy models for WaddlePerf domain
**Files:**
- Modify: `core/db/models.py` (add models, all with `tenant` column, UUID PKs, UUID FKs)
- Test: `core/tests/test_wpc_models.py`

**Interfaces (Produces):** SQLAlchemy models `OrgUnit`, `Device`, `DeviceEnrollmentSecret`, `DeviceApiKey`, `PerfTestResult`, `ClientConfig`, `ServerKey` — each with `tenant: str` and (where applicable) `org_unit_id`, `user_id`, `device_id` UUID refs. `metadata` JSON columns MUST use `Column("metadata", ...)` with a non-reserved attribute name (per the Phase-2 reserved-attr lesson).

- [ ] **Step 1:** Write `test_wpc_models.py` asserting each model creates via `Base.metadata.create_all` on sqlite and that per-tenant uniqueness holds (`UniqueConstraint("tenant", <natural key>)` where WaddlePerf had a global unique — e.g. OU name per tenant, device serial per tenant).
- [ ] **Step 2:** Run → fail (models absent).
- [ ] **Step 3:** Add the models translating `services/unified-api/models/*.py` `define_table` schemas to SQLAlchemy. `organization` is NOT a table (→ tenant). `user`/`role` are NOT re-added (core `users` already exists). Device credentials: store `api_key_hash` only.
- [ ] **Step 4:** Run → pass. Commit `feat(wpc): SQLAlchemy models for org-units/devices/tests (tenant-scoped, single users)`.

### Task B2: Alembic migrations 0010+
**Files:**
- Create: `core/migrations/versions/0010_wpc_org_units.py`, `0011_wpc_devices_enrollment.py`, `0012_wpc_tests_results_config.py`
- Modify: `core/tests/test_migrations_head.py` (expected table set)

- [ ] **Step 1:** Author the migrations (down_revision chain from `0009`) creating: `org_units`; `devices` + `device_api_keys` + `device_enrollment_secrets`; `perf_test_results` + `client_configs` + `server_keys`. Columns/indexes/constraints EXACTLY match the B1 models (use `batch_alter_table` for sqlite where needed). Reconcile the `database/schema.sql` vs `services/unified-api/models` drift toward the models.
- [ ] **Step 2:** `alembic upgrade head` on fresh sqlite creates all tables; `test_migrations_head` asserts migrations == `Base.metadata`. Run full suite → green.
- [ ] **Step 3:** Commit `migration(wpc): 0010-0012 waddleperf cluster schema`.

---

## Task Group C — Managers + org-units/devices blueprints

### Task C1: Service managers (penguin-dal, tenant-scoped)
**Files:**
- Create: `core/modules/waddleperf_cluster/services/{org_unit_manager,device_manager,enrollment_manager,test_manager,stats_manager}.py`
- Test: `core/tests/test_wpc_managers.py`

**Interfaces (Produces):** each manager `__init__(self, db, tenant)`; methods mirror the WaddlePerf service layer (`create_ou/list_ous/...`, `enroll_device/authenticate_device/heartbeat/...`, `record_test_result/list_results`, `summary/by_device/by_type/trends`). Every query tenant-scoped; device auth constant-time on `api_key_hash`.

- [ ] Standard TDD cycle per manager (mocked-DAL tests via `core/tests/conftest.py` helpers). Commit each manager separately. Keep each < 1000 lines.

### Task C2: org_units + devices + enrollment blueprints
**Files:**
- Create: `core/modules/waddleperf_cluster/api/{org_units,devices,enrollment}.py`
- Test: `core/tests/test_wpc_org_units.py`, `test_wpc_devices.py`

**Final URLs (module prefix `/api/v1/waddleperf_cluster` + blueprint `url_prefix`):**
`/org-units` CRUD; `/devices`, `/devices/<id>`, `/devices/<id>/heartbeat`, `/devices/<id>/config`; `/enrollment/secrets`, `/enrollment/secrets/<ou_id>` (GET/POST), `/enrollment/secrets/<secret_id>` (DELETE), `/enrollment/enroll` (POST).

- [ ] TDD each blueprint. `@require_tenant` + `@require_scope` for admin/user routes; device `enroll` gated by the per-OU enrollment secret (constant-time), `heartbeat`/`config` by the device `api_key`. Flag `@require_feature("waddleperf_cluster","devices"|"org_units")`. Tenant from token/enrollment-secret record, never body. Commit per blueprint.

---

## Task Group D — tests + stats + live-test WS

### Task D1: tests + stats blueprints (wire the dead bps)
**Files:**
- Create: `core/modules/waddleperf_cluster/api/{tests,stats}.py`
- Test: `core/tests/test_wpc_tests.py`, `test_wpc_stats.py`

**Final URLs:** `/tests` CRUD + `/tests/<id>/results` (result upload from clients); `/stats/summary`, `/stats/by-device`, `/stats/by-type`, `/stats/trends`, `/stats/recent`.

- [ ] TDD. Result upload endpoint authenticates the device `api_key` (tenant + device from record), validates payload shape, stores via `test_manager`. Stats tenant-scoped. Flags `waddleperf_cluster.tests`/`.stats`. Commit each.

### Task D2: live-test WebSocket + engine proxy
**Files:**
- Create: `core/modules/waddleperf_cluster/api/live_test.py`, `core/modules/waddleperf_cluster/services/engine_client.py`
- Test: `core/tests/test_wpc_live_test.py`

**Interfaces:** `engine_client` posts to the testserver engine over HTTP (`ENGINE_URL`, bearer/API-key + `X-Device-*` headers) mirroring `webClient`'s proxy; `live_test` streams results over Quart `websocket`, session-validated.

- [ ] TDD with a mocked engine HTTP client (no real network). Cover auth-gated stream start, per-tenant isolation, engine-error handling (fail closed). Commit `feat(wpc): live-test websocket + testserver engine client`.

---

## Task Group E — Module contract + verification

### Task E1: Assemble the ModuleContract
**Files:**
- Create/modify: `core/modules/waddleperf_cluster/__init__.py`, `core/modules/waddleperf_cluster/api/__init__.py`
- Modify: `core/modules/__all__` (autodiscovery registration)
- Test: `core/tests/test_wpc_contract.py`

- [ ] Wire `module()` → `ModuleContract(name="waddleperf_cluster", blueprints=[...all...], flags=["tobogganing.waddleperf_cluster.{org_units,devices,enrollment,tests,stats,live_test,large_cluster}"], entitlements=[Entitlement("waddleperf_cluster.large_cluster","professional"), ...community...], nav=[...], migrations=["0010","0011","0012"], health=<engine reachability probe>)`.
- [ ] Register the module in `core/modules/__all__`. Add a `create_app` URL-map test asserting all `waddleperf_cluster` routes resolve at the exact paths and SASE/ping routes are unchanged.
- [ ] Enforce the `>5 nodes` Professional gate inline in device-enroll / test-run (license entitlement + count check), mirroring SASE `large_cluster`.
- [ ] Commit `feat(wpc): wire waddleperf_cluster ModuleContract + register`.

### Task E2: Verification + PR
- [ ] `cd core && python3 -m pytest tests/ -q` all-green; `mypy --strict` clean on the module; every file < 1000 lines; migration chain `0001→0012` and `alembic upgrade head == Base.metadata`.
- [ ] Engine builds in-container; `docker build engines/testserver` green.
- [ ] Open PR `feature/phase-3a-waddleperf-cluster` → `release/v1.2.X` documenting scope, tier gates, dropped sources, and deferred items (client contracts → Phase 3b; per-tenant signed enrollment tokens; React views → Phase 5).

---

## Self-Review Notes
- Reserved-`metadata` attribute: any JSON `metadata` column uses `Column("metadata", ...)` with a safe attribute name (Phase-2 lesson).
- Sub-agents report green off subsets: the orchestrator runs the FULL `core/` suite at each checkpoint; fix agents run **edit-and-test only** in disjoint files and the orchestrator commits sequentially (Phase-2 anti-bundling lesson).
- Verify imported first-party modules exist AND aren't gitignored (`git check-ignore -v`) — the `certs/` incident.
- Do NOT bring committed binaries / tracked `.env` secrets from WaddlePerf; scan the imported tree with `gitleaks` before commit.
