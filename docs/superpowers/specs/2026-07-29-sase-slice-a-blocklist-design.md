# SASE Slice A — STIX-Normalized IOC Blocklist (Design Spec)

**Date**: 2026-07-29
**Status**: Design approved; ready for implementation plan
**Cross-references**:
- SASE security design: `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md` ("Detection→Block Feedback Loop")
- Shared cache: `hub_api/cache/` (`CacheClient`, namespaces `sase:blocklist:*`, `sase:catcache:*`)
- Existing feeds: `hub_api/modules/sase/security/feeds/` (real ingestion → `threat_indicators` table)

## Goal

Stand up the shared **detection→block store** the whole SASE loop depends on: a STIX-2.1-normalized IOC blocklist in Valkey that analysis adapters (Slice D) will WRITE, Inspection Points (future Go/Rust data plane) will READ and enforce on future traffic, and hub-api CURATES. Slice A seeds it from the **existing real `feeds/` ingestion** so it is useful immediately and Slices B–E plug into a ready store.

## Scope (locked)

- **In**: STIX normalizer (OASIS `stix2` lib), `BlocklistStore` over `CacheClient`, a curator that populates the store from the existing `threat_indicators` table, a Python `check()` read-API, and an enforcement-contract doc for the data plane.
- **Out** (later slices / future): the Go/Rust Inspection Point enforcement itself (documented contract only); the analysis-adapter *writers* (Slice D); the category cache `sase:catcache:*` and SWG filtering (Slice B); enforcement *actions* and block pages (Slice B/C). Slice A stores "this IOC is malicious + provenance," NOT what to do about it (action = policy, decided at enforcement time).

## Architecture — two representations, one source of truth

1. **Canonical: STIX 2.1 Indicator** (via `stix2` lib) — interchange/audit format; the reason the SASE spec chose STIX (MISP/TAXII/feed interop). Persisted for audit; NOT read per-packet.
2. **Denormalized: Valkey fast-index** — O(1) enforcement reads, keyed by IOC value:
   - `sase:blocklist:ip:<ip>` · `sase:blocklist:domain:<domain>` · `sase:blocklist:url:<url-sha256>` · `sase:blocklist:hash:<sha256>`
   - value = compact JSON `Verdict{ioc_type, value, severity, source, stix_id, first_seen, expiry}` (no action field — action is Slice-B policy).

Data flow: `threat_indicators` (feeds, exists) → `curator` → `stix_normalizer` (canonical Indicator + `stix_id`) → `BlocklistStore.put` (compact Verdict into Valkey, dedup + TTL) → `BlocklistStore.check(ioc_type, value)` (read-API; the Go Inspection Point reads the same keys directly).

## Components — `hub_api/modules/sase/security/blocklist/`

- `models.py` — `@dataclass(slots=True) Verdict(ioc_type: str, value: str, severity: str, source: str, stix_id: str, first_seen: int, expiry: int|None)`; `IOCType` = {"ip","domain","url","hash"}; `Severity` = {"low","medium","high","critical"}.
- `stix_normalizer.py` — `to_stix_indicator(ioc_type, value, *, severity, source, first_seen) -> stix2.Indicator` building the correct STIX pattern per type: `[ipv4-addr:value = '<ip>']`, `[domain-name:value = '<d>']`, `[url:value = '<u>']`, `[file:hashes.'SHA-256' = '<h>']`; `labels=["malicious-activity"]`, `confidence` from severity, `external_references` = the feed source. Returns the object (its `.id` is the `stix_id`).
- `store.py` — `BlocklistStore(cache: CacheClient)`: `async put(verdict) -> None` (dedup: if an entry exists for the same IOC value, keep the higher severity / newer `first_seen`; set TTL from `expiry`), `async check(ioc_type, value) -> Verdict|None`, `async remove(ioc_type, value)`. All keys under the `sase:blocklist` namespace (URL keyed by `sha256(url)` to bound key length). `check` uses `fail_closed=False` (a cache blip must NOT block traffic — availability over catching one packet, per the out-of-band mandate; a missed lookup fails **open**).
- `curator.py` — `BlocklistCurator(dal, store, normalizer)`: `async curate() -> CurationStats` reads active rows from `threat_indicators`, normalizes each, `put`s the Verdict, dedups, applies TTL/expiry, writes an audit summary; a `curate_one(indicator)` hook the feed-ingest path calls on new indicators. TTL default from indicator age / a configurable window; expired entries drop naturally (Valkey TTL) + a sweep prunes the canonical audit.
- `api/blocklist.py` (optional, flag-gated) — a read-only admin endpoint `GET /api/v1/sase/blocklist/check?type=&value=` returning the verdict (for hub-webui / debugging). Response through a typed DTO (per the output-validation rule).

## Feature flag & tier

- Flag `tobogganing.sase.blocklist` — **community** (it extends the existing community `threat_feeds`); default OFF until validated. Registered in the sase module contract.
- No new license entitlement (community).

## Dependency

- `stix2` (OASIS) — pin exact version with hash via `uv pip compile --generate-hashes` into `hub_api/requirements.{in,txt}`. Western/OASIS-maintained (supply-chain OK).

## Enforcement contract (doc, `docs/architecture/sase-blocklist-enforcement-contract.md`)

The Go/Rust Inspection Point (future) reads `sase:blocklist:*` directly from the shared Valkey (per-service key-prefix ACL, read-only on that prefix), checks each flow's IOCs (dest IP/domain, requested URL, downloaded file hash) against the store, and enforces on **future** traffic only — decoupled/async, **no per-request gRPC to hub-api**. The verdict→action mapping (drop/reject/soft-block/log-only) is **policy** resolved separately (Slice B). A cache miss/outage **fails open** (out-of-band mandate: never add latency, "allow a few through").

## Error handling

- `check` fails open on cache error (returns None → traffic allowed). `put`/`curate` fail soft (log + continue; a curation error must not crash feed ingestion). Namespace guard (`CacheClient`) rejects any write outside `sase:blocklist:*`. Invalid IOC (unparseable IP/hash) → skipped with a logged warning, never a crash.
- Valkey at-rest encryption is the deployment baseline (same shared Valkey as the auth revocation store) — noted in Helm values, not code.

## Testing

- **Normalizer**: each IOC type → a valid `stix2.Indicator` with the correct pattern (assert `pattern` string + `stix2.parse` round-trips); severity→confidence mapping.
- **Store**: `put`+`check` round-trip per IOC type; dedup keeps higher severity; TTL/expiry honored (put with short TTL → gone after); URL keyed by hash; namespace guard rejects cross-prefix; `check` fails open when cache unavailable (returns None, no raise).
- **Curator**: seeded `threat_indicators` rows → `curate()` populates the store; two indicators for the same IOC → higher severity wins; expired indicator → not stored (or TTL'd); a malformed row is skipped without aborting the run; `CurationStats` counts.
- **Read-API** (if built): `check` endpoint returns the verdict DTO; unknown IOC → 404/empty; flag OFF → 404/disabled.
- Full-suite parity; ≥ current baseline; boot clean.

## Sequencing (for the plan)

1. `models.py` + `stix_normalizer.py` (+ pin `stix2`) — no store yet.
2. `BlocklistStore` (`store.py`) on `CacheClient`.
3. `BlocklistCurator` (`curator.py`) reading `threat_indicators`.
4. Flag + optional read-API + sase contract registration.
5. Enforcement-contract doc.

Each an independently testable commit; a single feature branch (or a short stack). Curator depends on store; store depends on models/normalizer.

## Notes

- No change to the existing `feeds/` ingestion behavior — the curator *reads* `threat_indicators`; it does not alter how feeds populate that table.
- The Valkey blocklist is the same shared instance/`CacheClient` as the auth revocation store — different namespace (`sase:blocklist:*` vs `auth:*`), enforced by the namespace guard.
- Future: Slice D adapters call `curate_one`/`store.put` with adapter verdicts (Suricata/Strelka/CAPE); Slice B adds the category cache + action policy on top of the same store.
