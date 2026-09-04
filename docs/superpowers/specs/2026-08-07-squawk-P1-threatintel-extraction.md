# Squawk → netsvcs Merge — P1: threatintel shared-module extraction

**Date**: 2026-08-07
**Phase**: P1 (the load-bearing refactor of shipped SASE code)
**Branch**: `feature/squawk-merger` (lands here; NOT merged to release — part of the in-progress merge program)
**Umbrella**: `docs/superpowers/specs/2026-08-07-squawk-netsvcs-merge-umbrella.md`
**P0 input**: `docs/superpowers/specs/2026-08-07-squawk-P0-import-manifest.md`

## Goal

Extract the shipped SASE threat-intel code into a new **shared module** `hub_api/modules/threatintel/` that both `sase` (SWG/enforcement) and the future `netsvcs` (DNS filtering) consume. Harvest Squawk's MISP/OpenIOC/CSV/STIX parsers into it. **Import rule: `sase` and `netsvcs` MAY import `threatintel`; `threatintel` imports NEITHER.**

This is the riskiest phase — it moves code that shipped in v1.2.X (not yet tagged). The hard gate is **full existing-suite parity** (every SASE test green) plus net-new parser tests.

## Actual source layout (from P0 recon)

Code lives under `hub_api/modules/sase/security/`, not directly under `sase/`:
- `sase/security/blocklist/` — `store.py` (`BlocklistStore`, actively wired), `models.py` (`Verdict` dataclass, Valkey-only), `stix_normalizer.py` (`to_stix_indicator`, uses `stix2`), `curator.py` (`BlocklistCurator`), `api.py` (`blueprint`, `check_ioc` route), `__init__.py` (empty).
- `sase/security/feeds/` — `sources.py` (parsers/fetchers, `ThreatIndicator` dataclass), `manager.py` (`SecurityFeedsManager`), `detection.py` (`DetectionLogger`), `models.py` (SQLAlchemy ORM: `ThreatIndicator`/`FeedUpdate`/`ThreatDetection`), `__init__.py` (public re-exports).

## Target layout

```
hub_api/modules/threatintel/
├── __init__.py            # module() -> ModuleContract (name="threatintel")
├── blocklist/             # git mv from sase/security/blocklist/
│   ├── store.py           # namespace literal → "threatintel:blocklist"
│   ├── models.py  stix_normalizer.py  curator.py  api.py  __init__.py
├── feeds/                 # git mv from sase/security/feeds/
│   ├── sources.py  manager.py  detection.py  models.py  __init__.py
│   └── parsers.py         # NEW — harvested squawk parsers
```

## Contract deltas (exact — these are asserted by tests)

**sase `__init__.py` AFTER** (drop blocklist blueprint + `threat_feeds`/`blocklist` flag+entitlement):
- blueprints: `[swg_blueprint, blockpages_blueprint]` → **2**
- flags: **7** — scanner, protection, context_auth, adapters, swg, swg_ai_categorizer, blockpages
- entitlements: **7** (matching)
- migrations: **6** unchanged — `["0006","0008","0021","0022","0023","0024"]` (0008 stays: it also creates the scanner/protection tables)
- `adapters` flag/entitlement STAY in sase (adapters are SASE inspection; they only repoint their `BlocklistStore` import)

**threatintel `__init__.py` NEW**:
- name `"threatintel"`, blueprints `[blocklist_blueprint]` (mounts `/api/v1/threatintel/blocklist/check`)
- flags: `["tobogganing.threatintel.blocklist", "tobogganing.threatintel.feeds"]`
- entitlements: `[Entitlement("threatintel.blocklist","community"), Entitlement("threatintel.feeds","community")]`
- migrations: `["0008"]` (references the same shared revision; no file move, no new migration)
- nav: `[NavEntry("Threat Intel", "/api/v1/threatintel", "shield-alert")]`
- Add `"threatintel"` to `hub_api/modules/__init__.py::__all__`.

**Flag-key rename note**: the blocklist HTTP gate changes from `require_feature("sase","blocklist")` → `require_feature("threatintel","blocklist")`. New flag keys default OFF (standard). Pre-release, so no live PostHog impact — but record that `sase.blocklist`→`threatintel.blocklist` and `sase.threat_feeds`→`threatintel.feeds`.

## Cache namespace

`hub_api/cache/keys.py`: `NAMESPACES` `"sase:blocklist"` → `"threatintel:blocklist"`. Update the 4 literals in `blocklist/store.py`. Catcache (`sase:catcache`) is unaffected — stays in sase. Runtime effect: existing `sase:blocklist:*` cache entries orphan and TTL out; the store rebuilds from feeds/adapters (fail-open cache, no data loss).

## Break-on-move checklist (every item must be reconciled — from P0 recon)

| Target | Change |
|---|---|
| `sase/security/adapters/base.py:10-12` | import `Verdict`/`BlocklistStore`/`to_stix_indicator` from `hub_api.modules.threatintel.blocklist.*` |
| `sase/security/adapters/poller.py:10` | import `BlocklistStore` from threatintel |
| moved-file internal imports | `curator.py` self-imports, `feeds/__init__.py` re-exports, `api.py` auth imports — repoint to threatintel paths |
| ~15 test files | `...sase.security.{feeds,blocklist}.*` → `...threatintel.{feeds,blocklist}.*` |
| `test_sase_feeds.py` monkeypatch | `hub_api.modules.sase.security.feeds.manager.fetch_blackweb_*` → threatintel path (lines 268/273/308/312) |
| `test_migrations_head.py:42` | import ORM models from `hub_api.modules.threatintel.feeds.models` |
| `test_sase_blocklist_api.py` | module import + fixture register threatintel; route → `/api/v1/threatintel/blocklist/check` |
| `test_sase_module.py` | counts → 2 bp / 7 flags / 7 ent / 6 mig; drop `sase_blocklist` from blueprint names + `threat_feeds`/`blocklist` from flag set; fix `test_sase_module_registered_in_app` (those two are threatintel flags now); fix `test_sase_routes_registered_at_correct_urls` (sase no longer serves blocklist route) |
| `test_cache_client.py` | `sase:blocklist` → `threatintel:blocklist` (3 asserts) |
| `scripts/audit_imports.py` + `test_module_boundaries.py` | allow `sase → threatintel`; add threatintel row asserting it imports neither sase nor netsvcs |
| ORM registration | ensure `threatintel/feeds/models.py` is imported into `Base.metadata` (via Alembic env / module import chain) so `test_migrations_head.py` still finds the tables |
| NEW `test_threatintel_module.py` | contract test (sibling of `test_sase_module.py`): name, 1 blueprint, 2 flags/entitlements, migrations `["0008"]`, route `/api/v1/threatintel/blocklist/check` |

## Parser harvest (additive — new `threatintel/feeds/parsers.py`)

Harvest from `~/code/squawk/dns-server/bins/ioc_manager.py` (functions identified in P0):
- `parse_misp_feed(payload)` ← `_parse_misp_feed` (+ type/date mappers)
- `parse_openioc_feed(xml_text)` ← `_parse_openioc_feed`
- `parse_threat_csv(text)` ← `_parse_csv_feed` (confidence/category columns)
- `parse_stix_bundle(payload)` — **use OASIS `stix2`** (already a dep via `stix_normalizer`), NOT squawk's regex `_parse_stix_feed`
- All return `list[ThreatIndicator]` (the `feeds/sources.py` dataclass). Add a `metadata: dict` field to that dataclass if absent; parsers populate provenance keys `misp_event_id`/`misp_attribute_id`/`source_format` → these flow into the ORM `metadata` JSON column on `_store_indicator` (no schema change; column already exists as `name="metadata"`).
- Malformed input → skip the record, never raise (mirror existing feed-parser robustness tests).
- **Deferred to a later phase**: live TAXII2 polling transport (`taxii2-client` dep + network) — it's ingestion wiring for when `netsvcs` consumes feeds, out of P1's risk budget. Text feed (`_parse_text_feed`) is NOT harvested (tobogganing already covers plaintext/CIDR).

NEW `test_threatintel_parsers.py`: per-parser happy-path + malformed-skip + provenance-in-metadata assertions.

## Verification gate (all must pass before push)

1. `python3 -m pytest hub_api/tests/` — **full suite green** (parity: every pre-existing SASE test passes under new paths).
2. `python3 scripts/audit_imports.py` (or `test_module_boundaries.py`) — no forbidden cross-imports; `threatintel` imports neither `sase` nor `netsvcs`.
3. Repo-wide grep clean: zero remaining `sase.security.feeds` / `sase.security.blocklist` references outside git history.
4. `make lint` (flake8/black/isort/mypy) clean on changed files.
5. `make test-security` (bandit) clean on new parser code.
6. New parser tests present and green; threatintel contract test present and green.

## Execution shape

P1 is a **cohesive refactor**, not a fan-out — nearly everything touches the same tree, so parallel edits would race (per `parallel-agent-git-hygiene`). Sequential pipeline:
1. **Extraction+repoint** (one specialist, atomic) → full suite green → commit.
2. **Parser harvest** (additive, after module exists) → suite green → commit.
3. **Independent verification** (parallel read-only: full suite re-run, import audit, stale-ref grep, security scan) → push.
Push to `feature/squawk-merger` as backup; do NOT merge to release.
