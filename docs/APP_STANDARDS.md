# Tobogganing - Application-Specific Standards

## Project Overview

Tobogganing is a Secure Access Service Edge (SASE) platform implementing Zero Trust networking principles. It provides enterprise-grade network security through policy-driven access control, encrypted tunnels, and identity-aware traffic routing.

Previously known as SASEWaddle, the project was renamed to Tobogganing in v2.0.0 alongside a complete architectural overhaul from a monolithic design to a three-service hub model.

### Core Concept: Hub Model

Tobogganing operates on a **hub-centric architecture**. Each deployment consists of one or more hubs that act as secure gateways for client traffic. Clients connect to a minimum of two hubs for redundancy and failover. The hub-router enforces network policies received from the hub-api, while the hub-webui provides administrative visibility and control.

```
                    +------------------+
                    |   hub-webui      |
                    |   (React/Vite)   |
                    +--------+---------+
                             |
                             | REST/WebSocket
                             |
+-------------+     +--------+---------+     +------------------+
|  Client A   +---->|    hub-api       |<--->|   Database       |
|  Client B   |     |  (Quart/Python)  |     |  (PostgreSQL/    |
|  Client C   |     +--------+---------+     |   SQLite)        |
+------+------+              |               +------------------+
       |                     | gRPC (policy distribution)
       |                     |
       |            +--------+---------+
       +----------->|   hub-router     |
        WireGuard   |  (Go 1.24)       |
        tunnel      |  XDP data plane  |
                    +------------------+
```

## Three-Service Hub Architecture

### hub-api (Quart / Python 3.13)

The hub-api is the control plane and management service for the platform.

- **Framework**: Quart (async-native ASGI), deviating from the standard Flask choice
- **Runtime**: Python 3.13 with uvicorn and uvloop
- **Database**: PyDAL for multi-database support (PostgreSQL production, SQLite development)
- **Authentication**: JWT with bcrypt password hashing, certificate management via `cryptography`
- **Caching**: Redis for sessions, tokens, and policy distribution state
- **Metrics**: Prometheus client for observability
- **Async HTTP**: aiohttp and httpx for outbound service communication

**Quart Deviation from Flask Standard**: The project template specifies Flask as the standard Python web framework. Tobogganing uses Quart instead because the hub-api must handle long-lived gRPC streams for policy distribution to hub-routers, WebSocket connections for real-time client status updates, and concurrent certificate operations. Quart provides native async/await support on ASGI, making it the correct choice for these workload characteristics. Quart maintains API compatibility with Flask, so existing patterns and middleware largely carry over.

**Key Responsibilities:**
- User and group management with role-based access (Admin, Maintainer, Viewer)
- Policy CRUD operations and versioning
- Certificate lifecycle management (Root CA, Intermediate CA, client certificates)
- Hub registration and health monitoring
- License validation against PenguinTech License Server
- gRPC server for streaming policy updates to hub-routers
- Audit logging and compliance reporting
- Database backup and restore with S3 support

### hub-router (Go 1.24)

The hub-router is the data plane and policy enforcement point.

- **Language**: Go 1.24 with CGO enabled (required for XDP/AF_XDP)
- **Data Plane**: Dual-path architecture using XDP and AF_XDP
- **Policy Engine**: Receives policies from hub-api via gRPC
- **WireGuard**: Client tunnel termination via wgctrl
- **API**: Gin-based health and metrics endpoints
- **Monitoring**: Prometheus metrics, structured logging via logrus

**Key Responsibilities:**
- WireGuard tunnel termination for connected clients
- Packet filtering and routing based on active policies
- XDP fast path for high-throughput traffic
- AF_XDP slow path for complex inspection and Go userspace processing
- NUMA-aware memory pool management for packet buffers
- Health reporting to hub-api
- OIDC/OAuth2 integration for identity-aware routing

### hub-webui (React / Vite)

The hub-webui provides the administrative interface for the platform.

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite 5
- **Styling**: Tailwind CSS 4
- **Data Fetching**: TanStack React Query with Axios
- **Testing**: Vitest with React Testing Library
- **Routing**: React Router DOM v6

**Key Responsibilities:**
- Dashboard with real-time hub status and client connections
- Policy editor with domain, port, protocol, IP, and user/group dimensions
- User and group management interface
- Hub configuration and monitoring
- Certificate management UI
- Audit log viewer
- License status display

## Policy Engine

The policy engine is a core differentiator of Tobogganing. Policies define what traffic is allowed, denied, or inspected as it flows through hub-routers.

### Policy Dimensions

Policies are evaluated across multiple dimensions simultaneously:

| Dimension | Description | Examples |
|-----------|-------------|----------|
| **Domain** | FQDN or wildcard domain matching | `*.example.com`, `api.internal.corp` |
| **Ports** | TCP/UDP port ranges | `80`, `443`, `8000-9000` |
| **Protocols** | Layer 4 protocol matching | `tcp`, `udp`, `icmp` |
| **IP CIDR** | Source or destination IP ranges | `10.0.0.0/8`, `192.168.1.0/24` |
| **Users** | Individual user identity | `user@example.com` |
| **Groups** | Group membership | `engineering`, `contractors` |

### Policy Distribution

Policies are authored in the hub-api and distributed to hub-routers via gRPC streaming:

1. Admin creates or updates a policy via hub-webui or REST API
2. hub-api validates the policy and persists it to the database
3. hub-api pushes the updated policy set to all connected hub-routers via gRPC stream
4. hub-router compiles the policy into its internal evaluation engine
5. hub-router applies the policy to all subsequent packets

Policy updates are atomic and versioned. Hub-routers confirm receipt, enabling the hub-api to track policy consistency across the fleet.

## Identity Providers

Tobogganing supports multiple identity provider configurations, with some features gated behind licensing.

### Free Tier (Local Authentication)

- Local user database with bcrypt-hashed passwords
- JWT token issuance and validation
- Basic role-based access control (Admin, Maintainer, Viewer)
- API key authentication for client registration

### Premium Tier (License-Gated)

The following identity provider integrations require a valid PenguinTech license:

- **OIDC**: OpenID Connect integration for SSO (via `coreos/go-oidc` in hub-router)
- **SAML**: SAML 2.0 identity provider federation
- **SCIM**: System for Cross-domain Identity Management for user/group provisioning

License validation occurs at the hub-api level. When a premium IdP is configured, the hub-api checks the license status against the PenguinTech License Server before enabling the integration. If the license expires or is invalid, the system gracefully falls back to local authentication with appropriate warnings.

## XDP/AF_XDP Data Plane

The hub-router implements a dual-path data plane for high-performance packet processing.

### Fast Path: Kernel eBPF (XDP)

The XDP fast path runs as an eBPF program attached directly to the network interface. It handles simple allow/deny decisions entirely in kernel space without copying packets to userspace.

- **Source**: `services/hub-router/bpf/xdp_filter.c`
- **Loading**: Via `cilium/ebpf` Go library
- **Decisions**: Allow, drop, or redirect to AF_XDP for slow-path processing
- **Performance**: Line-rate packet processing with minimal CPU overhead

### Slow Path: Go Userspace (AF_XDP)

When packets require deeper inspection (identity-aware routing, application-layer policy, logging), the XDP program redirects them to an AF_XDP socket where the Go userspace processes them.

- **Implementation**: `services/hub-router/internal/dataplane/af_xdp.go`
- **Workers**: `services/hub-router/internal/dataplane/worker.go`
- **Coordination**: `services/hub-router/internal/dataplane/dataplane.go`
- **Use Cases**: OIDC token validation, complex policy evaluation, traffic mirroring, audit logging

### NUMA-Aware Memory Pools

For multi-socket servers, the hub-router allocates packet buffers from NUMA-local memory pools to minimize cross-socket memory access latency.

- **Implementation**: `services/hub-router/internal/dataplane/numa_pool.go`
- **Strategy**: One pool per NUMA node, workers pinned to cores on their respective NUMA nodes
- **Buffer Size**: Configurable, defaults to jumbo frame support (9000 bytes)

## gRPC Communication

Hub-api and hub-router communicate over gRPC for policy distribution and status reporting.

### Key RPCs

- `StreamPolicies`: Server-streaming RPC from hub-api to hub-router delivering policy updates
- `ReportStatus`: Unary RPC from hub-router to hub-api reporting health, connected clients, and resource utilization
- `SyncCertificates`: Bidirectional streaming for certificate distribution and rotation

### Connection Resilience

- Hub-routers maintain persistent gRPC connections with automatic reconnection
- Exponential backoff on connection failure (1s, 2s, 4s, 8s, max 30s)
- Policy cache on hub-router survives brief hub-api outages

## Multi-Hub Client Connections

Clients connect to a minimum of two hubs for redundancy. The client maintains WireGuard tunnels to each hub simultaneously.

### Failover Behavior

1. Client establishes tunnels to Hub A (primary) and Hub B (secondary)
2. Traffic routes through Hub A by default
3. If Hub A becomes unreachable, traffic automatically fails over to Hub B
4. When Hub A recovers, traffic gradually migrates back (configurable)

### Hub Selection

- Clients receive hub assignments from the hub-api during registration
- Assignment considers geographic proximity, hub load, and client group policies
- Hub list is refreshed periodically and on connection events

## Overlay Architecture

Tobogganing implements a flexible, multi-layer overlay network architecture supporting
both traditional L3 VPN (WireGuard) and emerging L7 dark services (OpenZiti).

### Overlay Types

#### WireGuard (Default, Production)

WireGuard is the primary overlay for all deployments:

- **Layer**: L3 VPN with kernel tun device
- **Hub-Router**: Listens on UDP port 51820, decrypts packets into userspace
- **Client**: Transparent routing via kernel tunnel, all traffic flows through
- **Performance**: Native kernel acceleration, minimal overhead
- **Failover**: Multi-hub support with automatic traffic switching

#### OpenZiti (Optional, Dark Services)

OpenZiti provides an alternative L7 overlay for advanced use cases:

- **Layer**: Application-level connections via userspace SDK
- **Hub-Router**: Accepts `edge.Listener` connections, reads `handleZitiConnection` handler
- **Client**: Uses `ziti.Context.Dial()` for explicit service access
- **Authentication**: App-level JWT handshake (SDK doesn't expose caller identity)
- **Use Case**: Dark services — network resources invisible to port scanners

### Dual-Mode Operation (Recommended)

Clients default to operating in **dual-mode** with both overlays active simultaneously:

1. **WireGuard** handles general L3 traffic (transparent routing)
2. **OpenZiti** provides L7 dark service access (explicit service connection)
3. **Failover**: If OpenZiti unavailable, WireGuard remains fully operational
4. **Policy Routing**: `scope` field in policies directs enforcement to specific overlays

**Architecture Diagram:**

```
Client (dual-mode)
├─ WireGuard (L3)
│  └─ Transparent routing → Hub-Router port 51820
│     └─ Policy enforcement (wireguard scope)
│
└─ OpenZiti (L7)
   └─ Explicit service dial → Hub-Router ziti listener
      └─ Policy enforcement (openziti scope)
```

### Policy Scope Dimension

Policies now include a `scope` dimension controlling which overlay(s) the rule applies to:

```python
# hub-api policy model
policy = {
    "name": "example",
    "scope": "wireguard",  # "wireguard" | "openziti" | "" (empty = all)
    # ... other dimensions (domains, ports, users, groups, cidrs)
}
```

**Scope Values:**
- `scope: "wireguard"` — Only enforce on WireGuard traffic
- `scope: "openziti"` — Only enforce on OpenZiti connections
- `scope: ""` (empty string) — Enforce on all traffic regardless of overlay

**Policy Evaluation Flow:**
```
1. Packet/Connection arrives at hub-router
2. Identify overlay: WireGuard packet → "wireguard" | OpenZiti connection → "openziti"
3. Evaluate policies:
   - Filter: scope == "" OR scope == identified_overlay
   - Evaluate remaining 5 dimensions (domains, ports, protocols, IPs, users/groups)
4. Action: allow/deny/inspect
```

## XDP Edge Protection

The hub-router implements optional XDP (eXpress Data Path) protection for deployments
where the container CNI cannot provide L3/L4 filtering.

### When XDP is Required

| Deployment | CNI | XDP Needed |
|------------|-----|-----------|
| Kubernetes + Cilium | eBPF-based | Optional (Cilium handles filtering) |
| Kubernetes + Flannel/Calico | Basic overlay | **Required** |
| Bare Metal / VMs | None | **Required** |
| Edge / Spoke deployments | Basic | **Required** |

### XDP Data Plane

Hub-router uses a dual-path data plane:

#### Fast Path: Kernel eBPF (XDP)

```
NIC → XDP program (xdp_ratelimit.c)
  ├─ Blocklist lookup (BPF hash map) → DROP
  ├─ SYN/UDP flood check (token bucket) → DROP
  ├─ Rate limit check → DROP or PASS
  └─ PASS: redirect to AF_XDP socket
```

**Features:**
- **IP Blocklist**: Instant drop from kernel, synced from hub-api
- **SYN Flood Protection**: Per-source-IP token buckets
- **UDP Flood Protection**: Per-source-IP rate limiting
- **Performance**: Line-rate processing, minimal CPU overhead

#### Slow Path: Go Userspace (AF_XDP)

Packets that pass XDP checks are delivered to userspace via AF_XDP sockets for:

- Complex policy evaluation (identity-aware routing, application-layer rules)
- Traffic mirroring to Suricata IDS
- Audit logging and compliance
- Certificate validation

### NUMA-Aware Memory Pools

Multi-socket servers receive automatic optimization:

```go
// Hub-router detects NUMA topology
for node := 0; node < numNUMANodes; node++ {
    pool := numa.NewBufferPool(node)      // Allocate on local node
    workers[node] = startWorkerOnNode(node)  // Pin threads
}
```

**Benefits:**
- Buffers allocated on same NUMA node as NIC
- Worker threads pinned to cores on respective nodes
- Minimizes cross-socket memory latency
- 10-20% performance improvement on dual-socket systems

### Build Configuration

XDP support is optional and gated by build tags:

```bash
# Default build (no XDP)
go build -o hub-router ./cmd/main.go
# All XDP operations are safe no-ops

# XDP-enabled build
go build -tags xdp -o hub-router ./cmd/main.go
# Requires: clang, libbpf headers, Linux kernel 5.10+
```

**Safety**: Even in default builds, setting `xdp.enabled: true` causes no crashes —
XDP initialization gracefully skips, and the hub-router continues normal operation.

### Configuration

```yaml
xdp:
  enabled: true
  interface: eth0
  rate_limit_pps: 10000
  syn_rate_limit_pps: 1000
  udp_rate_limit_pps: 5000
  blocklist_sync_url: http://hub-api:8080/api/v1/security/blocklist
```

### Kubernetes Integration

When `xdp.enabled: true`, the Helm chart automatically:
- Adds `CAP_BPF` and `CAP_SYS_ADMIN` capabilities
- Mounts `/sys/fs/bpf` (BPF filesystem) for kernel program storage
- Sets `hostNetwork: false` (Cilium manages pod networking)

See `k8s/helm/tobogganing/values.yaml` for Helm configuration.

## Cilium Integration

For Kubernetes deployments, Tobogganing integrates with Cilium as the CNI plugin rather than maintaining a custom CNI implementation.

### Why Cilium

- Mature eBPF-based networking with extensive community support
- Native network policy enforcement that complements Tobogganing policies
- Built-in observability via Hubble
- Replaces the previous custom `k8s-cni` component from v1.x

### Integration Points

- Tobogganing hub-router pods use Cilium for pod-to-pod networking
- Cilium network policies protect the hub-api and hub-router management interfaces
- Hubble provides visibility into inter-service traffic for debugging
- Cilium's WireGuard mode can optionally encrypt intra-cluster traffic

## Container Base Images

All three services use Debian bookworm-based container images:

| Service | Base Image | Rationale |
|---------|-----------|-----------|
| hub-api | `python:3.13-slim-bookworm` | Stable Python runtime with minimal footprint |
| hub-router | `golang:1.24-bookworm` (build) / `debian:bookworm-slim` (runtime) | CGO required for XDP; multi-stage build |
| hub-webui | `node:22-bookworm` (build) / `nginx:stable` (runtime) | Static asset serving via nginx |

The migration from Alpine to Debian bookworm was driven by CGO compatibility requirements for the hub-router's XDP/AF_XDP functionality and the desire for consistency across all services.

## Development Conventions

### API Versioning

All hub-api REST endpoints are prefixed with `/api/v1/`. Breaking changes require a version bump.

### Configuration

- Environment variables for runtime configuration (12-factor app)
- `.env` files for local development (never committed)
- Viper for Go configuration management in hub-router
- python-dotenv for Python configuration in hub-api

### Logging

- Structured JSON logging across all services
- `structlog` for hub-api
- `logrus` for hub-router
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Error Handling

- hub-api returns RFC 7807 problem detail responses
- hub-router returns gRPC status codes for RPC errors
- hub-webui displays user-friendly error messages with retry options

## Technology Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Python web framework | Quart over Flask | Async-native ASGI required for gRPC streams and WebSockets |
| Go data plane | XDP/AF_XDP over pure Go | Line-rate performance for simple filtering decisions |
| Container base | Debian bookworm over Alpine | CGO compatibility for eBPF libraries |
| Kubernetes CNI | Cilium over custom | Mature eBPF-based CNI; reduces maintenance burden |
| Frontend framework | React/Vite over Next.js | SPA sufficient for admin UI; no SSR needed |
| Database abstraction | PyDAL | Multi-database support matching template standard |
| gRPC over REST | gRPC for inter-service | Streaming support, binary protocol, schema enforcement |
| Identity protocols | OIDC/SAML/SCIM | Industry standard; premium features for revenue |
