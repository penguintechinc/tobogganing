# Squawk DNS Integration Guide

## Overview

**Squawk** is PenguinTech's DNS-over-HTTPS (DoH) proxy service that provides secure, privacy-preserving DNS resolution with policy-based filtering capabilities. This guide covers how Squawk integrates with Tobogganing's networking infrastructure.

## What is Squawk?

Squawk is a centralized DNS service that:
- Encrypts DNS queries using HTTPS (RFC 8484)
- Provides policy-based DNS filtering and blocklists
- Offers privacy-first DNS resolution without query logging
- Integrates seamlessly with Tobogganing's policy engine
- Supports custom DNS rules per tenant and team

## Integration Architecture

Tobogganing integrates Squawk at three levels:

```
┌─────────────┐
│   Client    │
│  (Native,   │
│  Docker)    │
└──────┬──────┘
       │ DNS port 53 (UDP/TCP)
       ▼
┌────────────────────────┐
│  Local DNS Listener    │
│  (127.0.0.1:53)        │
└──────┬─────────────────┘
       │ Forward to hub-router
       ▼
┌────────────────────────┐
│  Hub-Router DNS        │
│  Forwarder Module      │
└──────┬─────────────────┘
       │ HTTPS to Squawk
       ▼
┌────────────────────────┐
│  Squawk DoH Server     │
│  (Upstream DNS)        │
└────────────────────────┘
```

### Resolution Flow

1. **Client initiates DNS query** via local DNS listener (127.0.0.1:53)
2. **Hub-router DNS forwarder** receives query and applies policy filters
3. **Policy engine** checks if domain is blocked by tenant/team policies
4. **Squawk DoH proxy** receives filtered query via HTTPS
5. **Upstream DNS resolver** (Cloudflare, Google, custom) resolves query
6. **Response** cached in hub-router and returned to client
7. **Metrics** recorded: query count, duration, blocked count

## Configuration

### Hub-Router Configuration

Enable Squawk DNS forwarding in the hub-router via environment variables or viper config:

```yaml
# deploy/kubernetes/values-hub-router.yaml
dns:
  enabled: true
  listen_addr: "0.0.0.0:53"
  squawk_server: "https://dns.penguintech.io/dns-query"
  # Optional: custom upstream DNS (if Squawk unavailable)
  fallback_upstream: "1.1.1.1:53"
  # Query caching (seconds)
  cache_ttl: 3600
  # Maximum concurrent queries
  max_concurrent_queries: 1000
  # Enable blocklist enforcement
  blocklist_enforcement: true
```

Environment variables:

```bash
# Enable DNS module
HUB_ROUTER_DNS_ENABLED=true

# DNS listener address
HUB_ROUTER_DNS_LISTEN_ADDR=0.0.0.0:53

# Squawk DoH server endpoint
HUB_ROUTER_DNS_SQUAWK_SERVER=https://dns.penguintech.io/dns-query

# Fallback upstream (for resilience)
HUB_ROUTER_DNS_FALLBACK_UPSTREAM=1.1.1.1:53

# Cache TTL
HUB_ROUTER_DNS_CACHE_TTL=3600

# Max concurrent queries
HUB_ROUTER_DNS_MAX_CONCURRENT_QUERIES=1000
```

### Native Client Configuration

Enable DNS resolution on native clients (macOS, Linux, Windows):

```yaml
# ~/.tobogganing/config.yaml
squawk_enabled: true
squawk_server_url: "https://dns.penguintech.io/dns-query"
dns_listen_addr: "127.0.0.1:53"
# Optional: fallback DNS servers
fallback_dns:
  - "1.1.1.1"
  - "8.8.8.8"
```

### Docker Client Configuration

Enable DNS resolution in containerized deployments:

```bash
docker run -d \
  --name tobogganing-client \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -e SQUAWK_ENABLED=true \
  -e SQUAWK_SERVER_URL=https://dns.penguintech.io/dns-query \
  -e DNS_LISTEN_ADDR=127.0.0.1:53 \
  ghcr.io/penguintechinc/tobogganing-client:latest
```

Or via docker-compose:

```yaml
# docker-compose.yml
services:
  tobogganing-client:
    image: ghcr.io/penguintechinc/tobogganing-client:latest
    environment:
      SQUAWK_ENABLED: "true"
      SQUAWK_SERVER_URL: "https://dns.penguintech.io/dns-query"
      DNS_LISTEN_ADDR: "127.0.0.1:53"
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun
```

### Helm Configuration

Configure Squawk integration in Kubernetes deployments:

```yaml
# deploy/kubernetes/values.yaml
squawk:
  enabled: true
  dohServer: "https://dns.penguintech.io/dns-query"
  # Include Squawk as sub-chart (optional dependency)
  subchart:
    enabled: false  # Use external Squawk service
    # Or deploy Squawk in-cluster:
    # enabled: true
    # image: ghcr.io/penguintechinc/squawk:latest
    # replicas: 2

hub-router:
  dns:
    enabled: true
    listenAddr: "0.0.0.0:53"
    squawkServer: "http://squawk:8080/dns-query"
    cacheTTL: 3600
    blocklistEnforcement: true

# DNS Service exposure
dns-service:
  enabled: true
  type: ClusterIP
  port: 53
  # Optional: NodePort for host DNS
  # type: NodePort
  # nodePort: 53
```

## Policy-Based DNS Filtering

Tobogganing's policy engine controls DNS filtering via policy rules:

```python
# Policy rule structure
{
    "name": "block-adult-sites",
    "scope": "wireguard",
    "protocol": "dns",
    "action": "block",
    "domains": ["*.adult.com", "*.nsfw.io"],
    "tenant_id": "tenant-uuid",
    "teams": ["security-team"],
    "priority": 100
}
```

### API Endpoint: Create DNS Policy

```bash
POST /api/v1/policies/dns
Content-Type: application/json

{
  "name": "block-streaming-services",
  "scope": "wireguard",
  "protocol": "dns",
  "action": "block",
  "domains": ["*.netflix.com", "*.hulu.com", "*.disney.com"],
  "reason": "Enforce corporate streaming policy",
  "tenant_id": "tenant-123"
}
```

### API Endpoint: Query DNS Policy

```bash
GET /api/v1/policies/dns?tenant_id=tenant-123&team_id=team-456

# Response
{
  "status": "success",
  "data": [
    {
      "id": "policy-uuid",
      "name": "block-streaming-services",
      "scope": "wireguard",
      "protocol": "dns",
      "action": "block",
      "domains": ["*.netflix.com", "*.hulu.com", "*.disney.com"],
      "priority": 100,
      "created_at": "2026-02-26T10:00:00Z"
    }
  ]
}
```

## Prometheus Metrics

Squawk integration exposes metrics for monitoring DNS activity:

```prometheus
# Query count by result type
tobogganing_dns_queries_total{
  type="A",
  result="success",
  tenant_id="tenant-123"
} 15234

# Query latency (seconds)
tobogganing_dns_query_duration_seconds{
  operation="resolve",
  quantile="0.95"
} 0.045

# Blocked queries by reason
tobogganing_dns_blocked_total{
  reason="blocklist",
  tenant_id="tenant-123"
} 3456

# Cache performance
tobogganing_dns_cache_hits_total{
  tenant_id="tenant-123"
} 8900

tobogganing_dns_cache_misses_total{
  tenant_id="tenant-123"
} 1234
```

### Grafana Dashboard

Include these queries in monitoring dashboards:

```promql
# DNS query rate (per second)
rate(tobogganing_dns_queries_total[5m])

# Cache hit ratio
rate(tobogganing_dns_cache_hits_total[5m]) /
(rate(tobogganing_dns_cache_hits_total[5m]) + rate(tobogganing_dns_cache_misses_total[5m]))

# Block rate
rate(tobogganing_dns_blocked_total[5m]) / rate(tobogganing_dns_queries_total[5m])

# P95 query latency
histogram_quantile(0.95, tobogganing_dns_query_duration_seconds)
```

## NTP Time Synchronization

**Important**: Squawk DoH relies on accurate system time. When Squawk is enabled:

- **Use Squawk's time APIs**: Tobogganing queries Squawk's `/time` endpoint (if available)
- **Fallback to host NTP**: If Squawk unavailable, use system NTP
- **Sync interval**: Check time sync every 1 hour
- **Time skew detection**: Warn if system time differs from Squawk time by >30 seconds

Configuration:

```yaml
# hub-router
dns:
  time_sync:
    enabled: true
    squawk_time_endpoint: "https://dns.penguintech.io/time"
    check_interval: "1h"
    max_skew_tolerance: "30s"
    ntp_servers:
      - "time.cloudflare.com"
      - "time.google.com"
```

## Troubleshooting

### DNS Queries Not Reaching Squawk

**Symptom**: Clients can't resolve domains

**Check**:
1. Verify DNS listener is active: `netstat -tuln | grep :53`
2. Check hub-router logs: `docker logs hub-router | grep dns`
3. Verify Squawk endpoint reachability: `curl -v https://dns.penguintech.io/dns-query`
4. Check firewall allows egress HTTPS (port 443)

**Fix**:
```bash
# Manually test DNS forwarding
nslookup google.com 127.0.0.1

# Check hub-router DNS module status
curl http://localhost:8080/health | jq '.components.dns'
```

### High DNS Query Latency

**Symptom**: Slow page loads, DNS timeouts

**Check**:
1. Monitor query duration: `tobogganing_dns_query_duration_seconds`
2. Check Squawk DoH server health: `https://dns.penguintech.io/health`
3. Verify network latency to Squawk
4. Monitor cache hit ratio

**Fix**:
```bash
# Increase cache TTL (but respect domain TTL)
HUB_ROUTER_DNS_CACHE_TTL=7200

# Enable query pipelining for parallel requests
HUB_ROUTER_DNS_PIPELINE_DEPTH=16
```

### Policy-Blocked Domains Not Working

**Symptom**: Blocked domains still resolve

**Check**:
1. Verify policy rule is active: `GET /api/v1/policies/dns`
2. Check policy scope matches client scope: `scope: "both"` or `scope: "wireguard"`
3. Verify tenant/team assignment
4. Check blocklist enforcement enabled: `HUB_ROUTER_DNS_BLOCKLIST_ENFORCEMENT=true`

**Fix**:
```bash
# Reload policies
curl -X POST http://localhost:8080/admin/reload-policies

# Force policy refresh on client
tobogganing-client config reload
```

### Squawk Server Unavailable

**Symptom**: DNS fails when Squawk is down

**Fix**:
1. Fallback upstream should be configured
2. Check fallback DNS is reachable: `nslookup google.com 1.1.1.1`
3. Verify fallback is enabled: `HUB_ROUTER_DNS_FALLBACK_UPSTREAM=1.1.1.1:53`

## Security Considerations

1. **DoH Transport**: All queries encrypted end-to-end with Squawk
2. **Policy Enforcement**: DNS filtering applied before query leaves hub-router
3. **Blocklist Updates**: Fetched periodically from Squawk, cached locally
4. **Logging**: Query metadata logged for audit trails (not query content)
5. **Privacy**: Client IPs masked when forwarding to upstream resolvers

## Performance Impact

- **Query latency**: +5-15ms per query (network + crypto overhead)
- **Memory usage**: ~50MB per 100K cached records
- **CPU usage**: Minimal (<5% single core for 1000 QPS)
- **Network**: ~50 bytes per query to Squawk

## Related Documentation

- [Policy Rules](./ARCHITECTURE.md#policy-rules)
- [Hub-Router Configuration](./DEPLOYMENT.md#hub-router)
- [Network Architecture](./ARCHITECTURE.md#unified-networking)

