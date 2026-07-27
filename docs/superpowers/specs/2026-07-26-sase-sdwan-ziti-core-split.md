# Re-Decomposition Spec: SASE → SDWAN + ZITI + Core Split

**Date**: 2026-07-26  
**Status**: Finalized; ready for sequencing and implementation plan  
**Author**: PenguinTech arch (Claude)  
**Cross-references**: 
- Module taxonomy: `docs/architecture/module-taxonomy.md`
- Hub topology: `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md`
- Network diagram: `docs/architecture/hub-network-topology.md`

---

## Context: Product Positioning

Tobogganing is a **lightweight, open-source-driven alternative to ZScaler** (SASE/SSE). The module taxonomy reflects this positioning:
- **`sdwan`** = Connectivity layer (overlay transport: WireGuard, IPsec, OpenVPN; routing via FRR/OSPF)
- **`sase`** = Security-Service-Edge layer (inspection, threat-feeds, context-based auth, mirror hooks to external analysis tools)
- **`ziti`** = Alternative identity overlay (greenfield; can coexist with or replace `sdwan` tunneling)
- **core** = Infrastructure (auth, PKI, backup — the foundation all layers depend on)

This decomposition makes clear what each component does and how it positions against ZScaler's architecture.

---

## Goal

Decompose the monolithic `hub_api/modules/sase/` module into four functional targets — **core** (management-plane), **`sdwan`** (overlay transport + routing), **`ziti`** (greenfield identity overlay), and **`sase`** (security inspection + context-auth) — such that:

1. **Placement rules** are explicit: transport layer → `sdwan`, management-plane (auth/PKI/backup) → **core**, greenfield identity → **`ziti`** (standalone), security inspection + context-auth → **`sase`**.
2. **No cross-module imports** between `sdwan` ↔ `sase` or `ziti` ↔ (`sdwan`/`sase`); all can import **core**.
3. **Licensing is clear**: core (free), `sdwan` (Community→Professional), `ziti` (Professional→Enterprise), `sase` (Community→Enterprise, tiered).
4. **Full test parity** is maintained across the split; no test coverage regressions.
5. **Migrations** are properly partitioned and version sequencing is unbroken.

---

## SASE Traffic-Mirror Hooks & External Analysis Tools

**SASE owns the traffic-mirror delivery layer.** The `sase` module provides:

- **SPAN / monitor-port hooks** — intercept and mirror traffic from Inspection Points (hub-client, bridge-router) to external analysis tools
- **Mirror integration adapters** — deliver mirrored streams to:
  - **Arkime** (PCAP collection & indexing)
  - **Zeek** (network analysis & IDS)
  - **Suricata** (IDS/IPS threat detection)

**Optional Helm Sub-Charts**: Arkime, Zeek, and Suricata are packaged as **optional Helm sub-charts** in the product's Helm deployment. They are:
- **Off by default** — operators opt-in to deploy
- **No hard dependency** — `sase` module functions without them; mirror hooks remain available but unused
- **Deployment requirement**: if enabled, the operator must configure mirror destinations in `sase` config (Arkime endpoint, Zeek listener, Suricata interface)

This decoupling keeps the baseline product lightweight while providing the analytical depth required for enterprise threat hunting and compliance audits.

---

## Placement Rules

| Component | Rule | Target |
|---|---|---|
| **Transport layer** | WireGuard, IPsec, OpenVPN tunneling + routing (FRR/OSPF/VRF) | **`sdwan`** |
| **Management-plane** | User logins, API keys, JWT validation, X.509 PKI certs, encrypted backup | **core** |
| **Identity overlay** | OpenZiti control-plane + greenfield auth model (no hard dependency on transport) | **`ziti`** (new module) |
| **Security inspection** | IDS/IPS threat-feeds, vuln scanner, DDoS/rate-limit, context-based auth (threat intel, impossible travel, risk-based step-up) | **`sase`** |

---

## Current → Target File Mapping

The monolithic `hub_api/modules/sase/` directory splits as follows:

| Current path | Component | → Target | Notes |
|---|---|---|---|
| `api/jwt.py` | JWT issue/validate | **core** | Unifies with `auth.user_manager` |
| `api/certs.py` | X.509 PKI management | **core** | Move `CertificateManager` (PKI only) here |
| `auth/user_manager.py` | Username/password, API keys | **core** | Unify auth in core |
| `certs/certificate_manager.py` (PKI methods) | X.509 cert lifecycle | **core** | Split: PKI → core, WireGuard keys → `sdwan` |
| `certs/certificate_manager.py` (WireGuard methods) | `generate_wireguard_keys`, `get_all_wireguard_peers`, `revoke_wireguard_keys`, `get_wireguard_config` | **`sdwan`** | New class: `WireGuardKeyManager` |
| `backup/` | Encrypted S3 backup + restore | **core** | Ops infrastructure (not module-licensed) |
| `api/clusters.py` | Cluster CRUD, orchestration | **`sdwan`** | Transport entity |
| `api/clients.py` | Client CRUD, status, VPN config | **`sdwan`** | Transport entity |
| `api/status.py` | Cluster/client status endpoints | **`sdwan`** | Transport entity |
| `api/wireguard.py` | WireGuard peer management, config | **`sdwan`** | Transport entity |
| `orchestrator/` | Cluster/client failover, scaling | **`sdwan`** | Transport orchestration |
| `network/vrf_manager.py` | VRF, FRR, OSPF routing | **`sdwan`** | Routing layer |
| `network/port_manager.py` | Headend port allocation + binding | **`sdwan`** | Transport data-plane |
| `firewall/access_control.py` | Basic ACL rules | **`sdwan`** | Baseline data-plane policy |
| `security/feeds/` | Threat-feed integration | **`sase`** | Security inspection |
| `security/scanner/` | Vulnerability scanner | **`sase`** | Security inspection |
| `security/protection/` | DDoS/rate-limit/IPS | **`sase`** | Security inspection |
| `security/mirror/` | Traffic-mirror hooks (SPAN/monitor-port) → Arkime, Zeek, Suricata | **`sase`** | Mirror delivery + optional Helm sub-charts |
| (OpenZiti — no current code) | OpenZiti control + SDK integration | **`ziti`** | New module scaffold |
| `hub_api/modules/waddleperf_*` | Perf testing (`perftest_cluster`, `perftest_client`, `perftest_c2c`) | **`perftest`** | Isolated rename; zero cross-module entanglement |

---

## Hard Seams (Implementation Challenges)

### 1. `CertificateManager` Dual-Purpose Split

**Problem**: `hub_api/modules/sase/certs/certificate_manager.py` contains both X.509 PKI management and WireGuard key operations in a single class.

**Solution**:
- Extract X.509 PKI methods → new **core** class `CertificateManager` (PKI-only):
  - `generate_x509(subject, validity_days)`
  - `revoke_x509(cert_id)`
  - `list_x509_certs()`
  - `validate_x509(cert_data)`
  - `get_x509_config()`
- Extract WireGuard key methods → new **`sdwan`** class `WireGuardKeyManager`:
  - `generate_wireguard_keys(client_id)`
  - `get_all_wireguard_peers(cluster_id)`
  - `revoke_wireguard_keys(key_id)`
  - `get_wireguard_config(client_id)`
- Update all import statements in affected modules.

### 2. `hub_api/api/headend_routes.py` Spans Multiple Targets

**Problem**: The flat data-plane API imports and wires together `auth.user_manager`, `certs.certificate_manager`, `firewall.access_control`, `network.port_manager`, `orchestrator.cluster_manager` — spans **core + `sdwan`**.

**Decision**: Keep `headend_routes.py` in **`sdwan`** (transport home). Expose core helpers via **core** shim exports so `sdwan` imports remain **local**:
- `hub_api/core/exports.py` → re-exports `CertificateManager`, `UserManager`, `BackupManager`
- `sdwan/api/headend_routes.py` imports `from hub_api.core import CertificateManager` (not direct path)
- This avoids circular imports and keeps each module's API surface clear.

### 3. Alembic Migrations Partitioning

**Problem**: Migrations `0002`–`0008` are owned wholesale by the `sase` contract (blueprints, schema, indices). After the split, each module must own its own migrations.

**Solution**:
- Create new migration heads:
  - `hub_api/core/migrations/` — migrations for `users`, `api_keys`, `certificates` (X.509), `backups` tables
  - `hub_api/sdwan/migrations/` — migrations for `clusters`, `clients`, `wireguard_peers`, `ports`, `vrf_routes`, `acl_rules` tables
  - `hub_api/sase/migrations/` — migrations for `threat_feeds`, `scan_results`, `protection_rules` tables
  - `hub_api/ziti/migrations/` — new (empty initially; reserved for OpenZiti schema when implemented)
- Re-number migrations per module (`001_init.sql`, `002_add_idx.sql`, etc.) after alembic split.
- Alembic branches (one head per module) ensure migrations are applied per-module order.
- **Verification**: full migration replay from scratch produces identical schema.

### 4. Monolithic `ModuleContract` Partitioning

**Problem**: The single `sase/contract.py` blueprint includes nav items, Quart routes, PostHog flags, tier gating, and entitlements for all current features.

**Solution**:
- Each module defines its own `ModuleContract`:
  - `core/contract.py` — no nav/flags/tier (always-on, free)
  - `sdwan/contract.py` — nav (Clusters, Clients, Status), flags (`tobogganing.sdwan.*`), tier (Community→Professional)
  - `sase/contract.py` — nav (Security), flags (`tobogganing.sase.*`), tier (Community→Enterprise, tiered)
  - `ziti/contract.py` — nav (Identity), flags (`tobogganing.ziti.*`), tier (Professional→Enterprise)
  - `perftest/contract.py` — nav (Performance), flags (`tobogganing.perftest.*`), tier (Community→Professional)
- Hub's `ModuleRegistry` aggregates all contracts at startup.
- Each contract declares its own entitlements (which feature → which tier).

---

## Flag-Key Migration

### Current → Target Naming

| Current key | → Target key | Reason |
|---|---|---|
| `tobogganing.sase.clusters` | `tobogganing.sdwan.clusters` | Transport feature |
| `tobogganing.sase.clients` | `tobogganing.sdwan.clients` | Transport feature |
| `tobogganing.sase.status` | `tobogganing.sdwan.status` | Transport feature |
| `tobogganing.sase.wireguard` | `tobogganing.sdwan.wireguard` | Transport feature |
| `tobogganing.sase.large_cluster` | `tobogganing.sdwan.large_cluster` | Transport feature |
| `tobogganing.sase.threat_feeds` | `tobogganing.sase.threat_feeds` | (unchanged) Security inspection |
| `tobogganing.sase.scanner` | `tobogganing.sase.scanner` | (unchanged) Security inspection |
| `tobogganing.sase.protection` | `tobogganing.sase.protection` | (unchanged) Security inspection |
| `tobogganing.sase.context_auth` | `tobogganing.sase.context_auth` | (unchanged) Context-based auth |
| (new) | `tobogganing.ziti.control_plane` | OpenZiti (greenfield) |
| (new) | `tobogganing.ziti.sdk_integration` | OpenZiti client SDK |
| `tobogganing.waddleperf_cluster` | `tobogganing.perftest.cluster` | Rename only (isolated) |
| `tobogganing.waddleperf_client` | `tobogganing.perftest.client` | Rename only (isolated) |
| `tobogganing.waddleperf_c2c` | `tobogganing.perftest.c2c` | Rename only (isolated) |

### PostHog Migration Script

```bash
# Update all feature-flag references in code + tests
find . -type f -name "*.py" \
  -exec sed -i 's/tobogganing\.sase\.clusters/tobogganing.sdwan.clusters/g' {} \; \
  -exec sed -i 's/tobogganing\.sase\.clients/tobogganing.sdwan.clients/g' {} \; \
  -exec sed -i 's/tobogganing\.sase\.status/tobogganing.sdwan.status/g' {} \; \
  -exec sed -i 's/tobogganing\.sase\.wireguard/tobogganing.sdwan.wireguard/g' {} \; \
  -exec sed -i 's/tobogganing\.waddleperf_cluster/tobogganing.perftest.cluster/g' {} \;

# In PostHog self-hosted instance:
# 1. Create new feature flags: tobogganing.sdwan.*, tobogganing.ziti.*
# 2. Copy flag state from old keys: tobogganing.sase.{clusters,clients,status,wireguard,large_cluster} → new tobogganing.sdwan.* keys
# 3. Keep old keys for read-only (for 2-3 weeks during migration)
# 4. Deprecate old keys in docs
```

---

## Sequencing

### Phase 1: `perftest` Rename (Independent)

**Scope**: Isolated rename of `waddleperf_*` module to `perftest`. Zero cross-module entanglement.

**Steps**:
1. Rename `hub_api/modules/waddleperf_*` → `hub_api/modules/perftest/`
2. Update imports in blueprints and tests
3. Rename PostHog flags: `tobogganing.waddleperf_*.*` → `tobogganing.perftest.*.*`
4. Update Alembic: separate migration head for perftest
5. Test: full suite pass
6. Merge PR #74 (or whatever number)

**Estimated effort**: ~c2c-scale (paths, flags, tests)

### Phase 2: Core-Auth + Backup Extraction

**Scope**: Extract management-plane infrastructure (auth, PKI, backup) into **core** (non-module).

**Steps**:
1. Create `hub_api/core/` directory structure:
   - `hub_api/core/__init__.py`
   - `hub_api/core/auth.py` — `UserManager`, password/API-key ops
   - `hub_api/core/certificates.py` — `CertificateManager` (PKI-only)
   - `hub_api/core/backup.py` — `BackupManager`
   - `hub_api/core/exports.py` — re-exports for callers
   - `hub_api/core/migrations/` — Alembic head for core tables
   - `hub_api/core/contract.py` — (minimal; no nav/flags/tier since core is always-on)
2. Migrate `sase/api/jwt.py`, `sase/auth/user_manager.py` → **core**
3. Split `sase/certs/certificate_manager.py`: PKI → **core**, WireGuard → **`sdwan`**
4. Move `sase/backup/` → **core**
5. Update all imports in `sase`, `sdwan`, tests
6. Create core Alembic migrations (`users`, `api_keys`, `certificates`, `backups`)
7. Test: full suite pass, zero test coverage regression
8. Merge PR (part 1 of the split)

**Estimated effort**: Large (auth/backup impact broad surface)

### Phase 3: `sdwan` Module Extraction

**Scope**: Extract transport layer (clusters, clients, orchestration, routing, ports, firewall) into **`sdwan`** module.

**Steps**:
1. Create `hub_api/modules/sdwan/` directory structure (mirrors `sase` layout)
2. Move `sase/api/{clusters,clients,status,wireguard}.py` → `sdwan/api/`
3. Move `sase/orchestrator/` → `sdwan/orchestrator/`
4. Move `sase/network/{vrf_manager,port_manager}.py` → `sdwan/network/`
5. Move `sase/firewall/access_control.py` → `sdwan/firewall/`
6. Create `WireGuardKeyManager` in `sdwan/certs/wireguard_manager.py` (split from `sase`)
7. Keep `hub_api/api/headend_routes.py` in `sdwan/api/` (or optionally in root `hub_api/api/` if it serves as a bridge)
8. Create `sdwan/contract.py` with nav, flags, tier gating
9. Create `sdwan/migrations/` (Alembic head)
10. Update all imports; verify no `sdwan` → `sase` or `sase` → `sdwan` cross-imports
11. Test: full suite pass
12. Merge PR (part 2 of the split)

**Estimated effort**: Largest (transport is the bulk of the current codebase)

### Phase 4: `sase` Module Reduction

**Scope**: Reduce `sase` to security inspection + context-based auth (feeds, scanner, protection, context-auth).

**Steps**:
1. Delete `sase/api/{jwt,certs}.py`, `sase/auth/`, `sase/backup/` (moved to core in Phase 2)
2. Delete `sase/api/{clusters,clients,status,wireguard}.py`, `sase/orchestrator/`, `sase/network/`, `sase/firewall/` (moved to `sdwan` in Phase 3)
3. Keep `sase/security/{feeds,scanner,protection}/` — IDS/IPS, scanning, protection
4. Add (or move) context-based auth logic to `sase/auth/context.py` (threat intel, impossible travel, risk-based step-up)
5. Update `sase/contract.py` to reflect new nav (Security only) + new flags
6. Update Alembic migrations: only schema for threat_feeds, scan_results, protection_rules, context_auth tables
7. Test: full suite pass
8. Merge PR (part 3 of the split)

**Estimated effort**: Medium (mostly deletions; smaller codebase post-split)

### Phase 5: `ziti` Module Scaffold

**Scope**: Create new **`ziti`** module scaffold (control-plane + client SDK integration) — greenfield, no code migration.

**Steps**:
1. Create `hub_api/modules/ziti/` directory structure
2. Create `ziti/contract.py` with nav (Identity), flags (`tobogganing.ziti.*`), tier (Professional→Enterprise)
3. Create `ziti/migrations/` (Alembic head; initially empty)
4. Create placeholder modules: `ziti/api/`, `ziti/orchestrator/`, `ziti/models/`
5. Add OpenZiti Python SDK imports + basic initialization (do not implement features yet; scaffold only)
6. Create `ziti/README.md` documenting the future roadmap
7. Test: module loads, contract registers, no import errors
8. Merge PR (part 4 of the split)

**Estimated effort**: Small (scaffold only; no feature implementation)

### Summary Sequencing

```
Phase 1 (perftest rename) → Phase 2 (core extraction) → Phase 3 (sdwan extraction) → Phase 4 (sase reduction) → Phase 5 (ziti scaffold)
```

Each phase is a separate PR. Phases 2–5 are sequentially dependent (each phase assumes prior phases landed). Phase 1 is independent and can land in parallel.

---

## Verification Approach

### Per-Module Contract Tests

Each module's contract is tested independently:

```python
# sdwan/tests/test_contract.py
def test_sdwan_contract_flags():
    contract = SDWanModuleContract()
    flags = contract.feature_flags()
    assert 'tobogganing.sdwan.clusters' in flags
    assert flags['tobogganing.sdwan.clusters'].tier == 'Community'

def test_sdwan_contract_no_cross_imports():
    import sdwan.api.clusters
    # Verify no 'from hub_api.modules.sase' or 'import sase'
```

### Cross-Module Import Audit

- `sdwan` does NOT import from `sase` or `ziti`
- `sase` does NOT import from `sdwan` or `ziti`
- `ziti` does NOT import from `sdwan` or `sase`
- All modules **can** import from **core**

```bash
# Automated check in CI
python scripts/audit_imports.py --module sdwan --forbid sase,ziti
python scripts/audit_imports.py --module sase --forbid sdwan,ziti
python scripts/audit_imports.py --module ziti --forbid sdwan,sase
```

### Full Suite Parity

- All existing tests pass with ≥90% coverage
- No test deletions (only reorganization)
- Smoke tests (build, run, health checks) pass
- API contract tests verify all endpoints still work

```bash
make test                           # ≥90% coverage
make smoke-test                     # Health checks, basic endpoints
pytest tests/api/sdwan/ -v          # sdwan endpoints (clusters, clients, status, wireguard)
pytest tests/api/sase/ -v           # sase endpoints (feeds, scanner, protection)
pytest tests/api/core/ -v           # core endpoints (login, certs, backup)
```

### Migration Audit

- `alembic upgrade head` produces identical schema (before vs. after split)
- No orphaned migrations or version gaps
- Each module's Alembic head is independently testable

```bash
# Test migration sequence
alembic upgrade head --tag core
alembic upgrade head --tag sdwan
alembic upgrade head --tag sase
alembic upgrade head --tag ziti
# Verify all tables present and consistent
```

### Flag Scope Validation

- PostHog flags renamed correctly
- Tier gates applied per feature
- Old flag keys deprecated (read-only fallback for 2–3 weeks)

```python
# tests/test_flag_migration.py
def test_sdwan_flags_renamed():
    # Verify old key redirects to new key with same state
    old = client.is_feature_enabled('tobogganing.sase.clusters', distinct_id)
    new = client.is_feature_enabled('tobogganing.sdwan.clusters', distinct_id)
    assert old == new  # During migration window
```

---

## Notes

- **No breaking changes to external API** — all endpoint URLs, request/response schemas remain unchanged
- **Backwards compatibility** — old flag keys redirect to new keys (PostHog side) during 2–3 week migration window
- **Operator guide** — document the module structure change in deployment guide and runbooks
- **Future work** — OpenZiti is greenfield; implementation roadmap separate from this re-decomposition

---

## Cross-References

- **Module Taxonomy**: `docs/architecture/module-taxonomy.md` (placement rules, current state)
- **Hub Topology & Architecture**: `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md` (system design, contracts)
- **Network Diagram**: `docs/architecture/hub-network-topology.md` (visual reference)
