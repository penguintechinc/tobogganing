# netsvcs-dns: DNS Resolver Fleet-Node Service

DNS-over-HTTPS (DoH) and DNS-over-TLS (DoT) resolver for the netsvcs control plane.

## Overview

This is the data-plane DNS resolver service (P3) for the squawk→netsvcs merge. Each instance runs as a DaemonSet pod, enrolls as a `dns_resolver` machine-JWT client with the control plane (P2), and handles DNS queries with:
- Split-horizon zone resolution (public/internal/restricted/private visibility)
- IOC (Indicator of Compromise) filtering via control-plane CheckIOC gRPC
- Request-scoped caching (Redis/Valkey async)
- Prometheus metrics + heartbeat reporting to control plane

## Protocols

- **DoH** (DNS-over-HTTPS): HTTP/2 on port 8080
  - RFC 8484 wireformat: `POST /dns/query`
  - Google JSON: `GET /dns/query?name=...&type=...`
- **DoT** (DNS-over-TLS): port 853, RFC 7858 2-byte length prefix
- **Metrics**: Prometheus format on port 9090 at `/metrics`
- **Health**: `/healthz` (liveness) and `/ready` (readiness) on port 8080

## Control Plane Integration

Resolver ↔ Control Plane (gRPC):
- `RegisterServer` — enroll on startup
- `GetConfig` — fetch current zone config, IOC state
- `StreamConfigUpdates` — live resync on version bump
- `CheckIOC` — per-query filtering (fail-open)
- `ValidateToken` — DNS-client token validation
- `SendHeartbeat` — periodic metrics + config version ack

## Configuration

Environment variables (see `Dockerfile`/Helm values):
- `CONTROL_PLANE_GRPC_ADDR` — netsvcs manager gRPC endpoint (e.g., `hub-api-grpc:50051`)
- `ENROLLMENT_BOOTSTRAP_TOKEN` — machine JWT for initial enrollment (from secret)
- `GRPC_TLS_CA_PATH` — CA cert for gRPC channel (optional; mTLS-capable)
- `GRPC_INSECURE_DEV_FLAG` — allow insecure (dev only)
- `CACHE_URL` — Redis/Valkey connection (e.g., `redis://valkey:6379`)
- `CONFIG_CACHE_DIR` — offline config cache directory

## Deployment

### Kubernetes/Helm

```bash
helm install netsvcs-dns ./k8s/helm/netsvcs-dns \
  --kube-context local-alpha \
  --namespace netsvcs \
  --values k8s/helm/netsvcs-dns/alpha.yml
```

Each environment has its own values file:
- `alpha.yml` — local K8s, insecure gRPC, minimal resources
- `beta.yml` — remote dal2-beta, gRPC TLS, test resources
- `gamma.yml` — remote dal2-gamma, gRPC TLS, test resources
- `production.yml` — production domain, gRPC TLS + mTLS, full HA resources

### Local Testing

```bash
cd engines/netsvcs-dns
python3 -m pytest tests/ -v
python3 -m app.main  # Requires CONTROL_PLANE_GRPC_ADDR + bootstrap token env vars
```

## Testing

Isolated test suite (not in hub_api):
```bash
cd engines/netsvcs-dns
python3 -m pytest tests/ -q  # Unit + integration tests
python3 -m pytest tests/ --cov --cov-fail-under=90  # Coverage gate (90%+ required)
```

Tests cover:
- Resolver + split-horizon matrix
- Cache (async Redis)
- DoH (JSON + RFC8484)
- DoT (TLS + RFC7858)
- gRPC client (manager enrollment, config fetch, stream, validate_token, check_ioc)
- IOC blocking
- Metrics reporting
- Error handling

## Metrics

Prometheus counters/histograms/gauges:
- `netsvcs_dns_queries_total{type}` — total queries by type
- `netsvcs_dns_cache_hits_total` — cache hits
- `netsvcs_dns_cache_misses_total` — cache misses
- `netsvcs_dns_errors_total{error_type}` — errors (refused, timeout, etc.)
- `netsvcs_dns_ioc_blocks_total` — IOC-blocked queries
- `netsvcs_dns_upstream_latency_seconds` — upstream DNS latency (histogram)
- `netsvcs_dns_query_latency_seconds` — total query latency (histogram)
- `netsvcs_dns_cache_size_bytes` — cache size gauge

## Security

- **TLS/mTLS on gRPC** (control-plane channel is SPIFFE-ready)
- **JWT-signed machine identity** (bootstrap + refresh tokens, short-lived ~1h)
- **Tenant scoping** (all queries scoped to token tenant)
- **IOC/threat feeds via control plane** (never imported locally; fail-open on error)
- **Split-horizon authorization** (zone visibility by tenant + token teams)
- **Non-root container** (runAsNonRoot + read-only root FS + drop ALL capabilities)

## Implementation Status

**P3-S4 (completed):**
- Prometheus metrics collection + `/metrics` endpoint
- DoT no-cert regression test (guards stdlib logging crash)
- Finalized Dockerfile (Debian bookworm, SHA256 digest-pinned, multi-stage, non-root)
- Minimal DaemonSet Helm chart (alpha/beta/gamma/production overrides)

**Related phases:**
- P2: netsvcs control plane (hub-api, ManagerService gRPC)
- P1: threatintel (IOC feeds, provided via control plane)
- P4: Rust edge node-agent (SASE client, forwards queries to these resolvers)
