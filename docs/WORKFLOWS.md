# Tobogganing Project CI/CD Workflows

Complete documentation for Tobogganing's multi-component CI/CD pipeline with `.WORKFLOW` compliance standards.

## Project Overview

Tobogganing is a comprehensive SASE/Zero Trust solution with containerized server-side components — end-user clients now live in the separate `penguin` project:

**Core Components**:
1. **Manager** (Python 3.12) - Orchestration and API
2. **Headend** (Go 1.23) - WireGuard termination
3. **K8s CNI Plugin** (Go 1.23) - Kubernetes networking
4. **Frontend Website** (Node.js 18) - Marketing site
5. **Documentation Site** (MkDocs) - Technical docs
6. **Deployment Configs** (K8s/Helm) - Infrastructure

## Workflow Architecture

### Primary Workflows

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| CI/CD Pipeline | `.github/workflows/ci.yml` | Push/PR | All component testing and security |
| Version Monitoring | `.github/workflows/version-monitor.yml` | .version changes | Version validation and consistency |
| Version Release | `.github/workflows/version-release.yml` | .version push main | Automated release creation |
| Push | `.github/workflows/push.yml` | Push main | Docker registry push |
| Release | `.github/workflows/release.yml` | GitHub release | Release artifact publishing |
| Cron | `.github/workflows/cron.yml` | Daily 2 AM UTC | Scheduled maintenance |

## .WORKFLOW Compliance Implementation

### Version Management System

**Format**: `vMajor.Minor.Patch.build` (e.g., `v1.2.0.1737803600`)

**Version Monitoring (version-monitor.yml)**:
- Validates semantic versioning format
- Checks Epoch64 timestamp for build identification
- Verifies all 8+ components support version
- Scans Python/Go security in version context
- Logs version metadata to workflow runs

**Component Verification**:
- Manager: `manager/app.py`, `requirements.txt`
- Headend: `headend/go.mod`, `proxy/` package
- K8s CNI: `k8s-cni/go.mod`, `cmd/tobogganing-cni/`
- Frontend: `website/package.json`, `src/` directory

## Comprehensive CI/CD Workflow

### ci.yml: Multi-Component Testing

**Jobs** (with parallel execution):

1. **test-manager** (Python 3.12)
   - Cache pip dependencies
   - pylint linting
   - mypy type checking
   - pytest unit tests
   - Coverage upload to Codecov

2. **test-headend** (Go 1.23)
   - Cache Go modules
   - golangci-lint analysis
   - go test with race detector
   - Coverage upload to Codecov

3. **security-scan**
   - bandit: Python code analysis (manager/)
   - gosec: Go security (headend, K8s CNI)
   - Trivy: Filesystem vulnerability scan
   - GitHub Security tab integration

4. **build-images** (Parallel Docker builds)
   - Manager (Python container)
   - Headend (Go container)
   - Multi-arch: linux/amd64, linux/arm64
   - Docker layer caching

5. **integration-test**
   - Multi-component interaction
   - Docker Compose test environment
   - Health endpoint validation
   - Connectivity verification

## Security Scanning Standards

### Python Security (bandit)

**Scope**: manager/ directory

**Detection**:
```bash
pip install bandit[toml]
bandit -r manager --format json
```

Covers:
- Hardcoded credentials
- Weak cryptography
- SQL injection patterns
- Insecure deserialization
- YAML parsing vulnerabilities

### Go Security (gosec)

**Scope**: headend/, k8s-cni/

**Detection**:
```bash
gosec -no-fail -fmt json ./headend ./k8s-cni
```

Covers:
- SQL injection risks
- Weak cryptography
- Hardcoded credentials
- Command injection
- TLS misconfiguration

### Filesystem Scanning (Trivy)

**Scope**: Entire repository

**Detects**:
- Vulnerable dependencies
- Container image risks
- Configuration issues
- Known CVEs

## Testing Strategy

### Unit Tests

**Manager (Python)**:
- pytest framework
- Service mocking
- API endpoint tests
- Database transaction tests
- Auth system tests
- Coverage: 80%+ target

**Headend (Go)**:
- Go testing
- Race detector enabled
- WireGuard mock tests
- Proxy function tests
- Coverage: 80%+ target

**K8s CNI (Go)**:
- Go testing
- CNI command parsing
- Network allocation tests
- Interface management tests

**Frontend (Node.js)**:
- Jest framework
- Component tests
- Integration tests
- UI interaction tests
- Coverage: 80%+ target

### Integration Tests

After unit tests pass:
- Multi-component interaction
- Docker Compose environment
- Manager → Headend communication
- Client → Headend connectivity
- CNI plugin with K8s simulation
- Database operations
- Cache operations

### Docker Testing

Validates all container builds:
- Image builds successfully
- Required binaries present
- Correct language versions
- Service ports accessible
- Health check endpoints respond

## Multi-Architecture Docker Builds

### Build Matrix

**Parallel Strategy**:
- Manager image: linux/amd64, linux/arm64
- Headend image: linux/amd64, linux/arm64

**Optimization**:
- Docker Buildx with QEMU
- GitHub Actions cache
- Layer caching across builds
- Minimal image sizes (debian-slim base)

### Docker Image Tagging

**Naming Convention**:
- Development: `tobogganing-{component}:dev-{short-sha}`
- PR: `tobogganing-{component}:{version}-pr{number}`
- Release: `tobogganing-{component}:{version}`
- Latest: `tobogganing-{component}:latest` (main only)

**Registry Targets**:
- GHCR: `ghcr.io/penguintechinc/tobogganing`
- Docker Hub: `penguincloud/tobogganing` (optional)

## Environment Variables

### Build Environment

```yaml
GO_VERSION: '1.23'
PYTHON_VERSION: '3.12'
NODE_VERSION: '18'
REGISTRY: ghcr.io
```

### Component-Specific

**Manager**:
```bash
DATABASE_URL: postgresql://user:pass@localhost/tobogganing
REDIS_URL: redis://localhost:6379
JWT_SECRET: test-secret-key
METRICS_TOKEN: test-token
```

**Headend**:
```bash
WIREGUARD_PORT: 51820
API_PORT: 8080
TRAFFIC_MIRROR_ENABLED: false
SYSLOG_ENABLED: false
```

## Release Process

### Version File Updates

1. **Update .version**:
   ```
   v1.2.0.1737803600
   ```

2. **Update docs/RELEASE_NOTES.md**:
   - Prepend new release section
   - Document all changes
   - Include platform-specific notes

3. **Create Pull Request**:
   - Title: "Release v1.2.0"
   - Description: Version details
   - Link related issues

4. **Merge to main**:
   - All CI checks must pass
   - Code review approval required

5. **Automatic Release**:
   - version-release.yml creates GitHub Release
   - Workflows publish all artifacts
   - Docker images pushed to registries

### Release Artifacts

**Produced by workflows**:
- Manager Docker image
- Headend Docker image
- Release notes (Markdown)
- Checksums (SHA256)

## Dependency Management

### Python (Manager)

**Scanning**:
```bash
pip install safety
safety check
```

**Tools**: bandit, pylint, mypy

### Go (All Go components)

**Scanning**:
```bash
go mod audit
gosec ./...
```

**Tools**: golangci-lint, gosec

### Node.js (Frontend)

**Scanning**:
```bash
npm audit
npm audit fix
```

## Performance Optimization

### Caching Strategies

- Go modules: `~/go/pkg/mod` cached
- Python packages: `~/.cache/pip` cached
- Docker layer cache via GitHub Actions
- npm cache via actions/setup-node

### Parallel Execution

- Unit tests run simultaneously
- Docker builds run in parallel
- Security scans independent of tests

### Build Time Targets

- CI pipeline: <15 minutes total
- Docker builds: <5 minutes per image
- Full workflow with artifacts: <20 minutes

## Local Development Workflow

### Pre-commit Checks

**Manager (Python)**:
```bash
cd manager
pip install -r requirements.txt
pip install pylint mypy pytest bandit[toml]
black . && isort .
pylint . && mypy . && bandit -r .
pytest
```

**Headend (Go)**:
```bash
cd headend
go mod download
golangci-lint run
go test -v -race ./...
gosec ./...
```

**K8s CNI (Go)**:
```bash
cd k8s-cni
go mod download
golangci-lint run
go test -v -race ./...
gosec ./...
```

**Frontend (Node.js)**:
```bash
cd website
npm install
npm run lint && npm run format && npm run typecheck && npm test
```

## Troubleshooting

### Build Failures

**Manager Docker build fails**:
- Check Python 3.12 compatibility
- Verify base image has required libraries
- Check requirements.txt syntax

**Headend Docker build fails**:
- Verify Go 1.23 compatibility
- Check go.mod for correct versions
- Ensure all imports resolve

### Test Failures

**Python tests fail**:
- Check database setup
- Verify Redis connectivity
- Review environment variables

**Go tests fail**:
- Run with -race flag locally
- Check for timing dependencies
- Verify mock implementations

**Integration tests fail**:
- Check Docker Compose setup
- Verify service startup timing
- Check network connectivity

### Security Scan Issues

**False positives in bandit**:
- Add `# nosec: B101` to suppress
- Configure .bandit for exceptions

**False positives in gosec**:
- Add `// #nosec G101` to suppress
- Verify actual security issue

## Documentation

For comprehensive information:
- **docs/WORKFLOWS.md**: This file
- **docs/STANDARDS.md**: Code quality standards
- **docs/OVERVIEW.md**: Architecture overview
- **Manager**: `manager/README.md`
- **Headend**: `headend/README.md`
- **K8s CNI**: `k8s-cni/README.md`

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Buildx](https://docs.docker.com/buildx/working-with-buildx/)
- [QEMU Docker Support](https://github.com/tonistiigi/binfmt)
- [WireGuard Protocol](https://www.wireguard.com/)
- [Kubernetes CNI](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)
