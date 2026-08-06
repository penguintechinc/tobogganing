# SASE Slice B — SWG Tier-1 Category Filter + Enforcement Actions (Design Spec)

**Date**: 2026-08-06
**Status**: Design approved; ready for implementation plan
**Cross-references**:
- SASE security design: `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md` ("URL / Domain Category Filtering", "Enforcement Actions")
- Slice A blocklist (merged): `hub_api/modules/sase/security/blocklist/`
- Shared cache: `hub_api/cache/` (`CacheClient`, namespace `sase:catcache:*`)
- Feeds ingestion pattern: `hub_api/modules/sase/security/feeds/manager.py`

## Goal

Tier-1 Secure Web Gateway: categorized-domain lookup (O(k) radix) + a per-tenant/user/group **category→action** policy, seeded from open category databases on a freshclam-style daily schedule. The fast inline tier (~95% of traffic). Mirrors Slice A's shape — **Python ingests + builds + serves + exposes a `lookup` API; the hot-path inline lookup + enforcement is a documented data-plane contract**. The AI Tier-2 for uncategorized domains is **Slice E** (B only tags `Uncategorized`, applies the tenant default, and leaves an enqueue hook).

## Scope (locked)

- **In**: `EnforcementAction` enum (shared; C reuses), category-DB ingestion (extend feeds machinery), `domain_categories` store (DB canonical + Valkey `sase:catcache:*` fast-index), reverse-ordered radix builder + serializable artifact, custom categories (admin-defined, win on conflict), `CategoryPolicy` (category→action, per tenant/user/group), freshclam daily scheduler, `lookup` + `radix artifact` APIs, data-plane enforcement contract doc.
- **Out** (later slices): the inline data-plane enforcement itself (contract only); the AI Tier-2 categorizer (Slice E — B leaves the `Uncategorized`→enqueue hook); block-page rendering + routing (Slice C — B's action just names what fires); analysis adapters (Slice D).

## Action model (locked)

**One unified `EnforcementAction` enum**, in `hub_api/modules/sase/security/enforcement.py` (shared so Slice C + the data-plane contract reference one field):

| action | meaning |
|--------|---------|
| `allow` | permit |
| `log_only` | permit + record (monitor/baseline) |
| `soft_block` | bypassable interstitial ("risky site", acknowledge to continue) — spec's "warn" |
| `block` | deny with an active response (TCP RST / HTTP 403 + block page) — spec's "reject" |
| `drop` | silently drop, no response to client |

`isolate` (route to sandboxed/segmented access) is **deferred** — it needs data-plane network segmentation that doesn't exist yet; reserved as a future enum member, not implemented.

## Components — `hub_api/modules/sase/security/swg/`

- `hub_api/modules/sase/security/enforcement.py` (shared) — `class EnforcementAction(str, Enum)` with the 5 members above; `DEFAULT_UNCATEGORIZED = EnforcementAction.allow` (tenant may override to `block` = fail-closed).
- `swg/models.py` — `@dataclass(slots=True) DomainCategory(domain, categories: tuple[str,...], source, updated_at)`; `@dataclass(slots=True) CategoryPolicy(id, tenant, scope, scope_id, category, action: EnforcementAction, created_at)` (`scope` ∈ {"tenant","group","user"}); `@dataclass(slots=True) LookupResult(domain, categories, action, matched_scope, uncategorized: bool)`.
- `swg/sources.py` — category feed source registry (URL + license + parser) for UT1[CC], blocklistproject[MIT], cipher-oos, HaGeZi/OISD[CC0], StevenBlack[MIT], urlhaus/PhishTank[CC0]. Each maps its lists → `(domain, category)` pairs. Mirrors `feeds/sources.py`.
- `swg/ingest.py` — `CategoryIngestManager(db)` — extends the feeds asyncio-loop pattern (`feeds/manager.py`): per-source daily fetch → upsert into `domain_categories` (DB) + write `sase:catcache:*` fast-index entries. Custom categories (admin-defined via API) upserted with a `source="custom"` that **wins on conflict** during radix build.
- `swg/radix.py` — `RadixTree` reverse-ordered domain trie (`com.badsite.gambling`): `insert(domain, categories)`, `lookup(domain) -> categories|None` (O(k), subdomain-covering — a match on `com.badsite` covers `x.badsite.com`), `serialize() -> bytes` / `deserialize(bytes)`. `build_from_store(db) -> RadixTree`.
- `swg/policy.py` — `CategoryPolicyManager(db)` — CRUD for `CategoryPolicy` (tenant-scoped); `resolve(tenant, categories, *, user_id, group_ids) -> EnforcementAction` (most-specific scope wins: user > group > tenant; among a domain's categories, the most-restrictive action wins; custom-category policy overrides).
- `swg/lookup.py` — `SwgLookup(radix, policy_mgr, cache)` — `async lookup(domain, *, tenant, user_id, group_ids) -> LookupResult`: radix (or `sase:catcache:*`) → categories; if none → `uncategorized=True` + tenant default action + (Slice-E) enqueue hook (a no-op stub in B); else `policy_mgr.resolve(...)`. Fails **open** (miss/cache-error → `allow`) per the out-of-band mandate.
- `swg/api.py` — blueprint `url_prefix="/swg"`:
  - `GET /api/v1/sase/swg/lookup?domain=` → `LookupResultDTO` (typed, exact fields) — `@require_tenant` + `@require_scope("sase:read")` + `@require_feature("sase","swg")`.
  - `GET /api/v1/sase/swg/radix` → the serialized radix artifact + `version`/etag — `@require_machine_jwt("swg:read")` (the data plane pulls this daily).
  - `POST /api/v1/sase/swg/categories` (custom category upsert) + `PUT/GET /api/v1/sase/swg/policy` (category→action policy) — `@require_scope("sase:write")` + governance.
- `swg/scheduler.py` — register a freshclam-style daily job (via `hub_api/scheduler` `register_job_handler` or the feeds asyncio loop) that refreshes category feeds + rebuilds the radix artifact. Same daily cadence covers A's threat feeds + future ClamAV.

## Alembic

New migration (next sequential rev after the current head — read the head at implementation time, do not hardcode): tables `domain_categories` (domain PK-ish, categories, source, tenant nullable for global vs custom, updated_at; indexed on domain + source) and `category_policies` (id, tenant, scope, scope_id, category, action, created_at; indexed on tenant + category). Declared in the sase `ModuleContract.migrations`.

## Flags & tier

- Flag `tobogganing.sase.swg` — **community** (SWG is core product per the ZScaler-alternative positioning); default OFF until validated. Registered in the sase `module()` contract with `Entitlement("sase.swg","community")`.
- Optional commercial feed (spec) = Enterprise — **out of scope** for this slice (a future entitlement).

## Dependencies

- A pure-Python radix/trie: **implement in-repo** (`swg/radix.py`) rather than add a dependency — the structure is simple (reverse-ordered domain trie) and avoids a supply-chain add; the spec's LMDB/Cuckoo alternatives are noted as future scaling, not needed now.
- Category feed fetching reuses the existing `aiohttp` already in feeds. No new external dependency.

## Data flow

`category DBs` → `CategoryIngestManager` (daily) → `domain_categories` (DB) + `sase:catcache:*` (Valkey) → `RadixTree.build_from_store` → serialized artifact (`GET /swg/radix`, data plane pulls daily) + `SwgLookup` (API + the same lookup the data plane does inline). Policy: `category → EnforcementAction` resolved per tenant/user/group at lookup time.

## Error handling

- `lookup` fails **open** (`allow`) on radix miss or cache error — never add latency (out-of-band mandate; "allow a few through"). Custom categories win on conflict; most-restrictive action wins among a domain's categories.
- Ingestion fails soft (per-source try/except + error backoff, mirror feeds) — one bad feed never aborts the run or crashes the app. Malformed feed lines skipped with a logged count.
- Namespace guard (`CacheClient`) confines writes to `sase:catcache:*`.
- Uncategorized → tenant default (fail-open `allow` or fail-closed `block`); the Slice-E enqueue hook is a no-op stub in B (logs "would enqueue").

## Testing

- **Radix**: insert + subdomain-covering lookup (`com.badsite` covers `a.b.badsite.com`); serialize→deserialize round-trip; custom category overrides a feed category; miss → None.
- **Ingest**: fixture category lists → `domain_categories` populated + `sase:catcache:*` written; custom category upsert wins on conflict; malformed line skipped without aborting; per-source failure isolated.
- **Policy**: `resolve` — user scope beats group beats tenant; most-restrictive action among multiple categories; custom-category policy override; unknown category → tenant default.
- **Lookup**: categorized domain → categories + resolved action; uncategorized → tenant default + enqueue-hook called (stub); fail-open on cache error (returns `allow`, no raise).
- **API**: `lookup` returns the exact DTO field set; flag OFF → 402 (house `@require_feature` convention); `radix` artifact requires machine-JWT `swg:read`; custom-category/policy write requires `sase:write`; invalid domain → 400.
- Full-suite parity ≥ current baseline; boot clean; `audit_imports --module sase` clean.

## Sequencing (for the plan)

1. `enforcement.py` (shared enum) + `swg/models.py`.
2. `swg/radix.py` (RadixTree, serialize).
3. `swg/sources.py` + `swg/ingest.py` (+ Alembic `domain_categories`) + `sase:catcache:*`.
4. `swg/policy.py` (+ Alembic `category_policies`).
5. `swg/lookup.py` (ties radix + policy + cache; fail-open; uncategorized stub).
6. `swg/api.py` + flag + contract registration + `swg/scheduler.py`.
7. Data-plane enforcement contract doc.

Single feature branch `feature/sase-swg` (or short stack). Independent of Slice D (disjoint module) → **implements in parallel with D (Wave 1)**.

## Notes

- No change to Slice A / existing feeds behavior. `sase:catcache:*` and `sase:blocklist:*` share the one Valkey via the namespace-guarded `CacheClient`.
- The `EnforcementAction` enum is the seam Slice C (block pages, per-source routing) and the data-plane contract both key off — defining it here avoids C re-deriving it.
- Slice E (AI Tier-2) plugs into the `uncategorized` hook + writes back to `sase:catcache:*` + the radix — B leaves that hook and the write-back path ready.
