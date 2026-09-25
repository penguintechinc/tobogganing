# Phase 2: Port SASE into `modules/sase` (≤1000-line refactor) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Port the py4web `services/hub-api` SASE control plane into Quart blueprints under `core/modules/sase/`, register it through the Phase 1 module contract, split every god file to <1000 lines, migrate the four raw-`sqlite3` managers to penguin-dal, and unify the three auth styles onto the `core` auth middleware — with SASE features declared behind PostHog flags + license tiers.

**Architecture:** `services/hub-api` is decomposed into `core/modules/sase/{api,web,firewall,network,security,backup,audit,analytics}` sub-packages. Each domain's routes become Quart blueprints returned by `sase.module() -> ModuleContract`. Domain manager singletons move into an explicit app-factory lifecycle. Raw sqlite managers cut over to the `core` penguin-dal + the existing `database/` PyDAL schema (reconciling table-name drift). The py4web `@action`/`security_fixture`/inline-Bearer auth collapses onto `core.auth.middleware` (`require_tenant`, `require_scope`, plus a `require_session_user` added here).

**Tech Stack:** Quart, penguin-dal, `core/` framework (Phase 1), pytest (asyncio, 90% gate).

## Global Constraints

- **Depends on #53 (Phase 0) + #54 (Phase 1) being merged to `release/v1.2.X`.** Branch `feature/phase-2-sase-module` off the updated `release`. The Phase 0 `certs/certificate_manager.py` and the `core/` framework must both be present.
- Every file that lands must be <1000 lines (hard requirement of this phase). Split by domain, not by layer.
- All runtime DB access via penguin-dal; NO raw `sqlite3`. Reconcile the per-manager tables against `services/hub-api/database/__init__.py`'s existing PyDAL schema; move `_ensure_*_tables()` DDL into the Alembic baseline / `define_schema`.
- Auth: replace inline Bearer parsing and the py4web `security_fixture`/session decorators with `core.auth.middleware`. Preserve the `sasewaddle_session` cookie name for client compatibility. Add tenant scoping to every query (tenant claim already mandatory in core).
- SASE features declared as module flags `tobogganing.sase.{feature}` (default OFF) + entitlements: IDS/IPS + threat feeds = Community/flag-only; backup/S3 + HA orchestration = Professional; SSO/MFA/advanced-analytics = Enterprise.
- Quart-native async throughout — delete every `loop.run_until_complete` sync-over-async.
- Type hints; `@dataclass(slots=True)`; no bare except; `python3`. 90% coverage on ported code.

## Pre-flight (Task 0)

- [ ] Confirm `certs/certificate_manager.py` is present (from Phase 0). Confirm `core/` framework present. Create branch `feature/phase-2-sase-module` off merged `release/v1.2.X`.
- [ ] Scaffold `core/modules/sase/` package + `core/modules/sase/__init__.py` with a stub `module() -> ModuleContract` (empty blueprints), add `"sase"` to `core/modules/__all__`. Prove the app still boots + tests pass. Commit.

## Task group A — penguin-dal migration (do before porting routes that use them)

Each converts one manager off raw `sqlite3` onto `core` penguin-dal, deletes its `_init_database`/CREATE-TABLE code, and reconciles table drift. TDD: write a test that the manager reads/writes via the DAL against a test DB, per manager.

- [ ] **A1 — `auth/user_manager.py`** (`users.db` → DAL `users`/`sessions`). Note: `core` already owns the `users` identity table (Phase 1) — this manager's user CRUD must target the core `users` table (UUID PK, tenant), and sessions the core session store. Reconcile columns; migrate `create_user/authenticate/create_session/validate_session/logout/list_users/update_user_status/has_permission`. Commit.
- [ ] **A2 — `firewall/access_control.py`** (`firewall.db` `access_rules` → DAL; reconcile with `database`'s `firewall_rules`). Migrate `add_rule/remove_rule/get_user_rules/check_access/get_all_rules/update_rule/export_user_rules`. Commit.
- [ ] **A3 — `network/vrf_manager.py`** (`network.db` `vrfs`/`ospf_areas`/`ospf_neighbors` → DAL; reconcile with `database`'s `vrfs`/`ospf_config`). Migrate full CRUD + `generate_frr_config`. Commit.
- [ ] **A4 — `network/port_manager.py`** (`data/sasewaddle.db` `port_ranges` → DAL; replace the dynamic UPDATE string-builder with parameterized DAL updates). Migrate `get_headend_config/get_cluster_config/add/remove/update_port_range/get_all_configs`. Commit.

Each A-task: failing test (DAL read/write for that manager) → implement cutover → delete sqlite code → test passes → commit.

## Task group B — split + port the two mega route files

**B1 — `web/routes.py` (1198) → `core/modules/sase/web/`** (per the mapped line-ranges):
- `web/pages.py` — login/logout/dashboard/clusters/clients/certificates/users/metrics/firewall/network page handlers (src 47–356) + `_format_time_ago`.
- `web/checkin.py` — checkin_dashboard (357–489).
- `web/admin_actions.py` — cluster/client/user toggle+revoke+create + get_stats (490–617).
- `web/firewall_routes.py` — web firewall CRUD (618–778).
- `web/network_routes.py` — VRF/OSPF CRUD (779–924).
- `web/ports_routes.py` — web port config (1115–1198); MOVE the headend `api/v1/...` firewall+port routes (925–1114) into the API blueprint group (they are API, not web).
- Each becomes a Quart `Blueprint`; the module aggregates them. Replace `@action.uses("template.html")` with `await render_template`, session decorators with `core` `require_session_user`. One sub-file per bullet, each <1000 lines (all are well under). TDD per blueprint (route returns expected status/shape with a mocked service). Commit per sub-file or per cohesive pair.

**B2 — `api/routes.py` (913) → `core/modules/sase/api/`**:
- `api/clusters.py` (register/heartbeat/list/status), `api/clients.py` (register/config/tunnel-config/rotate-key/metrics/list), `api/certs.py` (generate), `api/auth_tokens.py` (token/refresh/validate/revoke/public-key), `api/wireguard.py` (keys/peers/revoke/headend-config), `api/headend_metrics.py`.
- Replace the ~10 inline `Authorization: Bearer` parses with `core` bearer/JWT dependency (`require_scope`/a bearer decorator). Keep the Phase 0 enrollment-token gate on register/cert issuance. TDD per blueprint. Commit per file.

## Task group C — port the secondary route files + split oversized services

- [ ] **C1** — `api/security_scanner_routes.py` (713) → `sase/security/scanner_routes.py` (feeds + scans + findings + dashboard); convert `security_fixture` → core middleware; sync→async. Split if >1000 (it isn't, but the backing `scanner.py` is — see C5). Commit.
- [ ] **C2** — `api/audit_routes.py` (547) + `audit/` singletons → `sase/audit/` blueprint. Commit.
- [ ] **C3** — `api/backup_routes.py` (434) → `sase/backup/routes.py`; build `BackupManager` via the app factory (not ad-hoc). Commit.
- [ ] **C4** — `api/analytics_routes.py` (449) + `web/analytics_routes.py` (69) + `api/security_routes.py` (552) → `sase/analytics/` + `sase/security/routes.py`. Commit.
- [ ] **C5 — split the oversized service modules** (the actual ≤1000-line targets among services):
  - `security/scanner.py` (889) → `security/scanner/{core.py,scans.py,parsers.py,infra_monitor.py}`.
  - `security/feeds.py` (775) → `security/feeds/{manager.py,sources.py,detection.py}`.
  - `security/__init__.py` (682) → `security/{ratelimit.py,ddos.py,middleware_core.py}`.
  - `backup/__init__.py` (762) → `backup/{manager.py,s3.py,crypto.py,cli.py}`.
  Each split preserves the public singleton/API; move `_ensure_*_tables` DDL into the schema. TDD: import + a smoke test per split module. Commit per module split.

## Task group D — auth unification + module assembly

- [ ] **D1** — Add `require_session_user` (server-side `sessions` table via DAL, `sasewaddle_session` cookie, native async) to `core/auth/middleware.py`; delete `web/auth.py`'s `run_until_complete` pattern. Reimplement `security/middleware.py`'s `security_fixture`/`require_admin_role` as core decorators. Commit.
- [ ] **D2** — `core/modules/sase/__init__.py` `module()` returns the full `ModuleContract`: all blueprints (api + web + security + audit + backup + analytics), nav entries, declared flags (`tobogganing.sase.*`), entitlements (tiers per Global Constraints), migrations (the SASE tables), and health hooks. Wire the domain managers into the app-factory lifecycle (startup/shutdown) instead of import-time self-init. Commit.
- [ ] **D3** — Unify the two entrypoints: delete `services/hub-api/app.py` vs `main.py` divergence; the module is hosted by `core` app factory. Remove the old py4web `services/hub-api/main.py`/`app.py` once parity is reached (or leave hub-api runnable until Phase 2 merges — decide at execution: prefer full cutover so there's one control plane). Commit.

## Task group E — verification

- [ ] **E1** — Full `core` suite incl. SASE module tests, `--cov-fail-under=90`. mypy strict + flake8.
- [ ] **E2** — File-size gate: `git ls-files 'core/modules/sase/**/*.py' | xargs wc -l` → every file <1000. Fail the task if any exceeds.
- [ ] **E3** — Smoke: app boots with the SASE module registered; representative routes (login page, cluster register with enrollment token, firewall rule CRUD, a flag-gated analytics route) exercised against a test DB.
- [ ] Open PR into `release/v1.2.X`.

## Known risks / call-outs (from the map)
- **Table-name drift**: `access_rules` vs `firewall_rules`; `ospf_areas`/`ospf_neighbors` vs `ospf_config`. Pick the `core`/`database` schema as authoritative and adapt managers; add an Alembic revision for any SASE-specific tables.
- **Three auth styles** (inline Bearer / session-cookie / security_fixture) all collapse onto `core.auth.middleware` — D1 must land before B/C routes are considered done.
- **Manager lifecycle**: 5 managers have initialize/shutdown; domain singletons self-init at import (each opening a sqlite db — which A1–A4 remove). Move all to explicit factory startup hooks (D2).
- **`_ensure_*_tables()` DDL** in scanner/feeds/security/audit must move into the schema authority, not run at runtime.
- Scope: this is the largest phase (~15k source lines). Execute A → D1 → B/C → D2/D3 → E, committing per sub-file; keep each PR-reviewable.

## Self-Review
- Every god file >1000 and every 700–1000 at-risk file has an explicit split target (B1, B2, C5). All four sqlite3 managers have a DAL migration task (A1–A4). Auth unification (D1) precedes route ports. Coverage + file-size + smoke gates in E. Deferred items from earlier phases (certs from Phase 0, core from Phase 1) are pre-flight dependencies (Task 0). No placeholders — each task names exact source line-ranges and target files from the structural map.
