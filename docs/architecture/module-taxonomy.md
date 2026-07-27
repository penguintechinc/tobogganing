# Module Taxonomy (functional naming)

**Principle:** modules are named by **what they do**, not by product lineage. All *advanced* security lives in the `sase` module; strip `sase` away and only **basic firewall rules + basic authentication + overlay transport** remain (baseline/always-on).

**Product Positioning:** Tobogganing is a **lightweight, open-source-driven alternative to ZScaler** (SASE/SSE). The module structure reflects this:
- **`sdwan`** = Connectivity layer (overlay transport + routing)
- **`sase`** = Security-Service-Edge layer (inspection, threat-feeds, context-auth, mirror hooks)
- **`ziti`** = Alternative identity overlay (greenfield; optional coexistence)
- **core** = Infrastructure foundation (auth, PKI, backup)

> Status: finalized direction (2026-07-26). Placement rules: (1) **transport layer** (WireGuard, IPsec, OpenVPN tunneling AND routing) → `sdwan`; (2) **management-plane** (user logins, API keys, JWT, PKI certs, backup) → **core**; (3) **greenfield overlay auth** (OpenZiti) → new module **`ziti`** (standalone, no cross-wiring to `sdwan` transport). The `perftest` rename is isolated; the `sase`→`sase`+`sdwan`+`core`+`ziti` re-decomposition is finalized in `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md`.

## Modules

| Module | Function | Tier posture |
|---|---|---|
| *(core — not a module)* | **Management-plane / infrastructure**: username/password, API keys, JWT issue/validate, PKI (X.509) certs, encrypted backup. Always-on, zero licensing gate. | Free/Community |
| **`sdwan`** | **Overlay transport + routing layer**: WireGuard/IPsec/OpenVPN tunneling, cluster/client orchestration, failover, VRF/OSPF/FRR routing, headend ports, and **basic firewall rules** (ACLs). Baseline data-plane policy. | Community → Professional |
| **`ziti`** | **Greenfield identity overlay** — OpenZiti control-plane + client SDK integration. Standalone auth model (not wired to `sdwan` transport). Can coexist with `sdwan`; no mandatory dependency. | Professional → Enterprise (greenfield) |
| **`sase`** | **Security-Service-Edge layer** — the control plane for deep-inspection (hub-client + bridge-router): IDS/IPS threat-feeds, vuln scanner, DDoS/rate-limit protection, **context-based / adaptive authentication** (threat intel, impossible travel, risk-based / step-up), and **traffic-mirror hooks** (SPAN/monitor-port → Arkime, Zeek, Suricata, Strelka, CAPE). | Community → Enterprise (tiered) |
| **`perftest`** | **Network performance testing** (was `waddleperf_*`): `perftest_cluster`, `perftest_client`, `perftest_c2c`. | Community → Professional |
| **`netsvcs`** | **Network services** — reserved home for the future **squawk (DNS)** merge. Nothing current moves here. | (future) |

## Detection → Block Feedback Loop (`sase`)

The **`sase` module** owns the out-of-band analysis and verdict pipeline:
- **Mirror targets** (Arkime, Zeek, Suricata, Strelka, CAPE) fed via SPAN/monitor-port; zero latency on live traffic (no inline blocking).
- **Detection adapters** normalize analysis output (Suricata EVE, Zeek notices, file/sandbox verdicts) to **STIX 2.1 indicators**.
- **Shared Valkey IOC store** curated by hub-api (dedup, TTL, threat-intel merge). Inspection Points read and enforce on FUTURE traffic (retroactive, IP/domain/hash/URL block lists).
- Decoupled async — no gRPC round-trip on enforcement path.

## The auth line (important)

- **Basic auth = CORE**, never gated behind a module: username/password, API keys, JWT, PKI certs.
- **Context-based / adaptive auth = `sase`**: threat intel, impossible-travel, risk-based / step-up. This is licensed security, not baseline.

Rule of thumb: *if it's more than "are these credentials valid?", it's `sase`.*

## Current → target mapping (the `sase` re-decomposition)

Today `hub_api/modules/sase/` is one monolithic module. It splits across four targets:

| Current area (`hub_api/modules/sase/…`) | → Target |
|---|---|
| `api/jwt`, `auth/user_manager`, `certs/certificate_manager.py` (X.509 PKI only), `backup/` | **core** (management-plane) |
| `certs/certificate_manager.py` (WireGuard key mgmt: `generate_wireguard_keys`, `get_all_wireguard_peers`, `revoke_wireguard_keys`, `get_wireguard_config`) | **`sdwan`** (`WireGuardKeyManager`) |
| `api/clusters`, `api/clients`, `api/status`, `api/wireguard`, `orchestrator/`, `network/vrf`, `network/port_manager` | **`sdwan`** (overlay transport + routing + orchestration) |
| `firewall/access_control` (basic rules) | **`sdwan`** (baseline data-plane policy) |
| `security/feeds`, `security/scanner`, `security/protection` | **`sase`** |
| context-based auth (new — see above) | **`sase`** |
| (OpenZiti — greenfield code, not yet written) | **`ziti`** (scaffold + new control-plane) |
| `hub_api/modules/waddleperf_*` | **`perftest`** (isolated rename, zero cross-module entanglement) |

## Hard seams (what makes the split non-trivial)

1. **Placement rules** — what belongs where:
   - **core**: All management-plane / infrastructure (user logins, API keys, JWT, X.509 PKI certs, encrypted backup). Licensing: none (always free).
   - **`sdwan`**: All transport layer (WireGuard/IPsec/OpenVPN tunneling, routing, clusters/clients, orchestration, failover, VRF/OSPF, ports, basic firewall ACLs). Licensing: Community → Professional.
   - **`ziti`**: OpenZiti identity overlay (greenfield, no current code). Control-plane only; client SDK integration. Licensing: Professional → Enterprise. No hard dependency on `sdwan` transport; can coexist.
   - **`sase`**: Security inspection + context-based auth (threat-feeds, scanner, protection, threat intel, impossible travel, risk-based step-up). Licensing: Community → Enterprise (tiered).

2. **`CertificateManager` is dual-purpose** (`hub_api/modules/sase/certs/certificate_manager.py`) — X.509 PKI **and** WireGuard key management in one class. **Split**: PKI management (`generate_x509`, `revoke_x509`, etc.) → **core** (`CertificateManager`); WireGuard key operations (`generate_wireguard_keys`, `get_all_wireguard_peers`, `revoke_wireguard_keys`, `get_wireguard_config`) → **`sdwan`** (`WireGuardKeyManager`).

3. **`hub_api/api/headend_routes.py`** (flat data-plane API blueprint) imports `auth.user_manager` + `certs.certificate_manager` + `firewall.access_control` + `network.port_manager` + `orchestrator.cluster_manager`. Spans **core + `sdwan`**. Decision: keep in `sdwan` (transport home); re-export core helpers via shim so imports remain local.

4. **Alembic migrations `0002`–`0008`** and the monolithic `ModuleContract` (blueprints, nav, `tobogganing.sase.*` flags, entitlements, tier gating) must be **partitioned per new module** — each module owns its own migrations and contract.

5. **Flag-key migration**: `tobogganing.sase.{clusters,clients,status,wireguard,large_cluster}` → `tobogganing.sdwan.*`; `tobogganing.sase.{threat_feeds,scanner,protection,context_auth}` stay in `tobogganing.sase.*`; `tobogganing.ziti.*` new flags for OpenZiti features. Auth/PKI/backup are not module features (they are core, unflaged).

6. **Cross-module imports**: No `sdwan` → `sase` or `sase` → `sdwan` imports. Both can import from **core**. **`ziti`** does not import from `sdwan` or `sase` (greenfield identity, separate auth model).

## Verification approach

- **Per-module contract tests**: each module (`core`, `sdwan`, `ziti`, `sase`) declares its own `ModuleContract` with flags, nav, tier gating (default OFF for new modules).
- **Cross-module import audit**: no `sdwan`↔`sase` imports; `ziti` standalone; all others can import **core** freely.
- **Full suite parity**: after split, all existing tests pass with same coverage (≥90%).
- **Migration audit**: Alembic migrations properly partitioned; version sequence unbroken.
- **Flag scope validation**: flag keys renamed correctly (`tobogganing.sdwan.*` vs old `tobogganing.sase.{transport}.*`); tier gates applied.

## Cross-references

- **Hub topology & architecture**: see `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md`
- **Network diagram**: see `docs/architecture/hub-network-topology.md`
- **Re-decomposition spec**: see `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md`
