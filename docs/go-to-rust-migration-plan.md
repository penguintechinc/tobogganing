# Go → Rust Migration Plan — tobogganing

**Status:** APPROVED (direction + all 5 decisions resolved 2026-09-25) — execution gated per §5
**Date:** 2026-09-25
**Scope:** the 3 remaining Go modules in `tobogganing`
**Driver:** Go Phase-Out standard (`critical-rules.md` Data Plane; `general.md` Language Selection) — in-line-of-traffic → Rust; agents/CLI → Rust. hub-router is the flagged migration-debt priority.

---

## 1. Executive summary

| Module | LOC | Disposition | Risk | Effort |
|---|---|---|---|---|
| `shared/go_libs` | ~2.6K src | **DELETE** — 0 consumers (dead code) | none | ~0.5 day |
| `engines/testserver` | ~3.5K src / 10.6K test | **REWRITE (pilot)** — not in live-traffic path, strong test spec | low | ~1.5–2 wks |
| `services/hub-router` | ~5.8K src / 1.1K test | **REWRITE (phased)** — in-line data plane, security-sensitive | high | ~8–10 wks |

**Recommended order:** `go_libs` delete (anytime) → `testserver` pilot (establishes Rust service patterns in-repo, low risk) → `hub-router` (phased, with a WireGuard spike first). Total ≈ **10–12 weeks**, value landing incrementally.

**Foundation already exists:** `agents/node-agent` is a working Rust workspace (tokio, tonic/gRPC, rustls, tracing, clap) — the conventions, CI, and Dockerfile patterns to mirror are in-repo, so no greenfield tooling risk.

**Bonus payoffs:** removing Go also (a) resolves the deferred `x/crypto` CVE that required Go 1.26 (> the 1.25.x ceiling), (b) retires the Go CI toolchain (golangci-lint / gosec-go / go-test), and (c) is a chance to fix several real bugs found during analysis (below).

**Hard gate before committing the hub-router timeline:** a 1-week **WireGuard/netlink spike** — the live WG routing is a shell-exec anti-pattern that must be *redesigned*, not ported, and Rust's kernel-WG ecosystem is the biggest unknown.

---

## 2. Module 1 — `shared/go_libs`: DELETE (not migrate)

Analysis found **zero consumers** — hub-router and testserver each implement their own utilities; `go_libs` (crypto, grpc, http, validation, scripts packages) is dead code.

- **Action:** delete `shared/go_libs/` and its `go.mod`; remove any CI reference. No Rust equivalent needed now.
- If a future Rust gRPC service needs shared middleware (auth/audit/correlation/rate-limit interceptors), extract a small `penguin-grpc-utils` crate then — not before (YAGNI). Rust logging = `tracing`+OTLP; proto codegen = `build.rs`+tonic-prost (already how node-agent does it).
- Note: PR #152 fixed `go_libs` compile errors to un-block govulncheck — that hardened dead code; deletion supersedes it.

---

## 3. Module 2 — `engines/testserver`: REWRITE (pilot)

WaddlePerf diagnostic probe target. **Not in the live customer-traffic path** (clients call it on demand) → low cutover risk. Single HTTP service (`gorilla/mux`) on :8080, no gRPC, GORM (Postgres/MySQL/SQLite).

### 3.1 Why it's the pilot
- Lowest risk (no live traffic, no privileged networking).
- **10.6K LOC of tests / 13 files** = a strong behavioral parity spec, including deliberately "permissive" semantics that MUST be preserved (SSH post-banner auth-failure = success; UDP no-response = success).
- Establishes the in-repo Rust *service* patterns (vs node-agent's *agent* patterns): axum HTTP, SeaORM, request/response DTOs, OTel, Dockerfile, CI job.

### 3.2 Target stack
`tokio` + `axum` (HTTP) · `rustls` (TLS) · `SeaORM` (DB, clean GORM swap: Postgres/MySQL/SQLite) · `tracing`+OTLP · `hyper`/`reqwest` (HTTP/1.1+2 probes, ALPN) · tokio `UdpSocket` + `hickory-resolver` (UDP/DNS) · `tokio::process::Command`+`regex` (ICMP/traceroute/*_trace — **the Go code shells out to `ping`/`traceroute` binaries, not raw sockets**, so this is a near-mechanical port) · `russh` (SSH banner/kex probe — the one non-trivial protocol; confirm it exposes server-version pre-auth).

### 3.3 Migration approach — parity-test-driven
1. Scaffold the Rust service mirroring node-agent (workspace, CI job, multi-stage Dockerfile with root-context per the fixed build convention).
2. **Port the Go test suite first** as the executable spec (the JSON request/response field names for every protocol are the contract — documented in the analysis).
3. Port protocols easy→hard: speedtest → TCP/HTTP/TLS → UDP/DNS → ICMP/traceroute/traces (shell-out) → SSH.
4. **Fix the flagged pre-existing gaps during the rewrite** (don't port them): opaque-hash "auth" → real JWT signature/claims verification (`security.md`); **add the gRPC surface with two-layer versioning** — proto package `testserver.v1` + an `api_version` field per request message (`backend.md`), alongside the REST surface (decision #1); wire the dead `MAX_CONCURRENT_TESTS` cap.
5. Cutover: build the Rust image, deploy to alpha, run the ported suite + live probes, then swap the Deployment image (it's a stateless target — a normal rolling replace, no traffic-continuity concern).

---

## 4. Module 3 — `services/hub-router`: REWRITE (phased, highest risk)

In-line data-plane proxy + WireGuard control + OAuth2/SAML SSO + firewall. Runs privileged (root + NET_ADMIN). This is the hard one.

### 4.1 Reality check from analysis (changes the risk model)
- **The `wgctrl`+netlink packages (`./wireguard`, `./config`) are DEAD CODE** (zero imports). The *live* WireGuard path is **shell-exec**: `wg-quick` in `entrypoint.sh` owns `wg0`; `proxy/wireguard_router.go` shells `wg show`/`iptables` **per connection**.
- That per-connection shell-exec is a **perf/DoS liability and leaks an iptables mangle rule per connection** (never cleaned up) — a real bug. The Rust version must **redesign** this (SO_MARK-based connection marking + a proper WG/netlink control layer), not port it.
- **No XDP/eBPF anywhere** (confirmed) — any fast path in Rust is *new* functionality, out of scope for a parity migration.
- **Data-plane hot path has ZERO tests** (only auth is tested — 1.1K LOC). The Rust port needs **net-new characterization tests**: capture the Go behavior (proxy byte-copy, firewall match, packet marking) as golden tests *first*, then port against them.

### 4.2 Go → Rust crate mapping

| Go dependency | Rust crate | Maturity | Note / tradeoff |
|---|---|---|---|
| gin (HTTP) | `axum` + `tokio` | ✅ prod | matches node-agent |
| `golang.org/x/oauth2` | `oauth2` | ✅ prod | timing-safe |
| `crewjam/saml` (SAML SP) | Rust `samael`/`opensaml`/`saml-rs`; **Python `pysaml2` sidecar fallback (never Go)** | ⚠️ **pre-1.0, unaudited** | **highest risk — Rust-first, Python fallback per decision #2 (§4.4)** |
| kernel WireGuard cfg (live: shell `wg`) | **`defguard_wireguard_rs` 0.12** + `rtnetlink` 0.23 | ✅ prod (Apache-2.0, cargo-deny clean) | redesign, not port; `spawn_blocking` for syscalls. **Spike (2026-09-25) rejected `wireguard-control` 2.0** — LGPL-2.1-or-later + unmaintained `paste` (RUSTSEC-2024-0436); see `docs/spikes/2026-09-25-rust-wireguard-netlink-spike.md` |
| iptables (live: shell per-conn) | `nftables` (atomic batches) or `rtnetlink` | ⚠️ pre-1.0 / needs host `nft` | replace per-connection insert with SO_MARK |
| prometheus client | `metrics` + `opentelemetry-otlp` | ✅ prod | aligns with the hub_api OTel work |
| zap/logrus + syslog | `tracing` + OTLP | ✅ prod | repo standard |
| grpc | `tonic` | ✅ prod | only if we add a gRPC surface (none today) |

### 4.3 Subsystem sequence (easy → hard, from the difficulty ranking)
1. helpers · 2. middleware · 3. syslog · 4. **machine-JWT** (452 LOC of tests = near-complete spec, do early) · 5. ports/config-client · 6. mirror · 7. RSA JWT provider (no tests — careful re-derivation) · 8. firewall (no tests, hot path — fix the O(n·log n)-per-request sort while porting) · 9. tcp/udp proxy (**dedup the 3× duplicated loop**, fix unbounded buffering → streaming) · 10. HTTP reverse-proxy (no 1:1 axum equivalent) · 11. **SAML2/XML-DSig** (highest security-regression risk) · 12. **WireGuard/netlink control** (the redesign; spike this first).

### 4.4 The three top risks + mitigations
1. **SAML 2.0 in Rust (pre-1.0, unaudited; XML-DSig canonicalization/XSW interop gaps vs Go).** → **Target a Rust SAML SP.** If the Rust XML-DSig ecosystem proves inadequate, fall back to a **Python** SAML sidecar (mature `pysaml2`/`python3-saml`) that validates the assertion → mints a short-lived JWT; Rust verifies only JWTs. **Never a Go sidecar** (decision #2; auth is security-sensitive = Rust/Python only per `general.md`). Validate assertion parity (XSW/replay/expiry, matching the current hardened pipeline) against production IdPs before retiring the sidecar.
2. **Async-runtime starvation** — kernel syscalls (`rtnetlink`/`nftables`/WG) inside axum handlers starve tokio → dropped packets/keepalives. → **Mandatory `tokio::task::spawn_blocking`** for all kernel I/O; a dedicated control-plane worker pool separate from the request runtime.
3. **WireGuard state desync on crash mid-update** (traffic leak/black-hole). → `nftables` **atomic batches**; dry-run pre-validate; **adopt existing kernel state on startup** (query `wg0`/peers via `rtnetlink`, resume without teardown).

### 4.5 Cutover — incremental, no dropped tunnels
Blue-green is unsafe (stateful WG tunnels). Three phases:
1. **Shadow (wks 1–2):** Rust daemon runs read-only, mirrors kernel state, exports telemetry. Go still owns all writes.
2. **API-proxy (wks 3–4):** Go reverse-proxies non-critical routes (health, config reads) to Rust; validate parity via golden tests.
3. **State takeover (wk 5+):** Go stops **without tearing down `wg0`/peers/rules**; Rust adopts the existing `ifindex` + peers via `rtnetlink` and resumes. Active flows persist (no forced rekey). **Post-migration the Rust process owns `wg0`** (creation + lifecycle), replacing `entrypoint.sh`'s `wg-quick` (decision #3) — during the takeover it adopts the device the old entrypoint created, and on subsequent restarts it creates/adopts `wg0` itself.

**Verification:** declarative state-diff (WG peers + routes + nft rules from Go runtime vs Rust shadow → byte-for-byte match before any write handoff); WG keepalive/rekey continuity monitored across takeover; replay the (net-new characterization + existing auth) test suite against the Rust impl before each phase.

### 4.6 Fix-while-porting (do NOT port these bugs)
- Per-connection iptables mangle-rule **leak** → SO_MARK once per flow.
- 3× duplicated proxy loop (main pkg + dynamic_ports) → single implementation.
- Unbounded HTTP response buffering → streaming.
- O(n·log n) firewall sort **per request** → precomputed/indexed match.
- **root + CAP_CHOWN + allowPrivilegeEscalation** driven by `entrypoint.sh` (chown `wg0.key`, non-namespaced `net.core.*` sysctls) → **init-container split** so the main process drops to non-root + NET_ADMIN only (also closes the R5 audit finding).

---

## 5. Sequencing, milestones, effort

| Phase | Work | Gate to exit | Est. |
|---|---|---|---|
| 0 | Delete `go_libs`; scaffold Rust service conventions (from node-agent) | dead code gone; scaffold builds in CI | 0.5–1 wk |
| 1 | **testserver** rewrite (parity-test-driven) + fix auth/api_version gaps | ported test suite green; alpha probes pass; image swapped | 1.5–2 wks |
| 2a | **hub-router WireGuard/netlink SPIKE** (SO_MARK routing + WG/rtnetlink prototype) — ✅ **DONE 2026-09-25: GO** (defguard_wireguard_rs; spawn_blocking + `nft -f -` validated live; live-`wg0`-adoption zero-loss test deferred to first 1-2 days of 2c on a privileged node) | ✅ redesign proven; 2c estimate holds | done |
| 2b | hub-router control-plane subsystems (auth/machine-JWT/ports/firewall/mirror) + SAML sidecar | golden/parity tests green in shadow mode | 3–4 wks |
| 2c | hub-router data-plane (proxy + WG control) + cutover phases 1–3 | state-diff match; keepalive continuity; takeover w/o dropped flows | 3–4 wks |
| 3 | retire Go CI toolchain; retire the (Python, if used) SAML sidecar once Rust SAML proven | no Go left; SAML parity validated on prod IdPs | trailing |

**Total ≈ 10–12 weeks.** Phases 0–1 deliver standalone value (Go partly gone, patterns proven) before the high-risk hub-router work.

## 6. Decisions — RESOLVED (2026-09-25)
1. **testserver `/api/v1`:** ✅ **Add the gRPC + `api_version` two-layer versioning** (`backend.md`) during the rewrite (proto package `testserver.v1` + `api_version` field per request). Not REST-only.
2. **SAML:** ✅ **No Go — anywhere.** Real-time/data-plane is strictly Rust. SAML is security-sensitive, so per `general.md` it is **Rust or Python, never Go**: target a **Rust** SAML SP; if the pre-1.0 Rust XML-DSig ecosystem proves inadequate during the spike/build, fall back to a **Python** SAML sidecar (mature `pysaml2`/`python3-saml`) — **not** a Go sidecar. Retire the sidecar once Rust SAML is validated against production IdPs.
3. **WG device ownership:** ✅ **The Rust process owns `wg0`** (creation + lifecycle), replacing `entrypoint.sh`'s `wg-quick`. This folds device setup into the Rust control plane and is what enables the non-root/init-container split (§4.6).
4. **Timeline:** ✅ **Gated on the Phase-2a WireGuard/netlink spike** — the hub-router estimate is not committed until the spike proves the SO_MARK redesign + crate maturity.
5. **Fix-while-porting scope:** ✅ **Confirmed in-scope** (§4.6) — the iptables leak, 3× duplicated proxy loop, unbounded buffering, per-request firewall sort, and root/CAP_CHOWN init-container split are all fixed during the rewrite.

---

*Inputs: per-module architecture analyses + 2026 Rust-ecosystem research (crate maturity grounded to current crates.io). No production code written — this document is the deliverable for review.*
