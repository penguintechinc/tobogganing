# Tobogganing Project Development & CI/CD Standards

Development standards, code quality requirements, and CI/CD compliance for Tobogganing's multi-component SASE platform.

## Table of Contents

1. [Version Management](#version-management)
2. [Code Quality Standards](#code-quality-standards)
3. [Component-Specific Standards](#component-specific-standards)
4. [Security Standards](#security-standards)
5. [Testing Standards](#testing-standards)
6. [CI/CD Compliance](#cicd-compliance)
7. [Kubernetes & Infrastructure](#kubernetes--infrastructure)

## Version Management

### Version File Format

Tobogganing uses semantic versioning with Epoch64 timestamps: `vMajor.Minor.Patch.build`

**Examples**:
- `v1.2.0.1737803600` - Release with build metadata
- `v1.0.0.1737727200` - Initial release

**Version Increment Rules**:

| Type | Change | Example |
|------|--------|---------|
| Major | Breaking API changes, removed features | v1.x.x → v2.0.0 |
| Minor | New features, non-breaking enhancements | v1.0.x → v1.1.0 |
| Patch | Bug fixes, security updates | v1.0.0 → v1.0.1 |
| Build | Epoch64 timestamp for build identification | v1.0.0.1737727200 |

### Synchronized Component Versioning

All 8+ components share the same version:
- Manager, Headend, Docker Client, Native Clients
- K8s CNI Plugin, Frontend, Docs, Deployment configs

**Version File Location**: `.version` at project root

## Code Quality Standards

### Universal Requirements

All code MUST:
- ✅ Pass linting without exceptions
- ✅ Include comprehensive error handling
- ✅ Have appropriate logging
- ✅ Follow security-first design
- ✅ Have tests covering critical paths
- ✅ Avoid hardcoded credentials
- ✅ Use typed variables (strong typing)

### Python Standards (Manager, Docs)

**Version**: Python 3.12

**Required Tools**:
- black (code formatting)
- isort (import sorting)
- flake8 (linting)
- mypy (type checking)
- bandit (security)
- pytest (testing)

**Code Example**:

```python
"""Manager service API endpoints."""

from typing import Optional, Dict, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class User:
    """System user with role-based access."""
    id: str
    email: str
    roles: List[str]

async def create_user(email: str, roles: List[str]) -> User:
    """Create new system user.

    Args:
        email: User email address
        roles: List of role names

    Returns:
        Created User object

    Raises:
        ValueError: If email format invalid
    """
    if not email or '@' not in email:
        raise ValueError("Invalid email format")

    user = User(id=generate_id(), email=email, roles=roles)
    logger.info(f"Created user: {user.id}")
    return user
```

**Standards**:
- PEP 8 code style
- PEP 257 docstrings
- PEP 484 type hints (mandatory)
- 80%+ test coverage
- Async/await patterns for I/O
- PyDAL for database abstraction

### Go Standards (Headend, Clients, K8s CNI)

**Version**: Go 1.23+

**Required Tools**:
- golangci-lint
- gosec
- go fmt
- go vet
- go test

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
    Status(ctx context.Context) (ConnectionStatus, error)
}

// Connect establishes WireGuard tunnel
func (c *Client) Connect(ctx context.Context, ep Endpoint) error {
    if ep.IP == "" || ep.Port == 0 {
        return errors.New("invalid endpoint")
    }

    log.Printf("Connecting to %s:%d", ep.IP, ep.Port)
    // Implementation
    return nil
}
```

**Standards**:
- gofmt formatting
- Error handling mandatory
- Interface-based design
- 80%+ test coverage
- Race detector: `go test -race`
- Cross-compilation support

**Build Tags for Conditional Compilation**:
```go
// GUI builds (default)
// +build !nogui

// Headless builds (servers, embedded)
// +build nogui

// Platform-specific
// +build linux,amd64
```

### JavaScript/Node.js Standards (Frontend, Website)

**Version**: Node.js 18+, TypeScript

**Required Tools**:
- ESLint
- Prettier
- TypeScript
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
                const response = await fetch('/api/v1/tunnels/status');
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

## Component-Specific Standards

### Manager Service (Python 3.12)

**Responsibilities**:
- User and organization management
- Client orchestration
- Certificate lifecycle
- API endpoints
- Authentication/authorization
- Audit logging
- Metrics collection

**Key Requirements**:
- RESTful API design
- Role-based access control (RBAC)
- Database migrations
- Comprehensive logging
- Prometheus metrics endpoint
- Health check endpoints (/health, /healthz)

**Database**:
- PyDAL for database abstraction
- PostgreSQL/MySQL support
- Connection pooling
- Transaction management

### Headend Server (Go 1.23)

**Responsibilities**:
- WireGuard tunnel termination
- User/service authentication
- Traffic routing and proxying
- Traffic mirroring for IDS
- Health monitoring
- Connection logging

**Key Requirements**:
- High-performance networking
- Goroutine-based concurrency
- Proper resource cleanup
- Non-blocking I/O
- Connection pooling
- Memory management optimization

**Protocols**:
- WireGuard for VPN
- TCP/UDP proxying
- VXLAN/GRE for mirroring
- syslog for audit

### Native Clients (Go 1.23)

**Dual Build Architecture**:

**GUI Builds** (Desktop):
- Fyne framework
- System tray integration
- Configuration UI
- Real-time status display
- Requires: libayatana-appindicator, libgtk-3, webkit2gtk

**Headless Builds** (Servers):
- CLI interface
- Daemon mode
- Configuration via files/env
- Minimal dependencies
- Static compilation

**Cross-Platform**:
- macOS: Universal binaries (Intel + Apple Silicon)
- Linux: amd64, arm64
- Windows: amd64, arm64

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

## Testing Standards

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

## CI/CD Compliance

### Mandatory Checks

✅ **Must Pass**:
- Linting (black, flake8, golangci-lint, ESLint)
- Type checking (mypy, TypeScript)
- Unit tests (pytest, go test, Jest)
- Security scanning (bandit, gosec, Trivy)
- Coverage thresholds (80%+)
- Docker builds (all components)

❌ **Prohibited**:
- Committed build artifacts
- Disabled security checks
- Skipped failing tests
- Hardcoded configuration
- Passwords in code

### Pull Request Requirements

Before merge to main:
1. ✅ All CI checks pass
2. ✅ Code review approval (minimum 1)
3. ✅ Security scan passes
4. ✅ Test coverage ≥80%
5. ✅ Documentation updated
6. ✅ Version bumped (if applicable)

### Release Workflow

1. Update `.version` file with Epoch64 timestamp
2. Update `docs/RELEASE_NOTES.md`
3. Create PR to main
4. All CI checks must pass
5. Merge to main (triggers release)
6. Workflows publish all artifacts

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

**CNI Integration**:
- Implements Kubernetes CNI spec 1.0.0
- Per-pod WireGuard tunnels
- Automatic IP allocation
- Network namespace management
- Route configuration

### Helm Chart Standards

**Structure**:
- Chart.yaml with version sync
- templates/ for K8s manifests
- values.yaml for configuration
- charts/ for dependencies
- Documentation in README

### Infrastructure as Code

**Tools**:
- Kubernetes manifests (YAML)
- Helm charts for templating
- Kustomize for overlays
- Terraform for infrastructure

## Monitoring & Observability

### Metrics

**Prometheus Endpoints**:
- `/metrics` - All services expose Prometheus metrics
- Standard metric types: Counter, Gauge, Histogram
- Custom application metrics

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
- Cloud logging integration

### Health Checks

**Endpoints**:
- `/health` - Detailed health information
- `/healthz` - Kubernetes-compatible (OK/fail)
- Database connectivity
- Service dependencies
- Certificate validity

## Documentation Standards

### Code Comments

**Python**:
```python
# Explain WHY, not WHAT
total = sum(values)  # Use built-in sum() for O(n) efficiency
```

**Go**:
```go
// Connect establishes WireGuard tunnel to endpoint
// Uses UDP for efficient packet transmission
func (c *Client) Connect(ctx context.Context, ep Endpoint) error {
```

### API Documentation

Required:
- Endpoint descriptions
- Request/response examples
- Authentication requirements
- Error codes and meanings
- Rate limiting details

## Compliance Checklist

Before committing:
- ✅ Code passes local linting
- ✅ Tests pass locally (all affected components)
- ✅ Coverage ≥80%
- ✅ Security scan passes locally
- ✅ No hardcoded secrets
- ✅ Error handling complete
- ✅ Logging appropriate
- ✅ Documentation updated
- ✅ Related issues linked
- ✅ Version updated (if applicable)

Before creating PR:
- ✅ Branch created from develop
- ✅ All commits are clean and squashed
- ✅ Commit messages clear and descriptive
- ✅ All related tests included

Before merging PR:
- ✅ All CI passes (Manager, Headend, Clients, K8s CNI, Frontend, Docs)
- ✅ Approved by reviewer
- ✅ Conflicts resolved
- ✅ Documentation complete
- ✅ Release notes updated

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
