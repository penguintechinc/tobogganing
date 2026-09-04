# SASE Slice B — SWG Category Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`). Executed by `penguin-python-dev` — PenguinTech Python conventions (async, `@dataclass(slots=True)`, type hints, structlog, penguin-dal, Alembic).

**Goal:** Tier-1 SWG — categorized-domain radix lookup + per-tenant/user/group category→action policy, seeded from open category DBs on a daily schedule; Python builds/serves, data-plane enforces (contract).

**Architecture:** Mirrors Slice A. `domain_categories` DB canonical + Valkey `sase:catcache:*` fast-index; a reverse-ordered `RadixTree` built from them, serialized and served (`GET /swg/radix`) for the data plane to pull daily; `SwgLookup` resolves domain→categories→`EnforcementAction` (unified enum) per tenant/user/group; fails **open**.

**Tech Stack:** Python 3.13, `hub_api/cache/CacheClient`, penguin-dal, Alembic, Quart, `aiohttp` (existing), `hub_api/scheduler`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-06-sase-slice-b-swg-design.md` — authoritative.
- Green gate: `python3 -m pytest hub_api/tests/` (baseline **923**, 0 fail) in **batches** (env kills >~120s); `create_app()` boots; `scripts/audit_imports.py --module sase --forbid sdwan,ziti` clean. Clean bytecode first.
- **Commit-completeness (hard):** after each commit `git status --short` empty + `git show HEAD --stat` lists every file; `git check-ignore` every NEW file; after `git push` confirm `git log --oneline -1 origin/<branch>` == your SHA.
- **`lookup` fails OPEN** (miss/cache-error → `allow`) — out-of-band mandate. Ingestion fails soft (per-source try/except; malformed line skipped, counted).
- Unified `EnforcementAction` = {`allow`,`log_only`,`soft_block`,`block`,`drop`}; `isolate` reserved-not-implemented. Custom categories win on conflict; most-restrictive action wins among a domain's categories; scope precedence user>group>tenant.
- Valkey writes confined to `sase:catcache:*` (CacheClient guard). Flag `tobogganing.sase.swg` — community, default OFF, gated via `@require_feature("sase","swg")`.
- **No new pip dependency** — RadixTree implemented in-repo.
- Alembic: read the current migration head at implementation time (`hub_api/migrations/versions/`), chain the new revs after it; declare in the sase `ModuleContract.migrations`.

---

## Task 1: `EnforcementAction` enum + SWG models

**Files:** Create `hub_api/modules/sase/security/enforcement.py`, `hub_api/modules/sase/security/swg/__init__.py`, `swg/models.py`; Test `hub_api/tests/test_sase_swg_models.py`.

**Interfaces:**
- Produces: `class EnforcementAction(str, Enum)` = allow/log_only/soft_block/block/drop (+ `isolate` reserved, with a comment "reserved — not implemented"); `ACTION_SEVERITY` ordering (allow < log_only < soft_block < block < drop) for most-restrictive resolution; `DEFAULT_UNCATEGORIZED = EnforcementAction.allow`. `@dataclass(slots=True)` `DomainCategory`, `CategoryPolicy(... action: EnforcementAction ...)`, `LookupResult(domain, categories: tuple[str,...], action: EnforcementAction, matched_scope: str, uncategorized: bool)`.

- [ ] **Step 1: Write failing test:**

```python
from hub_api.modules.sase.security.enforcement import EnforcementAction, ACTION_SEVERITY, most_restrictive

def test_action_enum_values():
    assert EnforcementAction.block.value == "block"
    assert EnforcementAction.soft_block.value == "soft_block"

def test_most_restrictive():
    assert most_restrictive([EnforcementAction.allow, EnforcementAction.block, EnforcementAction.log_only]) == EnforcementAction.block
    assert most_restrictive([EnforcementAction.drop, EnforcementAction.block]) == EnforcementAction.drop
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `enforcement.py` (enum, `ACTION_SEVERITY` dict, `most_restrictive(actions) -> EnforcementAction` picking the highest severity, `DEFAULT_UNCATEGORIZED`) + `swg/models.py` dataclasses. 2-3 line docstrings.
- [ ] **Step 4: Run → PASS.** **Step 5: Green gate + commit.**

---

## Task 2: `RadixTree` (reverse-ordered domain trie)

**Files:** Create `swg/radix.py`; Test `hub_api/tests/test_sase_swg_radix.py`.

**Interfaces:**
- Produces: `class RadixTree` with `insert(domain: str, categories: tuple[str,...]) -> None`, `lookup(domain: str) -> tuple[str,...]|None` (subdomain-covering: a node for `badsite.com` matches `a.b.badsite.com`), `serialize() -> bytes`, classmethod `deserialize(data: bytes) -> RadixTree`.

- [ ] **Step 1: Write failing tests:**

```python
from hub_api.modules.sase.security.swg.radix import RadixTree

def test_exact_and_subdomain_cover():
    t = RadixTree(); t.insert("badsite.com", ("gambling",))
    assert t.lookup("badsite.com") == ("gambling",)
    assert t.lookup("a.b.badsite.com") == ("gambling",)   # subdomain covered
    assert t.lookup("good.com") is None

def test_more_specific_wins():
    t = RadixTree(); t.insert("shop.com", ("shopping",)); t.insert("evil.shop.com", ("malware",))
    assert set(t.lookup("evil.shop.com")) == {"malware"}   # most-specific node

def test_serialize_roundtrip():
    t = RadixTree(); t.insert("x.com", ("news",))
    t2 = RadixTree.deserialize(t.serialize())
    assert t2.lookup("a.x.com") == ("news",)
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — store domains reversed (`com.badsite`) as label-path in a nested-dict trie; `lookup` walks labels root→leaf and returns the categories of the **deepest** node marked terminal along the path (subdomain-covering + most-specific). `serialize`/`deserialize` via `json.dumps(...).encode()` (compact; the artifact the data plane pulls).
- [ ] **Step 4: Run → PASS.** **Step 5: Green gate + commit.**

---

## Task 3: Category sources + ingestion + `domain_categories` (Alembic) + catcache

**Files:** Create `swg/sources.py`, `swg/ingest.py`, `hub_api/migrations/versions/<next>_swg_domain_categories.py`; Test `hub_api/tests/test_sase_swg_ingest.py` (real-DAL).

**Interfaces:**
- Consumes: penguin-dal, `CacheClient` (`sase:catcache`), `DomainCategory` (T1).
- Produces: `CATEGORY_SOURCES` list (name, url, license, `parse(text) -> Iterable[tuple[str, str]]` domain→category); `CategoryIngestManager(db, cache)` with `async ingest_source(source) -> IngestStats`, `async ingest_all() -> IngestStats`, `async upsert_custom(domain, category, tenant) -> None`. `@dataclass(slots=True) IngestStats(source, scanned, stored, skipped)`.

- [ ] **Step 1:** Read `feeds/sources.py` + `feeds/manager.py` for the fetch/upsert/error-backoff pattern; read the current Alembic head + `0002_sase_firewall_rules.py` for the migration template.
- [ ] **Step 2: Write the Alembic migration** — `domain_categories` (id, domain indexed, category, source, tenant nullable, updated_at; unique-ish on (domain,category,source,tenant)); chain `down_revision` = current head.
- [ ] **Step 3: Write failing tests** (real-DAL, mirror `test_sase_feeds_realdal.py`):

```python
async def test_ingest_populates_categories(real_dal, cache):
    mgr = CategoryIngestManager(real_dal, cache)
    stats = await mgr.ingest_source(_fixture_source([("bad.com","gambling"),("x.com","news")]))
    assert stats.stored == 2
    # catcache written
    assert await cache.get("sase:catcache", "bad.com") is not None

async def test_custom_category_wins_on_conflict(real_dal, cache):
    mgr = CategoryIngestManager(real_dal, cache)
    await mgr.ingest_source(_fixture_source([("shop.com","shopping")]))
    await mgr.upsert_custom("shop.com", "blocked-shopping", tenant="acme")
    # both stored; radix build (T5) resolves custom-wins — here assert both rows present, source distinguishes
    rows = await real_dal(real_dal.domain_categories.domain == "shop.com").select()
    assert any(r.source == "custom" for r in rows)

async def test_malformed_line_skipped_without_crash(real_dal, cache):
    stats = await CategoryIngestManager(real_dal, cache).ingest_source(_fixture_source_with_bad_line())
    assert stats.skipped >= 1   # run completed
```

- [ ] **Step 4: Run → FAIL.**
- [ ] **Step 5: Implement** `sources.py` (the 6 feed sources w/ real URLs + parsers per license — UT1[CC]/blocklistproject[MIT]/cipher-oos/HaGeZi-OISD[CC0]/StevenBlack[MIT]/urlhaus-PhishTank[CC0]; each `parse()` yields domain→category) and `ingest.py` (fetch via aiohttp, upsert into `domain_categories` + write `sase:catcache:<domain>` = categories JSON; per-line try/except → skipped++; per-source try/except; `upsert_custom` with source="custom").
- [ ] **Step 6: Run → PASS.** **Step 7: Green gate** (batch: new test + `test_sase_feeds*.py` untouched + migrations head test) **+ commit.**

---

## Task 4: `CategoryPolicy` manager + `category_policies` (Alembic)

**Files:** Create `swg/policy.py`, `hub_api/migrations/versions/<next+1>_swg_category_policies.py`; Test `hub_api/tests/test_sase_swg_policy.py`.

**Interfaces:**
- Produces: `CategoryPolicyManager(db)` with `async set_policy(tenant, scope, scope_id, category, action) -> None`, `async get_policies(tenant) -> list[CategoryPolicy]`, `async resolve(tenant, categories, *, user_id=None, group_ids=()) -> tuple[EnforcementAction, str]` (returns action + matched_scope; user>group>tenant; `most_restrictive` among matched categories; default `DEFAULT_UNCATEGORIZED` if none).

- [ ] **Step 1:** Alembic migration `category_policies` (id, tenant idx, scope, scope_id, category, action, created_at). `down_revision` = T3's rev.
- [ ] **Step 2: Write failing tests:**

```python
async def test_resolve_scope_precedence(real_dal):
    m = CategoryPolicyManager(real_dal)
    await m.set_policy("acme","tenant",None,"gambling","block")
    await m.set_policy("acme","user","u1","gambling","allow")
    action, scope = await m.resolve("acme", ("gambling",), user_id="u1")
    assert action == EnforcementAction.allow and scope == "user"   # user beats tenant

async def test_resolve_most_restrictive_across_categories(real_dal):
    m = CategoryPolicyManager(real_dal)
    await m.set_policy("acme","tenant",None,"news","allow")
    await m.set_policy("acme","tenant",None,"malware","block")
    action, _ = await m.resolve("acme", ("news","malware"))
    assert action == EnforcementAction.block

async def test_resolve_unknown_category_defaults(real_dal):
    action, scope = await CategoryPolicyManager(real_dal).resolve("acme", ("weird",))
    assert action == EnforcementAction.allow and scope == "default"
```

- [ ] **Step 3: Run → FAIL. Step 4: Implement** `resolve` (query tenant's policies, filter to the domain's categories, pick most-specific scope then `most_restrictive` action). **Step 5: Run → PASS. Step 6: Green gate + commit.**

---

## Task 5: `SwgLookup` (radix + policy + cache, fail-open, uncategorized stub)

**Files:** Create `swg/lookup.py`; Test `hub_api/tests/test_sase_swg_lookup.py`.

**Interfaces:**
- Consumes: `RadixTree` (T2), `CategoryPolicyManager` (T4), `CacheClient`, `IngestManager`'s `domain_categories`/catcache.
- Produces: `SwgLookup(radix, policy_mgr, cache)` with `async lookup(domain, *, tenant, user_id=None, group_ids=()) -> LookupResult`; `build_radix(db) -> RadixTree` (custom-wins-on-conflict merge). A no-op `_enqueue_uncategorized(domain, tenant)` stub (logs "would enqueue for Slice-E").

- [ ] **Step 1: Write failing tests:**

```python
async def test_categorized_domain_resolves_action(lookup_with_seeded_radix):
    r = await lookup.lookup("a.badsite.com", tenant="acme")   # badsite.com→gambling, policy block
    assert r.categories == ("gambling",) and r.action == EnforcementAction.block and not r.uncategorized

async def test_uncategorized_uses_default_and_enqueues(lookup, monkeypatch):
    called = monkeypatch-spy on _enqueue_uncategorized
    r = await lookup.lookup("unknown.example", tenant="acme")
    assert r.uncategorized and r.action == EnforcementAction.allow and called

async def test_lookup_fails_open_on_cache_error(lookup_with_dead_cache):
    r = await lookup.lookup("x.com", tenant="acme")
    assert r.action == EnforcementAction.allow   # no raise
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement** — `build_radix` reads `domain_categories`, merges custom-over-feed, inserts into `RadixTree`; `lookup` tries radix then `sase:catcache`; categories→`policy_mgr.resolve`; none→`uncategorized=True`+`DEFAULT_UNCATEGORIZED` (or tenant override)+`_enqueue_uncategorized`; ANY error → `LookupResult(action=allow)` (fail open). **Step 4: Run → PASS. Step 5: Green gate + commit.**

---

## Task 6: API + flag + contract registration + scheduler

**Files:** Create `swg/api.py`, `swg/scheduler.py`; Modify `hub_api/modules/sase/__init__.py` (flag `tobogganing.sase.swg`, `Entitlement("sase.swg","community")`, blueprint, migrations list); Test `hub_api/tests/test_sase_swg_api.py`.

**Interfaces:**
- Produces: blueprint `sase_swg` `url_prefix="/swg"` — `GET /lookup?domain=` (`LookupResultDTO`), `GET /radix` (serialized artifact + version, `@require_machine_jwt("swg:read")`), `POST /categories` + `GET|PUT /policy` (`@require_scope("sase:write")`). `swg/scheduler.py` registers a daily category-refresh + radix-rebuild job via `register_job_handler`.

- [ ] **Step 1: Write failing tests** — `lookup` returns exact `LookupResultDTO` fields; flag OFF → 402; `radix` needs machine-JWT `swg:read` (add `swg:read` to `CLUSTER_SCOPES` in `machine_claims.py`); policy write needs `sase:write`; invalid domain → 400.
- [ ] **Step 2: Run → FAIL. Step 3: Implement** the blueprint (DTO-dataclass, `@require_feature("sase","swg")`, decorator stack per the blocklist api.py convention), register flag+entitlement+blueprint+migrations in the sase `module()`, add `swg:read` to the cluster machine scope set, and `scheduler.py` (register the daily job handler; the handler calls `ingest_all` + rebuilds the radix artifact into cache/store). **Step 4: Run → PASS. Step 5: Green gate** (batch: new test + `test_sase_module.py` + `test_registry.py` + `test_machine_jwt_issuance.py` (scope add)) + boot (blueprint mounts) **+ commit.**

---

## Task 7: Data-plane enforcement contract doc

**Files:** Create `docs/architecture/sase-swg-enforcement-contract.md`.

- [ ] **Step 1:** Document: the Inspection Point pulls `GET /api/v1/sase/swg/radix` daily (freshclam cadence, machine-JWT `swg:read`), loads it in-memory, does inline O(k) reverse-domain lookup per request → categories → resolves `EnforcementAction` (unified enum) via cached policy, enforces (allow/log_only pass; soft_block interstitial; block RST/403+page; drop silent), **fails open** on miss. Uncategorized → tenant default + async enqueue to Slice-E (future). Action→page-serving is Slice-C. Commit.

---

## Self-Review

- **Spec coverage:** enum→T1; radix→T2; ingestion+catcache+domain_categories→T3; policy→T4; lookup+fail-open+uncategorized-stub→T5; API+flag+scheduler→T6; contract→T7; custom-wins→T3/T5; scope precedence + most-restrictive→T4. All covered.
- **Placeholders:** none — the uncategorized enqueue is an explicit no-op stub (Slice E), not a TODO.
- **Type consistency:** `EnforcementAction`, `most_restrictive`, `RadixTree.{insert,lookup,serialize,deserialize}`, `CategoryIngestManager`, `CategoryPolicyManager.resolve`, `SwgLookup.lookup`, `LookupResult(DTO)` — consistent across tasks.

## Execution

Sequential (2→5 build on each other; 6 needs all). Single feature branch `feature/sase-swg` off release. Independent of Slice D → runs in parallel (Wave 1). `penguin-python-dev` per task; verify commit-completeness + clean-bytecode + full-suite before merge.
