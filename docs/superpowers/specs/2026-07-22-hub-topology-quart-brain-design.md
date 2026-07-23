# Tobogganing — `hub-*` Topology + Quart Brain Consolidation (Target Architecture)

**Status:** Draft for review · **Date:** 2026-07-22 · **Supersedes direction of:** `2026-07-08-waddleperf-module-merge-design.md` (the merge stands; this re-decomposes the result into the `hub-*` service family and finalizes the control-plane framework).

## 1. Why

The WaddlePerf merge produced a working control-plane skeleton (`core/`, Quart) but left the platform in a half-state: a stale py4web `services/hub-api` still carries a few data-plane endpoints, VPN termination and cluster-routing are conflated in one Go service, licensing/metering are stubbed or unwired, and the end-user clients live in-repo. This spec fixes the architecture: **one Quart brain (`hub-api`) + a family of `hub-*` data-plane services + a clean client split**, so each of the three connectivity axes (node↔node, cluster↔cluster, user/agent↔cluster) has one clear owner.

## 2. Target architecture

| Service | Role | Today | Language |
|---|---|---|---|
| **hub-api** | Central brains: control plane, config, auth, licensing/flags/metering, orchestration, portal backend, all module control-planes (SASE + WaddlePerf) | `core/` (Quart) — **rename to `hub-api`**; py4web `services/hub-api` retired | Python/Quart + penguin-dal |
| **hub-router** | Cluster-to-cluster (c2c) data plane **and** intra-cluster node relay (hub-and-spoke) | `services/hub-router` (split: routing kept, VPN termination removed) | Go (existing — maintain) |
| **hub-client** | VPN concentrator — **WireGuard and OpenZiti coexisting**, selected per end-user | *new* (VPN-termination role split out of hub-router) | **Rust** (new + security-sensitive + high-perf net — Go phase-out) |
| **hub-perf** | WaddlePerf test receivers (perf data plane) | `engines/testserver` — rename | Go (existing — maintain) |

**Clients (two distinct connect paths):**
- **Node agents → hub-routers** (intra-cluster + relayed c2c):
  - **client-k8s** = `clients/docker` — DaemonSet-style containerized node agent. **Stays in this repo, maintained here.**
  - **client-node** = *new* agent for hypervisors / bare hosts **outside** k8s that need to connect in.
- **End-user desktop → hub-client** (VPN):
  - **penguin** = thick desktop agent, lives in the separate **penguin modular desktop framework** project. `clients/native` + `clients/mobile` relocate there.

## 3. Connectivity axes (who owns what)

- **A · node↔node (intra-cluster):** each node agent (client-node native / client-k8s DaemonSet) connects to the **hub-routers** in hub-and-spoke; no direct peer mesh. Node-to-node reachability is realized through the hub-routers, not raw WireGuard peer-to-peer. **Production requires ≥2 hub-routers; a single hub-router MUST emit a "not production ready" warning** (enforced in hub-api config validation).
- **B · cluster↔cluster (c2c):** **hub-routers** carry inter-cluster traffic. The existing `waddleperf_c2c` perf matrix measures across these; the c2c *data path* is the hub-router's job.
- **C · user/agent↔cluster/service:** end-user **penguin** agent → **hub-client** concentrator. **Per-end-user** choice of WireGuard vs OpenZiti: the selection is configured in **hub-api** and shipped to the penguin agent as an attached config file — not a global toggle. WireGuard and OpenZiti coexist at hub-client.

## 4. Key rules & standards

- **Brain framework:** Quart + penguin-dal (runtime) + SQLAlchemy/Alembic (schema). py4web is fully sunset — `services/hub-api` is legacy to retire, not extend.
- **New data-plane services default to Rust** (Go phase-out; `hub-client` is both new *and* security-sensitive — VPN/crypto/auth — so Rust or Python only, never Go). Existing Go services (`hub-router`, `hub-perf`) are maintained under Go standards, not rewritten on sight.
- **Per-service DB accounts**, single `users` identity table, UUID cross-refs.
- **Every feature behind a PostHog flag** (`tobogganing.{module}.{feature}`, default OFF) **+ license entitlement** where tiered. The license gate must call the real client (fixes the `_is_licensed_for_tier` → `False` stub).
- **Service-to-service:** gRPC preferred (REST fallback); SPIFFE/SPIRE or OIDC machine JWTs, never static keys.
- **REST surfaces publish OpenAPI** (`openapi/v{major}.yaml`), login-only public doc + auth-gated full spec.
- **≥2 replicas / HA in production**; securityContext everywhere; digest-pinned images.

## 5. Current → target migration map

- `core/` → **rename to `hub-api`** (module registry, entitlements/flags, `core/crypto` KMS, metering, scheduler, `modules/*` all move under the new name).
- `services/hub-api` (py4web) → **delete**, after porting its remaining endpoints into the Quart brain: `GET /api/v1/firewall/rules`, `GET /api/v1/headend/<id>/ports`, and the flat client/auth paths the Go data plane calls.
- `core/modules/sase` → **keep** as the Quart SASE control-plane; it is the duplicate-of-record once py4web dies.
- `services/hub-router` → **split**: keep c2c + node-relay routing as `hub-router`; extract VPN termination into new `hub-client`.
- `engines/testserver` → **rename to `hub-perf`**.
- `clients/docker` → **keep** as `client-k8s`. `clients/native` + `clients/mobile` → **relocate** to penguin project. New **client-node** agent for non-k8s hosts.

## 6. Phasing

Each phase gets its own spec + plan at execution time; this is the umbrella.

- **P-A · Brain consolidation (unblocks everything).** Port py4web-only endpoints into the Quart brain; wire the license gate to the real client; delete `services/hub-api`; rename `core/`→`hub-api`; add the ≥2-hub-router config-validation warning. Deliverable: one Quart brain, py4web gone, licensing functional.
- **P-B · Data-plane decomposition.** Split `services/hub-router` → `hub-router` (c2c + node relay) + `hub-client` (VPN); rename `testserver`→`hub-perf`; re-point the Go data plane at the brain's ported flat paths. (Stashed WireGuard peer-sync WIP lands in `hub-client` here.)
- **P-C · hub-client VPN (WireGuard + OpenZiti coexist).** OpenZiti concentrator alongside WireGuard; per-end-user selection driven by the hub-api-authored config file consumed by penguin.
- **P-D · Clients.** New `client-node` agent (non-k8s hosts → hub-routers); maintain `client-k8s`; relocate native/mobile to penguin.
- **P-E · Resume folded-in fixes** in their final homes: metering wiring (#6), rate-limiting on perf/live-test (#11), OpenAPI specs (#8), cluster failover/re-homing (#10), gRPC engine path (#13), real c2c connectivity depth (#9).

## 7. Already landed (keep)

- `#12` (committed `4bfacd8`): `require_scope("tests:write")` on both live-test routes; AutoPerf tier-3 no longer calls the non-existent `speedtest` engine route; guard test added.

## 8. Open decisions (resolve at each phase's own spec)

1. **Brain name rename mechanics** — `core/`→`hub-api` as a directory/module rename vs. a new package; import-path churn across ~800 tests. (P-A)
2. **client-node reuse** — greenfield vs. adapt existing `clients/native` Go before it relocates. (P-D)
3. **hub-client language confirm** — Rust recommended (new + security-sensitive); confirm no Go-only OpenZiti/WireGuard dependency forces otherwise. (P-B/P-C)
4. **OpenZiti integration depth** — SDK-embedded vs. sidecar concentrator; identity issuance vs. SPIFFE. (P-C)
5. **hub-router relay protocol** — how node↔node and c2c traffic is carried/authenticated through the routers. (P-B)
6. **Metering "node" unit** — does a node = a hub-router, a hub-client, a hub-perf, or the deployable cluster? (carried from the merge spec; P-A/P-E)

## 9. Verification (per phase)

- P-A: security scans clean; brain boots as `hub-api`; py4web gone; license gate returns 402 without entitlement and passes with it (no monkeypatch); ≥2-hub-router warning fires on 1. Full suite green after import-path rename.
- P-B/C/D: each new/split service builds in-container, has health/readiness, securityContext, ≥90% coverage; end-to-end connect flows (node→hub-router, penguin→hub-client WG and OpenZiti) exercised on clean alpha.
- Cross-seam integration tests (the gap that hid every prior break): client→brain→data-plane and data-plane→brain, not module-isolated with a monkeypatched license.
