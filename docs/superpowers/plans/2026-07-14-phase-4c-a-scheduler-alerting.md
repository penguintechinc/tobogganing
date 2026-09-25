# Phase 4c-a — Server-Side Scheduler + Notifications + Alert Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DB-backed server-side scheduling (`core/scheduler`), per-tenant notification delivery (`core/notifications`), and threshold alert rules in `waddleperf_cluster` — the first slice of Phase 4c (AutoPerf + region registry follow in 4c-b and depend on this slice).

**Architecture:** A Celery-beat static entry fires a `scheduler.sweep` task every 30s; the sweep queries due rows in a tenant-scoped `scheduled_jobs` table (penguin-dal) and dispatches each to a handler task registered per `(module, job_type)` — DB-backed dynamic schedules without third-party beat schedulers. Consumers own their REST surface and gating: `waddleperf_cluster` server-initiated recurring tests (Community flag) and `waddleperf_c2c` recurring matrix runs (Professional). `core/notifications` holds channels (SMTP email + HMAC-signed webhook) and a delivery log; alert rules live in `waddleperf_cluster`, evaluated on result ingest and via a sweep job.

**Tech Stack:** Python 3.13, Quart, penguin-dal `AsyncDB` (canonical API), SQLAlchemy+Alembic (schema authority), Celery 5 + Valkey (import-safe stub pattern from `waddleperf_c2c/worker/celery_app.py`), stdlib `smtplib` in `asyncio.to_thread` (no new deps), existing HTTP client pattern from `EngineClient` for webhooks.

## Global Constraints

- ALL async: managers `async def`, one `AsyncDB` per coroutine/Celery task (task builds fresh DAL via `asyncio.run`, copying `waddleperf_c2c/worker/tasks.py`).
- Canonical DAL API only: `await db(db.t.col == v).select()`, `await db((a) & (b)).select()` (ONE query arg per `db(...)` call), `await db.t.async_insert(**cols)`, `await db(cond).update(**ch)/.delete()/.count()`.
- All id/tenant columns `sa.String(36)` (NEVER `sa.UUID` — sqlite reflection breaks). Insert paths pass ALL NOT NULL columns explicitly.
- Flags = `tobogganing.{module}.{feature}` via `feature_enabled(module, feature)`; entitlements = BARE `{module}.{feature}` in module contracts. New flags default OFF.
- Real-DAL tests (`real_dal` fixture: temp sqlite → `alembic upgrade head` → `AsyncDB` → `reflect`) for every manager; mock only at SMTP/webhook/engine transport boundaries.
- Tenant isolation fail-closed: every query tenant-filtered; writes enforce per-row ownership.
- Files ≤1000 lines; type hints everywhere; PEP 257 docstrings; `@dataclass(slots=True)` where a dataclass fits; no secrets logged (webhook secrets, SMTP creds masked).
- Full suite (`cd core && python3 -m pytest tests/ -q`) green at every commit checkpoint; orchestrator commits, workers edit-and-test only.
- Branch: `feature/phase-4c-a-scheduler-alerting` off `feature/phase-4b-kms`.

---

### Task 1: `scheduled_jobs` schema + JobManager

**Files:**
- Create: `core/models/scheduled_job.py` (SQLAlchemy model; follow existing `core/models/*` style)
- Create: `core/migrations/versions/0016_scheduled_jobs.py` (down_revision = "0015")
- Create: `core/scheduler/__init__.py`, `core/scheduler/job_manager.py`
- Test: `core/tests/test_scheduler_job_manager.py` (real_dal)

**Interfaces:**
- Produces table `scheduled_jobs`: `id String(36) PK`, `tenant String(36) NOT NULL (indexed)`, `module String(64) NOT NULL`, `job_type String(64) NOT NULL`, `payload Text NOT NULL` (JSON string), `interval_seconds Integer NOT NULL`, `enabled Boolean NOT NULL server_default true`, `last_run_at DateTime NULL`, `next_run_at DateTime NOT NULL (indexed)`, `created_at/updated_at DateTime NOT NULL`.
- Produces `JobManager(db: AsyncDB)`:
  - `async create_job(tenant: str, module: str, job_type: str, payload: dict[str, Any], interval_seconds: int, enabled: bool = True) -> dict[str, Any]` (validates `interval_seconds >= 30`; `next_run_at = now + interval`; returns row dict)
  - `async list_jobs(tenant: str, module: str | None = None) -> list[dict[str, Any]]`
  - `async get_job(tenant: str, job_id: str) -> dict[str, Any] | None`
  - `async set_enabled(tenant: str, job_id: str, enabled: bool) -> bool`
  - `async delete_job(tenant: str, job_id: str) -> bool`
  - `async due_jobs(now: datetime, limit: int = 100) -> list[dict[str, Any]]` — cross-tenant BY DESIGN (the sweep is a system actor); `enabled == True` AND `next_run_at <= now`
  - `async mark_ran(job_id: str, now: datetime) -> None` — sets `last_run_at=now`, `next_run_at = now + interval_seconds`, `updated_at=now`

**Steps:**
- [ ] Write failing real_dal tests: create→get round-trip (payload JSON survives); tenant A cannot get/delete/list tenant B's job; `due_jobs` returns only enabled+due, across tenants; `mark_ran` advances `next_run_at` by exactly `interval_seconds`; `interval_seconds < 30` → ValueError.
- [ ] Run → FAIL. Implement model + migration + manager. Run `alembic upgrade head` on a temp DB to prove the migration.
- [ ] Full suite → PASS. **Commit:** `feat(scheduler): scheduled_jobs schema + tenant-scoped JobManager`

### Task 2: Sweep task + handler registry + beat wiring

**Files:**
- Create: `core/scheduler/registry.py`, `core/scheduler/celery_app.py`, `core/scheduler/tasks.py`
- Test: `core/tests/test_scheduler_sweep.py`

**Interfaces:**
- `registry.py`: module-level `_handlers: dict[tuple[str, str], str]`; `register_job_handler(module: str, job_type: str, task_name: str) -> None`; `handler_for(module: str, job_type: str) -> str | None`; `clear_handlers() -> None` (tests).
- `celery_app.py`: copy the import-safe Celery/stub pattern from `core/modules/waddleperf_c2c/worker/celery_app.py` verbatim-in-spirit; app name `"tobogganing_scheduler"`; broker/backend from `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` (Valkey default); `beat_schedule = {"scheduler-sweep": {"task": "core.scheduler.tasks.sweep", "schedule": float(os.getenv("SCHEDULER_SWEEP_SECONDS", "30"))}}`.
- `tasks.py`: `sweep()` Celery task → `asyncio.run(_sweep_async(...))`. `_sweep_async(db: AsyncDB | None = None, dispatch: Callable[[str, dict[str, Any]], None] | None = None, now: datetime | None = None) -> int` (injectable for tests; returns count dispatched): fresh AsyncDB when None; for each `due_jobs()` row → resolve `handler_for(module, job_type)`; unknown handler → structlog warning + `mark_ran` (advance anyway — a bad row must not wedge the sweep); known → `dispatch(task_name, {"job_id", "tenant", "module", "job_type", "payload": parsed dict})` then `mark_ran`. Default dispatch = `celery_app.send_task(task_name, kwargs=...)`. Per-job try/except: one failing dispatch must not abort the sweep (log + continue, still `mark_ran`).

**Steps:**
- [ ] Failing tests (real_dal + fake dispatch list): due job dispatched once with parsed payload and advanced; not-due/disabled skipped; unknown handler advanced + warned, sweep returns correct count; dispatch raising on job 1 does not prevent job 2; second sweep at same `now` dispatches nothing (idempotent via next_run_at advance).
- [ ] Run → FAIL. Implement. Full suite → PASS.
- [ ] **Commit:** `feat(scheduler): beat sweep task with per-(module,job_type) handler registry`

### Task 3: Consumer — `waddleperf_cluster` server-initiated recurring tests

**Files:**
- Create: `core/modules/waddleperf_cluster/api/scheduled_tests.py`, `core/modules/waddleperf_cluster/worker/__init__.py`, `core/modules/waddleperf_cluster/worker/tasks.py`
- Modify: `core/modules/waddleperf_cluster/__init__.py` (blueprint + flag `scheduled_tests` + entitlement `waddleperf_cluster.scheduled_tests` tier community + register_job_handler call)
- Test: `core/tests/test_wpc_scheduled_tests.py`

**Interfaces:**
- Blueprint `scheduled_tests_bp` (url_prefix `/scheduled-tests`), all routes `@require_feature("waddleperf_cluster", "scheduled_tests")` + existing tenant/scope middleware pattern (copy the decorator stack from `api/schedules.py` in waddleperf_client or the cluster module's own tests.py):
  - `POST /` body `{device_id, test_type, target, interval_seconds}` → creates JobManager job with `module="waddleperf_cluster"`, `job_type="server_test"`, payload = body → 201
  - `GET /` → tenant's jobs (module-filtered); `DELETE /<job_id>` → 204/404; `PATCH /<job_id>` body `{enabled: bool}` → 200
- `worker/tasks.py`: Celery task `run_server_test(job_id, tenant, module, job_type, payload)` registered on the scheduler celery_app (import from `core.scheduler.celery_app`); `asyncio.run` → fresh AsyncDB → resolve device via existing `DeviceManager`, execute via existing `EngineClient` (injectable factory like c2c tasks), store result via existing `TestManager` result-ingest path so stats/alerting see it. Engine errors: log + record failed result; never raise out of the task.
- Module `__init__.py`: `register_job_handler("waddleperf_cluster", "server_test", "core.modules.waddleperf_cluster.worker.tasks.run_server_test")` at contract build.

**Steps:**
- [ ] Failing tests: flag off → 402; flag on (monkeypatch feature_enabled) CRUD round-trip against real_dal; created job visible to `JobManager.due_jobs` after interval; `run_server_test` inner async fn with fake engine factory stores a result row (real_dal); cross-tenant DELETE → 404.
- [ ] Run → FAIL. Implement. Full suite → PASS.
- [ ] **Commit:** `feat(waddleperf_cluster): server-initiated recurring tests via core scheduler`

### Task 4: Consumer — `waddleperf_c2c` recurring matrix runs (Professional)

**Files:**
- Create: `core/modules/waddleperf_c2c/api/recurring.py`
- Modify: `core/modules/waddleperf_c2c/__init__.py` (blueprint + flag `recurring_runs` + entitlement `waddleperf_c2c.recurring_runs` tier professional + handler registration)
- Modify: `core/modules/waddleperf_c2c/worker/tasks.py` (add `start_recurring_run` task)
- Test: `core/tests/test_c2c_recurring.py`

**Interfaces:**
- Blueprint `recurring_bp` (url_prefix `/recurring`), routes `@require_feature("waddleperf_c2c", "recurring_runs")`: `POST /` body `{endpoint_ids: list[str] | null, interval_seconds}` → JobManager job `module="waddleperf_c2c"`, `job_type="matrix_run"` → 201; `GET /`, `DELETE /<job_id>`, `PATCH /<job_id>` as Task 3.
- Worker task `start_recurring_run(job_id, tenant, module, job_type, payload)`: fresh AsyncDB → existing `RunManager.create_run(...)` + `enqueue_run(...)` (reuse; do not duplicate pair-fanout logic).
- Handler registration: `register_job_handler("waddleperf_c2c", "matrix_run", "core.modules.waddleperf_c2c.worker.tasks.start_recurring_run")`.

**Steps:**
- [ ] Failing tests: flag on + UNLICENSED → 402 via tier path (monkeypatch `feature_enabled` True only — do NOT patch `_is_licensed_for_tier`; assert 402 mentions professional) — the entitlement-key-trap test; flag on + licensed (monkeypatch `core.entitlements.gate._is_licensed_for_tier`) → CRUD works (real_dal); `start_recurring_run` inner async with fakes creates a run row; assert entitlement key is bare (`entitlement_for("waddleperf_c2c.recurring_runs")` is not None, `entitlement_for("tobogganing.waddleperf_c2c.recurring_runs")` is None).
- [ ] Run → FAIL. Implement. Full suite → PASS.
- [ ] **Commit:** `feat(waddleperf_c2c): Professional recurring matrix runs via core scheduler`

### Task 5: `core/notifications` — channels, transports, delivery log

**Files:**
- Create: `core/models/notification.py`, `core/migrations/versions/0017_notifications.py` (down_revision = "0016")
- Create: `core/notifications/__init__.py`, `core/notifications/channels.py`, `core/notifications/service.py`, `core/notifications/transports.py`
- Test: `core/tests/test_notifications.py` (real_dal + fake transports)

**Interfaces:**
- Tables: `notification_channels` (`id String(36) PK`, `tenant String(36) NOT NULL idx`, `name String(128) NOT NULL`, `kind String(16) NOT NULL` — `email`|`webhook`, `config Text NOT NULL` (JSON: email → `{"to": [addr,...]}`; webhook → `{"url":..., "secret":...}`), `enabled Boolean NOT NULL default true`, `created_at DateTime NOT NULL`); `notification_deliveries` (`id String(36) PK`, `tenant String(36) NOT NULL idx`, `channel_id String(36) NOT NULL`, `subject String(256) NOT NULL`, `status String(16) NOT NULL` — `sent`|`failed`, `error Text NULL`, `created_at DateTime NOT NULL`).
- `channels.py`: `ChannelManager(db)` — tenant-scoped async CRUD (`create_channel(tenant, name, kind, config)` validating kind + required config keys and `url` is https; `list_channels`, `get_channel`, `delete_channel`, `set_enabled`). Webhook `secret` NEVER returned in list/get responses (redact to `"****" + last4`).
- `transports.py`: `EmailTransport.send(to: list[str], subject: str, body: str) -> None` — stdlib `smtplib.SMTP` + STARTTLS in `asyncio.to_thread`, env `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/SMTP_FROM`; `WebhookTransport.send(url: str, secret: str, subject: str, body: str) -> None` — POST JSON `{"subject", "body", "timestamp"}` with header `X-Tobogganing-Signature: sha256=<hmac_sha256(secret, raw_body)>` using the same HTTP client library EngineClient uses (inspect `core/modules/waddleperf_cluster/services/engine_client.py` and reuse). Both async, both raise `TransportError` on failure.
- `service.py`: `NotificationService(db, email_transport=None, webhook_transport=None)` (injectable); `async notify(tenant: str, subject: str, body: str, channel_ids: list[str] | None = None) -> dict[str, int]` — resolves channels (given ids, tenant-verified per-row; None → all enabled for tenant), sends per channel, records one delivery row per attempt (`sent`/`failed` + error), never raises transport errors outward; returns `{"sent": n, "failed": m}`.

**Steps:**
- [ ] Failing tests: channel CRUD + tenant isolation (A cannot use B's channel_id in `notify` — verify a delivery row is NOT created and count unaffected); secret redaction in get/list; notify with fake transports → delivery rows with correct status; failing transport → `failed` row + no exception; webhook signature = HMAC-SHA256 over exact raw body (recompute in fake and assert); non-https webhook URL rejected at create.
- [ ] Run → FAIL. Implement. Full suite → PASS.
- [ ] **Commit:** `feat(notifications): per-tenant channels (email/HMAC webhook) + delivery log`

### Task 6: `waddleperf_cluster` alert rules + evaluation + API

**Files:**
- Create: `core/models/alert.py`, `core/migrations/versions/0018_alert_rules.py` (down_revision = "0017")
- Create: `core/modules/waddleperf_cluster/services/alert_evaluator.py`, `core/modules/waddleperf_cluster/api/alerts.py`, worker task in `core/modules/waddleperf_cluster/worker/tasks.py` (extend)
- Modify: `core/modules/waddleperf_cluster/__init__.py` (blueprint; flags `alerts`, `alert_routing`; entitlements `waddleperf_cluster.alerts` community, `waddleperf_cluster.alert_routing` professional; register `alert_sweep` handler)
- Modify: the test-result ingest path (`core/modules/waddleperf_cluster/api/tests.py` result POST → after successful store, fire-and-forget evaluate; find exact function via grep `record_result\|results`)
- Test: `core/tests/test_wpc_alerts.py`

**Interfaces:**
- Tables: `alert_rules` (`id String(36) PK`, `tenant String(36) NOT NULL idx`, `name String(128) NOT NULL`, `metric String(64) NOT NULL`, `comparator String(8) NOT NULL` — `gt|gte|lt|lte`, `threshold Float NOT NULL`, `window_seconds Integer NOT NULL default 300`, `device_id String(36) NULL`, `test_type String(32) NULL`, `channel_id String(36) NULL`, `enabled Boolean NOT NULL default true`, `created_at DateTime NOT NULL`); `alert_events` (`id String(36) PK`, `tenant String(36) NOT NULL idx`, `rule_id String(36) NOT NULL`, `device_id String(36) NULL`, `observed_value Float NOT NULL`, `fired_at DateTime NOT NULL`, `notified Boolean NOT NULL default false`).
- `AlertEvaluator(db, notifications: NotificationService)`:
  - `async evaluate_result(tenant: str, result: dict[str, Any]) -> int` — match enabled rules (tenant + optional device/test_type filters) against the result's metric value (results store metrics as JSON — inspect `TestManager` result shape and document the key lookup); comparator breach → insert `alert_events` row → `notifications.notify(tenant, subject, body, [rule.channel_id] if set else None)` → mark event notified on success; returns events fired. Dedup: skip firing if an event for the same rule fired within `window_seconds` (query recent events).
  - `async sweep(tenant-less) -> int` — for scheduler `job_type="alert_sweep"`: window aggregates via existing StatsManager where usable; MVP = re-check latest result per (rule, device) within window.
- API blueprint `alerts_bp` (url_prefix `/alerts`), rules+events routes `@require_feature("waddleperf_cluster", "alerts")`; channel CRUD routes proxy `ChannelManager` — `email` kind under `alerts` flag; creating a `webhook` channel additionally requires `require_feature("waddleperf_cluster", "alert_routing")` (Professional): `POST/GET/DELETE /rules`, `GET /events`, `POST/GET/DELETE /channels`.
- Ingest hook: after result store, `if feature_enabled("waddleperf_cluster", "alerts"): await evaluator.evaluate_result(...)` in try/except — alert failure must NEVER fail the ingest response.

**Steps:**
- [ ] Failing tests (real_dal, fake transports): rule CRUD + tenant isolation; breach on ingest → event row + delivery row; no breach → nothing; dedup within window fires once; evaluator exception does not break ingest (patch evaluator to raise, POST result still 2xx); flag off → 402 on rules API AND no evaluation on ingest; webhook channel create unlicensed → 402 via tier path (entitlement-key-trap variant), licensed → 201; email channel create needs only `alerts`.
- [ ] Run → FAIL. Implement. Full suite → PASS.
- [ ] **Commit:** `feat(waddleperf_cluster): threshold alert rules with ingest + sweep evaluation`

### Task 7: Wiring sweep, env, docs, verification

**Files:**
- Modify: `.env.example` (`CELERY_BROKER_URL`, `SCHEDULER_SWEEP_SECONDS`, `SMTP_HOST/PORT/USER/PASS/FROM`)
- Create: `docs/SCHEDULER.md` (running beat+worker: `celery -A core.scheduler.celery_app beat` / `worker`; job model; handler registration contract; flags/tiers table for scheduled_tests, recurring_runs, alerts, alert_routing)
- Modify: memory file + task list
- Steps: full suite; `flake8`/`black --check`/`isort --check`/`bandit -r core/scheduler core/notifications` on touched dirs; ≤1000-line check; **Commit:** `docs(scheduler): scheduler + notifications ops guide`; push; stacked PR (base `feature/phase-4b-kms`).

## Self-Review Notes

- Spec coverage: scheduler (T1–T2), both consumers with correct tiers (T3–T4), notifications split delivery-vs-rules (T5–T6), ingest + sweep evaluation paths (T6), env/docs (T7). AutoPerf + regions deferred to 4c-b per spec sequencing. ✔
- Entitlement-key-trap tests present for both Professional features (T4, T6). ✔
- Sweep resilience: unknown handler / failing dispatch / bad row all advance `next_run_at` and continue. ✔
- Type consistency: JobManager returns row dicts; handler task signature `(job_id, tenant, module, job_type, payload)` uniform across T2–T4/T6. ✔
