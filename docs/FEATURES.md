# 🚀 Tobogganing Features Documentation

> **Last Updated**: 2025-08-21
> **Version**: 1.1.0

## 📋 Table of Contents

- [🔒 Security Features](#-security-features)
- [🌐 Network Features](#-network-features)
- [🖥️ Client Applications](#️-client-applications)
- [💼 Management Features](#-management-features)
- [📊 Analytics & Monitoring](#-analytics--monitoring)
- [🚀 Deployment Features](#-deployment-features)
- [🔧 Configuration](#-configuration)

---

## 🔒 Security Features

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

---

## 🖥️ Client Applications

Tobogganing provides two distinct client types optimized for different deployment scenarios and user experiences:

### 🖼️ **Desktop GUI Clients**
**Perfect for end users who want the best experience**

#### Supported Platforms
| Platform | Binary Name | Features |
|----------|-------------|----------|
| **macOS Universal** | `tobogganing-client-darwin-universal` | Intel + Apple Silicon support |
| **macOS Intel** | `tobogganing-client-darwin-amd64` | Optimized for Intel Macs |
| **macOS Apple Silicon** | `tobogganing-client-darwin-arm64` | M1/M2/M3 native performance |
| **Linux AMD64** | `tobogganing-client-linux-amd64` | Desktop Linux distributions |
| **Linux ARM64** | `tobogganing-client-linux-arm64` | ARM64 Linux systems |
| **Windows** | `tobogganing-client-windows-amd64.exe` | Windows 10/11 support |

#### System Tray Integration Features
- ✅ **Native System Tray Icon** - Platform-specific tray integration
- ✅ **One-Click Connect/Disconnect** - Toggle VPN with single click
- ✅ **Real-Time Connection Status** - Visual indicators for connection state
- ✅ **Statistics Viewer** - Connection performance metrics in browser
- ✅ **Configuration Management** - Auto-update with random scheduling (45-60 min)
- ✅ **Settings Access** - Easy access to configuration and preferences
- ✅ **Graceful Shutdown** - Automatic disconnection on application exit

#### Installation & Usage
```bash
# Quick GUI installation
curl -sSL https://github.com/penguintechinc/tobogganing/releases/latest/download/install-gui.sh | bash

# Manual installation
curl -L https://github.com/penguintechinc/tobogganing/releases/latest/download/tobogganing-client-darwin-universal -o tobogganing-client
chmod +x tobogganing-client

# Start with system tray
./tobogganing-client gui --auto-connect
```

### 🖥️ **Headless Clients**
**Optimized for servers, containers, and automation**

#### Supported Platforms
| Platform | Binary Name | Use Case |
|----------|-------------|----------|
| **Desktop Platforms** | `*-headless` variants | Server deployments |
| **Linux ARM v7** | `tobogganing-client-linux-armv7-headless` | Raspberry Pi 4/5 |
| **Linux ARM v6** | `tobogganing-client-linux-armv6-headless` | Raspberry Pi Zero/1 |
| **Linux MIPS** | `tobogganing-client-linux-mips-headless` | Router firmware |
| **Linux MIPSLE** | `tobogganing-client-linux-mipsle-headless` | Little-endian MIPS |

#### Command-Line Features
- ✅ **CLI Interface Only** - No GUI dependencies required
- ✅ **Daemon Mode** - Background operation for servers
- ✅ **Docker Ready** - Perfect for containerized environments
- ✅ **Automation Friendly** - Script and systemd integration
- ✅ **Small Footprint** - Minimal resource usage
- ✅ **Cross-Platform** - Wide embedded platform support

#### Installation & Usage
```bash
# Quick headless installation
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

**React Native apps for iOS and Android**

#### Mobile Features
- ✅ **Native Mobile Experience** - Platform-specific UI/UX
- ✅ **WireGuard Integration** - Native VPN protocols
- ✅ **Biometric Authentication** - Fingerprint/Face ID support
- ✅ **Background Connectivity** - Persistent VPN connections
- ✅ **Data Usage Monitoring** - Real-time bandwidth tracking
- ✅ **Server Selection** - Choose optimal headend location

#### Installation

The mobile client no longer lives in this repo — it was consolidated into
the unified `penguind` desktop/mobile client in the `penguin` project
(`reference/tobogganing-clients/` for the prior implementation).

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

## 📚 Additional Resources

- [Architecture Guide](./ARCHITECTURE.md)
- [Quick Start Guide](./QUICKSTART.md)
- [API Documentation](./API.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)
- [Security Best Practices](./SECURITY.md)

---

*For the latest updates and feature announcements, visit our [GitHub repository](https://github.com/penguintechinc/tobogganing)*
