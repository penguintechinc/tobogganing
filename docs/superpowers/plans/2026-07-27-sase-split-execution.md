# SASE → core / sdwan / sase / ziti Split — Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. This is a **reorganization** (moves + import retargeting + contract re-partitioning), not greenfield — the acceptance criterion for every phase is **suite parity** (all pre-existing tests still pass, none deleted), not new red-green-refactor cycles.

**Goal:** Decompose the monolithic `hub_api/modules/sase/` into four functional homes — **core** (auth/PKI/backup infra), **`sdwan`** (transport + routing), **`sase`** (security inspection + context-auth), **`ziti`** (greenfield identity scaffold) — with no forbidden cross-module imports and full test parity.

**Architecture:** Quart brain (`hub_api/`). Modules self-describe via a `def module() -> ModuleContract` factory in their package `__init__.py`; `hub_api/app.py` discovers them from the hardcoded `hub_api/modules/__init__.py::__all__` list and mounts blueprints at `/api/v1/{name}{prefix}`. **core** is a plain infra package (sibling of `modules/`), imported directly — it is NOT registry-mounted and has no contract.

**Tech Stack:** Python 3.13, Quart, penguin-dal, Alembic (single linear chain), pytest (840 tests under `hub_api/tests/`).

## Global Constraints

- **Green gate command (there is no `make test` for the brain — Makefile is stale):**
  `python3 -m pytest hub_api/tests/` — **840 tests must pass** (baseline as of 2026-07-27). Long full runs have been killed by the environment (exit 143/144); **run in targeted batches by test file/pattern** and aggregate, never assume a killed run == failure.
- **No test deletions.** Tests may be *renamed/moved* to track the code, but coverage must not shrink. Baseline count 840 must not drop.
- **Import boundary (enforced by `scripts/audit_imports.py`, Task 0):** `sdwan ⊥ {sase, ziti}`, `sase ⊥ {sdwan, ziti}`, `ziti ⊥ {sdwan, sase}`. All modules **may** import `hub_api.core`.
- **Contracts live inline** in each package's `__init__.py::module()` (dataclass `ModuleContract` from `hub_api/registry/contract.py`) — do NOT introduce `contract.py` files.
- **Migrations stay one linear chain** in `hub_api/migrations/versions/` (0001–0020). Only each contract's `migrations=[...]` metadata list is re-partitioned. No Alembic branching. `hub_api/tests/test_migrations_head.py` must stay green.
- **No external API changes** — endpoint URLs, request/response schemas unchanged. Blueprint `url_prefix`s and mount points preserved so `/api/v1/sase/clusters` etc. keep resolving (see Task on mount compatibility).
- Every branch is pushed immediately on creation and after every commit (backup). Feature→release merges are pre-authorized when the green gate is fully met.

## Deviations from spec (flagged, with rationale)

1. **Migrations: single linear chain kept** (spec §Hard-Seam 3 wanted per-module dirs/branches). Rationale: the chain works and is head-tested; multi-head branching adds risk with zero table-level benefit. Contract `migrations` metadata is re-partitioned to reflect ownership.
2. **No 90% coverage gate stood up** (global standard wants one; none is configured for hub_api and the root Makefile targets a deleted `manager/` dir). A pure reorganization cannot change coverage. Tracked as **separate debt** — see "Follow-up debt" at end. Flag to user.
3. **Contracts inline / `core/__init__.py` re-exports** — follows the established codebase idiom rather than the spec's `contract.py` / `exports.py` filenames.
4. **`headend_routes.py` stays at `hub_api/api/`** — retarget imports only.
5. **perftest** is already 3 dirs (`perftest_{cluster,client,c2c}`) with flags `tobogganing.perftest_cluster.*`; the spec's `tobogganing.perftest.cluster.*` renaming is **out of scope** here (already-merged concern) — noted, not actioned.

## Follow-up debt (surface to user; not in this plan's scope)

- Root `Makefile` `test`/`build`/`lint` targets reference the deleted `manager/`, `headend`, `client`, `website` — no `hub_api` targets. Rewrite the Makefile to drive the Quart brain.
- No pytest config (`pytest.ini`/`pyproject.toml`) or coverage threshold for `hub_api`. Stand up config + `--cov-fail-under=90`.
- `scripts/version/update-version.sh` referenced by standards but absent.
- perftest flag/dir naming not consolidated to the taxonomy's `perftest.*`.

---

## Task 0: Import-boundary guard (`scripts/audit_imports.py`)

**Branch:** `chore/module-import-audit` off `release/v1.2.X` (independent; lands first so every later phase can invoke it).

**Files:**
- Create: `scripts/audit_imports.py`
- Create: `hub_api/tests/test_module_boundaries.py`

**Interfaces:**
- Produces: CLI `python3 scripts/audit_imports.py --module <name> --forbid <a,b>` → exit 0 clean, exit 1 + prints `path:line: forbidden import <target>` on violation. `--root hub_api/modules` default; core scanned as `hub_api/core` when `--module core-pkg` (core has no forbidden targets, so it's not audited).
- Consumed by: every phase's green gate + the boundary test.

- [ ] **Step 1: Write `scripts/audit_imports.py`** — AST-based (`ast.parse`, walk `Import`/`ImportFrom`), resolve the module dir from `hub_api/modules/<name>` (configurable `--root`), flag any `import`/`from` whose dotted target starts with `hub_api.modules.<forbidden>` for each forbidden name. Skip `__pycache__`, test files. 2-3 line module docstring per house style.

```python
#!/usr/bin/env python3
"""Audit a module's Python files for forbidden cross-module imports.

Enforces the sase/sdwan/ziti decomposition boundary: a module must not import
its siblings. Exits non-zero (listing every offending path:line) on violation.
"""
from __future__ import annotations
import argparse, ast, sys
from pathlib import Path


def _violations(module_dir: Path, forbidden: list[str]) -> list[str]:
    """Return 'path:line: forbidden import <target>' for each cross-module import."""
    forbidden_prefixes = tuple(f"hub_api.modules.{name}" for name in forbidden)
    out: list[str] = []
    for py in module_dir.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                targets.append(node.module)
            elif isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            for t in targets:
                if t.startswith(forbidden_prefixes):
                    out.append(f"{py}:{node.lineno}: forbidden import {t}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--forbid", required=True, help="comma-separated sibling names")
    ap.add_argument("--root", default="hub_api/modules")
    args = ap.parse_args()
    module_dir = Path(args.root) / args.module
    if not module_dir.is_dir():
        print(f"module dir not found: {module_dir}", file=sys.stderr)
        return 2
    viols = _violations(module_dir, [f.strip() for f in args.forbid.split(",") if f.strip()])
    for v in viols:
        print(v)
    return 1 if viols else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write `hub_api/tests/test_module_boundaries.py`** — parametrized test invoking `_violations` directly (import the function) for each of the three modules against its forbidden siblings; assert empty. Guarded so it no-ops for modules that don't exist yet (early phases), e.g. `if not (Path("hub_api/modules")/name).is_dir(): pytest.skip(...)`.
- [ ] **Step 3: Run** `python3 scripts/audit_imports.py --module sase --forbid sdwan,ziti` — expect exit 0 today (no sdwan/ziti yet). Run the boundary test: `python3 -m pytest hub_api/tests/test_module_boundaries.py -v` → passes (skips absent modules).
- [ ] **Step 4: Green gate** — batch-run the suite; 840 pass (841 with the new test; update baseline note to 841).
- [ ] **Step 5: Commit + push + PR** into `release/v1.2.X`, merge when green.

---

## Phase 2: Core extraction (auth / PKI / backup)

**Branch:** `feature/split-core-extraction` off `release/v1.2.X` (worktree under `.worktrees/`).

**Creates `hub_api/core/`** as a plain infra package. Moves `UserManager`, `BackupManager`, and the **PKI-only** `CertificateManager` into it; converts the old dual-purpose cert class's WireGuard half into a `WireGuardKeyManager` that **stays in sase for now** (Phase 3 relocates it to sdwan). Retargets every importer.

**Files:**
- Create: `hub_api/core/__init__.py` (re-exports `CertificateManager`, `UserManager`, `BackupManager`)
- Create: `hub_api/core/certificates.py` (PKI-only `CertificateManager`: `generate_certificate`, `validate_certificate`, `generate_headend_certificate`, `generate_client_certificate`, `_validate_ca_certificate`, `_generate_ca`, `_persist_ca`, `_is_certificate_expiring`, plus `__init__/initialize/shutdown/is_healthy` scoped to CA state only)
- Create: `hub_api/core/auth.py` (moved `UserManager` + `User`/`Session`/`UserRole` dataclasses from `sase/auth/user_manager.py`)
- Create: `hub_api/core/backup/` (moved `manager.py`, `crypto.py`, `s3.py`, `cli.py`, `__init__.py` from `sase/backup/`)
- Modify → become WG-only: `hub_api/modules/sase/certs/certificate_manager.py` → rename class to `WireGuardKeyManager` (`generate_wireguard_keys`, `get_all_wireguard_peers`, `revoke_wireguard_keys`, `get_wireguard_config`, `_allocate_ip`, `WireGuardPeer` dataclass, own `_peers` state + lifecycle). Keep file path for now.
- Modify: `hub_api/modules/sase/certs/__init__.py` (export `WireGuardKeyManager`)
- Modify: `hub_api/modules/sase/auth/__init__.py` → re-export from `hub_api.core` (transitional shim, removed in Phase 4) OR delete + retarget importers. Prefer **retarget importers**.
- Modify importers: `hub_api/api/headend_routes.py` (`CertificateManager`, `UserManager` → `from hub_api.core import ...`), `hub_api/modules/sase/api/certs.py` (PKI `CertificateManager` → core), `hub_api/modules/sase/api/wireguard.py` (`WireGuardKeyManager` → `hub_api.modules.sase.certs`), `hub_api/modules/sase/api/jwt.py` (`UserManager` → core)
- Move tests: `test_sase_certs.py`→`test_core_certs.py` (PKI) + keep WG assertions in a `test_sase_wireguard_keys.py`; `test_sase_user_manager.py`→`test_core_user_manager.py`; `test_sase_backup.py`+`test_backup_isolation_realdal.py` → `test_core_backup*.py`. Update their imports. **No assertions removed.**
- Modify: `hub_api/modules/sase/__init__.py::module()` — drop `certs`, `jwt`, `auth` flags/entitlements that are now core-owned **only if** their blueprints move; the cert/jwt **blueprints stay registered under sase for this phase** (endpoints unchanged) importing managers from core. Contract `migrations` unchanged this phase.

**Interfaces:**
- Produces: `hub_api.core.CertificateManager` (PKI), `hub_api.core.UserManager`, `hub_api.core.BackupManager`; `hub_api.modules.sase.certs.WireGuardKeyManager`.
- Consumes: Task 0 audit script.

- [ ] **Step 1** Create worktree + branch off `release/v1.2.X`; push `-u` immediately.
- [ ] **Step 2** Create `hub_api/core/` package; move `UserManager` → `core/auth.py`, `backup/` → `core/backup/` verbatim (no logic change); add re-exports to `core/__init__.py`.
- [ ] **Step 3** Split `certificate_manager.py`: copy PKI methods+CA state into `core/certificates.py::CertificateManager`; reduce the sase file to `WireGuardKeyManager` (WG methods+`_peers` state). Confirm WG methods reference no CA state (recon confirms they don't).
- [ ] **Step 4** Retarget all importers (headend_routes, sase api certs/jwt/wireguard, package `__init__` re-exports).
- [ ] **Step 5** Move/rename the affected test files; update their imports; verify no assertion loss (`git diff --stat` shows renames, not shrink).
- [ ] **Step 6** `python3 scripts/audit_imports.py --module sase --forbid sdwan,ziti` → exit 0. `grep -rn "modules.sase.auth\|modules.sase.backup" hub_api --include=*.py` → only transitional shims (or none).
- [ ] **Step 7** Green gate in batches: `pytest hub_api/tests/test_core_*.py -v`, then `pytest hub_api/tests/test_sase_*.py -v`, then a full `pytest hub_api/tests/` (batched). 840+ pass, count not reduced.
- [ ] **Step 8** App boot check: `python3 -c "import hub_api.app as a; a.create_app()"` (or the real factory name) imports clean.
- [ ] **Step 9** Commit, push, open PR into `release/v1.2.X`; merge when fully green.

---

## Phase 3: `sdwan` module extraction

**Branch:** `feature/split-sdwan-extraction` off the **Phase 2 branch** (stacked; rebase onto release once Phase 2 merges). Worktree under `.worktrees/`.

**Files:**
- Create: `hub_api/modules/sdwan/__init__.py` (`module()` → `ModuleContract(name="sdwan", ...)`), `sdwan/api/__init__.py` (blueprints tuple)
- Move: `sase/api/{clusters,clients,status,wireguard}.py` → `sdwan/api/`
- Move: `sase/orchestrator/` → `sdwan/orchestrator/` (`cluster_manager.py`, `client_registry.py`, `__init__.py`)
- Move: `sase/network/{vrf_manager,port_manager}.py` → `sdwan/network/`
- Move: `sase/firewall/access_control.py` (+`__init__.py`) → `sdwan/firewall/`
- Move: `sase/certs/certificate_manager.py` (now `WireGuardKeyManager`) → `sdwan/certs/wireguard_manager.py`; `sdwan/certs/__init__.py` exports it
- Modify: `hub_api/modules/__init__.py::__all__` — add `"sdwan"` (ordering after `sase`)
- Modify: `hub_api/api/headend_routes.py` — retarget `AccessControlManager`, `PortConfigManager`, `ClusterManager` → `hub_api.modules.sdwan.*`; `WireGuardKeyManager` (peers endpoint) → `hub_api.modules.sdwan.certs`
- Modify: `sase/api/{clients,clusters,status}.py` moved to sdwan retarget orchestrator imports to `sdwan.orchestrator`; `sdwan/api/wireguard.py` retargets `WireGuardKeyManager` → `sdwan.certs.wireguard_manager`
- Modify: `sdwan/__init__.py::module()` contract — `name="sdwan"`; nav `Clusters`/`Clients`/`Status`; flags `tobogganing.sdwan.{clusters,clients,status,wireguard,large_cluster}`; entitlements (clusters/clients/status/wireguard = community, large_cluster = professional); `migrations=["0002","0003","0004","0007","0009"]` (firewall, vrf, ports, orchestrator, cluster_api_key — **0009 corrected in here per recon**)
- **Mount-compatibility:** registry mounts at `/api/v1/{name}{prefix}`, so moving clusters/clients/status/wireguard from `sase` to `sdwan` changes URLs `/api/v1/sase/clusters` → `/api/v1/sdwan/clusters`. **Spec §Notes says no URL changes.** Resolve by giving the sdwan blueprints an explicit `url_prefix` that preserves the external path, OR (preferred) confirm with the data-plane consumers (hub-router/testserver Go clients) whether `/sase/*` is a hardcoded contract. **DECISION REQUIRED at Phase 3 start** — see "Open decision" below; default to preserving `/api/v1/sase/*` via explicit prefixes until the Go clients are updated in lockstep.
- Move tests: `test_sase_api_{clients,clusters,status}.py`, `test_sase_ports.py`, `test_sase_vrf.py`, `test_sase_firewall.py`, `test_sase_orchestrator_realdal.py` → `test_sdwan_*.py`; retarget imports.

**Interfaces:**
- Produces: `hub_api.modules.sdwan.certs.wireguard_manager.WireGuardKeyManager`; sdwan blueprints; sdwan contract.
- Consumes: `hub_api.core` (Phase 2).

- [ ] **Step 1** Worktree/branch off Phase 2 branch; push.
- [ ] **Step 2** Create `sdwan/` skeleton + `module()` contract.
- [ ] **Step 3** `git mv` the api/orchestrator/network/firewall/certs files into `sdwan/`; fix intra-module relative imports.
- [ ] **Step 4** Add `"sdwan"` to `modules.__all__`.
- [ ] **Step 5** Retarget `headend_routes.py` + any remaining importers to `hub_api.modules.sdwan.*`.
- [ ] **Step 6** Resolve mount-compat (see Open decision); wire `url_prefix` to preserve external URLs.
- [ ] **Step 7** Move/rename tests; update imports; no assertion loss.
- [ ] **Step 8** Audits: `audit_imports.py --module sdwan --forbid sase,ziti` → 0; `--module sase --forbid sdwan,ziti` → 0 (sase must no longer reference moved pieces).
- [ ] **Step 9** Green gate batched (`test_sdwan_*`, `test_sase_*`, full); app boot check; count not reduced.
- [ ] **Step 10** Commit, push, PR into release; merge when green. Rebase onto release if Phase 2 already merged.

**Open decision (Phase 3):** external URL preservation for moved transport endpoints (`/api/v1/sase/{clusters,clients,status,wireguard}` → `/sdwan/*`). Confirm whether Go data-plane clients hardcode `/sase/*`. Default: preserve old paths via explicit blueprint `url_prefix` + add new `/sdwan/*` aliases, deprecate `/sase/*` transport paths later.

---

## Phase 4: `sase` reduction (security inspection + context-auth)

**Branch:** `feature/split-sase-reduction` off the **Phase 3 branch** (stacked).

**Files:**
- Delete (moved to core in Phase 2): `sase/api/{jwt,certs}.py`, `sase/auth/` (if shims remain), `sase/backup/` — and remove their blueprints from `sase/api/__init__.py`. The cert/jwt **endpoints relocate to core-owned blueprints registered directly in `app.py`** (like `auth_bp`/`portal_bp`/`headend_bp`), preserving `/api/v1/...` paths.
  - Create: `hub_api/core/api/__init__.py`, `hub_api/core/api/certs.py`, `hub_api/core/api/jwt.py` (the blueprints, importing core managers); register in `app.py` alongside the other direct blueprints.
- Delete (moved to sdwan in Phase 3): `sase/api/{clusters,clients,status,wireguard}.py`, `sase/orchestrator/`, `sase/network/`, `sase/firewall/`, `sase/certs/` — confirm already `git mv`d out; remove empty dirs.
- Keep: `sase/security/{feeds,scanner,protection}/` (unchanged).
- Create: `hub_api/modules/sase/auth/context.py` — **scaffold** for context-based auth (threat-intel lookup, impossible-travel, risk-based step-up). Minimal, flag-gated, contract-registered; no heavy implementation (that's a later feature phase). 2-3 line docstrings; a `ContextAuthEvaluator` class stub with typed method signatures + `NotImplementedError`-free safe defaults (returns "allow" with reason) so tests can assert wiring.
- Modify: `sase/__init__.py::module()` — nav `Security` only; flags `tobogganing.sase.{threat_feeds,scanner,protection,context_auth}`; entitlements (threat_feeds/scanner/protection = community, context_auth = professional per taxonomy); blueprints = security blueprints (+ context_auth if it exposes routes); `migrations=["0006","0008"]` (per-tenant-unique touching security + security tables; **verify 0005/0006 ownership** — 0005 is user fields → core, 0006 per-tenant-unique → whichever tables; assign precisely during the task by reading each migration).
- Move tests: keep `test_sase_feeds*.py`, `test_sase_scanner.py`, `test_sase_protection.py`; the moved-out ones already relocated in Phases 2-3. Add `test_sase_context_auth.py` for the new stub wiring.

- [ ] **Step 1** Worktree/branch off Phase 3 branch; push.
- [ ] **Step 2** Create core cert/jwt blueprints under `hub_api/core/api/`; register in `app.py`; delete the sase copies; confirm endpoint URLs identical (route + methods diff = none).
- [ ] **Step 3** Remove now-empty sase subpackages; prune `sase/api/__init__.py` blueprint tuple to security(+context) only.
- [ ] **Step 4** Add `sase/auth/context.py` stub + register flag/entitlement in the contract.
- [ ] **Step 5** Rewrite `sase/__init__.py::module()` to the reduced contract; re-partition `migrations` metadata precisely (read each claimed revision to confirm the table it creates belongs to sase).
- [ ] **Step 6** Audits all three modules → 0. App boot check.
- [ ] **Step 7** Green gate batched; count not reduced; confirm cert/jwt endpoints still answer (contract test or route list diff).
- [ ] **Step 8** Commit, push, PR into release; merge when green.

---

## Phase 5: `ziti` module scaffold (greenfield — independent)

**Branch:** `feature/split-ziti-scaffold` off `release/v1.2.X` **directly** (no dependency on 2–4; can run in parallel).

**Files:**
- Create: `hub_api/modules/ziti/__init__.py` (`module()` → contract: nav `Identity`, flags `tobogganing.ziti.{control_plane,sdk_integration}`, entitlements control_plane=professional, sdk_integration=enterprise, `migrations=[]`, blueprints=[] or a health-only bp)
- Create: `hub_api/modules/ziti/api/__init__.py` (empty blueprints tuple or a single `GET /api/v1/ziti/health` stub)
- Create: `hub_api/modules/ziti/{orchestrator,models}/__init__.py` (placeholder packages)
- Create: `hub_api/modules/ziti/README.md` (roadmap: OpenZiti control-plane + SDK integration, coexists with/alternative to sdwan tunneling; no transport dependency)
- Modify: `hub_api/modules/__init__.py::__all__` — add `"ziti"`
- Create: `hub_api/tests/test_ziti_module.py` — asserts `module()` returns a contract named `ziti`, flags default present, registry mounts without error, no import errors.
- **No OpenZiti SDK dependency added** unless it is available on PyPI and pins cleanly with hashes — scaffold imports must not break the suite if the SDK is absent. Gate any `import openziti` behind a try/except with a logged "not installed" and a flag-off default.

- [ ] **Step 1** Worktree/branch off release; push.
- [ ] **Step 2** Create the ziti package + contract + placeholders + README.
- [ ] **Step 3** Add `"ziti"` to `modules.__all__`.
- [ ] **Step 4** Write `test_ziti_module.py`; run it + `audit_imports.py --module ziti --forbid sdwan,sase` → 0.
- [ ] **Step 5** Green gate batched (module loads, no import errors); count grows by the new test, none reduced.
- [ ] **Step 6** Commit, push, PR into release; merge when green.

---

## Self-review

- **Spec coverage:** placement rules (§Placement) → Phases 2-5 map each row; CertManager split (§Hard-Seam 1) → Phase 2 Step 3 + Phase 3 move; headend_routes span (§Hard-Seam 2) → Phase 2 Step 4 + Phase 3 Step 5; migration partitioning (§Hard-Seam 3) → **deviated** (metadata-only, flagged); contract partitioning (§Hard-Seam 4) → inline `module()` edits each phase; flag migration (§Flag-Key) → contract flag lists per phase (transport flags `sase.*`→`sdwan.*`); ziti scaffold (§Phase 5) → Phase 5. SASE security/enforcement design (mirror hooks, STIX/Valkey, SWG, block pages) is **future feature work**, explicitly out of this reorg's scope.
- **Placeholder scan:** context-auth and ziti are intentional scaffolds (spec-sanctioned "greenfield/placeholder"); all file moves are concrete paths.
- **Type/name consistency:** `CertificateManager` (PKI, core) vs `WireGuardKeyManager` (WG, sase→sdwan) used consistently; `module()` factory + `ModuleContract` fields match `hub_api/registry/contract.py`.
