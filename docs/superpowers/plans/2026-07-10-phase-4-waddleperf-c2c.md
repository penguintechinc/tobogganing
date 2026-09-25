# Phase 4 — WaddlePerf cluster2cluster (c2c) Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Greenfield `waddleperf_c2c` module — node/region-to-region performance testing. A tenant-scoped registry of test **nodes**, matrix **runs** that execute pairwise tests via an **async Celery + Valkey job queue**, and a region-to-region results **matrix** + trends. Professional-tier.

**Architecture:** Quart control plane at `/api/v1/waddleperf_c2c`. A `POST /runs` creates a matrix run and enqueues one Celery task per ordered node pair (source→dest) onto a **Valkey** broker. Celery **workers** (separate process/deployment) each execute one pair by calling the *source* node's testserver engine (`EngineClient(base_url=source.engine_url)`) against the *dest* node's target, then record a `c2c_pair_result` and advance the run's progress. Clients poll run status + the results matrix. The whole module is license-gated Professional on top of a PostHog flag.

**Tech Stack:** Quart, penguin-dal (runtime), SQLAlchemy+Alembic (schema), **Celery 5 + Valkey broker**, httpx (engine client, reused from 3a), PostHog flags + entitlements, pytest.

## Global Constraints
- Python 3.13; type hints (`mypy --strict`); `@dataclass(slots=True)`; no bare except; `python3`; every file <1000 lines.
- Runtime DB via tenant-scoped penguin-dal; schema Alembic-only. Single `users` table; `tenant` on every table; UUID refs. JSON columns → `Column("metadata", ...)` (reserved-attr rule).
- **Professional tier**: every feature flag `tobogganing.waddleperf_c2c.{feature}` (default OFF) AND a Professional license entitlement (`waddleperf_c2c.*` → tier `professional`). Gate = `@require_feature(...)` (flag + tier). No enablement without both.
- Tenant-first auth (`@require_tenant` + `@require_scope`); node engine credentials hashed at rest (`hmac.compare_digest`), never returned after creation except once. Never trust tenant/node from body.
- **Celery workers**: fresh DAL per task (`create_dal()` inside the task, not module-global); Valkey broker via `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` env; bounded concurrency; idempotent per-pair tasks (safe to retry). Never block the Quart event loop — enqueue only, never run pairs inline in a request.
- Valkey (NOT Redis/Bitnami) for the broker. Per-service Valkey ACL user with key-prefix. Module mounts at `/api/v1/waddleperf_c2c`; register in `core.modules.__all__`.

## Target File Structure
```
core/modules/waddleperf_c2c/
  __init__.py                          # module() -> ModuleContract
  api/{endpoints,runs,matrix}.py       # blueprints
  services/{endpoint_manager,run_manager,matrix_service}.py
  worker/{celery_app.py,tasks.py}      # celery app + run_pair task
core/db/models.py                      # + C2CEndpoint, C2CMatrixRun, C2CPairResult
core/migrations/versions/0014_c2c_endpoints.py, 0015_c2c_runs_results.py
core/tests/test_c2c_*.py
k8s/                                   # (follow-up) worker Deployment + Valkey subchart
```

---

## Task Group A — Schema

### Task A1: Models + migrations
**Files:** `core/db/models.py`, `core/migrations/versions/0014_c2c_endpoints.py`, `0015_c2c_runs_results.py`, `core/tests/test_migrations_head.py`, `core/tests/test_c2c_models.py`
- `C2CEndpoint` (c2c_endpoints): id, tenant, region (String, indexed), name, engine_url, target (the host other nodes test against), api_key_hash (nullable, indexed), enabled (bool), created_at, updated_at. Unique(tenant, region, name).
- `C2CMatrixRun` (c2c_matrix_runs): id, tenant, status (pending/running/completed/failed), test_types (JSON list), total_pairs (int), completed_pairs (int), failed_pairs (int), created_by (user_id), created_at, started_at (nullable), completed_at (nullable).
- `C2CPairResult` (c2c_pair_results): id, tenant, run_id (indexed), source_endpoint_id, dest_endpoint_id, source_region, dest_region, test_type, status, latency_ms (nullable), throughput (nullable), loss_pct (nullable), test_output (Text), measured_at. Index(tenant, run_id), Index(tenant, source_region, dest_region).
- Migrations 0014 (endpoints), 0015 (runs+results), chained from 0013. Update `test_migrations_head`.
- TDD; full suite green; `alembic upgrade head` == Base.metadata.

## Task Group B — Managers

### Task B1: EndpointManager + RunManager + MatrixService
**Files:** `core/modules/waddleperf_c2c/services/*.py`, `core/tests/test_c2c_managers.py`
- `EndpointManager(db, tenant)`: CRUD + `authenticate_node(api_key)` (global hash lookup pattern, if nodes call back) — tenant-scoped list/get/create(returns raw key once)/update/delete.
- `RunManager(db, tenant)`: `create_run(test_types, endpoint_ids|None)` → creates a `c2c_matrix_run` (status pending, total_pairs = N*(N-1) for the selected enabled endpoints), returns the run + the ordered source→dest pair list to enqueue; `get_run`, `list_runs`, `mark_running/complete/fail`, `record_pair_result(run_id, pair_data)` (writes `c2c_pair_result`, increments completed/failed_pairs, flips run to completed when done). All tenant-scoped.
- `MatrixService(db, tenant)`: `latest_matrix(test_type)` → NxN region grid of the most recent pair results; `run_matrix(run_id)`; `trends(source_region, dest_region, test_type, window)`.
- Mocked-DAL tests for each.

## Task Group C — Celery worker + tasks

### Task C1: Celery app + run_pair task
**Files:** `core/modules/waddleperf_c2c/worker/celery_app.py`, `core/modules/waddleperf_c2c/worker/tasks.py`, `core/tests/test_c2c_tasks.py`
- `celery_app.py`: Celery instance, broker/result backend from `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` (Valkey), sane defaults (`task_acks_late=True`, bounded prefetch). Import-safe when Celery/broker absent (guard so the Quart app and tests import without a live broker).
- `tasks.py`: `@celery_app.task run_pair(run_id, tenant, source_id, dest_id, test_type)` — fresh DAL, load source+dest endpoints (tenant-scoped), `asyncio.run(EngineClient(base_url=source.engine_url, api_key=<source key>).run_test(test_type, target=dest.target, device_headers={...}))`, then `RunManager(db, tenant).record_pair_result(...)`. Fail-safe: on engine error record a failed pair result (status=failed) and advance progress; idempotent (skip if this pair already recorded for the run).
- `run_manager.enqueue_run(run)` dispatches `run_pair.delay(...)` for each pair (or `.apply_async`); provide a synchronous fallback path ONLY for tests (a `dispatch=` injectable) — never run inline in a request handler.
- Tests: `run_pair` with a mocked `EngineClient` + mocked DAL records a result and advances the run; engine error → failed pair recorded; idempotent re-run skips. Do NOT require a live broker — call the task function directly and mock `.delay`.

## Task Group D — Blueprints

### Task D1: endpoints + runs + matrix blueprints
**Files:** `core/modules/waddleperf_c2c/api/{endpoints,runs,matrix}.py`, tests
- `endpoints.py` — `Blueprint("c2c_endpoints", url_prefix="/endpoints")`: CRUD (JWT + `c2c:read`/`c2c:write` + `@require_feature("waddleperf_c2c","endpoints")`).
- `runs.py` — `Blueprint("c2c_runs", url_prefix="/runs")`: `POST ""` create+enqueue a matrix run (body: test_types, optional endpoint_ids) → 202 with run id; `GET ""` list; `GET "/<run_id>"` status/progress. Enqueue via `RunManager.enqueue_run` (Celery) — never execute inline. Feature `runs`.
- `matrix.py` — `Blueprint("c2c_matrix", url_prefix="/matrix")`: `GET "/latest?test_type="` NxN region matrix; `GET "/runs/<run_id>"` a run's matrix; `GET "/trends?source=&dest=&test_type="`. Feature `matrix`.
- All tenant from claims; `meta` envelope. Tests: endpoint CRUD + tenant isolation; run create enqueues the right pair count (mock dispatch) and returns 202; matrix aggregation shape; flag/scope/Professional gates (402 without Professional entitlement).

## Task Group E — Contract + verify + PR

### Task E1: ModuleContract + register + Professional gating
**Files:** `core/modules/waddleperf_c2c/__init__.py`, `api/__init__.py`, `core/modules/__init__.py`, `core/tests/test_c2c_contract.py`
- `module()`: blueprints; flags `tobogganing.waddleperf_c2c.{endpoints,runs,matrix}`; entitlements ALL `professional`; nav; migrations `["0014","0015"]`; health (broker/endpoint reachability, lightweight/static).
- Register `waddleperf_c2c` in `core.modules.__all__`. URL-map contract test; assert Professional entitlement (402 when unlicensed) via the gate.

### Task E2: Worker deployment + Valkey (k8s) — follow-up-friendly
**Files:** `k8s/helm/...`, `k8s/kustomize/...` (use k8s-manifest-builder)
- Celery worker Deployment (non-root, resource limits, health) + Valkey subchart (`valkey/valkey:8-bookworm@sha256:<digest>`), env `CELERY_BROKER_URL`. May be a stub/follow-up commit — code is the Phase-4 deliverable; deployment can land alongside.

### Task E3: Verify + PR
- Full `core/` suite green; every file <1000; `alembic upgrade head` == Base.metadata (0001→0015); `mypy --strict` on the module; Celery app imports without a live broker.
- PR `feature/phase-4-waddleperf-c2c` → base `feature/phase-3b-waddleperf-client` (stacked). Note Professional gating, the queue/worker model, and that broker/worker k8s may be a follow-up.

## Self-Review Notes
- Never run pairwise engine calls inline in a Quart request — enqueue only (event-loop + timeout safety). Workers use fresh DAL per task.
- Reserved-`metadata` rule on JSON columns; reuse the global-hash node-auth pattern; no tenant-from-body.
- Orchestrator runs the FULL suite at each checkpoint; fix/build agents edit-and-test only on disjoint files; orchestrator owns shared `__init__`/contract wiring + registration.
- Celery import must be guarded so the Quart app + tests import with no broker present.
