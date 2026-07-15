# Phase DAL — Repo-wide async penguin-dal correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Fix the control-plane persistence layer, which uses a penguin-dal API that does not exist in penguin-dal 0.2.0 (`AsyncDB`). Convert every broken manager to the real async API, back the fix with real sqlite integration tests (not mocks), and update documentation.

**Architecture:** `get_db()` returns a penguin-dal **`AsyncDB`**. Managers are async; they use `await db(cond).select()/.update()/.delete()/.count()` and `await db.table.async_insert()`. Routes (async) `await` managers. The Celery worker builds a fresh `AsyncDB` per task and runs managers via `asyncio.run`.

**Reference (already-correct) file:** `core/modules/sase/auth/user_manager.py`. Copy its idioms exactly.

## Global Constraints
- Python 3.13; type hints (`mypy` where clean); no bare except; `python3`; every file < 1000 lines.
- Tenant-scoped: every query filters by the manager's tenant. Never trust tenant from body/header.
- Real integration tests via the `real_dal` fixture (conftest) — the anti-mock guard. Every converted manager gets at least one `real_dal` round-trip + tenant-isolation test.
- Managers must pass ALL NOT NULL columns explicitly (e.g. `created_at`/`updated_at` via `datetime.now(datetime.UTC)`) — penguin-dal reflection does not apply model Python defaults.

## Canonical Conversion Cheatsheet (penguin-dal 0.2.0 AsyncDB)
| Broken current form | Correct async form |
|---|---|
| `db.t.select(a=x).first()` | `(await db(db.t.a == x).select()).first()` → `Row \| None` |
| `db.t.select(a=x, b=y)` | `await db((db.t.a == x) & (db.t.b == y)).select()` → `Rows` |
| `db.t.create(**kw)` / `db.t.insert(**kw)` | `await db.t.async_insert(**kw)` (returns PK; keep the dict you built to return) |
| `db.t.update(a=x, **ch)` | `await db(db.t.a == x).update(**ch)` → int rowcount |
| `db.t.delete(a=x)` | `await db(db.t.a == x).delete()` → int rowcount |
| `await asyncio.to_thread(db.t.create, **kw)` | `await db.t.async_insert(**kw)` (drop `to_thread`) |
| `await asyncio.to_thread(db.t.select, a=x)` | `await db(db.t.a == x).select()` |
| `row_obj.update(**ch)` / `row_obj.delete()` | `await db(db.t.id == row.id).update(**ch)` / `.delete()` |
| `db(q).async_select()` / `.async_count()` | `await db(q).select()` / `await db(q).count()` (async methods are named `select`/`count`) |
| `db.execute_query(...)` / `db.query(...).all()` | `await db(cond).select()` |
| `db.execute_insert("t", {...})` | `await db.t.async_insert(**{...})` |
| `db.execute_update("t", ...)` / `db.session.add(x)+commit()` | `await db(cond).update(**ch)` / `await db.t.async_insert(**cols)` |
| newest-first | `orderby=db.t.created_at.column.desc()` |
| pagination | `limitby=(offset, limit)` |
| count | `await db(cond).count()` → int |
| atomic counter increment | `await db(db.t.id == x).update(col=db.t.col.column + 1)` |

- `Rows`: `.first()`, `.last()`, `.as_list()`, iterate, `len()`, truthy-if-nonempty. `Row`: attr access `row.id`, item `row["id"]`, `.get("id")`, `.as_dict()`.
- Every DAL method becomes `async def`; every caller `await`s it. Most route callers already `await`; c2c `api/*` callers are currently sync and MUST be made to `await`.
- Real-DAL test skeleton:
  ```python
  @pytest.mark.asyncio
  async def test_x(real_dal):
      mgr = TheManager(real_dal, tenant="t1")
      rec = await mgr.create_...(...)
      assert (await mgr.get_...(rec["id"]))["id"] == rec["id"]
      # tenant isolation: TheManager(real_dal, "t2").get_...(rec["id"]) is None
  ```

## Task Groups (each = disjoint file set; convert + real_dal tests; edit-only)

### DAL-1 — `core/auth/service.py` (BROKEN-SYNC, 10 sites, 8 methods→async)
No non-test callers. Convert `AuthService` methods to `async def`. Update `core/tests/test_auth_service.py` to `await` + `@pytest.mark.asyncio`; add `real_dal` round-trips (authenticate, refresh, MFA). Also fix the flaky TOTP window: `valid_window=1` in `verify_mfa`.

### DAL-2 — `waddleperf_c2c` (BROKEN-SYNC): `services/{endpoint_manager,run_manager,matrix_service}.py`, `api/{endpoints,runs,matrix}.py`, `worker/tasks.py`
Convert managers → async; add `await` at the 3 `api/*` callers (currently sync). Worker: build a fresh `AsyncDB` per task, run managers via `asyncio.run`; delete `_convert_uri_to_sync` + sync `DB`. Fold in review findings: (#2) `record_pair_result` uses ATOMIC increment `completed_pairs=db.c2c_matrix_runs.completed_pairs.column + 1` (+ failed_pairs), (#3) worker outer `except` records a FAILED pair result + advances progress (never drop), (#4) reject empty/blank `api_key` in `create_endpoint` + `authenticate_node_global`, (#5) `GET /matrix/runs/<id>` uses `RunManager.get_run` for existence (not empty-cells). Update mock tests + add `real_dal` tests.

### DAL-3 — `waddleperf_cluster/services/*` (BROKEN-THREAD): device_manager, org_unit_manager, enrollment_manager, test_manager, device_auth
Drop `to_thread`; use real async API. Callers already `await`. Update mock tests + add `real_dal` tests (esp. `authenticate_device_global`).

### DAL-4 — `waddleperf_client/services/schedule_manager.py` (BROKEN-THREAD)
Drop `to_thread`; real async API. Update tests + `real_dal` tests.

### DAL-5 — `sase/orchestrator/{cluster_manager,client_registry}.py` (BROKEN-THREAD + row-object update/delete)
Drop `to_thread`; convert row-object `.update()/.delete()` → `await db(db.t.id==row.id)...`. Callers (`sase/api/*`) already await. Update tests + `real_dal` tests.

### DAL-6 — sase BROKEN-SYNC + BROKEN-HELPER: `backup/manager.py`, `security/scanner/core.py`, `security/protection/ratelimit.py`
`backup`: async + real API (callers = `backup/cli.py`). `scanner/core`: replace `db.execute_query/execute_insert/execute_update` with real API. `ratelimit`: replace `db.query().all()`/`db.session.add/commit` with real API; make its sync methods async. Update tests + `real_dal` tests.

### DAL-7 — sase feeds: `security/feeds/{detection,manager}.py` (`.async_select`/`.async_count` → `.select`/`.count`)
Rename to the real async methods. Update tests + `real_dal` tests.

### DAL-8 — `core/auth/middleware.py` + `core/entitlements/metering.py`
`middleware`: session/user lookups already async but wrapped in `to_thread` — await AsyncQuerySet directly. `metering`: `count_users` via `await db(...).count()`. Update tests + `real_dal` tests where feasible.

### DAL-9 — verify-only: `sase/auth/user_manager.py`, `network/port_manager.py`, `network/vrf_manager.py`, `firewall/access_control.py`
Already correct. Confirm; reconcile any stray `.async_*`. Add a `real_dal` test each to prove correctness (anti-mock).

### DAL-DOCS — documentation
Update `docs/standards/DATABASE.md` (add the penguin-dal 0.2.0 async usage pattern + the "reflect from migrations" test-harness note). Add `docs/APP_STANDARDS.md`/module notes referencing the cheatsheet. Note the model (`UUID(as_uuid=False)`) vs migration (`String(36)`) type divergence as a known follow-up.

## Sequencing
- Foundation (DONE): `real_dal` fixture + harness smoke test (commit dbf76a6).
- Wave A (parallel, edit-only): DAL-1, DAL-2, DAL-3, DAL-4.
- Wave B (parallel, edit-only): DAL-5, DAL-6, DAL-7, DAL-8.
- Wave C: DAL-9 (verify) + DAL-DOCS.
- Orchestrator runs the FULL `core/` suite and commits each group with a narrow `git add` after green. No agent commits.

## Self-Review Notes
- The reference pattern is `user_manager.py` — do not invent a different style.
- penguin-dal reflection ignores model defaults → pass timestamps/NOT NULL cols explicitly.
- Schema authority is Alembic; the `real_dal` fixture builds via `alembic upgrade head`.
- Keep every file < 1000 lines; split test files if needed.
