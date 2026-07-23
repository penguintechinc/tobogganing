# Tobogganing — `hub-*` Topology + Quart Brain Consolidation (Target Architecture)

**Status:** Draft for review · **Date:** 2026-07-22 · **Supersedes direction of:** `2026-07-08-waddleperf-module-merge-design.md` (the merge stands; this re-decomposes the result into the `hub-*` service family and finalizes the control-plane framework).

## 1. Why

The WaddlePerf merge produced a working control-plane skeleton (`core/`, Quart) but left the platform in a half-state: a stale py4web `services/hub-api` still carries a few data-plane endpoints, VPN termination and cluster-routing are conflated in one Go service, licensing/metering are stubbed or unwired, and the end-user clients live in-repo. This spec fixes the architecture: **one Quart brain (`hub-api`) + a family of `hub-*` data-plane services + a clean client split**, so each of the three connectivity axes (node↔node, cluster↔cluster, user/agent↔cluster) has one clear owner.

## 2. Target architecture

| Service | Role | Today | Language |
|---|---|---|---|
| **hub-api** | Central brains: control plane, config, auth, licensing/flags/metering, orchestration, portal backend, all module control-planes (SASE + WaddlePerf) | `core/` (Quart) — **rename to `hub-api`**; py4web `services/hub-api` retired | Python/Quart + penguin-dal |
| **hub-router** | Cluster-to-cluster (c2c) transport + node relay. **Lightweight only** — basic policy + authentication checks; deep inspection lives at the Inspection Points, not here | `services/hub-router` (split: routing kept, VPN termination removed) | Go (existing — maintain) |
| **hub-client** | The **front door** — SASE ingress Inspection Point terminating agent (**primary** WG/OpenZiti, **fallback** OpenVPN-443/IPsec-MOBIKE), contractors, clientless (*future*, Apache Guacamole) & vendor/customer S2S IPsec. Customized proxy (Envoy or custom Rust/Go) with monitoring + rules; taps Suricata/Zeek/Arkime (see §11) | *new* (split out of hub-router) | Proxy foundation TBD — Envoy+Rust *or* custom Rust/Go (§8) |
| **bridge-router** | **Enterprise-tier.** Network transit/interconnect hub + SASE PEP (GCP NCC / AWS TGW-analogous, but with inline inspection) — bridges the fabric to external networks / VPCs / sites & agentless services; same Envoy + sensor-tap design as hub-client (§11) | *new* | Proxy foundation TBD — Envoy+Rust *or* custom Rust/Go (§8) |
| **hub-perf** | WaddlePerf test receivers (perf data plane) | `engines/testserver` — rename | Go (existing — maintain) |

**Management overlays (thin, no logic of their own):** `hub-cli` and `hub-webui` sit on top of `hub-api` for configuration, management, and review. `hub-webui` is today's React portal; `hub-cli` is new. Neither holds business logic — both are clients of the hub-api API.

**Clients (two distinct connect paths):**
- **Node agents → hub-routers** (intra-cluster + relayed c2c):
  - **client-k8s** = `clients/docker` — DaemonSet-style containerized node agent. **Stays in this repo, maintained here.**
  - **client-node** = *new* agent for hypervisors / bare hosts **outside** k8s that need to connect in.
- **End-user desktop → hub-client** (VPN):
  - **penguin** = thick desktop agent, lives in the separate **penguin modular desktop framework** project. `clients/native` + `clients/mobile` relocate there.

## 3. Connectivity axes (who owns what)

- **A · node↔node (network layer):** each node agent (client-node native / client-k8s DaemonSet) connects to the **hub-routers** in hub-and-spoke; no direct peer mesh. hub-routers do **lightweight policy + auth only**. **Production requires ≥2 hub-routers; a single hub-router MUST emit a "not production ready" warning** (hub-api config validation). NOTE: **intra-cluster k8s east-west *security* is out of scope** — Cilium NetworkPolicy / admission control / Tetragon, configured in the **Gough** project. Tobogganing owns the *true network / overlay* layer, not in-cluster pod security.
- **B · cluster↔cluster (c2c):** **hub-routers** carry inter-cluster traffic (light policy/auth). The existing `waddleperf_c2c` perf matrix measures across these; the c2c *data path* is the hub-router's job.
- **C · user/agent↔cluster/service:** **hub-client is the front door** — the universal ingress Inspection Point (§11) for all inbound access: penguin agent (**primary** WireGuard/OpenZiti; **fallback** OpenVPN-over-HTTPS/TCP-443 or IPsec IKEv2/MOBIKE when the primaries are blocked — per-end-user config from hub-api, shipped as a config file), contractors, clientless (*future*, Apache Guacamole), and vendor/customer site-to-site IPsec. Everything is inspected here before entering the fabric.
- **Egress / bridge:** agentless targets (services, external/legacy networks) are reached via **bridge-router**, the second Inspection Point (§11); agent-equipped nodes reach hub-routers directly.

## 4. Key rules & standards

- **Brain framework:** Quart + penguin-dal (runtime) + SQLAlchemy/Alembic (schema). py4web is fully sunset — `services/hub-api` is legacy to retire, not extend.
- **Inspection Points (`hub-client`, `bridge-router`) = customized Envoy** — pinned upstream data plane + **Rust** custom filters/ext_proc for the security-sensitive rules/verdict path (Go phase-out; never custom Go). Existing Go services (`hub-router`, `hub-perf`) maintained under Go standards, not rewritten on sight.
- **Scope boundary:** tobogganing owns the *true network / overlay layer*. **Intra-cluster k8s east-west security** (Cilium NetworkPolicy, admission control, Tetragon runtime security) is **out of scope — owned by the Gough project.** hub-routers do only lightweight in-fabric policy + auth.
- **Per-service DB accounts**, single `users` identity table, UUID cross-refs.
- **Every feature behind a PostHog flag** (`tobogganing.{module}.{feature}`, default OFF) **+ license entitlement** where tiered. The license gate must call the real client (fixes the `_is_licensed_for_tier` → `False` stub).
- **Service-to-service:** gRPC preferred (REST fallback); SPIFFE/SPIRE or OIDC machine JWTs, never static keys.
- **Config distribution:** every client, hub, and bridge fetches its configuration from `hub-api` via **gRPC** — hub-api is the single source of truth; nothing is configured locally.
- **Enrollment:** clients and hubs join via temporary, single-use **connect tokens** minted by hub-api (Kubernetes-join-analogous). End-user clients operate in hostile territory — see §10.
- **REST surfaces publish OpenAPI** (`openapi/v{major}.yaml`), login-only public doc + auth-gated full spec.
- **≥2 replicas / HA in production**; securityContext everywhere; digest-pinned images.

## 5. Current → target migration map

- `core/` → **rename to `hub-api`** (module registry, entitlements/flags, `core/crypto` KMS, metering, scheduler, `modules/*` all move under the new name).
- `services/hub-api` (py4web) → **delete**, after porting its remaining endpoints into the Quart brain: `GET /api/v1/firewall/rules`, `GET /api/v1/headend/<id>/ports`, and the flat client/auth paths the Go data plane calls.
- `core/modules/sase` → **keep** as the Quart SASE control-plane; it is the duplicate-of-record once py4web dies.
- `services/hub-router` → **split**: keep lightweight c2c + node-relay routing as `hub-router`; extract VPN termination + client-edge inspection into new `hub-client` (Inspection Point).
- **New `bridge-router`** (Inspection Point) — egress bridge to agentless services / external networks; shares hub-client's Envoy + sensor-tap design (§11).
- `engines/testserver` → **rename to `hub-perf`**.
- `clients/docker` → **keep** as `client-k8s`. `clients/native` + `clients/mobile` → **relocate** to penguin project. New **client-node** agent for non-k8s hosts.

## 6. Phasing

Each phase gets its own spec + plan at execution time; this is the umbrella.

- **P-A · Brain consolidation (unblocks everything).** Port py4web-only endpoints into the Quart brain; wire the license gate to the real client; delete `services/hub-api`; rename `core/`→`hub-api`; add the ≥2-hub-router config-validation warning. Deliverable: one Quart brain, py4web gone, licensing functional.
- **P-B · Data-plane decomposition.** Split `services/hub-router` → `hub-router` (c2c + node relay) + `hub-client` (VPN); rename `testserver`→`hub-perf`; re-point the Go data plane at the brain's ported flat paths. (Stashed WireGuard peer-sync WIP lands in `hub-client` here.)
- **P-C · Inspection Points (hub-client + bridge-router).** Customized Envoy data plane + Rust filters/ext_proc; WireGuard + OpenZiti concentration at hub-client (per-end-user selection via the hub-api-authored config file); Suricata/Zeek/Arkime tap + alert/block feedback at both. See §11.
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
7. **End-user first-connect auth** — is a valid connect token sufficient, or is interactive OIDC/MFA additionally required so a stolen config alone can't join? (P-C/§10)
8. **Inspection-Point customization mechanism** — proxy-wasm (Rust) filter vs Rust ext_authz/ext_proc sidecar vs native C++ Envoy filter, for the rules/verdict path. (P-C/§11)
9. **Sensor tap format** — Envoy L7 tap vs an L3/L4 packet mirror the sensors (Suricata/Zeek/Arkime) natively consume. (P-C/§11)
10. **bridge-router placement** — vs hub-router c2c transport; which targets route via bridge-router (external/VPC/agentless) vs directly to hub-routers (agent nodes). (P-B/P-C)

## 9. Verification (per phase)

- P-A: security scans clean; brain boots as `hub-api`; py4web gone; license gate returns 402 without entitlement and passes with it (no monkeypatch); ≥2-hub-router warning fires on 1. Full suite green after import-path rename.
- P-B/C/D: each new/split service builds in-container, has health/readiness, securityContext, ≥90% coverage; end-to-end connect flows (node→hub-router, penguin→hub-client WG and OpenZiti) exercised on clean alpha.
- Cross-seam integration tests (the gap that hid every prior break): client→brain→data-plane and data-plane→brain, not module-isolated with a monkeypatched license.

## 10. Enrollment & bootstrap security (connect tokens)

**Threat model:** the end-user client operates in **hostile territory** — compromised public Wi-Fi, hostile DNS, on-path attackers. Bootstrap must survive capture and MITM.

- **Connect tokens (k8s-join-analogous):** hub-api mints **temporary, short-TTL, single-use, revocable** connect tokens — a distinct class per enrollee (end-user client, hub-router, bridge-router, node agent). The token authorizes **enrollment only**, never data access — like `kubeadm` bootstrap tokens.
- **End-user config file (.ovpn-analogous):** hub-api emits a file with connect endpoint(s), transport methods — **primary** (`wg` | `ziti`) plus **fallback** (`openvpn` over 443 | `ipsec` MOBIKE) tried when primaries are blocked — a **pinned server/CA trust anchor**, and the initial connect token. **No long-lived secret** — bootstrap material + trust anchor only.
- **Bootstrap exchange (k8s TLS-bootstrap-analogous):** client → hub-client over TLS 1.3 (server verified against the pinned anchor) → token **one-time-consumed** → hub issues **short-lived, rotating** credentials (WireGuard peer config or Ziti identity + client cert/JWT) → tunnel established. Mirrors bootstrap-token → CSR → CA-signed cert.
- **Hostile-territory hardening:** the pinned anchor defeats MITM / hostile DNS; single-use + short TTL means a captured token grants at most one quickly-revoked enrollment; nothing sensitive in URLs/cleartext; issued creds are short-lived + centrally revocable.
- **Enrollment varies by modality** (hub-client is the front door for all of them): **agent** clients use the connect-token + config-file flow above; **clientless** (*future*, Apache Guacamole) is interactive OIDC/IdP at the browser, no token file; **vendor/customer site-to-site IPsec** uses IKE (PSK or cert) per configured peer — not connect tokens.

## 11. Inspection Points (hub-client + bridge-router)

Two services share one archetype — a **customized Envoy proxy** that inspects and enforces SASE policy on traffic passing through it:

- **Data plane:** Envoy (pinned upstream) + monitoring + a rules engine; policy/rules pulled from hub-api over gRPC.
- **Sensor tap:** the data path is mirrored to network-security sensors — **Suricata** (IDS/IPS), **Zeek** (NSM), **Arkime** (session capture) — which analyze and return **alerts** and **block verdicts**.
- **Enforcement loop:** verdicts return in-line (Envoy ext_authz / dynamic deny) to allow/block; Zeek/Arkime add monitoring + retrospective capture.
- **Custom logic:** Envoy core pinned upstream (C++); security-sensitive custom logic in **Rust** — proxy-wasm (Rust) filters and/or a Rust ext_authz/ext_proc sidecar. No custom Go.
- **Ties to** existing `core/modules/sase/security` (Suricata + threat feeds + scanner, Community tier): hub-api owns rules/feeds/config; the Inspection Points enforce + tap.

Instances:
- **hub-client** — ingress Inspection Point at the *client edge*. Terminates **all inbound access modalities**: penguin **agent** (**primary** WireGuard/OpenZiti; **fallback** OpenVPN-443 / IPsec-MOBIKE for restrictive networks), **contractors**, **clientless** (*future* — Apache Guacamole HTML5 RDP/VNC/SSH gateway; not yet implemented), and **vendor/customer site-to-site IPsec** tunnels — every one inspected before entering the fabric. Enrollment differs by modality (§10).
- **bridge-router** *(Enterprise tier — PostHog flag + Enterprise entitlement)* — a **network transit/interconnect hub** (analogous to GCP Network Connectivity Center / AWS Transit Gateway) **with inline SASE inspection (PEP)**: bridges the fabric to external networks, VPCs, sites, and agentless services, enforcing policy + tapping sensors at the junction.

By contrast, **hub-routers are lightweight** (basic policy + auth), and **intra-cluster k8s east-west security is out of scope** — Cilium NetworkPolicy / admission control / Tetragon, configured in the **Gough** project.
