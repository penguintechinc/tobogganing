```
                    🐧 SASEWaddle - The Sassy SASE Penguin 🐧
                              
                                   .-""""""-.
                                 .'          '.
                                /   O      O   \
                               :           `    :
                               |                |
                               :    \______/    :    "Zero Trust? More like Zero Chill!"
                                \              /
                                 '.  '------'  .'      
                            jgs    `""------""`
                                      
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  🛡️  SECURE  •  🚀 FAST  •  🔓 OPEN SOURCE  •  🐧 WADDLE-POWERED  │
    └─────────────────────────────────────────────────────────────────────────┘
```

# SASEWaddle

[![GitHub release](https://img.shields.io/github/release/your-org/sasewaddle.svg)](https://github.com/your-org/sasewaddle/releases)
[![Build Status](https://github.com/your-org/sasewaddle/workflows/CI/badge.svg)](https://github.com/your-org/sasewaddle/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Go Report Card](https://goreportcard.com/badge/github.com/your-org/sasewaddle)](https://goreportcard.com/report/github.com/your-org/sasewaddle)

**SASEWaddle** is an Open Source Secure Access Service Edge (SASE) solution implementing Zero Trust Network Architecture (ZTNA) principles. Built with modern technologies like WireGuard, Go, and Python, it provides enterprise-grade network security with the flexibility of open source.

## 🚀 Features

### Zero Trust Security
- **Dual Authentication**: X.509 certificates + JWT/SSO integration
- **Never Trust, Always Verify**: Every connection authenticated and authorized
- **Certificate Management**: Automated certificate lifecycle management
- **Multi-Factor Authentication**: Support for various authentication methods
- **Advanced Firewall System**: Domain, IP, protocol, and port-based access control
- **Real-time Access Testing**: Test access rules before deployment

### High Performance
- **WireGuard VPN**: Modern, fast, and secure VPN protocol
- **Concurrent Architecture**: Go-based headend with concurrent connection handling
- **Async Python**: Manager service built with Python asyncio for high throughput
- **Optimized Protocols**: Support for HTTP/HTTPS, TCP, and UDP traffic
- **Dynamic Port Configuration**: Admin-configurable proxy listening ports
- **PyDAL Database**: MySQL/PostgreSQL/SQLite with read replica support

### Enterprise Ready
- **Multi-Platform**: Native clients for Mac, Windows, and Linux with system tray integration
- **Cloud Native**: Kubernetes-ready with auto-scaling and monitoring
- **Traffic Mirroring**: Suricata IDS/IPS integration (VXLAN/GRE/ERSPAN)
- **Compliance**: Syslog audit logging and compliance reporting
- **High Availability**: Multi-datacenter orchestration with failover
- **VRF & OSPF Support**: Enterprise network segmentation with FRR integration
- **Database Backup System**: Local and S3-compatible storage with encryption

### Advanced Management
- **Web Management Portal**: Beautiful py4web interface with role-based access (Admin/Reporter)
- **Real-time Analytics**: Operating system distribution, traffic monitoring, and performance metrics
- **Interactive Dashboards**: Chart.js visualizations with hourly/daily aggregations
- **Comprehensive API**: RESTful API with OpenAPI documentation
- **Prometheus Metrics**: Built-in metrics with authenticated endpoints
- **Health Monitoring**: Kubernetes-compatible health checks (/health, /healthz)

### Easy Deployment
- **Multi-Architecture Support**: ARM64 and AMD64 Docker images
- **Cross-Platform Binaries**: Native builds for all major platforms including embedded devices
- **Automated CI/CD**: Complete GitHub Actions workflows for building, testing, and releasing
- **Infrastructure as Code**: Terraform, Kubernetes, and Docker Compose configurations
- **Next.js Marketing Website**: Cloudflare Pages deployment with Workers

## 🏗️ Architecture

SASEWaddle implements a comprehensive SASE architecture with three main components:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SASEWADDLE ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐    │
│   │   CLIENTS    │        │   HEADEND    │        │   MANAGER    │    │
│   │              │        │   SERVER     │        │   SERVICE    │    │
│   │ • Native GUI │◄──────►│ • WireGuard  │◄──────►│ • Web Portal │    │
│   │ • Docker     │        │ • Go Proxy   │        │ • REST API   │    │
│   │ • Mobile     │        │ • Firewall   │        │ • PyDAL DB   │    │
│   │ • Embedded   │        │ • IDS/IPS    │        │ • Metrics    │    │
│   └──────────────┘        └──────────────┘        └──────────────┘    │
│         ▲                        ▲                        ▲            │
│         │                        │                        │            │
│   ┌─────▼──────────────────────▼────────────────────────▼─────┐      │
│   │               SUPPORTING INFRASTRUCTURE                     │      │
│   │  • Redis Cache  • MySQL/PostgreSQL  • Prometheus/Grafana   │      │
│   │  • Suricata IDS • FRR (VRF/OSPF)   • Syslog Server        │      │
│   └─────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Manager Service (Python 3.12)
- **Web Management Portal**: py4web-based interface with role-based access control
- **Certificate Authority**: Automated X.509 certificate generation and lifecycle management
- **Database Backend**: PyDAL with MySQL/PostgreSQL/SQLite and read replica support
- **API Gateway**: RESTful API for client registration and configuration distribution
- **Analytics Engine**: Real-time metrics collection and aggregation
- **Backup System**: Local and S3-compatible storage with encryption

### Headend Server (Go 1.21)
- **WireGuard VPN**: High-performance VPN termination with peer-to-peer routing
- **Multi-Protocol Proxy**: TCP/UDP/HTTP/HTTPS with configurable listening ports
- **Traffic Security**: Firewall rules with domain/IP/protocol/port filtering
- **IDS/IPS Integration**: Traffic mirroring to Suricata via VXLAN/GRE/ERSPAN
- **Authentication**: JWT validation and external IdP integration (SAML2/OAuth2)
- **Network Routing**: VRF and OSPF support through FRR integration

### Client Applications
- **Native Desktop**: Go-based clients for Windows, macOS, and Linux with system tray
- **Docker Container**: Containerized client for Kubernetes and Docker deployments
- **Mobile Apps**: React Native applications for iOS and Android
- **Embedded Support**: Lightweight clients for ARM, MIPS, and IoT devices
- **Auto-Configuration**: Automatic certificate rotation and configuration updates

## 🚀 Quick Start

### Using Docker Compose (Recommended for Testing)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-org/sasewaddle.git
   cd sasewaddle/deploy/docker-compose
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start services**:
   ```bash
   docker-compose -f docker-compose.dev.yml up -d
   ```

4. **Access the interface**:
   - Manager Web UI: http://localhost:8000
   - API Documentation: http://localhost:8000/api/docs

### Native Client Installation

#### Quick Install (Linux/macOS)
```bash
curl -sSL https://github.com/your-org/sasewaddle/releases/latest/download/install.sh | bash
```

#### Manual Installation
1. Download the appropriate binary from [Releases](https://github.com/your-org/sasewaddle/releases)
2. Extract and move to your PATH
3. Run `sasewaddle-client init` to configure

#### Configuration
```bash
# Initialize client configuration
sasewaddle-client init --manager-url https://your-manager.example.com:8000 --api-key YOUR_API_KEY

# Connect to the network
sasewaddle-client connect

# Check connection status
sasewaddle-client status
```

## 📖 Documentation

- **[Installation Guide](https://docs.sasewaddle.com/installation)** - Get up and running quickly
- **[Architecture Guide](https://docs.sasewaddle.com/architecture)** - Understand the system design
- **[Deployment Guide](https://docs.sasewaddle.com/deployment)** - Production deployment instructions
- **[API Reference](https://docs.sasewaddle.com/api)** - Complete API documentation
- **[Use Cases](https://docs.sasewaddle.com/use-cases)** - Real-world examples and configurations

## 🛠️ Development

### Prerequisites
- Go 1.21+ (for headend and client)
- Python 3.12+ (for manager)
- Node.js 18+ (for website)
- Docker (for containerized development)

### Building from Source

```bash
# Clone repository
git clone https://github.com/your-org/sasewaddle.git
cd sasewaddle

# Quick build all React applications + screenshots
./scripts/build-apps.sh

# Alternative: Build individual components
./scripts/build-apps.sh --mobile-only      # Mobile app only
./scripts/build-apps.sh --website-only     # Website only  
./scripts/build-apps.sh --screenshots-only # Screenshots only

# Build Manager Service
cd manager
pip install -r requirements.txt
python -m manager.main

# Build Headend Server
cd headend
go build -o build/headend ./cmd

# Build Native Client
cd clients/native
make all  # Builds for all platforms
# or
make local  # Build for current platform only
```

### Running Tests

```bash
# Python tests
cd manager && pytest

# Go tests (headend)
cd headend && go test ./...

# Go tests (client)
cd clients/native && go test ./...

# Integration tests
make test-integration
```

### Build Artifacts

The build process generates the following artifacts:

```bash
build/
├── apps/
│   ├── mobile-android.bundle      # React Native Android bundle
│   ├── mobile-ios.bundle         # React Native iOS bundle  
│   ├── mobile-assets/            # Mobile app assets
│   ├── website-static/           # Next.js static files
│   └── website-export/           # Exported website
├── screenshots/                  # Generated app screenshots
└── BUILD_REPORT.md              # Comprehensive build report

website/public/images/screenshots/  # Website screenshots
├── homepage-desktop.png
├── features-desktop.png
├── mobile-connection-screen.png
└── ...more screenshots
```

## 🚢 Deployment Options

### Kubernetes (Production)
```bash
cd deploy/kubernetes
kubectl apply -f .
```

### Terraform (Cloud)
```bash
cd deploy/terraform
terraform init
terraform plan
terraform apply
```

### Docker Compose (Development)
```bash
cd deploy/docker-compose
docker-compose up -d
```

See the [Deployment Guide](deploy/README.md) for detailed instructions.

## 🤝 Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) for details on:

- Code of conduct
- Development setup
- Pull request process
- Coding standards
- Testing requirements

## 🛡️ Security

Security is our top priority. We follow responsible disclosure practices:

- Report security issues to: security@sasewaddle.com
- See our [Security Policy](SECURITY.md) for details
- Regular security audits and updates

## 📄 License

SASEWaddle is licensed under the [MIT License](LICENSE).

## 🙋 Support

### Community Support
- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: Questions and community help
- **Discord**: Real-time chat and support
- **Documentation**: Comprehensive guides and tutorials

---

**Made with ❤️ by the open source community**

*SASEWaddle - Secure Access, Simplified*
