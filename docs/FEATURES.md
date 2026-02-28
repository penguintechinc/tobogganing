# 🚀 Tobogganing Features Documentation

> **Last Updated**: 2026-02-26
> **Version**: 0.3.0

## 📋 Table of Contents

- [🔒 Security Features](#-security-features)
- [🌐 Network Features](#-network-features)
- [🖥️ Client Applications](#️-client-applications)
- [💼 Management Features](#-management-features)
- [📊 Analytics & Monitoring](#-analytics--monitoring)
- [🚀 Deployment Features](#-deployment-features)
- [🔧 Configuration](#-configuration)
- [🔌 Platform Integrations](#-platform-integrations)

---

## 🔒 Security Features

### ✅ Input Validation (v0.3.0+)

**Comprehensive input validation** on all API endpoints using Pydantic 2.x schemas:

#### Backend Validation
- **Pydantic BaseModel schemas** for all POST/PUT/PATCH endpoints
- **Structured error responses** (HTTP 422) with field-level validation details
- **Custom validators**: IsCIDR, IsPortRange, IsProtocol, IsEmail
- **PyDAL integration**: Runtime validators on database layer
- **Automatic OpenAPI docs** with schema validation

#### Frontend Validation
- **Zod schemas** mirroring backend validation
- **Real-time field validation** with user feedback
- **Type-safe form handling** with TypeScript
- **Client-side pre-validation** before API submission

#### Example: Create Policy Rule
```python
# Backend (Pydantic schema)
class CreatePolicyRule(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    protocol: Literal["tcp", "udp", "icmp", "dns"]
    src_cidrs: List[str] = Field(..., min_items=1)
    dst_port_ranges: Optional[List[str]] = None  # Validated as port ranges
    action: Literal["allow", "block", "log"]

    @field_validator('src_cidrs')
    @classmethod
    def validate_cidrs(cls, v):
        for cidr in v:
            if not IsCIDR(cidr):
                raise ValueError(f"Invalid CIDR: {cidr}")
        return v

# Frontend (Zod schema)
const CreatePolicyRuleSchema = z.object({
    name: z.string().min(1).max(255),
    protocol: z.enum(["tcp", "udp", "icmp", "dns"]),
    src_cidrs: z.array(z.string()).min(1),
    action: z.enum(["allow", "block", "log"])
});
```

### 🛡️ Advanced Firewall System

The firewall system provides granular access control with multiple rule types:

#### Supported Rule Types

| Rule Type | Description | Example |
|-----------|-------------|---------|
| **Domain Rules** | Wildcard and exact domain matching | `*.example.com`, `api.example.com` |
| **IP Address** | IPv4 and IPv6 filtering | `192.168.1.1`, `2001:db8::1` |
| **IP Range** | CIDR notation support | `10.0.0.0/8`, `192.168.0.0/16` |
| **Protocol Rules** | Advanced TCP/UDP/ICMP filtering | `tcp:*:*->192.168.1.1:80` |
| **URL Patterns** | Regular expression matching | `https://.*\.secure\.example\.com/api/.*` |

#### Configuration Example

```yaml
firewall:
  rules:
    - type: domain
      pattern: "*.internal.company.com"
      action: allow
      priority: 10
    
    - type: protocol_rule
      protocol: tcp
      dst_port: "22,80,443"
      src_ip: "10.0.0.0/8"
      action: allow
      priority: 20
```

### 🔐 Dual Authentication System

Every connection requires two levels of authentication:

1. **Network Layer**: X.509 certificate-based WireGuard authentication
2. **Application Layer**: JWT tokens or SSO integration (SAML2.0/OAuth2)

### 🚨 IDS/IPS Integration

**Suricata Integration Features:**
- Real-time threat detection with EVE JSON format
- Multiple mirror protocols: VXLAN, GRE, ERSPAN
- Zero-copy traffic mirroring for performance
- Configurable sample rates and filtering
- Automatic rule updates from ET Open ruleset

**Configuration:**
```bash
# Environment variables
TRAFFIC_MIRROR_ENABLED=true
TRAFFIC_MIRROR_DESTINATIONS=10.0.0.100:4789,10.0.0.101:4789
TRAFFIC_MIRROR_PROTOCOL=VXLAN
TRAFFIC_MIRROR_SURICATA_ENABLED=true
TRAFFIC_MIRROR_SURICATA_HOST=172.20.0.100
```

### 📝 Audit & Compliance

**Syslog Integration:**
- UDP syslog support for compliance logging
- User resource access tracking
- Connection audit trails
- Structured logging with metadata

**Database Backup System:**
- Local backup with compression and encryption
- S3-compatible storage (AWS S3, MinIO, GCS)
- Automated scheduling with cron expressions
- Checksum verification and metadata tracking
- Cross-region replication support

---

## 🌐 Network Features

### 🔀 VRF & OSPF Support

Enterprise-grade network segmentation using FRR (Free Range Routing):

#### VRF Configuration
```bash
vrf customer-a
  description Customer A Private Network
  rd 65000:100
  import rt 65000:100
  export rt 65000:100
  exit

router ospf vrf customer-a
  router-id 10.1.1.1
  network 10.1.0.0/16 area 0.0.0.0
  network 192.168.100.0/24 area 0.0.0.1
  exit
```

#### Supported OSPF Area Types
- **Backbone (Area 0)**: Central routing hub
- **Stub Areas**: Branch offices with single uplink
- **NSSA**: Stub areas with limited external connectivity
- **Normal Areas**: Standard OSPF areas

### 🔌 Dynamic Port Configuration

Administrators can configure proxy listening ports through the web interface:

- **TCP Port Ranges**: Configure multiple TCP port ranges
- **UDP Port Ranges**: Configure multiple UDP port ranges
- **Real-time Updates**: Changes applied without restart
- **Web UI Management**: Beautiful interface for port configuration

### 🔐 Default-Deny Network Policies (v0.3.0+)

**Zero-trust network policies** for Kubernetes deployments:

#### Helm Deployment
```yaml
# deploy/kubernetes/networkpolicy-default-deny.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: tobogganing
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
---
# Explicit allowlist
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-tobogganing-services
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    # Allow hub-api to hub-router communication
    - from:
        - podSelector:
            matchLabels:
              app: hub-router
      ports:
        - protocol: TCP
          port: 8080
    # Allow Squawk DNS (if enabled)
    - from:
        - podSelector:
            matchLabels:
              app: squawk
      ports:
        - protocol: UDP
          port: 53
    # Allow WaddlePerf probes (if enabled)
    - from:
        - podSelector:
            matchLabels:
              app: waddleperf
      ports:
        - protocol: TCP
          port: 443
```

#### Kustomize Configuration
```bash
# deploy/kubernetes/base/
# kustomization.yaml references:
#   - networkpolicy-default-deny.yaml
#   - networkpolicy-allow.yaml (explicit allowlist)
```

---

## 🖥️ Client Applications

> **End-user desktop and mobile clients** have been migrated to [penguintechinc/penguin](https://github.com/penguintechinc/penguin) — a unified modular client with Flutter (iOS/Android) and Go (desktop). See that repo for end-user installation instructions.

The native Go client in this repo (`clients/native/`) is scoped to **server and infrastructure use** — connecting hardware, VMs, bare metal servers, containers, and embedded/IoT devices to the Tobogganing cluster.

### 🖥️ **Server/Infrastructure Client**
**Headless Go client for connecting servers, VMs, and embedded devices to the cluster**

#### Supported Platforms
| Platform | Binary Name | Use Case |
|----------|-------------|----------|
| **Linux AMD64** | `tobogganing-client-linux-amd64` | Servers, VMs, cloud instances |
| **Linux ARM64** | `tobogganing-client-linux-arm64` | ARM servers, Raspberry Pi 4/5 |
| **Linux ARMv7** | `tobogganing-client-linux-armv7` | Raspberry Pi, embedded gateways |
| **Linux ARMv6** | `tobogganing-client-linux-armv6` | Raspberry Pi Zero/1, constrained devices |
| **Linux MIPS** | `tobogganing-client-linux-mips` | Router firmware, network appliances |
| **Linux MIPSLE** | `tobogganing-client-linux-mipsle` | Little-endian MIPS devices |

#### Features
- **Daemon Mode** — Background operation for unattended servers
- **Dual-Mode Overlay** — WireGuard (L3 kernel) + OpenZiti (L7 dark services) simultaneously
- **Systemd Integration** — Native service management
- **Docker/Container Ready** — No GUI dependencies, minimal footprint
- **Automation Friendly** — CLI-driven, scriptable, CI/CD compatible
- **Embedded Platform Support** — ARM, MIPS, IoT devices
- **Auto-Configuration** — Certificate rotation and config updates from hub-api
- **System Attestation** — Hardware fingerprinting with TPM 2.0, cloud instance identity, and drift detection for infrastructure trust verification

#### Installation & Usage
```bash
# Quick install
curl -sSL https://github.com/penguintechinc/tobogganing/releases/latest/download/install-headless.sh | bash

# Connect as daemon
./tobogganing-client connect --daemon

# Check status
./tobogganing-client status
```

### 🐳 **Docker Container Client**

**Enterprise-ready containerized deployment**

```bash
# Official Docker image
docker run -d \
  --name tobogganing-client \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -e MANAGER_URL=https://manager.example.com \
  -e API_KEY=your-api-key \
  ghcr.io/penguintechinc/tobogganing-client:latest
```

**Container Features:**
- ✅ **Multi-Architecture** - ARM64 and AMD64 support
- ✅ **Health Checks** - Kubernetes-compatible health monitoring
- ✅ **Auto-Configuration** - Pulls config from manager automatically
- ✅ **Certificate Management** - Automatic rotation and renewal
- ✅ **Resource Efficient** - Minimal container footprint

### 📱 **Mobile Applications**

> Mobile clients (iOS and Android) have been migrated to the unified modular client at [penguintechinc/penguin](https://github.com/penguintechinc/penguin) using Flutter, replacing the previous React Native implementation. See that repo for mobile build and installation instructions.

### 🔧 **Client Configuration**

#### Universal Configuration
```yaml
# ~/.tobogganing/config.yaml
manager:
  url: "https://manager.example.com:8000"
  api_key: "your-api-key"
  timeout: "30s"

client:
  log_level: "info"
  auto_connect: true
  auto_update: true
  update_interval: "1h"
  system_tray: true  # GUI builds only

wireguard:
  interface: "wg-tobogganing"
  dns: ["1.1.1.1", "8.8.8.8"]
  mtu: 1420
```

#### Environment Variables
```bash
# Core configuration
export SASEWADDLE_MANAGER_URL="https://manager.example.com:8000"
export SASEWADDLE_API_KEY="your-api-key"
export SASEWADDLE_LOG_LEVEL="info"

# GUI-specific (GUI builds only)
export SASEWADDLE_SYSTEM_TRAY="true"
export SASEWADDLE_AUTO_UPDATE="true"

# Headless-specific
export SASEWADDLE_DAEMON_MODE="true"
export SASEWADDLE_PID_FILE="/var/run/tobogganing.pid"
```

---

## 💼 Management Features

### 🖥️ Web Management Portal

**py4web-based interface with comprehensive features:**

#### Role-Based Access Control
| Role | Permissions |
|------|------------|
| **Admin** | Full system access, user management, configuration |
| **Reporter** | Read-only access, view reports, analytics |
| **User** | Basic access, own profile management |

#### Dashboard Features
- Real-time connection statistics
- System health monitoring
- Active user tracking
- Traffic analytics with Chart.js visualizations
- Alert management

### 👥 User Management

- **User Creation & Management**: Admin-controlled user lifecycle
- **Role Assignment**: Granular permission management
- **Session Management**: Secure session handling with Redis
- **Password Policies**: bcrypt hashing, complexity requirements
- **2FA Support**: Optional two-factor authentication

### 🗄️ Database Architecture

**PyDAL with Multi-Database Support:**

```python
# MySQL Configuration (Default)
DB_TYPE=mysql
DB_HOST=mysql.example.com
DB_PORT=3306
DB_USER=tobogganing
DB_PASSWORD=secure_password
DB_NAME=tobogganing_production

# Read Replica Support
DB_READ_REPLICA_ENABLED=true
DB_READ_HOST=mysql-read.example.com
DB_READ_PORT=3306

# TLS/SSL Support
DB_TLS_ENABLED=true
DB_TLS_CA_CERT=/certs/ca.pem
DB_TLS_VERIFY_MODE=VERIFY_CA
```

**Supported Databases:**
- MySQL 8.0+ (recommended for production)
- PostgreSQL 13+
- SQLite (development only)

---

## 📊 Analytics & Monitoring

### 📈 Real-Time Analytics Dashboard

**Comprehensive metrics and visualizations:**

- **Operating System Distribution**: Track client OS versions
- **Traffic Monitoring**: Real-time bandwidth and connection metrics
- **Geographic Distribution**: Client location mapping
- **Performance Metrics**: CPU, memory, disk usage tracking
- **Historical Data**: Hourly and daily aggregations
- **Custom Reports**: Export capabilities for compliance

### 🔍 Prometheus Metrics

**Authenticated metrics endpoints with comprehensive telemetry:**

```prometheus
# Connection metrics
tobogganing_connections_total{type="wireguard", status="active"}
tobogganing_bandwidth_bytes{direction="ingress", protocol="tcp"}
tobogganing_auth_attempts_total{result="success", method="jwt"}

# System metrics
tobogganing_cpu_usage_percent{component="headend"}
tobogganing_memory_usage_bytes{component="manager"}
tobogganing_disk_usage_percent{path="/data"}

# Business metrics
tobogganing_users_total{role="admin"}
tobogganing_certificates_issued_total{type="client"}
tobogganing_firewall_rules_evaluated_total{action="allow"}
```

### 🏥 Health Monitoring

**Kubernetes-compatible health checks:**

- `/health`: Detailed health information with component status
- `/healthz`: Simple health check for load balancers
- Component-level health monitoring
- Dependency checking (database, Redis, etc.)

---

## 🚀 Deployment Features

### 🐳 Multi-Architecture Support

**Docker Images:**
- ARM64 and AMD64 support
- Multi-stage builds for security
- Minimal base images (Alpine Linux)
- Automated vulnerability scanning

**Native Binaries:**
- Windows (amd64)
- macOS (Universal Binary: Intel + Apple Silicon)
- Linux (amd64, arm64, armv7, armv6)
- Embedded platforms (MIPS, MIPSLE)

### 🔄 CI/CD Pipeline

**Complete GitHub Actions workflows:**

1. **Testing Pipeline**
   - Python linting (Black, Pylint, MyPy)
   - Go linting (golangci-lint)
   - Unit and integration tests
   - Security scanning (Trivy)

2. **Build Pipeline**
   - Multi-architecture Docker builds
   - Cross-platform Go compilation
   - Universal Binary creation for macOS
   - Automated releases with checksums

3. **Deployment Pipeline**
   - Kubernetes manifests
   - Terraform modules
   - Docker Compose configurations

---

## 🔧 Configuration

### 📝 Environment Variables

**Core Configuration:**
```bash
# Manager Service
MANAGER_API_URL=https://manager.example.com:8000
JWT_SECRET=your-secret-key
SESSION_TIMEOUT_HOURS=8
METRICS_TOKEN=prometheus-token

# Headend Service
HEADEND_URL=https://headend.example.com:8443
HEADEND_AUTH_TYPE=jwt
HEADEND_LOG_LEVEL=info
HEADEND_MIRROR_ENABLED=true

# Client Configuration
API_KEY=temporary-api-key
AUTO_UPDATE=true
SYSTEM_TRAY_ENABLED=true
```

### 🎯 Configuration Management

**Centralized configuration with:**
- Environment variable support
- Configuration file templates
- Secret management integration
- Dynamic configuration updates
- Configuration validation

---

## 🔌 Platform Integrations

### DNS-Over-HTTPS with Squawk (v0.3.0+)

**PenguinTech's Squawk DNS proxy integration** for secure, policy-driven DNS:

#### Features
- ✅ **DNS-over-HTTPS (DoH)**: RFC 8484 encrypted DNS queries
- ✅ **Policy-based filtering**: Block/allow domains per tenant/team
- ✅ **Local DNS listener**: 127.0.0.1:53 on clients and hub-router
- ✅ **Fallback upstream**: Graceful degradation if Squawk unavailable
- ✅ **Query caching**: Configurable TTL-aware caching
- ✅ **Prometheus metrics**: Query count, duration, blocked queries

#### Configuration
```bash
# Hub-router
HUB_ROUTER_DNS_ENABLED=true
HUB_ROUTER_DNS_SQUAWK_SERVER=https://dns.penguintech.io/dns-query

# Docker client
docker run -e SQUAWK_ENABLED=true ghcr.io/penguintechinc/tobogganing-client

# Native client
squawk_enabled: true
squawk_server_url: "https://dns.penguintech.io/dns-query"
```

#### Metrics
```prometheus
tobogganing_dns_queries_total{type="A", result="success"}
tobogganing_dns_query_duration_seconds{operation="resolve"}
tobogganing_dns_blocked_total{reason="blocklist"}
tobogganing_dns_cache_hits_total
```

See [Squawk Integration Guide](./SQUAWK_INTEGRATION.md) for comprehensive documentation.

---

### Network Fabric Monitoring with WaddlePerf (v0.3.0+)

**PenguinTech's WaddlePerf** for cluster-to-cluster latency and performance monitoring:

#### Features
- ✅ **Multi-protocol probes**: HTTP, TCP, UDP, ICMP
- ✅ **Fabric metrics**: Latency, jitter, packet loss, throughput
- ✅ **Inter-cluster monitoring**: Hub-to-hub performance tracking
- ✅ **WebUI dashboard**: /metrics/fabric with latency matrices
- ✅ **Prometheus metrics**: Real-time performance telemetry
- ✅ **Alert thresholds**: Configurable latency/jitter/packet-loss alerts

#### Configuration
```yaml
# Hub-router
perf:
  enabled: true
  interval: "30s"
  targets:
    - name: "headend-us-east"
      address: "headend-us-east.example.com:443"
      protocols: ["http", "tcp", "udp"]
  alert_latency_ms: 100
  alert_packet_loss_pct: 1.0
```

#### Metrics
```prometheus
tobogganing_fabric_latency_ms{source="hub-router", target="headend", protocol="http"}
tobogganing_fabric_jitter_ms{source="hub-router", target="headend"}
tobogganing_fabric_packet_loss_pct{source="hub-router", target="headend"}
tobogganing_fabric_throughput_mbps{protocol="tcp"}
tobogganing_fabric_probe_success_ratio
```

See [WaddlePerf Integration Guide](./WADDLEPERF_INTEGRATION.md) for comprehensive documentation.

---

### Zero-Trust Overlay with OpenZiti (v0.3.0+)

**Config-driven OpenZiti overlay** for L7 dark-service zero-trust networking alongside WireGuard:

#### Features
- ✅ **L7 Dark Services**: OpenZiti operates at L7 via `edge.Listener.Accept()`, not L3 packets
- ✅ **Config-Driven Selection**: Same binary, runtime switch via `overlay.type` — no build tags
- ✅ **Dual-Mode Default**: Client runs WireGuard (L3 kernel) + OpenZiti (L7 userspace) simultaneously
- ✅ **JWT+HOST Handshake**: Client sends `JWT:<token>\nHOST:<target>\n` on OpenZiti connections
- ✅ **OverlayScope Policy**: 7th policy dimension — rules target `wireguard`, `openziti`, or `both`
- ✅ **Identity-File Auth**: OpenZiti identity JSON contains controller URL + credentials

#### Configuration
```yaml
# Hub-router config
overlay:
  type: openziti           # "wireguard" (default) or "openziti"
  openziti:
    identity_file: /etc/tobogganing/ziti-identity.json
    service_name: tobogganing-headend

# Client config (default: "dual")
overlay_type: dual         # "wireguard", "openziti", or "dual"
openziti:
  identity_file: ~/.tobogganing/ziti-identity.json
  service_name: tobogganing-headend
```

#### Overlay Architecture
```
Hub-Router OverlayManager
├── WireGuardProvider (always active)
│   ├── Listener() → nil (kernel handles L3)
│   └── existing HTTP/TCP/UDP proxies serve WG traffic
└── OpenZitiProvider (when overlay.type = "openziti")
    ├── Listener() → edge.Listener (L7 dark service)
    └── serveZitiConnections() → JWT handshake → policy → proxy

Client OverlayProvider
├── WireGuardProvider: Dial() → nil (kernel tunnel routes traffic)
├── OpenZitiProvider: Dial() → zitiCtx.Dial() + JWT+HOST handshake
└── DualProvider (default): both active, Ziti preferred for Dial()
```

See [OpenZiti Integration Guide](./OPENZITI_INTEGRATION.md) for comprehensive documentation.

---

### XDP/eBPF Edge Protection (v0.3.0+)

**Kernel-level packet filtering** for bare-metal and VM hub-router deployments:

#### Features
- ✅ **Per-Source-IP Rate Limiting**: Token bucket in BPF hash map, configurable from Go
- ✅ **SYN Flood Protection**: Track SYN packets per source IP, drop above threshold
- ✅ **UDP Flood Protection**: Rate limit UDP per source IP (protects WireGuard port)
- ✅ **IP Blocklist**: Policy-engine deny rules pushed to BPF map for kernel-level drops
- ✅ **AF_XDP Zero-Copy**: NIC → userspace bypassing kernel network stack
- ✅ **NUMA-Aware Pools**: Buffer allocation pinned to NIC-local NUMA node
- ✅ **Build-Tag Gated**: `go build -tags xdp` enables BPF; default build uses no-op stubs

#### When to Use XDP

| Deployment Model | XDP Needed? | Why |
|---|---|---|
| In-cluster (Cilium CNI) | No | Cilium provides equivalent eBPF protection |
| Bare Metal / VMs | **Yes** | No CNI for kernel-level filtering |
| Spoke K8s (basic CNI) | Depends | Yes if CNI lacks eBPF support |

#### Configuration
```yaml
xdp:
  enabled: true
  interface: eth0
  rate_limit_pps: 10000
  syn_rate_limit_pps: 1000
  udp_rate_limit_pps: 5000
```

#### Metrics
```prometheus
tobogganing_xdp_packets_total{action="pass|drop|ratelimit"}
tobogganing_xdp_syn_flood_drops_total
tobogganing_xdp_udp_flood_drops_total
tobogganing_xdp_blocklist_size
```

See [XDP Guide](./XDP_GUIDE.md) | [Hub-Router Deployment](./HUB_ROUTER_DEPLOYMENT.md) for comprehensive documentation.

---

### Resource Sizing Guide (v0.3.0+)

**Comprehensive capacity planning** for Tobogganing deployments:

See [Resource Sizing Guide](./RESOURCE_SIZING.md) for:
- CPU and memory requirements by component
- Bandwidth calculations
- Scaling guidance (10, 100, 1000 client deployments)
- Kubernetes resource requests and limits
- Database sizing recommendations

---

### System Attestation (v0.3.0+)

**Hardware-rooted trust verification** for infrastructure clients (servers, VMs, bare metal):

#### Confidence Scoring

| Signal | Weight | Source |
|--------|--------|--------|
| TPM 2.0 PCR Quote | 40 | /dev/tpmrm0 |
| Cloud Instance Identity | 35 | IMDS (AWS/GCP/Azure) |
| DMI product_uuid | 10 | /sys/class/dmi/id/ |
| DMI board_serial | 8 | /sys/class/dmi/id/ |
| FleetDM Cross-Reference | 7 | FleetDM API (optional) |
| Network MAC Addresses | 5 | net.Interfaces() |
| Disk Serials | 4 | /sys/block/*/device/serial |
| DMI vendor + product | 3 | /sys/class/dmi/id/ |
| CPU model + count | 3 | /proc/cpuinfo |

**Confidence levels**: high (>=90), medium (>=60), low (>=30), minimal (<30)

#### Features
- **Composite Hash**: SHA-256 of stable hardware fields for identity binding
- **TPM Support**: Optional PCR quote with challenge-response nonce (build-tag gated: `-tags tpm`)
- **Cloud Auto-Detection**: AWS/GCP/Azure instance identity via IMDS
- **FleetDM Integration**: Optional server-side cross-reference with FleetDM/osquery data
- **Drift Detection**: Token refresh compares fingerprints; rejects on critical field changes (product_uuid)
- **JWT Claims**: Attestation confidence embedded in access tokens (`attest_conf`, `attest_method`)

See [Attestation Guide](./ATTESTATION.md) for comprehensive documentation.

---

## 📚 Additional Resources

- [Architecture Guide](./ARCHITECTURE.md)
- [Quick Start Guide](./QUICKSTART.md)
- [API Documentation](./API.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)
- [Security Best Practices](./SECURITY.md)
- [Squawk Integration Guide](./SQUAWK_INTEGRATION.md)
- [WaddlePerf Integration Guide](./WADDLEPERF_INTEGRATION.md)
- [OpenZiti Integration Guide](./OPENZITI_INTEGRATION.md)
- [Resource Sizing Guide](./RESOURCE_SIZING.md)
- [XDP Guide](./XDP_GUIDE.md)
- [Hub-Router Deployment Models](./HUB_ROUTER_DEPLOYMENT.md)

---

*For the latest updates and feature announcements, visit our [GitHub repository](https://github.com/penguintechinc/tobogganing)*