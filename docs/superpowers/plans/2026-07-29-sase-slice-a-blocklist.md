# SASE Slice A — STIX IOC Blocklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`). Executed by `penguin-python-dev` — PenguinTech Python conventions (async, `@dataclass(slots=True)`, type hints, structlog, penguin-dal).

**Goal:** A STIX-2.1-normalized IOC blocklist in Valkey, seeded from the existing `threat_indicators` feeds, readable O(1) by Inspection Points — the shared detection→block store for the SASE loop.

**Architecture:** Canonical STIX 2.1 Indicators (OASIS `stix2` lib) for interchange/audit + a denormalized Valkey fast-index (`sase:blocklist:{ip,domain,url,hash}:<value>` → compact `Verdict`) over the existing `CacheClient`. A curator populates the index from `threat_indicators`; `check()` fails **open**.

**Tech Stack:** Python 3.13, `stix2` (OASIS), `hub_api/cache/CacheClient`, penguin-dal, Quart.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-29-sase-slice-a-blocklist-design.md` — authoritative.
- Green gate: `python3 -m pytest hub_api/tests/` (baseline **899**, 0 fail) in **targeted batches** (env kills >~120s); `create_app()` boots; `scripts/audit_imports.py --module sase --forbid sdwan,ziti` clean. Clean bytecode first: `find hub_api -type d -name __pycache__ -exec rm -rf {} +`.
- **Commit-completeness (hard):** after each commit `git status --short` empty + `git show HEAD --stat` lists every file; `git check-ignore` every NEW file (module lives under `sase/security/blocklist/` — not a `certs/` dir, but verify); after `git push` confirm `git log --oneline -1 origin/<branch>` == your SHA.
- **`check()` fails OPEN** (cache error → `None` → traffic allowed) — out-of-band mandate, never add latency. `put`/`curate` fail soft (log + continue).
- All Valkey keys under `sase:blocklist` namespace (the `CacheClient` guard enforces it). URL keyed by `sha256(url)` to bound key length.
- New dep `stix2`: pin exact version + hash via `uv pip compile --generate-hashes` into `hub_api/requirements.{in,txt}`.
- Flag `tobogganing.sase.blocklist` — community, default OFF.

---

## Task 1: Verdict models + STIX normalizer (+ pin `stix2`)

**Files:**
- Create: `hub_api/modules/sase/security/blocklist/__init__.py`, `models.py`, `stix_normalizer.py`
- Modify: `hub_api/requirements.in` (+`stix2`), `hub_api/requirements.txt` (recompiled with hashes)
- Test: `hub_api/tests/test_sase_blocklist_normalizer.py`

**Interfaces:**
- Produces: `@dataclass(slots=True) Verdict(ioc_type, value, severity, source, stix_id, first_seen, expiry)`; `IOC_TYPES = ("ip","domain","url","hash")`; `SEVERITIES = ("low","medium","high","critical")`; `to_stix_indicator(ioc_type, value, *, severity, source, first_seen) -> stix2.Indicator`.

- [ ] **Step 1: Add + pin `stix2`** — add `stix2` to `requirements.in`; `cd hub_api && uv pip compile requirements.in --generate-hashes -o requirements.txt`; `uv pip install --require-hashes -r requirements.txt` (or `pip install stix2` if uv unavailable, but the committed txt MUST have the hash). Confirm `python3 -c "import stix2; print(stix2.__version__)"`.
- [ ] **Step 2: Write failing test** (`test_sase_blocklist_normalizer.py`):

```python
import stix2
from hub_api.modules.sase.security.blocklist.stix_normalizer import to_stix_indicator

def test_ip_indicator_pattern():
    ind = to_stix_indicator("ip", "1.2.3.4", severity="high", source="spamhaus", first_seen=1000)
    assert ind.pattern == "[ipv4-addr:value = '1.2.3.4']"
    assert "malicious-activity" in ind.labels
    assert stix2.parse(ind.serialize()).id == ind.id   # round-trips

def test_domain_and_hash_and_url_patterns():
    assert to_stix_indicator("domain","bad.com",severity="low",source="ut1",first_seen=1).pattern == "[domain-name:value = 'bad.com']"
    assert to_stix_indicator("hash","a"*64,severity="critical",source="strelka",first_seen=1).pattern == "[file:hashes.'SHA-256' = '%s']" % ("a"*64)
    assert to_stix_indicator("url","http://x/y",severity="medium",source="urlhaus",first_seen=1).pattern == "[url:value = 'http://x/y']"
```

- [ ] **Step 3: Run → FAIL** (module missing).
- [ ] **Step 4: Implement** `models.py` (Verdict dataclass + constants) and `stix_normalizer.py` (`to_stix_indicator` building the pattern per type via `stix2.Indicator(pattern=..., pattern_type="stix", labels=["malicious-activity"], valid_from=<from first_seen>, confidence=<severity→int>, external_references=[stix2.ExternalReference(source_name=source)])`). Map severity→confidence (low=15/med=50/high=75/crit=95). 2-3 line docstrings.
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Green gate** (batch: new test; then `test_sase_feeds*.py` untouched) + commit.

---

## Task 2: `BlocklistStore` over `CacheClient`

**Files:**
- Create: `hub_api/modules/sase/security/blocklist/store.py`
- Test: `hub_api/tests/test_sase_blocklist_store.py`

**Interfaces:**
- Consumes: `CacheClient` (`get/set/delete("sase:blocklist", *parts, ..., fail_closed=)`), `Verdict` (T1).
- Produces: `BlocklistStore(cache)` with `async put(verdict) -> None`, `async check(ioc_type, value) -> Verdict|None`, `async remove(ioc_type, value) -> None`; `_key(ioc_type, value)` (url → `sha256(value)`).

- [ ] **Step 1: Write failing tests:**

```python
@pytest.mark.asyncio
async def test_put_check_roundtrip(store):
    await store.put(Verdict("ip","1.2.3.4","high","spamhaus","indicator--x",1000,None))
    v = await store.check("ip","1.2.3.4")
    assert v.severity == "high" and v.source == "spamhaus"

@pytest.mark.asyncio
async def test_dedup_higher_severity_wins(store):
    await store.put(Verdict("domain","b.com","low","a","id1",1,None))
    await store.put(Verdict("domain","b.com","critical","b","id2",2,None))
    assert (await store.check("domain","b.com")).severity == "critical"

@pytest.mark.asyncio
async def test_check_fails_open_on_cache_error(store_with_dead_cache):
    assert await store_with_dead_cache.check("ip","9.9.9.9") is None   # no raise

@pytest.mark.asyncio
async def test_url_keyed_by_hash(store):
    await store.put(Verdict("url","http://x/"+ "a"*500,"high","urlhaus","id",1,None))
    assert await store.check("url","http://x/"+ "a"*500) is not None
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `BlocklistStore`: serialize `Verdict` to JSON for the value; `put` reads any existing entry and keeps the higher `SEVERITIES.index` (tie → newer `first_seen`); TTL from `expiry` (`ttl_seconds = expiry - now` if set). `check` uses `cache.get(..., fail_closed=False)` wrapped so ANY error → `None` (fail open). `_key`: url → `hashlib.sha256(value.encode()).hexdigest()`, else the raw value.
- [ ] **Step 4: Run → PASS** (use a `CacheClient` on an unreachable port for the fail-open test; for roundtrip use the in-memory fallback path — study `test_cache_client.py`).
- [ ] **Step 5: Green gate** + commit.

---

## Task 3: `BlocklistCurator` from `threat_indicators`

**Files:**
- Create: `hub_api/modules/sase/security/blocklist/curator.py`
- Test: `hub_api/tests/test_sase_blocklist_curator.py`

**Interfaces:**
- Consumes: penguin-dal `threat_indicators` table (read the existing schema in `feeds/models.py` for column names — `indicator_type`, `value`, `severity`, `source`, timestamps), `BlocklistStore` (T2), `to_stix_indicator` (T1).
- Produces: `BlocklistCurator(dal, store)` with `async curate() -> CurationStats`, `async curate_one(row) -> bool`; `@dataclass(slots=True) CurationStats(scanned, stored, deduped, skipped)`.

- [ ] **Step 1: Read** `feeds/models.py` + `feeds/manager.py` to learn the exact `threat_indicators` columns + how `feeds` maps its indicator types to the `ioc_type` set (`ip`/`domain`/…). Map feed indicator_type → blocklist IOC_TYPES; skip unmappable with a warning.
- [ ] **Step 2: Write failing tests** (real-DAL, mirror `test_sase_feeds_realdal.py`):

```python
@pytest.mark.asyncio
async def test_curate_populates_store(real_dal, store):
    # seed 2 threat_indicators rows (ip high, domain low)
    stats = await BlocklistCurator(real_dal, store).curate()
    assert stats.stored == 2
    assert (await store.check("ip", "<seeded-ip>")).severity == "high"

@pytest.mark.asyncio
async def test_curate_dedups_same_ioc(real_dal, store):
    # seed two rows same domain, low then critical
    await BlocklistCurator(real_dal, store).curate()
    assert (await store.check("domain","<d>")).severity == "critical"

@pytest.mark.asyncio
async def test_curate_skips_malformed_without_crashing(real_dal, store):
    # seed a row with an unmappable indicator_type
    stats = await BlocklistCurator(real_dal, store).curate()
    assert stats.skipped >= 1   # run completed, did not raise
```

- [ ] **Step 3: Run → FAIL.**
- [ ] **Step 4: Implement** `curate()`: select active `threat_indicators` rows, map each to `(ioc_type, value, severity, source, first_seen)`, `to_stix_indicator(...)` → `stix_id`, build `Verdict`, `await store.put(...)`; count stats; wrap each row in try/except → `skipped += 1` on error (never abort the run). `curate_one(row)` for the feed-ingest hook. Log a masked summary.
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Green gate** + commit.

---

## Task 4: Flag + read-API + sase contract registration

**Files:**
- Create: `hub_api/modules/sase/security/blocklist/api.py` (read-only `GET /api/v1/sase/blocklist/check`)
- Modify: `hub_api/modules/sase/__init__.py` (add `tobogganing.sase.blocklist` flag + entitlement community; register the blueprint)
- Test: `hub_api/tests/test_sase_blocklist_api.py`

**Interfaces:**
- Consumes: `BlocklistStore`, `require_scope`/flag-gate, `app.config["CACHE"]`.
- Produces: `GET /api/v1/sase/blocklist/check?type=&value=` → `200 {verdict DTO}` or `404` if not blocklisted / flag OFF.

- [ ] **Step 1: Write failing tests** — check endpoint returns the verdict DTO (typed, exact field set — output-validation rule); unknown IOC → 404; flag OFF → 404/disabled; invalid `type` → 400.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the blueprint (flag-gated via `feature_enabled("tobogganing.sase","blocklist")`, `require_scope` for read), returning a typed DTO (dataclass/`@validate_response`), never the raw Verdict internals beyond the declared fields. Add the flag + `Entitlement("sase.blocklist","community")` + the blueprint to the sase `module()` contract.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Green gate** (batch: new test + `test_sase_module.py` + `test_registry.py`) + boot check (blueprint mounts) + commit.

---

## Task 5: Enforcement-contract doc

**Files:**
- Create: `docs/architecture/sase-blocklist-enforcement-contract.md`

- [ ] **Step 1:** Document how the Go/Rust Inspection Point reads `sase:blocklist:*` (read-only ACL on that prefix) from the shared Valkey, checks per-flow IOCs (dest IP/domain, requested URL sha256, file hash) against the store, enforces on **future** traffic only (no per-request gRPC), and **fails open** on miss/outage. Note the verdict→action mapping is Slice-B policy. Commit.

---

## Self-Review

- **Spec coverage:** two representations→T1+T2; store `sase:blocklist:*` + fail-open→T2; curator from feeds→T3; flag/read-API/contract→T4; enforcement contract→T5; `stix2` dep→T1. All covered.
- **Placeholders:** none — the read-API is a concrete endpoint, not a maybe.
- **Type consistency:** `Verdict`, `to_stix_indicator`, `BlocklistStore.{put,check,remove}`, `BlocklistCurator.{curate,curate_one}`, `CurationStats` — consistent across tasks.

## Execution

Sequential (2 needs 1; 3 needs 2; 4 needs 2). Single feature branch `feature/sase-blocklist` off release (or a short stack). Dispatch `penguin-python-dev` per task; verify commit-completeness + clean-bytecode + full-suite before merge.
