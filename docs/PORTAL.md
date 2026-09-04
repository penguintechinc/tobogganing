# Tobogganing Portal

Single React portal for all modules — served by its own Express container, driven by the core module manifest.

## Architecture

- **Manifest-driven**: on login the portal fetches `GET /api/v1/portal/manifest` — every registered module's nav entries (`label`, `path`, `icon` = lucide slug) plus its evaluated feature-flag states and the caller's role. The sidebar and routes render from this, so UI gating always tracks backend flag/entitlement gating; new modules appear without portal changes.
- **Auth**: `POST /api/v1/auth/login` (email/password, TOTP MFA step on `{"mfa_required": true}`), `/auth/refresh-token`, `/auth/logout`. Uniform 401s (no user enumeration). Tokens live in memory + sessionStorage; the axios client injects Bearer and performs a single-flight refresh-and-retry on 401. (`/auth/refresh` is a distinct, separately-routed endpoint reserved for machine/headend token refresh — see `docs/architecture/headend-machine-jwt-contract.md`.)
- **Routes**: `/login` public; everything else behind ProtectedRoute. Module views mount at `/m/{module}/{slug(label)}`; unimplemented views render a placeholder.
- **Roles**: `useRole()`/`canWrite()` from JWT claims — `viewer` sees read-only UI.

## Development

```bash
make portal-dev      # vite dev server on :5173, /api proxied to :8080
make portal-test     # eslint + jest (90% coverage gate enforced)
make portal-build    # npm ci + production build
make portal-e2e      # playwright smoke suite (built app + mock core API)
```

Backend for local dev: run core on `:8080` (`hypercorn core.app:create_app()` per core docs). The vite proxy forwards `/api` (websockets included).

## Runtime container

`portal/Dockerfile` — multi-stage `node:26-bookworm-slim` (digest-pinned), non-root `appuser`, native-node healthcheck on `/healthz`. `server.js` serves `dist/`, proxies `/api/*` (+ websocket upgrade for `/api/v1/waddleperf_cluster/live-test`) to `CORE_API_URL` (default `http://localhost:8080`), SPA-falls-back to `index.html`. Port 3000 (`PORT` env).

## Stack

React 18 + TypeScript (Vite 5), TanStack Query 5 (all server state), react-router 6, TailwindCSS 4 (CSS-first config in `src/styles/index.css`, dark slate+gold theme), recharts (lazy-loaded), lucide-react icons. Exact-pinned deps, `package-lock.json` committed, `npm ci` in CI/Docker.

Note: `@penguintechinc/react-libs` / `react-aaa` had peer-dep conflicts at scaffold time; thin local equivalents live in `src/` with TODOs — revisit in Phase 5b.

## Testing

- **Jest + RTL**: 90% threshold (lines/branches/functions/statements) enforced in `jest.config.js`; interceptors are unit-tested by invoking handlers directly.
- **Playwright** (`portal/e2e/`): smoke suite boots the built app via `server.js` against a mock core API (`e2e/mock-api.js`, port 3001); artifacts in `/tmp/playwright-tobogganing`, cleaned after every run.

## Views

Full module parity as of Phase 5b:

- **waddleperf_cluster**: Devices, Tests (expandable results), Stats (summary + trends), Alerts (rules/channels/events tabs, Professional upsell on webhook channels), Scheduled Tests, AutoPerf (policies + tier state), Live Test (WebSocket stream → real-time chart; JWT passed via the `Sec-WebSocket-Protocol` handshake header — `new WebSocket(url, ["tobogganing-bearer", token])` — the one header browsers can set on a WS handshake, keeping the token out of the URL and access logs).
- **waddleperf_c2c**: Nodes (endpoints), Runs with the source×dest matrix grid (colored by loss/latency), Recurring jobs (matrix_run/node_health), Regions (aggregate cards + redacted public-node table).
- **sase**: Clusters, Clients, Status.

New modules appear automatically: register nav in the module contract and add a page to the module's view map in `src/routes/` — the manifest does the rest.
