# Squawk P5 — UI + Helm Umbrella + Cross-Module E2E + CI Gates — Design

- **Date:** 2026-08-20
- **Branch:** `feature/squawk-merger` (off `release/v1.2.X`)
- **Status:** Approved — scope **Comprehensive**; CI gates **add jobs + enforce repo-wide** (user-selected)
- **Part of:** squawk → netsvcs merge umbrella. Final phase (follows P0–P4). P0–P4 DONE.

## Goal

Finish the squawk cutover: give the netsvcs (DNS) + threatintel modules real portal UI, deploy P3 (netsvcs-dns) and P4 (node-agent) as part of the umbrella Helm release, cover the cross-module merge seams with end-to-end tests, and turn on the coverage gates repo-wide in CI.

## Locked Decisions

| Decision | Value |
|---|---|
| Scope | **Comprehensive** — existing-endpoint UI **plus** net-new threat-intel feed + blocklist management API+UI |
| CI gates | Add the missing CI jobs (Rust `llvm-cov`, netsvcs-dns pytest, Playwright) **and** enforce coverage repo-wide (drop `\| exit 0`, `--cov-fail-under=90`, `--fail-under-lines 90`) |
| UI framework | Follow the portal's existing local pattern (React 18 + Vite + TanStack Query + data-driven `viewRegistry`), mirroring the `sase` module. No new UI libs. |
| Feature flags | Every new UI surface + endpoint behind `tobogganing.netsvcs.*` / `tobogganing.threatintel.*` PostHog flags, default OFF |

## Recon Baseline (verified)

- **Portal:** React 18 + Vite 5 + TS, `react-router-dom` 6, `@tanstack/react-query` 5, `axios`, `recharts`. JWT in sessionStorage w/ refresh interceptor (`src/api/client.ts`). Data-driven routing `/m/:module/:view` → `src/routes/viewRegistry.ts` → `PlaceholderView` fallback. Nav comes from backend `ModuleContract.nav` via `useManifest`. Copy the `sase` pattern: `src/api/sase.ts` (typed axios fns) + `src/pages/sase/*` (`useQuery`+`DataTable`) + `src/routes/saseViews.ts` (slug→component). **No netsvcs/threatintel UI exists** — sidebar shows the nav entries but views render placeholders.
- **Helm:** umbrella at `k8s/helm/tobogganing` (v2.0.0, `dependencies:` + `Chart.lock`) aggregates only the 5 SASE subcharts. netsvcs-dns (`engines/netsvcs-dns/k8s/helm/netsvcs-dns`, `.yml` values) + node-agent (`k8s/helm/node-agent`, `values-*.yaml`) are **not wired in**. `scripts/deploy-beta.sh` deploys only the umbrella. NetworkPolicy has no gRPC `:50051` rule. First-party images not digest-pinned; values naming inconsistent (no `gamma` in umbrella).
- **Tests/CI:** no `test-integration`/`test-e2e` make targets. `.github/workflows/ci.yml` has `test-manager` (Python), `test-headend`/`test-client` (Go) — **no Rust, no netsvcs-dns, no Playwright job**; `integration-test` is a placeholder. Coverage non-blocking (`pytest.ini` forbids `--cov-fail-under`; cov runs `\| exit 0`). `portal/e2e/mock-api.js` lacks netsvcs/threatintel routes. `real_dal` fixture (`hub_api/tests/conftest.py`) drives real-DB tests.

## Work Breakdown

### A. threatintel backend (net-new — unblocks the full threatintel UI)
New REST endpoints in `hub_api/modules/threatintel` (Quart, quart-schema validated response DTOs, scope-gated, tenant-scoped, `real_dal` tested):
- Feed management: list / create / delete / trigger-refresh threat-feed sources (MISP/STIX/TAXII/CSV) over the existing feeds manager. Add a migration only if a new column/table is genuinely required; prefer existing `ThreatIndicator`/feed models.
- Blocklist management: list / add / remove blocklist entries (over `BlocklistStore`).
- Publish OpenAPI (`openapi/v1.yaml`) for the new routes; docs endpoint stays authed.

### B. portal UI
- `src/api/netsvcs.ts` + `src/api/threatintel.ts` (typed axios clients), `src/routes/netsvcsViews.ts` + `threatintelViews.ts` into `viewRegistry`, expand backend `NavEntry` lists (netsvcs currently has only "DNS").
- **netsvcs pages:** Zones (list/CRUD) → Records drilldown (nested table/modal, CRUD); DNS Servers fleet (+ metrics detail panel); Analytics dashboard (recharts over `/netsvcs/analytics/{summary,queries,performance,servers}`).
- **threatintel pages:** IOC Check (lookup→verdict); Feeds management + Blocklist management (backed by A).
- All behind feature flags. Marketing screenshots (`docs/screenshots/`) captured against seeded mock data (`capturing-marketing-screenshots` skill).

### C. Helm umbrella integration
- Wire netsvcs-dns + node-agent into `k8s/helm/tobogganing` as dependencies with `condition:` toggles; relocate the netsvcs-dns chart into the umbrella tree (or reference), regenerate `Chart.lock`.
- Add NetworkPolicy allow rules for the new intra-cluster gRPC `:50051` paths (netsvcs-dns ↔ hub-api CheckIOC/config-sync; node-agent → hub-api). Prefer `CiliumNetworkPolicy` per `security.md` (flag the existing plain `NetworkPolicy` as a standards gap).
- Reconcile values env matrix (add `gamma`, standardize `values-*.yaml` naming) + a shared image/registry/digest block; **digest-pin first-party images**.
- Extend `scripts/deploy-beta.sh` (+ siblings) to roll out all three as one unit.
- `helm lint` + `helm template` clean for every env.

### D. cross-module E2E seam tests
Cover the four merge seams (priority order):
1. machine-JWT enroll → `RegisterServer` → hub issues config → agent applies (highest blast radius).
2. zone/record CRUD (control plane) → `GetConfig` → netsvcs-dns resolves the record.
3. feed ingest → blocklist store → `IOCChecker.check_domain/ip`.
4. resolver/agent IOC lookup → threatintel block decision.
- Add `test-integration` + `test-e2e` make targets; extend `portal/e2e/mock-api.js` with netsvcs/threatintel routes; add a seed path (mock data, 3–4 items/feature).
- Regression tests referencing the P1–P4 bugs (penguin-dal comma-syntax; gRPC hardening; double-enroll).

### E. CI hardening + repo-wide gates
- Add CI jobs: Rust (`cargo llvm-cov --fail-under-lines 90` for node-agent), netsvcs-dns pytest (+cov), Playwright (portal e2e). Replace the `integration-test` placeholder with the real `test-e2e`.
- **Measure the current per-language coverage baseline FIRST** and report the repo-wide-enforcement lift before closing gaps. Then flip enforcement: remove `\| exit 0`, set `--cov-fail-under=90` (Python) / `--fail-under-lines 90` (Rust) / jest `coverageThreshold` (portal).
- Close the gaps the flip surfaces to reach 90% everywhere. If a gap is a mountain (baseline far below 90% for a large legacy area), stop and report rather than silently grinding.

## Execution Waves (fan-out)

```
Wave 1 (parallel worktrees, disjoint dirs):
  A threatintel backend (hub_api/modules/threatintel) ── penguin-python-dev
  B-netsvcs UI (portal/src netsvcs)                    ── penguin-react-dev   (endpoints already exist)
  C Helm umbrella (k8s/helm, engines/.../k8s)          ── k8s-manifest-builder
  D E2E seam tests (hub_api/tests, engines tests)      ── penguin-python-dev
  + coverage-baseline measurement                       ── (orchestrator/test-runner)
Wave 2:
  B-threatintel UI (needs A)                            ── penguin-react-dev
  E CI hardening + repo-wide gates + gap-closing        ── penguintech-dev + language specialists
Wave 3:
  screenshots + final integration verify + umbrella helm lint/template
```

Each worktree owns a disjoint directory set → minimal merge conflict (shared points: `openapi/v1.yaml`, `Makefile`, `.github/workflows/ci.yml`, backend `NavEntry` lists — resolved at integration). Independent verification on the merged tree, same discipline as P4.

## Global Constraints (carried from standards)

Tenant from validated JWT only; response DTOs (no raw ORM); OIDC scopes for authz; feature-flag every surface (default OFF); penguin-dal for runtime (real_dal tenant tests — comma-syntax is a TypeError); rootless containers; digest-pin images; no PRC deps; 90% coverage the enforced target.

## Out of Scope

End-user desktop agent (stays `~/code/penguin`); the `feature/squawk-merger` → `release/v1.2.X` PR (user-gated, opened only after P5 completes).
