# Testing Guide - Tobogganing

Comprehensive testing documentation for Tobogganing SASE platform, including unit tests, integration tests, VPN testing, mock data, and cross-architecture validation.

## Overview

Testing is organized into multiple levels to ensure comprehensive coverage, fast feedback, and production-ready code:

| Test Level | Purpose | Speed | Coverage |
|-----------|---------|-------|----------|
| **Smoke Tests** | Fast verification of basic functionality | <2 min | Build, run, API health, UI loads, VPN tunnels |
| **Unit Tests** | Isolated function/method testing | <1 min | Code logic, edge cases |
| **Integration Tests** | Component interaction verification | 1-5 min | Data flow, API contracts, VPN connectivity |
| **E2E Tests** | Critical workflows end-to-end | 5-10 min | User scenarios, business logic, full VPN flows |
| **Performance Tests** | Scalability and throughput validation | 5-15 min | Load, latency, connection count limits |
| **WireGuard Tests** | VPN protocol and connectivity verification | 2-5 min | Tunnel establishment, traffic routing, peer management |

---

## Mock Data Scripts

### Purpose

Mock data scripts populate the development database with realistic test data, enabling:
- Rapid local development without manual data entry
- Consistent test data across the development team
- Documentation of expected data structure and relationships
- Quick feature iteration with pre-populated databases
- VPN testing with realistic client/headend/policy data

### Location & Structure

```
scripts/mock-data/
├── seed-all.py             # Orchestrator: runs all seeders in order
├── seed-users.py           # 3-4 users with different roles (admin, operator, viewer)
├── seed-headends.py        # 3-4 headend servers in different regions
├── seed-clients.py         # 3-4 clients with various configurations
├── seed-policies.py        # 3-4 access policies with different rules
├── seed-[feature].py       # Additional feature-specific seeders
└── README.md               # Instructions for running mock data
```

### Naming Convention

- **Python**: `seed-{feature-name}.py`
- **Shell**: `seed-{feature-name}.sh`
- **Organization**: One seeder per logical entity/feature

### Scope: 3-4 Items Per Entity

Each seeder should create **exactly 3-4 representative items** to test all variations:

**Example (Users)**:
```python
# scripts/mock-data/seed-users.py
items = [
    {"email": "admin@example.com", "role": "admin", "status": "active"},
    {"email": "operator@example.com", "role": "operator", "status": "active"},
    {"email": "viewer@example.com", "role": "viewer", "status": "active"},
    {"email": "disabled@example.com", "role": "viewer", "status": "inactive"},
]
```

**Example (Headend Servers)**:
```python
# scripts/mock-data/seed-headends.py
items = [
    {"name": "US-East-1", "region": "us-east-1", "status": "online", "capacity": 5000},
    {"name": "EU-West-1", "region": "eu-west-1", "status": "online", "capacity": 3000},
    {"name": "AP-Southeast-1", "region": "ap-southeast-1", "status": "offline", "capacity": 2000},
    {"name": "Backup", "region": "backup", "status": "standby", "capacity": 1000},
]
```

**Example (Clients)**:
```python
# scripts/mock-data/seed-clients.py
items = [
    {"name": "Client-Laptop", "user": "admin@example.com", "platform": "macos", "status": "connected"},
    {"name": "Client-Desktop", "user": "operator@example.com", "platform": "windows", "status": "connected"},
    {"name": "Client-Linux", "user": "viewer@example.com", "platform": "linux", "status": "disconnected"},
    {"name": "Client-Docker", "user": "admin@example.com", "platform": "docker", "status": "connected"},
]
```

### Execution

**Seed all test data**:
```bash
make seed-mock-data          # Via Makefile
python scripts/mock-data/seed-all.py  # Direct execution
```

**Seed specific entity**:
```bash
python scripts/mock-data/seed-users.py
python scripts/mock-data/seed-headends.py
python scripts/mock-data/seed-clients.py
python scripts/mock-data/seed-policies.py
```

### Implementation Pattern

**Python (PyDAL)**:
```python
#!/usr/bin/env python3
"""Seed mock data for users entity."""

import os
import sys
from dal import DAL

def seed_users():
    db = DAL('sqlite:memory')  # or use DB_TYPE env var

    users = [
        {"email": "admin@example.com", "role": "admin", "password_hash": "..."},
        {"email": "operator@example.com", "role": "operator", "password_hash": "..."},
        {"email": "viewer@example.com", "role": "viewer", "password_hash": "..."},
        {"email": "test@example.com", "role": "viewer", "password_hash": "..."},
    ]

    for user in users:
        db.auth_user.insert(**user)

    print(f"✓ Seeded {len(users)} users")

if __name__ == "__main__":
    seed_users()
```

**Shell (API-based)**:
```bash
#!/bin/bash
# scripts/mock-data/seed-clients.sh

API_URL="${API_URL:-http://localhost:5000}"
TOKEN="${AUTH_TOKEN}"

# Client 1 - Native macOS
curl -X POST "$API_URL/api/v1/clients" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "MacBook-Pro", "platform": "macos", "auto_start": true}'

# Client 2 - Windows Desktop
curl -X POST "$API_URL/api/v1/clients" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Windows-Desktop", "platform": "windows", "auto_start": true}'

# Client 3 - Linux Server
curl -X POST "$API_URL/api/v1/clients" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Ubuntu-Server", "platform": "linux", "auto_start": true}'

# Client 4 - Docker Container
curl -X POST "$API_URL/api/v1/clients" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Docker-App", "platform": "docker", "auto_start": false}'

echo "✓ Seeded 4 clients"
```

### Makefile Integration

Add to your `Makefile`:

```makefile
.PHONY: seed-mock-data
seed-mock-data:
	@echo "Seeding mock data..."
	@python scripts/mock-data/seed-all.py
	@echo "✓ Mock data seeding complete"

.PHONY: clean-data
clean-data:
	@echo "Clearing mock data..."
	@rm -f data/dev.db
	@echo "✓ Mock data cleared"
```

### When to Create Mock Data Scripts

**Create a mock data script after each new feature/entity completion**:
- After implementing user management → create `seed-users.py`
- After implementing headend services → create `seed-headends.py`
- After implementing client registration → create `seed-clients.py`
- After implementing policy engine → create `seed-policies.py`

This ensures developers can immediately test the feature without manual setup.

---

## Smoke Tests

### Purpose

Smoke tests provide fast verification that basic functionality works after code changes, preventing regressions in core features.

### Requirements (Mandatory)

All projects **MUST** implement smoke tests before committing:

- ✅ **Build Tests**: All containers build successfully without errors
- ✅ **Run Tests**: All containers start and remain healthy
- ✅ **API Health Checks**: All API endpoints respond with 200/healthy status
- ✅ **WireGuard Tests**: Headend WireGuard interface initializes successfully
- ✅ **VPN Connectivity**: Client can establish tunnel to headend
- ✅ **Page Load Tests**: All web pages load without JavaScript errors
- ✅ **Tab Navigation Tests**: All tabs/routes navigate without console errors

### Location & Structure

```
tests/smoke/
├── build/          # Container build verification
│   ├── test-manager-build.sh
│   ├── test-headend-build.sh
│   ├── test-webui-build.sh
│   └── test-client-build.sh
├── run/            # Container runtime and health
│   ├── test-manager-run.sh
│   ├── test-headend-run.sh
│   └── test-webui-run.sh
├── api/            # API health endpoint validation
│   ├── test-manager-health.sh
│   ├── test-headend-health.sh
│   └── README.md
├── vpn/            # WireGuard and VPN connectivity
│   ├── test-wireguard-init.sh
│   ├── test-vpn-tunnel.sh
│   └── README.md
├── webui/          # Page load and tab navigation
│   ├── test-pages-load.sh
│   ├── test-tabs-navigate.sh
│   └── README.md
├── run-all.sh      # Execute all smoke tests
└── README.md       # Documentation
```

### Execution

**Run all smoke tests**:
```bash
make smoke-test              # Via Makefile
./tests/smoke/run-all.sh     # Direct execution
```

**Run specific test category**:
```bash
./tests/smoke/build/test-manager-build.sh
./tests/smoke/api/test-manager-health.sh
./tests/smoke/vpn/test-wireguard-init.sh
./tests/smoke/webui/test-pages-load.sh
```

### Speed Requirement

Complete smoke test suite **MUST run in under 2 minutes** to provide fast feedback during development.

### Implementation Examples

**Build Test (Shell)**:
```bash
#!/bin/bash
# tests/smoke/build/test-manager-build.sh

set -e

echo "Testing Manager API build..."
cd services/api-server

# Attempt to build the container
if docker build -t api-server:test .; then
    echo "✓ Manager API builds successfully"
    exit 0
else
    echo "✗ Manager API build failed"
    exit 1
fi
```

**Health Check Test**:
```bash
#!/bin/bash
# tests/smoke/api/test-manager-health.sh

set -e

echo "Checking Manager API health..."
HEALTH_URL="http://localhost:5000/health"

RESPONSE=$(curl -s -w "\n%{http_code}" "$HEALTH_URL")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ Manager API is healthy (HTTP $HTTP_CODE)"
    exit 0
else
    echo "✗ Manager API is unhealthy (HTTP $HTTP_CODE)"
    exit 1
fi
```

**WireGuard Initialization Test**:
```bash
#!/bin/bash
# tests/smoke/vpn/test-wireguard-init.sh

set -e

echo "Testing WireGuard initialization..."

# Start headend
docker-compose up -d hub-node

# Wait for headend to initialize
sleep 3

# Check if WireGuard interface exists
if docker-compose exec hub-node ip link show wg0 2>/dev/null; then
    echo "✓ WireGuard interface initialized successfully"
    exit 0
else
    echo "✗ WireGuard interface failed to initialize"
    docker-compose logs hub-node
    exit 1
fi
```

**VPN Tunnel Test**:
```bash
#!/bin/bash
# tests/smoke/vpn/test-vpn-tunnel.sh

set -e

echo "Testing VPN tunnel establishment..."

# Start all services
docker-compose up -d

# Wait for services to be ready
sleep 5

# Register a test client
RESPONSE=$(curl -s -X POST http://localhost:5000/api/v1/clients/register \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test-api-key"}')

CLIENT_ID=$(echo $RESPONSE | jq -r '.client_id')

# Start client
docker-compose up -d native-client

# Wait for tunnel to establish
sleep 5

# Check tunnel status
if docker-compose exec native-client ip link show wg0 >/dev/null 2>&1; then
    echo "✓ VPN tunnel established successfully"
    exit 0
else
    echo "✗ VPN tunnel failed to establish"
    docker-compose logs native-client
    exit 1
fi
```

**Page Load Test (Playwright)**:
```bash
#!/bin/bash
# tests/smoke/webui/test-pages-load.sh

npx playwright test tests/smoke/webui/pages.spec.ts \
  --config=tests/smoke/webui/playwright.config.ts
```

### Pre-Commit Integration

Smoke tests run as part of the pre-commit checklist (step 5) and **must pass before proceeding** to full test suite:

```bash
./scripts/pre-commit/pre-commit.sh
# Step 1: Linters
# Step 2: Security scans
# Step 3: No secrets
# Step 4: Build & Run
# Step 5: Smoke tests ← Must pass
# Step 6: Full tests
```

---

## Unit Tests

### Purpose

Unit tests verify individual functions and methods in isolation with mocked dependencies.

### Location

```
tests/unit/
├── manager/
│   ├── test_auth.py
│   ├── test_api.py
│   ├── test_models.py
│   └── test_policies.py
├── headend/
│   ├── wireguard_test.go
│   ├── routing_test.go
│   ├── auth_test.go
│   └── proxy_test.go
├── clients/
│   ├── config_test.go
│   ├── vpn_test.go
│   └── health_test.go
├── webui/
│   ├── components/
│   │   └── ClientList.test.tsx
│   └── utils/
│       └── api-client.test.ts
└── k8s-cni/
    ├── ipam_test.go
    └── network_test.go
```

### Execution

```bash
make test-unit              # All unit tests
pytest tests/unit/          # Python
go test ./...               # Go
npm test                    # JavaScript/TypeScript
```

### Requirements

- All dependencies must be mocked
- Network calls must be stubbed
- Database access must be isolated
- Tests must run in parallel when possible

### Example Tests

**Python (Manager)**:
```python
# tests/unit/manager/test_auth.py
import pytest
from unittest.mock import Mock, patch
from app.auth import AuthService

@pytest.fixture
def auth_service():
    return AuthService()

def test_generate_jwt_token():
    """Test JWT token generation"""
    token = auth_service.generate_token(user_id="123")
    assert token is not None
    assert len(token) > 20

def test_validate_jwt_token():
    """Test JWT token validation"""
    token = auth_service.generate_token(user_id="123")
    decoded = auth_service.validate_token(token)
    assert decoded['user_id'] == "123"

def test_validate_invalid_token():
    """Test invalid token rejection"""
    with pytest.raises(ValueError):
        auth_service.validate_token("invalid-token")
```

**Go (Headend)**:
```go
// tests/unit/headend/wireguard_test.go
package wireguard_test

import (
    "testing"
    "github.com/stretchr/testify/assert"
    "headend/pkg/wireguard"
)

func TestCreateInterface(t *testing.T) {
    wg := wireguard.NewInterface("wg0")
    assert.NotNil(t, wg)
    assert.Equal(t, "wg0", wg.Name)
}

func TestAddPeer(t *testing.T) {
    wg := wireguard.NewInterface("wg0")
    peer, err := wg.AddPeer("AAAA...")
    assert.NoError(t, err)
    assert.NotNil(t, peer)
}
```

---

## Integration Tests

### Purpose

Integration tests verify that components work together correctly, including real database interactions and service communication.

### Location

```
tests/integration/
├── manager/
│   ├── test_client_registration.py
│   ├── test_certificate_issuance.py
│   ├── test_policy_enforcement.py
│   └── test_api_contracts.py
├── headend/
│   ├── test_wireguard_integration.go
│   ├── test_client_connection.go
│   ├── test_traffic_routing.go
│   └── test_traffic_mirroring.go
├── vpn/
│   ├── test_end_to_end_tunnel.py
│   ├── test_multi_client_connections.py
│   └── test_failover_scenarios.py
└── services/
    ├── test_service_communication.py
    └── test_data_pipeline.py
```

### Execution

```bash
make test-integration       # All integration tests
pytest tests/integration/   # Python
go test -tags=integration ./...  # Go
npm run test:integration    # JavaScript
```

### Requirements

- Use real databases (test instances)
- Test complete workflows
- Verify API contracts
- Test error scenarios
- Test with actual WireGuard if possible

### Example Tests

**Client Registration to VPN Connection**:
```python
# tests/integration/vpn/test_end_to_end_tunnel.py
import pytest
from app.client_manager import ClientManager
from app.certificate_manager import CertificateManager
from app.headend_gateway import HeadendGateway

class TestE2ETunnel:
    @pytest.fixture
    def setup(self):
        self.client_manager = ClientManager()
        self.cert_manager = CertificateManager()
        self.headend = HeadendGateway()

    def test_client_registration_to_tunnel(self):
        """Test complete flow from client registration to tunnel establishment"""
        # Step 1: Register client with API key
        client = self.client_manager.register_client(
            api_key="test-key",
            platform="linux"
        )
        assert client.status == "registered"

        # Step 2: Generate certificate
        cert = self.cert_manager.generate_certificate(client.id)
        assert cert.is_valid

        # Step 3: Create WireGuard config
        config = self.headend.create_wireguard_config(client.id, cert)
        assert config.private_key is not None

        # Step 4: Verify tunnel can be established (mocked)
        assert self.headend.validate_config(config)
```

---

## WireGuard Testing Strategies

### Purpose

WireGuard testing ensures VPN protocol correctness, peer management, and traffic routing.

### Testing Levels

**1. Protocol-Level Testing** (Unit):
```bash
# Test WireGuard library functions
go test -v ./pkg/wireguard/
# Verify: Key generation, peer addition, configuration parsing
```

**2. Interface-Level Testing** (Integration):
```bash
# Test actual WireGuard interface operations
# (Requires Linux with WireGuard kernel module)
go test -tags=integration -v ./tests/integration/headend/

# Manual testing:
sudo ip link add dev wg_test type wireguard
sudo ip addr add 10.0.0.1/24 dev wg_test
sudo wg set wg_test listen-port 51820 private-key <(wg genkey)
```

**3. Connectivity Testing** (E2E):
```bash
# Test client-to-headend tunnel establishment
# Requires running Manager, Headend, and Client services
make test-vpn-connectivity

# Manual verification:
sudo ping -I wg0 10.0.0.2  # ping through tunnel
sudo wg show              # inspect tunnel stats
sudo tcpdump -i wg0       # capture tunnel traffic
```

### Example WireGuard Tests

**Key Management**:
```go
// tests/integration/headend/test_key_management.go
func TestKeyGeneration(t *testing.T) {
    wg := wireguard.New()

    privKey, _ := wg.GeneratePrivateKey()
    pubKey := wg.DerivePublicKey(privKey)

    assert.NotNil(t, privKey)
    assert.NotNil(t, pubKey)
    assert.NotEqual(t, privKey, pubKey)
}
```

**Peer Management**:
```go
func TestPeerAdditionRemoval(t *testing.T) {
    wg := wireguard.New()

    // Create interface
    iface, _ := wg.CreateInterface("wg0")

    // Add peer
    peer, _ := iface.AddPeer("AAAA...")
    assert.Equal(t, 1, iface.PeerCount())

    // Remove peer
    iface.RemovePeer(peer.ID)
    assert.Equal(t, 0, iface.PeerCount())
}
```

**Traffic Routing**:
```bash
# tests/integration/vpn/test_traffic_routing.sh
#!/bin/bash

# Start headend
docker-compose up -d hub-node

# Register client and get config
curl -X POST http://localhost:5000/api/v1/clients/register ...

# Start client
docker-compose up -d native-client

# Test traffic flows through tunnel
sudo iptables -t mangle -I FORWARD -i wg0 -j MARK --set-mark 0x1
sudo tcpdump -i wg0 'mark 0x1' -c 10

# Verify packet count > 0
echo "✓ Traffic routed through WireGuard tunnel"
```

---

## End-to-End Tests

### Purpose

E2E tests verify critical user workflows from start to finish, testing the entire application stack.

### Location

```
tests/e2e/
├── client-registration.spec.ts
├── vpn-connection.spec.ts
├── policy-enforcement.spec.ts
├── multi-client-scenario.spec.ts
└── failover-recovery.spec.ts
```

### Execution

```bash
make test-e2e               # All E2E tests
npx playwright test tests/e2e/  # Playwright
```

### Example Tests

**Complete VPN Connection Flow**:
```typescript
// tests/e2e/vpn-connection.spec.ts
import { test, expect } from '@playwright/test';

test('Complete VPN connection flow', async ({ page }) => {
  // Step 1: Admin logs in
  await page.goto('http://localhost:3000/login');
  await page.fill('[name="email"]', 'admin@example.com');
  await page.fill('[name="password"]', 'password');
  await page.click('button:has-text("Login")');

  // Step 2: Admin generates client config
  await page.goto('http://localhost:3000/clients');
  await page.click('button:has-text("Add Client")');
  await page.fill('[name="client-name"]', 'test-client');
  await page.click('button:has-text("Generate")');

  // Step 3: Download and verify config
  const downloadPromise = page.waitForEvent('popup');
  await page.click('a:has-text("Download Config")');
  const config = await downloadPromise;

  // Step 4: Verify client connects
  await page.goto('http://localhost:3000/clients');
  await expect(page.locator('text=test-client')).toContainText('Connected');
});
```

---

## Performance Tests

### Purpose

Performance tests validate scalability, throughput, and resource usage under load.

### Location

```
tests/performance/
├── load-test.js
├── stress-test.js
├── concurrent-connections.go
└── profile-report.md
```

### Execution

```bash
make test-performance
npm run test:performance
```

---

## Cross-Architecture Testing

### Purpose

Cross-architecture testing ensures the application builds and runs correctly on both amd64 and arm64 architectures, preventing platform-specific bugs.

### When to Test

**Before every final commit**, test on the alternate architecture:
- Developing on amd64 → Build and test arm64 with QEMU
- Developing on arm64 → Build and test amd64 with QEMU

### Setup (First Time)

Enable Docker buildx for multi-architecture builds:

```bash
docker buildx create --name multiarch --driver docker-container
docker buildx use multiarch
```

### Single Architecture Build

```bash
# Test current architecture (native, fast)
docker build -t api-server:test services/api-server/

# Or explicitly specify architecture
docker build --platform linux/amd64 -t api-server:test services/api-server/
```

### Cross-Architecture Build (QEMU)

```bash
# Test alternate architecture (uses QEMU emulation)
docker buildx build --platform linux/arm64 -t api-server:test services/api-server/

# Or test both simultaneously
docker buildx build --platform linux/amd64,linux/arm64 -t api-server:test services/api-server/
```

### Multi-Architecture Build Script

Create `scripts/build/test-multiarch.sh`:

```bash
#!/bin/bash
# Test both architectures before commit

set -e

SERVICES=("api-server" "hub-node" "webui")
ARCHITECTURES=("linux/amd64" "linux/arm64")

for service in "${SERVICES[@]}"; do
    echo "Testing $service on multiple architectures..."

    for arch in "${ARCHITECTURES[@]}"; do
        echo "  → Building for $arch..."
        docker buildx build \
            --platform "$arch" \
            -t "$service:multiarch-test" \
            "services/$service/" || {
            echo "✗ Build failed for $service on $arch"
            exit 1
        }
    done

    echo "✓ $service builds successfully on amd64 and arm64"
done

echo "✓ All services passed multi-architecture testing"
```

### Makefile Integration

```makefile
.PHONY: test-multiarch
test-multiarch:
	@echo "Testing multi-architecture builds..."
	@bash scripts/build/test-multiarch.sh

.PHONY: build-multiarch
build-multiarch:
	@docker buildx build \
		--platform linux/amd64,linux/arm64 \
		-t $(IMAGE_NAME):$(VERSION) \
		--push .
```

---

## Test Execution Order (Pre-Commit)

Follow this order for efficient testing before commits:

1. **Linters** (fast, <1 min)
2. **Security scans** (fast, <1 min)
3. **Secrets check** (fast, <1 min)
4. **Build & Run** (5-10 min)
5. **Smoke tests** (fast, <2 min) ← Gates further testing
6. **Unit tests** (1-2 min)
7. **Integration tests** (2-5 min)
8. **E2E tests** (5-10 min)
9. **VPN connectivity tests** (2-3 min)
10. **Cross-architecture build** (optional, slow)

---

## CI/CD Integration

All tests run automatically in GitHub Actions:

- **On PR**: Smoke + Unit + Integration tests
- **On main merge**: All tests + Performance tests
- **Nightly**: Performance + Cross-architecture tests
- **Release**: Full suite + Manual sign-off

See [Workflows](WORKFLOWS.md) for detailed CI/CD configuration.

---

## VPN Testing Checklist

**Before committing VPN-related changes**:
- [ ] WireGuard interface creates without errors
- [ ] Peers can be added and removed
- [ ] Tunnels establish and tear down cleanly
- [ ] Certificates are properly validated
- [ ] Traffic routes through tunnels correctly
- [ ] Multiple concurrent connections work
- [ ] Failover/reconnection scenarios pass
- [ ] Performance meets latency targets (<10ms)
- [ ] Memory usage is within limits (<512MB per service)

---

**Last Updated**: 2026-01-06
**Maintained by**: Penguin Tech Inc
