# Tobogganing - Claude Code Context

## Project Overview

Tobogganing is a multi-component SASE (Secure Access Service Edge) platform with WireGuard VPN infrastructure. The project consists of 8+ components spanning Python, Go, and Node.js/TypeScript, designed for enterprise-scale secure network access and zero-trust architecture.

**Project Features:**
- Multi-platform support (macOS, Linux, Windows)
- WireGuard VPN infrastructure with headend server
- Native clients (GUI and headless)
- Kubernetes CNI plugin for pod networking
- Manager service with authentication and RBAC
- High-performance networking with Go
- Web UI dashboard for management
- Enterprise security and compliance

## Technology Stack

### Core Technologies

**Python 3.12**:
- Manager service (authentication, RBAC, API)
- Documentation generation
- PyDAL for database abstraction (mandatory)
- Flask + Flask-Security-Too for web services

**Go 1.23+**:
- Headend server (WireGuard termination, traffic routing)
- Native clients (GUI and headless modes)
- Kubernetes CNI plugin (pod networking)
- XDP/AF_XDP for performance-critical paths (when needed)

**Node.js 18+ / TypeScript**:
- Web UI dashboard (React)
- Admin management interface
- Real-time status monitoring
- API client integration

**Infrastructure**:
- **Containerization**: Docker with multi-stage builds
- **Orchestration**: Kubernetes with Helm charts
- **Networking**: WireGuard for VPN tunnels
- **Database**: PostgreSQL (primary), MySQL/SQLite supported
- **CI/CD**: GitHub Actions with multi-arch builds

### Infrastructure & DevOps
- **Containers**: Docker with multi-stage builds, Docker Compose
- **Orchestration**: Kubernetes with Helm charts
- **Configuration Management**: Ansible for infrastructure automation
- **CI/CD**: GitHub Actions with comprehensive pipelines
- **Monitoring**: Prometheus metrics, Grafana dashboards
- **Logging**: Structured logging with configurable levels

### Databases & Storage
- **Primary**: PostgreSQL (default, configurable via `DB_TYPE` environment variable)
- **Cache**: Redis/Valkey with optional TLS and authentication
- **Database Abstraction Layers (DALs)**:
  - **Python**: PyDAL (mandatory for ALL Python applications)
    - SQLAlchemy for schema initialization
    - PyDAL for migrations and day-to-day operations
    - Thread-safe connection pooling
    - Multi-database support (postgres, mysql, sqlite)
  - **Go**: GORM or sqlx (mandatory for network services)
    - Cross-database compatibility required
    - Connection pooling and retry logic
- **Migrations**: Automated schema management via PyDAL
- **Connection Management**: Thread-local connections for Python

**Supported DB_TYPE Values**:
- `postgres` - PostgreSQL (recommended)
- `mysql` - MySQL/MariaDB with Galera support
- `sqlite` - SQLite (development/testing)

### Security & Authentication
- **Manager Service**: Flask-Security-Too (mandatory)
  - Role-based access control (RBAC)
  - JWT token authentication
  - Password hashing with bcrypt
  - Multi-factor authentication (2FA)
  - Session management and timeout
- **WireGuard**: Certificate-based and pre-shared key authentication
- **mTLS**: Mutual TLS for service-to-service communication
- **TLS Enforcement**: TLS 1.2 minimum, prefer TLS 1.3
- **Network Security**:
  - Zero-trust architecture
  - Per-pod WireGuard tunnels
  - Encrypted inter-service communication
- **Scanning**: Trivy vulnerability scanning, CodeQL analysis
- **Code Quality**: All code must pass security analysis

## PenguinTech License Server Integration

All projects integrate with the centralized PenguinTech License Server at `https://license.penguintech.io` for feature gating and enterprise functionality.

**IMPORTANT: License enforcement is ONLY enabled when project is marked as release-ready**
- Development phase: All features available, no license checks
- Release phase: License validation required, feature gating active

**License Key Format**: `PENG-XXXX-XXXX-XXXX-XXXX-ABCD`

**Core Endpoints**:
- `POST /api/v2/validate` - Validate license
- `POST /api/v2/features` - Check feature entitlements
- `POST /api/v2/keepalive` - Report usage statistics

**Environment Variables**:
```bash
# License configuration
LICENSE_KEY=PENG-XXXX-XXXX-XXXX-XXXX-ABCD
LICENSE_SERVER_URL=https://license.penguintech.io
PRODUCT_NAME=your-product-identifier

# Release mode (enables license enforcement)
RELEASE_MODE=false  # Development (default)
RELEASE_MODE=true   # Production (explicitly set)
```

📚 **Detailed Documentation**: [License Server Integration Guide](docs/licensing/license-server-integration.md)

## WaddleAI Integration (Optional)

For projects requiring AI capabilities, integrate with WaddleAI located at `~/code/WaddleAI`.

**When to Use WaddleAI:**
- Natural language processing (NLP)
- Machine learning model inference
- AI-powered features and automation
- Intelligent data analysis
- Chatbots and conversational interfaces

**Integration Pattern:**
- WaddleAI runs as separate microservice container
- Communicate via REST API or gRPC
- Environment variable configuration for API endpoints
- License-gate AI features as enterprise functionality

📚 **WaddleAI Documentation**: See WaddleAI project at `~/code/WaddleAI` for integration details

## Project Structure

```
tobogganing/
├── .github/             # CI/CD pipelines and templates
│   └── workflows/       # GitHub Actions for builds and releases
├── manager/             # Manager service (Python 3.12)
│   ├── api/            # Flask + Flask-Security-Too API
│   ├── models/         # PyDAL database models
│   ├── migrations/     # Database migrations
│   └── tests/          # Manager unit tests
├── headend/            # Headend server (Go 1.23)
│   ├── main.go         # WireGuard termination
│   ├── routing/        # Traffic routing logic
│   ├── auth/           # Certificate authentication
│   └── tests/          # Headend unit tests
├── clients/            # Native clients (Go 1.23)
│   ├── gui/            # GUI client (Fyne framework)
│   ├── cli/            # Headless CLI client
│   ├── common/         # Shared client code
│   └── tests/          # Client unit tests
├── k8s-cni/            # Kubernetes CNI plugin (Go 1.23)
│   ├── plugin/         # CNI plugin implementation
│   ├── config/         # Network configuration
│   └── tests/          # CNI plugin tests
├── webui/              # Web UI dashboard (React/TypeScript)
│   ├── src/            # React components and pages
│   ├── public/         # Static assets
│   └── tests/          # Frontend tests
├── deploy/             # Deployment configurations
│   ├── docker-compose/ # Docker Compose files
│   ├── k8s/            # Kubernetes manifests
│   └── helm/           # Helm charts
├── docs/               # Documentation
├── scripts/            # Build and utility scripts
├── .version            # Version tracking
└── CLAUDE.md           # This file
```

### Multi-Component Architecture

Tobogganing uses a multi-component architecture with specialized services:

| Component | Technology | Purpose | Deployment |
|-----------|-----------|---------|-----------|
| **Manager** | Python 3.12 + Flask | User management, authentication, RBAC, API | Container or VM |
| **Headend** | Go 1.23 | WireGuard termination, traffic routing | Container or VM |
| **Native Clients** | Go 1.23 | User-facing WireGuard clients | Desktop, server, mobile |
| **K8s CNI Plugin** | Go 1.23 | Pod networking with WireGuard | Kubernetes node |
| **WebUI** | React + TypeScript | Management dashboard | Container |

#### Deployment Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      Internet / Corporate Network                        │
└──────────────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │  Load Balancer     │
                    │  (Optional: NGINX) │
                    └─────────┬──────────┘
                              │
        ┌─────────────────────┼──────────────────────┐
        │                     │                      │
    ┌───┴────┐          ┌─────┴──────┐      ┌───────┴────┐
    │ WebUI  │          │  Manager   │      │  Headend   │
    │ (Port  │          │  (Port     │      │  (Port     │
    │ 3000)  │          │  5000)     │      │  51820)    │
    │        │          │            │      │            │
    │React   │          │Flask +     │      │WireGuard   │
    │UI      │          │Security    │      │Server      │
    └───┬────┘          └─────┬──────┘      └───────┬────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │   PostgreSQL       │
                    │   (Port 5432)      │
                    │                    │
                    │  - Users & Auth    │
                    │  - Policies        │
                    │  - Logs            │
                    └────────────────────┘

Kubernetes Integration (Optional):
├── Manager Pod → Database
├── Headend Pod → WireGuard service
├── CNI Plugin → Per-pod tunnels
└── WebUI Pod → React dashboard
```

#### Component Communication Patterns

- **Manager to Headend**: REST API (HTTPS)
- **Clients to Headend**: WireGuard protocol
- **WebUI to Manager**: REST API + WebSockets
- **Pod to Headend**: WireGuard (via CNI plugin)
- **Inter-service**: mTLS for security

### Default Roles (WebUI)

| Role | Permissions |
|------|-------------|
| **Admin** | Full access: user CRUD, settings, all features |
| **Maintainer** | Read/write access to resources, no user management |
| **Viewer** | Read-only access to resources |

## Version Management System

**Format**: `vMajor.Minor.Patch.build`
- **Major**: Breaking changes, API changes, removed features
- **Minor**: Significant new features and functionality additions
- **Patch**: Minor updates, bug fixes, security patches
- **Build**: Epoch64 timestamp of build time

**Update Commands**:
```bash
./scripts/version/update-version.sh          # Increment build timestamp
./scripts/version/update-version.sh patch    # Increment patch version
./scripts/version/update-version.sh minor    # Increment minor version
./scripts/version/update-version.sh major    # Increment major version
```

## Development Workflow

### Local Development Setup
```bash
git clone <repository-url>
cd project-name
make setup                    # Install dependencies
make dev                      # Start development environment
```

### Essential Commands
```bash
# Development
make dev                      # Start development services
make test                     # Run all tests
make lint                     # Run linting
make build                    # Build all services
make clean                    # Clean build artifacts

# Production
make docker-build             # Build containers
make docker-push              # Push to registry
make deploy-dev               # Deploy to development
make deploy-prod              # Deploy to production

# Testing
make test-unit               # Run unit tests
make test-integration        # Run integration tests
make test-e2e                # Run end-to-end tests

# License Management
make license-validate        # Validate license
make license-check-features  # Check available features
```

## Critical Development Rules

### Development Philosophy: Safe, Stable, and Feature-Complete

**NEVER take shortcuts or the "easy route" - ALWAYS prioritize safety, stability, and feature completeness**

#### Core Principles
- **No Quick Fixes**: Resist quick workarounds or partial solutions
- **Complete Features**: Fully implemented with proper error handling and validation
- **Safety First**: Security, data integrity, and fault tolerance are non-negotiable
- **Stable Foundations**: Build on solid, tested components
- **Future-Proof Design**: Consider long-term maintainability and scalability
- **No Technical Debt**: Address issues properly the first time

#### Red Flags (Never Do These)
- ❌ Skipping input validation "just this once"
- ❌ Hardcoding credentials or configuration
- ❌ Ignoring error returns or exceptions
- ❌ Commenting out failing tests to make CI pass
- ❌ Deploying without proper testing
- ❌ Using deprecated or unmaintained dependencies
- ❌ Implementing partial features with "TODO" placeholders
- ❌ Bypassing security checks for convenience
- ❌ Assuming data is valid without verification
- ❌ Leaving debug code or backdoors in production

#### Quality Checklist Before Completion
- ✅ All error cases handled properly
- ✅ Unit tests cover all code paths
- ✅ Integration tests verify component interactions
- ✅ Security requirements fully implemented
- ✅ Performance meets acceptable standards
- ✅ Documentation complete and accurate
- ✅ Code review standards met
- ✅ No hardcoded secrets or credentials
- ✅ Logging and monitoring in place
- ✅ Build passes in containerized environment
- ✅ No security vulnerabilities in dependencies
- ✅ Edge cases and boundary conditions tested

### Git Workflow
- **NEVER commit automatically** unless explicitly requested by the user
- **NEVER push to remote repositories** under any circumstances
- **ONLY commit when explicitly asked** - never assume commit permission
- Always use feature branches for development
- Require pull request reviews for main branch
- Automated testing must pass before merge

**Before Every Commit - Security Scanning**:
- **Run security audits on all modified packages**:
  - **Go packages**: Run `gosec ./...` on modified Go services
  - **Node.js packages**: Run `npm audit` on modified Node.js services
  - **Python packages**: Run `bandit -r .` and `safety check` on modified Python services
- **Do NOT commit if security vulnerabilities are found** - fix all issues first
- **Document vulnerability fixes** in commit message if applicable

**Before Every Commit - API Testing**:
- **Create and run API testing scripts** for each modified container service
- **Testing scope**: All new endpoints and modified functionality
- **Test files location**: `tests/api/` directory with service-specific subdirectories
  - `tests/api/flask-backend/` - Flask backend API tests
  - `tests/api/go-backend/` - Go backend API tests
  - `tests/api/webui/` - WebUI container tests
- **Run before commit**: Each test script should be executable and pass completely
- **Test coverage**: Health checks, authentication, CRUD operations, error cases
- **Command pattern**: `cd services/<service-name> && npm run test:api` or equivalent

**Before Every Commit - Screenshots**:
- **Run screenshot tool to update UI screenshots in documentation**
  - Run `cd services/webui && npm run screenshots` to capture current UI state
  - This automatically removes old screenshots and captures fresh ones
  - Commit updated screenshots with relevant feature/documentation changes

### Local State Management (Crash Recovery)
- **ALWAYS maintain local .PLAN and .TODO files** for crash recovery
- **Keep .PLAN file updated** with current implementation plans and progress
- **Keep .TODO file updated** with task lists and completion status
- **Update these files in real-time** as work progresses
- **Add to .gitignore**: Both .PLAN and .TODO files must be in .gitignore
- **File format**: Use simple text format for easy recovery
- **Automatic recovery**: Upon restart, check for existing files to resume work

### Dependency Security Requirements
- **ALWAYS check for Dependabot alerts** before every commit
- **Monitor vulnerabilities via Socket.dev** for all dependencies
- **Mandatory security scanning** before any dependency changes
- **Fix all security alerts immediately** - no commits with outstanding vulnerabilities
- **Regular security audits**: `npm audit`, `go mod audit`, `safety check`

### Linting & Code Quality Requirements
- **ALL code must pass linting** before commit - no exceptions
- **Python**: flake8, black, isort, mypy (type checking), bandit (security)
- **JavaScript/TypeScript**: ESLint, Prettier
- **Go**: golangci-lint (includes staticcheck, gosec, etc.)
- **Ansible**: ansible-lint
- **Docker**: hadolint
- **YAML**: yamllint
- **Markdown**: markdownlint
- **Shell**: shellcheck
- **CodeQL**: All code must pass CodeQL security analysis
- **PEP Compliance**: Python code must follow PEP 8, PEP 257 (docstrings), PEP 484 (type hints)

### Pre-Commit Hooks
- **ESLint**: Configured and enforced in pre-commit hooks for all JavaScript/TypeScript files
- **Python linters**: Integrated into pre-commit hooks
- **Security scanning**: Run automatically via pre-commit framework
- **Automated fixes**: Prettier and black run automatically before each commit

### Build & Deployment Requirements
- **NEVER mark tasks as completed until successful build verification**
- All Go and Python builds MUST be executed within Docker containers
- Use containerized builds for local development and CI/CD pipelines
- Build failures must be resolved before task completion

### Documentation Standards
- **README.md**: Keep as overview and pointer to comprehensive docs/ folder
- **docs/ folder**: Create comprehensive documentation for all aspects
- **RELEASE_NOTES.md**: Maintain in docs/ folder, prepend new version releases to top
- Update CLAUDE.md when adding significant context
- **Build status badges**: Always include in README.md
- **ASCII art**: Include catchy, project-appropriate ASCII art in README
- **Company homepage**: Point to www.penguintech.io
- **License**: All projects use Limited AGPL3 with preamble for fair use

### File Size Limits
- **Maximum file size**: 25,000 characters for ALL code and markdown files
- **Split large files**: Decompose into modules, libraries, or separate documents
- **CLAUDE.md exception**: Maximum 39,000 characters (only exception to 25K rule)
- **High-level approach**: CLAUDE.md contains high-level context and references detailed docs
- **Documentation strategy**: Create detailed documentation in `docs/` folder and link to them from CLAUDE.md
- **Keep focused**: Critical context, architectural decisions, and workflow instructions only
- **User approval required**: ALWAYS ask user permission before splitting CLAUDE.md files
- **Use Task Agents**: Utilize task agents (subagents) to be more expedient and efficient when making changes to large files, updating or reviewing multiple files, or performing complex multi-step operations
- **Avoid sed/cat**: Use sed and cat commands only when necessary; prefer dedicated Read/Edit/Write tools for file operations

## Development Standards

Comprehensive development standards are documented separately to keep this file concise.

📚 **Complete Standards Documentation**: [Development Standards](docs/STANDARDS.md)

### Quick Reference

**API Versioning**:
- ALL REST APIs MUST use versioning: `/api/v{major}/endpoint` format
- Semantic versioning for major versions only in URL
- Support current and previous versions (N-1) minimum
- Add deprecation headers to old versions
- Document migration paths for version changes

**Database Standards**:
- PyDAL mandatory for ALL Python applications
- Thread-safe usage with thread-local connections
- Environment variable configuration for all database settings
- Connection pooling and retry logic required

**Protocol Support**:
- REST API, gRPC, HTTP/1.1, HTTP/2, HTTP/3 support
- Environment variables for protocol configuration
- Multi-protocol implementation required

**Performance Optimization (Python):**
- Dataclasses with slots mandatory (30-50% memory reduction)
- Type hints required for all Python code
- asyncio for I/O-bound operations
- threading for blocking I/O
- multiprocessing for CPU-bound operations
- Avoid premature optimization - profile first

**High-Performance Networking (Case-by-Case):**
- XDP (eXpress Data Path): Kernel-level packet processing
- AF_XDP: Zero-copy socket for user-space packet processing
- Use only for network-intensive applications requiring >100K packets/sec
- Evaluate Python vs Go based on traffic requirements

**Microservices Architecture**:
- Web UI, API, and Connector as **separate containers by default**
- Single responsibility per service
- API-first design
- Independent deployment and scaling
- Each service has its own Dockerfile and dependencies

**Docker Standards**:
- Multi-arch builds (amd64/arm64)
- Debian-slim base images
- Docker Compose for local development
- Minimal host port exposure

**Testing**:
- Unit tests: Network isolated, mocked dependencies
- Integration tests: Component interactions
- E2E tests: Critical workflows
- Performance tests: Scalability validation

**Security**:
- TLS 1.2+ required
- Input validation mandatory
- JWT, MFA, mTLS standard
- SSO as enterprise feature

## Application Architecture

**ALWAYS use microservices architecture** - decompose into specialized, independently deployable containers:

1. **Web UI Container**: ReactJS frontend (separate container, served via nginx)
2. **Application API Container**: Flask + Flask-Security-Too backend (separate container)
3. **Connector Container**: External system integration (separate container)

**Default Container Separation**: Web UI and API are ALWAYS separate containers by default. This provides:
- Independent scaling of frontend and backend
- Different resource allocation per service
- Separate deployment lifecycles
- Technology-specific optimization

**Benefits**:
- Independent scaling
- Technology diversity
- Team autonomy
- Resilience
- Continuous deployment

📚 **Detailed Architecture Patterns**: See [Development Standards - Microservices Architecture](docs/STANDARDS.md#microservices-architecture)

## Component Integration Patterns

### Manager Service - Flask + Flask-Security-Too
The Manager service provides authentication and user management for the entire platform:

```python
from flask import Flask
from flask_security import Security, auth_required
from flask_security.datastore import DataStore
from pydal import DAL, Field

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Database setup with PyDAL
db = DAL(
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@"
    f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/tobogganing",
    pool_size=10
)

# Define tables for users, roles, policies
db.define_table('auth_user',
    Field('email', 'string', unique=True),
    Field('password', 'string'),
    Field('active', 'boolean', default=True),
    Field('fs_uniquifier', 'string', unique=True))

db.define_table('auth_role',
    Field('name', 'string', unique=True),  # admin, operator, viewer
    Field('permissions', 'json'))

# Custom PyDAL datastore
user_datastore = CustomPyDALUserDatastore(db, db.auth_user, db.auth_role)
security = Security(app, user_datastore)

@app.route('/api/v1/headends', methods=['GET'])
@auth_required()
def list_headends():
    """List all headend servers"""
    return {'headends': get_all_headends()}

@app.route('/healthz')
def health():
    return {'status': 'healthy'}, 200
```

### Headend Server - WireGuard Termination (Go)
The Headend service handles WireGuard tunnel termination and traffic routing:

```go
package main

import (
    "context"
    "log"
    "net"
    "github.com/vishvananda/netlink"
)

// Headend manages WireGuard interfaces
type Headend struct {
    ListenPort int
    PrivateKey string
    Peers      map[string]*Peer
}

// Peer represents a connected client
type Peer struct {
    PublicKey   string
    AllowedIPs  []net.IPNet
    LastHandshake time.Time
}

// StartServer creates and manages WireGuard interface
func (h *Headend) StartServer(ctx context.Context) error {
    // Create WireGuard interface
    // Configure routing and iptables
    // Accept and route traffic

    log.Printf("Headend listening on port %d", h.ListenPort)

    select {
    case <-ctx.Done():
        return ctx.Err()
    }
    return nil
}

// AuthenticatePeer verifies client certificate
func (h *Headend) AuthenticatePeer(cert []byte) error {
    // Validate certificate via Manager API
    // Add peer to WireGuard interface
    return nil
}
```

### WebUI Dashboard - React + TypeScript
The WebUI provides management and monitoring for Tobogganing platform:

```typescript
// API client for Manager backend
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Add JWT token to requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('jwt_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Headend status monitoring component
import React, { useEffect, useState } from 'react';

interface Headend {
  id: string;
  name: string;
  status: 'online' | 'offline';
  connectedClients: number;
  throughput: number;
}

export const HeadendMonitor: React.FC = () => {
  const [headends, setHeadends] = useState<Headend[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHeadends = async () => {
      try {
        const response = await apiClient.get('/api/v1/headends');
        setHeadends(response.data.headends);
      } catch (error) {
        console.error('Failed to fetch headends:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchHeadends();
  }, []);

  return (
    <div>
      <h2>Headend Servers</h2>
      {loading ? <p>Loading...</p> : <HeadendList headends={headends} />}
    </div>
  );
};
```

### License-Gated Features (Python)
```python
from shared.licensing import license_client, requires_feature
from flask_security import auth_required

@app.route('/api/v1/advanced/analytics')
@auth_required()
@requires_feature("advanced_analytics")
def generate_advanced_report():
    """Requires authentication AND professional+ license"""
    return {'report': analytics.generate_report()}
```

### Monitoring Integration
```python
from prometheus_client import Counter, Histogram, generate_latest

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')

@app.route('/metrics')
def metrics():
    return generate_latest(), {'Content-Type': 'text/plain'}
```

## Website Integration Requirements

**Each project MUST have two dedicated websites**:
- Marketing/Sales website (Node.js based)
- Documentation website (Markdown based)

**Website Design Preferences**:
- Multi-page design preferred
- Modern aesthetic with clean appearance
- Subtle, sophisticated color schemes
- Gradient usage encouraged
- Responsive design
- Performance focused

**Repository Integration**:
- Add `github.com/penguintechinc/website` as sparse checkout submodule
- Only include project-specific folders
- Folder naming: `{app_name}/` and `{app_name}-docs/`

## Troubleshooting & Support

### Common Issues
1. **Port Conflicts**: Check docker-compose port mappings
2. **Database Connections**: Verify connection strings and permissions
3. **License Validation Failures**: Check license key format and network connectivity
4. **Build Failures**: Check dependency versions and compatibility
5. **Test Failures**: Review test environment setup

### Debug Commands
```bash
# Container debugging
docker-compose logs -f service-name
docker exec -it container-name /bin/bash

# Application debugging
make debug                    # Start with debug flags
make logs                     # View application logs
make health                   # Check service health

# License debugging
make license-debug            # Test license server connectivity
make license-validate         # Validate current license
```

### Support Resources
- **Technical Documentation**: [Development Standards](docs/STANDARDS.md)
- **License Integration**: [License Server Guide](docs/licensing/license-server-integration.md)
- **Integration Support**: support@penguintech.io
- **Sales Inquiries**: sales@penguintech.io
- **License Server Status**: https://status.penguintech.io

## CI/CD & Workflows

### Documentation
- **Complete workflow documentation**: See [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md)
- **CI/CD standards and requirements**: See [`docs/STANDARDS.md`](docs/STANDARDS.md)

### Build Naming Conventions

All container images follow automatic naming based on branch and version changes:

| Scenario | Main Branch | Other Branches |
|----------|------------|-----------------|
| Regular build (no `.version` change) | `beta-<epoch64>` | `alpha-<epoch64>` |
| Version release (`.version` changed) | `vX.X.X-beta` | `vX.X.X-alpha` |
| Tagged release | `vX.X.X` + `latest` | N/A |

**Example**: Updating `.version` to `1.2.0` on main branch triggers builds tagged `v1.2.0-beta` (and auto-creates a GitHub pre-release).

### Version Management

- **Location**: `.version` file in repository root
- **Format**: Semantic versioning (e.g., `1.2.3`)
- **File tracking**: All workflows monitor `.version` for changes
- **Update command**: Edit `.version` file and commit
  ```bash
  echo "1.2.3" > .version
  git add .version
  git commit -m "Release v1.2.3"
  ```

### Pre-Commit Checklist

Before committing, run in this order:

- [ ] **Linters**: `npm run lint` or `golangci-lint run` or equivalent
- [ ] **Security scans**: `npm audit`, `gosec`, `bandit` (per language)
- [ ] **Tests**: `npm test`, `go test ./...`, `pytest` (unit tests only)
- [ ] **Version updates**: Update `.version` if releasing new version
- [ ] **Documentation**: Update docs if adding/changing workflows
- [ ] **No secrets**: Verify no credentials, API keys, or tokens in code
- [ ] **Docker builds**: Verify Dockerfile uses debian-slim base (no alpine)

**Only commit when asked** — follow the pre-commit checklist above, then wait for approval before `git commit`.

### Full Documentation

For complete workflow behavior, troubleshooting, and project-specific details, see [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md).

## License & Legal

**License File**: `LICENSE.md` (located at project root)

**License Type**: Limited AGPL-3.0 with commercial use restrictions and Contributor Employer Exception

The `LICENSE.md` file is located at the project root following industry standards. This project uses a modified AGPL-3.0 license with additional exceptions for commercial use and special provisions for companies employing contributors.

## Template Customization

### Multi-Component Architecture Customization

Tobogganing's four-component architecture (Manager, Headend, Clients, K8s CNI) provides flexibility for enterprise customization while maintaining security and performance.

#### Manager Service Customization
**When to customize**:
- Adding custom authentication providers (SAML, OAuth2, LDAP)
- Implementing policy engines or rule systems
- Integrating with external compliance systems

**Customization patterns**:
```python
# Custom authentication provider
from flask_security import UserDatastore

class CustomUserDatastore(UserDatastore):
    def find_user(self, **kwargs):
        # Custom lookup logic
        pass

# Custom API endpoints for policies
@app.route('/api/v1/policies', methods=['POST'])
@auth_required()
@requires_role('admin')
def create_policy():
    # Policy creation with validation
    return {'policy_id': policy.id}
```

**Database schema extensions**:
- Add custom policy tables in migrations
- Track audit logs for compliance
- Support multi-tenancy via policy namespacing

#### Headend Server Customization
**When to customize**:
- Implementing custom traffic routing rules
- Adding performance monitoring (packet captures, metrics)
- Supporting additional VPN protocols beyond WireGuard
- Custom authentication with external services

**Customization patterns**:
```go
// Custom routing logic
type CustomRouter struct {
    basePath string
    policies map[string]*Policy
}

func (cr *CustomRouter) Route(packet *Packet) (*Destination, error) {
    // Custom routing based on policies
    return cr.applyPolicies(packet)
}

// Custom metrics for Prometheus
type HeadendMetrics struct {
    packetsProcessed prometheus.Counter
    routingLatency   prometheus.Histogram
}
```

#### Native Clients Customization
**When to customize**:
- Adding platform-specific integrations (macOS Keychain, Windows Credential Manager)
- Custom UI for branded clients
- Integration with system DNS resolvers
- Custom logging for audit trails

**Customization patterns**:
```go
// Platform-specific credential storage
type CredentialStore interface {
    Store(key, value string) error
    Retrieve(key string) (string, error)
}

// macOS implementation uses Keychain
type MacOSCredentialStore struct{}

// Windows implementation uses Credential Manager
type WindowsCredentialStore struct{}
```

#### Kubernetes CNI Plugin Customization
**When to customize**:
- Integrating with pod security policies
- Custom IPAM (IP Address Management) schemes
- Advanced network policies
- Multi-cluster networking

**Customization patterns**:
```go
// Custom IPAM provider
type CustomIPAM struct {
    pools map[string]*IPPool
}

func (ipam *CustomIPAM) AllocateIP(namespace, pod string) (net.IP, error) {
    // Custom IP allocation based on namespace/policy
    return ipam.findAvailableIP(namespace)
}

// Network policy enforcement
func (cni *Plugin) ApplyNetworkPolicy(namespace string, policy *Policy) error {
    // Translate policy to iptables/ebpf rules
    return cni.enforcer.Apply(policy)
}
```

### Adding Enterprise Features
1. **Custom Authentication**: Extend Manager with SAML, OAuth2, or LDAP
2. **Policy Engine**: Build custom policy evaluation system
3. **Audit Logging**: Track all administrative actions
4. **Multi-Tenancy**: Isolate organizations via policy namespacing
5. **Advanced Analytics**: Monitor traffic patterns and client behavior
6. **DLP Integration**: Block sensitive data exfiltration at headend
7. **Geographic Enforcement**: Route through regional headends based on policy

### Adding New Services
- Create Go service for performance-critical components (traffic inspection, advanced routing)
- Create Python service for business logic (policy evaluation, reporting)
- Create TypeScript service for management UI
- Configure inter-service authentication via mTLS
- Add service discovery configuration for dynamic scaling

---

**Project Version**: See `.version` file
**Last Updated**: 2025-12-18
**Maintained by**: Penguin Tech Inc
**Based on**: Project Template v1.5.0

## Development Standards Reference

For comprehensive development standards, code quality requirements, and CI/CD compliance specific to Tobogganing, refer to: **[Development Standards](docs/STANDARDS.md)**

Key Standards Coverage:
- Component-specific requirements (Manager, Headend, Clients, CNI)
- Python, Go, and TypeScript coding standards
- Security and testing requirements
- CI/CD compliance and workflows
- Kubernetes and infrastructure standards
- Monitoring, logging, and observability

## Quick Links

- **Repository**: [Tobogganing on GitHub](https://github.com/penguintechinc/tobogganing)
- **Documentation**: [Full Project Docs](docs/)
- **Issue Tracker**: GitHub Issues
- **License**: Limited AGPL3 with fair use preamble

*Tobogganing is an enterprise-grade SASE platform providing secure network access through WireGuard VPN infrastructure with zero-trust architecture.*
