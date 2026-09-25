```
              🛷 TOBOGGANING — Slide Into Zero Trust! 🛷
                     ⛄ "Downhill to Security!" ⛄

                ╭─────────────────────────────────╮
               ╱   ◉   T O B O G G A N I N G   ◉   ╲
              ╱      🛡️  Zero Trust · SASE Edge      ╲
             ╱───────────────────────────────────────╲
            ╱█████████████████████████████████████████╲
           ╱░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░╲
          ╱  ❄️ WireGuard · DoH/DoT · Threat-Intel · mTLS ╲
         ╱______________________________________________╲
             ╲╲╲╲╲  Sliding down the security slope!  ╱╱╱╱╱
```

# Tobogganing

[![GitHub release](https://img.shields.io/github/release/penguintechinc/tobogganing.svg)](https://github.com/penguintechinc/tobogganing/releases)
[![Build Status](https://github.com/penguintechinc/tobogganing/workflows/CI/badge.svg)](https://github.com/penguintechinc/tobogganing/actions)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

**Tobogganing is an open-source SASE (Secure Access Service Edge) + Zero-Trust Network Access (ZTNA) platform.** It fuses identity-aware connectivity, DNS-layer security, and threat intelligence into a single, policy-driven secure service edge — enforcing least-privilege, micro-segmented access across **intra-cluster, inter-cluster, and external** boundaries.

Every request is authenticated, every peer is verified, every zone is scoped: *never trust, always verify.*

---

## 🧭 The Three Pillars — SCP

Tobogganing is organized around **Security, Connectivity, and Policies (SCP)**, each applied consistently across the three connectivity domains.

| Pillar | What it delivers | Key building blocks |
|--------|------------------|---------------------|
| 🛡️ **Security** | Zero-trust identity + DNS-layer threat defense | Threat-intel IOC feeds, blocklist curation, DNS filtering; OIDC scopes; machine-JWT node enrollment; per-tenant isolation; mTLS/SPIFFE-ready |
| 🔌 **Connectivity** | Identity-aware secure edge across every boundary | Unified Rust **node-agent** (WireGuard + local DNS/DHCP/NTP edge), **netsvcs** DNS control plane with DoH/DoT resolvers, SD-WAN |
| 📜 **Policies** | Centralized, tenant-scoped policy enforcement | SASE Secure Web Gateway rules, DNS zones / records / split-horizon, SD-WAN routing policy, least-privilege access rules |

### Applied across three connectivity domains

| Domain | Connects | How Tobogganing does it |
|--------|----------|--------------------------|
| **Intra-cluster** | Node ⇄ node & service ⇄ service inside one cluster | Node-to-node **WireGuard woven into Cilium**, plus **Cilium NetworkPolicies + admission-controller policies** that enforce least-privilege, micro-segmented service-to-service traffic |
| **Inter-cluster** | Cluster ⇄ cluster, across regions **and cloud vendors** | **Cluster gateways** that screen traffic between clusters and make it trivial to interconnect them — even across different clouds — with Kubernetes-native, easy-on WireGuard connectivity |
| **External** | Endpoints & edge sites ⇄ the SASE fabric | Endpoints connect to the **SASE VPN concentrator nodes** over **OpenZiti or WireGuard** |

> The gRPC (`ManagerService`, `:50051`) vs REST (`/api/v1`) split below is the **control-plane API transport** (how components fetch identity/policy/config) — distinct from these data-plane connectivity domains.

---

## 🏗️ Architecture

A central **control plane** (`hub-api`) is the brain: it holds identity, policy, DNS config, and threat-intel state, and hands them out over **gRPC inside the cluster** and **REST to external edges**. Data-plane components — the DoH/DoT resolver fleet, the WireGuard router, and the Rust node-agents — enroll with machine JWTs and pull live config.

```
                        ┌──────────────────────────────────┐
                        │   portal  (hub-webui)            │
                        │   React + TypeScript · Vite       │
                        └──────────────────┬───────────────┘
                                           │ REST /api/v1 (OpenAPI 3.x)
                                           ▼
   ┌───────────────────┐   gRPC :50051  ┌──────────────────────────────────┐
   │  netsvcs-dns      │  ManagerService│   hub-api   (CONTROL PLANE)      │
   │  DoH :8080 / HTTP2│◀──────────────▶│   Quart · modular registry        │
   │  DoT :853         │  GetConfig      │   netsvcs · threatintel · sase ·  │
   │  split-horizon    │  StreamConfig   │   sdwan · perftest · ziti · ping  │
   │  + IOC filtering  │  CheckIOC       │   REST :8080  ·  gRPC :50051      │
   │  (DaemonSet)      │                 └───────┬──────────────────┬───────┘
   └─────────▲─────────┘                gRPC :50051│         WireGuard /       │
             │ :53 forward              (intra)    │         policy config     │
             │                                     ▼                           │
   ┌─────────┴───────────────┐          ┌────────────────────────────┐        │
   │  node-agent  (Rust)     │◀────────▶│  hub-router  (DATA PLANE)  │        │
   │  connectivity: WG/Ziti  │ WireGuard│  WireGuard :51820          │        │
   │  netsvcs-edge: :53 DNS  │  tunnel  │  proxy :8443 · IDS/IPS      │        │
   │  DHCP · NTP             │          │  mirror · metrics :9090     │        │
   │  DaemonSet + musl binary│          └────────────────────────────┘        │
   └─────────┬───────────────┘                                                │
             │ REST /api/v1  —  external / bare-metal / inter-cluster edges ───┘
             ▼
      external clusters & edge sites
```

**Transport boundary:** gRPC is the intra-cluster contract (`hub-api` ⇄ `netsvcs-dns`, `hub-api` ⇄ `node-agent` DaemonSets); REST `/api/v1` serves external clients (edge/bare-metal node-agents, the portal, inter-cluster peers). The Rust node-agent's `transport` crate selects gRPC (tonic) or REST (reqwest) at runtime from `AgentConfig::mode`.

---

## 🧩 Components & Modules

### Deployable services

| Service | Stack | Role | Ports |
|---------|-------|------|-------|
| **hub-api** | Python 3.13 · Quart · gRPC | Control-plane brain — auth, policy, DNS config, threat-intel, module registry | REST `8080`, gRPC `50051` |
| **hub-router** (`services/hub-router/`) | Go · WireGuard · gin | Tunnel termination, multi-protocol proxy, deny-by-default per-user firewall, out-of-band traffic mirror — see [SASE / Network Security](#-sase--network-security) | WG `51820`, HTTP(S) `8443`, TCP `8444`, UDP `8445`, metrics `9090` |
| **hub-webui** (`portal/`) | React · TypeScript · Vite · Express | Management web UI (see [New in this release](#-new-in-this-release)) | `3000` |
| **netsvcs-dns** (`engines/netsvcs-dns/`) | Python DaemonSet | DoH/DoT resolver — split-horizon + IOC filtering, Redis-cached | DoH `8080`, DoT `853`, metrics `9090` |
| **node-agent** (`agents/node-agent/`) | Rust (aya · tonic · reqwest) | Unified edge client — WireGuard/Ziti connectivity + local DNS/DHCP/NTP edge | local DNS `53` |
| **redis / valkey** | StatefulSet | Config + resolver response cache | `6379` |

### `hub-api` modules (`hub_api/modules/`)

| Module | Responsibility |
|--------|----------------|
| **netsvcs** | DNS control plane — zone/record/server managers, analytics, gRPC `ManagerService`, IOC check |
| **threatintel** | IOC feed ingestion (STIX/TAXII + custom parsers), URL safety, blocklist curation & store |
| **sase** | Secure Web Gateway policy + domain categorisation, tenant-authored block pages & routing, out-of-band analysis-tool adapters, DDoS/rate-limit protection, security scanner — see [SASE / Network Security](#-sase--network-security) |
| **sdwan** | SD-WAN orchestration, certs, firewall, network segmentation |
| **perftest_cluster / _client / _c2c** | Cluster, client, and cluster-to-cluster performance testing (WaddlePerf lineage) |
| **ziti** | OpenZiti overlay integration |
| **ping** | Lightweight reachability / health probes |

### The unified Rust node-agent (`agents/node-agent/crates/`)

One static binary, two jobs — SASE connectivity **and** local netsvcs edge — packaged both as a musl bare-metal build and a K8s DaemonSet container.

| Crate | Role |
|-------|------|
| `agent` | Binary entrypoint — wires connectivity + edge into one process |
| `connectivity` | WireGuard/Ziti data plane, XDP inspection tap |
| `netsvcs-edge` | Local `:53` DNS + DHCP + NTP, forwarding DNS to the DoH resolver fleet |
| `transport` | gRPC (tonic) + REST (reqwest) `ControlPlaneClient`, selected at runtime |
| `core` | Shared config, errors, machine-JWT signing, control-plane contract |

### gRPC control-plane contract (`proto/netsvcs/v1/manager.proto`)

`package netsvcs.manager.v1` — `ManagerService`: `RegisterServer`, `RefreshToken`, `GetConfig`, `StreamConfigUpdates`, `SendHeartbeat`, `ValidateToken`, `CheckIOC`. Nodes enroll with a machine JWT and stream live config updates.

---

## 🛡️ SASE / Network Security

The SASE data plane is the **Security** pillar in packet form. `hub-router` terminates tunnels and proxies traffic under a deny-by-default, per-user firewall; a *copy* of that traffic is fanned out to opt-in open-source analysis tools; their detections are pulled back in **out-of-band**, normalized to STIX indicators, and folded into the same threat-intel blocklist the rest of the platform already reads. Inspection never sits in the packet's critical path — a full analysis outage costs visibility, not connectivity.

```
                 user / site traffic
                          │
                          ▼
        ┌─────────────────────────────────────────────┐
        │  hub-router  ·  DATA PLANE                  │──▶ upstream
        │  WireGuard  :51820                          │
        │  HTTP(S) proxy  :8443                       │
        │  raw TCP :8444  ·  raw UDP :8445            │
        │  dynamic port ranges (from hub-api)         │
        │  per-user firewall  ·  syslog allow/deny    ◀──────────┐
        └─────────────────┬───────────────────────────┘          │
                          │                                      │
       (1) MIRROR - a copy of every proxied flow:                │
           VXLAN (default) / GRE / ERSPAN, plus an               │
           optional Suricata EVE-JSON feed on :9999              │
                          │                                      │
                          ▼                                      │
        ┌─────────────────────────────────────────────┐          │
        │  (2) ANALYSIS TOOLS - opt-in sub-charts,    │          │
        │      off by default                         │          │
        │  suricata · zeek · arkime · strelka · cape  │          │
        └─────────────────┬───────────────────────────┘          │
                          │                                      │
       (3) DETECT - NDJSON pulled out-of-band: EVE               │
           alerts, Zeek notices, Arkime sessions,                │
           Strelka YARA hits, CAPE verdicts                      │
                          │                                      │
                          ▼                                      │
        ┌─────────────────────────────────────────────┐          │
        │  hub-api  ·  CONTROL PLANE                  │          │
        │  adapters:  parse -> AdapterHit -> STIX     │          │
        │             -> Verdict -> blocklist (Valkey)│          │
        │  SWG policy · block pages · protection      ├──────────┘
        └─────────────────────────────────────────────┘

       (4) ENFORCE - deny-by-default firewall rules and SWG
           verdicts, pulled by the data plane from hub-api
```

### Data plane — `hub-router`

| Listener | Port | Behaviour |
|----------|------|-----------|
| WireGuard | `51820/udp` | Tunnel termination; `wg0` is provisioned at start-up from `GET /api/v1/clusters/{id}/headend-config` |
| HTTP(S) proxy | `8443/tcp` | Reverse proxy (target from `X-Target-Host`), TLS ≥ 1.2, injects `X-Frame-Options` / `X-Content-Type-Options` / `X-XSS-Protection`; also serves `/health` and the JWT · OAuth2-OIDC · SAML2 login routes |
| Raw TCP / UDP | `8444/tcp` · `8445/udp` | Byte-stream proxy; `wg0` traffic is REDIRECTed here by iptables. Token and target are read from the first packet |
| Dynamic ranges | from control plane | Extra per-port TCP+UDP listeners built from `GET /api/v1/headend/{headend_id}/ports`, re-fetched every 60 s |
| Metrics | `9090/tcp` | Prometheus `/metrics`, bearer-token or JWT gated |

**Per-user firewall.** Rules are pulled from `GET /api/v1/firewall/rules` on a randomised 30–90 s ticker and evaluated in priority order, **default deny** — a user with no rules reaches nothing. Rule types: exact and `*.` wildcard domain, IP, CIDR, case-insensitive URL regex, and 5-tuple `proto:src→dst:direction` with port lists and ranges. Every allow *and* deny is emitted to syslog with user, source IP, target, method, path, status and byte counts.

### Traffic mirror (the out-of-band tap)

With `mirror.enabled`, every proxied HTTP/TCP/UDP flow is copied onto a buffered channel and fanned out by worker goroutines. When the queue fills, copies are dropped and counted rather than back-pressuring the data path.

| Setting | Purpose |
|---------|---------|
| `mirror.destinations` | `host:port` list receiving the mirrored stream |
| `mirror.protocol` | `VXLAN` (default, VNI 1000), `GRE` (IP proto 47) or `ERSPAN` (Type-II) encapsulation |
| `mirror.buffer_size` | Fan-out queue depth (default `1000`) |
| `mirror.suricata_enabled` / `_host` / `_port` | Optional second target receiving newline-delimited **Suricata EVE JSON** over TCP (default `9999`) instead of encapsulated packets |

A kernel-level alternative ships alongside it: [`wireguard/scripts/setup-mirror.sh`](services/hub-router/wireguard/scripts/setup-mirror.sh) uses `iptables -t mangle -j TEE` plus `tc … action mirred`, and runs independently of the in-process mirror.

### Analysis tools → detections → threat intel

The adapters in [`hub_api/modules/sase/security/adapters/`](hub_api/modules/sase/security/adapters/) are **strictly pull-only**: they parse each tool's newline-delimited JSON and never write rules, signatures, or config back to the tools or to the proxy. The loop closes through policy, not through the sensors.

| Tool | Output parsed | IOCs extracted |
|------|---------------|----------------|
| **Suricata** | EVE JSON, `event_type: alert` | destination IP, TLS SNI / HTTP host, reconstructed URL, file SHA-256; severity from `alert.severity` |
| **Zeek** | notice log | source and destination IP, queried domain |
| **Arkime** | session records carrying malicious tags | src/dst IP and every session hostname; a `c2` tag escalates to critical |
| **Strelka** | scan results with YARA matches | file SHA-256; ≥ 3 rule matches escalate to critical |
| **CAPE** | sandbox verdicts (`malscore > 5.0` or `verdict: malicious`) | sample SHA-256 plus network IPs, DNS requests and HTTP URIs |

Each hit becomes an `AdapterHit` (`ioc_type`, `value`, `severity`, `first_seen`), is converted to a **STIX indicator**, wrapped in a `Verdict`, and written to the shared threat-intel blocklist store in Valkey (`threatintel:blocklist:{ioc_type}`) — the same store the `threatintel` module's feed curator writes to and its `check` API serves. `AdapterPoller` drives ingestion on a configurable interval with exponential back-off. Adapters are configured per source by environment variable (`{SOURCE}_ENABLED`, `_ENDPOINT`, `_LOG_PATH`) and are **off by default**.

> **Wiring status:** the adapters and poller take an injected `reader` callback rather than opening their own sockets or log files, so the collection transport is supplied per deployment — no built-in collector is wired into `hub-api` yet.

### Secure Web Gateway & block pages

- **Categorisation** — a label-reversed radix trie of domains backed by `domain_categories`, ingested from six licensed public feeds (UT1, The Block List Project, Hagezi/OISD, StevenBlack, URLhaus, Cipher OOS) plus tenant-supplied custom entries, with a 24 h Valkey cache
- **Tier-2 classifier** — on a lookup miss a Celery job fetches the site through an SSRF-hardened client (full DNS re-resolution, private/loopback/link-local/reserved rejection, redirect re-validation, 512 KB / 5 s caps), extracts metadata only, and runs a local TF-IDF + linear classifier; below 0.5 confidence the domain stays `uncategorized`. Gated by the `tobogganing.sase/swg_ai_categorizer` flag (Professional)
- **Policy** — `CategoryPolicy` binds a category to an `EnforcementAction` (`allow`, `log_only`, `soft_block`, `block`, `drop`) at tenant / group / user scope; user beats group beats tenant, then the most restrictive action within the winning scope wins. Uncategorised traffic defaults to allow
- **Block pages** — tenant-authored, versioned markdown with draft/live publishing and revert, rendered through `{{variable}}` substitution and bleach-sanitised HTML. `BlockRoute` maps a `source_type` (e.g. `web-category:gambling`, `oob-analysis:malware`) to a page or an external URL, carries governance metadata (owner, ticket, expiry, review date, risk), and falls back to the tenant's `default` route

| Endpoint | Auth |
|----------|------|
| `GET /api/v1/sase/swg/lookup` | `sase:read` + `sase.swg` feature |
| `GET /api/v1/sase/swg/radix` | machine JWT `swg:read` — edge/agent artifact pull |
| `POST /api/v1/sase/swg/categories` · `GET\|PUT /api/v1/sase/swg/policy` | `sase:read` / `sase:write` |
| `GET\|POST\|PUT /api/v1/sase/blockpages/pages` · `…/publish` · `…/preview` · `GET\|PUT …/routes` | `sase:read` / `sase:write` + `sase.blockpages` feature |

Every route is tenant-scoped (`@require_tenant`).

### DDoS protection, rate limiting & scanning

- **Rate limiting** — Redis sorted-set sliding window with built-in per-endpoint rules (auth `5/60 s` → 15 min block, API `60/60 s`, web `200/60 s`) plus per-tenant `rate_limit_rules` rows with endpoint prefixes, CIDR exemptions and priority; falls back to an in-process deque if Redis is unreachable
- **DDoS heuristics** — request volume, suspicious path and user-agent patterns, endpoint-sweep and inter-arrival behaviour, and distributed-source detection, escalating to timed IP blocks and a 1 h emergency-mode flag; events land in `security_events`
- **Scanner** — scheduled vulnerability, container, dependency and port scans invoking `trivy image`, `trivy fs`, `nmap`, `safety` and `govulncheck`, with findings normalised into `security_findings` (severity, CVEs, CVSS). Configuration and compliance scan types are still placeholders

> **Wiring status:** `protection` and `scanner` register no blueprints and are not yet mounted into the `hub-api` request path — they are libraries awaiting wiring, not live enforcement.

### Deploying the analysis tools

All five ship as condition-gated sub-charts under [`k8s/helm/tobogganing/charts/`](k8s/helm/tobogganing/charts/), **off by default** — see [`OPTIONAL_SUBCHARTS.md`](k8s/helm/tobogganing/OPTIONAL_SUBCHARTS.md).

| Sub-chart | Condition key | Default | Image |
|-----------|---------------|---------|-------|
| `suricata` | `suricata.enabled` | `false` | `jasonish/suricata:7.0.7`, digest-pinned |
| `zeek` | `zeek.enabled` | `false` | `zeek/zeek:6.2.1`, digest-pinned |
| `strelka` | `strelka.enabled` | `false` | `target/strelka-frontend:1.0.1`, digest-pinned |
| `arkime` | `arkime.enabled` | `false` | none shipped — supply one or the template fails fast |
| `cape` | `cape.enabled` | `false` | none shipped — needs a hypervisor host, out of scope for the chart |

Suricata runs with a documented root exception (`NET_ADMIN` + `NET_RAW`) so it can read the mirror feed on `9999`; the rest are rootless with read-only root filesystems and `emptyDir` scratch (no PVCs).

> **Enabling a sub-chart alone does not connect the tap.** The umbrella chart does not yet template `hub-router`'s mirror settings, so `mirror.enabled` and `mirror.destinations` must be set on `hub-router` as well.

### Roadmap — designed, not implemented

Two pieces of the intended architecture exist **only as design documents**, with no corresponding code in the tree:

- **Envoy-based inspection proxy**, with security-sensitive logic in Rust (proxy-wasm filters and/or a Rust `ext_authz` / `ext_proc` sidecar), superseding today's Go proxy. [`docs/architecture/hub-network-topology.md`](docs/architecture/hub-network-topology.md) still records the proxy foundation as *TBD*; [`docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md`](docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md) §11 holds the fuller spec
- **In-line verdict return** — a Rust wrapper that extracts detections from the sensors and pushes block verdicts back into the proxy (Envoy `ext_authz` / dynamic deny), closing the loop in-line. No such crate exists; the only Rust in the repo is the [`node-agent`](agents/node-agent/) workspace, and today's return path is limited to the firewall rules and SWG policy the data plane pulls from `hub-api`

---

## ✨ New in This Release

### 🖥️ netsvcs + threat-intel Web UI

A full management surface for DNS and threat intelligence, served from `portal/`:

- **netsvcs / DNS** — [`ZonesPage`](portal/src/pages/netsvcs/ZonesPage.tsx) (zones + split-horizon), [`ZoneRecordsPage`](portal/src/pages/netsvcs/ZoneRecordsPage.tsx) (records), [`DnsServersPage`](portal/src/pages/netsvcs/DnsServersPage.tsx) (resolver fleet health), [`AnalyticsPage`](portal/src/pages/netsvcs/AnalyticsPage.tsx) (query analytics)
- **threat-intel** — [`IocCheckPage`](portal/src/pages/threatintel/IocCheckPage.tsx) (on-demand IOC lookup), [`FeedsPage`](portal/src/pages/threatintel/FeedsPage.tsx) (feed source management), [`BlocklistPage`](portal/src/pages/threatintel/BlocklistPage.tsx) (blocklist curation)

### 🦀 Unified Rust node-agent

WireGuard connectivity and the local DNS/DHCP/NTP edge collapse into **one** memory-safe Rust binary — a single install per node instead of a stack of daemons, with runtime gRPC/REST transport selection.

### 📦 One Helm umbrella

The whole SASE + netsvcs stack now deploys as a single Helm release — `hub-api`, `hub-router`, `hub-webui`, the `netsvcs-dns` resolver fleet, and the `node-agent` DaemonSet, with optional out-of-band analysis tools (Suricata, Zeek, Arkime, Strelka, CAPE) off by default.

---

## 🖼️ Screenshots

> Captured against seeded mock data. See [`docs/screenshots/`](docs/screenshots/).

**Authentication**

![Login](docs/screenshots/login.png)

**netsvcs — DNS control plane**

| Zones | Servers | Analytics |
|-------|---------|-----------|
| ![DNS Zones](docs/screenshots/dns-zones.png) | ![DNS Servers](docs/screenshots/dns-servers.png) | ![DNS Analytics](docs/screenshots/dns-analytics.png) |

**Threat intelligence**

| IOC Check | Feeds | Blocklist |
|-----------|-------|-----------|
| ![IOC Check](docs/screenshots/threatintel-ioc.png) | ![Feeds](docs/screenshots/threatintel-feeds.png) | ![Blocklist](docs/screenshots/threatintel-blocklist.png) |

---

## 🚀 Deployment

Tobogganing ships as a single Helm umbrella chart: [`k8s/helm/tobogganing`](k8s/helm/tobogganing). The environment lives in the kube-context and the values file — never in the namespace (always `tobogganing`).

### Alpha — local MicroK8s

```bash
helm dependency build k8s/helm/tobogganing
helm upgrade --install tobogganing k8s/helm/tobogganing \
  --kube-context local-alpha \
  --namespace tobogganing --create-namespace \
  --values k8s/helm/tobogganing/values-alpha.yaml
```

### Beta → Gamma → Production

CI builds and publishes images to `ghcr.io/penguintechinc/tobogganing/{service}`; deploy with the matching values file and context.

| Env | Context | Values file |
|-----|---------|-------------|
| Alpha | `local-alpha` | `values-alpha.yaml` |
| Beta | `dal2-beta` | `values-beta.yaml` |
| Gamma | `dal2-gamma` | `values-gamma.yaml` |
| Production | `tobogganing-prod` | `values-production.yaml` |

```bash
helm upgrade --install tobogganing k8s/helm/tobogganing \
  --kube-context dal2-beta \
  --namespace tobogganing \
  --values k8s/helm/tobogganing/values-beta.yaml
```

Optional analysis-tool sub-charts (`suricata`, `zeek`, `arkime`, `strelka`, `cape`) are off by default — enable per [`k8s/helm/tobogganing/OPTIONAL_SUBCHARTS.md`](k8s/helm/tobogganing/OPTIONAL_SUBCHARTS.md).

---

## 🛠️ Development

**Prerequisites:** Python 3.13+, Rust 1.98+, Node.js 20+, Docker, and a local Kubernetes (MicroK8s / Docker Desktop).

```bash
# Control plane (hub-api) — Quart + gRPC
cd hub_api && uv pip install --system --require-hashes -r requirements.txt && python -m hub_api.app

# DoH/DoT resolver
cd engines/netsvcs-dns && pip install -r requirements.txt && python -m app.main

# Unified node-agent
cd agents/node-agent && cargo build --release

# Web UI
cd portal && npm ci && npm run dev
```

Python dependencies are compiled with `uv pip compile --generate-hashes` (hash-verified installs everywhere, per org standard) and installed with `uv pip install --require-hashes`. After editing any `requirements*.in`, regenerate the matching lock file with `make compile-deps` (or the narrower `make compile-deps-hub-api`) — never hand-edit a `requirements*.txt`.

### Tests

```bash
make test              # full suite
pytest hub_api/tests                              # control-plane
cd engines/netsvcs-dns && pytest --cov --cov-fail-under=90   # resolver (90%+ gate)
cd agents/node-agent && cargo test                # node-agent
cd portal && npm test                             # web UI
```

The REST API publishes an OpenAPI 3.x spec at [`openapi/v1.yaml`](openapi/v1.yaml).

---

## 📖 Documentation

| Guide | Path |
|-------|------|
| Overview | [`docs/OVERVIEW.md`](docs/OVERVIEW.md) |
| Architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Quickstart | [`docs/QUICKSTART.md`](docs/QUICKSTART.md) |
| Authentication | [`docs/AUTHENTICATION.md`](docs/AUTHENTICATION.md) |
| API reference | [`docs/API.md`](docs/API.md) |
| Client installation | [`docs/CLIENT_INSTALLATION.md`](docs/CLIENT_INSTALLATION.md) |
| netsvcs-dns resolver | [`engines/netsvcs-dns/README.md`](engines/netsvcs-dns/README.md) |

---

## 🤝 Contributing & Security

- Contributions: see [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)
- Report vulnerabilities responsibly: see [`SECURITY.md`](SECURITY.md)

## 📄 License

Licensed under **AGPL-3.0** for personal and internal use; commercial and SaaS deployments require a commercial license, and enterprise features are separately licensed. See [`LICENSE`](LICENSE) and [`docs/LICENSE.md`](docs/LICENSE.md) for the full terms, including the Contributor Employer (GPL-2.0) exception.

---

*Made with ❄️ by PenguinTech — secure access, simplified.*
