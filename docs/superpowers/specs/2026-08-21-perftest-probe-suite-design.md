# PerfTest Probe Suite — Design (WaddlePerf completion)

- **Date:** 2026-08-21
- **Branch:** `feature/squawk-merger` (spec home; implementation in `fix/`+`feature/` worktrees → release)
- **Status:** DRAFT — for owner review
- **Supersedes:** the ad-hoc "WaddlePerf restoration" increment; folds in `2026-07-08-waddleperf-module-merge-design.md`'s unfinished Phase 3/5 scope.

## Why (honest state)

The WaddlePerf→tobogganing merge kept the **control plane** (`perftest_cluster` devices/schedules/alerts, `perftest_client` agent-config API, `perftest_c2c`) but left the product non-functional end-to-end:
- `engines/testserver` (the Go probe/speedtest engine) was **never deployed** (no chart until `ed6d02b`), hard-depends on MariaDB (`log.Fatalf`), lacks `ping`/`traceroute` binaries + `NET_RAW` (so icmp/traceroute/http_trace fail at runtime).
- The **browser self-service speed test** (webClient) was never ported (admin LiveTest viewer only; basic SpeedTestPage landed `df5e07c`, single-mode).
- Probe coverage stops at http1.1/tcp/udp/icmp/traceroute; **no** TLS/DNS/NTP/WS/SSH/SMTP/IMAP/MQTT/STUN/SIP, no http2/http3.
This spec is the plan to make the advertised product true.

## Product goal (north star)

Probe **to/from hosts and services** — source = our servers OR end-user clients; target = our services OR external — across **ICMP, TCP, UDP, TLS, DNS, NTP, HTTP(1/2/3), WebSocket, SSH, SMTP, IMAP, MQTT, STUN, SIP**, with **protocol-aware latency checks**, **live single- AND multi-service response-time charts**, **network-interface inspection + configuration**, and **internet speed testing**. Lightweight, cross-platform, for admins + developers.

## Core data model — the Auto Check-in (admin-configured via API/webui)

| Field | Spec |
|---|---|
| source client | client XYZ — a **server** or an **end-user client** (the agent that runs the probes) |
| target service | **ours** (internal service) or **external** (URL/host:port) |
| test types | multi-select of probe types (http1 ping, http_trace, STUN, … any protocol below) |
| interval | **1–60 min**, plus **jitter randomizer up to ±10%** (avoid synchronized load / thundering herd) |
| samples per run | **1–5** |
| thresholds (optional) | acceptable **std-dev ranges: min / max / mean** |
| tier | **1** = run always · **2** = run only when a Tier-1 FAILS · **3** = run only when a Tier-2 FAILS |

Semantics: tier-N check-ins fire only on failure of their tier-(N−1) dependency (cascading escalation). Recommended default Tier-1 set: `{http_trace, traceroute, udp, http2}` — path-localizes faults (wifi vs ISP vs upstream vs whole-path) and covers the protocols users feel (web h1/h2 + realtime UDP). Tier-2 default: heavy `throughput`. Tier-3: deep diagnostics (multi-stream throughput / MTU-style analysis via the Rust server, below).
All schedules tenant-scoped; results feed thresholds → alerting (existing `alerts`).

## Probe protocol matrix

| Protocol | Today | Build | Where |
|---|---|---|---|
| ICMP, TCP, UDP, HTTP/1.1, traceroute (+`*_trace`) | ✅ in `ALLOWED_TEST_TYPES` | fix runtime (binaries + NET_RAW) | testserver (Go) + node-agent |
| HTTP/2, HTTP/3 | ❌ | new — **leverage patterns from `fever-ch/http-ping`** (Go, does h1/h2/h3) | testserver + node-agent |
| TLS (handshake latency/validity) | ❌ | new | both |
| DNS | ❌ (as probe) | thin probe **reusing `engines/netsvcs-dns` know-how** — don't duplicate resolver logic | both |
| NTP | ❌ (as probe) | thin probe reusing node-agent netsvcs-edge `ntp-proto` | node-agent; Go equivalent in testserver |
| WebSocket | ❌ | new (connect+echo RTT) | both |
| SSH, SMTP, IMAP, MQTT, STUN, SIP | ❌ | new protocol-aware handshake probes (banner/EHLO/CONNECT/binding-request/OPTIONS — measure to protocol-ack, no auth'd session needed except where configured) | testserver first; node-agent follow |
| throughput/speedtest | Go handlers exist, dropped at API | expose type + adapter seam | testserver now → Rust server later |

**Protocol-aware latency** = each probe reports phase timings where meaningful (DNS-resolve / connect / TLS / first-byte / protocol-ack), not one opaque RTT.

## Components

1. **hub_api `perftest_cluster`** — orchestration: check-in CRUD (model above), tier-cascade evaluation, jitter scheduler, std-dev threshold checks, results API. penguin-dal, tenant-scoped, quart-schema DTOs, feature-flagged.
2. **`engines/testserver` (Go — kept, maintenance per Go phase-out)** — server-side probe engine + speedtest target. Fixes: **GORM multi-DB (DB_TYPE-selected: postgres default / mysql / sqlite)** replacing the hard MariaDB Fatalf; install `iputils-ping`/`traceroute`/`tcptraceroute` + `NET_RAW` (documented cap-exception); add h2/h3 + new-protocol probe handlers (fever-ch patterns).
3. **Rust node-agent (`agents/node-agent`)** — the **k8s / VM server-client prober**: a `probes` capability consuming check-in schedules from the control plane (the existing `perftest_client` schedule-distribution API), running client-side probes, reporting results. Reuses its rustls/hickory/ntp-proto stacks. **This repo's client scope is servers only** (DaemonSet + bare-metal/VM).
3b. **End-user desktop prober = `tobogganing-perf` module in the `penguin` desktop repo** (per client standards: desktop clients consolidate into `penguin`, never per-product). Consumes the SAME schedule-distribution + results REST API as the node-agent's `probes` capability — this spec defines that interface contract; the module itself is built and tracked in the `penguin` repo (separate workstream).
4. **Portal** — (a) **Check-in admin UI** (CRUD the model above); (b) **multi-service live response-time charts** (N services on one chart; extend LiveTest/recharts); (c) **speed test, 3 authenticated modes: file-download / multi-stream / single-stream** (fast.com/speedtest.net-style; extends `df5e07c`); (d) **server-launched tests over WebSocket** — run a test FROM a chosen server node toward a target, streamed live (LA-user-vs-SFO-server / CDN-entry-node diagnosis).
5. **Rust throughput server (new, `engines/`)** — the iperf replacement, with **modern auth (JWT/OIDC — not iperf3's weak RSA/PSK)**. Parity target: **the SUPERSET of iperf2 + iperf3 features/flags; where the two conflict, the more flexible/feature-rich behavior wins.** Every knob below is an admin-settable field in the test/check-in definition (grouped in the UI: mode · transport · bounds · shaping · payload · socket/network · reporting).

   | Group | Features (iperf flag lineage) |
   |---|---|
   | Test modes | normal (client→server), **reverse** (`-R`, i3), **bidirectional simultaneous** (`-d` dualtest, i2), **bidirectional alternating** (`-r` tradeoff, i2), **parallel streams** (`-P`), single-stream |
   | Transports | **TCP, UDP, SCTP** (`--sctp`, i3.1), **multicast UDP** (bind group `-B` + TTL `-T`, i2) |
   | Run bounds | duration `-t` · bytes `-n` · block/packet count `-k` (i3) · **omit first N sec** `-O` (skip TCP slow-start, i3) |
   | Traffic shaping | target bandwidth `-b` for **both TCP and UDP**, per-stream (i3 semantics) · **burst mode** `-b n/cnt` (i3) · **pps units** `-b 1000pps` (i2.0.8) · token-bucket TCP rate limiting (i2.0.8) |
   | Payload | buffer/datagram length `-l` · **representative stream from file** `-F` · from stdin/inline blob `-I` (i2) |
   | Socket / network | window size `-w` · MSS set `-M` **+ observed MSS/MTU reporting** `-m` (i2 — feeds the MTU-diagnosis story) · TCP no-delay `-N` · DSCP/TOS `-S` · IPv6 flow label `-L` · congestion-control algorithm `-C` · zerocopy `-Z` · bind interface/address `-B` (incl. `host:port` form, i2.0.7) · client port `--cport` · server port `-p` · IPv4/IPv6 `-4`/`-6` |
   | Reporting | interval reports `-i` down to **5 ms** (i2.0.7) · formats b/k/m/g/adaptive `-f` · **JSON** `-J` · structured results exchange (i3) · UDP **jitter** (RFC 1889), datagram **loss + out-of-order**, **PPS** display · **end/end latency mean/min/max/std-dev** at µs resolution (i2.0.7/8 — pairs directly with the check-in std-dev thresholds) · TCP retries + CWND · read histograms · 64-bit UDP counters (i3.1) · logfile/verbose/title |
   | Server model | **multi-client concurrent** (i2 semantics — explicitly rejecting iperf3's one-client-at-a-time) · dynamic client-driven server parameter exchange (i3) · CPU affinity `-A` + realtime scheduling `-z` (i2) as pod/config options |
   | Adaptive / forward-looking | **adaptive window sizing** (`-W`, i2 under-development — client converges on the optimal TCP window via binary-exponential search toward the bandwidth-delay product, and *reports the suggested window* for the current path) · auto-BDP hinting (compute `bottleneck bw × RTT` from measured values and surface it next to the configured window) · iperf's other under-development/planned features get first-class implementations here rather than being skipped — treat "experimental in iperf" as "in-scope for us" |

   Conflict resolutions (flexibility wins): server concurrency → iperf2 multi-client; `-b` → iperf3 TCP+UDP semantics **plus** iperf2 pps units + burst; bidirectional → keep BOTH iperf2 modes **and** iperf3 reverse. Dropped as N/A in our context: iperf1.7 compatibility mode (`-C`, i2), Win32 service install, CSV `-y`/report-exclusion `-x` (superseded by JSON + the results API/DB). Daemon/pidfile are deploy-level (K8s/systemd), not app flags.
   Security-sensitive + high-perf ⇒ Rust per standards. Parity verified against a side-by-side iperf2+iperf3 test matrix before it replaces the testserver `/speedtest` heavy path.
6. **NIC inspection + configuration** — read: interfaces/addresses/MTU/link state via node-agent (rtnetlink, exists in connectivity crate) surfaced through the control plane + portal; write/config = gated admin action (scope + audit).

## Phases

| Phase | Deliverable | Size |
|---|---|---|
| **W1 — Engine runs** | testserver GORM/postgres + probe binaries/NET_RAW + chart (done `ed6d02b`) deploys green on microk8s; existing probe types verified live | S–M |
| **W2 — Check-in model** | schema/migration + CRUD API + jitter scheduler + tier cascade + std-dev thresholds; admin UI page; salvage stopped wp-backend work | M |
| **W3 — Protocol expansion** | h2/h3 (fever-ch), TLS, DNS, NTP, WS probes in testserver + node-agent `probes` capability; protocol-aware phase timings | M–L |
| **W4 — Protocol long tail** | SSH, SMTP, IMAP, MQTT, STUN, SIP probes | M |
| **W5 — Experience surfaces** | multi-service live charts; 3-mode speed test; WebSocket server-launched tests | M |
| **W6 — Heavy tier + NIC** | Rust multi-client auth'd throughput server; NIC inspect/config | L |

Each phase: own `fix/`/`feature/` worktree(s) → tests green (90% floor) → merge to `feature/squawk-merger`-successor or release per branch state at the time. W1+W2 restore the *advertised* product; W3+ extend to the north star. README/marketing stays aligned to shipped phases.

## Out of scope

Squawk/netsvcs work (done, PR #116). The `tobogganing-perf` **penguin-desktop module's implementation** — its API interface is defined here, but the module is built/tracked in the `penguin` repo as its own workstream.
