# Squawk → netsvcs Merge — P0 Import Manifest

**Date**: 2026-08-07
**Phase**: P0 (scope & dedup) — the deliverable that feeds P1–P5
**Source**: `/home/penguin/code/squawk` (Squawk DNS v5.1.1)
**Produced by**: 10 parallel read-only recon agents (one per repo area)
**Umbrella**: `docs/superpowers/specs/2026-08-07-squawk-netsvcs-merge-umbrella.md`

## Executive summary — read this first

**Squawk is prototype-grade, not production code to lift.** Across all 10 areas the recon found the same pattern: good *bones* wrapped in unfinished/insecure implementation.

- The "new" DNS agent (`dns-server/app`) implements only **DoH-JSON** — no DoT/HTTP3, gRPC is **dead-wired** (never called), and JWTs are decoded with **`verify_signature=False`** everywhere.
- The **DHCP and NTP "servers" are HTTPS-REST prototypes** — no real DHCP/NTP wire protocol, stub auth ("accept any non-empty token"), in-memory only, NTP cookie crypto is a literal **XOR demo stub**, and both Dockerfiles are **broken** (`COPY managers/` → nonexistent dir).
- The **actively-CI-tested** suite targets the **legacy `bins/`** code we're discarding; every KEPT component (`dns-server/app/services`, `manager/backend/app`, dhcp, ntp, frontend) has **zero or near-zero committed tests**.
- Several capabilities exist **only** in the legacy pile: HTTP/3, cert/mTLS issuance, WHOIS, MFA/SSO/session schemas.

**Implication for phasing/effort:** the merge is "**port the good bones + finish + harden + write comprehensive new tests**," NOT a clean lift. Raw LOC (~28K Py / 8K Go) understates it — much needs completion. Budget accordingly.

## Master verdict table

| Squawk area | LOC | Verdict | Lands as | Phase |
|---|---|---|---|---|
| `manager/backend/` (Flask+PyDAL control plane) | ~4.7K | **KEEP** (port Flask→Quart, PyDAL→penguin-dal) | `hub_api/modules/netsvcs/` | P2 |
| `dns-server/app/` (Quart DoH agent) | ~1.5K | **KEEP** (lift + finish) | `engines/netsvcs-dns` | P3 |
| `dns-server/bins/ioc_manager.py` parsers | (of 2.1K) | **HARVEST** (parsers only) | `threatintel/feeds/` | P1 |
| `dhcp-server/` + `ntp-server/` | ~0.8K | **KEEP** (HTTPS-REST prototypes → finish; wire-vs-REST decision) | `engines/netsvcs-{dhcp,ntp}` | P4 |
| `squawk-client-go/` (Go edge agent) | ~8K | **PORT → Rust** (reference, not preserve) | `agents/node-agent/` | P4 |
| `manager/frontend/` (React MUI) | ~2.6K | **KEEP → REBUILD** (MUI→Tailwind) | `portal/src/pages/netsvcs/` | P5 |
| `dns-server/bins/` (legacy monolith) | ~12K | **DISCARD** (harvest ioc_manager only; flag 4 unique caps) | — | — |
| `dns-server/web/` (py4web console) | ~2.8K | **DISCARD** (MFA/SSO schemas = spec reference) | — | — |
| `dns-server/flask_app/` (Flask variant) | ~1.6K | **DISCARD** (redundant) | — | — |
| `squawk-client/` (legacy Py client) | ~2.8K | **DISCARD** (superseded by Go→Rust) | — | — |
| `shared/{go,py,node,react}_libs` | ~15K | **REPLACE** with penguin-libs | — | — |
| `shared/licensing/` | — | **CONVERGE** — byte-identical to tobogganing's; use tobogganing's (superset) | `shared/licensing` | P1 |
| `protos/` (dns_query + manager_service) | — | **KEEP** (dedupe triplicate; `.v1` + `api_version`) | `proto/netsvcs/v1/` | P2 |
| `install.py` | ~0.5K | **REFERENCE** (systemd installer for the Rust agent) | — | P4 |
| `=1.69.0`/`=5.29.2`/`=0.23.0`/`=1.3.13`, venv/, `__pycache__` | — | **DISCARD** (junk) | — | — |

## P1 — threatintel harvest (the load-bearing input)

**Parser harvest list** (tobogganing has NONE of these — it only does plaintext/CIDR hostlists today; all squawk parsers are hand-rolled stdlib, no PRC/abandoned deps, `cabby` absent):

| Format | squawk fn:line | Harvest as-is? |
|---|---|---|
| MISP JSON | `_parse_misp_feed:623` (+ type/date mappers) | **YES** — structurally sound |
| OpenIOC XML | `_parse_openioc_feed:771` | **YES** |
| threat-CSV (confidence/category cols) | `_parse_csv_feed:562` | **YES** |
| structured JSON (URLhaus/generic) | `_parse_json_feed:530` | **YES** |
| generic XML | `_parse_xml_feed:1129` | yes |
| STIX 2.x | `_parse_stix_feed:707`, `_parse_stix_objects:1798` | **NO — replace with OASIS `stix2` lib** (squawk's is naive regex) |
| TAXII 2.1 | `TAXII2Client:1981` | **NO — replace with `taxii2-client` (OASIS)** |
| YARA / Snort | `_parse_yara_feed:1023`, `_parse_snort_feed:1081` | harvest cautiously (regex scrapers, don't parse rules) |
| txt hostfile | `_parse_text_feed:485` | **SKIP** — tobogganing already covers (+squawk's is broken, missing helpers) |

- **Model delta to preserve**: squawk carries `misp_event_id`, `misp_attribute_id`, `source_format` that tobogganing's `ThreatIndicator`/`Verdict` lack → fold into `threat_metadata` when landing the MISP parser (else provenance lost).
- **DISCARD from ioc_manager**: its store/schema (4 PyDAL tables), fetch/scheduler, enforcement/lookup, overrides, feed-CRUD/licensing — all superseded by tobogganing `feeds/`+`BlocklistStore`+`SwgLookup`. Cherry-pick the fetch auth-setup (basic/bearer/apikey) logic.
- **Licensing**: `shared/licensing` is byte-identical to tobogganing's + tobogganing adds `entitlements.py`+tests → adopt tobogganing's as canonical, discard squawk's.
- **Test harvest**: `dns-server/tests_full_future/test_ioc_manager.py` (27 tests) — top priority.
- **Recall P1 also refactors shipped SASE** (`feeds/`+`blocklist/` move into `threatintel`; SWG/adapters/catcache repoint) — preserve all existing SASE tests (suite parity). This is the riskiest phase.

## P2 — netsvcs control plane

- **KEEP-port blueprints**: `zones` (+records), `dns_servers` (fleet reg/config/heartbeat/metrics), `analytics`, `ioc_feeds` (→ remap to threatintel). Flask→Quart mechanical; PyDAL `db(...).select()` → penguin-dal (drop PyDAL auto-migrate + the parallel Alembic dir → single penguin-dal migration).
- **KEEP-port models**: `dns_zone`, `dns_record` (CASCADE), `dns_server` (join_key, per-server jwt_secret), `dns_server_metrics`, `token` (DNS-resolver token), `ioc_feed`(→threatintel).
- **DROP → tobogganing identity/tenant**: `auth`/`users`/`teams`/`tokens` blueprints, `auth_user`/`team`/`team_member` models, bespoke bcrypt+PyJWT (`auth_service.py`), `middleware/{auth,rbac}.py`, bespoke `license_service.py`. **Preserve semantics** of `validate_dns_token` (token→team→allowed_zones) + server-JWT + the zone-visibility access logic when remapping `team_id → tenant_id`.
- **gRPC** (`manager_service.proto`): KEEP; port sync grpcio→`grpc.aio`, add TLS/mTLS (currently `add_insecure_port`), **implement the missing `StreamConfigUpdates`**, reconcile the `SendHeartbeat` unary-vs-bidi mismatch, and **fix `ConfigService.get_config_version()`** (uses non-deterministic Python `hash()` → needs a real monotonic version column). `CheckIOC` is a stub → wire to threatintel.
- **Proto**: dedupe the triplicate `dns_query_service.proto` (keep one), rename packages `…query.v1`/`…manager.v1`, add the `api_version` field (per `backend.md`; tobogganing has no proto exemplar yet).
- **Tenancy call**: `dns_server`/`ioc_feed` are currently org-global (no team_id) — decide tenant-scoped vs global in P2.

## P3 — DNS data-plane service (`engines/netsvcs-dns`)

- **Lift** `app/services/`: `dns_resolver` (dnspython fwd + custom-zone), `selective_router` (split-horizon public/internal/restricted/private — the genuinely net-new capability), `cache_manager` (fix sync-redis-in-async), `metrics_reporter`, `manager_client`.
- **Must-fix on port**: (1) `ioc_checker` → **threatintel client** (needs `is_blocked(domain)` parent-suffix + `is_ip_blocked(ip)` against the shared store); (2) **JWT `verify_signature=False`** at `selective_router.py:69`, `resilience.py:117`, `manager_client` → real machine-JWT verification; (3) **wire the dead gRPC** (compile proto, use pb2 not dicts, actually call `serve_grpc()`); (4) **Debian-slim rebuild** + create the missing `requirements-dns-server.txt` (the wired Docker build currently runs the *legacy* `bins/` server, not `app.main`); (5) auth → machine-JWT enrollment.
- **Net-new decision**: DoT (853) + HTTP/3 DoH are NOT in `app/` (only legacy `bins/server_http3.py`) → if required, add via **`penguin-h3`** (Python H3/QUIC) — this is where tobogganing's H3 stack fits.
- **Test harvest**: `test_selective_dns_routing.py` (26), `test_server.py` (10), partial `test_authentication`/`test_api_integration` (IOC/override parts; **drop whois**). The kept `app/services/*` have ZERO committed tests → net-new suite required.

## P4 — Rust `node-agent` + DHCP/NTP services

**squawk-client-go → Rust node-agent** (confirmed netsvcs-ONLY — zero WireGuard/tunneling code; connectivity half comes from tobogganing, no Go reference):

| Capability | Go lib | Rust crate | Story |
|---|---|---|---|
| local :53 DNS server + RR build | `miekg/dns` | `hickory-dns` | strong |
| DoH JSON client / h1/h2 | `net/http` | `reqwest`+`serde` | strong |
| HTTP/3 QUIC | `quic-go` | `quinn` (+`h3`) | **moderate** — `h3` less mature |
| gRPC client | grpc-go | `tonic`+`prost` | strong (Rust adds TLS) |
| DHCP codec + client | hand-rolled | `dhcproto`+`tokio` | strong |
| NTP + NTS-KE | hand-rolled | **`ntpd-rs`/`ntp-proto`** | **weak/caveat** — NOT `statime` (PTP); squawk tunnels NTS over HTTPS (non-standard) → redo transport |
| :68/:123 intercept | `net.ListenUDP` | `tokio` UDP | strong |
| config / CLI / logging | viper/cobra/log | `figment`/`clap`/`tracing` | strong |
| license | `net/http` | `reqwest` or the `integrating-license-server` skill | strong |
| **connectivity (WireGuard/XDP)** | — none in squawk — | `boringtun`/`aya` | **design against tobogganing** |

- **No control-plane loop** exists in the edge agent to port (its gRPC is DNS-query-only) → design the agent↔manager enrollment/heartbeat fresh (reference `dns-server/app/manager_client.py` + `tests_full_future/test_client_config_api.py`).
- **Installer**: `install.py` is the systemd reference — reproduce its hardening (`PrivateTmp`/`ProtectSystem=strict`/`ProtectHome`/`NoNewPrivileges`/`ReadWritePaths`) + the dual `resolved.conf`/`resolv.conf` DNS-rewrite **and rollback**, but **drop `User=root`** to a dedicated user. **No `.deb`/`.rpm`/nfpm/goreleaser exists** → new packaging needed. **Naked static-musl binary + container image from one CI build** (decisions #7/#8).

**DHCP + NTP services** (`engines/netsvcs-{dhcp,ntp}`): both are **HTTPS-REST prototypes, not real wire servers** → **scope decision: keep HTTPS-REST or implement real DHCP/NTP wire.** Both need: a control-plane binding (built from scratch — neither has gRPC/manager wiring), real auth (currently stub), persistence (in-memory), Dockerfile fix (`COPY managers/` is broken) + Debian base, and NTP's XOR cookie stub → real AEAD. Cleanly DNS-decoupled → the independent `tobogganing.netsvcs.{dhcp,ntp}.*` flags need zero decoupling work.

## P5 — UI + Helm + tests

- **Frontend = REBUILD, not port**: portal is Tailwind v4 + TanStack Query; squawk is MUI + zustand → every keeper page is a visual rebuild. Only ~934 TSX LOC of keepers (Dashboard/StatsOverview/QueryChart/DNSServerFleet/DNSServers/Zones); QueryChart is the easiest (recharts shared). **The IOC-feeds UI and the DNS-records editor DON'T EXIST** → net-new builds. Drop Login/Users/Teams/Navbar/Sidebar/ProtectedRoute → portal equivalents. New `portal/src/api/netsvcs.ts`.
- **Helm = author fresh** (none in squawk): the `docker-compose-manager.yml` (manager + 2 DNS nodes via `JOIN_KEY`) is the topology reference; the node-agent DaemonSet; optional DHCP/NTP sub-charts (like the SASE analysis sub-charts). Fix: **root containers** (Dockerfile.dns-server/dhcp/ntp/manager/nginx) → non-root + fixed UIDs; **postgres 15/16 → 17**; pin valkey; translate `init-postgres.sql`.
- **Tests = net-new for everything kept** (CI today only tests legacy `bins/`; 80% gate vs tobogganing's 90%). Harvest `tests_full_future/` per phase; the **ghost bytecode** in `manager/backend/tests/`, dhcp/ntp, `tests/{unit,integration,smoke,load}` (source lost) gives rebuild-checklist names (e.g. `test_spiffe_auth`, `test_ioc_ssrf`, `test_scope_authz`, `test_nts_wire_interop`).

## Map-or-drop decisions (explicit calls for later phase specs — don't silently drop)

| Capability | Only exists in | Recommendation |
|---|---|---|
| HTTP/3 DoH | legacy `bins/server_http3.py` | ADD via `penguin-h3` if H3 DoH is a product requirement (P3) |
| cert/mTLS issuance | legacy `cert_manager.py` | MAP → tobogganing **core PKI** (`core/certificates.py`) |
| MFA / SSO / session / audit schemas | legacy `dns_console` tables | MAP → tobogganing **identity** (penguin-aaa handles MFA/SSO centrally) |
| WHOIS | legacy `whois_manager.py` | **NET-NEW** — no tobogganing analog; decide if it ships (likely defer) |
| config versioning/rollback | legacy `client_config_api.py` | evaluate for the netsvcs config-distribution model (P2) |
| DHCP/NTP real wire protocol | (neither exists — HTTPS-REST only) | **scope decision** P4: keep HTTPS-REST or implement UDP 67/68/123 wire |

## Discard manifest (explicit — delete, do not import)

`dns-server/bins/` (except ioc_manager parsers) · `dns-server/web/` · `dns-server/flask_app/` · `squawk-client/` · `shared/{go_libs,py_libs,node_libs,react_libs,database}` · squawk's `shared/licensing/*` · duplicate `dns_query_service.proto` (×2) · `=1.69.0`/`=5.29.2`/`dns-server/=0.23.0`/`squawk-client-go/=1.3.13` · all `venv/`, `__pycache__/`, `.pytest_cache/` · the dangling `docker-compose.license.yml` refs to nonexistent `Dockerfile.console`/`license-server/`.

## Recommended next phase

**P1 (threatintel extraction)** — it's the load-bearing refactor of shipped SASE code + the harvest target, and everything else consumes it. Its spec should nail: the `sase:blocklist:*` → shared key-prefix decision, the parser harvest (MISP/OpenIOC/CSV as-is; STIX/TAXII via OASIS libs), the model-delta columns, and the SASE-consumer repoint with full suite parity.
