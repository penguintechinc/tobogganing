# Phase 2a Spike — Rust WireGuard/Netlink Redesign for hub-router

**Status:** COMPLETE — gates the hub-router migration timeline (`docs/go-to-rust-migration-plan.md` §5, phase 2a)
**Date:** 2026-09-25
**Prototype:** `spike/wg-netlink-poc/` (this worktree, branch `spike/rust-wireguard-netlink`) — THROWAWAY, not production code, not part of any workspace, not to be merged as-is
**Sandbox constraints:** no root, no `CAP_NET_ADMIN`/`CAP_NET_RAW` (bounding set present but not in the effective/current set for this unprivileged user), no password-less `sudo`. `wireguard` kernel module IS loaded on the host, but `ip link add ... type wireguard` fails with `EPERM` — confirms this environment cannot exercise the privileged happy path. That gap is called out explicitly per goal below, per the task's instruction not to claim untested behavior works.

## Verdict: GO, with a crate-selection correction

The Rust kernel-WireGuard control + SO_MARK + atomic-nftables redesign is **viable** — every mechanism the migration plan needs compiles, has the right async-safety shape, and (where testable without privilege) behaves correctly. **One correction to the migration plan's crate table:** `wireguard-control` 2.0.0 must be **rejected**, not adopted — `cargo deny check` caught a real license conflict plus an unmaintained transitive dependency (details in Goal 1). **`defguard_wireguard_rs` 0.12.1 is the recommended replacement** — same capability, clean license, current dependency line, no RustSec finding.

## Goal-by-goal results

| Goal | Result | Detail |
|---|---|---|
| 1. Kernel WG control (create/list/adopt) | **Works — compiles + behavior verified by source inspection; runtime happy-path needs privileged env** | See below |
| 2. SO_MARK connection marking | **Compiles; needs privileged env to verify runtime success** | `so_mark.rs` |
| 3. Async safety (`spawn_blocking`) | **Works — validated live in this sandbox** | `blocking.rs` |
| 4. nftables atomic batch | **Works — ruleset generation validated live; kernel apply needs privileged env** | `nft_batch.rs` |

### Goal 1 — Kernel WireGuard control

**Finding: reject `wireguard-control` 2.0.0, adopt `defguard_wireguard_rs` 0.12.1.**

`cargo deny check` against this crate's `deny.toml` (copied from `agents/node-agent`, the in-repo Rust license/advisory baseline) fails with two real findings, both attributable solely to `wireguard-control`:

```
error[rejected]: failed to satisfy license requirements
  wireguard-control-2.0.0/Cargo.toml:38  license = "LGPL-2.1-or-later"
  rejected: license is not explicitly allowed

error[unmaintained]: paste - no longer maintained (RUSTSEC-2024-0436)
  paste v1.0.15 <- netlink-packet-utils v0.5.2 <- netlink-packet-core v0.7.0
  <- netlink-packet-wireguard v0.2.3 <- wireguard-control v2.0.0
```

`wireguard-control` is itself LGPL-2.1-or-later (not a transitive dependency — its own `Cargo.toml`), and its dependency tree is pinned to an old `netlink-packet-*` line (core 0.7.0, route 0.21.0, wireguard 0.2.3) that pulls the archived/unmaintained `paste` crate with no safe upgrade. Statically linking LGPL-2.1 code into hub-router's proprietary, license-gated binary is a real distribution-model conflict, not a style nit — needs legal sign-off to use at all, independent of the advisory.

`defguard_wireguard_rs` 0.12.1 (verified standalone, `cargo deny check` → `advisories ok, bans ok, licenses ok*, sources ok`, `*` only the throwaway check-crate's own missing `license` field, fixed trivially) is Apache-2.0, depends on the *current* `netlink-packet-*` line (core 0.9.0, generic 0.5.0, route 0.33.0, utils 0.6.0, wireguard 0.5.0 — same versions `rtnetlink` 0.23 already pulls, so no version fragmentation), and is actively maintained (multi-platform: Linux kernel + userspace boringtun fallback, FreeBSD, Windows).

**API shape confirmed by source inspection + compiled prototype (`wg_control_defguard.rs`):**
- `WGApi::<Kernel>::new(ifname)` — construction only, no privileged I/O (unit-tested, passes unprivileged)
- `create_interface()` — idempotent: its Linux netlink backend explicitly swallows `EEXIST` (`netlink.rs:242` etc.), confirmed by reading source — **this is the adopt-without-teardown path** the cutover plan (§4.5 phase 3) needs
- `configure_interface(&InterfaceConfiguration)` — pushes device config (private key, port, peers, fwmark)
- `configure_peer(&Peer)` — "Adds a peer or updates peer configuration" (crate's own doc comment) — non-destructive merge, matches the requirement to add/update one peer without disturbing others
- `read_interface_data() -> Host { peers: HashMap<Key, Peer>, .. }` — the adoption read-path, equivalent to `wg show`

Also prototyped and confirmed compiling against `wireguard-control` 2.0.0's real API (`wg_control.rs`, kept deliberately alongside `defguard_wireguard_rs` for the side-by-side `cargo deny` comparison above, not as a second candidate) — reading its `backends/kernel.rs` source directly confirmed `DeviceUpdate::apply()` also creates-and-adopts idempotently (`NLM_F_CREATE|NLM_F_EXCL` with `AlreadyExists` swallowed) and is likewise pure-Rust netlink (its crates.io description "bindings to the WireGuard embeddable C library" is stale/misleading — no C linkage found in its dependency tree). Same conclusion on the *mechanism*; different conclusion on *this specific crate* due to license + advisory.

**Additionally prototyped:** `rtnetlink` 0.23 directly (`rtnl_probe.rs`) for an unprivileged existence check (`RTM_GETLINK` dump) before touching the privileged WG-genl path — **this ran live and succeeded** in the sandbox (link dumps need no capability), giving a cheap pre-check independent of the WG control library choice.

**NEEDS PRIVILEGED ENV:** `Device::list`/`Device::get` (wireguard-control) and `WGApi::read_interface_data`/`create_interface` (defguard) all require `CAP_NET_ADMIN` even for reads — confirmed failing closed (clean `Err`, no panic) in this sandbox via `ip link add wg-test type wireguard` → `EPERM`. Real adoption behavior (does a second process's `create_interface()`/`apply()` against a `wg-quick`-owned `wg0` actually leave existing peers/keepalives untouched) is a source-level guarantee here, not yet an observed one — **must be validated on a real cluster node with `CAP_NET_ADMIN` and an active WG tunnel before committing to the cutover plan (§4.5)**.

### Goal 2 — SO_MARK connection marking

`so_mark.rs`: `libc::setsockopt(fd, SOL_SOCKET, SO_MARK, &mark, ...)` on any `AsRawFd` socket (works uniformly for `std`/`tokio` TCP/UDP sockets). One syscall per connection, replacing the Go anti-pattern's per-connection `iptables -t mangle -A OUTPUT ... MARK` shell-out + permanent rule leak.

**Validated:** syscall plumbing is correct (fd, `SOL_SOCKET`/`SO_MARK`=36, `c_int`-sized option value per `man 7 socket`) — confirmed by a real `setsockopt` call against a bound loopback listener failing with exactly `EPERM` (the expected no-`CAP_NET_ADMIN` outcome), not a different/malformed-argument error.
**NEEDS PRIVILEGED ENV:** confirming the mark is actually observed on egress packets (`nft`/`tcpdump` visibility) needs `CAP_NET_ADMIN` on a real node.

### Goal 3 — Async safety (`spawn_blocking`)

**Fully validated live**, no privilege needed. `blocking.rs` wraps the (confirmed-blocking, raw-`libc`-socket) WG control calls in `tokio::task::spawn_blocking`; a `multi_thread`/2-worker test confirms a concurrently-scheduled sleep task completes promptly rather than being starved. `rtnetlink`, by contrast, is natively async (its own tokio netlink socket) and needs no `spawn_blocking` — the two libraries have genuinely different concurrency shapes, and the control-plane code must know which is which per call site. This is a **mandatory pattern**, not optional: any direct `.await`-adjacent call into `wireguard-control`/`defguard_wireguard_rs`/synchronous `nft` invocation on a tokio worker thread will starve request handling under peer-churn load (migration-plan risk #2).

### Goal 4 — nftables atomic batch

`nft_batch.rs`: generates a ruleset (`table inet hub_router { chain mark_authenticated { ... meta mark <N> accept } }`) and applies it via `nft -f -` (`tokio::process::Command`, ruleset piped over stdin) — **not** the `rustables` crate (GPL-3.0-or-later — same license-policy conflict class as `wireguard-control`, ruled out without an explicit licensing exception) or `nftnl` (MIT/Apache-2.0, but requires linking the C `libnftnl` at build+runtime — reintroduces exactly the native-toolchain dependency this migration is trying to remove). `nft -f` gives nftables' own atomic-transaction guarantee (crash-safety per migration-plan risk #3) without either tradeoff, and — unlike the Go code's per-*connection* `iptables` shell-out — is only invoked once at startup/config-reload, so exec overhead is a non-issue.

**Validated live:** ruleset string generation (unit test, no privilege) and — because `nft` happens to be installed in this sandbox — the `apply_ruleset_atomic` call actually executed `nft -f -` and failed with a real permission error from the kernel (not "binary not found"), confirming the process-spawn/stdin-pipe/exit-status-check plumbing end-to-end.
**NEEDS PRIVILEGED ENV:** confirming the rule is actually installed into the kernel nf_tables subsystem and matches real traffic needs `CAP_NET_ADMIN` on a real node.

## What's validated vs needs-privileged-env (summary)

| Claim | Status |
|---|---|
| `defguard_wireguard_rs`/`wireguard-control` API shapes compile against real 2026 crate versions | ✅ Validated (compiles + 9 unit tests pass) |
| `create_interface`/`apply()` is idempotent (source-verified `EEXIST` swallow) | ✅ Validated by source read, not yet by live adoption |
| Unprivileged `rtnetlink` link dump works | ✅ Validated live |
| `spawn_blocking` prevents runtime starvation for blocking WG calls | ✅ Validated live |
| nft ruleset generation is correct + atomic-apply plumbing works | ✅ Validated live (up to the permission boundary) |
| WG-genl read/write, SO_MARK, nft kernel-apply succeed with `CAP_NET_ADMIN` | ⚠️ **NEEDS PRIVILEGED ENV** — a real cluster node with root/`CAP_NET_ADMIN` and (for full confidence) an active `wg-quick`-owned tunnel to adopt |
| Adoption leaves existing peers/keepalives undisturbed under real traffic | ⚠️ **NEEDS PRIVILEGED ENV + a live WG tunnel** — highest-value remaining validation, directly gates cutover phase 3 |

## Biggest remaining unknown

Whether **adopting a live, actively-handshaking `wg0`** (peers with open UDP sessions, mid-keepalive) via `create_interface()`/`apply()` truly causes zero packet loss / no forced rekey — the source code guarantees idempotent *link* creation and non-destructive peer *config* merge, but says nothing about in-kernel session/handshake state, which is a WireGuard kernel-module property, not a userspace-library one. This can only be answered on a real node with a real tunnel (migration plan §4.5's own verification step: state-diff match + keepalive-continuity monitoring across takeover).

## Crate recommendation

| Layer | Recommendation | Maturity/risk |
|---|---|---|
| Kernel WG device/peer control | **`defguard_wireguard_rs` 0.12.1** (not `wireguard-control` — LGPL + unmaintained-advisory, reject) | Apache-2.0, actively maintained, current netlink-packet-* line, multi-platform. Pre-1.0 API stability caveat still applies (0.x). |
| Link existence pre-check | `rtnetlink` 0.23 | Prod-grade, async-native, unprivileged reads |
| Connection marking | `libc::setsockopt` (`SO_MARK`) directly — no crate needed | Stable syscall, `libc` is prod-grade |
| Firewall/routing batch | `nft -f -` via `tokio::process::Command` | nftables itself is the prod-grade, kernel-blessed atomicity guarantee; avoids GPL-3 (`rustables`) and native-lib linkage (`nftnl`) |
| Blocking-call isolation | `tokio::task::spawn_blocking` | Standard tokio pattern, mandatory per call site touching WG/nft/netlink |

**Action item for the migration plan:** update §4.2's crate-mapping table — replace `wireguard-control 2.0` with `defguard_wireguard_rs 0.12`.

## Effort read for the hub-router WG subsystem

The migration plan's existing estimate (subsystem #12, folded into phase 2c, 3–4 wks total for phase 2c including the proxy) **holds**, with one adjustment: swapping the crate recommendation is a naming change in the plan, not new work — the API shapes are close enough (both are create/configure/read-oriented) that no design rework is needed. No new risk surfaced that would push the estimate up; the adoption-under-live-traffic unknown above was already the plan's acknowledged top risk (§4.4 risk #3) and remains appropriately budgeted for in phase 2c's cutover work (state-diff verification, keepalive monitoring). **Recommend spending the first 1–2 days of phase 2c specifically on a privileged-node adoption test** (real `wg-quick`-created `wg0` with a live peer, adopt via `defguard_wireguard_rs`, confirm zero packet loss) before writing the rest of the control-plane code — cheap, and it's the one thing this spike could not itself verify.

## Prototype crate

`spike/wg-netlink-poc/` — standalone (`publish = false`, not a workspace member), all deps exact-pinned. Verified clean:

```
cargo build           # compiles, both wireguard-control and defguard_wireguard_rs paths
cargo clippy --all-targets -- -D warnings   # clean
cargo fmt --check                            # clean
cargo test             # 9 passed; 0 failed
cargo deny check        # advisories FAILED, bans ok, licenses FAILED, sources ok
                         # — both failures attributable solely to wireguard-control
                         #   (kept deliberately, for the documented comparison above)
```

Module map:

| Module | Goal | Notes |
|---|---|---|
| `wg_control.rs` | 1 | `wireguard-control` 2.0 prototype — kept for comparison, **not the recommendation** |
| `wg_control_defguard.rs` | 1 | `defguard_wireguard_rs` 0.12 prototype — **the recommendation** |
| `rtnl_probe.rs` | 1, 3 | `rtnetlink` 0.23 unprivileged link dump; async-vs-blocking contrast |
| `so_mark.rs` | 2 | `SO_MARK` via raw `libc::setsockopt` |
| `nft_batch.rs` | 4 | Ruleset generation + atomic `nft -f -` apply |
| `blocking.rs` | 3 | `spawn_blocking` wrappers + starvation test |
| `main.rs` | — | Demo binary wiring all of the above with clear privileged-env warnings |
