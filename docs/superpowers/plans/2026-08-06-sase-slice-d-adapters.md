# SASE Slice D — Analysis Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`). Executed by `penguin-python-dev` (Python adapters) + `k8s-manifest-builder` (Helm sub-charts). PenguinTech conventions.

**Goal:** Per-tool adapters (Suricata/Zeek/Strelka/CAPE/Arkime) that parse native output → normalize IOCs to STIX → write to the existing Slice-A `BlocklistStore`; tools ship as optional off-by-default Helm sub-charts. Strictly out-of-band.

**Architecture:** `adapters/` package: an `AnalysisAdapter` base + per-tool parsers emitting `AdapterHit`s; `ingest()` reuses the Slice-A write path (`to_stix_indicator → Verdict → BlocklistStore.put`); a poller loop (mirrors `feeds/manager.py`); flag-gated; Helm sub-charts default false.

**Tech Stack:** Python 3.13, `hub_api/modules/sase/security/blocklist/` (Slice A), `CacheClient`, `aiohttp` (existing), `hub_api/scheduler`, Helm.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-06-sase-slice-d-adapters-design.md` — authoritative.
- Green gate: `python3 -m pytest hub_api/tests/` (baseline **923**, 0 fail) in batches; `create_app()` boots; `scripts/audit_imports.py --module sase --forbid sdwan,ziti` clean. Clean bytecode first.
- **Commit-completeness (hard):** `git status --short` empty + `git show HEAD --stat` after each commit; `git check-ignore` new files; after push confirm origin SHA matches.
- **Every adapter is fail-soft**: malformed input → `skipped++`, never raises/aborts; a tool unreachable → logged, retried next poll; NOTHING touches live traffic (out-of-band — read side-channels only).
- Reuse the Slice-A write path verbatim: `to_stix_indicator(ioc_type, value, severity=, source=, first_seen=)` → `Verdict(...)` → `await BlocklistStore(cache).put(verdict)`. `source` = the tool name. `ioc_type ∈ ("ip","domain","url","hash")`, `severity ∈ ("low","medium","high","critical")`.
- Flag `tobogganing.sase.adapters` — community, default OFF, gated via `@require_feature` where an API surface exists (adapters are mostly background — the flag gates the poller registration).
- Parsers pure-Python (json/csv) — **no new pip dep**; Strelka/CAPE via `aiohttp` if needed.
- Helm: use `authoring-helm-charts` skill; each tool `condition: <tool>.enabled` default false; securityContext per standards (Suricata NET_ADMIN/NET_RAW = documented ROOT/cap exception).

---

## Task 1: Adapter base + config

**Files:** Create `hub_api/modules/sase/security/adapters/__init__.py`, `adapters/base.py`, `adapters/config.py`; Test `hub_api/tests/test_sase_adapters_base.py`.

**Interfaces:**
- Produces: `@dataclass(slots=True) AdapterHit(ioc_type, value, severity, first_seen, detail)`; `@dataclass(slots=True) AdapterStats(source, scanned, stored, skipped)`; `class AnalysisAdapter(ABC)` with `source: str`, `abstract parse(raw) -> Iterable[AdapterHit]`, concrete `async ingest(raw, store) -> AdapterStats` (parse → `to_stix_indicator` → `Verdict` → `store.put`; per-hit try/except → skipped++); `AdapterConfig` reading per-tool enabled/endpoint from env (each default disabled).

- [ ] **Step 1:** Read `blocklist/curator.py::curate_one` for the exact normalize→Verdict→put sequence to reuse.
- [ ] **Step 2: Write failing test** — a `_StubAdapter(parse returns 2 hits)`; `await stub.ingest(raw, store)` → `stats.stored == 2` and `store.check` finds them with `source==stub.source`; a hit that raises in normalization → `skipped++`, run completes.
- [ ] **Step 3: Run → FAIL. Step 4: Implement** base (the `ingest` template calling the Slice-A write path) + config. **Step 5: Run → PASS. Step 6: Green gate + commit.**

---

## Task 2: Suricata EVE adapter (the live one)

**Files:** Create `adapters/suricata.py`; Test `hub_api/tests/test_sase_adapters_suricata.py` (with a fixture EVE JSON line).

**Interfaces:**
- Produces: `SuricataAdapter(AnalysisAdapter)` `source="suricata"`; `parse(raw: str)` handles newline-delimited EVE JSON, extracts from `alert` events: dest IP (`dest_ip`→ip), `tls.sni`/`http.hostname`→domain, `http.url`→url, `fileinfo.sha256`→hash; severity from `alert.severity` (1→critical,2→high,3→medium, else low).

- [ ] **Step 1: Write failing tests** — a fixture EVE alert line with dest_ip + http.hostname → 2 hits (ip + domain) with correct severity; a fileinfo event with sha256 → hash hit; a non-alert event (`event_type:"flow"`) → 0 hits; a malformed line → skipped, no raise; `ingest` writes them to the store.
- [ ] **Step 2: Run → FAIL. Step 3: Implement** the EVE parser. **Step 4: Run → PASS. Step 5: Green gate + commit.**

---

## Task 3: Zeek / Strelka / CAPE / Arkime adapters

**Files:** Create `adapters/{zeek,strelka,cape,arkime}.py`; Test `hub_api/tests/test_sase_adapters_others.py` (fixtures per tool).

**Interfaces:**
- Produces: `ZeekAdapter` (source="zeek", parses notice.log JSON/TSV → ip/domain), `StrelkaAdapter` (source="strelka", YARA match + file sha256 → hash), `CapeAdapter` (source="cape", verdict malscore + sample sha256 + contacted hosts → hash/ip/domain), `ArkimeAdapter` (source="arkime", tagged session → ip/domain). All subclass `AnalysisAdapter`.

- [ ] **Step 1: Write failing tests** — one fixture per tool → correct `AdapterHit`s (ioc_type/value/severity); malformed → skipped no-raise; `ingest` → store populated with the right `source`. (Fixtures are small representative captures — hand-author from each tool's documented output shape.)
- [ ] **Step 2: Run → FAIL. Step 3: Implement** the 4 parsers behind the shared base. **Step 4: Run → PASS. Step 5: Green gate + commit.**

---

## Task 4: Poller + scheduler/flag + contract registration

**Files:** Create `adapters/poller.py`; Modify `hub_api/modules/sase/__init__.py` (flag `tobogganing.sase.adapters`, `Entitlement("sase.adapters","community")`; register the poller job/handler); Test `hub_api/tests/test_sase_adapters_poller.py`.

**Interfaces:**
- Produces: `AdapterPoller(adapter, reader, store, interval)` — `async run_once()` (read new output via `reader`, `adapter.ingest`), `async loop()` (interval, error-backoff, mirror `feeds/manager.py`); a `register(...)` wiring pollers for enabled tools only (config-gated). `reader` = a callable returning new raw output (EVE log tail / API poll).

- [ ] **Step 1: Write failing tests** — `run_once` with a stub reader returning a fixture EVE line → store populated; a reader that raises → caught, `run_once` returns stats with 0 stored (no crash); poller only registers for tools with `enabled=True` in config; flag OFF → poller not registered.
- [ ] **Step 2: Run → FAIL. Step 3: Implement** poller + register flag/entitlement in the sase `module()` + wire the poller registration behind the flag + per-tool config. **Step 4: Run → PASS. Step 5: Green gate** (batch: new test + `test_sase_module.py` + `test_registry.py`) + boot **+ commit.**

---

## Task 5: Optional Helm sub-charts (off-by-default) — `k8s-manifest-builder`

**Files:** Modify `k8s/helm/tobogganing/Chart.yaml` (+`dependencies:` for the 5 tools, each `condition: <tool>.enabled`), `values.yaml` (`<tool>.enabled: false`), create `charts/` stubs; docs note the ROOT/cap exception for Suricata.

- [ ] **Step 1:** Dispatch `k8s-manifest-builder`: add the first `dependencies:` block (Suricata/Zeek/Arkime/Strelka/CAPE), each `condition: <tool>.enabled` default **false** in values.yaml; sub-chart stubs (or digest-pinned upstream refs) under `charts/`; securityContext per standards; Suricata's NET_ADMIN/NET_RAW as a documented `ROOT EXCEPTION (approved)`. Verify `helm lint` + `helm template --set suricata.enabled=true` renders it and default renders nothing for the tools.
- [ ] **Step 2: Commit.**

---

## Task 6: (folded into T2/T3 fixtures) — n/a. Contract note

The enforcement/read side is Slice A's contract (`sase-blocklist-enforcement-contract.md`) — D is write-only into that store, so no new data-plane contract doc is needed. Add a short `docs/architecture/sase-adapters.md` note describing the mirror→tool→adapter→blocklist flow + that everything is out-of-band. (Optional; fold into T4 commit if small.)

## Self-Review

- **Spec coverage:** base+config→T1; Suricata→T2; Zeek/Strelka/CAPE/Arkime→T3; poller+flag+contract→T4; Helm sub-charts→T5; out-of-band + fail-soft everywhere. All covered.
- **Placeholders:** none — each adapter is a real parser tested against a fixture.
- **Type consistency:** `AdapterHit`, `AdapterStats`, `AnalysisAdapter.{parse,ingest}`, `AdapterPoller` — consistent; write path matches Slice-A `to_stix_indicator`/`Verdict`/`BlocklistStore.put`.

## Execution

Sequential (2,3 need 1; 4 needs 1-3). Single feature branch `feature/sase-adapters` off release. **Disjoint from Slice B** → parallel (Wave 1). `penguin-python-dev` for T1-4; `k8s-manifest-builder` for T5. Verify commit-completeness + clean-bytecode + full-suite before merge.
