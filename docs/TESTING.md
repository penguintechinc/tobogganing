# Tobogganing - Testing and Validation Guide

This document covers testing strategies, tools, and procedures for the Tobogganing project across all three services and integration points.

## Testing Philosophy

Every change to Tobogganing must be validated at multiple levels:

1. **Unit tests** verify individual functions and components in isolation
2. **Integration tests** verify communication between services (gRPC, REST, database)
3. **End-to-end tests** verify complete user workflows through the full stack
4. **Smoke tests** provide fast verification that builds are functional
5. **Performance tests** ensure the data plane meets throughput requirements
6. **Security scans** catch vulnerabilities before they reach production

## Mock Data Scripts

All test environments should be populated with realistic mock data using:

```bash
make seed-mock-data
```

This creates 3-4 items per feature following the project template standard:

### Users (4 items)

| Email | Role | Purpose |
|-------|------|---------|
| admin@example.com | Admin | Full platform access, user management |
| maintainer@example.com | Maintainer | Read/write access, no user management |
| viewer@example.com | Viewer | Read-only access |
| contractor@example.com | Viewer | External user, limited group membership |

### Groups (3 items)

| Name | Members | Purpose |
|------|---------|---------|
| Engineering | admin, maintainer | Internal engineering team |
| Operations | admin, maintainer | Infrastructure operations |
| Contractors | contractor | External contractor access |

### Hubs (3 items)

| Name | Region | Status |
|------|--------|--------|
| hub-us-east-1 | US East (Virginia) | Active |
| hub-eu-west-1 | EU West (Ireland) | Active |
| hub-ap-southeast-1 | AP Southeast (Singapore) | Active |

### Policies (4 items)

| Name | Dimensions | Action |
|------|-----------|--------|
| Allow-Web | Ports 80, 443; all users | Allow |
| Block-Social | Domains *.facebook.com, *.tiktok.com; all users | Deny |
| Engineering-Internal | Group: Engineering; CIDR: 10.0.0.0/8 | Allow |
| Contractor-Limited | Group: Contractors; Ports 443 only; Domains: *.corp.example.com | Allow |

### Clients (3 items)

| Name | Platform | Hub Assignment |
|------|----------|----------------|
| dev-laptop-linux | Linux AMD64 | hub-us-east-1, hub-eu-west-1 |
| ops-workstation-mac | macOS ARM64 | hub-us-east-1, hub-ap-southeast-1 |
| contractor-device | Windows AMD64 | hub-eu-west-1 |

## Smoke Tests

Smoke tests provide fast build verification and should complete in under 2 minutes.

```bash
make smoke-test
```

The smoke test suite (`tests/smoke/run-smoke-tests.sh`) verifies:

1. **Build verification**: All three services build without errors
2. **Container start**: Docker images start and pass health checks
3. **API health**: hub-api responds to `/healthz` endpoint
4. **Hub Router health**: hub-router responds on the health port
5. **WebUI loads**: hub-webui serves the index page
6. **Database connectivity**: hub-api can connect to the database
7. **Redis connectivity**: hub-api can connect to Redis

### Running Smoke Tests Individually

```bash
# Build verification only
cd services/hub-api && python -c "import app" && echo "hub-api: OK"
cd services/hub-router && go build ./proxy && echo "hub-router: OK"
cd services/hub-webui && npm run build && echo "hub-webui: OK"

# Health endpoint check (requires running services)
curl -sf http://localhost:8080/healthz && echo "hub-api: healthy"
curl -sf http://localhost:9090/health && echo "hub-router: healthy"
curl -sf http://localhost:3000 > /dev/null && echo "hub-webui: healthy"
```

## Unit Tests

### hub-api (pytest-asyncio)

The hub-api uses pytest with pytest-asyncio for testing async Quart endpoints.

**Running all hub-api tests:**
```bash
make test-hub-api
# or directly:
cd services/hub-api && python -m pytest tests/ -v --cov=.
```

**Running specific test files:**
```bash
cd services/hub-api
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_policies.py -v
python -m pytest tests/test_users.py -v
```

**Running with coverage report:**
```bash
cd services/hub-api
python -m pytest tests/ --cov=. --cov-report=html
# Open htmlcov/index.html
```

**Test conventions for hub-api:**
- Test files are named `test_*.py` in `services/hub-api/tests/`
- Use `@pytest.mark.asyncio` for async test functions
- Use `pytest.fixture` for shared test setup (app client, database fixtures)
- Mock external dependencies (Redis, license server) in unit tests
- Coverage target: 80% minimum for new code

**Example test structure:**
```python
import pytest
from app import create_app

@pytest.fixture
async def client():
    app = create_app(testing=True)
    async with app.test_client() as client:
        yield client

@pytest.mark.asyncio
async def test_healthz(client):
    response = await client.get("/healthz")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_create_policy_requires_auth(client):
    response = await client.post("/api/v1/policies", json={"name": "test"})
    assert response.status_code == 401
```

### hub-router (go test -race)

The hub-router uses Go's built-in testing framework with race detection.

**Running all hub-router tests:**
```bash
make test-hub-router
# or directly:
cd services/hub-router && go test -v -race ./...
```

**Running specific packages:**
```bash
cd services/hub-router
go test -v -race ./internal/policy/...
go test -v -race ./internal/dataplane/...
go test -v -race ./internal/api/...
```

**Running with coverage:**
```bash
cd services/hub-router
go test -v -race -coverprofile=coverage.out ./...
go tool cover -html=coverage.out -o coverage.html
```

**Running benchmarks:**
```bash
cd services/hub-router
go test -bench=. -benchmem ./internal/dataplane/...
go test -bench=. -benchmem ./internal/policy/...
```

**Test conventions for hub-router:**
- Test files are `*_test.go` alongside source files
- Always use `-race` flag to detect data races
- Use table-driven tests for multiple scenarios
- Mock gRPC connections for policy engine tests
- Benchmark critical paths (policy evaluation, packet processing)
- Coverage target: 80% minimum for new code

### hub-webui (vitest)

The hub-webui uses Vitest with React Testing Library.

**Running all hub-webui tests:**
```bash
make test-hub-webui
# or directly:
cd services/hub-webui && npx vitest --run
```

**Running in watch mode:**
```bash
cd services/hub-webui
npx vitest
```

**Running specific test files:**
```bash
cd services/hub-webui
npx vitest --run src/components/PolicyEditor.test.tsx
npx vitest --run src/pages/Dashboard.test.tsx
```

**Running with coverage:**
```bash
cd services/hub-webui
npx vitest --run --coverage
```

**Test conventions for hub-webui:**
- Test files are `*.test.tsx` or `*.test.ts` alongside source files
- Use React Testing Library for component tests
- Use `@testing-library/jest-dom` for DOM assertions
- Mock API calls with MSW or Vitest mocks
- Test user interactions, not implementation details
- Coverage target: 75% minimum for new code

## Integration Tests

Integration tests verify communication between Tobogganing services.

### gRPC Communication Tests

Verify that hub-api and hub-router communicate correctly over gRPC:

```bash
cd tests/integration
python -m pytest test_grpc_policy_stream.py -v
```

**What is tested:**
- Policy stream establishment between hub-api and hub-router
- Policy update delivery and acknowledgment
- Connection recovery after disconnection
- Certificate distribution via gRPC
- Status reporting from hub-router to hub-api

### API Flow Tests

Verify end-to-end API workflows:

```bash
cd tests/integration
python -m pytest test_api_flows.py -v
```

**What is tested:**
- User registration and authentication flow
- Policy CRUD operations and versioning
- Hub registration and health reporting
- Client registration and certificate issuance
- Role-based access control enforcement

### Policy Enforcement Tests

Verify that policies created in hub-api are enforced in hub-router:

```bash
cd tests/integration
python -m pytest test_policy_enforcement.py -v
```

**What is tested:**
- Domain-based allow/deny rules
- Port-based filtering
- IP CIDR matching
- User and group-based access control
- Policy update propagation latency

### Running All Integration Tests

```bash
make test-integration
```

**Prerequisites for integration tests:**
- All three services must be running (use `make dev`)
- Mock data must be seeded (use `make seed-mock-data`)
- Network connectivity between services

## End-to-End Tests

E2E tests exercise complete user scenarios through the entire stack.

```bash
make test-e2e
```

### Test Scenarios

1. **New User Onboarding**: Admin creates user via WebUI, user receives credentials, user logs in
2. **Policy Lifecycle**: Create policy, verify enforcement, update policy, verify updated enforcement, delete policy
3. **Client Connection**: Register client, establish tunnel, verify connectivity, test failover
4. **Hub Management**: Add hub, verify router connects, assign clients, verify traffic flow
5. **License Gating**: Attempt OIDC configuration without license, verify rejection, add license, verify success

### Running E2E Tests

```bash
cd tests/e2e
python -m pytest -v --timeout=120
```

**Prerequisites for E2E tests:**
- Full stack running via Docker Compose
- Mock data seeded
- At least 5 minutes for full suite completion

## Performance Testing

### Packet Processing Benchmarks

Benchmark the hub-router data plane:

```bash
cd services/hub-router
# Policy evaluation benchmark
go test -bench=BenchmarkPolicyEvaluation -benchmem ./internal/policy/

# Packet processing benchmark
go test -bench=BenchmarkPacketProcess -benchmem ./internal/dataplane/

# NUMA pool allocation benchmark
go test -bench=BenchmarkNUMAAlloc -benchmem ./internal/dataplane/
```

### Performance Targets

| Metric | Target | Test Method |
|--------|--------|-------------|
| Policy evaluation latency | < 1 microsecond | Go benchmark |
| XDP fast-path throughput | > 10 Gbps | iperf3 through XDP path |
| AF_XDP slow-path throughput | > 1 Gbps | iperf3 through AF_XDP |
| API response time (p99) | < 100 ms | Load test with k6 or wrk |
| WebUI initial load | < 2 seconds | Lighthouse audit |
| gRPC policy update latency | < 50 ms | Integration test timing |

### Load Testing

For API load testing, use k6 or wrk:

```bash
# Install k6
# Run load test against hub-api
k6 run tests/performance/api_load_test.js

# Or with wrk
wrk -t4 -c100 -d30s http://localhost:8080/api/v1/health
```

## Security Scanning

Security scanning is mandatory before every commit.

### Python Security (hub-api)

```bash
# Static analysis for security issues
cd services/hub-api
python -m bandit -r . -x tests

# Dependency vulnerability check
pip-audit
```

### Go Security (hub-router)

```bash
# Static security analysis
cd services/hub-router
gosec ./...

# Dependency vulnerability check
go install golang.org/x/vuln/cmd/govulncheck@latest
govulncheck ./...
```

### JavaScript Security (hub-webui)

```bash
# Dependency vulnerability check
cd services/hub-webui
npm audit

# Fix automatically where possible
npm audit fix
```

### Container Security

```bash
# Scan all container images with Trivy
docker run --rm -v $(pwd):/workspace aquasec/trivy fs /workspace

# Scan individual images
docker run --rm aquasec/trivy image tobogganing/hub-api:latest
docker run --rm aquasec/trivy image tobogganing/hub-router:latest
docker run --rm aquasec/trivy image tobogganing/hub-webui:latest
```

### Running All Security Scans

```bash
make security-scan
```

## Test Organization

```
tests/
  smoke/
    run-smoke-tests.sh        # Fast build and health verification
  unit/
    (per-service tests are in services/*/tests/)
  integration/
    test_grpc_policy_stream.py # gRPC communication tests
    test_api_flows.py          # API workflow tests
    test_policy_enforcement.py # Policy enforcement verification
    conftest.py                # Shared fixtures
  e2e/
    test_user_onboarding.py    # Full user workflow
    test_policy_lifecycle.py   # Policy creation through enforcement
    test_client_connection.py  # Client tunnel and failover
    conftest.py                # E2E fixtures and setup
  performance/
    api_load_test.js           # k6 load test script
    benchmark_results/         # Stored benchmark baselines
```

## CI/CD Test Execution

Tests run automatically in GitHub Actions on pull requests and pushes:

1. **Lint** (all services in parallel)
2. **Unit tests** (all services in parallel)
3. **Build** (Docker images for all services)
4. **Integration tests** (requires built images)
5. **Security scan** (Trivy on images)

The full CI pipeline takes approximately 10-15 minutes. Smoke tests alone take under 2 minutes.

## Coverage Requirements

| Service | Minimum Coverage | Tool |
|---------|-----------------|------|
| hub-api | 80% | pytest-cov |
| hub-router | 80% | go test -cover |
| hub-webui | 75% | vitest --coverage |
| Integration | N/A (scenario-based) | pytest |

Coverage reports are generated in CI and can be viewed locally:

```bash
# hub-api
cd services/hub-api && python -m pytest --cov=. --cov-report=html tests/

# hub-router
cd services/hub-router && go test -coverprofile=coverage.out ./... && go tool cover -html=coverage.out

# hub-webui
cd services/hub-webui && npx vitest --run --coverage
```

## Testing Checklist

Before submitting a pull request, verify:

- [ ] All unit tests pass: `make test-unit`
- [ ] No race conditions: hub-router tests run with `-race`
- [ ] Integration tests pass (if inter-service changes): `make test-integration`
- [ ] Security scans clean: `make security-scan`
- [ ] Coverage meets minimums for changed code
- [ ] Mock data seeds correctly: `make seed-mock-data`
- [ ] Smoke tests pass: `make smoke-test`
