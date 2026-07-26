# Module Taxonomy (functional naming)

**Principle:** modules are named by **what they do**, not by product lineage. All *advanced* security lives in the `sase` module; strip `sase` away and only **basic firewall rules + basic authentication** remain (both baseline/always-on).

> Status: agreed direction (2026-07-23). The `perftest` rename is a clean, isolated first step; the `sase`→`sase`+`sdwan`+core split is a re-decomposition that gets its own spec + plan. Nothing renamed yet.

## Modules

| Module | Function | Tier posture |
|---|---|---|
| *(core — not a module)* | **Basic authentication**: username/password, API keys, JWT issue/validate, PKI certs. Always-on. | Free/Community |
| **`sase`** | **Security proxy / Inspection Point layer** — the control plane for the deep-inspection that hub-client + bridge-router enforce: IDS/IPS threat-feeds, vuln scanner, DDoS/rate-limit protection, and **context-based / adaptive authentication** (threat intel, impossible travel, risk-based / step-up — anything beyond basic credentials). | Community → Enterprise (tiered) |
| **`sdwan`** | **Routing / overlay + baseline data-plane policy**: clusters, clients, status, WireGuard tunnels, cluster/client orchestration + failover, VRF/OSPF, headend ports, and **basic firewall rules**. | Community + Professional |
| **`perftest`** | **Network performance testing** (was `waddleperf_*`): `perftest_cluster`, `perftest_client`, `perftest_c2c`. | Community → Professional |
| **`netsvcs`** | **Network services** — reserved home for the future **squawk (DNS)** merge. Nothing current moves here. | (future) |

## The auth line (important)

- **Basic auth = CORE**, never gated behind a module: username/password, API keys, JWT, PKI certs.
- **Context-based / adaptive auth = `sase`**: threat intel, impossible-travel, risk-based / step-up. This is licensed security, not baseline.

Rule of thumb: *if it's more than "are these credentials valid?", it's `sase`.*

## Current → target mapping (the `sase` re-decomposition)

Today `hub_api/modules/sase/` is one monolithic module. It splits:

| Current area (`hub_api/modules/sase/…`) | → Target |
|---|---|
| `security/feeds`, `security/scanner`, `security/protection` | **`sase`** |
| context-based auth (new — see above) | **`sase`** |
| `api/jwt`, `auth/user_manager`, `certs` (PKI) | **core** (basic auth) |
| `firewall/access_control` (basic rules) | **`sdwan`** |
| `api/clusters`, `api/clients`, `api/status`, `api/wireguard`, `orchestrator/`, `network/vrf`, `network/port_manager` | **`sdwan`** |
| `backup/` (encrypted S3 backup) | **OPEN** — core/ops, not `netsvcs` |
| `hub_api/modules/waddleperf_*` | **`perftest`** (isolated rename, zero `sase` entanglement) |

## Hard seams (what makes the `sase` split non-trivial)

1. **`CertificateManager` is dual-purpose** (`hub_api/modules/sase/certs/certificate_manager.py`) — X.509 PKI **and** WireGuard key management in one class. Split: PKI → **core auth**, WireGuard keys (`generate_wireguard_keys`, `get_all_wireguard_peers`, …) → **`sdwan`**.
2. **`hub_api/api/headend_routes.py`** (the flat data-plane API) fans into auth + firewall + ports + clusters + wireguard-peers — spans **core-auth + `sdwan`**; barely touches `sase`.
3. **Migrations `0002`–`0008`** and the monolithic `ModuleContract` (blueprints, nav, `tobogganing.sase.*` flags, entitlements) must be **partitioned per new module**.
4. `security/*`, `network/vrf`, `backup/*` are standalone (no wired blueprint) → **low-risk to relocate**; `network/port_manager` is the exception (wired via `headend_routes`).

## Flag keys

Convention `tobogganing.{module}.{feature}` is unchanged; keys migrate with the modules:
`tobogganing.waddleperf_*.*` → `tobogganing.perftest_*.*`, the security flags → `tobogganing.sase.*`, routing flags → `tobogganing.sdwan.*`.

## Sequencing

1. **`perftest` rename** — isolated, ~`c2c`-scale (paths, flag keys, tests). Do first.
2. **`sase` / `sdwan` / core-auth split** — own spec + plan; resolve the OPEN `backup/` home and the `CertificateManager` split first.

See `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md` for the surrounding hub-* architecture and `docs/architecture/hub-network-topology.md` for the network diagram.
