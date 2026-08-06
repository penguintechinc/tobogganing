# SASE Slice D — Out-of-Band Analysis Adapters (Design Spec)

**Date**: 2026-08-06
**Status**: Design approved; ready for implementation plan
**Cross-references**:
- SASE security design: `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md` ("SASE Traffic-Mirror Hooks", "Detection→Block Feedback Loop")
- Slice A blocklist write-side (merged): `hub_api/modules/sase/security/blocklist/` (`to_stix_indicator`, `Verdict`, `BlocklistStore.put`, `BlocklistCurator.curate_one`)
- Existing Go mirror: `services/hub-router/proxy/mirror/manager.go` (VXLAN/GRE/ERSPAN + Suricata EVE emission)

## Goal

Turn the out-of-band analysis tools' output into blocklist verdicts. Each tool (Suricata, Zeek, Strelka, CAPE, Arkime) gets an **adapter** that parses its native output → normalizes IOCs to STIX 2.1 → writes to the **existing** Slice-A `BlocklistStore` (`sase:blocklist:*`). The tools ship as **optional, off-by-default Helm sub-charts**. Strictly **out-of-band** — adapters read a mirror/log side-channel; nothing here touches the live traffic path (zero added latency; "allow a few through").

## Scope (locked)

- **In**: an adapter base class + framework; per-tool parsers (Suricata EVE, Zeek notice, Strelka YARA/file-scan, CAPE verdict, Arkime session-flag) that emit `Verdict`s into `BlocklistStore`; a poller/scheduler (mirror the feeds asyncio loop / register a scheduler job); optional off-by-default Helm sub-charts for the 5 tools (establish the `dependencies:` + `condition:` pattern — none exists yet); adapter config (mirror destinations, tool endpoints).
- **Out**: changing the Go mirror (`hub-router`) — it already emits to Suricata; D consumes the side-channel; the block-list *enforcement* (data-plane, Slice A's contract); the category/SWG path (Slice B).

## Architecture

The Go mirror already duplicates traffic out-of-band to Suricata (EVE JSON → a log volume with **no consumer today** — that volume is the seam). Adapters run as **sidecars / scheduled pollers** in hub-api's plane: each tails/polls its tool's output on an interval, extracts IOCs (malicious IP/domain/URL/file-hash), and calls the Slice-A write path. Decoupled + async — no inline coupling to live traffic.

**Write path (per the recon, reused verbatim):**
`normalize hit → to_stix_indicator(ioc_type, value, severity=…, source="suricata"|"zeek"|"strelka"|"cape"|"arkime", first_seen=ts) → Verdict(ioc_type, value, severity, source, stix_id=ind.id, first_seen, expiry) → await BlocklistStore(cache).put(verdict)`. Optionally also upsert into `threat_indicators` (as feeds do) so the existing curator re-derives it and hub-api curates/audits centrally.

## Components — `hub_api/modules/sase/security/adapters/`

- `adapters/base.py` — `class AnalysisAdapter(ABC)`: `source: str`; `abstract parse(raw) -> Iterable[AdapterHit]`; concrete `async ingest(raw, store) -> AdapterStats` (parse → normalize → `store.put`, per-hit try/except → skipped++, best-effort). `@dataclass(slots=True) AdapterHit(ioc_type, value, severity, first_seen, detail)`; `@dataclass(slots=True) AdapterStats(source, scanned, stored, skipped)`.
- `adapters/suricata.py` — `SuricataAdapter` — parses **EVE JSON** lines; extracts IOCs from `alert` events (dest IP, TLS/HTTP hostname → domain, http.url → url; `fileinfo.sha256` → hash); maps Suricata alert severity → `SEVERITIES`. (The one with a live data source today.)
- `adapters/zeek.py` — `ZeekAdapter` — parses Zeek `notice.log` / intel hits (TSV or JSON) → IOCs.
- `adapters/strelka.py` — `StrelkaAdapter` — parses Strelka scan events (YARA matches + file `sha256`) → hash IOCs (+ severity from match).
- `adapters/cape.py` — `CapeAdapter` — parses CAPE sandbox verdicts (malscore/verdict + sample sha256 + contacted hosts) → hash + ip/domain IOCs.
- `adapters/arkime.py` — `ArkimeAdapter` — parses Arkime session flags/tags → ip/domain IOCs.
- `adapters/poller.py` — `AdapterPoller(adapter, source_reader, store)` — an interval loop (mirror `feeds/manager.py`): read new tool output (EVE log tail / Zeek log / Strelka|CAPE|Arkime API) → `adapter.ingest`. Registered as a scheduler job OR an always-on sidecar; off unless the tool's flag is on.
- `adapters/config.py` — per-tool config (endpoint/log path/enabled) from env; each tool default **disabled**.

## Helm sub-charts (establish the pattern — greenfield)

Under `k8s/helm/tobogganing/` add the first `dependencies:` block in `Chart.yaml`, one entry per tool, each `condition: <tool>.enabled` defaulting **false** in `values.yaml`; sub-chart stubs (or upstream chart refs, digest-pinned) under `charts/`. Each tool's Deployment carries securityContext per standards (Suricata needs `NET_ADMIN`/`NET_RAW` — a documented ROOT/cap exception). Use the `authoring-helm-charts` skill. **Off by default**; the baseline product ships without them.

## Flags & tier

- Flag `tobogganing.sase.adapters` — **community** (IDS/threat detection is community per the ZScaler-alternative positioning + the existing Suricata/IDS community entitlement); default OFF. Per-tool enable via config, not per-tool flags. Registered in the sase `module()` contract with `Entitlement("sase.adapters","community")`.

## Dependencies

- Parsers are pure Python (json/csv) — **no new pip dependency** for Suricata/Zeek/Arkime. Strelka/CAPE API clients: if a maintained Western client lib exists, pin it with hashes; otherwise call their REST APIs via existing `aiohttp` (preferred — avoids a dependency). Decide per-tool at implementation; default to `aiohttp`.

## Error handling

- Every adapter is **best-effort + fail-soft**: a malformed line/event → `skipped++`, never aborts the run or crashes; a tool being unreachable → logged + retried on the next poll (never blocks). `store.put` is already best-effort (Slice A). Nothing here can affect live traffic (out-of-band mandate — adapters only read side-channels).
- Adapter writes go through the Slice-A namespace-guarded store (`sase:blocklist:*` only).

## Testing

- **Each adapter**: fixture tool output (a captured EVE JSON line, a Zeek notice row, a Strelka YARA event, a CAPE verdict JSON, an Arkime session) → correct `AdapterHit`s (right ioc_type/value/severity); malformed input → `skipped`, no raise; empty → zero hits.
- **Write path**: `adapter.ingest(fixture, store)` populates the blocklist store (`store.check` returns the verdict with `source="suricata"` etc.); severity mapping correct.
- **Poller**: an interval loop calls `ingest` on new output; a tool-unreachable read is caught + retried (no crash).
- **Helm**: `helm lint` + `helm template --set <tool>.enabled=true` renders the sub-chart; default (flags off) renders nothing for the tools; securityContext present; digests pinned.
- Full-suite parity; boot clean; `audit_imports --module sase` clean.

## Sequencing (for the plan)

1. `adapters/base.py` (base + `AdapterHit`/`AdapterStats`) + `adapters/config.py`.
2. `adapters/suricata.py` (the live one — EVE parser) — fully real + tested.
3. `adapters/{zeek,strelka,cape,arkime}.py` — parsers behind the same base, fixture-tested (can be one task or split).
4. `adapters/poller.py` + scheduler/sidecar registration + flag + contract registration.
5. Optional Helm sub-charts (off-by-default) — `authoring-helm-charts` skill.

Single feature branch `feature/sase-adapters` off release. **Disjoint from Slice B** (`adapters/` vs `swg/`) → **implements in parallel with B (Wave 1)**.

## Notes

- No change to the Go mirror or Slice A. D is purely additive — new `adapters/` package + optional sub-charts.
- The Suricata adapter is the immediately-useful one (live EVE output exists); the others become useful when their sub-charts are enabled.
- Central curation/audit stays in hub-api (Slice A's curator) — adapters can optionally also write `threat_indicators` so the curator re-derives + dedups + TTLs centrally.
