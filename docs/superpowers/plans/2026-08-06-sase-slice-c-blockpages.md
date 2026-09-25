# SASE Slice C — Block Pages (Markdown) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`). Backend by `penguin-python-dev`; portal (Task 6) by `penguin-react-dev`.

**Goal:** Markdown-based block/soft-block pages (drag-drop palette of basic md elements → markdown doc with template vars) + per-source block-routing + external-redirect (`X-Block-*`) + rule governance metadata; Python stores/serves definitions, data-plane renders (contract).

**Architecture:** `blockpages/` module — `BlockPage` (markdown, draft/live+versions), `BlockRoute` (source_type→page|external), `RuleMetadata` governance; `render.py` markdown→sanitized HTML+vars; APIs derive tenant STRICTLY from claims; portal drag-drop markdown builder (dnd-kit).

**Tech Stack:** Python 3.13, penguin-dal, Alembic, Quart, a markdown lib + HTML sanitizer; portal React 18 + Vite + TS + Tailwind v4 + dnd-kit.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-06-sase-slice-c-blockpages-design.md` — authoritative.
- Green gate: `python3 -m pytest hub_api/tests/` (baseline **979**, 0 fail) in batches; `create_app()` boots; `scripts/audit_imports.py --module sase --forbid sdwan,ziti` clean. Clean bytecode first.
- **Commit-completeness (hard):** `git status --short` empty + `git show HEAD --stat` after each commit; `git check-ignore` new files; after push confirm origin SHA.
- **TENANT FROM AUTHENTICATED CLAIMS ONLY** (Slice B shipped a cross-tenant bug — do NOT repeat): every API derives tenant from `current_claims()`/`g.tenant` via `@require_tenant`; a body/param/header tenant that mismatches → 403; every manager query filters by the authenticated tenant. A cross-tenant regression test per endpoint.
- Render output is **sanitized** (strip script/style/event-handlers even from admin markdown). Missing route → global default page (fail-safe, never an error leaking internals).
- Alembic: chain after head **0022** (→ 0023 block_pages, 0024 block_routes); declare in the sase `ModuleContract.migrations`. Flag `tobogganing.sase.blockpages` — community, `@require_feature("sase","blockpages")` (402 when off).
- New deps (markdown lib + sanitizer + dnd-kit): pin exact + hashes; Socket-verify; Western/maintained only (no PRC).

---

## Task 1: Models + Alembic (block_pages, block_routes)

**Files:** Create `hub_api/modules/sase/security/blockpages/__init__.py`, `models.py`, migrations `<0023>_block_pages.py`, `<0024>_block_routes.py`; Test `hub_api/tests/test_sase_blockpages_models.py`.

**Interfaces:** `@dataclass(slots=True)` `BlockPage(id,tenant,name,markdown,status,version,created_by,updated_by,created_at,updated_at)`, `PageStatus(str,Enum){draft,live}`; `BlockRoute(id,tenant,source_type,destination_kind,page_id,external_url,created_at,+metadata)`, `RouteDest(str,Enum){page,external}`; `RuleMetadata(created_by,updated_by,ticket,notes,expiry,review_date,scope,risk)`.

- [ ] Step 1: Read `sdwan/firewall/access_control.py` (dataclass+enum+Manager pattern) + `0002_sase_firewall_rules.py` (migration template; head is 0022). Step 2: Write failing test (construct the dataclasses + enums). Step 3: Implement models + the 2 migrations (block_pages: id,tenant idx,name,markdown,status,version,created_by,updated_by,timestamps; block_routes: id,tenant idx,source_type,destination_kind,page_id,external_url,+governance cols; down_revision chains 0022→0023→0024). Step 4: PASS. Step 5: Green gate (+migrations_head test) + commit.

---

## Task 2: `BlockPageManager` (CRUD + versioning, tenant-scoped)

**Files:** Create `blockpages/pages.py`; Test `hub_api/tests/test_sase_blockpages_pages.py` (real-DAL).

**Interfaces:** `BlockPageManager(db)`: `async create(tenant,name,markdown,created_by)`, `async update(tenant,page_id,markdown,updated_by)`, `async publish(tenant,page_id)` (draft→live, version++), `async revert(tenant,page_id,version)`, `async get_live(tenant,name)`, `async list_pages(tenant)`. Every method filters by `tenant`.

- [ ] Step 1: Failing tests — create+get; publish bumps version + status=live; revert restores prior markdown; **cross-tenant: page under tenant A not visible/updatable by tenant B** (`# regression: cross-tenant`). Step 2: FAIL. Step 3: Implement (tenant-scoped queries). Step 4: PASS. Step 5: Green gate + commit.

---

## Task 3: `BlockRouteManager` + `resolve` + governance metadata

**Files:** Create `blockpages/routes.py`; Test `hub_api/tests/test_sase_blockpages_routes.py`.

**Interfaces:** `BlockRouteManager(db)`: `async set_route(tenant,source_type,destination_kind,page_id=None,external_url=None,metadata=None)`, `async get_routes(tenant)`, `async resolve(tenant,source_type) -> BlockRoute|None` (exact source_type → else global default → None).

- [ ] Step 1: Failing tests — set+resolve picks the right route; missing source_type → default/None; governance metadata persisted+queryable; cross-tenant isolation. Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Green gate + commit.

---

## Task 4: `render.py` (markdown → sanitized HTML + variables)

**Files:** Create `blockpages/render.py` (+ pin markdown lib + sanitizer in requirements); Test `hub_api/tests/test_sase_blockpages_render.py`.

**Interfaces:** `render_block_page(markdown: str, variables: dict[str,str]) -> str`; `VARIABLES` = the documented set.

- [ ] Step 1: Add markdown lib (`markdown` or `mistune`) + sanitizer (`nh3`/`bleach`) to requirements.in, `uv pip compile --generate-hashes`. Step 2: Failing tests — markdown headings/img/text/link/list/divider render; `{{blocked_url}}` etc. substituted; a `<script>alert(1)</script>` in markdown is sanitized OUT of the HTML; unknown variable → empty/left-as-is (documented). Step 3: FAIL. Step 4: Implement (substitute vars → render markdown → sanitize HTML to a safe tag allowlist). Step 5: PASS. Step 6: Green gate + commit.

---

## Task 5: API + flag + contract registration

**Files:** Create `blockpages/api.py`; Modify `hub_api/modules/sase/__init__.py` (flag `tobogganing.sase.blockpages`, `Entitlement(...,"community")`, blueprint, migrations 0023/0024); Test `hub_api/tests/test_sase_blockpages_api.py`.

**Interfaces:** blueprint `sase_blockpages` `url_prefix="/blockpages"`: `GET|POST|PUT /pages`, `POST /pages/<id>/publish`, `POST /pages/<id>/preview`, `GET|PUT /routes`. Typed DTOs; `@require_tenant`+`@require_scope`+`@require_feature("sase","blockpages")`; **tenant from `current_claims()` only**.

- [ ] Step 1: Failing tests — page CRUD+publish+preview (render) via API returns typed DTO; **body-tenant mismatch → 403** (`# regression: cross-tenant`); flag OFF → 402; write needs `sase:write`; external route response carries the documented `X-Block-*` header names. Step 2: FAIL. Step 3: Implement (mirror `blocklist/api.py` + the SWG cross-tenant-fixed pattern — tenant strictly from claims); register flag/entitlement/blueprint/migrations in `module()`. Step 4: PASS. Step 5: Green gate (+ `test_sase_module.py` + `test_registry.py`) + boot + commit.

---

## Task 6: Portal — markdown block-builder + routing-config UI (`penguin-react-dev`)

**Files:** Create `portal/src/pages/sase/BlockPageBuilder.tsx`, `BlockRoutingConfig.tsx`; Modify `portal/src/api/sase.ts` (+client funcs), `portal/src/routes/saseViews.ts` (+slugs); Tests colocated `.test.tsx`.

- [ ] Step 1: Add `dnd-kit` (exact pin) to `portal/package.json` + a markdown renderer for preview. Step 2: Build `BlockPageBuilder` — a drag-drop list of md-element blocks (h1–h4, image, text, link, list, divider); each block edits content; serialize ordered blocks → markdown; live preview; save/publish via `api/sase.ts`. Step 3: Build `BlockRoutingConfig` — source_type→destination table + governance fields. Step 4: Jest/RTL tests (builder serializes blocks → expected markdown; routing table CRUD; role-based visibility). Step 5: `npm run lint` + `npm test` pass; commit. (Screenshots per the marketing-screenshots rule since this is UI-affecting.)

---

## Task 7: Data-plane serving contract doc

**Files:** Create `docs/architecture/sase-blockpage-serving-contract.md`.

- [ ] Document: on `block`/`soft_block` (Slice B `EnforcementAction`), the Inspection Point resolves the `BlockRoute` for the block's `source_type` (pulled config, freshclam cadence — not per-request gRPC); `page` → fetch live markdown + render+sanitize+substitute vars → serve (403 block / interstitial soft_block); `external` → redirect with the `X-Block-*` header set; no route → global default. Commit.

## Self-Review

- **Spec coverage:** markdown page model→T1/T2/T4; versioning→T2; routing+resolve→T3; governance→T3; render+sanitize+vars→T4; API+flag+cross-tenant→T5; portal drag-drop builder→T6; external-redirect+X-Block-*→T5/T7; contract→T7. All covered.
- **Placeholders:** none.
- **Type consistency:** `BlockPage/BlockRoute/RuleMetadata`, `PageStatus/RouteDest`, `BlockPageManager.{create,update,publish,revert,get_live}`, `BlockRouteManager.{set_route,resolve}`, `render_block_page` — consistent.

## Execution

Backend T1-5,7 (`penguin-python-dev`), portal T6 (`penguin-react-dev`). Single feature branch `feature/sase-blockpages`. Parallel with Slice E (Wave 2); combine the sase-contract conflict at rebase (as B/D). Verify commit-completeness + clean-bytecode + full-suite + cross-tenant regressions before merge.
