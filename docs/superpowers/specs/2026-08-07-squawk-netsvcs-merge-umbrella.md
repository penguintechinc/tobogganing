# Squawk → `netsvcs` Merge — Umbrella Program Spec

**Date**: 2026-08-07
**Status**: Decomposition + decisions approved; per-phase specs to follow
**Type**: Umbrella (multi-subsystem program) — each phase gets its own spec→plan→implement cycle
**Cross-references**:
- Merge-pattern precedent: WaddlePerf→perftest (`docs/superpowers/specs/2026-07-08-waddleperf-module-merge-design.md`), sase/sdwan/ziti split
- Roadmap memory: `future-squawkdns-merge` (squawk → `netsvcs` after the hub-* program)
- Source repo: `/home/penguin/code/squawk` (Squawk DNS, v5.1.1)
- Existing SASE to refactor: `hub_api/modules/sase/security/{feeds,blocklist}/`

## Goal

Merge the Squawk DNS product into tobogganing as network-services (`netsvcs`), following the established WaddlePerf pattern (control plane → `hub_api/modules/` in Quart; data-plane services → `engines/`; per-node agent → `agents/node-agent/` in Rust). Squawk today is a **DoH resolver + threat-intel DNS filtering + authoritative split-horizon custom zones + DHCP + NTP + a Go edge agent + control plane** — a multi-phase program, not a single merge.

## Locked decisions (from brainstorming)

1. **Threat-intel becomes its own shared module.** Do NOT converge Squawk's IOC onto SASE, and do NOT keep two stores. Instead **extract** the existing SASE `feeds/` + `blocklist/` into a standalone **`threatintel`** module, harvest Squawk's MISP/STIX/TAXII/OpenIOC feed parsers into it, and make **SASE (SWG/enforcement) AND netsvcs (DNS filtering) both consumers**. One threat-intel pipeline + store (`sase:blocklist:*` → generalized), leveraged by all products.
2. **The control plane and the DNS resolver *service* stay Python/Quart — only the *node-agent* goes to Rust (#8).** This "no rewrite" applies to two things and NOT the agent: (a) the **control-plane API** (`hub_api`, incl. the new `netsvcs` module) stays Quart/Python — it's a hub_api module like every other; (b) the central **DoH resolver service** (`engines/netsvcs-dns`, from `dns-server/app`) stays Python/Quart, rewritten to Rust ONLY on a measured throughput need (>10K rps) — not up front (YAGNI; and per the Go phase-out, any such rewrite would be Rust, not Go). The squawk `:53` **edge forwarder is NOT kept as Go** — it is folded into the Rust node-agent (decision #8). So: API + resolver-service = Python (no rewrite); node-agent = Rust.
3. **Full suite in scope**: DNS + DHCP + NTP. netsvcs is the complete network-services module.
4. **DHCP and NTP are INDEPENDENT feature flags.** Each netsvcs service (DNS, DHCP, NTP) is separately flag-gated + tiered, so operators enable them independently: `tobogganing.netsvcs.dns.*`, `tobogganing.netsvcs.dhcp.*`, `tobogganing.netsvcs.ntp.*`.
5. **Discard the legacy.** Squawk has 3 overlapping DNS codebases (legacy `dns-server/bins` monolith, a Flask variant, the new `dns-server/app` Quart agent) + a py4web console + a legacy Python client. Base the merge on the **new `manager/` control plane + `dns-server/app` agent + `squawk-client-go`**; discard the rest (harvest only the MISP/STIX/TAXII/OpenIOC parsers from `bins/ioc_manager.py` into `threatintel`).
6. **Replace bespoke auth.** Squawk's `auth_user`/`team`/`token` + hand-rolled PyJWT → dropped; remap onto tobogganing's single `users` identity table + tenant model + existing token/JWT issuance (penguin-aaa/penguin-dal). Squawk's per-DNS-server join-key/JWT fleet-registration maps onto the machine-JWT/enrollment model already built (auth redesign + `docs/architecture/headend-machine-jwt-contract.md`).
7. **Unified server/node agent (`node-agent`).** Merge the tobogganing **server** agents (`clients/docker` = client-k8s DaemonSet + the planned client-node bare-metal agent) AND the squawk **server** agents (`squawk-client-go` edge :53 DoH forwarder + DHCP + NTP clients) into **ONE binary** with two deploy modes — **K8s DaemonSet** and **bare-metal/systemd** (non-k8s servers + hypervisors). One agent per server does BOTH: **connectivity** (WireGuard/OpenZiti into the SASE fabric, node registration, Inspection-Point tap) AND **netsvcs edge** (local :53 DNS forward/resolve + `threatintel` filtering, DHCP, NTP). Each capability is **independently flag-gated** (consistent with decision #4) so an operator runs connectivity-only, DNS-only, or any combination. Lives in the **tobogganing repo** (`agents/node-agent/`). The central DoH resolver **service** (`engines/netsvcs-dns`) stays separate — the agent forwards to it or resolves locally. The **end-user desktop** agent is unaffected — it stays in `~/code/penguin` (penguin modular desktop). *(Naming `node-agent` is provisional; alt: `hub-agent`/`server-agent`.)*
8. **The node-agent is written in Rust** (not Go). It hits all three Rust triggers — a NEW service (not maintenance), **security-sensitive** (holds WireGuard keys + machine-JWT auth + tunneling on every privileged node — the "security-sensitive = Rust or Python3, never Go" rule), and **high-perf edge networking** (WireGuard/XDP/DNS) — plus it aligns with the Go phase-out; memory safety is highest-value on a privileged per-node agent. The existing Go (`squawk-client-go` ~8K LOC + tobogganing docker client) is **reference to port, not code to preserve.** Crate stack: `aya` (XDP/eBPF), `quinn` (QUIC/HTTP3 for DoH), `boringtun`/netlink (WireGuard), `hickory-dns` (DNS), `ntpd-rs` (NTP/NTS — stronger than the Go story), `tonic`/`tokio` (gRPC/async), `dhcproto` (DHCP client). Known thinner area: Rust **DHCP-server** crates — minor here (the agent is mostly a DHCP *client*; the DHCP *server* is a separate `engines/` service). `cargo deny`/`clippy -D warnings` gate per `backend-rust.md`.

## Target shape

```
hub_api/modules/
├── threatintel/        # NEW shared: feed ingestion (MISP/STIX/TAXII/OpenIOC + blackweb/spamhaus),
│                       # STIX normalizer, blocklist store, IOC curation, verdict API.
│                       # Extracted from sase/security/{feeds,blocklist}; SASE + netsvcs consume it.
├── sase/               # security/{feeds,blocklist} REMOVED → import from threatintel;
│                       # SWG/enforcement/adapters become threatintel clients.
└── netsvcs/            # NEW: DNS (zones/records/servers), DHCP, NTP control planes;
                        # per-service independent flags + tiers.
engines/
├── netsvcs-dns/        # Python Quart DoH/DoT resolver SERVICE (from dns-server/app); reads threatintel for filtering
├── netsvcs-dhcp/       # DHCP server service
└── netsvcs-ntp/        # NTP/NTS server service
agents/
└── node-agent/         # NEW UNIFIED per-server/per-node agent (RUST, ONE binary, two deploy modes):
                        #   • K8s DaemonSet  • bare-metal/systemd (non-k8s servers + hypervisors)
                        # MERGES tobogganing server agents (clients/docker=client-k8s + planned
                        # client-node) AND squawk server agents (squawk-client-go edge :53
                        # forwarder + DHCP + NTP clients). Capabilities, each INDEPENDENTLY flag-gated:
                        #   connectivity (WireGuard/OpenZiti → SASE fabric, node reg, Inspection tap)
                        #   + netsvcs edge (local :53 DNS forward/resolve+threatintel-filter, DHCP, NTP)
# End-user desktop agent stays in ~/code/penguin (penguin modular desktop) — NOT merged here.
```

## Phasing (each phase = its own spec→plan→implement cycle)

### P0 — Scope & dedup (design/decision phase)
Import the chosen base (new `manager/` + `dns-server/app` + `squawk-client-go`) into a working area; catalog exactly what's discarded (legacy `bins/` monolith, Flask variant, py4web console, Python client, stray junk files `=1.69.0` etc.); identify the MISP/STIX/TAXII/OpenIOC parsers in `bins/ioc_manager.py` (86KB) to harvest. Deliverable: an import manifest + the P1 harvest list. No runtime code yet.

### P1 — `threatintel` shared module (touches shipped SASE code — sequence first, carefully)
- Create `hub_api/modules/threatintel/`; MOVE `sase/security/feeds/` + `sase/security/blocklist/` into it (the STIX normalizer, `BlocklistStore`, curator, feed sources/manager). Generalize naming where SASE-specific (`sase:blocklist:*` Valkey prefix stays for compat, or migrate to `ti:blocklist:*` with a documented cache-key migration).
- Harvest Squawk's feed parsers (MISP/STIX/TAXII/OpenIOC) into `threatintel/feeds/sources.py` — adds source formats SASE's `feeds/` doesn't yet cover.
- Update SASE consumers (SWG `lookup.py`, `blocklist/api.py`, the Slice-D adapters' write path, Slice-E catcache write-back) to import from `threatintel`. Preserve behavior + all tests (suite parity).
- Contract: `threatintel` module with its own flags/entitlements (community threat feeds; enterprise KMS/advanced feeds later). **Import-boundary rule**: sase + netsvcs may import threatintel; threatintel imports neither.

### P2 — netsvcs control plane
- `hub_api/modules/netsvcs/` — port `dns_zone`/`dns_record`/`dns_server` (+ metrics) PyDAL models → penguin-dal + Alembic (chain after the current head); port `dns_servers`/`zones`/`analytics` blueprints → Quart.
- DROP `auth_user`/`team`/`token`; every query tenant-scoped from claims (the cross-tenant discipline the SASE work hardened). Fleet registration (join-key → per-server JWT) → the machine-JWT/enrollment model.
- Keep the `manager_service.proto` gRPC contract (RegisterServer/GetConfig/StreamConfigUpdates/SendHeartbeat/ValidateToken/CheckIOC) — `CheckIOC` becomes a thin `threatintel` client.
- Flag `tobogganing.netsvcs.dns.*` (community core; some features professional).

### P3 — Data-plane services (DNS + DHCP + NTP, independent flags)
- `engines/netsvcs-dns/` — the Quart DoH/DoT/HTTP3 resolver **service** (`dns-server/app`): registers with the control plane, syncs zones + config over gRPC, resolves (forward + custom-zone answers), enforces filtering by reading `threatintel` (blocklist + SWG category verdicts). Debian-slim rebuild (Squawk is Ubuntu today).
- `engines/netsvcs-dhcp/` + `engines/netsvcs-ntp/` — DHCP + NTP/NTS server **services** (from `dhcp-server/` + `ntp-server/`).
- **Independent flags**: `tobogganing.netsvcs.{dns,dhcp,ntp}.*` — each separately enable-able + tiered; any works without the others. Per-service contract registration so enabling one never requires another.

### P4 — Unified `node-agent` (the server-agent convergence — decision #7)
- `agents/node-agent/` — ONE **Rust** binary (decision #8) merging the tobogganing server agents (`clients/docker` client-k8s + planned client-node) AND the squawk edge agent (`squawk-client-go` :53 forwarder + DHCP + NTP clients) — the existing Go is ported, not preserved. Crates: `aya`/`quinn`/`boringtun`/`hickory-dns`/`ntpd-rs`/`tonic`/`tokio`.
- **Two first-class deployment artifacts, built from the ONE Rust binary — both are explicit P4 deliverables:**
  1. **Standalone binary** (bare-metal / non-k8s servers + hypervisors — the *client-node* role): a single **static musl** executable, installed + supervised as a **systemd** service via a bare-metal installer (deb/rpm or install script). No Kubernetes required; self-registers with the control plane over the machine-JWT/enrollment flow.
  2. **Kubernetes DaemonSet** (in-cluster — the *client-k8s* role): the same binary as a container image, scheduled **one pod per node** across the cluster (tolerations for all nodes incl. control-plane if desired). Requires host access + `NET_ADMIN`/`NET_RAW` (WireGuard/XDP) + `:53` bind → a documented `ROOT EXCEPTION (approved)`; securityContext otherwise per standards. The DaemonSet manifest is authored in the product Helm chart (P5), but the **requirement + the image build live in P4**.
- **Same binary, two packagings** (not two codebases): the identical Rust artifact ships **naked** (the static binary, for bare-metal/systemd) OR **containerized** (the same binary in an image, for the DaemonSet). One CI build emits both outputs; the two deploy paths can never diverge in behavior.
- Capabilities, each **independently flag-gated** via **Cargo feature flags** (the Rust `xdp`/`noxdp` feature pattern in `backend-rust.md`) + runtime config: **connectivity** (WireGuard/OpenZiti → SASE fabric, node registration via the machine-JWT/enrollment model, Inspection-Point tap) + **netsvcs edge** (local :53 DNS forward/resolve+`threatintel`-filter, DHCP, NTP client). Forwards DNS to `engines/netsvcs-dns` or resolves locally (P4-spec decision).
- Retire `clients/docker` (client-k8s) + `squawk-client-go` into this one agent; the **end-user desktop** stays in `~/code/penguin`.

### P5 — UI + Helm + tests
- Fold Squawk's React (manager/frontend: users/teams→identity, zones/records, DNS-server fleet, IOC feeds→threatintel, analytics) into the tobogganing portal (`portal/src/pages/netsvcs/`), shared `@penguintechinc/react-*` components, per the established portal conventions.
- Author Helm (absent in squawk today) — netsvcs services + optional DHCP/NTP sub-charts (like the SASE analysis sub-charts), digest-pinned, securityContext, Cilium policies. Includes the `node-agent` **DaemonSet** manifest (capability toggles via values) + the bare-metal/systemd install packaging.
- Port/expand Squawk's thin tests to tobogganing standards (90% gate); the parked `dns-server/tests_full_future/` suite is a harvest source.

## Key integration decisions surfaced per-phase (for the phase specs)

- **P1**: the Valkey key-prefix migration (`sase:blocklist:*` → shared `ti:blocklist:*`) vs keeping the prefix for zero-migration; how to name the generalized module without breaking SASE imports (shim vs hard cutover).
- **P2**: mapping Squawk's `team` model + `visibility` (public/internal/restricted/private zones) onto tobogganing's tenant + scope model — split-horizon is a genuinely new capability with no SASE analog.
- **P3**: resolver filtering reads threatintel in-process vs over gRPC `CheckIOC` (the data plane is a separate service — likely a pulled-artifact + local cache like the SWG radix, not per-query gRPC).
- **P4 (node-agent, Rust)**: does the agent resolve+filter DNS locally (`hickory-dns`) or forward to `engines/netsvcs-dns`; the connectivity-vs-netsvcs capability toggling mechanism (Cargo **feature flags**, mirroring the Rust `xdp`/`noxdp` feature pattern in `backend-rust.md`, vs pure runtime config); DaemonSet securityContext + required caps (NET_ADMIN/NET_RAW for WireGuard/XDP + `:53` bind — documented ROOT/cap exception); AF_XDP/`aya` maturity check for the target throughput; how the bare-metal/systemd installer is packaged (single static musl binary); final name (`node-agent` vs `hub-agent`/`server-agent`); port order off the existing Go `clients/docker` + `squawk-client-go`.

## Non-goals (this program)

- No Rust rewrite of the **control-plane API** or the **DNS resolver service** — both stay Python/Quart (decision #2). This is distinct from the **node-agent**, which IS Rust (decision #8).
- No preservation of the 3 legacy DNS codebases / py4web console / Python client (decision #5).
- No new threat-intel store forked from SASE (decision #1).
- No change to the end-user desktop agent (stays in `~/code/penguin`) — only the **server/node** agents merge (decision #7).
- The node-agent is NOT kept/written in Go — it is Rust, porting the existing Go (decision #8). (The central resolver *service* staying Python per decision #2 is separate — a service, not the agent.)

## Verification (program-level)

Each phase lands green on its own (suite parity, boot, audit-imports boundary `threatintel ⊥ {sase,netsvcs}` consumers-only, per-service flag independence tested). P1 must preserve all existing SASE tests (it refactors shipped code). The program is complete when netsvcs (DNS+DHCP+NTP) is flag-gated-independently, DNS filtering reads `threatintel`, SASE consumes the same `threatintel`, and the legacy Squawk codebases are gone.

## Next step

Write the **P1 (`threatintel` extraction) spec** first — it's the load-bearing refactor of shipped SASE code that everything else builds on — then P2 (netsvcs control plane). P0 is a short scoping/import-manifest task that can precede P1.
