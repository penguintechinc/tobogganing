# Tobogganing Resource Sizing Guide

## Overview

This guide helps operators plan CPU, RAM, bandwidth, and storage for Tobogganing deployments. Resource requirements scale with client count and feature enablement. Use the formulas and example deployments below to right-size your infrastructure.

## Component Resource Requirements

### Hub-Router (services/hub-router)

The most resource-intensive component. Handles WireGuard termination, proxy, DNS forwarding, and performance monitoring.

| Clients | CPU (cores) | RAM | Bandwidth | Replicas |
|---------|------------|-----|-----------|----------|
| 100     | 1          | 512Mi | 100 Mbps | 1 |
| 1,000   | 4          | 2Gi   | 1 Gbps   | 2 |
| 10,000  | 8          | 8Gi   | 10 Gbps  | 4 |

**Key Factors:**
- WireGuard encryption is CPU-bound (~400 Mbps per core with ChaCha20-Poly1305)
- Each client tunnel consumes ~2KB RAM for state
- DNS forwarder (Squawk) adds ~50MB base + 1KB per cached entry
- XDP/BPF acceleration can 3-5x throughput per core

### Hub-API (services/hub-api)

Python/Quart async service handling API requests, policy management, and gRPC.

| Clients | CPU (cores) | RAM | Replicas |
|---------|------------|-----|----------|
| 100     | 0.25       | 256Mi | 1 |
| 1,000   | 0.5        | 512Mi | 2 |
| 10,000  | 2          | 2Gi   | 4 |

**Key Factors:**
- Async Quart handles ~1000 req/s per worker
- PyDAL connection pools: 10 per instance default
- JWT validation is CPU-light (~0.1ms per validation)
- gRPC streaming for policy updates adds ~100KB per connected router

### Hub-WebUI (services/hub-webui)

Static React SPA served by Nginx. Very lightweight.

| Clients | CPU (cores) | RAM | Replicas |
|---------|------------|-----|----------|
| Any     | 0.1        | 128Mi | 2 |

### Redis

Used for JWT token cache, policy sync, session storage.

| Clients | CPU (cores) | RAM | Storage |
|---------|------------|-----|---------|
| 100     | 0.1        | 128Mi | 256Mi |
| 1,000   | 0.25       | 256Mi | 1Gi |
| 10,000  | 0.5        | 1Gi   | 4Gi |

**Formula:** ~1KB per active session + ~500B per cached policy rule

## Database Sizing

### MySQL/PostgreSQL

| Clients | CPU (cores) | RAM | Storage | IOPS |
|---------|------------|-----|---------|------|
| 100     | 0.5        | 512Mi | 1Gi | 100 |
| 1,000   | 2          | 2Gi   | 10Gi | 500 |
| 10,000  | 4          | 8Gi   | 50Gi | 2000 |

### SQLite (Development Only)

Suitable for development/testing with <100 clients. Single file, no separate resource allocation.

## Network Bandwidth Planning

### WireGuard Throughput

- Single core: ~400 Mbps (ChaCha20-Poly1305)
- With XDP acceleration: ~2 Gbps per core
- Per-client overhead: ~100 bytes/packet for WireGuard encapsulation
- Keepalive traffic: ~100 bytes every 25 seconds per client

### Cluster-to-Cluster (Fabric)

- VPN mesh traffic grows O(n^2) with cluster count
- Recommend: dedicated hub-router instances per region
- iBGP control plane: <1 Mbps even with 100 clusters

### DNS (Squawk)

- Average query: ~200 bytes request, ~500 bytes response
- At 100 queries/s: ~0.5 Mbps
- Cache hit rate typically 60-80%, reducing upstream traffic

## WaddlePerf Metrics Overhead

When fabric monitoring is enabled:
- Per-test probe: ~1KB per measurement
- Default interval: 5 minutes
- Storage: ~300 bytes per metric row
- At 10 clusters (45 pairs): ~13KB per 5-minute interval = ~150MB/month

## Scaling Formulas

### Hub-Router Replicas

```
replicas = ceil(total_bandwidth_gbps / (0.4 * cores_per_replica))
```

Example: 4 Gbps demand / (0.4 * 8 cores) = 1.25 → 2 replicas

### Hub-API Replicas

```
replicas = ceil(peak_requests_per_second / 800)
```

Example: 2000 req/s / 800 = 2.5 → 3 replicas

### Redis Memory

```
memory_mb = (active_sessions * 1) + (policy_rules * 0.5) + (dns_cache_entries * 1) + 64
```

Example: (500 sessions) + (2000 rules * 0.5) + (10000 dns * 1) + 64 = ~10.5GB

## Example Deployments

### Small (Startup/Lab) — up to 100 clients

- 1x hub-router (1 core, 512Mi)
- 1x hub-api (0.25 core, 256Mi)
- 2x hub-webui (0.1 core, 128Mi)
- 1x Redis (0.1 core, 128Mi)
- SQLite or small MySQL
- **Total:** ~1.5 cores, 1Gi RAM

### Medium (SMB) — up to 1,000 clients

- 2x hub-router (4 cores, 2Gi each)
- 2x hub-api (0.5 core, 512Mi each)
- 2x hub-webui (0.1 core, 128Mi)
- 1x Redis (0.25 core, 256Mi)
- MySQL with read replica
- **Total:** ~10 cores, 6Gi RAM

### Large (Enterprise) — up to 10,000 clients

- 4x hub-router (8 cores, 8Gi each)
- 4x hub-api (2 cores, 2Gi each)
- 2x hub-webui (0.1 core, 128Mi)
- Redis Sentinel (3 nodes)
- MySQL Galera cluster (3 nodes)
- **Total:** ~44 cores, 42Gi RAM

## Recommendations

- Always deploy hub-webui with 2+ replicas for HA
- Use HPA for hub-api (target 70% CPU)
- Monitor hub-router CPU closely — it's the bottleneck
- Enable XDP/BPF on hub-router for >1000 clients
- Use read replicas for hub-api database queries at >500 clients
- Deploy Redis Sentinel for production environments
