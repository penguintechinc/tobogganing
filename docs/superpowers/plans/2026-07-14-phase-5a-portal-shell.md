# Phase 5a — Portal Shell (Backend Auth/Manifest + React App Skeleton) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The tobogganing portal foundation: browser auth endpoints + a flag-filtered module manifest endpoint on core, and a greenfield `portal/` React app — login (with MFA), manifest-driven sidebar nav, role-aware shell, three anchor views (devices, tests, stats), Express container. Full view parity lands in 5b.

**Architecture:** Core gains `POST /api/v1/auth/{login,refresh,logout}` wired to the existing (already-tested) `AuthService`, and `GET /api/v1/portal/manifest` exposing each registered module's `NavEntry` list plus evaluated flag states — the portal renders ONLY what the manifest says is enabled, so UI gating always tracks backend gating. The portal is Vite + React 18 + TypeScript with published `@penguintechinc/react-libs` / `@penguintechinc/react-aaa` components, TanStack Query for all server state, one axios client with token-refresh interceptors, and an Express runtime container proxying `/api` + `/ws`.

**Tech Stack:** React 18.3.x, Vite 5, TypeScript (ES2022/bundler), react-router 6, @tanstack/react-query 5, axios, TailwindCSS 4, recharts (stats), lucide-react (NavEntry icon names are lucide slugs), Jest + React Testing Library (90% threshold), Playwright (`outputDir=/tmp/playwright-tobogganing`), Express on node:26-bookworm-slim.

## Global Constraints

- Exact npm versions (no `^`/`~`); commit `package-lock.json`; `npm ci` in Docker/CI.
- Backend: same constraints as prior phases (canonical async DAL, real_dal + HTTP tests, type hints, ≤1000 lines, tenant fail-closed). Portal files ≤5000 chars per frontend rules — split components.
- Console logging format `[ComponentName] Action { sanitizedData }`; never log tokens/passwords/full emails.
- Dark theme slate+gold per `docs/standards/UI_DESIGN.md` CSS variables; mobile-responsive (sidebar `hidden lg:block` + hamburger).
- ESLint + Prettier pass; jest `coverageThreshold` 90 (lines/branches/functions/statements) on `portal/src`.
- Auth failure semantics: 401 invalid credentials (uniform message, no user-enumeration), 200 `{mfa_required: true}` without tokens when MFA needed.
- Branch: `feature/phase-5a-portal-shell` off `feature/phase-4c-b-autoperf-regions` (worktree `~/code/tobogganing-wt-4c-a`). Workers edit-and-test only; orchestrator commits.

---

### Task 1 (backend): Browser auth routes

**Files:** `core/api/__init__.py` + `core/api/auth_routes.py` (new core-level blueprint, registered directly in `create_app` — NOT a module contract; auth is core infrastructure like `/health`); tests `core/tests/test_portal_auth_api.py` (real_dal + HTTP).

**Interfaces:**
- Blueprint `auth_bp` url_prefix `/api/v1/auth` registered in `core/app.py` after CORS setup.
- `POST /login` body `{email, password, mfa_token?}` → `AuthService(db, key_provider, config).authenticate(email, password, mfa_token)` (verify constructor signature in `core/auth/service.py` and match). Responses: success → 200 `{access_token, refresh_token, expires_in: 3600, token_type: "Bearer"}`; `mfa_required` → 200 `{mfa_required: true}` (no tokens); failure → 401 `{"error": "Invalid credentials"}` (uniform; do not distinguish unknown-user vs bad-password). 400 on missing fields. Never log password/mfa_token; log email masked (`u***@domain`).
- `POST /refresh` body `{refresh_token}` → `refresh_access_token` → 200 tokens / 401.
- `POST /logout` body `{refresh_token}` → revoke via the existing revocation path in AuthService (find it; if absent, delete the refresh_tokens row directly) → 204.
- Key provider comes from `current_app.config["KEY_PROVIDER"]`; db from `get_db()`.

**Tests:** login success returns decodable token with tenant claim; wrong password → 401 uniform body; unknown email → identical 401 body; MFA-enabled user without token → `{mfa_required: true}`, with valid TOTP → tokens (reuse the MFA fixtures from `core/tests/test_auth_service_realdal.py`); refresh rotates access token; logout then refresh → 401; missing fields → 400.

### Task 2 (backend): Portal manifest endpoint

**Files:** `core/api/portal_routes.py`; register in `create_app`; tests `core/tests/test_portal_manifest_api.py`.

**Interfaces:**
- `GET /api/v1/portal/manifest` — requires valid Bearer token (use `require_tenant` middleware pattern). Response:
```json
{"modules": [{"name": "waddleperf_cluster",
              "nav": [{"label": "Devices", "path": "/api/v1/waddleperf_cluster/devices", "icon": "laptop"}],
              "flags": {"tobogganing.waddleperf_cluster.alerts": false, ...}}],
 "role": "<claims role or 'viewer'>",
 "meta": {...}}
```
- Iterate `current_app.registry` modules (add a `modules()` accessor to ModuleRegistry if none exists); evaluate each declared flag via `feature_enabled(module, feature)` parsing the flag key's `{module}.{feature}` tail; unauthenticated → 401/403.

**Tests:** 403 without token; with token → registered modules present with nav entries; flags evaluated (monkeypatch `_flag_on` to enable one flag and assert true/false split); role surfaces from claims.

### Task 3 (portal): Scaffold + auth + shell

**Files:** `portal/` — `package.json` (exact versions), `vite.config.ts` (dev proxy `/api`→`http://localhost:8080`), `tsconfig.json`, `tailwind.config`/`src/styles/index.css` (UI_DESIGN.md variables), `.eslintrc`/`.prettierrc`, `src/main.tsx`, `src/App.tsx`, `src/api/client.ts`, `src/api/auth.ts`, `src/context/AuthContext.tsx` (wrap `@penguintechinc/react-aaa` AuthProvider), `src/pages/LoginPage.tsx` (LoginPageBuilder wired to `/api/v1/auth/login` incl. MFA), `src/components/Shell.tsx` (SidebarMenu from manifest + role, ConsoleVersion, hamburger <lg), `src/hooks/useManifest.ts` (TanStack Query on `/api/v1/portal/manifest`, staleTime 5m), `src/pages/DashboardPage.tsx`, route table mapping module nav → UI routes `/m/{module}/{slug(label)}` with ProtectedRoute.
- API client: axios instance baseURL `/api/v1`, request interceptor injects Bearer, response interceptor on 401 → single-flight refresh via `/auth/refresh` then retry once, else redirect `/login`. Tokens in memory + `sessionStorage` (documented tradeoff), never logged.
- Nav filtering: a nav entry renders only if its module has ANY enabled flag relevant to it — MVP rule: render module section if the module appears in manifest; per-view flag gating refined in 5b. Role `viewer` hides mutation buttons (shared `useRole()` hook).

**Tests (Jest+RTL):** client interceptor injects token; 401 triggers one refresh then retry; LoginPage submits and stores tokens, shows MFA step on `mfa_required`; Shell renders sidebar entries from a mocked manifest and hides admin-only items for viewer; router redirects unauthenticated → /login.

### Task 4 (portal): Anchor views — devices, tests, stats

**Files:** `src/pages/waddleperf/DevicesPage.tsx`, `TestsPage.tsx`, `StatsPage.tsx` + `src/api/waddleperf.ts` + shared `src/components/DataTable.tsx` (sortable, paginated, `data-testid`s).
- Devices: table (name, org unit, status, last_heartbeat) from `GET /waddleperf_cluster/devices`.
- Tests: table from `GET /waddleperf_cluster/tests` + row expand for result metrics.
- Stats: summary cards + recharts line chart from `GET /waddleperf_cluster/stats/summary` and `/stats/trends`.
- All via TanStack Query hooks; loading/error/empty states mandatory; viewer role read-only.

**Tests:** each page renders rows from mocked API, shows empty + error states; table sort fires; chart renders with mocked trend data.

### Task 5 (portal): Express container + smoke tests

**Files:** `portal/server.js` (Express: static `dist/`, `/api` + `/ws` proxy via `http-proxy-middleware` with ws:true, SPA fallback, `/healthz`), `portal/Dockerfile` (multi-stage node:26-bookworm-slim digest-pinned, `npm ci` + build → runtime with non-root user + native-node healthcheck), `portal/playwright.config.ts` (`outputDir: '/tmp/playwright-tobogganing'`), `portal/e2e/smoke.spec.ts` (login page renders + validates + rejects bad creds against a mocked API route; protected route redirects; shell renders nav), Makefile targets (`portal-dev`, `portal-build`, `portal-test`).

### Task 6: Verification + PR

- Backend: full pytest suite green. Portal: `npm run lint`, `npm test` (90% threshold enforced), `npm run build`, Playwright smoke (cleanup `/tmp/playwright-tobogganing` after, pass or fail).
- Update `docs/SCHEDULER.md`? No — new `docs/PORTAL.md` (dev setup, env, proxy, auth flow, manifest contract). Memory update. Push; stacked PR base `feature/phase-4c-b-autoperf-regions`.

## Self-Review Notes
- Manifest-driven nav means 5b views slot in without shell changes — the module framework's UI contract is proven here. ✔
- Auth endpoints reuse the tested AuthService; no new auth logic invented. ✔
- Anti-enumeration 401, masked email logging, tokens never logged. ✔
