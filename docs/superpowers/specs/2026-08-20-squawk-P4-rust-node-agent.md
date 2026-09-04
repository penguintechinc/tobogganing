# Squawk P4 — Unified Rust Node-Agent — Design

- **Date:** 2026-08-20
- **Branch:** `feature/squawk-merger` (off `release/v1.2.X`)
- **Status:** Approved — decisions locked via brainstorming rounds (Rust; crate map; connectivity + netsvcs-edge feature-gated; gRPC-intra / REST-edge; two packagings from one musl binary; universal short-lived signed JWTs)
- **Part of:** squawk → netsvcs merge umbrella (`2026-08-07-squawk-netsvcs-merge-umbrella.md`). Follows P0–P3.

## Goal

Merge the tobogganing edge agent (`clients/native/`, Go — WireGuard/Ziti connectivity + machine-JWT enrollment/heartbeat) and the squawk DNS client (reference-only, DNS-forwarding) into **one Rust binary** at `agents/node-agent/`. The binary delivers both **SASE connectivity** and **netsvcs-edge** (local DNS/DHCP/NTP) and ships two ways: a naked static musl binary (bare-metal/systemd) and a K8s DaemonSet container — from a single build.

## Locked Decisions

| Decision | Value |
|---|---|
| Language | Rust (security-sensitive edge agent; Go phase-out). `rustc` 1.98, edition 2021 |
| Build shape | One cargo **workspace** — `cargo build` builds everything ("one big build") |
| Capability gating | Cargo features `connectivity` + `netsvcs-edge`, both default-on; either can be compiled out |
| Transports | **BOTH** — gRPC (`tonic`) for intra-cluster (DaemonSet ↔ hub_api: high volume, trusted net, binary HTTP/2 hard to edge-secure); REST (`reqwest`) for edge/bare-metal (low volume, edge-securable). Runtime-selected by deployment mode |
| Auth | Universal short-lived **signed** JWTs on every inter-service call (JWS; JWE where payload sensitive). Machine-JWT enrollment against the P2 netsvcs control plane |
| Packaging | Two from ONE binary: (a) static musl + systemd unit (bare-metal); (b) multi-stage digest-pinned Debian container + Helm DaemonSet chart (K8s), documented `NET_ADMIN`/`:53` root-exception |
| Upstream DNS | netsvcs-edge forwards to the **P3 DoH resolvers** (`engines/netsvcs-dns/`) |

## Merge Sources

| Source | Language | What carries over |
|---|---|---|
| `clients/native/` | Go | WireGuard tunnel, Ziti hook, machine-JWT enrollment/heartbeat loop — **the connectivity reference** |
| squawk-client-go | Go | DNS `:53` forward semantics only — **reference-only**; DHCP/NTP/transport are unwired scaffold, ZERO WireGuard/enrollment. Node↔control-plane loop is designed **fresh** here |

## Crate Map (workspace members)

| Crate | Responsibility | Key deps |
|---|---|---|
| `core` | config (`figment`+`clap`), error (`thiserror`), structured logging (`tracing`), machine-JWT sign/verify (`jsonwebtoken`), the `ControlPlaneClient` trait, shared domain types (`@dataclass`-equivalent structs) | figment, clap, thiserror, tracing, jsonwebtoken, serde |
| `transport` | gRPC (`tonic`) + REST (`reqwest`) implementations of `ControlPlaneClient`; runtime selection by mode | tonic, prost, reqwest, rustls |
| `connectivity` | WireGuard data plane (`boringtun`), enrollment + heartbeat loops, XDP inspection tap (`aya`, feature `xdp`), Ziti hook | boringtun, aya, tokio |
| `netsvcs-edge` | local `:53` forwarder (`hickory-server`) → P3 DoH upstream (`hickory-resolver` DoH); DHCP client (`dhcproto`); NTP client (`ntp-proto`) | hickory-server, hickory-resolver, dhcproto, ntp-proto |
| `agent` (bin) | `clap` CLI, config load, feature-gated wiring, supervised task set, `healthz` subcommand | tokio, clap, all above |

**Crate DAG:** `core` → `transport` → {`connectivity`, `netsvcs-edge`} → `agent`. Every module crate depends only on `core` + `transport`, so once those are committed the modules build independently.

## Control-Plane Loop (designed fresh)

squawk-client-go has no enrollment loop — this is authored new, mirroring P2/P3 machine-JWT:

```
bootstrap (machine-JWT)  →  enroll (POST/gRPC RegisterServer)  →  receive node config + rotating refresh token
        →  run capability loops (connectivity / netsvcs-edge)
        →  periodic heartbeat + metrics push  →  config-version poll  →  single-use refresh (jti replay-protected)
```

- `aud="headend"`, `node_type` extends the P2 `dns_resolver` enrollment; scopes `dns:config:read metrics:write ioc:read` + connectivity scopes.
- Refresh is single-use with `jti` replay-protection (same contract as P2 `RefreshToken`).

## Transport Boundary

| Mode | Transport | Target |
|---|---|---|
| DaemonSet (intra-cluster) | gRPC `tonic` | hub_api netsvcs manager (`proto/netsvcs/v1`) |
| Bare-metal edge | REST `reqwest` | hub_api `/api/v1/netsvcs` |

Both carry a short-lived signed JWT (`Authorization: Bearer …`). The `ControlPlaneClient` trait is transport-agnostic; the two crates in `transport` implement it.

## Packaging

**musl static (bare-metal):** `cargo build --release --target x86_64-unknown-linux-musl` → single static binary + `systemd` unit + example config (`figment` reads env + file).

**Container (K8s):** multi-stage `rust:1.98-slim-bookworm`@digest builder → `debian:bookworm-slim`@digest runtime, non-root by default. The connectivity+DNS DaemonSet pod needs `NET_ADMIN` (WireGuard) and to bind `:53` → **documented `ROOT EXCEPTION (approved)`** in Dockerfile + Helm securityContext. Chart at `k8s/helm/node-agent/` (DaemonSet, `alpha.yml`/`beta.yml`/`gamma.yml`/`production.yml`).

## Security

- `Result<T, E>` everywhere; no `.unwrap()`/`.expect()` outside tests.
- `rustls` only (no openssl).
- Credentials written `0600`, dirs `0700` (matches P3 `manager_client.py`).
- No hardcoded secrets; deps exact-pinned; `Cargo.lock` committed; `cargo deny check` clean.
- Tenant always from validated JWT claims — never body/query/header.

## Feature Flags (PostHog)

`tobogganing.netsvcs.edge-dns`, `tobogganing.netsvcs.edge-dhcp`, `tobogganing.netsvcs.edge-ntp`, `tobogganing.connectivity.xdp-tap` — default OFF, evaluated at agent startup via the cached license/flag client (graceful degradation to last-known on unreachable).

## Parallel Build Plan (worktrees)

- **Stage F (foundation, sequential):** workspace + `core` + `transport` + `agent` skeleton; **stub** `connectivity`/`netsvcs-edge` crates (compilable no-op `lib.rs`). `cargo build` + `cargo clippy --all-targets -- -D warnings` green. Commit to `feature/squawk-merger`. **This is the interface contract.**
- **Stage P (parallel worktrees — each owns one crate dir, zero file overlap):**
  - `feature/p4-connectivity` → fills `crates/connectivity/`
  - `feature/p4-netsvcs-edge` → fills `crates/netsvcs-edge/`
  - `feature/p4-packaging` → `Dockerfile`, `k8s/helm/node-agent/`, systemd unit, musl release profile
- **Stage I (integration, sequential):** merge worktrees, wire `agent` bin to call both modules, full `cargo build --all-targets` + `cargo test` (nextest) + `cargo clippy -D warnings` + `cargo build --release --target x86_64-unknown-linux-musl` + `cargo deny check`. Verify both packagings. Commit.

## Testing

- `cargo nextest` (fallback `cargo test`); 90% floor via `cargo llvm-cov --fail-under-lines 90`.
- Unit inline `#[cfg(test)]`; integration in each crate's `tests/`.
- Module tests mock the `ControlPlaneClient` trait (no live hub_api).

## Out of Scope (P5)

Portal UI wiring, Helm umbrella integration, cross-module E2E.
