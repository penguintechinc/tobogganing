# Tobogganing Release Notes

All notable changes to Tobogganing will be documented in this file. New releases will be prepended to this file.

---

## v2.0.0 - "Hub Architecture" (2026-02-08)

### Breaking Changes

This is a major release with significant architectural changes. Direct upgrades from v1.x are not supported; a migration guide will be published separately.

**Renamed Project**: SASEWaddle has been renamed to **Tobogganing**. All package names, container images, configuration keys, and API endpoints reflect the new name.

**Architecture Migration**: The monolithic three-tier architecture (Manager, Headend, Client) has been replaced with a three-service hub model (hub-api, hub-router, hub-webui). See the migration notes below for details.

**License Change**: The project license has changed from MIT to Limited AGPL-3.0 with commercial use restrictions and a Contributor Employer Exception. See `LICENSE.md` at the project root for full terms.

### Major New Features

**Three-Service Hub Architecture**

The entire backend has been redesigned around a hub model where clients connect to distributed hubs for secure access.

- **hub-api** (Quart / Python 3.13): Control plane for user management, policy authoring, certificate lifecycle, and hub coordination. Replaces the py4web-based Manager service.
- **hub-router** (Go 1.24): Data plane for packet processing, policy enforcement, WireGuard tunnel termination, and traffic routing. Replaces the Go Headend server.
- **hub-webui** (React 18 / Vite 5): Administrative interface for managing hubs, users, policies, and monitoring. Replaces the py4web-embedded web interface.

**py4web to Quart Migration**

The hub-api migrates from py4web to Quart, an async-native ASGI framework compatible with Flask patterns. This enables:
- Native async/await for all request handlers
- Long-lived gRPC streaming connections to hub-routers
- WebSocket support for real-time status updates in the WebUI
- uvicorn + uvloop for high-performance async I/O
- PyDAL retained for multi-database abstraction

**XDP/AF_XDP Data Plane**

The hub-router introduces a kernel-bypass data plane for high-performance packet processing:
- **Fast path (XDP)**: eBPF program attached to the NIC processes simple allow/deny decisions at line rate without entering userspace
- **Slow path (AF_XDP)**: Packets requiring complex inspection (identity-aware routing, logging, application-layer policies) are redirected to Go userspace via AF_XDP sockets
- **NUMA-aware memory pools**: Packet buffers allocated from NUMA-local memory to minimize cross-socket latency on multi-socket servers
- **BPF source**: `services/hub-router/bpf/xdp_filter.c` compiled via cilium/ebpf
- **Performance target**: 10+ Gbps on the fast path, 1+ Gbps on the slow path

**Policy Engine**

A new multi-dimensional policy engine enables fine-grained access control:
- **Domain filtering**: FQDN and wildcard matching (e.g., `*.example.com`)
- **Port control**: Individual ports and ranges (e.g., `80`, `443`, `8000-9000`)
- **Protocol filtering**: TCP, UDP, ICMP matching
- **IP CIDR rules**: Source and destination network matching (e.g., `10.0.0.0/8`)
- **User identity**: Per-user access policies
- **Group membership**: Policies applied to groups of users
- Policies are authored in hub-api and distributed to hub-routers via gRPC streaming with versioning and acknowledgment

**React WebUI**

The administrative interface has been rebuilt as a modern single-page application:
- React 18 with TypeScript for type safety
- Vite 5 for fast builds and hot module replacement
- Tailwind CSS 4 for styling with the gold text theme and Elder sidebar pattern
- TanStack React Query for server state management
- React Router DOM v6 for client-side routing
- Vitest with React Testing Library for component testing
- Role-based UI rendering (Admin, Maintainer, Viewer)

**gRPC Inter-Service Communication**

Hub-api and hub-router communicate over gRPC for real-time operations:
- `StreamPolicies`: Server-streaming RPC for policy distribution
- `ReportStatus`: Unary RPC for hub health and client count reporting
- `SyncCertificates`: Bidirectional streaming for certificate management
- Automatic reconnection with exponential backoff
- Policy cache on hub-routers survives brief hub-api outages

**Multi-Hub Client Connections with Failover**

Clients now connect to two or more hubs simultaneously:
- Automatic failover when the primary hub becomes unreachable
- Hub assignment considers geographic proximity and current load
- Configurable failback behavior when the primary hub recovers
- Hub list refreshed periodically from hub-api

**Cilium Integration**

For Kubernetes deployments, Cilium replaces the custom k8s-cni component:
- Mature eBPF-based CNI with extensive community support
- Native network policy enforcement complementing Tobogganing policies
- Hubble observability for inter-service traffic visibility
- Optional WireGuard encryption for intra-cluster traffic

**Identity Provider Support (Premium, License-Gated)**

Premium identity provider integrations are now available with a valid PenguinTech license:
- **OIDC**: OpenID Connect for single sign-on
- **SAML**: SAML 2.0 federation with external identity providers
- **SCIM**: Automated user and group provisioning
- Graceful fallback to local authentication when license is invalid or expired
- Local authentication remains free and always available

### Infrastructure Changes

**Alpine to Debian Bookworm Migration**

All container base images have been migrated from Alpine Linux to Debian bookworm:

| Service | Old Base | New Base | Rationale |
|---------|----------|----------|-----------|
| hub-api | python:3.12-alpine | python:3.13-slim-bookworm | Consistent base, better library compatibility |
| hub-router | golang:1.23-alpine | debian:bookworm-slim (runtime) | CGO required for XDP/eBPF; musl incompatible |
| hub-webui | node:20-alpine | nginx:stable (runtime) | Static asset serving, consistent with other services |

This change was driven primarily by the hub-router's requirement for glibc and eBPF development headers, which are not reliably available on Alpine/musl.

**Python 3.12 to 3.13 Upgrade**

- Takes advantage of Python 3.13 performance improvements
- Updated all dependencies to versions compatible with 3.13
- No code changes required beyond dependency updates

**Go 1.23 to 1.24 Upgrade**

- Enables new standard library features used in the data plane
- Updated all Go module dependencies
- `go.mod` specifies `go 1.24`

**Node.js 20 to 22 Upgrade**

- LTS version alignment
- Performance improvements in V8 engine
- Updated all npm dependencies

### Component Mapping (v1.x to v2.0.0)

| v1.x Component | v2.0.0 Component | Notes |
|----------------|------------------|-------|
| Manager Service (py4web) | hub-api (Quart) | Complete rewrite; async-native |
| Headend Server (Go) | hub-router (Go) | Refactored; added XDP data plane |
| Manager Web UI (py4web) | hub-webui (React) | Complete rewrite; SPA architecture |
| Custom k8s-cni | Cilium (external) | Replaced with mature eBPF CNI |
| WireGuard kernel module | WireGuard via wgctrl | Same protocol; updated integration |
| Fyne GUI client | Unchanged | Native client architecture preserved |
| Docker client | Unchanged | Container client architecture preserved |
| React Native mobile | Unchanged | Mobile client architecture preserved |

### Removed Features

- **py4web web interface**: Replaced by hub-webui (React SPA)
- **Custom Kubernetes CNI**: Replaced by Cilium
- **Monolithic deployment option**: All deployments now use the three-service model
- **FRR/VRF/OSPF integration**: Removed in favor of policy-based routing through the hub model (may return in a future release)
- **Suricata IDS/IPS direct integration**: Traffic mirroring capabilities are preserved; IDS/IPS integration will be reintroduced via hub-router plugins

### Security Improvements

- All inter-service communication uses TLS 1.3 or gRPC with TLS
- Certificate management simplified with dedicated PKI operations in hub-api
- bandit (Python), gosec (Go), npm audit (JS), and trivy (containers) integrated into CI/CD
- License enforcement prevents unauthorized use of premium features
- Audit logging enhanced with structured JSON output

### Developer Experience

- Makefile with comprehensive targets for build, test, lint, deploy, and development
- `make dev` starts the full development stack with Docker Compose
- `make seed-mock-data` populates 3-4 items per feature for realistic development
- `make smoke-test` provides fast build verification in under 2 minutes
- Hot reload for all three services during development
- Vitest replaces Jest for faster WebUI test execution
- golangci-lint replaces individual Go linters

### Build and CI/CD

- GitHub Actions workflows for multi-architecture builds (AMD64, ARM64)
- Docker Buildx for cross-platform container images
- Build tags: `beta-<epoch64>` (main), `alpha-<epoch64>` (feature branches), `vX.X.X` (releases)
- Automated security scanning on every pull request
- CodeQL compliance for Go and Python

### Known Issues

- XDP fast path requires Linux kernel 5.15+ and does not function on macOS or WSL2
- SCIM provisioning is limited to user and group sync; role mapping requires manual configuration
- Multi-hub failback timing is not yet configurable via the WebUI (CLI/API only)
- Cilium integration tested with Cilium 1.14+; earlier versions may not be compatible

### Migration Guide

A detailed migration guide for v1.x to v2.0.0 will be published as a separate document. Key points:

1. **Data migration**: Export users, certificates, and configuration from the v1.x Manager before upgrading
2. **Container images**: All image names have changed; update deployment manifests
3. **Configuration**: Environment variables have been renamed with `HUB_API_`, `HUB_ROUTER_`, and `VITE_` prefixes
4. **API endpoints**: The REST API has been reorganized under `/api/v1/`; existing client integrations will need updates
5. **License**: Ensure a valid PenguinTech license if using premium features (OIDC, SAML, SCIM)

### Upgrade Notes

- v1.x to v2.0.0 is a full migration, not an in-place upgrade
- Existing WireGuard tunnels will need to be re-established after migration
- Client applications from v1.x are compatible with v2.0.0 hub-routers after re-registration
- Database schema has changed; use the provided migration tool (published separately)

---

## v1.1.4 - "Build System Enhancement" (2025-08-22)

### Major Improvements

**Docker-Based GUI Builds**
- Reliable GUI client builds using Docker containers with Ubuntu base
- Cross-platform support for ARM64 and AMD64 via Docker Buildx and QEMU
- All GUI dependencies included: libayatana-appindicator3-dev, libgtk-3-dev, libgl1-mesa-dev
- Eliminates environment-specific build issues

**Fyne Framework Fixes**
- Fixed `undefined: app.App` error by correcting Fyne type declarations
- Proper import pattern using `fyne.App` interface instead of `app.App`
- Added GUI package compilation tests to catch issues early

**Enhanced CI/CD Pipeline**
- GitHub Actions updated with Docker Buildx for Linux builds
- Comprehensive testing with golangci-lint and GUI compilation verification
- Complete multi-platform matrix: AMD64/ARM64 across macOS, Linux, Windows
- 14+ binary variants covering every major platform and architecture

### Build Verification

- GUI client builds successfully via Docker on Ubuntu
- Headless client static compilation verified for embedded deployment
- All GitHub Actions workflow matrices tested and working
- Cross-platform ARM64 builds verified via Docker Buildx

---

## v1.1.0 - "Enterprise Features" (2025-08-21)

### Major New Features

**Advanced Management Portal**
- Dynamic port configuration via admin interface
- Enhanced firewall system with domain, IP, protocol, and port-based access control
- VRF and OSPF support with FRR integration
- Real-time analytics dashboard with Chart.js

**Security and Monitoring**
- Suricata IDS/IPS integration with traffic mirroring (VXLAN/GRE/ERSPAN)
- Syslog audit logging for compliance
- Enhanced JWT management and session security

**Database and Infrastructure**
- PyDAL database layer with MySQL/PostgreSQL/SQLite support and read replicas
- Database backup system with local and S3-compatible storage
- Redis caching for sessions and firewall rule caching

**Deployment and CI/CD**
- Multi-architecture Docker builds (ARM64, AMD64) via GitHub Actions
- Cross-platform native binaries for Windows, macOS, Linux, and embedded devices

---

## v1.0.1 - "Security Patch" (2025-01-21)

### Critical Security Fixes

- **CVE-2024-24783** (HIGH): Fixed panic in golang.org/x/image; updated to v0.18.0
- **CVE golang.org/x/oauth2** (HIGH): Fixed improper validation; updated to v0.27.0
- **Protestware detection**: Updated WireGuard dependencies to remove flagged gvisor.dev/gvisor package

### Build and Compatibility Fixes

- Fixed missing `headendPublicKey` field in Client struct
- Resolved deprecated `systray.GetTooltip()` API calls
- Updated Go to 1.23.1 with latest toolchain
- Fixed missing `CircuitBoardIcon` import in website EmbeddedSolutions component

---

## v1.0.0 - "Genesis" (2024-08-20)

### Initial Release

**Zero Trust Architecture**
- Dual authentication: X.509 certificates + JWT/SSO
- WireGuard encryption (ChaCha20Poly1305)
- Certificate-based VPN authentication with application-level JWT validation

**Three-Tier Architecture**
- Manager Service: Python 3.12 + py4web, certificate lifecycle, multi-datacenter orchestration
- Headend Server: Go 1.23, WireGuard termination, multi-protocol proxy
- Client Applications: Native Go for Mac/Windows/Linux, React Native for Android, Docker container

**Multi-Platform Support**
- macOS Universal binary (Intel + Apple Silicon)
- Windows x64, Linux AMD64/ARM64
- Android (React Native), Docker multi-arch
- Embedded SDK for third-party integration

**Cloud Native**
- Kubernetes production manifests with auto-scaling
- Docker Compose for development and small deployments
- Terraform for AWS infrastructure
- GitHub Actions CI/CD pipelines

---

*Release notes format: New releases will be added above the oldest entry, maintaining chronological order with newest first.*
