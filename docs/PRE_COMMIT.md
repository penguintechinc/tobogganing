# Pre-Commit Checklist - Tobogganing

**CRITICAL: This checklist MUST be followed before every commit.**

## Automated Pre-Commit Script

**Run the automated pre-commit script to execute all checks:**

```bash
./scripts/pre-commit/pre-commit.sh
```

This script will:
1. Run all checks in the correct order
2. Log output to `/tmp/pre-commit-tobogganing-<epoch>.log`
3. Provide a summary of pass/fail status
4. Echo the log file location for review

**Individual check scripts** (run separately if needed):
- `./scripts/pre-commit/check-python.sh` - Python linting & security
- `./scripts/pre-commit/check-go.sh` - Go linting & security
- `./scripts/pre-commit/check-node.sh` - Node.js/React linting, audit & build
- `./scripts/pre-commit/check-security.sh` - All security scans
- `./scripts/pre-commit/check-secrets.sh` - Secret detection
- `./scripts/pre-commit/check-docker.sh` - Docker build & validation
- `./scripts/pre-commit/check-tests.sh` - Unit tests
- `./scripts/pre-commit/check-vpn.sh` - VPN connectivity tests

---

## Required Steps (In Order)

Before committing, run in this order (or use `./scripts/pre-commit/pre-commit.sh`):

### Foundation Checks
- [ ] **Linters**: `npm run lint` or `golangci-lint run` or equivalent
- [ ] **Security scans**: `npm audit`, `gosec`, `bandit` (per language)
- [ ] **No secrets**: Verify no credentials, API keys, or tokens in code

### Build & Integration Verification
- [ ] **Build & Run**: Verify code compiles and containers start successfully
- [ ] **Smoke tests** (mandatory, <2 min): `make smoke-test`
  - All containers build without errors
  - All containers start and remain healthy
  - All API health endpoints respond with 200 status
  - WireGuard interfaces initialize successfully
  - Web pages load without JavaScript errors
  - See: [Testing Documentation - Smoke Tests](TESTING.md#smoke-tests)

### VPN Testing (Tobogganing-Specific)
- [ ] **WireGuard Tests**: `make test-vpn`
  - WireGuard interface creation and teardown
  - Peer management (add/remove)
  - Certificate validation
  - Basic tunnel connectivity
- [ ] **VPN Integration Tests** (if modifying Manager or Headend)
  - Client registration flow
  - Certificate issuance
  - Tunnel establishment
  - Policy enforcement

### Feature Testing & Documentation
- [ ] **Mock data** (for testing features): Ensure 3-4 test items per feature via `make seed-mock-data`
  - Populate development database with realistic test data
  - Needed before capturing screenshots and UI testing
  - See: [Testing Documentation - Mock Data Scripts](TESTING.md#mock-data-scripts)
- [ ] **Screenshots** (for UI changes): `node scripts/capture-screenshots.cjs`
  - Requires running `make dev` and `make seed-mock-data` first
  - Screenshots should showcase features with realistic mock data
  - Automatically removes old screenshots, captures fresh ones
  - Commit updated screenshots with feature/UI changes

### Comprehensive Testing
- [ ] **Unit tests**: `npm test`, `go test ./...`, `pytest`
  - Network isolated, mocked dependencies
  - Must pass before committing
- [ ] **Integration tests**: Component interaction verification
  - Tests with real database and service communication
  - VPN tunnel establishment and traffic routing
  - See: [Testing Documentation - Integration Tests](TESTING.md#integration-tests)

### Finalization
- [ ] **Version updates**: Update `.version` if releasing new version
- [ ] **Documentation**: Update docs if adding/changing workflows
- [ ] **Docker builds**: Verify Dockerfile uses debian-slim base (no alpine)
- [ ] **Cross-architecture**: (Optional) Test alternate architecture with QEMU
  - `docker buildx build --platform linux/arm64 .` (if on amd64)
  - `docker buildx build --platform linux/amd64 .` (if on arm64)
  - See: [Testing Documentation - Cross-Architecture Testing](TESTING.md#cross-architecture-testing)

---

## Language-Specific Commands

### Python (Manager Service)

```bash
# Linting
flake8 services/api-server/
black --check services/api-server/
isort --check services/api-server/
mypy services/api-server/

# Security
bandit -r services/api-server/
safety check

# Build & Run
python -m py_compile services/api-server/**/*.py  # Syntax check
pip install -r services/api-server/requirements.txt
python -m app.main &  # Verify it starts (then kill)

# Tests
cd services/api-server && pytest
```

### Go (Headend, Clients, K8s CNI)

```bash
# Linting
golangci-lint run ./...

# Security
gosec ./...

# Build & Run
go build ./...                       # Compile all packages
go run ./cmd/hub-node/main.go &     # Verify it starts (then kill)

# Tests
go test ./...
go test -tags=integration ./...     # Integration tests
```

### Node.js / JavaScript / TypeScript / ReactJS (WebUI)

```bash
# Linting
npm run lint
# or
npx eslint .

# Security (REQUIRED)
npm audit                          # Check for vulnerabilities
npm audit fix                      # Auto-fix if possible

# Build & Run
npm run build                      # Compile/bundle
npm start &                        # Verify it starts (then kill)

# Tests
npm test
npm run test:integration           # Integration tests
```

### Docker / Containers

```bash
# Lint Dockerfiles
hadolint Dockerfile

# Verify base image (debian-slim, NOT alpine)
grep -E "^FROM.*slim" services/*/Dockerfile

# Build & Run
docker build -t myservice:test services/myservice/        # Build image
docker run -d --name test-container myservice:test        # Start container
docker logs test-container                                # Check for errors
docker stop test-container && docker rm test-container    # Cleanup

# Docker Compose (if applicable)
docker-compose -f docker-compose.dev.yml build            # Build all services
docker-compose -f docker-compose.dev.yml up -d            # Start all services
docker-compose -f docker-compose.dev.yml logs             # Check for errors
docker-compose -f docker-compose.dev.yml down             # Cleanup
```

---

## WireGuard/VPN Specific Checks

### For Manager Service Changes

```bash
# Verify API endpoints exist
curl http://localhost:5000/api/v1/clients
curl http://localhost:5000/api/v1/headends
curl http://localhost:5000/api/v1/certificates

# Test authentication flow
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password"}'

# Test client registration
curl -X POST http://localhost:5000/api/v1/clients/register \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test-key"}'
```

### For Headend Service Changes

```bash
# Verify WireGuard interface initializes
docker-compose exec hub-node ip link show wg0

# Check WireGuard configuration
docker-compose exec hub-node wg show

# Test service responds to health checks
curl http://localhost:8080/health
```

### For Client Changes

```bash
# Verify client builds on all platforms
go build -o client-linux ./cmd/client
GOOS=darwin GOARCH=amd64 go build -o client-darwin-amd64 ./cmd/client
GOOS=windows GOARCH=amd64 go build -o client-windows.exe ./cmd/client

# Test client registration and connection
./client-linux register --api-key test-key
./client-linux connect
```

### For K8s CNI Plugin Changes

```bash
# Build CNI plugin
go build -o bin/tobogganing-cni ./cmd/plugin

# Verify plugin follows CNI spec
chmod +x bin/tobogganing-cni

# Test in Kubernetes (if cluster available)
kubectl apply -f deploy/k8s/daemonset.yaml
```

---

## Commit Rules

- **NEVER commit automatically** unless explicitly requested by the user
- **NEVER push to remote repositories** under any circumstances
- **ONLY commit when explicitly asked** - never assume commit permission
- **Wait for approval** before running `git commit`

---

## Security Scanning Requirements

### Before Every Commit
- **Run security audits on all modified packages**:
  - **Go packages**: Run `gosec ./...` on modified Go services
  - **Node.js packages**: Run `npm audit` on modified Node.js services
  - **Python packages**: Run `bandit -r .` and `safety check` on modified Python services
- **Do NOT commit if security vulnerabilities are found** - fix all issues first
- **Document vulnerability fixes** in commit message if applicable

### Vulnerability Response
1. Identify affected packages and severity
2. Update to patched versions immediately
3. Test updated dependencies thoroughly
4. Document security fixes in commit messages
5. Verify no new vulnerabilities introduced

### Specific Security Checks for Tobogganing

**Certificate Security**:
- [ ] No private keys in source code or logs
- [ ] Certificate expiration is validated
- [ ] Key rotation works correctly
- [ ] Revoked certificates are properly handled

**WireGuard Security**:
- [ ] Pre-shared keys (if used) are never hardcoded
- [ ] Private keys are stored securely (not in git)
- [ ] Interface names don't leak sensitive info
- [ ] Peer additions/removals are authenticated

**Authentication Security**:
- [ ] JWT tokens have proper expiration
- [ ] Token signing keys are protected
- [ ] Password hashing uses bcrypt with proper cost
- [ ] Session tokens are invalidated on logout

---

## API Testing Requirements

Before committing changes to container services:

- **Create and run API testing scripts** for each modified service
- **Testing scope**: All new endpoints and modified functionality
- **Test files location**: `tests/api/` directory with service-specific subdirectories
  - `tests/api/manager/` - Manager API tests
  - `tests/api/headend/` - Headend API tests
  - `tests/api/webui/` - WebUI tests
- **Run before commit**: Each test script should be executable and pass completely
- **Test coverage**: Health checks, authentication, CRUD operations, error cases

### Manager API Tests
```bash
# Test client endpoints
curl -H "Authorization: Bearer $JWT" http://localhost:5000/api/v1/clients
curl -H "Authorization: Bearer $JWT" http://localhost:5000/api/v1/clients/\{id\}

# Test headend endpoints
curl -H "Authorization: Bearer $JWT" http://localhost:5000/api/v1/headends

# Test authentication
curl -X POST http://localhost:5000/api/v1/auth/login

# Test permission/RBAC
curl -H "Authorization: Bearer $VIEWER_JWT" http://localhost:5000/api/v1/admin/settings
# Should return 403 Forbidden for non-admin users
```

### Headend API Tests
```bash
# Test health endpoint
curl http://localhost:8080/health

# Test metrics endpoint
curl http://localhost:8080/metrics

# Test WireGuard status
curl http://localhost:8080/status
```

---

## Screenshot & Mock Data Requirements

### Prerequisites
Before capturing screenshots, ensure development environment is running with mock data:

```bash
make dev                   # Start all services
make seed-mock-data       # Populate with 3-4 test items per feature
```

### Capture Screenshots
For all UI changes, update screenshots to show current application state with realistic data:

```bash
node scripts/capture-screenshots.cjs
# Or via npm script if configured: npm run screenshots
```

### What to Screenshot
- **Login page** (unauthenticated state)
- **Dashboard** (with mock clients and headends)
- **Client list** (with 3-4 representative clients in different states)
- **Headend monitor** (with regional headends)
- **Policy management** (with example policies)
- **User/role management** (with different user types)
- **Connection status** (showing active tunnels and statistics)
- **Empty states** vs populated views

### Commit Guidelines
- Automatically removes old screenshots and captures fresh ones
- Commit updated screenshots with relevant feature/UI/documentation changes
- Screenshots demonstrate feature purpose and functionality
- Helpful error message if login fails: "Ensure mock data is seeded"

---

## VPN-Specific Pre-Commit Checklist

When making changes to VPN-related code (Manager, Headend, Clients, K8s CNI):

```
VPN Feature Changes:
- [ ] WireGuard interface initialization works
- [ ] Peer management (add/remove/list) functions correctly
- [ ] Certificates are generated and validated
- [ ] JWT tokens are properly signed and validated
- [ ] Traffic routing respects policies
- [ ] Connection limits are enforced
- [ ] Reconnection after disconnect works
- [ ] Failover to backup headend works (if applicable)
- [ ] Multi-client concurrent connections work
- [ ] Memory usage stays within limits
- [ ] No hardcoded credentials or keys
- [ ] Logging doesn't leak sensitive info
```

---

## Troubleshooting Pre-Commit Failures

### Linting Failures
```bash
# Auto-fix Python linting
black services/api-server/
isort services/api-server/

# Auto-fix JavaScript linting
npm run lint -- --fix

# Check Go linting
golangci-lint run ./... --fix
```

### Build Failures
```bash
# Docker build issues
docker build --no-cache services/api-server/  # Rebuild without cache

# Dependency issues
pip install --upgrade -r services/api-server/requirements.txt
npm install && npm update
go mod tidy && go mod download
```

### Test Failures
```bash
# Run failing tests with verbose output
pytest -vv tests/unit/
go test -v ./...
npm test -- --verbose

# Debug VPN tests
docker-compose logs hub-node
docker-compose logs native-client
```

### Security Scan Failures
```bash
# Update vulnerable packages
npm audit fix --force
pip install --upgrade vulnerable-package==safe-version
go get -u vulnerable-module

# Review and document fixes
# Commit message should reference CVE/advisory
```

---

## Quick Reference Checklist

**Before Every Commit**:
```
⚠️  = Critical (blocks commit)
⚡ = Important (should fix)
📝 = Optional (nice to have)

⚠️  Linters pass (flake8, golangci-lint, eslint)
⚠️  Security scans pass (bandit, gosec, npm audit)
⚠️  No secrets in code
⚠️  Smoke tests pass (<2 min)
⚠️  Unit tests pass
⚠️  VPN tests pass (if VPN code modified)
⚡ Integration tests pass
⚡ Screenshots updated (UI changes)
⚡ Mock data created (new features)
⚡ Documentation updated
📝 Cross-architecture build passes (optional)
📝 Performance still acceptable
```

---

**Last Updated**: 2026-01-06
**Maintained by**: Penguin Tech Inc
