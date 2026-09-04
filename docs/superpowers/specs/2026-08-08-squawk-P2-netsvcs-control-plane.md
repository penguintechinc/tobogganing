# Squawk → netsvcs Merge — P2: netsvcs control plane

**Date**: 2026-08-08
**Phase**: P2 (new module — control plane; port squawk `manager/backend` Flask→Quart)
**Branch**: `feature/squawk-merger`
**Umbrella**: `docs/superpowers/specs/2026-08-07-squawk-netsvcs-merge-umbrella.md`
**Depends on**: P1 (threatintel shared module — netsvcs consumes it)

## Goal

Create a new `hub_api/modules/netsvcs/` control-plane module by porting squawk's `manager/backend` (Flask+PyDAL) into Quart+penguin-dal, on tobogganing's identity/tenant/machine-JWT foundation. This is greenfield in tobogganing (no shipped code to break — unlike P1), so it builds additively.

Scope: **DNS control plane only** — zones/records CRUD, the DNS-resolver fleet plane (enroll/config/heartbeat), analytics. The DNS resolver *data-plane service* is P3; DHCP/NTP data-plane is P4. P2 declares the independent `tobogganing.netsvcs.{dns,dhcp,ntp}` flags but only `dns` is live.

## Locked decisions (user-approved 2026-08-08)

1. **Strict per-tenant zones** — every `dns_zone`/`dns_record`/resolver-token row carries a mandatory `tenant` (nullable=False, per `hub_api/db/models.py` convention). Squawk's nullable-`team_id` "public/global zone" concept is dropped; `visibility` (public/internal/restricted/private) is an **intra-tenant** attribute only — no cross-tenant shared zones. Team → tenant collapse.
2. **Both REST (+OpenAPI) and gRPC** — the node plane is served over REST + machine-JWT (sdwan pattern) **and** a gRPC manager service. Publish an OpenAPI 3.x spec for the REST surface via `quart-schema` (already a dep). Build the gRPC service now (`.v1` proto + `api_version`, grpc.aio, TLS-capable) — fixing all squawk gRPC bugs.
3. **threatintel owns feeds; netsvcs consumes** — no `ioc_feeds` CRUD in netsvcs. DNS filtering + `CheckIOC` call `BlocklistStore.check("domain"/"ip", value)` directly (import `hub_api.modules.threatintel.blocklist.store` by full path, as sase does). Feed-source management stays in threatintel.

**Derived (from recon, following the sdwan precedent — not separately asked):**
- **DNS-resolver fleet = operator infrastructure.** `dns_server`/`dns_server_metrics` enroll under `ENROLLMENT_TENANT` (like sdwan clusters/headends), NOT per-tenant. Their `tenant` column = the enrollment tenant. Zones/records/tokens are the tenant-scoped policy the fleet serves.
- **Drop squawk auth wholesale** — `auth_user`/`team`/`team_member`/`token`-mgmt blueprints + `auth_service`/`middleware/{auth,rbac}`/`license_service` → tobogganing `users` identity + `require_tenant`/`require_scope` + machine-JWT + license/PostHog entitlement.

## Module structure (mirror `hub_api/modules/sdwan/`)

```
hub_api/modules/netsvcs/
├── __init__.py                 # module() -> ModuleContract (name="netsvcs")
├── api/
│   ├── __init__.py             # blueprints = [zones_bp, dns_servers_bp, analytics_bp]
│   ├── zones.py                # Blueprint("netsvcs_zones", url_prefix="/zones")  — zones+records CRUD
│   ├── dns_servers.py          # Blueprint("netsvcs_dns_servers", url_prefix="/dns-servers")
│   └── analytics.py            # Blueprint("netsvcs_analytics", url_prefix="/analytics")
├── managers/
│   ├── zone_manager.py         # penguin-dal, tenant-scoped (ZoneManager(db, tenant_id))
│   ├── server_manager.py       # fleet enroll/config/heartbeat (ServerManager(db, tenant_id))
│   └── config_service.py       # assembles resolver config (zones+records+threatintel), monotonic version
├── grpc/
│   ├── manager.proto           # OR under proto/netsvcs/v1/ — see gRPC section
│   └── server.py               # grpc.aio ManagerService (api_version-routed)
└── ioc.py                      # thin threatintel BlocklistStore.check() wrapper (CheckIOC + config filter)
```
Tables live centrally in `hub_api/db/models.py` (SQLAlchemy, for Alembic), queried at runtime via penguin-dal AsyncDB. Register: add `"netsvcs"` to `hub_api/modules/__init__.py::__all__`.

## Models + migration (`0025_netsvcs_control_plane.py`, revision "0025", down_revision "0024")

All tables get `id` (String(36) UUID) + mandatory `tenant String(255) nullable=False index`. Port from squawk (team_id→tenant, drop nullability):

| Table | Columns (beyond id+tenant) | Notes |
|---|---|---|
| `dns_zones` | name, visibility(enum public/internal/restricted/private, default public), description, created_at, updated_at | `UniqueConstraint(tenant, name)` — name unique per tenant, not global |
| `dns_records` | zone_id(FK dns_zones CASCADE), name, type(enum A/AAAA/CNAME/MX/TXT/NS/SOA/PTR/SRV), value, ttl(300), priority, weight, port, created_at, updated_at | index (zone_id, name, type); tenant denormalized for query-scoping + must match zone.tenant |
| `dns_servers` | name, status(online/offline/degraded), version, region, hostname, last_heartbeat, created_at, updated_at | tenant = ENROLLMENT_TENANT (infra). **NO join_key/jwt_secret** — machine-JWT replaces them |
| `dns_server_metrics` | server_id(FK dns_servers CASCADE), timestamp, queries_total, cache_hits, errors, avg_response_ms | index (server_id, timestamp) |
| `dns_resolver_tokens` | name, token(unique), active, expires_at, last_used, created_by, created_at, updated_at | resolver-token → tenant → allowed zones (see auth). tenant-scoped |
| `dns_config_versions` | server_scope(or tenant), version(BigInteger, monotonic), updated_at | **replaces squawk's hash()-based version** — a real monotonic counter bumped on zone/record change |

Do NOT port: `ioc_feed` (threatintel owns), `auth_user`/`team`/`team_member` (tobogganing identity), the `.pyc`-only future tables (dhcp_*/time_*/whois/mtls/ioc_entry — P3/P4). One clean migration; squawk's broken Alembic history is discarded.

## Auth mapping

- **User/API CRUD** (zones/records/servers-mgmt/analytics): `@require_tenant` → `@require_scope("dns:read"/"dns:write")` → `@require_feature("netsvcs","dns")` → handler; `tenant = current_claims()["tenant"]`; every manager query ANDs `tenant`.
- **DNS-resolver node plane** (enroll/config/heartbeat/refresh): machine-JWT.
  - Add a resolver node_type + scope set to `hub_api/auth/machine_claims.py`: extend `build_machine_claims` so `node_type="dns_resolver"` → e.g. `DNS_RESOLVER_SCOPES = "dns:config:read metrics:write ioc:read"`. Enroll under `ENROLLMENT_TENANT`.
  - Enrollment: reuse the sdwan bootstrap pattern (`/api/v1/jwt/token` mint via api_key, or a bootstrap-token register route returning machine-JWT). Config-pull + heartbeat routes gated `@require_machine_jwt("dns:config:read")` / `("metrics:write")`, node identity from `g.machine_sub`.
  - Squawk's per-server `jwt_secret`/`join_key` + double-decode `server_token_required` are DROPPED — machine-JWT (rotating refresh, jti-revocation) replaces them entirely.
- **Resolver-token → allowed zones** (squawk `validate_dns_token`): re-express as tenant-scoped — a resolver token maps to its `tenant`; allowed zones = all `dns_zones` where `tenant == token.tenant`. Exposed via gRPC `ValidateToken` + used by the resolver (P3).

## REST surface (port the KEEP routes; all tenant-scoped, quart-schema-annotated)

Port from squawk (drop team RBAC → tenant+scope): zones (9 routes: list/create/get/update/delete zone + list/create/update/delete record), dns_servers (mgmt: list/create/get/delete/regen + node plane: register/config/heartbeat/refresh/metrics), analytics (queries/performance/servers/summary — actually apply tenant scoping, which squawk's analytics omitted). Response envelope `{...,"meta":{"version":1,"timestamp":...}}` per sdwan. **Every response through a quart-schema `@validate_response` model** (per security.md output-validation) — no raw row serialization.

## OpenAPI 3.x (`quart-schema`)

- Annotate netsvcs routes with `@validate_request`/`@validate_response` (Pydantic/dataclass models) so the spec generates from code (backend.md: generate, don't hand-maintain).
- Publish `openapi/v1.yaml` (extend if hub_api already emits one; else create + wire quart-schema). Validate in CI (`spectral lint`).
- **Docs/spec route auth-gated** (backend.md + security.md): live `/openapi.json`/`/docs` behind the JWT middleware; only a login/token endpoint may be public — netsvcs has no login (identity is core's), so the whole netsvcs spec is authed. Do NOT let quart-schema auto-mount an unauthenticated docs UI.

## gRPC manager service (`.v1` + `api_version`, grpc.aio) — fix every squawk bug

- **Proto**: `proto/netsvcs/v1/manager.proto`, `package netsvcs.manager.v1`, `option go_package = "github.com/penguintechinc/tobogganing/proto/netsvcs/v1;netsvcsv1"`. Every request message carries `string api_version = 1`. Dedupe squawk's triplicate `dns_query_service.proto` → one (data-plane, package `netsvcs.query.v1`) — but the query service is P3; P2 defines only the manager proto (+ the query proto skeleton if cheap).
- **Server** (`grpc.aio`, NOT sync grpcio; TLS via server credentials, NOT `add_insecure_port`): implement the manager RPCs, routing on `api_version` (`"v1"` → handler; else `UNIMPLEMENTED "api_version {v} not supported"`).
  - `RegisterServer`, `RefreshToken`, `GetConfig` — port, back onto machine-JWT + ServerManager/ConfigService.
  - **`StreamConfigUpdates`** (server-streaming) — **implement it** (squawk left it missing); push `ConfigUpdate` on version bump.
  - **`SendHeartbeat`** — reconcile the proto/impl cardinality mismatch: proto says bidi-stream; implement as a proper streaming handler (or make the proto unary to match a unary impl — pick one and make proto+impl agree).
  - **`get_config_version()`** — replace squawk's non-deterministic `hash(counts)` with the `dns_config_versions` monotonic counter.
  - **`CheckIOC`** — wire to threatintel: `BlocklistStore(cache).check("domain", domain)` / `.check("ip", ip)` → `IOCCheckResponse{blocked, reason, feed_source}` (squawk hardcoded `blocked=False`).
  - Compile stubs at build time (squawk never committed `*_pb2.py`); add the `protoc`/`grpcio-tools` build step. Health + reflection via `py_libs.grpc.create_server` scaffolding where useful.

## threatintel consumption

`netsvcs/ioc.py`: thin wrapper constructing `BlocklistStore(cache)` (cache from `current_app.config`) and calling `.check(ioc_type, value)`. Used by gRPC `CheckIOC` and by `config_service` when assembling resolver config (so nodes get current blocklist state). `Verdict` → `IOCCheckResponse` mapping. Fail-open (BlocklistStore already fails open).

## Flags + entitlements (contract)

```
flags: tobogganing.netsvcs.dns, .zones, .dns_servers, .analytics, .dhcp, .ntp
entitlements: netsvcs.dns/.zones/.dns_servers/.analytics = community;
              netsvcs.dhcp/.ntp = community (declared; data-plane P4);
              (large-fleet / advanced = professional if a gate is warranted)
```
`dhcp`/`ntp` flags are declared independent per the umbrella (enable separately) but gate no live code in P2.

## Verification gate

1. `python3 -m pytest hub_api/tests/` — full suite green (existing 1113 + new netsvcs tests; no regression).
2. `alembic upgrade head` clean on a fresh DB (migration 0025 applies; `test_migrations_head.py` covers new tables).
3. netsvcs contract test (sibling of `test_sase_module.py`): name, blueprint count, flags/entitlements, migrations `["0025"]`, routes mount at `/api/v1/netsvcs/...`.
4. Tenant-isolation tests: cross-tenant zone/record access → 403/empty; node plane rejects missing/invalid machine-JWT; resolver-token→allowed-zones scoped to tenant.
5. OpenAPI: `spectral lint openapi/v1.yaml` clean; docs route requires auth.
6. gRPC: unit tests for api_version routing (v1 ok, unknown → UNIMPLEMENTED), CheckIOC→threatintel, monotonic version bump, StreamConfigUpdates emits on change.
7. `make lint` (advisory) + bandit clean on new code; deps pinned+hashed (any new dep e.g. grpcio-tools → requirements).

## Execution stages (additive new module — safe to parallelize on disjoint files)

- **S0 Foundation (sequential, 1 agent)**: models in `hub_api/db/models.py` + migration `0025`; module skeleton (`__init__.py` contract with empty/stub blueprints, `api/__init__.py`, register in `__all__`); `machine_claims.py` resolver node_type+scopes. Gate: migration applies, module registers, suite green. Commit.
- **S1 REST blueprints (parallel, disjoint files)**: zones.py+zone_manager, dns_servers.py+server_manager (incl. machine-JWT node plane), analytics.py — each with quart-schema models + tenant-scoped tests. Independent files → parallel-safe.
- **S2 gRPC + OpenAPI + threatintel wiring (parallel)**: proto+grpc.aio server+config_service(monotonic version)+ioc.py; OpenAPI spec generation + auth-gated docs. 
- **S3 Integration**: finalize module contract wiring, cross-cutting tenant-isolation + contract tests, full suite, spectral lint. Commit + push.

Independent verification of every agent PASS (full suite on clean bytecode, tenant-isolation asserts, no false-green) — same discipline as P1. Lands on `feature/squawk-merger` (not merged to release).
