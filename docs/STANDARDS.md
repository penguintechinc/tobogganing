# Development Standards

Development standards, code quality requirements, and CI/CD compliance for Tobogganing's multi-component SASE platform.

## Table of Contents

1. [Language Selection Criteria](#language-selection-criteria)
2. [Code Quality Standards](#code-quality-standards)
3. [Component-Specific Standards](#component-specific-standards)
4. [Security Standards](#security-standards)
5. [Testing Requirements](#testing-requirements)
6. [Protocol Support](#protocol-support)
7. [API Versioning](#api-versioning)
8. [Performance Best Practices](#performance-best-practices)
9. [Microservices Architecture](#microservices-architecture)
10. [Docker Standards](#docker-standards)
11. [CI/CD Standards](#cicd-standards)
12. [Kubernetes & Infrastructure](#kubernetes--infrastructure)

---

## Language Selection Criteria

Tobogganing uses a multi-language approach based on component requirements:

### Python 3.12 (Manager Service)
**Use Python for:**
- Manager service with Flask + Flask-Security-Too
- Authentication and RBAC management
- REST API endpoints
- Business logic and data processing
- Database operations via PyDAL

**Advantages:**
- Rapid development
- Flask ecosystem for web services
- PyDAL for database abstraction
- Strong for API development

### Go 1.23+ (Network Services)
**Use Go for:**
- Headend server (WireGuard termination)
- Native clients (GUI and headless)
- Kubernetes CNI plugin
- High-performance networking
- Traffic routing and proxying

**Advantages:**
- Native compiled binaries
- Goroutines for concurrency
- Low memory footprint
- Cross-platform support

### TypeScript/React (Web UI)
**Use for:**
- Web UI dashboard
- Admin management interface
- Real-time monitoring
- Browser-based client interactions

**Advantages:**
- Rich UI components
- React ecosystem
- Type safety with TypeScript
- Modern frontend development

---

## Code Quality Standards

### Universal Requirements

All code MUST:
- Pass linting without exceptions
- Include comprehensive error handling
- Have appropriate logging
- Follow security-first design
- Have tests covering critical paths
- Avoid hardcoded credentials
- Use typed variables (strong typing)

### Python Standards (Manager)

**Version**: Python 3.12

**Required Tools**:
- black (code formatting)
- isort (import sorting)
- flake8 (linting)
- mypy (type checking)
- bandit (security)
- pytest (testing)
- Flask-Security-Too (authentication)
- PyDAL (database abstraction)

**Code Example**:

```python
"""Manager service API endpoints."""

from typing import Optional, List
from dataclasses import dataclass, field
import logging
from pydal import DAL, Field

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class User:
    """System user with role-based access."""
    id: str
    email: str
    roles: List[str]
    created_at: str
    metadata: dict = field(default_factory=dict)

def validate_email(email: str) -> None:
    """Validate email format.

    Raises:
        ValueError: If email format invalid
    """
    if not email or '@' not in email:
        raise ValueError("Invalid email format")

def create_user(email: str, roles: List[str]) -> User:
    """Create new system user with validated input.

    Args:
        email: User email address
        roles: List of role names

    Returns:
        Created User object

    Raises:
        ValueError: If email format invalid
    """
    validate_email(email)

    user = User(id=generate_id(), email=email, roles=roles, created_at=now())
    logger.info(f"Created user: {user.id}")
    return user
```

**Standards**:
- PEP 8 code style
- PEP 257 docstrings
- PEP 484 type hints (mandatory)
- Dataclasses with slots for memory efficiency
- 80%+ test coverage
- Async/await for I/O operations
- PyDAL for all database operations

### Go Standards (Headend, Clients, CNI)

**Version**: Go 1.23+

**Required Tools**:
- golangci-lint
- gosec
- go fmt
- go vet
- go test with race detector

**Code Example**:

```go
package main

import (
    "context"
    "errors"
    "fmt"
    "log"
)

// Endpoint represents WireGuard endpoint
type Endpoint struct {
    IP   string
    Port int
}

// Client manages WireGuard connections
type Client interface {
    Connect(ctx context.Context, endpoint Endpoint) error
    Disconnect(ctx context.Context) error
    Status(ctx context.Context) (string, error)
}

// Connect establishes WireGuard tunnel with validation
func (c *Client) Connect(ctx context.Context, ep Endpoint) error {
    if ep.IP == "" || ep.Port == 0 {
        return errors.New("invalid endpoint: IP and Port required")
    }

    if ep.Port < 1 || ep.Port > 65535 {
        return fmt.Errorf("invalid port: %d (must be 1-65535)", ep.Port)
    }

    log.Printf("Connecting to %s:%d", ep.IP, ep.Port)

    select {
    case <-ctx.Done():
        return ctx.Err()
    default:
        // Implementation
        return nil
    }
}
```

**Standards**:
- gofmt formatting
- Error handling mandatory
- Interface-based design
- 80%+ test coverage
- Race detector: `go test -race ./...`
- Cross-compilation support
- Static binary builds

**Build Tags for Conditional Compilation**:
```go
// GUI builds (default)
// +build !nogui

// Headless builds (servers, embedded)
// +build nogui

// Platform-specific
// +build linux,amd64
```

### TypeScript/React Standards (WebUI)

**Version**: Node.js 18+, TypeScript

**Required Tools**:
- ESLint
- Prettier
- TypeScript (strict mode)
- Jest
- npm audit

**Code Example**:

```typescript
/**
 * Component for WireGuard tunnel status display
 */

import React, { useState, useEffect } from 'react';
import type { ConnectionStatus, TunnelMetrics } from './types';

interface TunnelStatusProps {
    onStatusChange?: (status: ConnectionStatus) => void;
}

/**
 * TunnelStatus displays real-time WireGuard connection status
 */
export const TunnelStatus: React.FC<TunnelStatusProps> = ({ onStatusChange }) => {
    const [status, setStatus] = useState<ConnectionStatus>('disconnected');
    const [metrics, setMetrics] = useState<TunnelMetrics | null>(null);

    useEffect(() => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch('/api/v1/status');
                if (!response.ok) throw new Error('Failed to fetch status');

                const data = await response.json() as ConnectionStatus;
                setStatus(data);
                onStatusChange?.(data);
            } catch (error) {
                console.error('Failed to fetch status:', error);
            }
        }, 5000);

        return () => clearInterval(interval);
    }, [onStatusChange]);

    return (
        <div>
            <h2>WireGuard Tunnel</h2>
            <p>Status: {status}</p>
            {metrics && <MetricsPanel metrics={metrics} />}
        </div>
    );
};
```

**Standards**:
- TypeScript mandatory (strict mode)
- Type annotations for all functions
- 80%+ test coverage with Jest
- React Hooks for state management
- Error boundaries for error handling
- Accessibility (WCAG 2.1 AA)

---

## Component-Specific Standards

### Manager Service (Python 3.12)

**Responsibilities**:
- User and organization management
- Client orchestration
- Certificate lifecycle
- API endpoints (`/api/v1/...`)
- Authentication/authorization (JWT)
- Audit logging
- Metrics collection

**Key Requirements**:
- RESTful API design with proper versioning
- Role-based access control (RBAC)
- Database migrations via PyDAL
- Comprehensive logging
- Prometheus metrics endpoint (`/metrics`)
- Health check endpoints (`/health`, `/healthz`)

**Database**:
- PyDAL for database abstraction (mandatory)
- PostgreSQL/MySQL support
- Connection pooling with thread-local instances
- Transaction management

**Security**:
- Flask-Security-Too for authentication
- JWT token validation
- Password hashing with bcrypt
- Input validation on all endpoints

### Headend Server (Go 1.23)

**Responsibilities**:
- WireGuard tunnel termination
- User/service authentication
- Traffic routing and proxying
- Traffic mirroring for IDS
- Health monitoring
- Connection logging
- Certificate validation

**Key Requirements**:
- High-performance networking
- Goroutine-based concurrency
- Proper resource cleanup
- Non-blocking I/O
- Connection pooling
- Memory management optimization

**Protocols**:
- WireGuard for VPN tunnels
- TCP/UDP for traffic proxying
- VXLAN/GRE for traffic mirroring
- Syslog for audit logging
- REST API for Manager integration

**Performance Targets**:
- Sub-millisecond latency
- Support 10K+ concurrent connections
- Handle 1Gbps+ throughput

### Native Clients (Go 1.23)

**Dual Build Architecture**:

**GUI Builds** (Desktop):
- Fyne framework for cross-platform UI
- System tray integration
- Configuration UI
- Real-time status display
- Requirements: libayatana-appindicator, libgtk-3, webkit2gtk

**Headless Builds** (Servers):
- CLI interface
- Daemon mode
- Configuration via files/environment
- Minimal dependencies
- Static compilation

**Cross-Platform**:
- macOS: Universal binaries (Intel + Apple Silicon)
- Linux: amd64, arm64
- Windows: amd64, arm64

**Features**:
- WireGuard tunnel management
- Certificate/key management
- Automatic reconnection
- Connection monitoring
- Policy enforcement

### K8s CNI Plugin (Go 1.23)

**Responsibilities**:
- Pod network setup
- WireGuard tunnel per pod
- IP allocation management
- Interface management
- Route configuration

**CNI Specification**:
- Version: 1.0.0 compliance
- Commands: ADD, DEL, CHECK, VERSION
- Configuration via JSON
- Network namespace management

**Key Requirements**:
- Low latency
- Memory efficient
- Error handling
- Logging support
- Idempotency

---

## Security Standards

### Input Validation

**Rule**: ALL external inputs MUST be validated

```python
# Python example
def validate_email(email: str) -> None:
    """Validate email format."""
    if not email or len(email) > 254:
        raise ValueError("Invalid email")
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise ValueError("Invalid email format")

def validate_port(port: int) -> None:
    """Validate port number."""
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port")
```

```go
// Go example
func ValidateEndpoint(ip string, port int) error {
    if ip == "" {
        return errors.New("IP required")
    }
    if port < 1 || port > 65535 {
        return errors.New("invalid port")
    }
    return nil
}
```

### Authentication & Authorization

**Requirements**:
- JWT token-based API auth
- Certificate-based mTLS
- Role-based access control (RBAC)
- Session timeout enforcement
- Secure password hashing (bcrypt)
- Multi-factor authentication support
- Audit logging of access

### Network Security

**TLS/SSL**:
- TLS 1.2 minimum (prefer 1.3)
- Valid certificates
- Certificate rotation
- HTTPS enforcement
- HSTS headers

**WireGuard**:
- Pre-shared keys
- Peer verification
- Key rotation
- Endpoint validation
- Certificate-based authentication

### Dependency Security

**Python**:
```bash
safety check
bandit -r .
```

**Go**:
```bash
go mod audit
gosec ./...
```

**Node.js**:
```bash
npm audit
npm audit fix
```

---

## Testing Requirements

### Unit Testing

**Python (Manager)**:
```python
def test_create_user_valid():
    """Test user creation with valid data."""
    user = create_user("test@example.com", ["admin"])
    assert user.email == "test@example.com"
    assert "admin" in user.roles

def test_create_user_invalid_email():
    """Test user creation with invalid email."""
    with pytest.raises(ValueError):
        create_user("invalid-email", ["user"])
```

**Go (Headend, Clients)**:
```go
func TestConnectValid(t *testing.T) {
    client := NewClient()
    err := client.Connect(context.Background(), Endpoint{IP: "10.0.0.1", Port: 51820})
    if err != nil {
        t.Errorf("Connect() failed: %v", err)
    }
}

func TestConnectInvalid(t *testing.T) {
    client := NewClient()
    err := client.Connect(context.Background(), Endpoint{IP: "", Port: 0})
    if err == nil {
        t.Error("Connect() should fail with empty endpoint")
    }
}
```

**Coverage Targets**:
- Minimum 80% code coverage
- 100% for security-critical code
- All error paths tested
- Edge cases covered
- Concurrent access tested (Go)

### Integration Testing

Scope:
- Multi-component interaction
- Manager → Headend API
- Client → Manager registration
- WireGuard tunnel establishment
- Database operations
- Authentication flows

### Docker Testing

Validation:
- Image builds successfully
- All binaries present
- Correct language versions
- Health endpoints respond
- Services start correctly

---

## Protocol Support

**ALL applications MUST support multiple communication protocols:**

### Required Protocol Support

1. **REST API**: RESTful HTTP endpoints
   - JSON request/response format
   - Proper HTTP status codes
   - Resource-based URL design

2. **gRPC**: High-performance RPC protocol
   - Protocol Buffers for serialization
   - Bi-directional streaming
   - Health checking

3. **HTTP/1.1**: Standard HTTP protocol
   - Keep-alive connections
   - Compression (gzip, deflate)

4. **HTTP/2**: Modern HTTP protocol
   - Multiplexing
   - Header compression

5. **WireGuard**: VPN tunnel protocol
   - UDP-based transport
   - Peer-to-peer tunneling

### Configuration via Environment Variables

- `HTTP1_ENABLED`: Enable HTTP/1.1 (default: true)
- `HTTP2_ENABLED`: Enable HTTP/2 (default: true)
- `GRPC_ENABLED`: Enable gRPC (default: false)
- `HTTP_PORT`: HTTP/REST API port (default: 8080)
- `GRPC_PORT`: gRPC port (default: 50051)
- `METRICS_PORT`: Prometheus metrics port (default: 9090)

---

## API Versioning

**ALL REST APIs MUST use versioning in the URL path**

### URL Structure

**Required Format:** `/api/v{major}/endpoint`

**Examples:**
- `/api/v1/users` - User management
- `/api/v1/headends` - Headend management
- `/api/v1/auth/login` - Authentication

**Key Rules**:
1. Always include version prefix in URL path
2. Semantic versioning: `v1`, `v2`, `v3`, etc.
3. Major version only in URL
4. Consistent prefix across all endpoints
5. Version-specific sub-resources

### Version Lifecycle

**Version Strategy**:
- **Current Version**: Active development
- **Previous Version (N-1)**: Bug fixes and security patches
- **Older Versions (N-2+)**: Deprecated

**Deprecation Process**:
1. Release new major version
2. Support previous version for 12 months
3. Add deprecation headers
4. Include sunset date
5. Provide migration guidance

---

## Performance Best Practices

**ALWAYS prioritize performance through modern patterns**

### Python Performance Requirements

#### Concurrency Patterns

1. **asyncio** - For I/O-bound operations
2. **threading** - For blocking I/O with libraries
3. **multiprocessing** - For CPU-bound operations

#### Dataclasses with Slots - MANDATORY

```python
@dataclass(slots=True, frozen=True)
class User:
    """User model with slots for 30-50% memory reduction."""
    id: int
    name: str
    email: str
    created_at: str
```

#### Type Hints - MANDATORY

```python
async def process_users(
    user_ids: List[int],
    batch_size: int = 100,
    callback: Optional[Callable[[User], None]] = None
) -> Dict[int, User]:
    """Process users with full type hints."""
    results: Dict[int, User] = {}
    for user_id in user_ids:
        user = await fetch_user(user_id)
        results[user_id] = user
        if callback:
            callback(user)
    return results
```

### Go Performance Requirements

- **Goroutines**: Leverage for concurrent operations
- **Channels**: For safe data passing
- **Sync primitives**: Use sync.Pool, sync.Map
- **Context**: For cancellation and timeouts

---

## Microservices Architecture

**ALWAYS use microservices architecture**

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Manager** | Python 3.12 + Flask | Authentication, RBAC, API |
| **Headend** | Go 1.23 | WireGuard termination, routing |
| **Clients** | Go 1.23 | User-facing VPN clients |
| **CNI Plugin** | Go 1.23 | Kubernetes pod networking |
| **WebUI** | React + TypeScript | Management dashboard |

### Design Principles

- **Single Responsibility**: One clear purpose per service
- **Independent Deployment**: Services update independently
- **API-First Design**: Well-defined APIs
- **Data Isolation**: Each service owns its data
- **Fault Isolation**: Failures don't cascade
- **Scalability**: Scale individual services per demand

### Service Communication

- **Synchronous**: REST API, gRPC
- **Asynchronous**: Message queues
- **Service Discovery**: Docker networking or mesh
- **Circuit Breakers**: Fallback mechanisms

---

## Docker Standards

### Build Standards

**All builds MUST be executed within Docker containers**

**Use multi-stage builds with debian-slim**:
```dockerfile
FROM golang:1.23-slim AS builder
WORKDIR /build
COPY . .
RUN CGO_ENABLED=0 go build -o bin/app ./cmd

FROM debian:bookworm-slim
COPY --from=builder /build/bin/app /usr/local/bin/
CMD ["app"]
```

### Docker Compose Standards

**ALWAYS create docker-compose files for local development**

**Prefer Docker networks over host ports**:
- Minimize host port exposure
- Use named networks for service-to-service communication
- Only expose ports for developer access

### Multi-Arch Build Strategy

GitHub Actions should use multi-arch builds:
```yaml
- uses: docker/build-push-action@v5
  with:
    platforms: linux/amd64,linux/arm64
```

---

## CI/CD Standards

### Required Workflows

- **Build workflows**: 1 per component
- **Security scanning**: Mandatory for all code
- **Testing**: Unit tests required
- **Version release**: Auto-release on version bump

### Pre-Commit Checklist

- [ ] Linters pass
- [ ] Security scans pass
- [ ] Tests pass (80%+ coverage)
- [ ] No hardcoded secrets
- [ ] Documentation updated

### Build Naming Conventions

| Scenario | Tag Pattern |
|----------|------------|
| Regular build (no version change) | `{branch}-{epoch64}` |
| Version release | `v{semver}-{branch}` |
| Tagged release | `v{semver}`, `latest` |

---

## Kubernetes & Infrastructure

### K8s Deployment Standards

**YAML Best Practices**:
- Resource requests and limits
- Health probes (liveness, readiness)
- Service accounts with RBAC
- Network policies
- PersistentVolumes for state
- ConfigMaps for configuration
- Secrets for credentials

### Helm Chart Standards

**Structure**:
- Chart.yaml with version sync
- templates/ for K8s manifests
- values.yaml for configuration
- charts/ for dependencies

### Infrastructure as Code

**Tools**:
- Kubernetes manifests (YAML)
- Helm charts for templating
- Kustomize for overlays
- Terraform for infrastructure

---

## Monitoring & Observability

### Metrics

**Prometheus Endpoints**:
- `/metrics` - All services expose Prometheus metrics
- Standard metric types: Counter, Gauge, Histogram

**Key Metrics**:
- Request latency
- Error rates
- Connection counts
- Packet throughput
- Certificate expiration

### Logging

**Strategy**:
- Structured JSON logging
- Log levels: DEBUG, INFO, WARNING, ERROR
- Correlation IDs for request tracing
- Syslog for audit logs

### Health Checks

**Endpoints**:
- `/health` - Detailed health information
- `/healthz` - Kubernetes-compatible

---

## Compliance Checklist

Before committing:
- ✅ Code passes local linting
- ✅ Tests pass locally
- ✅ Coverage ≥80%
- ✅ Security scan passes
- ✅ No hardcoded secrets
- ✅ Error handling complete
- ✅ Logging appropriate
- ✅ Documentation updated

Before creating PR:
- ✅ Branch created from develop
- ✅ Commits are clean
- ✅ Commit messages clear

Before merging PR:
- ✅ All CI passes
- ✅ Approved by reviewer
- ✅ Conflicts resolved
- ✅ Documentation complete
- ✅ Release notes updated

---

## Tools Reference

| Tool | Languages | Purpose | Command |
|------|-----------|---------|---------|
| black | Python | Formatting | `black .` |
| flake8 | Python | Linting | `flake8 .` |
| mypy | Python | Type checking | `mypy .` |
| bandit | Python | Security | `bandit -r .` |
| pytest | Python | Testing | `pytest` |
| golangci-lint | Go | Linting | `golangci-lint run` |
| gosec | Go | Security | `gosec ./...` |
| go test | Go | Testing | `go test -race ./...` |
| ESLint | JavaScript | Linting | `npm run lint` |
| Prettier | JavaScript | Formatting | `npm run format` |
| TypeScript | JavaScript | Type checking | `npm run typecheck` |
| Jest | JavaScript | Testing | `npm test` |
| docker | All | Containerization | `docker build .` |

---

## References

- [Go Build Tags](https://golang.org/pkg/go/build/)
- [Fyne Framework](https://fyne.io/)
- [WireGuard](https://www.wireguard.com/)
- [Kubernetes CNI](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Helm Charts](https://helm.sh/docs/)
- [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Semantic Versioning](https://semver.org/)
- [REST API Best Practices](https://restfulapi.net/)
