# Squawk → netsvcs Merge — P3: DNS data-plane resolver service

**Date**: 2026-08-11
**Phase**: P3 (new data-plane service — port squawk `dns-server/app`)
**Branch**: `feature/squawk-merger`
**Umbrella**: `docs/superpowers/specs/2026-08-07-squawk-netsvcs-merge-umbrella.md`
**Depends on**: P2 (netsvcs control plane — the resolver enrolls with + pulls config from it) and P1 (threatintel — IOC checks flow through the control plane's `CheckIOC`).

## Goal

Build `engines/netsvcs-dns` — the server-side DNS **resolver fleet-node** service. Each instance enrolls as a machine-JWT `dns_resolver` node, pulls config (zones/records/IOC state) from the netsvcs control plane, and serves DNS queries with split-horizon zone resolution + IOC filtering, reporting metrics via heartbeat. This is the software that runs as the `dns_servers` fleet that P2's control plane manages. (The P4 Rust node-agent is the separate EDGE client that forwards to these resolvers.)

## Locked decisions (user-approved 2026-08-11)

1. **Protocols: DoH (HTTP/2 — JSON + RFC 8484 wireformat) + DoT (853).** Squawk's app was DoH-JSON only; add DoT now. HTTP/3 DoH deferred (H3/QUIC least mature; add via `penguin-h3` later if required).
2. **Control-plane transport: gRPC.** The resolver fleet is **intra-cluster** (DaemonSet-style, high consistent query volume, trusted network) → gRPC. It uses a `grpc.aio` client of P2's `netsvcs.manager.v1.ManagerService` (RegisterServer/GetConfig/StreamConfigUpdates/ValidateToken/CheckIOC). This wires + exercises the P2 gRPC plane (currently latent) as its intended consumer. REST is reserved for external/edge clients (see [[grpc-rest-transport-boundary]]).
3. **Language: Python/Quart** (umbrella — resolver stays Python unless a measured >10K rps need, then Rust). **Resolver only** — DHCP/NTP are P4.
4. **Auth on the gRPC channel = short-lived signed JWTs (universal rule).** Every inter-service call (gRPC here) carries a short-lived, **signed** machine-JWT (JWS; ~1h access + rotating single-use refresh, aud=`headend`, tenant/scope claims) — the same model P2 enforces on `ManagerService`. Use **JWE (encrypted)** for any sensitive claim payloads. No long-lived static tokens between services. The gRPC channel is mTLS-capable (SPIFFE-ready) in addition to the JWT. See [[grpc-rest-transport-boundary]].

## Source (from P3 recon) — what to port from `~/code/squawk/dns-server/app/`

| squawk file | → | P3 treatment |
|---|---|---|
| `services/dns_resolver.py` (dnspython fwd + custom-zone) | keep | port; use `dns.asyncresolver` (squawk's `resolve` was sync-in-async) |
| `services/selective_router.py` (split-horizon public/internal/restricted/private) | keep — the net-new capability | **consolidate the 3 divergent copies** (this + `utils/resilience.py::_check_zone_permission` + `main._find_zone_name`) into ONE authoritative implementation |
| `services/cache_manager.py` (sync redis) | keep | **async redis/valkey** (`redis.asyncio`) — squawk used the sync client inside async |
| `services/ioc_checker.py` (in-memory sets) | replace | call control-plane **`CheckIOC` gRPC** (resolver is a separate service; cannot import threatintel directly) |
| `services/metrics_reporter.py` | keep | port; feeds heartbeat + Prometheus `/metrics` |
| `services/manager_client.py` (REST/`requests`) | replace | **`grpc.aio` client** of `ManagerService` (register/GetConfig/StreamConfigUpdates/ValidateToken); offline disk-cache resilience preserved |
| `app/main.py` (DoH `/dns/query` handler) | keep | port DoH pipeline; add the DoT listener |
| `app/grpc_server.py` (dead-wired DNSQueryService) | discard/defer | not the control path; the resolver is a gRPC CLIENT of the manager, not a server here |
| `utils/resilience.py` (ResilienceManager: normal/cached/degraded) | keep | port the graceful-degradation ladder; fold its split-horizon copy into the one authoritative router |

## Must-fix on port (P0/P3 recon flagged)

- **JWT `verify_signature=False`** at `selective_router.py:69`, `resilience.py:117`, `manager_client.py:228` → verify signatures properly against the control-plane public key (fetch via the machine-JWT/JWKS path; the resolver already holds a machine-JWT, use the same key material to verify DNS-client tokens where applicable, or delegate token validation to the control-plane `ValidateToken` RPC).
- **Sync I/O in async**: `cache_manager` (sync redis), `dns_resolver.resolve` (sync `dns.resolver`), `manager_client` (sync `requests`) → all async (`redis.asyncio`, `dns.asyncresolver`, `grpc.aio`).
- **gRPC dead-wiring**: squawk's gRPC was never compiled/served. Here the resolver is a gRPC CLIENT — generate/import the `proto/netsvcs/v1/manager_pb2*` stubs (built in P2) and actually call them.
- **Dockerfile**: squawk's default Dockerfile runs the legacy `bins/` server. New `engines/netsvcs-dns/Dockerfile` — Debian bookworm slim, multi-stage, non-root, runs `python3 -m app.main`; native health check.
- **Config-distribution**: use `GetConfig` + `StreamConfigUpdates` (P2 implemented streaming) for live resync on the monotonic version bump — not squawk's poll-only `should_sync`.

## Service structure

```
engines/netsvcs-dns/
├── app/
│   ├── main.py               # Quart app + DoH handler + DoT listener + startup (enroll, sync, heartbeat tasks)
│   ├── config.py             # env-driven (control-plane gRPC addr, enrollment, cache, ports, TLS)
│   ├── resolver.py           # DNSResolver (dns.asyncresolver + custom-zone)
│   ├── router.py             # SelectiveRouter — the ONE split-horizon impl (public/internal/restricted/private)
│   ├── cache.py              # async CacheManager (redis.asyncio / valkey)
│   ├── manager_client.py     # grpc.aio ManagerService client (register/config/stream/validate/checkioc) + disk cache
│   ├── ioc.py                # thin CheckIOC-over-gRPC wrapper (hot path)
│   ├── metrics.py            # MetricsReporter + Prometheus text
│   └── servers/
│       ├── doh.py            # DoH: JSON (application/dns-json) + RFC8484 wireformat, HTTP/2
│       └── dot.py            # DoT listener on :853 (TLS), forwards into the resolve pipeline
├── Dockerfile                # Debian slim, non-root, python3 -m app.main
├── requirements.in / .txt    # hash-pinned (dnspython, redis, grpcio, hypercorn, quart, prometheus-client)
├── k8s/helm/…                # DaemonSet chart (P5 may own the umbrella; a minimal chart here)
└── tests/                    # isolated pytest suite (unit + integration; NOT the hub_api suite)
```
The resolver imports the P2-generated proto stubs from `proto/netsvcs/v1/` (same repo).

## Resolve pipeline (DoH + DoT share it)

1. Extract query (name, type, DNS-client token from Authorization/param).
2. Resilience mode (normal/cached/degraded) — degraded → public zones only.
3. **IOC check** → control-plane `CheckIOC` (fail-open on error, as designed).
4. Cache lookup (async).
5. **Split-horizon**: `SelectiveRouter` matches zone (exact → parent-label walk); permission by visibility + the DNS-client token's tenant/teams (validated via `ValidateToken` → allowed zones); custom-zone records served directly, else recurse via `dns.asyncresolver`.
6. Cache on NOERROR; record metrics.
7. Return Google DoH-JSON or RFC8484 wireformat (DoH) / wire response (DoT).

## Verification gate

- Isolated `engines/netsvcs-dns/tests/` pytest suite (this service is NOT in the hub_api suite): unit (resolver, router split-horizon matrix, cache, ioc, metrics) + integration (DoH JSON + wireformat query flow, DoT query, split-horizon allow/deny per visibility, IOC-block, config sync + stream, degraded mode).
- gRPC client tested against P2's `ManagerService` (a test harness or a stubbed servicer) — proves the resolver↔control-plane contract, de-latents the P2 gRPC plane.
- Real JWT verification test (a bad-signature token is rejected — guards against the `verify_signature=False` regression).
- `make build`/container: image builds, runs `app.main`, `/healthz` + `/metrics` respond, DoH query returns.
- Security: bandit clean; TLS on DoT + the gRPC client (mTLS-capable); no `verify_signature=False`; deps hash-pinned.

## Execution stages

- **S0 Foundation**: `engines/netsvcs-dns` scaffold — config, the `grpc.aio` ManagerService client (enroll via RegisterServer, machine-JWT storage, GetConfig), Quart app skeleton + `/healthz`/`/metrics`, requirements, Debian Dockerfile. Gate: enrolls against a stub/real ManagerService, pulls config, container builds + starts.
- **S1 Resolver core**: `resolver.py` (async), `router.py` (the ONE consolidated split-horizon), `cache.py` (async). Gate: unit tests for resolve + the split-horizon visibility matrix + cache.
- **S2 Serving**: `servers/doh.py` (JSON + RFC8484) + `servers/dot.py` (853); the shared resolve pipeline; resilience ladder. Gate: DoH + DoT integration query tests.
- **S3 Control-plane wiring**: `ioc.py` (CheckIOC gRPC, fail-open), `ValidateToken` for DNS-client tokens, `StreamConfigUpdates` live resync, metrics→heartbeat, real JWT verification. Gate: IOC-block test, token-scoped zones, stream-resync, bad-signature rejection.
- **S4 Package + tests**: finalize Dockerfile/health, DaemonSet chart, full isolated suite green, bandit, deps pinned.

Independent verification of every agent PASS (run the isolated suite on clean bytecode; no false-green). Lands on `feature/squawk-merger` (not merged to release).
