# Phase 5b — Portal View Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full module-view parity in the portal: SASE (clusters/clients/status), waddleperf_cluster operations views (alerts, scheduled tests, AutoPerf, live test with real-time charts), and waddleperf_c2c (endpoints, runs + matrix grid, recurring, regions). Completes Phase 5.

**Architecture:** Each module owns a view map (`src/routes/{wpc,c2c,sase}Views.ts`) resolved by the shared registry — workers never touch shared route code. Pages follow the 5a pattern: typed API module per backend blueprint (envelopes read from the Python source, never guessed), TanStack Query hooks, DataTable for lists, loading/error/empty states, `canWrite()` gating on mutations. Live test streams over the existing WebSocket endpoint (token via query param — small backend addition) into a recharts live line chart.

**Tech Stack / Global Constraints:** identical to the 5a plan (`2026-07-14-phase-5a-portal-shell.md`) — exact-pinned deps, files ≤5000 chars, sanitized console logging, dark slate+gold, **jest 90/90/90/90 gate stays green after every task**, ESLint/Prettier clean, build clean. Branch: `feature/phase-5b-portal-views` off `feature/phase-5a-portal-shell`.

---

### Task A: waddleperf_cluster operations views

**Owns (create only):** `src/pages/waddleperf/{AlertsPage,ScheduledTestsPage,AutoPerfPage}.tsx` (+ subcomponents as needed for the 5000-char limit), `src/api/wpcOps.ts`, tests for each; **modify only** `src/routes/wpcViews.ts` (add `alerts`, `scheduled-tests`, `autoperf` — hyphenated slugs must match `slug(label)` of the module's NavEntries; check `core/modules/waddleperf_cluster/__init__.py` nav labels and ADD nav entries there for Alerts/Scheduled Tests/AutoPerf if missing, mirroring existing style — backend nav is the source of truth for what appears in the sidebar).

- AlertsPage: tabs (Rules / Channels / Events) per `core/modules/waddleperf_cluster/api/alerts.py` — rules table + create form (metric/comparator/threshold/window/device/test_type/channel), channels table + create (email config; webhook marked Professional — surface the 402 body message as a friendly upsell banner), events table (read-only). Mutations behind `canWrite()`.
- ScheduledTestsPage: table + create/enable-disable/delete per `api/scheduled_tests.py`.
- AutoPerfPage: policies table + create/delete + per-policy state panel (current tier T1/T2/T3 badge, clean cycles, escalated_at) per `api/autoperf.py`.

### Task B: waddleperf_c2c views

**Owns (create only):** `src/pages/c2c/{EndpointsPage,RunsPage,MatrixGrid,RecurringPage,RegionsPage}.tsx`, `src/api/c2c.ts`, tests; **modify only** `src/routes/c2cViews.ts` (slugs matching the module's NavEntries — read `core/modules/waddleperf_c2c/__init__.py`; add nav entries there for any missing views, e.g. Recurring/Regions).

- EndpointsPage: table (name/region/visibility/provider/health badge) + create per `api/endpoints.py` (+ 0020 fields).
- RunsPage: runs table + detail → MatrixGrid: source×dest grid of pair results colored by loss/latency (plain CSS grid, not recharts) per `api/matrix.py` shapes.
- RecurringPage: recurring jobs (job_type matrix_run|node_health) per `api/recurring.py`.
- RegionsPage: region aggregate cards + nodes table (redacted foreign-public rows render without engine columns) per `api/regions.py`.

### Task C: SASE views

**Owns (create only):** `src/pages/sase/{ClustersPage,ClientsPage,StatusPage}.tsx`, `src/api/sase.ts`, tests; **modify only** `src/routes/saseViews.ts` (slugs from the sase module's NavEntries: clusters, clients, status).

- ClustersPage/ClientsPage: tables + detail per `core/modules/sase/api/{clusters,clients}.py` envelopes; mutations behind `canWrite()`.
- StatusPage: health/status cards per `api/status.py`.

### Task D: Live test page (WS + real-time charts)

**Backend prereq (done by orchestrator):** `live_test.py` `_validate_websocket_auth` accepts `?token=` query param when the Authorization header is absent (browser WebSocket API cannot set headers) + test.

**Owns:** `src/pages/waddleperf/LiveTestPage.tsx` + `src/hooks/useLiveTest.ts` + tests; add `live-test` to `wpcViews.ts` (after Task A merges — sequenced). Hook: opens `wss?://…/api/v1/waddleperf_cluster/live-test/stream?token=<access_token>` via the page origin (proxy handles upgrade), buffers progress messages (cap 500), exposes status/series; page: run form (device/test_type/target) → POST `/live-test/run`, live recharts LineChart fed from the stream, connection state indicator. Mock WebSocket in jest (global.WebSocket stub).

### Task E: e2e + verification + PR

- Extend `e2e/smoke.spec.ts` + `mock-api.js`: manifest lists all three modules; navigate to one page per module and assert its table/empty-state renders (mock list endpoints return 2 rows / empty).
- Full verification: jest 90-gate, lint, build, Playwright all green (orchestrator-run); backend full suite green (nav-entry additions touch module contracts — contract tests may assert nav lists; update them).
- `docs/PORTAL.md` views section updated; memory; push; stacked PR base `feature/phase-5a-portal-shell`.

## Self-Review Notes
- Workers A/B/C are file-disjoint (own pages dir + own api module + own view-map file + own module's backend `__init__.py` nav lists). ✔
- Every backend envelope is read from source, matching the 5a discipline. ✔
- WS auth via query param is the only backend behavior change; header auth unchanged. ✔
