# SASE Slice E — OOB AI Tier-2 Categorizer (Design Spec)

**Date**: 2026-08-06
**Status**: Design approved; ready for implementation plan
**Cross-references**:
- SASE security design: `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md` ("Tier 2: Out-of-Band Async AI")
- Slice B SWG (merged): `hub_api/modules/sase/security/swg/` (`_enqueue_uncategorized` hook at `lookup.py:137`; `domain_categories` table migration 0021; `ingest.py` write-back patterns; the dangling `swg.tasks.refresh_categories_daily` handler in `scheduler.py`)
- Shared cache: `CacheClient` (`sase:catcache:*`) — **use the canonical signature** `cache.set("sase:catcache", domain, value=, ttl_seconds=)` (see the SWG catcache signature fix)
- Worker infra: `hub_api/scheduler/` + `hub_api/modules/perftest_c2c/worker/` (Celery over Valkey)

## Goal

Categorize **uncategorized** domains (from Slice B's enqueue hook) out-of-band: a Celery worker securely scrapes page **metadata** (prompt-injection-hardened), runs a **non-generative** classifier to assign a category, and writes back to `domain_categories` + `sase:catcache:*` so the next lookup is a local hit. Strictly out-of-band — never blocks the inline path; a categorization failure just leaves the domain at the tenant default.

## Scope (locked)

- **In**: replace B's `_enqueue_uncategorized` stub with a real Celery enqueue; a **sandboxed fetcher** (SSRF-guarded, no creds/JS, size+time caps); a **metadata-only scraper** (BeautifulSoup); a **non-generative classifier** (sklearn TF-IDF + linear); the categorize worker task + write-back; `swg/tasks.py` (also implementing the currently-dangling `refresh_categories_daily` the B scheduler registered); flag/tier.
- **Out**: no new Alembic migration (reuse `domain_categories` 0021 for write-back — **avoids a migration-number collision with the parallel Slice C**); no LLM (the optional generative tier stays future); no change to B's radix/policy (E just adds rows the radix picks up on rebuild).

## Decisions (locked)

1. **Classifier = sklearn TF-IDF + linear model** (LogisticRegression/LinearSVC), not FastText/DistilBERT. Rationale (from recon + standards): non-generative (cannot be prompt-injected — the core defense), self-contained, BSD-3, cleanly hash-pinnable, a **self-trained joblib artifact we control** (no external model-weight download → clean provenance), deterministic, smallest footprint given the repo has zero ML today. FastText is the noted alternative if language-robustness is later needed; transformers/DistilBERT rejected (heavy, external weights, pin-unfriendly).
2. **Worker = Celery over Valkey** (exists). The hook `.delay()`s a task; no polling.
3. **No new migration** — write-back reuses `domain_categories` (source `"ai"`) + catcache.
4. **Tier = professional** — new flag `tobogganing.sase.swg_ai_categorizer` (mirrors `context_auth`); base `sase.swg` stays community.

## Prompt-injection defense (the explicit requirement — three layers)

1. **Non-generative classifier** — outputs a category label from a fixed set, not free-form text; cannot be instruction-injected. Primary defense.
2. **Metadata-only pre-parse** — BeautifulSoup extracts title, meta description, h1–h3, bounded visible-text snippet; strips `<script>`/`<style>`/event handlers/hidden text. The classifier NEVER sees raw HTML/JS.
3. **Sandboxed fetcher** — SSRF-guarded (reject private/loopback/link-local/reserved IPs, re-check after each redirect — block redirects to internal targets), no cookies/creds, no JS (static fetch), size cap (512 KB) + time cap (5 s), fixed benign User-Agent.

**Blast radius**: a successful trick yields a mis-category (a policy allow/block), not code exec or exfiltration; admin/custom category overrides (Slice B) correct it.

## Components — `hub_api/modules/sase/security/swg/tier2/`

- `fetcher.py` — `async fetch(url) -> bytes|None`: SSRF guard (resolve host → reject non-public IPs; block redirects to private), size+time caps, no creds/cookies/JS, benign UA; returns bounded bytes or None (fetch failure → None, fail-safe). Prefer `httpx` (already pinned) over unpinned aiohttp.
- `scraper.py` — `extract_metadata(html: bytes) -> str`: BeautifulSoup → title + meta description + h1–h3 + bounded visible-text; strip script/style/hidden; return a size-capped text blob. Never returns raw HTML.
- `classifier.py` — `class DomainClassifier`: `classify(text: str) -> tuple[str, float]` (category + confidence) from a loaded joblib TF-IDF+linear model; `MODEL_PATH` config; if the model artifact is absent/unloadable → return `("uncategorized", 0.0)` (fail-safe, never crashes). `CONFIDENCE_THRESHOLD` — below it → `uncategorized` (don't write a low-confidence guess).
- `train.py` — offline training script: builds labeled samples (domains with known categories from `domain_categories` feeds → fetch metadata → label with their category), trains TF-IDF+linear, writes the joblib artifact. A `make`/script target; NOT run at request time. Ships a documented "train the model" step; until trained, the classifier fail-safes to uncategorized (E degrades gracefully — no worse than today).
- `worker.py` / `swg/tasks.py` — Celery task `swg.categorize_domain(domain, tenant)`: `fetch → extract_metadata → classify`; if confident → write-back (`domain_categories` upsert `source="ai"` + `cache.set("sase:catcache", domain, value=, ttl_seconds=86400)`, canonical signature); else record uncategorized. Fail-soft (any error logged, task returns; never retried into a loop). Also implement `refresh_categories_daily` here (the handler B's `scheduler.py` already registered but which has no backing module — fixes that dangling reference; it calls B's `CategoryIngestManager.ingest_all` + triggers a radix rebuild).
- Hook wiring — replace `SwgLookup._enqueue_uncategorized(domain, tenant)` (currently a no-op) with `swg.categorize_domain.delay(domain, tenant)` (guarded: if Celery unavailable, log + no-op — never break the inline lookup).

## Flags & tier

- Flag `tobogganing.sase.swg_ai_categorizer` — **professional**; default OFF. `Entitlement("sase.swg_ai_categorizer","professional")` in the sase `module()`. The enqueue hook checks the flag before dispatching (flag off → no-op, base SWG unaffected).

## Dependencies (all Western/OSS, hash-pinned via `uv pip compile --generate-hashes`; Socket-verified)

- `beautifulsoup4` (MIT) + `httpx` (already pinned) for scrape/fetch.
- `scikit-learn` (BSD-3) + `numpy`/`scipy` (BSD) + `joblib` for the classifier.
- `celery` (BSD) — currently a guarded/unpinned import; pin it.
- No PRC-origin packages; no external model-weight download (model is self-trained + committed or built by the train step).

## Error handling

- Every stage fail-safe: fetch failure/timeout/oversize → None → task ends (domain stays uncategorized, tenant default applies). Classifier model absent → `uncategorized` (E is a no-op until a model is trained — graceful degradation, never a regression vs today). Enqueue when Celery is down → logged no-op (inline lookup never blocks). Cache write uses the canonical namespace-guarded signature; DB write reuses B's tenant-aware upsert.
- SSRF guard is mandatory and tested — a fetch to a private/loopback/link-local target (or a redirect to one) must be refused.

## Testing

- **Fetcher**: rejects private/loopback/link-local/reserved IPs + redirects to them (SSRF); enforces size + time caps; no cookies sent; a normal public URL (mocked transport) returns bytes. (`# regression: SSRF sandbox`)
- **Scraper**: extracts title/meta/h1–h3/text; strips `<script>`/`<style>`/hidden; a page with an injected instruction in a script tag → that text never appears in the extracted metadata; output size-capped.
- **Classifier**: with a tiny fixture model → `classify` returns (category, confidence); below threshold → `uncategorized`; missing model → `("uncategorized",0.0)` no crash. Non-generative: output is always in the fixed category set.
- **Worker**: `categorize_domain` on a confident fixture → writes `domain_categories` (source="ai") + catcache (canonical signature, round-trip via real CacheClient in-memory fallback); low-confidence → no write; fetch failure → no write, no raise. `refresh_categories_daily` invokes ingest without error.
- **Hook**: `_enqueue_uncategorized` dispatches the task when flag ON; flag OFF → no dispatch; Celery-down → no-op, lookup still returns.
- Full-suite parity; boot clean; `audit_imports --module sase` clean.

## Sequencing (for the plan)

1. `fetcher.py` (SSRF-sandboxed) — the security-critical piece; full tests.
2. `scraper.py` (metadata-only, injection-stripping).
3. `classifier.py` + `train.py` (TF-IDF+linear, fail-safe model load).
4. `swg/tasks.py` (categorize_domain task + write-back + `refresh_categories_daily`) + hook wiring + flag + contract registration.
5. Deps pinning (folded into the tasks that introduce each).

Single feature branch `feature/sase-swg-ai` off release. **Independent of Slice C** (`swg/tier2/` vs `blockpages/`; E adds NO migration) → **parallel (Wave 2)**. Only shared file with C is the sase `module()` contract (both add a flag) → combine at rebase (as B/D).

## Notes

- E degrades gracefully: with the flag OFF or no trained model, behavior == today (uncategorized → tenant default). It only ever ADDS categorizations; it never blocks inline traffic (out-of-band mandate).
- E depends on the SWG catcache signature fix (canonical `CacheClient` calls) — land that first so E's write-back actually populates the cache.
- The self-trained model keeps provenance clean (no external weight download) and is the security-preferred choice over downloading third-party model binaries.
