# Phase 4c-b — AutoPerf Tiered Monitoring + Region/Node Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The final Phase 4c slice: AutoPerf auto-escalating tiered monitoring in `waddleperf_cluster` (Professional) and the public/private test-node region registry in `waddleperf_c2c` (Professional) — both built on the 4c-a scheduler/alerting/notifications infrastructure.

**Architecture:** AutoPerf = per-policy escalation state machine driven by alert events: a scheduler `autoperf_cycle` job runs the current tier's test set through the existing server-test execution path; alert-event presence for the device since the last cycle escalates T1→T2→T3, and N consecutive clean cycles de-escalate. Region registry = visibility/provider/health columns on `c2c_endpoints`, a `/regions` catalog API where `public` nodes are readable across tenants (by design — that is what public means; everything else stays tenant-fail-closed), and a scheduler `node_health` sweep hitting each engine's `/health`.

**Tech Stack:** identical to 4c-a (Quart, canonical penguin-dal AsyncDB, Alembic authority, Celery on `core.scheduler.celery_app`, real_dal tests, fakes only at engine/transport boundaries).

## Global Constraints

Same as the 4c-a plan (`2026-07-14-phase-4c-a-scheduler-alerting.md` Global Constraints) — canonical DAL, String(36) ids in migrations, models in `core/db/models.py`, `tests/test_migrations_head.py` per-migration set updates, bare entitlement keys, flags default OFF, real_dal + HTTP-level gate tests (including the entitlement-trap 402 for every Professional feature), files ≤1000 lines, workers edit-and-test only.

Branch: `feature/phase-4c-b-autoperf-regions` off `feature/phase-4c-a-scheduler-alerting`.

---

### Task 1: AutoPerf schema + manager

**Files:** models in `core/db/models.py`; `core/migrations/versions/0019_autoperf.py` (down_revision "0018"); `core/modules/waddleperf_cluster/services/autoperf_manager.py`; tests `core/tests/test_autoperf_manager.py` (real_dal).

**Interfaces:**
- Table `autoperf_policies`: `id String(36) PK`, `tenant NOT NULL idx`, `name String(128) NOT NULL`, `device_id String(36) NOT NULL`, `target String(500) NOT NULL`, `t1_interval_seconds Integer NOT NULL default 300`, `t2_interval_seconds Integer NOT NULL default 120`, `t3_interval_seconds Integer NOT NULL default 60`, `deescalate_after_clean Integer NOT NULL default 3`, `enabled Boolean NOT NULL default true`, `created_at NOT NULL`.
- Table `autoperf_state`: `id String(36) PK`, `tenant NOT NULL idx`, `policy_id String(36) NOT NULL (unique)`, `current_tier Integer NOT NULL default 1`, `clean_cycles Integer NOT NULL default 0`, `last_cycle_at DateTime NULL`, `escalated_at DateTime NULL`, `updated_at NOT NULL`.
- `AutoPerfManager(db)`: tenant-scoped async CRUD for policies (`create_policy` validates intervals ≥30 and t3≤t2≤t1, creating the state row and its scheduler job atomically-in-order: policy → state → `JobManager.create_job(tenant, "waddleperf_cluster", "autoperf_cycle", {"policy_id": ...}, t1_interval)`); `get_state(tenant, policy_id)`; `record_cycle(tenant, policy_id, breached: bool) -> dict` implementing the state machine: breached → tier=min(tier+1,3), clean_cycles=0, escalated_at=now; clean → clean_cycles+=1, and if clean_cycles ≥ deescalate_after_clean and tier>1 → tier-=1, clean_cycles=0. Tier changes must also retune the scheduler job's `interval_seconds` to the new tier's interval (add `JobManager.set_interval(job_id/tenant scoped)` or update via db — pick one, document it). `delete_policy` removes policy + state + its scheduler job.

**Tests:** CRUD + tenant isolation; escalation T1→T2→T3 caps at 3; de-escalation after exactly N clean cycles, one tier at a time; interval retune reflected in `scheduled_jobs`; delete cleans all three rows.

Steps: failing tests → migration/model/manager → `test_migrations_head` set for 0019 → full suite → **Commit** `feat(waddleperf_cluster): AutoPerf policies + escalation state machine`.

### Task 2: AutoPerf cycle job + API (Professional)

**Files:** extend `core/modules/waddleperf_cluster/worker/tasks.py` (`autoperf_cycle` task); `core/modules/waddleperf_cluster/api/autoperf.py`; contract updates in module `__init__.py`; tests `core/tests/test_autoperf_api.py`.

**Interfaces:**
- `autoperf_cycle(job_id, tenant, module, job_type, payload)`: fresh AsyncDB; load policy+state; tier test sets — T1 `["icmp", "http"]`, T2 + `["tcp", "udp", "http_trace"]`, T3 + `["speedtest", "traceroute"]`; execute each via the SAME engine/result path as `run_server_test` (refactor its inner helper for reuse — do not duplicate); breached = any `alert_events` row for (tenant, device_id) with `fired_at > state.last_cycle_at`; call `AutoPerfManager.record_cycle`; never raise.
- API blueprint `autoperf_bp` (`/autoperf`): `POST/GET/DELETE /policies`, `GET /policies/<id>/state` — all `@require_feature("waddleperf_cluster", "autoperf")`.
- Contract: flag `tobogganing.waddleperf_cluster.autoperf`; `Entitlement("waddleperf_cluster.autoperf", tier="professional")`; `register_job_handler("waddleperf_cluster", "autoperf_cycle", ...)`.

**Tests (HTTP + real_dal):** flag off → 402; flag on unlicensed → 402 professional (trap test, no `_is_licensed_for_tier` patch); licensed CRUD; cycle task with fake engine: breach path escalates + retunes interval, clean path counts down and de-escalates; engine failure records failed result and still cycles.

Steps: TDD → full suite → **Commit** `feat(waddleperf_cluster): Professional AutoPerf tiered monitoring cycle + API`.

### Task 3: Region/node registry schema + API (Professional)

**Files:** `core/migrations/versions/0020_endpoint_regions.py` (down_revision "0019") adding to `c2c_endpoints`: `visibility String(16) NOT NULL server_default 'private'` (`private|public`), `provider String(64) NULL`, `health_status String(16) NOT NULL server_default 'unknown'` (`unknown|healthy|unhealthy`), `last_health_check DateTime NULL`; update the `C2CEndpoint` model; `core/modules/waddleperf_c2c/api/regions.py`; `EndpointManager` extensions; contract updates; tests `core/tests/test_c2c_regions.py`.

**Interfaces:**
- `EndpointManager` additions: `list_regions(tenant) -> list[dict]` — aggregates by region over (own tenant's endpoints + ALL tenants' `visibility == "public"` endpoints): `{region, node_count, healthy_count, providers: [...]}`; `visible_endpoints(tenant, region=None) -> list[dict]` with the same own+public rule — public foreign endpoints are returned WITHOUT `engine_url`/`api_key_hash`/`target` (id, name, region, provider, health only; cross-tenant secrets never leak); endpoint create/update accepts `visibility`/`provider` (validate values).
- Blueprint `regions_bp` (`/regions`): `GET /` (region aggregate), `GET /nodes?region=...` (visible endpoints) — `@require_feature("waddleperf_c2c", "regions")`.
- Contract: flag `tobogganing.waddleperf_c2c.regions`; `Entitlement("waddleperf_c2c.regions", tier="professional")`.
- `test_migrations_head` 0020 note: it asserts table coverage, not columns — verify it still passes; if it checks columns, extend accordingly.

**Tests:** aggregate math over mixed visibility/tenants (real_dal); foreign public node redaction (no engine_url/target/api_key_hash in response — assert keys absent); foreign PRIVATE nodes never visible; flag off 402; unlicensed 402 professional (trap); licensed 200.

Steps: TDD → full suite → **Commit** `feat(waddleperf_c2c): Professional region/node registry with public-node catalog`.

### Task 4: Node health sweep

**Files:** extend `core/modules/waddleperf_c2c/worker/tasks.py` (`node_health` task); contract handler registration; tests `core/tests/test_c2c_node_health.py`.

**Interfaces:** `node_health(job_id, tenant, module, job_type, payload)`: fresh AsyncDB; for each of the TENANT's enabled endpoints (health checks are run by the owning tenant only), GET `{engine_url}/health` via the injectable engine-client factory (timeout 5s); update `health_status` (`healthy` on 200, else `unhealthy`) + `last_health_check`; per-endpoint try/except; never raise. Registered as `register_job_handler("waddleperf_c2c", "node_health", ...)` — tenants opt in by creating a scheduled job with that job_type through the existing recurring API pattern (extend `/recurring` POST to accept `job_type: "matrix_run" | "node_health"`, default `matrix_run`; `node_health` requires the `regions` feature).

**Tests:** healthy/unhealthy transitions with fake engine; one failing endpoint doesn't stop the sweep; foreign-tenant endpoints untouched; job_type validation on the recurring API.

Steps: TDD → full suite → **Commit** `feat(waddleperf_c2c): scheduler-driven node health sweep`.

### Task 5: Docs, env, verification, PR

- Extend `docs/SCHEDULER.md` consumer table with autoperf/regions rows; add an AutoPerf section (tiers, escalation rules) and regions section (visibility semantics, redaction rule) — or a short `docs/AUTOPERF.md` if >40 lines.
- Full suite; flake8/bandit on touched paths; ≤1000-line check; update memory; push; stacked PR (base `feature/phase-4c-a-scheduler-alerting`).

## Self-Review Notes
- Spec coverage: AutoPerf tiers/escalation/de-escalation/metering-tier (T1–T2), region catalog + public/private + health + matrix-adjacent selection via `visible_endpoints` (T3–T4). ✔
- Both Professional features carry the entitlement-trap 402 HTTP test. ✔
- Cross-tenant surface is exactly one deliberate opening (public-node read, secrets redacted) — tested both directions. ✔
