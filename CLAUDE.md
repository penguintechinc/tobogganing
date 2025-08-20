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
  - Web-based management interface

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
  - **Traffic Mirroring**: Optional traffic duplication to external security tools (IDS/IPS)
    - Configurable via environment variables
    - Supports multiple mirror destinations
    - Preserves original packet metadata
    - Zero-copy mirroring for performance

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

## Development Guidelines

### Coding Standards
- **Python**: Follow PEP 8, use type hints, async/await patterns
- **Golang**: Follow Go formatting standards, use modules
- **Docker**: Multi-stage builds for security and size optimization

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
│   ├── web/                # py4web frontend
│   ├── certs/              # Certificate management
│   └── orchestrator/       # Client coordination
├── headend/                # Headend server code
│   ├── proxy/              # Golang proxy
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

### Traffic Mirroring (Headend)
- `TRAFFIC_MIRROR_ENABLED`: Enable/disable traffic mirroring (true/false)
- `TRAFFIC_MIRROR_DESTINATIONS`: Comma-separated list of mirror destinations (e.g., "10.0.0.100:4789,10.0.0.101:4789")
- `TRAFFIC_MIRROR_PROTOCOL`: Mirror protocol (ERSPAN, VXLAN, GRE)
- `TRAFFIC_MIRROR_FILTER`: BPF filter for selective mirroring (optional)
- `TRAFFIC_MIRROR_SAMPLE_RATE`: Sample rate for mirroring (1-100, default: 100)
- `TRAFFIC_MIRROR_BUFFER_SIZE`: Buffer size for mirror queue (default: 1000)

## API Endpoints

### Manager API
- `POST /api/v1/clients/register` - Register new client
- `GET /api/v1/clients/{id}/config` - Get client configuration
- `POST /api/v1/certs/generate` - Generate certificates
- `GET /api/v1/status` - System status

### Headend API
- `POST /api/v1/auth` - Authenticate user/service
- `GET /api/v1/tunnels` - List active tunnels
- `POST /api/v1/routes` - Configure routing

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