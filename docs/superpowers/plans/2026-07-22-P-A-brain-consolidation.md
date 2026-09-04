# P-A — Quart Brain Consolidation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** One Quart brain named `hub-api`: license gate wired to the real client, the ≥2-hub-router production-readiness warning added, the py4web `services/hub-api` endpoints ported into the Quart brain and the py4web service deleted, and `core/` renamed to `hub-api`.

**Architecture:** hub-api is the single control plane / config source (gRPC to all data-plane components). See `docs/superpowers/specs/2026-07-22-hub-topology-quart-brain-design.md`.

**Tech Stack:** Python 3.13 / Quart / penguin-dal / SQLAlchemy+Alembic / pytest. Work on a branch off `release/v1.2.X`.

## Global Constraints

- Every runtime DB op via penguin-dal; schema/migrations via SQLAlchemy+Alembic only.
- Type hints on every function; `mypy --strict`, flake8, black, isort, bandit all pass.
- ≥90% coverage on touched code. Commit freely on the branch; do not push.
- No feature un-gated: flags default OFF; license entitlement checked via the real client (this plan makes that real).
- Order matters: the surgical fixes (Tasks 1–2) land first; the high-churn rename (Task 5) lands last, on an otherwise-green tree.

---

## Task 1: License gate calls the real client

**Files:**
- Modify: `core/entitlements/gate.py` (the `_is_licensed_for_tier` stub, ~L39-55)
- Modify: `core/tests/conftest.py` (replace the monkeypatch of the private fn with a license-tier fixture)
- Test: `core/tests/test_entitlements_gate.py` (new)

**Interfaces:**
- Consumes: `shared.licensing.python_client` — use `get_tier()` if present (returns `free`/`professional`/`enterprise`); otherwise derive tier from `check_feature`. Read the module before wiring.
- Produces: `_is_licensed_for_tier(tier: str) -> bool` that compares the *licensed* tier against the *required* tier using the ordering `free/community < professional < enterprise`, with graceful degradation (cache last-known; on error, fall back to cached, default community).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_entitlements_gate.py
import pytest
from core.entitlements import gate

@pytest.mark.parametrize("licensed,required,ok", [
    ("enterprise", "enterprise", True),
    ("enterprise", "professional", True),
    ("professional", "enterprise", False),
    ("professional", "professional", True),
    ("free", "professional", False),
    ("community", "community", True),
])
def test_tier_ordering(monkeypatch, licensed, required, ok):
    monkeypatch.setattr(gate, "_licensed_tier", lambda: licensed)
    assert gate._is_licensed_for_tier(required) is ok

def test_graceful_degradation_defaults_community(monkeypatch):
    def boom(): raise RuntimeError("license server down")
    monkeypatch.setattr(gate, "_resolve_tier_uncached", boom)
    gate._TIER_CACHE.clear()
    assert gate._is_licensed_for_tier("professional") is False
    assert gate._is_licensed_for_tier("community") is True
```

- [ ] **Step 2: Run to verify failure** — `pytest core/tests/test_entitlements_gate.py -v` → FAIL (`_licensed_tier`/`_resolve_tier_uncached` absent).

- [ ] **Step 3: Implement** — in `gate.py`: add `_resolve_tier_uncached()` (calls the real license client), `_licensed_tier()` (cached wrapper with graceful fallback to `_TIER_CACHE`, default `"community"` on error), and rewrite `_is_licensed_for_tier(tier)` to compare via an explicit `{"free":0,"community":0,"professional":1,"enterprise":2}` ordering. Remove the hardcoded `return False`.

- [ ] **Step 4: Update conftest** — replace any monkeypatch of `_is_licensed_for_tier` with a fixture that sets `_licensed_tier` (or the license client) to the tier a test needs; keep the existing "professional in tests" behavior via that fixture so the c2c/enterprise suites stay green.

- [ ] **Step 5: Run** — `pytest core/tests/test_entitlements_gate.py core/tests/test_c2c_*.py -v` → PASS. Then the full entitlements + c2c suites.

- [ ] **Step 6: Commit** — `fix(entitlements): wire license gate to real client (tier ordering + graceful degradation)`.

---

## Task 2: ≥2 hub-router production-readiness warning

**Files:**
- Modify/Create: `core/config/*` (hub-api config validation) — locate the config-validation entry point; add a check.
- Test: `core/tests/test_config_prod_readiness.py` (new)

**Interfaces:**
- Produces: `validate_prod_readiness(config) -> list[str]` returning warning strings; emits a "not production ready: <2 hub-routers" warning when the configured hub-router count < 2 and env is production.

- [ ] **Step 1: Write the failing test**

```python
def test_single_hub_router_warns():
    from core.config.readiness import validate_prod_readiness
    warns = validate_prod_readiness({"env": "production", "hub_router_count": 1})
    assert any("not production ready" in w and "hub-router" in w for w in warns)

def test_two_hub_routers_ok():
    from core.config.readiness import validate_prod_readiness
    assert validate_prod_readiness({"env": "production", "hub_router_count": 2}) == []
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** `core/config/readiness.py` with `validate_prod_readiness`; wire it into app startup logging (warn-level, non-fatal). Non-production envs skip the check.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `feat(hub-api): warn when production runs <2 hub-routers`.

> NOTE: if the hub-router entity isn't first-class yet, `hub_router_count` comes from config here; it re-binds to the live registry count in P-B.

---

## Task 3: Port py4web-only data-plane endpoints into the Quart brain

The Go data plane (hub-router headend) calls flat paths that today exist only in py4web `services/hub-api`. Port each into the Quart brain, served at the **flat path the data plane expects** (not under `/sase`), auth-enforced. One sub-task per endpoint group; each: read the py4web handler, write a failing Quart test, port, pass, commit.

**Endpoints to port (read `services/hub-api/api/routes.py` + `web/routes.py` for current behavior):**
- [ ] `GET /api/v1/firewall/rules` (py4web `web/routes.py:925`) — per-tenant firewall rules for the headend.
- [ ] `GET /api/v1/headend/<id>/ports` (py4web `web/routes.py:1025`) — dynamic port config for the headend.
- [ ] `GET /api/v1/wireguard/peers` (py4web `api/routes.py:742`) — headend peer list (Bearer cluster API key).
- [ ] Flat client/auth paths the Go clients call: `POST /api/v1/clients/register`, `GET /api/v1/clients/<id>/config`, `POST /api/v1/auth/token` (+ `/refresh`, `/validate`, `/revoke`), `POST /api/v1/wireguard/keys`. Reconcile status codes (Go expects 200 where Quart returns 201 — align).

**Per sub-task pattern:**
- [ ] Write a failing Quart blueprint test asserting path, method, auth, and response shape matching the py4web contract.
- [ ] Port the handler into the appropriate `core/modules/sase` blueprint at the flat path; use penguin-dal, tenant + scope middleware.
- [ ] Run the test → PASS; run the sase suite.
- [ ] Commit per endpoint group.

**Verification:** an integration test drives headend-shaped requests (firewall rules, ports, peers) against the Quart brain and asserts parity with the py4web responses.

---

## Task 4: Delete py4web `services/hub-api`

- [ ] Confirm Task 3 parity (all ported endpoints green; grep for any remaining caller of a py4web-only route).
- [ ] `git rm -r services/hub-api`; remove its Dockerfile, Helm chart/values, CI workflow steps, and any compose/k8s references.
- [ ] Run full suite + `make lint`; ensure nothing imports from the deleted service.
- [ ] Commit — `chore(hub-api): remove retired py4web service (endpoints ported to Quart brain)`.

---

## Task 5: Rename `core/` → `hub-api` (package `hub_api`)

High-churn; do LAST on a green tree. Open decision #1 resolved here: move to `services/hub-api/` with Python package `hub_api`.

- [ ] Full suite green baseline (`pytest core/tests -q`), record the count.
- [ ] `git mv core services/hub-api-tmp` then position as `services/hub-api/` (the py4web dir is already gone from Task 4); rename the import package `core` → `hub_api`.
- [ ] Mechanical import rewrite: replace `from core.` / `import core.` → `hub_api.` across the repo (code + tests). Update `pyproject.toml`/`setup`, Alembic `env.py` + `script_location`, entrypoints, Dockerfile(s), Helm values, and any `PYTHONPATH`/module refs.
- [ ] Run full suite → identical pass count to baseline. Run `mypy --strict`, flake8, black, isort.
- [ ] Update `docs/` references (`core/` → `hub-api`), including this plan's sibling spec.
- [ ] Commit — `refactor(hub-api): rename core → hub-api (Quart brain)`.

**Verification:** full suite green (same count as baseline), lint clean, app boots as `hub-api`, license gate returns 402 without entitlement / passes with it (no private-fn monkeypatch), ≥2-hub-router warning fires on 1.

---

## Self-review notes

- Tasks 1–2 are independent of the rename and unblock all Pro/Enterprise features (incl. bridge-router Enterprise gating) — that's why they lead.
- Task 3's flat-path decision (serve the data-plane paths where the Go headend already calls them) removes the seam that hid the client-can't-connect break; keep the `/api/v1/sase/*` control-plane paths for the portal/overlays.
- Cross-seam integration test (Task 3 verification) is the guard against the module-isolated, monkeypatched-license blind spot that hid prior breaks.
