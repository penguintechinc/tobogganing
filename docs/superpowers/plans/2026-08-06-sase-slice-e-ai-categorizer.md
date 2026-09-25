# SASE Slice E — OOB AI Tier-2 Categorizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`). Executed by `penguin-python-dev`.

**Goal:** Categorize uncategorized domains out-of-band — sandboxed metadata scrape + non-generative sklearn classifier → write back to `domain_categories` (source="ai") + `sase:catcache:*`; replaces Slice B's `_enqueue_uncategorized` stub. Never blocks inline traffic.

**Architecture:** `swg/tier2/` — SSRF-sandboxed `fetcher`, BeautifulSoup metadata `scraper`, TF-IDF+linear `classifier` (self-trained joblib, fail-safe), Celery `categorize_domain` task + write-back; hook wiring; professional flag. No new Alembic migration.

**Tech Stack:** Python 3.13, httpx (pinned), beautifulsoup4, scikit-learn/numpy/scipy/joblib, celery, `CacheClient` (canonical signature), penguin-dal.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-06-sase-slice-e-ai-categorizer-design.md` — authoritative.
- Green gate: `python3 -m pytest hub_api/tests/` (baseline after catcache-fix + Wave-2 start; ~980+, 0 fail) in batches; `create_app()` boots; `scripts/audit_imports.py --module sase --forbid sdwan,ziti` clean. Clean bytecode first.
- **Commit-completeness (hard):** `git status --short` empty + `git show HEAD --stat` after each commit; `git check-ignore` new files; after push confirm origin SHA.
- **Out-of-band + fail-safe everywhere:** fetch fail/oversize/timeout → None; classifier no-model → `("uncategorized",0.0)`; Celery down → hook no-ops; NOTHING blocks the inline lookup or crashes.
- **Prompt-injection defense (mandatory, tested):** non-generative classifier (fixed category set); metadata-only scrape (classifier never sees raw HTML/JS); SSRF-sandboxed fetcher (reject private/loopback/link-local/reserved IPs + redirects to them; size 512KB + time 5s caps; no cookies/creds/JS).
- **Cache write uses the canonical signature:** `cache.set("sase:catcache", domain, value=json, ttl_seconds=86400)` — NEVER a pre-built full key (the bug the catcache-fix corrected).
- **No new migration** — write-back reuses `domain_categories` (0021) with `source="ai"` via B's tenant-aware upsert.
- New deps (`beautifulsoup4`, `scikit-learn`+`numpy`+`scipy`+`joblib`, `celery`) pinned + hashed via `uv pip compile --generate-hashes`; Socket-verified; Western/OSS, no PRC, no external model download.
- Flag `tobogganing.sase.swg_ai_categorizer` — professional, `@require_feature` where surfaced; hook checks it before dispatch.

---

## Task 1: SSRF-sandboxed fetcher

**Files:** Create `hub_api/modules/sase/security/swg/tier2/__init__.py`, `tier2/fetcher.py`; Test `hub_api/tests/test_sase_swg_tier2_fetcher.py`.

**Interfaces:** `async fetch(url: str, *, max_bytes=512_000, timeout_s=5.0) -> bytes | None`; `is_public_host(host) -> bool` (resolves + rejects private/loopback/link-local/reserved/multicast).

- [ ] Step 1: Failing tests (mock the transport / patch resolution): a URL resolving to `127.0.0.1`/`10.0.0.0`/`169.254.*`/`::1` → refused (None); a redirect to a private IP → refused; oversize body → truncated/None; timeout → None; a public host with a small body → bytes; no `Cookie`/`Authorization` header sent. `# regression: SSRF sandbox`. Step 2: FAIL. Step 3: Implement with `httpx` (async, `follow_redirects` handled manually so each hop's host is SSRF-checked; `ipaddress` to classify resolved IPs; size cap via streamed read; benign fixed UA; no cookies). Step 4: PASS. Step 5: Green gate + commit.

---

## Task 2: Metadata-only scraper

**Files:** Create `tier2/scraper.py`; Test `hub_api/tests/test_sase_swg_tier2_scraper.py`.

**Interfaces:** `extract_metadata(html: bytes, *, max_chars=4000) -> str` (title + meta description + h1–h3 + bounded visible text; strips script/style/hidden/event-handlers).

- [ ] Step 1: Add `beautifulsoup4` (pin+hash). Step 2: Failing tests — extracts title/meta/h1–h3/text; a `<script>IGNORE PREVIOUS INSTRUCTIONS...</script>` and a `<style>` and `display:none` block → their text is ABSENT from the output; output ≤ max_chars; malformed HTML → best-effort, no raise. `# regression: injection stripped`. Step 3: FAIL. Step 4: Implement (BeautifulSoup, `.decompose()` script/style, skip hidden, join text, cap). Step 5: PASS. Step 6: Green gate + commit.

---

## Task 3: Non-generative classifier + train script

**Files:** Create `tier2/classifier.py`, `tier2/train.py` (+ pin scikit-learn/numpy/scipy/joblib); Test `hub_api/tests/test_sase_swg_tier2_classifier.py`.

**Interfaces:** `class DomainClassifier(model_path=None)`: `classify(text: str) -> tuple[str, float]`; `CONFIDENCE_THRESHOLD`; fail-safe `("uncategorized",0.0)` when the model is absent/unloadable. `train.py`: `build_model(samples, out_path)` (TF-IDF vectorizer + LinearSVC/LogisticRegression → joblib).

- [ ] Step 1: Add sklearn stack (pin+hash). Step 2: Failing tests — train a tiny in-test model on ~6 labeled samples → `classify` returns a category in the trained set with a confidence; text below threshold → `uncategorized`; `DomainClassifier(model_path="/nonexistent")` → `("uncategorized",0.0)` no crash; output category is ALWAYS from the fixed set (non-generative). Step 3: FAIL. Step 4: Implement classifier (load joblib, TF-IDF transform, predict + decision-function/proba → confidence, threshold) + `train.py`. Step 5: PASS. Step 6: Green gate + commit.

---

## Task 4: Celery task + write-back + hook + flag + contract (+ fix dangling refresh handler)

**Files:** Create `hub_api/modules/sase/security/swg/tasks.py`, `tier2/worker.py` (if separate); Modify `swg/lookup.py` (`_enqueue_uncategorized` → dispatch), `hub_api/modules/sase/__init__.py` (flag+entitlement+ register the task/handler); Test `hub_api/tests/test_sase_swg_tier2_worker.py`.

**Interfaces:** Celery task `swg.categorize_domain(domain, tenant)` (sync task wrapping `asyncio.run(_categorize_async(...))`, model on `perftest_c2c/worker/tasks.py`): `fetch → extract_metadata → classify`; confident → upsert `domain_categories` (source="ai", tenant) + `cache.set("sase:catcache", domain, value=json.dumps(sorted([cat])), ttl_seconds=86400)`; else record uncategorized. Also `refresh_categories_daily(...)` implementing the handler B's `scheduler.py` registered (calls `CategoryIngestManager.ingest_all` + logs) — **fixes the dangling reference**. `_enqueue_uncategorized(domain, tenant)` → if flag on and Celery available: `categorize_domain.delay(domain, tenant)`; else log no-op.

- [ ] Step 1: Add `celery` (pin+hash). Step 2: Failing tests — `categorize_domain` core on a confident fixture (mock fetch→html, real scraper+tiny classifier) writes `domain_categories`(source="ai") + catcache round-trips through a REAL CacheClient (in-memory fallback, canonical signature); low-confidence → no write; fetch-None → no write no raise; `_enqueue_uncategorized` dispatches when flag ON (mock `.delay`), no-op when OFF or Celery down; `refresh_categories_daily` runs ingest without error. Step 3: FAIL. Step 4: Implement tasks.py + hook rewiring + register flag `tobogganing.sase.swg_ai_categorizer`(professional)+entitlement in `module()`. Step 5: PASS. Step 6: Green gate (batch: new test + `test_sase_swg_lookup.py` + `test_sase_module.py` + `test_registry.py`) + boot + commit.

## Self-Review

- **Spec coverage:** SSRF fetcher→T1; metadata scraper→T2; classifier+train→T3; worker+write-back+hook+flag→T4; dangling `refresh_categories_daily` fix→T4; 3-layer injection defense→T1/T2/T3; no-migration write-back→T4; graceful degradation→T3/T4. All covered.
- **Placeholders:** none — train.py is a real script; the shipped state (no model) fail-safes to uncategorized by design.
- **Type consistency:** `fetch`/`is_public_host`, `extract_metadata`, `DomainClassifier.classify`, `categorize_domain`/`refresh_categories_daily`, canonical `cache.set` signature — consistent.

## Execution

Sequential (2→4 build up). Single feature branch `feature/sase-swg-ai` off release **after the catcache-fix lands**. Independent of Slice C (no shared migration) → parallel (Wave 2); combine the sase-contract conflict at rebase. Verify commit-completeness + clean-bytecode + full-suite + the SSRF/injection regressions before merge.
