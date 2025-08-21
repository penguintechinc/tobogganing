# SASEWaddle Project Documentation

## Project Overview
SASEWaddle is an Open Source Secure Access Service Edge (SASE) solution implementing Zero Trust Network Architecture (ZTNA) principles. The system consists of three main components:

1. **Manager Service** - Centralized orchestration and certificate management
2. **Headend Server** - WireGuard termination and proxy authentication  
3. **Client Applications** - Docker and native clients for various platforms

## Architecture

### Manager Service (Python 3.12)
- **Purpose**: Coordinate clients across multiple datacenters and clusters
- **Technology Stack**:
  - Python 3.12 with asyncio and multithreading for high performance
  - py4web for web frontend and REST API
  - Certificate generation and management system
- **Key Features**:
  - Multi-datacenter orchestration
  - Certificate lifecycle management
  - Client registration and configuration
  - API key generation for initial client setup
  - **Advanced Web Management Portal**:
    - Role-based access control (Admin/Reporter)
    - Real-time dashboard with live statistics
    - User management interface
    - Comprehensive firewall management
    - Prometheus metrics visualization
    - Session-based authentication with bcrypt
  - **Database Backup System**:
    - Local backup storage with compression and encryption
    - S3-compatible storage support (AWS S3, MinIO, Google Cloud Storage)
    - Automated backup scheduling with cron expressions
    - RESTful API and CLI interface for backup operations
    - Checksum verification and metadata tracking
    - Cross-region backup replication support
  - **Advanced Analytics Dashboard**:
    - Operating system distribution analytics with version tracking
    - Real-time traffic monitoring by headend and region
    - Agent and headend search with advanced filtering
    - Interactive charts and visualizations using Chart.js
    - Client connection statistics and system information
    - Headend performance metrics and health monitoring
    - Historical data aggregation with hourly/daily summaries
    - Automated data retention and cleanup processes
  - **Enterprise-Grade Firewall System**:
    - Domain-based access control (*.example.com)
    - IPv4 and IPv6 address filtering
    - Protocol-level filtering (TCP, UDP, ICMP)
    - Source and destination port ranges
    - Directional traffic control (inbound/outbound/both)
    - Priority-based rule processing
    - Real-time access testing
    - Export rules for headend consumption

### Headend Server (Docker)
- **Purpose**: Terminate WireGuard connections and proxy authenticated traffic
- **Technology Stack**:
  - WireGuard for VPN termination
  - Golang-based proxy for authentication
  - SAML2 and OAuth2 integration with external IdPs
  - Traffic mirroring for IDS/IPS integration
- **Key Features**:
  - WireGuard tunnel termination
  - User and service authentication
  - Traffic routing between clients
  - Internet gateway functionality
  - External IdP integration
  - **Advanced Traffic Mirroring & IDS Integration**:
    - Suricata IDS/IPS integration with EVE JSON format
    - Multiple mirror destinations (VXLAN, GRE, ERSPAN)
    - Real-time threat detection and alerting
    - Zero-copy mirroring for performance
    - Configurable sample rates and filtering
  - **Comprehensive Security Logging**:
    - UDP syslog integration for compliance
    - User resource access tracking
    - Connection audit trails
    - Structured logging with metadata

### Client Applications

#### Docker Container Client
- WireGuard-based VPN client
- Pulls configuration from Manager using temporary API keys
- Automatic key rotation and certificate management
- Containerized deployment for easy scaling

#### Native Golang Client
- **Platforms**: Mac Universal, Linux, Windows
- Lightweight and efficient
- Direct integration with system network stack
- GUI and CLI interfaces
- Auto-update capabilities
- **System Tray Integration**:
  - Real-time connection status monitoring
  - Connect/disconnect VPN with single click
  - Configuration update management with random scheduling (45-60 min intervals)
  - Manual configuration pull capability
  - Connection statistics viewer in browser
  - Settings and about dialogs
  - Graceful shutdown with automatic disconnection

## Development Guidelines

### Coding Standards
- **Python**: Follow PEP 8, use type hints, async/await patterns
- **Golang**: Follow Go formatting standards, use modules
- **Docker**: Multi-stage builds for security and size optimization
- **Go Development**: ALWAYS run lint check and build test after creating or modifying Go packages:
  - `golangci-lint run` for linting
  - `go build ./...` for build verification
  - Fix all linting errors before committing code

### Testing Requirements
- Unit tests for all components
- Integration tests for API endpoints
- End-to-end testing for VPN connectivity
- Security scanning for all containers

### Build Process
- All components built via GitHub Actions
- Version management through `.version` file
- Semantic versioning (starting at 1.0.0)
- Automated Docker image publishing
- Cross-platform binary compilation for Go clients

### Security Considerations
- Zero Trust principles throughout
- Mutual TLS for all communications
- Certificate rotation and revocation
- Secure key storage
- Audit logging for all operations
- Air-gapped deployment support
- Traffic mirroring for IDS/IPS integration
  - Enables external security monitoring
  - Supports threat detection and analysis
  - Maintains packet integrity for forensics
  - Optional encryption for mirrored traffic

## Project Structure
```
/workspaces/SASEWaddle/
├── manager/                 # Manager service code
│   ├── api/                # REST API endpoints
│   ├── web/                # py4web frontend with role-based access
│   ├── auth/               # User authentication and JWT management
│   ├── firewall/           # Advanced firewall and access control
│   ├── metrics/            # Prometheus metrics collection
│   ├── certs/              # Certificate management
│   └── orchestrator/       # Client coordination
├── headend/                # Headend server code
│   ├── proxy/              # Golang proxy with traffic mirroring
│   │   └── mirror/         # Traffic mirroring to Suricata IDS
│   ├── wireguard/          # WireGuard configuration
│   └── auth/               # IdP integration
├── clients/                # Client applications
│   ├── docker/             # Docker client
│   └── native/             # Golang native client
├── website/                # Next.js marketing website
│   ├── pages/              # Next.js pages
│   ├── components/         # React components
│   ├── public/             # Static assets
│   └── functions/          # Cloudflare Workers functions
├── deploy/                 # Deployment configurations
│   ├── suricata/           # Suricata IDS configuration
│   ├── prometheus/         # Prometheus configuration
│   └── grafana/            # Grafana dashboards
├── .github/workflows/      # GitHub Actions
├── tests/                  # Test suites
└── docs/                   # Documentation

```

## Commands to Run
- **Linting**: `make lint` or `python -m pylint manager/` for Python, `golangci-lint run` for Go
- **Type checking**: `python -m mypy manager/` for Python
- **Tests**: `make test` or `pytest` for Python, `go test ./...` for Go
- **Build**: `make build` or use GitHub Actions

## Development TODO List

### ✅ Completed Tasks
- [x] Implement Manager Service (py4web Docker container with async/multithreading)
- [x] JWT token management and validation
- [x] WireGuard certificate generation and lifecycle management  
- [x] REST API endpoints for client/node registration
- [x] Authentication endpoints for headend validation
- [x] Multi-thousand request handling with async/threading
- [x] py4web frontend for cluster management with role-based access (Admin/Reporter)
- [x] Configuration distribution API for headend/clients
- [x] Comprehensive Prometheus metrics endpoints with authentication
- [x] Health endpoints (/health, /healthz) for Kubernetes compatibility
- [x] Advanced firewall system with domain, IP, protocol, and port control
- [x] Implement Headend Server (Go multi-protocol proxy + WireGuard)
- [x] WireGuard tunnel termination for authenticated nodes
- [x] Multi-protocol proxy (TCP, UDP, HTTPS) with dual authentication
- [x] Traffic mirroring to Suricata IDS/IPS (VXLAN/GRE/ERSPAN)
- [x] Node-to-node communication routing through proxy
- [x] Docker containerization with proper entrypoint
- [x] Docker client (ARM64/AMD64) with WireGuard and auto-config
- [x] Native Go client for Mac Universal, Windows, Linux
- [x] FRR-based VRFs for IP space segmentation
- [x] OSPF routing across WireGuard tunnels
- [x] Admin portal for VRF and OSPF configuration
- [x] Configure headend to get firewall rules from manager with Redis caching
- [x] Add syslog logging for user resource access from headend (UDP only)
- [x] Add screenshots and connectivity diagrams to Next.js website
- [x] Allow admin to specify what ports the go proxy listens on
- [x] Ensure all Go files are well documented in code
- [x] Migrate Manager to use PyDAL with MySQL as default and read replica support
- [x] Test Go builds for proxy and clients

### 📝 Current TODO Status
*Last Updated: 2025-08-21*

All initial development tasks have been completed! The SASEWaddle project now includes:

**🎉 Version v1.1.0 Features Complete:**

1. ✅ **Manager Service** - Complete with PyDAL database, web portal, and API
2. ✅ **Headend Proxy** - Go-based with firewall, syslog, and traffic mirroring
3. ✅ **Client Applications** - Native Go client with GUI support
4. ✅ **Network Features** - VRF/OSPF routing via FRR integration
5. ✅ **Security Features** - Comprehensive firewall, IDS/IPS integration
6. ✅ **Monitoring** - Prometheus metrics, syslog logging, health checks
7. ✅ **Database** - PyDAL with MySQL/PostgreSQL/SQLite support
8. ✅ **Documentation** - Well-documented Go code with package descriptions

## Legacy Development TODO List (Historical)
- [x] Implement Manager Service (py4web Docker container with async/multithreading)
  - [x] JWT token management and validation
  - [x] WireGuard certificate generation and lifecycle management  
  - [x] REST API endpoints for client/node registration
  - [x] Authentication endpoints for headend validation
  - [x] Multi-thousand request handling with async/threading
  - [x] py4web frontend for cluster management
  - [x] Configuration distribution API for headend/clients
- [x] Implement Headend Server (Go multi-protocol proxy + WireGuard)
  - [x] WireGuard tunnel termination for authenticated nodes
  - [x] Multi-protocol proxy (TCP, UDP, HTTPS) with dual authentication:
    - [x] Certificate-based authentication (X.509 for WireGuard)
    - [x] JWT validation OR SSO integration (SAML2.0/OAuth2)
  - [x] Traffic mirroring to third-party IDS containers (VXLAN/GRE/ERSPAN)
  - [x] Node-to-node communication routing through proxy
  - [x] Configuration pulling from py4web Manager API
  - [x] Docker containerization with proper entrypoint
- [x] Implement Client Applications
  - [x] Docker client (ARM64/AMD64) with WireGuard and auto-config
    - [x] Multi-architecture Docker support (ARM64/AMD64)
    - [x] Automatic registration and configuration pulling
    - [x] Dual authentication: X.509 certificates + JWT tokens
    - [x] Health monitoring and connection recovery
    - [x] Background authentication renewal service
  - [x] Native Go client for Mac Universal, Windows, Linux
    - [x] Cross-platform build system (Makefile)
    - [x] macOS Universal binaries (Intel + Apple Silicon)
    - [x] Windows x64 and Linux (AMD64/ARM64) support
    - [x] CLI interface with connect/disconnect/status commands
    - [x] Configuration management and validation
    - [x] JWT authentication and token management
- [ ] Build system and deployment
  - [ ] Multi-architecture Docker builds (ARM64/AMD64)
  - [ ] Cross-platform Go binary compilation
  - [ ] GitHub Actions CI/CD workflows

## Authentication Architecture
**Dual Authentication Required:**
1. **WireGuard Layer**: X.509 certificate-based authentication
2. **Application Layer**: JWT token OR SSO (SAML2.0/OAuth2) authentication

This ensures both network-level and application-level security for all users and services.

## Environment Variables

### General
- `MANAGER_API_URL`: Manager service endpoint
- `HEADEND_URL`: Headend server endpoint
- `API_KEY`: Temporary API key for initial setup
- `IDP_URL`: External identity provider URL
- `IDP_TYPE`: SAML2 or OAUTH2
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR

### Manager Service Authentication & Security
- `JWT_SECRET`: Secret key for JWT token signing and validation
- `SESSION_TIMEOUT_HOURS`: Web session timeout in hours (default: 8)
- `METRICS_TOKEN`: Authentication token for Prometheus metrics scraping
- `REDIS_URL`: Redis connection string for session storage

### PyDAL Database Configuration
The Manager service uses PyDAL for database abstraction, supporting MySQL (default), PostgreSQL, and SQLite.

#### Primary Database
- `DB_TYPE`: Database type (mysql, postgresql, sqlite) - Default: mysql
- `DB_HOST`: Database host address
- `DB_PORT`: Database port (3306 for MySQL, 5432 for PostgreSQL)
- `DB_USER`: Database username
- `DB_PASSWORD`: Database password
- `DB_NAME`: Database name/schema
- `DB_POOL_SIZE`: Connection pool size (default: 10)
- `DB_CHARSET`: Character set (default: utf8mb4 for MySQL)
- `DB_COLLATION`: Collation (optional)
- `DB_CONNECT_TIMEOUT`: Connection timeout in seconds

#### Read Replica Support (Optional)
- `DB_READ_REPLICA_ENABLED`: Enable read replica (true/false) - Default: false
- `DB_READ_HOST`: Read replica host address
- `DB_READ_PORT`: Read replica port
- `DB_READ_USER`: Read replica username
- `DB_READ_PASSWORD`: Read replica password
- `DB_READ_NAME`: Read replica database name
- `DB_READ_POOL_SIZE`: Read replica connection pool size (default: 5)

#### TLS/SSL Database Connection (Optional)
- `DB_TLS_ENABLED`: Enable TLS/SSL for database connections (true/false)
- `DB_TLS_CA_CERT`: Path to CA certificate file
- `DB_TLS_CLIENT_CERT`: Path to client certificate file  
- `DB_TLS_CLIENT_KEY`: Path to client private key file
- `DB_TLS_VERIFY_MODE`: SSL verification mode
  - MySQL: VERIFY_IDENTITY, VERIFY_CA, DISABLED
  - PostgreSQL: require, verify-ca, verify-full, disable

#### Database Configuration Examples

**MySQL with TLS (Production)**
```bash
DB_TYPE=mysql
DB_HOST=mysql.example.com
DB_PORT=3306
DB_USER=sasewaddle_prod
DB_PASSWORD=secure_password_here
DB_NAME=sasewaddle_production
DB_TLS_ENABLED=true
DB_TLS_CA_CERT=/certs/ca.pem
DB_TLS_VERIFY_MODE=VERIFY_CA
```

**PostgreSQL (Alternative)**
```bash
DB_TYPE=postgresql
DB_HOST=postgres.example.com
DB_PORT=5432
DB_USER=sasewaddle
DB_PASSWORD=secure_password
DB_NAME=sasewaddle
```

**SQLite (Development)**
```bash
DB_TYPE=sqlite
DB_PATH=/data/sasewaddle.db
```

### Traffic Mirroring & IDS Integration (Headend)
- `TRAFFIC_MIRROR_ENABLED`: Enable/disable traffic mirroring (true/false)
- `TRAFFIC_MIRROR_DESTINATIONS`: Comma-separated list of mirror destinations (e.g., "10.0.0.100:4789,10.0.0.101:4789")
- `TRAFFIC_MIRROR_PROTOCOL`: Mirror protocol (ERSPAN, VXLAN, GRE)
- `TRAFFIC_MIRROR_FILTER`: BPF filter for selective mirroring (optional)
- `TRAFFIC_MIRROR_SAMPLE_RATE`: Sample rate for mirroring (1-100, default: 100)
- `TRAFFIC_MIRROR_BUFFER_SIZE`: Buffer size for mirror queue (default: 1000)
- `TRAFFIC_MIRROR_SURICATA_ENABLED`: Enable Suricata IDS/IPS integration (true/false)
- `TRAFFIC_MIRROR_SURICATA_HOST`: Suricata host address (e.g., "172.20.0.100")
- `TRAFFIC_MIRROR_SURICATA_PORT`: Suricata management port (default: 9999)

### Syslog Integration (Headend)
- `HEADEND_SYSLOG_ENABLED`: Enable syslog logging for user access (true/false)
- `HEADEND_SYSLOG_SERVER`: Syslog server address (UDP only, e.g., "syslog.example.com:514")
- `HEADEND_SYSLOG_FACILITY`: Syslog facility (e.g., "local0")
- `HEADEND_SYSLOG_TAG`: Syslog tag prefix (e.g., "sasewaddle-headend")

## API Endpoints

### Manager API

#### Core Management
- `POST /api/v1/clients/register` - Register new client
- `GET /api/v1/clients/{id}/config` - Get client configuration
- `POST /api/v1/certs/generate` - Generate certificates
- `GET /api/v1/status` - System status
- `GET /health` - Detailed health check
- `GET /healthz` - Kubernetes-style health check
- `GET /metrics` - Prometheus metrics (authenticated)

#### Web Portal API
- `POST /api/web/user` - Create new user (Admin only)
- `POST /api/web/user/{id}/toggle` - Enable/disable user (Admin only)
- `GET /api/web/stats` - Real-time dashboard statistics
- `POST /api/web/client/{id}/revoke` - Revoke client access

#### Firewall Management API
- `POST /api/web/firewall/rule` - Create firewall rule
- `DELETE /api/web/firewall/rule/{id}` - Delete firewall rule
- `GET /api/web/firewall/user/{id}/rules` - Get user's firewall rules
- `POST /api/web/firewall/check` - Test access for user/target
- `GET /api/web/firewall/user/{id}/export` - Export rules for headend

#### Network/VRF Management API  
- `POST /api/web/network/vrf` - Create new VRF
- `DELETE /api/web/network/vrf/{id}` - Delete VRF
- `PUT /api/web/network/vrf/{id}/ospf` - Configure OSPF for VRF
- `GET /api/web/network/vrf/{id}/config` - Get FRR configuration
- `GET /api/web/network/vrf/{id}/neighbors` - Get OSPF neighbors

### Headend API
- `POST /api/v1/auth` - Authenticate user/service
- `GET /api/v1/tunnels` - List active tunnels
- `POST /api/v1/routes` - Configure routing
- `GET /health` - Detailed health check
- `GET /healthz` - Kubernetes-style health check
- `GET /metrics` - Prometheus metrics (authenticated)

## 🌐 Advanced Network Management - VRF & OSPF

SASEWaddle includes enterprise-grade network segmentation and routing capabilities using FRR (Free Range Routing):

### Virtual Routing and Forwarding (VRF) Features

#### VRF Configuration Management
- **Multi-tenant isolation**: Separate routing tables per customer/environment
- **Route Distinguisher (RD)**: Support for ASN:value and IP:value formats
- **Route Targets**: Import/Export route target communities for BGP
- **IP Range Assignment**: CIDR block allocation per VRF
- **Web-based management**: Beautiful admin interface for VRF lifecycle

#### OSPF Routing Integration
- **Dynamic routing**: OSPF over WireGuard tunnels
- **Area-based design**: Support for Normal, Stub, NSSA, and Backbone areas
- **Multi-VRF OSPF**: Independent OSPF instances per VRF
- **Neighbor monitoring**: Real-time OSPF neighbor state tracking
- **Authentication**: MD5 and simple password authentication

### FRR Integration Features

#### Supported Protocols
- **OSPFv2**: IPv4 dynamic routing
- **OSPFv3**: IPv6 dynamic routing (future)
- **BGP**: Border Gateway Protocol for VRF route exchange
- **Static Routes**: Manual route configuration
- **Route Redistribution**: Between OSPF areas and protocols

#### Network Topologies Supported
- **Hub-and-Spoke**: Centralized routing through main sites
- **Full Mesh**: Direct OSPF peering between all sites
- **Hybrid**: Mixed topologies with area-based design
- **Multi-Area OSPF**: Scalable hierarchical routing

### Example VRF Configurations

#### Customer Isolation VRF
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

#### Multi-Site Corporate VRF  
```bash
vrf corporate-wan
 description Corporate Wide Area Network
 rd 10.0.0.1:200
 import rt 65000:200,65000:300
 export rt 65000:200
 exit

router ospf vrf corporate-wan
 router-id 10.0.0.1
 network 10.0.0.0/8 area 0.0.0.0
 area 0.0.0.1 stub
 area 0.0.0.2 nssa
 exit
```

### OSPF Area Design Examples

#### Backbone Area (Area 0)
- **Purpose**: Central routing hub
- **Networks**: Core infrastructure subnets
- **Characteristics**: Full LSA flooding, no external routes

#### Stub Areas  
- **Purpose**: Branch offices with single uplink
- **Characteristics**: No external LSAs, default route injection
- **Benefits**: Reduced routing table size, lower memory usage

#### NSSA (Not-So-Stubby Area)
- **Purpose**: Stub areas with limited external connectivity  
- **Characteristics**: Type-7 LSA support for external routes
- **Use case**: Branch offices with local internet breakout

### Network Management Interface

#### VRF Management Features
- 📊 **Real-time Dashboard**: VRF status, OSPF neighbor states
- 🔧 **Configuration Generator**: Automatic FRR config generation
- 📈 **Route Monitoring**: Live routing table inspection
- 🔍 **Neighbor Discovery**: OSPF adjacency troubleshooting
- 📋 **Export/Import**: Configuration backup and restore
- 🚨 **Alerting**: OSPF neighbor state change notifications

#### OSPF Configuration UI
- **Area Management**: Create and configure OSPF areas
- **Network Assignment**: Drag-and-drop network-to-area assignment
- **Authentication Setup**: MD5 key management per area
- **Timer Configuration**: Hello, dead, LSA refresh intervals
- **Route Redistribution**: Configure route filtering and redistribution

## 🔥 Advanced Firewall System

SASEWaddle includes a comprehensive firewall system for granular access control:

### Rule Types Supported

#### Domain Rules
- `*.example.com` - Wildcard subdomain matching
- `example.com` - Exact domain matching
- Works with both HTTP and HTTPS traffic

#### IP Address Rules
- `192.168.1.1` - Exact IPv4 address
- `2001:db8::1` - Exact IPv6 address
- Supports both source and destination filtering

#### IP Range Rules
- `192.168.1.0/24` - IPv4 CIDR notation
- `10.0.0.0/8` - Large network ranges
- `2001:db8::/32` - IPv6 network ranges

#### Protocol Rules (Advanced)
- **Format**: `protocol:src_ip:src_port->dst_ip:dst_port:direction`
- **Examples**:
  - `tcp:*:*->192.168.1.1:80` - Allow TCP to specific server on port 80
  - `udp:192.168.1.0/24:*->8.8.8.8:53` - Allow DNS from specific network
  - `icmp:*->*` - Allow all ICMP traffic
  - `tcp:10.0.1.5:*->*:443:outbound` - HTTPS from specific host

#### URL Pattern Rules
- Regular expressions for complex URL matching
- `https://.*\.secure\.example\.com/api/.*` - API endpoints only
- Case-insensitive matching supported

### Rule Processing
- **Priority-based**: Lower numbers processed first (1 = highest priority)
- **First-match wins**: Processing stops at first matching rule
- **Default policy**: Deny if no rules match

### Access Control Features
- **Per-user rules**: Individual firewall policies
- **Real-time testing**: Test access before deploying rules
- **Rule export**: Headend servers fetch rules from manager
- **Web interface**: Beautiful admin panel for rule management
- **Audit logging**: All access decisions logged

### Example Firewall Configuration

```json
{
  "user_id": "user123",
  "rules": {
    "allow_domains": [
      {"pattern": "*.company.com", "priority": 10},
      {"pattern": "github.com", "priority": 20}
    ],
    "deny_domains": [
      {"pattern": "*.social-media.com", "priority": 5}
    ],
    "allow_protocol_rules": [
      {
        "protocol": "tcp",
        "dst_ip": "10.0.0.0/8",
        "dst_port": "22,80,443",
        "direction": "outbound",
        "priority": 15
      }
    ]
  }
}
```

## Deployment

### Infrastructure Components
- Use Docker Compose for local development
- Kubernetes manifests for production deployment
- Support for air-gapped environments
- Multi-region deployment capabilities

### Website Deployment
- **Platform**: Cloudflare Pages with Workers
- **Framework**: Next.js with Edge Runtime
- **Features**:
  - Server-side rendering on Cloudflare Edge
  - API routes using Cloudflare Workers
  - Global CDN distribution
  - Automatic SSL/TLS
  - DDoS protection
- **Content**:
  - Product overview and features
  - Interactive demos
  - Documentation portal
  - Download links for clients
  - API reference
  - Use case examples
  - Security architecture diagrams

# Important TODOs for Critical Security Updates

## ✅ CVE Fix COMPLETED - golang.org/x/crypto 
**Status**: COMPLETED
**CVE**: GHSA-v778-237x-gjrc (CRITICAL) - Misuse of ServerConfig.PublicKeyCallback may cause authorization bypass
**Affected**: golang.org/x/crypto < 0.31.0
**Resolution**:
- ✅ Updated /workspaces/SASEWaddle/headend/go.mod: v0.17.0 → v0.31.0 
- ✅ Updated /workspaces/SASEWaddle/clients/native/go.mod: v0.16.0 → v0.31.0
- ✅ FIXED: WireGuard API compatibility issues in /workspaces/SASEWaddle/headend/wireguard/manager.go
  - Fixed ParseEndpoint (removed from wgtypes) → manual parsing with net.UDPAddr
  - Fixed wgtypes.IPNet and wgtypes.ParseIPNet → using standard net.ParseCIDR
- ✅ Headend builds successfully with patched crypto library
- ⚠️ Native client has GUI dependency issues (not CVE-related)

**Files Modified**:
- /workspaces/SASEWaddle/headend/go.mod (crypto: v0.17.0→v0.31.0)
- /workspaces/SASEWaddle/clients/native/go.mod (crypto: v0.16.0→v0.31.0) 
- /workspaces/SASEWaddle/headend/wireguard/manager.go (API compatibility fixes)
- /workspaces/SASEWaddle/clients/native/cmd/tray-example/main.go (import path fixes)

## 🔧 Pending: Native Client Build Issues 
**Status**: PENDING
**Issue**: GUI dependencies and WireGuard API changes in native client
**Impact**: Non-critical (headend security fixed)
**Details**: Native client has build issues related to missing X11/GL libraries and WireGuard API changes for embedded device creation. These are development environment issues, not security vulnerabilities.

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

## Documentation Standards
- All documentation files (except README.md) should be placed in the `docs/` folder
- Documentation should be colorful and icon-filled for better visual appeal
- Use emojis, icons, and formatting to make docs more engaging and readable
- Follow consistent styling across all documentation files
- Keep README.md in the root directory, but all other docs go in `docs/`

## Current Active Tasks (Updated 2025-08-21)
1. ✅ **Implement Manager py4web web portal with role-based access**
2. ✅ **Add Prometheus metrics endpoint to Manager service**  
3. ✅ **Implement user authentication and role system (admin/reporter)**
4. ✅ **Add /healthz endpoints to both Manager and Headend**
5. ✅ **Add authentication to Headend metrics endpoint**
6. ✅ **Add Suricata service to docker-compose configuration**
7. ✅ **Configure go-proxy to forward traffic to Suricata for IDS/IPS**
8. ✅ **Add comprehensive firewall system with domain, IP, protocol, and port control**
9. ✅ **Configure headend to get firewall rules from manager with Redis caching and randomized refresh**
10. ✅ **Add syslog logging for user resource access from headend (UDP only)**
11. ✅ **Add screenshots and connectivity diagrams to Next.js website**
12. ✅ **Add FRR-based VRFs for IP space segmentation**
13. ✅ **Implement OSPF routing across WireGuard tunnels**  
14. ✅ **Create admin portal for VRF and OSPF configuration**
15. ✅ **Allow admin to specify what ports the go proxy listens on**
16. ✅ **Migrate Manager to use PyDAL with MySQL as default and read replica support**
17. ✅ **Create multi-architecture Docker builds (ARM64/AMD64)**
18. ✅ **Set up cross-platform Go binary compilation**
19. ✅ **Create GitHub Actions CI/CD workflows**

