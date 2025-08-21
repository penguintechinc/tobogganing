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

### High Performance
- **WireGuard VPN**: Modern, fast, and secure VPN protocol
- **Concurrent Architecture**: Go-based headend with concurrent connection handling
- **Async Python**: Manager service built with Python asyncio for high throughput
- **Optimized Protocols**: Support for HTTP/HTTPS, TCP, and UDP traffic

### Enterprise Ready
- **Multi-Platform**: Native clients for Mac, Windows, and Linux
- **Cloud Native**: Kubernetes-ready with auto-scaling and monitoring
- **Traffic Mirroring**: Integration with IDS/IPS systems (VXLAN/GRE/ERSPAN)
- **Compliance**: Audit logging and compliance-ready features
- **High Availability**: Multi-datacenter orchestration with failover

### Easy Deployment
- **Infrastructure as Code**: Complete Terraform, Kubernetes, and Docker Compose configurations
- **Multiple Deployment Options**: Kubernetes, Docker, cloud providers, or bare metal
- **Automated CI/CD**: GitHub Actions for testing, building, and releasing
- **Monitoring**: Built-in Prometheus metrics and Grafana dashboards

## 🏗️ Architecture

SASEWaddle consists of three main components:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Clients       │    │   Headend        │    │   Manager       │
│                 │    │   Server         │    │   Service       │
│ • Native Apps   │◄──►│ • WireGuard      │◄──►│ • Orchestration │
│ • Docker        │    │ • Proxy          │    │ • Certificates  │
│ • Multi-platform│    │ • Authentication │    │ • Web Interface │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Manager Service (Python 3.12)
Central orchestration with certificate management, client registration, and multi-datacenter coordination.

### Headend Server (Go 1.21)
WireGuard termination point with multi-protocol proxy, traffic mirroring, and external IdP integration.

### Client Applications
Cross-platform native applications and Docker containers with automatic configuration and health monitoring.

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
