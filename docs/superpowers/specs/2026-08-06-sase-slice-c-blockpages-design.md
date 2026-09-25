# SASE Slice C — Block Pages (Markdown) + Routing + Governance (Design Spec)

**Date**: 2026-08-06
**Status**: Design approved; ready for implementation plan
**Cross-references**:
- SASE security design: `docs/superpowers/specs/2026-07-26-sase-sdwan-ziti-core-split.md` ("Enforcement Actions & Block Handling")
- Slice B enforcement enum (merged): `hub_api/modules/sase/security/enforcement.py` (`EnforcementAction`)
- Reuse: `hub_api/modules/sdwan/firewall/access_control.py` (rule+DAL pattern), `hub_api/modules/sase/security/blocklist/api.py` (DTO + decorator convention), `hub_api/modules/sase/security/protection/middleware_core.py:97` (`X-Block-Reason`/`X-Security-Block` header precedent)

## Goal

When an `EnforcementAction` of `block`/`soft_block` fires, the Inspection Point serves a customer-branded page (or redirects to a customer server). Slice C provides: **markdown-based block/soft-block pages** with a drag-and-drop builder (basic markdown elements), **per-source block-routing config** (which page for which block reason), **external-redirect** with `X-Block-*` context headers, and **rule governance metadata**. Like A/B, Python stores + serves definitions; the data plane renders/serves at enforcement (contract).

## Block-page model (locked — markdown, not a page-builder framework)

A block page is a **markdown document** with template variables. The portal offers a **drag-and-drop palette of basic markdown elements** (h1–h4, image, paragraph/text, link/button, unordered/ordered list, divider); each dragged block edits its content; the builder serializes the ordered blocks to **markdown**. Stored as markdown (not HTML, not a JSON block tree). The data plane renders markdown → sanitized HTML at enforcement, substituting server-rendered variables: `{{blocked_url}}`, `{{category}}`, `{{reason}}`, `{{user}}`, `{{org}}`, `{{support_link}}`, `{{appeal_link}}`, `{{timestamp}}`.

- Drag-and-drop is authoring UX only — the artifact is markdown; any editor that produces the same markdown is equivalent.
- Per-tenant branding (logo image block, colors via a small front-matter block, messaging). Draft/live status + version history (revert).
- Soft-block pages add a continuation control (`{{continue_url}}` / acknowledgement) rendered by the data plane.

## Scope (locked)

- **In**: backend block-page store (markdown + versioning), per-source block-routing config, rule governance metadata, external-redirect + `X-Block-*` header contract, typed APIs, a markdown render/preview function, the portal drag-and-drop markdown builder + route-config UI, data-plane serving contract doc.
- **Out**: the data-plane rendering/serving itself (contract only — the Go/Rust Inspection Point renders); changing B's enforcement actions (C keys off them).

## Components — backend `hub_api/modules/sase/security/blockpages/`

- `models.py` — `@dataclass(slots=True)`:
  - `BlockPage(id, tenant, name, markdown, status: PageStatus, version, created_by, updated_by, created_at, updated_at)`; `PageStatus ∈ {"draft","live"}`.
  - `BlockRoute(id, tenant, source_type, destination_kind: RouteDest, page_id, external_url, created_at, ...governance)`; `RouteDest ∈ {"page","external"}`; `source_type` e.g. `web-category:gambling`, `oob-analysis:malware`, `custom-rule:<id>`, `soft-block`.
  - `RuleMetadata(created_by, updated_by, ticket, notes, expiry, review_date, scope, risk)` embedded on `BlockRoute` (and reusable).
- `pages.py` — `BlockPageManager(db)`: CRUD, `publish(page_id)` (draft→live + new version), `revert(page_id, version)`, `get_live(tenant, name)`. **Tenant-scoped from authenticated claims — NEVER from request body/params** (hard rule; Slice B's cross-tenant lesson: derive tenant from `g.tenant`/claims in the API layer, and every manager query filters by the authenticated tenant).
- `routes.py` — `BlockRouteManager(db)`: routing-config CRUD; `resolve(tenant, source_type) -> BlockRoute|None` (which page/external for a block reason; fallback → global default).
- `render.py` — `render_block_page(markdown, variables) -> str` (markdown → **sanitized** HTML with variable substitution; a safe subset — headings/img/text/link/list/divider; sanitize output even though admin-authored, defense-in-depth). Used for preview + as the reference the data-plane contract mirrors.
- `api.py` — blueprint `url_prefix="/blockpages"`:
  - Page CRUD `GET|POST|PUT /pages` + `POST /pages/<id>/publish` + `POST /pages/<id>/preview` (render with sample vars).
  - Route-config `GET|PUT /routes`.
  - All: `@require_tenant` + `@require_scope("sase:write"|"sase:read")` + `@require_feature("sase","blockpages")`; typed DTOs (exact fields, no raw model); **tenant strictly from `current_claims()`** — a body/param tenant that mismatches → 403.
- Alembic: `block_pages`, `block_routes` (governance columns) tables — chain after head **0022** (so 0023, 0024); declared in the sase `ModuleContract.migrations`.

## Components — portal `portal/src/pages/sase/` + `portal/src/api/`

- A **BlockPageBuilder** page: drag-and-drop list of markdown-element blocks (dnd-kit — lightweight, MIT, React; pinned exact version) → serializes to markdown; live markdown preview; save/publish/version.
- A **BlockRoutingConfig** page: the source_type → destination table (page or external URL) + governance-metadata fields.
- `api/sase.ts` additions (typed client funcs), `routes/saseViews.ts` slugs, follow the existing portal conventions (recon-confirmed React 18 + Vite + TS + Tailwind v4).

## External redirect + `X-Block-*` headers (contract)

A `BlockRoute` with `destination_kind="external"` → the data plane redirects the blocked request to `external_url` with context headers (extends the existing `X-Block-Reason`/`X-Security-Block` precedent): `X-Blocked-URL`, `X-Block-Category`, `X-Block-Rule-ID`, `X-Block-Source`, `X-Block-User` (UUID), `X-Block-Tenant`, `X-Block-Reason`. The customer's server renders its own page (ZScaler/iBoss style).

## Data-plane serving contract (doc, `docs/architecture/sase-blockpage-serving-contract.md`)

On a `block`/`soft_block` action (from Slice B's `EnforcementAction`), the Inspection Point: resolves the `BlockRoute` for the block's `source_type` (via hub-api / a pulled config, freshclam cadence — not per-request gRPC); if `page` → fetches the live block-page markdown + renders markdown+variables → sanitized HTML + serves (403 for block, interstitial for soft_block); if `external` → redirects with `X-Block-*` headers; if no route → global default page. Pages/config pulled + cached like the radix (Slice B).

## Flags & tier

- Flag `tobogganing.sase.blockpages` — **community** (block handling is core SWG); default OFF. `Entitlement("sase.blockpages","community")` in the sase `module()`.

## Dependencies

- Markdown render: a maintained Western markdown lib (e.g. `markdown` or `mistune`) + an HTML sanitizer (e.g. `bleach` / `nh3`) — pin exact + hashes; Socket-verify. Portal: `dnd-kit` (MIT) + a markdown renderer for preview — pin exact.

## Error handling

- API derives tenant from claims only (cross-tenant is a hard 403 — the Slice-B lesson, baked in). Render sanitizes output (no script/style/event-handler injection even from admin markdown). Missing route → global default (fail-safe to a generic block page, never an error page that leaks internals). Preview/render never executes template variables as code (simple substitution only).

## Testing

- **Pages**: CRUD + publish (draft→live, version bumps) + revert; **cross-tenant**: a page created under tenant A is not readable/updatable by tenant B (regression, like B); tenant strictly from claims.
- **Routes**: `resolve(source_type)` picks the right page/external; missing → default; governance metadata persisted + queryable.
- **Render**: markdown → HTML with variables substituted; a `<script>` in the markdown is sanitized out; each md element type renders; soft-block continuation present.
- **API**: typed DTO field sets; flag OFF → 402; write needs `sase:write`; body-tenant mismatch → 403; external route emits the documented `X-Block-*` header set (assert the header names/values on the redirect DTO/contract).
- **Portal**: builder serializes blocks → expected markdown; preview renders; route-config table CRUD (Jest/RTL per the frontend standards).
- Full-suite parity; boot clean; `audit_imports --module sase` clean.

## Sequencing (for the plan)

1. `models.py` + Alembic `block_pages`/`block_routes`.
2. `pages.py` (`BlockPageManager`, versioning, tenant-scoped).
3. `routes.py` (`BlockRouteManager`, `resolve`) + governance metadata.
4. `render.py` (markdown→sanitized HTML + variables).
5. `api.py` + flag + contract registration (tenant-from-claims baked in).
6. Portal builder + routing-config UI (penguin-react-dev).
7. Data-plane serving contract doc.

Single feature branch `feature/sase-blockpages` off release. **Independent of Slice E** (`blockpages/` vs `swg` AI worker) → **parallel (Wave 2)**. Note: C and E both edit the sase `module()` contract → resolve that conflict at rebase (combine, as B/D did).

## Notes

- **Cross-tenant discipline baked in from the start** — Slice B shipped a cross-tenant bug the review caught; C's API derives tenant only from authenticated claims, with a regression test per endpoint.
- C keys off Slice B's `EnforcementAction` (`block`/`soft_block` trigger a page; the enum is the seam).
- Governance metadata model is reusable — later could extend to SWG policies + blocklist rules (out of scope here).
