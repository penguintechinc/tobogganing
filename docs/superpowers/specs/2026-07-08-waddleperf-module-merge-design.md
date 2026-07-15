# Design Spec: Tobogganing ⨝ WaddlePerf — Module Merge, Hardening, Licensing/Flags

**Date:** 2026-07-08
**Status:** Approved (design); implementation planning to follow per phase
**Author:** Justin Bowen (with Claude Code)
**Branch:** `release/v1.2.X`

---

## 1. Context & Goal

**Tobogganing** is a SASE/ZTNA platform: a Go WireGuard headend + multi-protocol proxy (`hub-router`), a Python control plane (`hub-api`, currently py4web + PyDAL), and clients. **WaddlePerf** is a network-performance testing platform: a Go test engine (`testServer`), a Quart control plane (`unified-api`, already penguin-dal), plus browser/container/desktop clients.

We are folding WaddlePerf into tobogganing as **first-class modules** under a single **formal module framework**, and taking the opportunity to:

1. Fix the HIGH-severity security holes found in the review.
2. Get every code file under **1000 lines**.
3. Put **every feature behind a PostHog feature flag**, with **license-tier entitlement gating** and usage metering.

This is a large program, decomposed into phases; each phase gets its own implementation plan (spec → plan → implement).

---

## 2. Architecture

### 2.1 Language split (non-negotiable)

- **Go = data plane.** All live/high-throughput traffic handling stays in Go: the WireGuard headend + multi-protocol proxy (`hub-router`), any DaemonSet/node-level proxy, and the perf test engine (`testserver`). Go standards apply: Go 1.25.x, gRPC (`:50051`) preferred for service-to-service, XDP/AF_XDP build tags, non-root with only `NET_ADMIN`.
- **Python/Quart = control plane only.** Management API, orchestration, auth, portal backend, licensing/metering. No live-traffic path moves off Go.

### 2.2 Formal module framework

One Quart `core/` control plane hosts modules. Each module registers, via a `register(app, ctx)` contract:

- Quart blueprint(s) under `/api/v{major}/{module}/…`
- Portal nav + view manifest (consumed by the single React portal)
- Alembic migration revisions
- Declared PostHog flag keys (default **OFF**)
- Declared license entitlements + tier
- Health/readiness hooks

Core enforces, in order: **tenant middleware first** → scope-based authz (OIDC claims) → PostHog flag check → license entitlement check. All gates degrade gracefully to last-known-cached values when PostHog/license server is unreachable (new/never-seen flags default OFF).

### 2.3 Target repository structure

```
tobogganing/
├── core/                         # Quart app factory, module registry, auth,
│                                 # flags (PostHog), licensing/entitlements/metering,
│                                 # penguin-dal + Alembic, core/crypto key providers
├── modules/
│   ├── sase/                     # firewall, certs, network (VRF/OSPF), ports,
│   │                             # audit, security (feeds/scanner), backup, orchestrator
│   ├── waddleperf_cluster/       # perf control plane + testserver engine ownership
│   ├── waddleperf_client/        # browser + container test-client contract/endpoints
│   └── waddleperf_c2c/           # greenfield node/region-to-region testing (Professional)
├── engines/
│   ├── hub-router/               # Go WireGuard headend/proxy (data plane)
│   └── testserver/               # Go perf test engine (data plane)
├── frontend/                     # single React portal, per-module views
├── k8s/{helm,kustomize}/         # umbrella chart + overlays (alpha/beta/prod)
└── docs/, scripts/, Makefile
```

---

## 3. Merge Decisions

- **Repo import:** clean copy, fresh start (no git-history import); WaddlePerf repo archived afterward.
- **Control plane:** full migration to Quart + penguin-dal `core/`, seeded from WaddlePerf `unified-api`. SASE features ported from py4web into `modules/sase`.
- **Clients removed from tobogganing entirely:** `clients/native`, `clients/mobile`, and WaddlePerf `goClient` now live in the separate "penguin" repo.
- **Dropped on import:** WaddlePerf `managerServer/api` + `webClient/api` (legacy Flask, superseded by unified-api), `archive/`, `managerServer/frontend`.
- **Frontend:** single React portal; each module contributes views/nav; browser-test live charts rebuilt inside it.
- **Database:** unify on penguin-dal runtime + SQLAlchemy/Alembic schema authority; support postgres/mysql/sqlite via `DB_TYPE`; single `users` identity table, UUID references only; eliminate raw `sqlite3`.

---

## 4. Licensing, Flags & Billing

**Every feature gets a PostHog flag** (self-hosted via `license.penguintech.io`, default OFF), regardless of tier. Flag key convention: `tobogganing.{module}.{feature}` (e.g. `tobogganing.waddleperf_c2c.region_matrix`). License bypass on `*.penguincloud.io`, `*.penguintech.cloud`, `tobogganing.app` domains.

### 4.1 Tiers

| Tier | Features | Billing |
|------|----------|---------|
| **Community** (flag-only) | WireGuard VPN, multi-protocol proxy, basic firewall, cert+JWT auth, single-node cluster (≤5 nodes), basic perf tests, web portal, Prometheus metrics, **IDS/IPS (Suricata) + threat-intel feeds** | Free |
| **Professional** | cluster2cluster testing, >5 nodes per cluster, HA/Galera multi-master, cluster orchestration failover, encrypted S3 backup | **per seat + per node** |
| **Enterprise** | SSO/SAML/OAuth2, org-wide MFA enforcement, advanced analytics, **external KMS keys (AWS/GCP) for encryption + auth** | **per feature + per seat + per node** |

Community & Professional use only the in-app generated key; Enterprise may bring an external KMS key.

### 4.2 Metering (`core/entitlements`)

- **Seat = an identity** — a distinct authenticated principal, human user OR machine/AI/service identity. Counted uniformly (no human-vs-machine split pricing); each carries a stable UUID in the `users` identity table.
- **Node** — registered clusters/headends/testservers. *(Exact counting rule — cluster vs headend vs testserver vs deployable unit — to be finalized before implementing the usage reporter; see §7.)*
- The usage reporter aggregates active seats + nodes, and for Enterprise per-feature enablement, and reports to `license.penguintech.io` via hourly keepalive. It **never blocks** request handling — cache and retry. The `>5 nodes` gate is enforced against the licensed node allowance.

---

## 5. Phased Delivery

### Phase 0 — Security hardening + licensing consolidation (first)
Fix on the current tree so nothing critical is carried into the merge.

- **Unauthenticated cert issuance / cluster registration** (`services/hub-api/api/routes.py:11,51,70,93`): require enrollment-secret / bootstrap-token auth; never issue CA/cert to anonymous callers; scope `list_clusters` to tenant.
- **Ephemeral per-worker JWT keys** (`auth/jwt_manager.py:40-64`): load a persistent signing key from secret/env, shared across uvicorn workers, with rotation (`kid` header). Design the key provider as a **pluggable abstraction** (`core/crypto`): default in-app persisted key; Enterprise-gated AWS/GCP KMS backends for both the at-rest encryption key and the JWT signing/auth key. Same interface, backend chosen by config + entitlement.
- **Hardcoded metrics token** (`hub-router/proxy/main.go:417`): require configured token, no default; `subtle.ConstantTimeCompare`.
- **Root hub-router container** (`k8s/manifests/hub-router-deployment.yaml`, `deploy/kubernetes/headend.yaml`): drop `privileged`, `runAsUser:0`, `allowPrivilegeEscalation`; run non-root with only `NET_ADMIN` (documented `ROOT EXCEPTION (approved)` / cap exception per standards).
- **Auth correctness:** `await validate_token` (`api/routes.py:207`); replace `require_admin_role` stub + `check_security_bypass` (`security/middleware.py:82-96`); fix `run_until_complete` in a running loop (`web/auth.py:24`); stop logging the default admin password (`user_manager.py:107`); fix `refresh_token` permission downgrade.
- **Licensing consolidation:** delete divergent `hub-api/licensing/__init__.py` (v1, `SASEWADDLE_LICENSE_KEY`); standardize on `shared/licensing` v2 (`LICENSE_KEY`). Introduce `core/entitlements` = PostHog flag + license check. Add `LICENSE_KEY`, `POSTHOG_KEY`, `POSTHOG_HOST` to `.env.example`.
- **Supply-chain quick wins:** SHA-pin GitHub Actions; digest-pin Docker base images (Debian bookworm; drop Alpine/EOL `ubuntu:20.04`); `uv pip compile --generate-hashes` for Python; remove committed Go binaries + committed dev secrets; fix README merge-conflict markers + brand drift (SASEWaddle → Tobogganing, `manager`/`headend` → `hub-api`/`hub-router`).

### Phase 1 — Quart core + module framework
- Stand up `core/` Quart app factory seeded from `unified-api` (models/services/blueprints/websocket, penguin-dal connection, Alembic baseline).
- Implement the module registry + contract, tenant/scope middleware, `core/flags` (PostHog client, `feature_enabled`, cached degradation), `core/entitlements` (tier gating + metering), unified auth (persistent JWT key, bcrypt, TOTP MFA from unified-api).
- Prove the contract with one trivial registered module. No feature behavior yet.

### Phase 2 — Port SASE into `modules/sase` (≤1000-line refactor lands here)
- Convert py4web routes → Quart blueprints, split by domain:
  - `web/routes.py` (1198) → per-domain blueprints (auth, clusters/clients, firewall, vrf/network, ports, checkin).
  - `api/routes.py` (913), `security/scanner.py` (889), `security/feeds.py` (775), `backup/__init__.py` (762), `api/security_scanner_routes.py` (713) → cohesive submodules.
  - Migrate raw sqlite3 (`firewall/access_control.py`, `network/port_manager.py`, `auth/user_manager.py`) → penguin-dal.
- Register SASE flags/entitlements: IDS/IPS + threat feeds → Community/flag-only; backup/S3 + HA orchestration → Professional; SSO/MFA/advanced analytics/external KMS → Enterprise.

### Phase 3 — Import WaddlePerf cluster + client modules
- `waddleperf_cluster`: `testServer` Go engine → `engines/testserver` (add missing gRPC deps or drop gRPC to REST per standards); control-plane blueprints (orgs/OUs, devices, enrollment-secrets, tests, stats, websocket live-test). Enforce `>5 nodes` → Professional gate.
- `waddleperf_client`: browser + container client contract (enrollment secret + API key + result upload) as module endpoints; refactor `containerClient` to the shared contract.
- Merge WaddlePerf schema (org_units, users, sessions, jwt_tokens, server_keys, server/client_test_results, client_configs) into the unified Alembic schema under the single `users` identity table.

### Phase 4 — cluster2cluster (greenfield, Professional)
- New `waddleperf_c2c` module: node/region-to-region test orchestration built on `testserver` protocol handlers; region matrix from the Public-Regions concept. License-gated Professional; flag `tobogganing.waddleperf_c2c.*` default OFF.

### Phase 4b — Enterprise external KMS (AWS/GCP)
- Implement `core/crypto` key-provider abstraction: `InAppKeyProvider` (default) + `AwsKmsKeyProvider` + `GcpKmsKeyProvider`, covering the at-rest encryption key and the JWT signing/auth key from Phase 0.
- Backend selection via config (`KMS_PROVIDER=inapp|aws|gcp` + creds/key ARN), gated behind Enterprise flag `tobogganing.core.external_kms` + license entitlement; fallback to in-app key when entitlement absent. Metered as a per-feature Enterprise entitlement.

### Phase 4c — WaddlePerf feature completion (scheduler, alerting, AutoPerf, regions)
Closes the remaining WaddlePerf-parity gaps. **All async** — Quart-native handlers, async Celery tasks, one penguin-dal instance per coroutine/task; no sync DB access anywhere in this phase.

- **Server-side scheduler (`core/scheduler`)** — Celery beat with DB-backed dynamic schedules (tenant-scoped `scheduled_jobs` table via penguin-dal; Alembic migration; beat process reloads schedule from DB, no code-defined crontabs). Modules register job types through the module contract. First consumers: `waddleperf_cluster` server-initiated recurring tests (flag `tobogganing.waddleperf_cluster.scheduled_tests`, Community) and `waddleperf_c2c` recurring matrix runs (flag `tobogganing.waddleperf_c2c.recurring_runs`, Professional). The scheduler itself is core infrastructure — consumers are gated, not the mechanism.
- **Alerting + notifications** — split delivery from rules:
  - `core/notifications`: per-tenant delivery channels (SMTP email + webhook), channel config CRUD, delivery log; secrets from env/secret store, never logged.
  - `modules/waddleperf_cluster` alert rules: threshold rules (metric, comparator, threshold, evaluation window) evaluated async on result ingest and on scheduler sweep. Basic email alerts → Community (`tobogganing.waddleperf_cluster.alerts`); webhook routing + escalation policies → Professional (`tobogganing.waddleperf_cluster.alert_routing`).
- **AutoPerf tiered monitoring (Professional)** — flag `tobogganing.waddleperf_cluster.autoperf`. Tier definitions (T1 light: ping/HTTP; T2: traces + DNS + TCP; T3: full speedtest + traceroute); per-device/target escalation state machine driven by alert-rule breaches, de-escalating after N consecutive clean cycles; executes via the scheduler; results feed stats + alerting. Metered as a per-feature entitlement.
- **Region/node registry (Professional)** — flag `tobogganing.waddleperf_c2c.regions`. Public/private test-node catalog (region, provider, visibility, health status), CRUD + scheduler-driven health sweep; c2c matrix orchestration can select endpoints by region. Registered nodes count toward node metering.

Internal sequencing: scheduler → alerting/notifications → AutoPerf (depends on both) → region registry (independent, may run in parallel).

### Phase 5 — Single portal frontend
- One React app (tobogganing portal) with per-module view manifests; rebuild browser-test live charts (websocket + recharts). Drop `managerServer/frontend`; retire `webClient/frontend` after parity. Role-based nav (Admin/Reporter/Viewer); shared `@penguintechinc/react-*` components. Includes views for Phase 4c features: alert rules + notification channels, AutoPerf tier status, region/node registry.

### Phase 6 — Remaining >1000-line files + hardening finish
- `shared/react_libs/src/components/FormModalBuilder.tsx` (1081) → split types / `buildFieldSchema` / theming / field-renderer subcomponents.
- `hub-router/proxy/main.go` (1326) → bootstrap, HTTP handlers, TCP proxy, UDP proxy, dynamic ports; de-duplicate repeated JWT/target packet-parse helpers.
- Re-enable the two disabled Go tests; raise coverage toward 90%; TLS `MinVersion` 1.2 on Go `tls.Config`; default-deny NetworkPolicy per namespace.

---

## 6. Reuse & References

- **Reuse:** `shared/licensing/python_client.py` (`@requires_feature`, `check_feature`, cache) + `client.go` / `middleware.go` as the licensing base; WaddlePerf `services/unified-api/` app structure as the Quart core seed.
- **Skills:** `integrating-license-server` (PostHog + entitlement wiring), `migrating-to-penguin-libs`, `implementing-database-patterns`.
- **Standards:** Quart + penguin-dal + Alembic; `@dataclass(slots=True)`; Debian bookworm digest-pinned images; securityContext everywhere; API `/api/v{major}` + `api_version` gRPC field.

---

## 7. Open Item (finalize during implementation planning)

- **Node counting rule for metering:** is a billable "node" a cluster, a headend, a testserver, each counted separately, or the deployable cluster unit? (Seat is settled: seat = a distinct identity, human or machine/AI.)

---

## 8. Verification (per phase)

- **Phase 0:** security scans (`make test-security` — bandit, gosec, gitleaks, trivy) clean; auth unit tests prove cert issuance rejects anonymous callers and JWTs validate across workers.
- **Framework/modules:** `make test` unit+integration on a penguin-dal test DB; module-registry integration test asserts each module's flags default OFF, the license gate returns 402 without entitlement, and cached-value fallback works when license/PostHog is unreachable.
- **Phase 4c:** real-DAL integration tests for schedule persistence + due-job evaluation; alert-rule breach produces a recorded notification (transport mocked at SMTP/webhook boundary only); AutoPerf escalation and de-escalation state transitions; region CRUD + matrix region filtering; all 4c flags default OFF and Professional features return 402 without entitlement.
- **End-to-end:** `make smoke-test` on a clean alpha cluster (Kustomize `local-alpha`); browser perf-test flow + WireGuard connect flow exercised; `make lint` + a ≤1000-line check across changed files.
- **Coverage:** ≥90% gate on touched services.
