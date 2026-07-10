# Phase 3b — WaddlePerf Client Module (thin) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Add the small `waddleperf_client` module — the genuinely-distinct client-facing surface not already covered by `waddleperf_cluster`: test **schedule/config distribution** to devices and a **client version/update-check** endpoint.

**Architecture:** A thin Quart module at `/api/v1/waddleperf_client`. Devices (authenticated by their per-device API key, via the shared global-lookup helper from 3a) pull their assigned test schedule + config; admins manage schedules per org-unit; a public/tenant version endpoint reports the latest client version for in-app update checks. Stacked on Phase 3a.

**Tech Stack:** Quart, penguin-dal (runtime), SQLAlchemy+Alembic (schema), PostHog flags + entitlements, pytest.

## Global Constraints
- Python 3.13; type hints; `@dataclass(slots=True)`; no bare except; `python3`; every file <1000 lines.
- Runtime DB via tenant-scoped penguin-dal; schema via Alembic only. Single `users` table; tenant column on every table; UUID refs.
- Every feature behind `tobogganing.waddleperf_client.{feature}` flag (default OFF) via `@require_feature`. All features **community** tier (basic client management is free).
- Device auth reuses `core/modules/waddleperf_cluster/services/device_auth.authenticate_device_global` (global api_key_hash lookup → device+tenant). Never trust tenant/device from body/header.
- Module mounts at `/api/v1/waddleperf_client` (registry combines module prefix + each blueprint's `url_prefix`). Register in module autodiscovery like `waddleperf_cluster`.

## File Structure
```
core/modules/waddleperf_client/
  __init__.py                       # module() -> ModuleContract
  api/{schedules,client_config,version}.py
  services/{schedule_manager.py}
core/db/models.py                   # + TestSchedule
core/migrations/versions/0013_wpc_test_schedules.py
core/tests/test_wpcl_*.py
```

---

## Task Group A — Schema + manager

### Task A1: TestSchedule model + migration 0013
**Files:** `core/db/models.py` (+ `TestSchedule`), `core/migrations/versions/0013_wpc_test_schedules.py`, `core/tests/test_migrations_head.py`, `core/tests/test_wpcl_models.py`
- `TestSchedule` (test_schedules): id, tenant, org_unit_id (nullable → tenant-wide), test_type, target, interval_seconds (int), enabled (bool), created_at, updated_at. Index(tenant, org_unit_id). No `metadata` column; if any JSON, use `Column("metadata", ...)`.
- Migration 0013 (down_revision "0012") creates `test_schedules`; update `test_migrations_head` expectations; `alembic upgrade head` == Base.metadata.
- TDD; full suite green.

### Task A2: ScheduleManager
**Files:** `core/modules/waddleperf_client/services/schedule_manager.py`, `core/tests/test_wpcl_schedule_manager.py`
- `ScheduleManager(db, tenant)`: `create_schedule`, `list_schedules` (filter org_unit), `update_schedule`, `delete_schedule`, and `resolve_for_device(device)` → the effective enabled schedules for a device's org_unit (org-unit-specific + tenant-wide). Tenant-scoped. Mocked-DAL tests.

## Task Group B — Blueprints + contract

### Task B1: schedules (admin) + client_config (device-facing) blueprints
**Files:** `core/modules/waddleperf_client/api/schedules.py`, `core/modules/waddleperf_client/api/client_config.py`, tests
- `schedules.py` — `Blueprint("wpcl_schedules", url_prefix="/schedules")`: `POST ""`, `GET ""`, `GET/PUT/DELETE "/<schedule_id>"` — JWT + `schedules:read`/`:write` + `@require_feature("waddleperf_client","schedules")`, tenant from claims.
- `client_config.py` — `Blueprint("wpcl_config", url_prefix="/config")`: `GET ""` — **device-facing**: authenticate the device via `authenticate_device_global(get_db(), api_key)` (tenant+device from record), return the resolved schedule + any `client_configs` for the device's org-unit. Flag `@require_feature("waddleperf_client","config")` checked inline (device path, no user JWT). Fail closed on bad key.
- Tests: admin CRUD + tenant isolation + flag/scope gates; device config-fetch requires a valid device key (bogus→401), returns resolved schedules, tenant from record.

### Task B2: version endpoint + module contract
**Files:** `core/modules/waddleperf_client/api/version.py`, `core/modules/waddleperf_client/api/__init__.py`, `core/modules/waddleperf_client/__init__.py`, module autodiscovery registration, `core/tests/test_wpcl_contract.py`
- `version.py` — `Blueprint("wpcl_version", url_prefix="/version")`: `GET ""` returns `{latest_version, min_version, download_url}` from `Config`/env (`WPCL_LATEST_VERSION`, `WPCL_MIN_VERSION`, `WPCL_DOWNLOAD_URL`) — no DB. `@require_feature("waddleperf_client","version")`; `@require_tenant` (or public if the version check must be pre-auth — default tenant-gated, document). Include `meta`.
- `api/__init__.py`: export `blueprints=[schedules, client_config, version]`.
- `__init__.py` `module()`: name `waddleperf_client`; blueprints; flags `tobogganing.waddleperf_client.{schedules,config,version}`; entitlements all community; nav (Schedules); migrations `["0013"]`; health None. Register in autodiscovery like `waddleperf_cluster`.
- `test_wpcl_contract.py`: create_app URL-map asserts routes at `/api/v1/waddleperf_client/{schedules,config,version}`; flags default OFF; other modules unchanged.

## Task Group C — Verify + PR
- Full `core/` suite green; every file <1000; `alembic upgrade head` == Base.metadata (0001→0013); mypy strict on module.
- PR `feature/phase-3b-waddleperf-client` → base `feature/phase-3a-waddleperf-cluster` (stacked); note it completes Phase 3.

## Self-Review Notes
- Reuse `device_auth.authenticate_device_global` — do NOT reintroduce tenant-from-header/body.
- JSON columns → `Column("metadata", ...)` (reserved-attr rule).
- Orchestrator runs the FULL suite at each checkpoint; fix agents edit-and-test only on disjoint files; orchestrator owns shared `__init__`/contract wiring.
