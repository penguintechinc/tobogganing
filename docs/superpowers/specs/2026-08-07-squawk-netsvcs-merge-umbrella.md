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

Merge the Squawk DNS product into tobogganing as network-services (`netsvcs`), following the established WaddlePerf pattern (control plane → `hub_api/modules/`, data plane → `engines/` + Go agent). Squawk is a **DoH resolver + threat-intel DNS filtering + authoritative split-horizon custom zones + DHCP + NTP + a Go edge agent + control plane** — a multi-phase program, not a single merge.

## Locked decisions (from brainstorming)

1. **Threat-intel becomes its own shared module.** Do NOT converge Squawk's IOC onto SASE, and do NOT keep two stores. Instead **extract** the existing SASE `feeds/` + `blocklist/` into a standalone **`threatintel`** module, harvest Squawk's MISP/STIX/TAXII/OpenIOC feed parsers into it, and make **SASE (SWG/enforcement) AND netsvcs (DNS filtering) both consumers**. One threat-intel pipeline + store (`sase:blocklist:*` → generalized), leveraged by all products.
2. **Resolver stays Python for now.** Land the existing Quart DoH resolver agent as the netsvcs DNS data plane; keep the Go `:53` edge forwarder. Rewrite in Go/Rust ONLY on a measured throughput need (>10K rps) — not up front (YAGNI).
3. **Full suite in scope**: DNS + DHCP + NTP. netsvcs is the complete network-services module.
4. **DHCP and NTP are INDEPENDENT feature flags.** Each netsvcs service (DNS, DHCP, NTP) is separately flag-gated + tiered, so operators enable them independently: `tobogganing.netsvcs.dns.*`, `tobogganing.netsvcs.dhcp.*`, `tobogganing.netsvcs.ntp.*`.
5. **Discard the legacy.** Squawk has 3 overlapping DNS codebases (legacy `dns-server/bins` monolith, a Flask variant, the new `dns-server/app` Quart agent) + a py4web console + a legacy Python client. Base the merge on the **new `manager/` control plane + `dns-server/app` agent + `squawk-client-go`**; discard the rest (harvest only the MISP/STIX/TAXII/OpenIOC parsers from `bins/ioc_manager.py` into `threatintel`).
6. **Replace bespoke auth.** Squawk's `auth_user`/`team`/`token` + hand-rolled PyJWT → dropped; remap onto tobogganing's single `users` identity table + tenant model + existing token/JWT issuance (penguin-aaa/penguin-dal). Squawk's per-DNS-server join-key/JWT fleet-registration maps onto the machine-JWT/enrollment model already built (auth redesign + `docs/architecture/headend-machine-jwt-contract.md`).

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
├── netsvcs-dns/        # Python Quart DoH/DoT resolver agent (from dns-server/app); reads threatintel for filtering
├── netsvcs-dhcp/       # DHCP server
└── netsvcs-ntp/        # NTP/NTS server
clients/ (or penguin desktop): squawk-client-go → the edge agent (:53 forwarder + DHCP + NTP clients)
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

### P3 — DNS data plane
- `engines/netsvcs-dns/` — the Quart DoH/DoT/HTTP3 resolver agent (`dns-server/app`): registers with the control plane, syncs zones + config over gRPC, resolves (forward + custom-zone answers), and enforces filtering by reading `threatintel` (blocklist + SWG category verdicts). Debian-slim rebuild (Squawk is Ubuntu today).
- `squawk-client-go` `:53` edge forwarder lands as the client edge component (DoH forward + local policy). Repo placement per `client.md` (product repo vs penguin desktop) — decide in P3 spec.

### P4 — DHCP + NTP (independent flags)
- `engines/netsvcs-dhcp/` + `engines/netsvcs-ntp/` (servers, from `dhcp-server/` + `ntp-server/`); Go DHCP + NTP/NTS clients in the edge agent.
- **Independent flags**: `tobogganing.netsvcs.dhcp.*` and `tobogganing.netsvcs.ntp.*` — each separately enable-able + tiered; DNS works without them and vice versa. Per-service contract registration so enabling one never requires another.

### P5 — UI + Helm + tests
- Fold Squawk's React (manager/frontend: users/teams→identity, zones/records, DNS-server fleet, IOC feeds→threatintel, analytics) into the tobogganing portal (`portal/src/pages/netsvcs/`), shared `@penguintechinc/react-*` components, per the established portal conventions.
- Author Helm (absent in squawk today) — netsvcs services + optional DHCP/NTP sub-charts (like the SASE analysis sub-charts), digest-pinned, securityContext, Cilium policies.
- Port/expand Squawk's thin tests to tobogganing standards (90% gate); the parked `dns-server/tests_full_future/` suite is a harvest source.

## Key integration decisions surfaced per-phase (for the phase specs)

- **P1**: the Valkey key-prefix migration (`sase:blocklist:*` → shared `ti:blocklist:*`) vs keeping the prefix for zero-migration; how to name the generalized module without breaking SASE imports (shim vs hard cutover).
- **P2**: mapping Squawk's `team` model + `visibility` (public/internal/restricted/private zones) onto tobogganing's tenant + scope model — split-horizon is a genuinely new capability with no SASE analog.
- **P3**: resolver filtering reads threatintel in-process vs over gRPC `CheckIOC` (the data plane is a separate service — likely a pulled-artifact + local cache like the SWG radix, not per-query gRPC).
- **P4**: DHCP/NTP repo placement + whether the Go clients live in the product repo or penguin desktop.

## Non-goals (this program)

- No Go/Rust resolver rewrite (decision #2).
- No preservation of the 3 legacy DNS codebases / py4web console / Python client (decision #5).
- No new threat-intel store forked from SASE (decision #1).

## Verification (program-level)

Each phase lands green on its own (suite parity, boot, audit-imports boundary `threatintel ⊥ {sase,netsvcs}` consumers-only, per-service flag independence tested). P1 must preserve all existing SASE tests (it refactors shipped code). The program is complete when netsvcs (DNS+DHCP+NTP) is flag-gated-independently, DNS filtering reads `threatintel`, SASE consumes the same `threatintel`, and the legacy Squawk codebases are gone.

## Next step

Write the **P1 (`threatintel` extraction) spec** first — it's the load-bearing refactor of shipped SASE code that everything else builds on — then P2 (netsvcs control plane). P0 is a short scoping/import-manifest task that can precede P1.
