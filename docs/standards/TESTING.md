# Testing Standards

Part of [Development Standards](../STANDARDS.md)

## Testing Phases

Testing is organized into three distinct phases aligned with the development workflow:

### Phase 1: Pre-Commit (Local Development)

**Location**: `tests/smoketests/`
**When**: Before every commit on developer machine
**Duration**: <2 minutes
**Purpose**: Fast validation before code enters repository

**What Runs**:
- Smoke tests (build, run, basic functionality)
- Quick sanity checks
- End-to-end build and runtime verification

**Execution**:
```bash
# Run via pre-commit script
./scripts/pre-commit/pre-commit.sh

# Or manually run smoke tests
./tests/smoketests/run-all.sh
```

**Requirements**:
- MUST pass before committing
- Runs on developer's local machine
- Uses local Docker containers
- Fast feedback loop (<2 min)

### Phase 2: CI/CD Pipeline (GitHub Actions)

**Location**: `.github/workflows/`
**When**: On every push/PR to GitHub
**Duration**: 5-15 minutes
**Purpose**: Comprehensive static validation

**What Runs**:
- Linters (flake8, eslint, golangci-lint, etc.)
- Unit tests (all languages)
- Compilation/build verification
- Security scans (gosec, bandit, npm audit, Trivy)
- Code quality checks (CodeQL)
- Multi-arch builds (amd64, arm64)

**Execution**: Automated via GitHub Actions

**Characteristics**:
- **Static analysis only** - no live deployment
- Runs in isolated GitHub Actions runners
- No external dependencies (databases, services)
- Mocked/stubbed external services
- Deterministic and repeatable
- Produces build artifacts (container images)

**Example Workflow Steps**:
```yaml
# .github/workflows/ci.yml
jobs:
  test:
    steps:
      - name: Lint
        run: make lint

      - name: Unit Tests
        run: make test-unit

      - name: Build
        run: make docker-build

      - name: Security Scan
        run: trivy image app:latest
```

### Phase 3: Deployment & Live Testing (K8s)

**Location**: `tests/deployment/` and `tests/live/`
**When**: Post-deployment validation
**Duration**: Variable (5-30 minutes)
**Purpose**: Verify live deployment in Kubernetes

**What Runs**:
- Deployment validation (pods running, services accessible)
- Live integration tests (real services, databases)
- End-to-end workflows (full system)
- Performance/load testing (optional)
- Health check verification

**Execution**:
```bash
# From developer machine (troubleshooting)
./tests/deployment/validate-k8s-deployment.sh

# Eventually in release CI/CD workflow (future)
# .github/workflows/release.yml
```

**Characteristics**:
- Tests against **live Kubernetes deployment**
- Real databases, services, and infrastructure
- Can be run from developer machine for troubleshooting
- Validates actual deployed state
- Currently manual, eventually automated in release workflow

**Use Cases**:
1. **Developer Troubleshooting**: Run from local machine to validate deployed app
2. **Manual QA**: Validate staging/beta deployments
3. **Future CI/CD**: Will be integrated into release workflow

**Example Deployment Test**:
```bash
#!/bin/bash
# tests/deployment/validate-k8s-deployment.sh

echo "=== Validating K8s Deployment ==="

# Check pods are running
kubectl get pods -n myapp | grep Running

# Check services are accessible
kubectl get svc -n myapp

# Test live API endpoint
curl -f https://myapp.penguintech.io/healthz

# Run live integration tests
kubectl exec -n myapp deploy/flask-backend -- pytest tests/live/
```

### Summary: Three-Phase Testing Strategy

| Phase | When | Where | Duration | Focus | Deployment |
|-------|------|-------|----------|-------|------------|
| **Phase 1: Pre-Commit** | Before commit | Dev machine | <2 min | Smoke tests, quick validation | Local Docker |
| **Phase 2: CI/CD** | On push/PR | GitHub Actions | 5-15 min | Linters, unit tests, builds, static analysis | No deployment |
| **Phase 3: Deployment** | Post-deploy | K8s cluster | 5-30 min | Live integration, E2E, performance | K8s deployment |

## Testing Requirements

### Smoke Tests (MANDATORY)

**CRITICAL: Smoke tests are REQUIRED before every commit**

Smoke tests verify basic functionality: build, run, API health, page/tab loads. These are quick validation tests (<2 minutes) that catch critical regressions.

#### Smoke Test Structure

**Standard Location:** `{PROJECT_ROOT}/tests/smoketests/{container_name}.sh`

Each container MUST have a corresponding smoke test script at this standardized location. Scripts can link to or pull in other test files from anywhere in the repo, but the entry point is always standardized.

**Example Structure:**
```
tests/
├── smoketests/
│   ├── flask-backend.sh      # Flask backend smoke tests
│   ├── go-backend.sh          # Go backend smoke tests
│   ├── webui.sh               # WebUI smoke tests
│   └── run-all.sh             # Runs all smoke tests
├── unit/                      # Unit tests (by language/service)
├── integration/               # Integration tests
└── e2e/                       # End-to-end tests
```

#### Smoke Test Requirements

Each smoke test script MUST verify:

1. **Build Verification**
   - Container builds successfully
   - No compilation errors
   - Dependencies resolve correctly

2. **Runtime Verification**
   - Container starts without errors
   - Process runs and doesn't crash
   - Listens on expected ports

3. **Unit Test Execution**
   - Basic unit tests pass
   - Core functionality validates
   - No critical failures

4. **Integration Test Execution**
   - Service-to-service communication works
   - Database connectivity successful
   - API contracts valid

5. **Page/Tab Load Tests** (for WebUI)
   - Main pages load without errors
   - All tabs/sections render
   - No JavaScript console errors
   - API calls to backend succeed

#### Example Smoke Test Scripts

**Flask Backend:** `tests/smoketests/flask-backend.sh`
```bash
#!/bin/bash
set -e

echo "=== Flask Backend Smoke Test ==="

# 1. Build verification
echo "Building container..."
docker build -t flask-backend:test ./services/flask-backend

# 2. Run container
echo "Starting container..."
CONTAINER_ID=$(docker run -d \
  -e DB_TYPE=sqlite \
  -e DB_NAME=test.db \
  flask-backend:test)

# Wait for startup
sleep 5

# 3. Health check
echo "Checking health endpoint..."
docker exec $CONTAINER_ID python3 -c "
import http.client
conn = http.client.HTTPConnection('localhost', 5000)
conn.request('GET', '/healthz')
r = conn.getresponse()
if r.status != 200:
    raise Exception(f'Health check failed: {r.status}')
print('✓ Health check passed')
"

# 4. Run unit tests inside container
echo "Running unit tests..."
docker exec $CONTAINER_ID pytest tests/unit -v

# 5. Run basic integration tests
echo "Running integration tests..."
docker exec $CONTAINER_ID pytest tests/integration/test_api_basic.py -v

# 6. API endpoint smoke tests
echo "Testing API endpoints..."
docker exec $CONTAINER_ID python3 -c "
import http.client, json
conn = http.client.HTTPConnection('localhost', 5000)

# Test auth endpoint
conn.request('GET', '/api/v1/auth/login')
r = conn.getresponse()
assert r.status in [200, 401], f'Auth endpoint failed: {r.status}'
print('✓ Auth endpoint responding')

# Test users endpoint
conn.request('GET', '/api/v1/users')
r = conn.getresponse()
assert r.status in [200, 401], f'Users endpoint failed: {r.status}'
print('✓ Users endpoint responding')
"

# Cleanup
docker stop $CONTAINER_ID
docker rm $CONTAINER_ID

echo "✓ Flask Backend Smoke Test PASSED"
```

**WebUI:** `tests/smoketests/webui.sh`
```bash
#!/bin/bash
set -e

echo "=== WebUI Smoke Test ==="

# 1. Build verification
echo "Building container..."
docker build -t webui:test ./services/webui

# 2. Run container
echo "Starting container..."
CONTAINER_ID=$(docker run -d -p 3000:3000 webui:test)

# Wait for startup
sleep 10

# 3. Health check
echo "Checking health endpoint..."
curl -f http://localhost:3000/healthz || exit 1

# 4. Run unit tests
echo "Running unit tests..."
docker exec $CONTAINER_ID npm run test:unit

# 5. Page load tests
echo "Testing page loads..."
docker exec $CONTAINER_ID node -e "
const http = require('http');

function testPage(path) {
  return new Promise((resolve, reject) => {
    http.get('http://localhost:3000' + path, (res) => {
      if (res.statusCode === 200) {
        console.log('✓ Page loaded:', path);
        resolve();
      } else {
        reject(new Error(\`Page failed: \${path} (Status: \${res.statusCode})\`));
      }
    }).on('error', reject);
  });
}

(async () => {
  await testPage('/');              // Home page
  await testPage('/login');         // Login page
  await testPage('/dashboard');     // Dashboard (may redirect)
  console.log('✓ All pages loaded successfully');
})();
"

# 6. Build production bundle
echo "Testing production build..."
docker exec $CONTAINER_ID npm run build

# Cleanup
docker stop $CONTAINER_ID
docker rm $CONTAINER_ID

echo "✓ WebUI Smoke Test PASSED"
```

**Go Backend:** `tests/smoketests/go-backend.sh`
```bash
#!/bin/bash
set -e

echo "=== Go Backend Smoke Test ==="

# 1. Build verification
echo "Building container..."
docker build -t go-backend:test ./services/go-backend

# 2. Run container
echo "Starting container..."
CONTAINER_ID=$(docker run -d go-backend:test)

# Wait for startup
sleep 5

# 3. Health check
echo "Checking health endpoint..."
docker exec $CONTAINER_ID /usr/local/bin/healthcheck || exit 1

# 4. Run unit tests
echo "Running unit tests..."
docker exec $CONTAINER_ID go test ./... -v

# 5. Run integration tests
echo "Running integration tests..."
docker exec $CONTAINER_ID go test ./tests/integration/... -v

# 6. Performance smoke test
echo "Running performance smoke test..."
docker exec $CONTAINER_ID go test -bench=. -benchtime=1s ./tests/benchmarks/smoke_test.go

# Cleanup
docker stop $CONTAINER_ID
docker rm $CONTAINER_ID

echo "✓ Go Backend Smoke Test PASSED"
```

**Run All:** `tests/smoketests/run-all.sh`
```bash
#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================"
echo "Running All Smoke Tests"
echo "======================================"

FAILED=0

for script in tests/smoketests/*.sh; do
  # Skip run-all.sh itself
  if [[ "$script" == *"run-all.sh" ]]; then
    continue
  fi

  echo ""
  echo "Running: $script"
  if bash "$script"; then
    echo "✓ PASSED: $script"
  else
    echo "✗ FAILED: $script"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "======================================"
if [[ $FAILED -eq 0 ]]; then
  echo "✓ ALL SMOKE TESTS PASSED"
  exit 0
else
  echo "✗ $FAILED SMOKE TEST(S) FAILED"
  exit 1
fi
```

#### Integration with Pre-Commit

Smoke tests MUST be executed in the pre-commit checklist:

```bash
# In scripts/pre-commit/pre-commit.sh
echo "Step 5: Smoke Tests"
echo "-------------------"
./tests/smoketests/run-all.sh || exit 1
```

#### Smoke Test Guidelines

1. **Keep it fast**: Smoke tests should complete in <2 minutes total
2. **Comprehensive coverage**: Test all critical paths (build, run, API, UI)
3. **Fail fast**: Exit immediately on first failure
4. **Clear output**: Print progress and results clearly
5. **Cleanup**: Always cleanup containers and resources
6. **Standardized location**: Always use `tests/smoketests/{container_name}.sh`
7. **Executable**: Make scripts executable (`chmod +x`)
8. **Minimal dependencies**: Use only what's available in the container
9. **Mock data**: Use test fixtures, don't require external services
10. **Deterministic**: Tests should pass consistently, not flaky

📚 **Complete testing guide**: [docs/TESTING.md](../../TESTING.md)

### Unit Testing

**All applications MUST have comprehensive unit tests:**

**Location:** `tests/unit/{service_name}/`

- **Network isolation**: Unit tests must NOT require external network connections
- **No external dependencies**: Cannot reach databases, APIs, or external services
- **Use mocks/stubs**: Mock all external dependencies and I/O operations
- **KISS principle**: Keep unit tests simple, focused, and fast
- **Test isolation**: Each test should be independent and repeatable
- **Fast execution**: Unit tests should complete in milliseconds
- **Coverage targets**: Aim for >80% code coverage minimum

**Python (pytest):**
```bash
pytest tests/unit/ -v --cov=app --cov-report=term-missing
```

**Go:**
```bash
go test ./... -v -cover
```

**Node.js (Jest):**
```bash
npm run test:unit -- --coverage
```

### Integration Testing

**Location:** `tests/integration/{service_name}/`

Integration tests verify component interactions and system integration:

- **Test component interactions**: Verify services communicate correctly
- **Use test databases**: Spin up test database containers
- **Verify API contracts**: Ensure API requests/responses match contracts
- **Test authentication and authorization**: Verify RBAC, JWT, permissions
- **Service dependencies**: Test with real services in isolated environment
- **Database transactions**: Test CRUD operations with real database
- **Message queues**: Test async communication patterns

**Example Integration Test Structure:**
```
tests/integration/
├── flask-backend/
│   ├── test_api_basic.py       # Basic API tests
│   ├── test_auth.py             # Authentication tests
│   └── test_database.py         # Database integration
├── go-backend/
│   └── integration_test.go      # Go integration tests
└── docker-compose.test.yml      # Test environment
```

**Running Integration Tests:**
```bash
# Start test environment
docker-compose -f tests/integration/docker-compose.test.yml up -d

# Run integration tests
pytest tests/integration/ -v

# Cleanup
docker-compose -f tests/integration/docker-compose.test.yml down -v
```

### End-to-End Testing

**Location:** `tests/e2e/`

E2E tests verify critical user workflows through the entire system:

- **Test critical user workflows**: Login, CRUD operations, key features
- **Use staging environment**: Test against staging deployment
- **Verify full system integration**: All services, databases, external APIs
- **Browser automation**: Use Playwright/Selenium for WebUI testing
- **API workflows**: Test complete API request chains
- **User scenarios**: Test from user perspective, not technical perspective

**Example E2E Test:**
```javascript
// tests/e2e/user-login-workflow.spec.js
const { test, expect } = require('@playwright/test');

test('user can login and access dashboard', async ({ page }) => {
  // Navigate to login page
  await page.goto('http://localhost:3000/login');

  // Fill login form
  await page.fill('input[name="email"]', 'admin@localhost.local');
  await page.fill('input[name="password"]', 'admin123');

  // Submit form
  await page.click('button[type="submit"]');

  // Verify redirect to dashboard
  await expect(page).toHaveURL('http://localhost:3000/dashboard');

  // Verify dashboard elements loaded
  await expect(page.locator('h1')).toContainText('Dashboard');

  // Verify API data loaded
  await expect(page.locator('.user-count')).toBeVisible();
});
```

### Performance Testing

**Location:** `tests/performance/`

Performance tests ensure the system meets scalability and latency requirements:

- **Benchmark critical operations**: Measure operation performance
- **Load testing for scalability**: Test under expected load
- **Stress testing**: Find breaking points
- **Regression testing**: Prevent performance degradation
- **Latency measurements**: Track response times
- **Throughput testing**: Measure requests/second capacity

**Tools:**
- **Python**: pytest-benchmark, locust
- **Go**: built-in benchmarking (`go test -bench`)
- **HTTP Load**: Apache Bench (ab), wrk, k6

**Example Go Benchmark:**
```go
// tests/performance/api_benchmark_test.go
func BenchmarkAPIEndpoint(b *testing.B) {
    for i := 0; i < b.N; i++ {
        resp, _ := http.Get("http://localhost:8080/api/v1/users")
        resp.Body.Close()
    }
}
```

### Mock Data Standards

**Location:** `tests/fixtures/` or `scripts/seed/`

All tests and development environments should use consistent mock data:

- **3-4 items per feature/entity**: Enough to show patterns, not too much
- **Realistic data**: Use plausible names, emails, values
- **Consistent fixtures**: Reuse same fixtures across test types
- **Seed scripts**: Automate mock data population
- **Reset capability**: Easy to reset to clean state

**Example Fixture:**
```python
# tests/fixtures/users.py
MOCK_USERS = [
    {
        "email": "admin@localhost.local",
        "username": "admin",
        "role": "admin"
    },
    {
        "email": "maintainer@localhost.local",
        "username": "maintainer",
        "role": "maintainer"
    },
    {
        "email": "viewer@localhost.local",
        "username": "viewer",
        "role": "viewer"
    }
]
```

### Test Execution Order

**Recommended execution order in CI/CD:**

1. **Linting** (fastest) - Catch style issues immediately
2. **Unit Tests** (fast) - Verify individual components
3. **Smoke Tests** (quick) - Verify build and basic functionality
4. **Integration Tests** (medium) - Verify component interactions
5. **E2E Tests** (slow) - Verify critical workflows
6. **Performance Tests** (slowest) - Verify scalability

### Cross-Architecture Testing

**Before final commit, test on alternate architecture using QEMU:**

```bash
# If developing on amd64, test on arm64:
docker buildx build --platform linux/arm64 -t app:test-arm64 .
docker run --platform linux/arm64 app:test-arm64 npm test

# If developing on arm64, test on amd64:
docker buildx build --platform linux/amd64 -t app:test-amd64 .
docker run --platform linux/amd64 app:test-amd64 npm test
```

This ensures multi-architecture compatibility and prevents platform-specific bugs.
