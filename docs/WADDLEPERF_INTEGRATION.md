# WaddlePerf Fabric Metrics Integration Guide

## Overview

**WaddlePerf** is PenguinTech's network performance testing and monitoring service. This guide covers how WaddlePerf integrates with Tobogganing to monitor fabric performance, measure cluster-to-cluster latency, and track end-to-end network health.

## What is WaddlePerf?

WaddlePerf provides:
- Multi-protocol network performance probes (HTTP, TCP, UDP, ICMP)
- Latency, jitter, and packet loss measurement
- Client-to-cluster and cluster-to-cluster fabric metrics
- Real-time dashboards and historical analytics
- Automated alert thresholds for network degradation

## Integration Architecture

WaddlePerf integrates at three levels:

```
┌──────────────────────┐
│   WaddlePerf Agent   │
│  (Hub-Router, Client)│
└──────────┬───────────┘
           │ Metrics collection
           ▼
┌──────────────────────┐
│   FabricMonitor      │
│  (Hub-Router)        │
└──────────┬───────────┘
           │ Performance data
           ▼
┌──────────────────────┐
│   Hub-API Storage    │
│  (Metrics DB)        │
└──────────┬───────────┘
           │ Prometheus export
           ▼
┌──────────────────────┐
│   WebUI Metrics Page │
│  (/metrics/fabric)   │
└──────────────────────┘
```

## Configuration

### Hub-Router Configuration

Enable fabric monitoring on hub-router:

```yaml
# deploy/kubernetes/values-hub-router.yaml
perf:
  enabled: true
  interval: "30s"
  # Target headends/clusters to probe
  targets:
    - name: "headend-us-east"
      address: "headend-us-east.example.com:443"
      protocols: ["http", "tcp", "udp"]
    - name: "headend-eu-west"
      address: "headend-eu-west.example.com:443"
      protocols: ["http", "tcp", "udp"]
  # Probe configuration
  http_timeout: "5s"
  tcp_timeout: "5s"
  udp_timeout: "5s"
  icmp_timeout: "5s"
  # Alert thresholds
  alert_latency_ms: 100
  alert_jitter_ms: 10
  alert_packet_loss_pct: 1.0
```

Environment variables:

```bash
# Enable fabric monitoring
HUB_ROUTER_PERF_ENABLED=true

# Probe interval
HUB_ROUTER_PERF_INTERVAL=30s

# Probe targets (comma-separated)
HUB_ROUTER_PERF_TARGETS=headend-us-east.example.com:443,headend-eu-west.example.com:443

# Protocol list
HUB_ROUTER_PERF_PROTOCOLS=http,tcp,udp,icmp

# Timeouts
HUB_ROUTER_PERF_HTTP_TIMEOUT=5s
HUB_ROUTER_PERF_TCP_TIMEOUT=5s
HUB_ROUTER_PERF_UDP_TIMEOUT=5s

# Alert thresholds
HUB_ROUTER_PERF_ALERT_LATENCY_MS=100
HUB_ROUTER_PERF_ALERT_JITTER_MS=10
HUB_ROUTER_PERF_ALERT_PACKET_LOSS_PCT=1.0
```

### Native Client Configuration

Enable performance monitoring on native clients:

```yaml
# ~/.tobogganing/config.yaml
perf_enabled: true
perf_interval: "60s"
# Report metrics back to hub-router
perf_upload_enabled: true
perf_upload_interval: "5m"
```

### Helm Configuration

Configure WaddlePerf in Kubernetes:

```yaml
# deploy/kubernetes/values.yaml
waddleperf:
  enabled: true
  # Include WaddlePerf as sub-chart (optional)
  subchart:
    enabled: false  # Use external WaddlePerf service
    # image: ghcr.io/penguintechinc/waddleperf:latest
    # replicas: 2

hub-router:
  perf:
    enabled: true
    interval: "30s"
    # List of target headends
    targets:
      - name: "headend-us-east"
        address: "headend-us-east.example.com:443"
      - name: "headend-eu-west"
        address: "headend-eu-west.example.com:443"
    # Alert thresholds
    alertLatencyMs: 100
    alertJitterMs: 10
    alertPacketLossPct: 1.0
    # Metrics export
    metricsPort: 8080
```

## Metrics Collection

### Collected Metrics

WaddlePerf collects the following metrics per target and protocol:

- **Latency (ms)**: Round-trip time from probe to target
- **Jitter (ms)**: Variance in latency (standard deviation)
- **Packet Loss (%)**: Percentage of packets that don't reach target
- **Throughput (Mbps)**: Data transmission rate (TCP/UDP only)
- **DNS Resolution Time (ms)**: Time to resolve target hostname
- **Connection Establishment Time (ms)**: Time to establish connection (TCP only)

### Prometheus Metrics

Hub-router exposes fabric metrics:

```prometheus
# Latency (milliseconds)
tobogganing_fabric_latency_ms{
  source="hub-router-us-east",
  target="headend-eu-west",
  protocol="http"
} 45.23

# Jitter (milliseconds)
tobogganing_fabric_jitter_ms{
  source="hub-router-us-east",
  target="headend-eu-west",
  protocol="http"
} 2.15

# Packet loss (percentage, 0-100)
tobogganing_fabric_packet_loss_pct{
  source="hub-router-us-east",
  target="headend-eu-west",
  protocol="icmp"
} 0.5

# Throughput (megabits per second)
tobogganing_fabric_throughput_mbps{
  source="hub-router-us-east",
  target="headend-eu-west",
  protocol="tcp"
} 950.5

# Probe success rate (0-1)
tobogganing_fabric_probe_success_ratio{
  source="hub-router-us-east",
  target="headend-eu-west",
  protocol="http"
} 0.98

# Total probes sent
tobogganing_fabric_probes_sent_total{
  source="hub-router-us-east",
  target="headend-eu-west",
  protocol="tcp"
} 1000

# Probes failed
tobogganing_fabric_probes_failed_total{
  source="hub-router-us-east",
  target="headend-eu-west",
  protocol="tcp"
} 20
```

## API Endpoints

### POST /api/v1/perf/metrics

Record performance metrics from client or probe:

```bash
curl -X POST http://localhost:8000/api/v1/perf/metrics \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "source": "client-uuid",
    "target": "headend-us-east",
    "protocol": "http",
    "latency_ms": 45.23,
    "jitter_ms": 2.15,
    "packet_loss_pct": 0.5,
    "throughput_mbps": 950.5,
    "timestamp": "2026-02-26T10:00:00Z"
  }'

# Response
{
  "status": "success",
  "data": {
    "id": "metric-uuid",
    "created_at": "2026-02-26T10:00:00Z"
  }
}
```

### GET /api/v1/perf/metrics

Query historical performance metrics:

```bash
# Get metrics for specific target and protocol
curl "http://localhost:8000/api/v1/perf/metrics?target=headend-us-east&protocol=http&limit=100" \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "status": "success",
  "data": [
    {
      "id": "metric-uuid",
      "source": "hub-router-us-east",
      "target": "headend-us-east",
      "protocol": "http",
      "latency_ms": 45.23,
      "jitter_ms": 2.15,
      "packet_loss_pct": 0.5,
      "throughput_mbps": 950.5,
      "timestamp": "2026-02-26T10:00:00Z"
    }
  ],
  "meta": {
    "total": 1000,
    "limit": 100,
    "offset": 0
  }
}
```

### GET /api/v1/perf/summary

Get aggregated performance summary:

```bash
curl "http://localhost:8000/api/v1/perf/summary?time_range=1h" \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "status": "success",
  "data": {
    "timestamp": "2026-02-26T10:00:00Z",
    "time_range": "1h",
    "targets": [
      {
        "name": "headend-us-east",
        "protocols": {
          "http": {
            "latency_avg_ms": 45.5,
            "latency_p95_ms": 52.3,
            "latency_p99_ms": 58.1,
            "jitter_avg_ms": 2.2,
            "packet_loss_avg_pct": 0.3,
            "throughput_avg_mbps": 948.5,
            "probe_count": 120,
            "success_count": 118
          }
        }
      }
    ]
  }
}
```

## WebUI Metrics Dashboard

The WebUI includes a comprehensive fabric metrics dashboard at `/metrics/fabric`:

### Latency Matrix

Visual grid showing inter-cluster latency:

```
┌────────────────────────────────────────────┐
│   From \ To      │  US-East  │  EU-West   │
├──────────────────┼──────────┼────────────┤
│  US-East         │    0ms   │   45ms     │
│  EU-West         │   47ms   │    0ms     │
└────────────────────────────────────────────┘
```

### Time-Series Graphs

Interactive charts showing:
- Latency trends over time
- Jitter patterns
- Packet loss events
- Throughput utilization

### Alert Thresholds

Visual indicators for:
- Latency > 100ms (yellow warning, red critical)
- Jitter > 10ms (yellow)
- Packet loss > 1% (red)

## Alert Configuration

Configure alert thresholds for network degradation:

```yaml
# prometheus/rules/tobogganing-perf.yaml
groups:
  - name: tobogganing.perf
    rules:
      - alert: HighFabricLatency
        expr: tobogganing_fabric_latency_ms > 100
        for: 5m
        annotations:
          summary: "High latency detected"
          description: "Latency from {{ $labels.source }} to {{ $labels.target }} is {{ $value }}ms"

      - alert: HighPacketLoss
        expr: tobogganing_fabric_packet_loss_pct > 1.0
        for: 5m
        annotations:
          summary: "Packet loss detected"
          description: "Packet loss from {{ $labels.source }} to {{ $labels.target }} is {{ $value }}%"

      - alert: HighJitter
        expr: tobogganing_fabric_jitter_ms > 10
        for: 5m
        annotations:
          summary: "High jitter detected"
          description: "Jitter from {{ $labels.source }} to {{ $labels.target }} is {{ $value }}ms"
```

## Protocols Tested

### HTTP/HTTPS

Probes TCP connection to target port 443, performs TLS handshake, measures HTTPS response time.

```bash
# Manual test
curl -w "time_total:%{time_total}\n" https://headend-us-east.example.com/health
```

### TCP

Establishes raw TCP connection to target port, measures connection time.

```bash
# Manual test
timeout 5 bash -c 'cat < /dev/null > /dev/tcp/headend-us-east.example.com/443'
echo $?  # 0 = success, 124 = timeout
```

### UDP

Sends UDP packets to target port, measures round-trip time.

```bash
# Manual test with netcat
echo "test" | timeout 5 nc -u headend-us-east.example.com 53
```

### ICMP

Sends ICMP echo requests (ping), measures latency and packet loss.

```bash
# Manual test
ping -c 10 headend-us-east.example.com
```

## Resource Overhead

WaddlePerf monitoring has minimal overhead:

- **CPU**: <5% of single core for probe interval 30s
- **Memory**: ~20MB per 100 targets
- **Network**: ~1KB per probe (varies by protocol)
- **Metrics storage**: ~300 bytes per metric point

Tuning for scale:

```yaml
# For high-scale deployments (>500 targets)
perf:
  interval: "60s"  # Increase probe interval
  max_concurrent_probes: 50  # Limit parallel probes
  metrics_retention_days: 7  # Retain 1 week of metrics
```

## Troubleshooting

### Metrics Not Appearing

**Symptom**: No fabric metrics in Prometheus

**Check**:
1. Verify hub-router perf module enabled: `HUB_ROUTER_PERF_ENABLED=true`
2. Check hub-router logs: `docker logs hub-router | grep perf`
3. Verify target reachability: `ping headend-us-east.example.com`
4. Check metrics endpoint: `curl http://localhost:8080/metrics | grep fabric`

**Fix**:
```bash
# Manually trigger probe
curl -X POST http://localhost:8080/admin/perf/probe \
  -H "Content-Type: application/json" \
  -d '{
    "target": "headend-us-east.example.com:443",
    "protocol": "http"
  }'
```

### High Latency Alerts

**Symptom**: Persistent latency > 100ms

**Investigate**:
1. Check inter-datacenter network latency independently
2. Monitor hub-router CPU/memory (may indicate resource contention)
3. Check WireGuard tunnel MTU (may cause fragmentation)
4. Verify no packet loss (may indicate congestion)

**Fix**:
```bash
# Increase alert threshold if baseline latency high
HUB_ROUTER_PERF_ALERT_LATENCY_MS=150

# Or optimize tunnel MTU
# Adjust WireGuard MTU to 1280 (smaller for high-latency links)
wireguard:
  mtu: 1280
```

### Packet Loss on UDP

**Symptom**: UDP probes show high packet loss

**Check**:
1. Verify UDP port 53 (DNS) is open to target
2. Check firewall rules allow UDP
3. Monitor network congestion

**Fix**:
```bash
# Disable UDP probes if not needed
HUB_ROUTER_PERF_PROTOCOLS=http,tcp,icmp

# Or add longer timeout for UDP
HUB_ROUTER_PERF_UDP_TIMEOUT=10s
```

## Related Documentation

- [Network Architecture](./ARCHITECTURE.md#unified-networking)
- [Monitoring & Observability](./DEPLOYMENT.md#monitoring)
- [Prometheus Configuration](./DEPLOYMENT.md#prometheus)

