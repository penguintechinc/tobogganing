# Local Development Guide - Tobogganing

Complete guide to setting up a local development environment for the Tobogganing SASE platform, running all components locally, and following the development workflow.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Starting Development Environment](#starting-development-environment)
4. [Development Workflow](#development-workflow)
5. [Working with Components](#working-with-components)
6. [Common Tasks](#common-tasks)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **macOS 12+**, **Linux (Ubuntu 20.04+)**, or **Windows 10+ with WSL2**
- **Docker Desktop** 4.0+ (or Docker Engine 20.10+)
- **Docker Compose** 2.0+
- **Git** 2.30+
- **Python** 3.12+ (for Manager service development)
- **Go** 1.23+ (for Headend, Clients, and K8s CNI development)
- **Node.js** 18+ (for WebUI development)
- **WireGuard** kernel module (for Headend VPN testing)

### Optional Tools

- **WireGuard CLI tools** (`wg`, `wg-quick`) for manual testing
- **Docker Buildx** (for multi-architecture builds)
- **Helm** (for Kubernetes deployments)
- **kubectl** (for Kubernetes clusters)
- **conntrack-tools** (for connection tracking debugging)

### Installation

**macOS (Homebrew)**:
```bash
brew install docker docker-compose git python node go wireguard-tools
brew install --cask docker
```

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git python3.12 nodejs golang-1.23 wireguard wireguard-tools
sudo usermod -aG docker $USER  # Allow docker without sudo
newgrp docker                   # Activate group change
```

**Verify Installation**:
```bash
docker --version      # Docker 20.10+
docker-compose --version  # Docker Compose 2.0+
git --version
python3 --version     # Python 3.12+
go version            # Go 1.23+
node --version        # Node.js 18+
wg --version          # WireGuard tools
```

---

## Initial Setup

### Clone Repository

```bash
git clone https://github.com/penguintechinc/tobogganing.git
cd tobogganing
```

### Install Dependencies

```bash
# Install all project dependencies
make setup
```

This runs:
1. Python environment setup (venv, requirements for Manager service)
2. Go module setup (go mod download for Headend and Clients)
3. Node.js dependency installation (npm install for WebUI)
4. Pre-commit hooks installation
5. Database initialization

### Environment Configuration

Copy and customize environment files:

```bash
# Copy example environment files
cp .env.example .env
cp .env.local.example .env.local  # Optional: local overrides
```

**Key Environment Variables**:
```bash
# Database
DB_TYPE=postgresql              # postgres, mysql, sqlite
DB_HOST=localhost
DB_PORT=5432
DB_NAME=tobogganing_dev
DB_USER=postgres
DB_PASSWORD=postgres

# Manager Service (Flask Backend)
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-secret-key-for-dev
FLASK_PORT=5000

# Headend Server
HEADEND_PORT=51820              # WireGuard port
HEADEND_API_PORT=8080           # Headend health/metrics API

# WebUI
WEBUI_PORT=3000

# Cache & Storage
REDIS_URL=redis://localhost:6379

# License (Development - all features available)
RELEASE_MODE=false
LICENSE_KEY=not-required-in-dev

# WireGuard
WG_PRIVATE_KEY=generated-on-startup
WG_PUBLIC_KEY=generated-on-startup
```

### Database Initialization

```bash
# Create database and run migrations
make db-init

# Seed with mock data (3-4 items per entity)
make seed-mock-data

# Verify database connection
make db-health
```

---

## Starting Development Environment

### Quick Start (All Services)

```bash
# Start all services in one command
make dev

# This runs:
# - PostgreSQL database (port 5432)
# - Redis cache (port 6379)
# - Manager API (port 5000)
# - Headend Server (port 51820 for WireGuard, 8080 for API)
# - WebUI (port 3000)

# Access the application:
# Web UI:           http://localhost:3000
# Manager API:      http://localhost:5000
# Headend API:      http://localhost:8080
# Database Admin:   http://localhost:8080 (Adminer)
```

### Individual Service Management

**Start specific services**:
```bash
# Start only Manager API
docker-compose up -d api-server

# Start WebUI and database
docker-compose up -d postgres webui

# Start without detaching (see logs)
docker-compose up api-server
```

**View service logs**:
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api-server

# Last 100 lines, follow new entries
docker-compose logs -f --tail=100 webui

# WireGuard headend logs
docker-compose logs -f hub-node
```

**Stop services**:
```bash
# Stop all services (keep data)
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v

# Restart services
docker-compose restart

# Rebuild and restart (apply code changes)
docker-compose down && docker-compose up -d --build
```

### Development Docker Compose Files

- **`docker-compose.dev.yml`**: Local development (hot-reload, debug ports, verbose logging)
- **`docker-compose.yml`**: Production-like (health checks, resource limits, optimized)

Use dev version locally:
```bash
docker-compose -f docker-compose.dev.yml up
```

---

## Development Workflow

### 1. Start Development Environment

```bash
make dev        # Start all services
make seed-mock-data  # Populate with test data
```

### 2. Make Code Changes

Edit files in your favorite editor. Services auto-reload based on language:

- **Python (Manager)**: Reload on file save (FLASK_DEBUG=1)
- **Node.js (WebUI)**: Hot reload (Webpack dev server)
- **Go (Headend/Clients)**: Requires restart (`docker-compose restart hub-node`)

### 3. Verify Changes

```bash
# Quick smoke tests (build, run, API health, page loads)
make smoke-test

# Run linters
make lint

# Run unit tests
make test

# Run specific component tests
cd services/api-server && pytest tests/unit/
cd services/hub-node && go test ./...
cd services/webui && npm test
```

### 4. Test WireGuard VPN Connectivity

Test the VPN tunneling locally:

```bash
# Start headend server
docker-compose up -d hub-node

# Register a test client (creates certificate + JWT)
curl -X POST http://localhost:5000/api/v1/clients/register \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test-api-key"}'

# Start native client (in another terminal)
docker-compose up -d native-client

# Verify WireGuard tunnel is active
sudo wg show

# Test tunnel connectivity
ping -I wg0 10.0.0.1  # or assigned peer IP
```

### 5. Test Manager Authentication & RBAC

Test user authentication and role-based access:

```bash
# Create test users with different roles
make seed-mock-data  # Seeds admin, operator, viewer users

# Test authentication
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password"}'

# Use returned JWT for subsequent requests
curl -X GET http://localhost:5000/api/v1/headends \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

### 6. Populate Mock Data for Feature Testing

After implementing a new feature, ensure proper mock data:

```bash
# Create mock data script (e.g., for new "Policies" feature)
cat > scripts/mock-data/seed-policies.py << 'EOF'
from dal import DAL

def seed_policies():
    db = DAL('postgresql://user:password@localhost/tobogganing_dev')

    policies = [
        {"name": "Allow All", "rules": "*", "status": "active"},
        {"name": "Restrictive", "rules": "deny", "status": "active"},
        {"name": "Office Hours", "rules": "9-5", "status": "inactive"},
        {"name": "Emergency", "rules": "elevated", "status": "active"},
    ]

    for policy in policies:
        db.policies.insert(**policy)

    print(f"✓ Seeded {len(policies)} policies")

if __name__ == "__main__":
    seed_policies()
EOF

# Run the mock data script
python scripts/mock-data/seed-policies.py

# Add to seed-all.py orchestrator
echo "from seed_policies import seed_policies; seed_policies()" >> scripts/mock-data/seed-all.py
```

📚 **Complete Mock Data Guide**: [Testing Documentation - Mock Data Scripts](TESTING.md#mock-data-scripts)

### 7. Run Pre-Commit Checklist

Before committing, run the comprehensive pre-commit script:

```bash
./scripts/pre-commit/pre-commit.sh
```

**Steps**:
1. ✅ Linters (flake8, black, golangci-lint, eslint, etc.)
2. ✅ Security scans (bandit, gosec, npm audit)
3. ✅ Secret detection (no API keys, passwords, tokens)
4. ✅ Build & Run (build all containers, verify runtime)
5. ✅ Smoke tests (build, health checks, UI loads, VPN connectivity)
6. ✅ Unit tests (isolated component testing)
7. ✅ Integration tests (component interactions)
8. ✅ Version update & Docker standards

**Troubleshooting Pre-Commit**:

See [Pre-Commit Documentation](PRE_COMMIT.md) for detailed guidance on:
- Fixing linting errors
- Resolving security vulnerabilities
- Excluding files from checks
- Bypassing specific checks (with justification)

### 8. Testing & Validation

Comprehensive testing guide:

📚 **Complete Testing Guide**: [Testing Documentation](TESTING.md)

**Quick Test Commands**:
```bash
# Smoke tests only (fast, <2 min)
make smoke-test

# Unit tests only
make test-unit

# Integration tests only
make test-integration

# All tests
make test

# Specific test file
pytest tests/unit/test_auth.py
go test ./...

# Cross-architecture testing (QEMU)
make test-multiarch
```

### 9. Create Pull Request

Once tests pass:

```bash
# Push branch
git push origin feature-branch-name

# Create PR via GitHub CLI
gh pr create --title "Brief feature description" \
  --body "Detailed description of changes"

# Or use web UI: https://github.com/penguintechinc/tobogganing/compare
```

### 10. Code Review & Merge

- Address review feedback
- Re-run tests if changes made
- Merge when approved

---

## Working with Components

### Manager Service (Python)

**Development**:
```bash
# Install Python dependencies
cd services/api-server
pip install -r requirements.txt

# Run locally (without Docker)
FLASK_ENV=development FLASK_DEBUG=1 python -m app.main

# Or run in Docker
docker-compose up -d api-server
```

**Key Files**:
- `services/api-server/app/main.py` - Flask app setup
- `services/api-server/app/auth/` - Authentication logic
- `services/api-server/app/api/` - REST API endpoints
- `services/api-server/app/database/` - PyDAL models

**API Development**:
```bash
# Add new endpoint
# 1. Define model in services/api-server/app/database/models.py
# 2. Create API in services/api-server/app/api/endpoints.py
# 3. Add to routes in services/api-server/app/main.py
# 4. Test with: curl http://localhost:5000/api/v1/<endpoint>
```

### Headend Server (Go)

**Development**:
```bash
# Build locally
cd services/hub-node
go build -o headend ./cmd/hub-node

# Run locally
./headend -config config/headend.yaml

# Or run in Docker
docker-compose up -d hub-node
```

**Key Files**:
- `services/hub-node/cmd/hub-node/main.go` - Service entry point
- `services/hub-node/pkg/wireguard/` - WireGuard integration
- `services/hub-node/pkg/auth/` - Certificate authentication
- `services/hub-node/pkg/proxy/` - Traffic routing/proxying

**Headend Development**:
```bash
# Test WireGuard interface creation
sudo ip link add dev wg0 type wireguard
sudo ip addr add 10.0.0.1/24 dev wg0

# Test with local headend
./headend -interface wg0

# Verify interface
ip link show wg0
sudo wg show
```

### Client Applications (Go)

**Development**:
```bash
# Build native client
cd services/clients/native
go build -o tobogganing-client ./cmd/client

# Build GUI client (requires Fyne)
go build -o tobogganing-gui ./cmd/gui

# Or build via Docker
docker-compose up -d native-client
```

**Key Files**:
- `services/clients/native/cmd/client/` - CLI client
- `services/clients/native/cmd/gui/` - GUI client (Fyne)
- `services/clients/native/pkg/vpn/` - VPN connection logic
- `services/clients/native/pkg/config/` - Configuration management

### WebUI Dashboard (React/TypeScript)

**Development**:
```bash
# Start WebUI with hot reload
cd services/webui
npm install
npm start

# Or run in Docker
docker-compose up -d webui
```

**Key Files**:
- `services/webui/src/pages/` - Page components
- `services/webui/src/components/` - Reusable UI components
- `services/webui/src/api/` - API client integration
- `services/webui/src/auth/` - Authentication context

**WebUI Development**:
```bash
# Add new page
# 1. Create component: src/pages/MyPage.tsx
# 2. Add route: src/App.tsx
# 3. Add navigation link: src/components/Navigation.tsx

# Test component
npm test -- MyPage.test.tsx
```

### Kubernetes CNI Plugin (Go)

**Development**:
```bash
# Build CNI plugin
cd services/k8s-cni
go build -o tobogganing-cni ./cmd/plugin

# Test in Kubernetes
kubectl apply -f config/daemonset.yaml

# Verify plugin is working
kubectl get daemonset -n kube-system tobogganing-cni
```

**Key Files**:
- `services/k8s-cni/cmd/plugin/` - CNI plugin entry point
- `services/k8s-cni/pkg/network/` - Network configuration
- `services/k8s-cni/pkg/wireguard/` - WireGuard integration

---

## Common Tasks

### Adding a New Python Dependency (Manager)

```bash
# Add to services/api-server/requirements.txt
echo "new-package==1.0.0" >> services/api-server/requirements.txt

# Rebuild Manager container
docker-compose up -d --build api-server

# Verify import works
docker-compose exec api-server python -c "import new_package"
```

### Adding a New Go Dependency

```bash
# Add dependency
cd services/hub-node
go get github.com/new/package

# Update go.mod
go mod tidy

# Rebuild container
docker-compose up -d --build hub-node
```

### Adding a New Node.js Dependency (WebUI)

```bash
# Add to services/webui/package.json
cd services/webui
npm install new-package

# Rebuild WebUI container
docker-compose up -d --build webui

# Verify in running container
docker-compose exec webui npm list new-package
```

### Adding a New Environment Variable

```bash
# Add to .env
echo "NEW_VAR=value" >> .env

# Restart services to pick up new variable
docker-compose restart

# Verify it's set
docker-compose exec api-server printenv | grep NEW_VAR
```

### Debugging a Service

**View logs in real-time**:
```bash
docker-compose logs -f api-server
```

**Access container shell**:
```bash
# Python (Manager)
docker-compose exec api-server bash

# Go (Headend)
docker-compose exec hub-node sh

# Node.js (WebUI)
docker-compose exec webui bash
```

**Execute commands in container**:
```bash
# Run Python script
docker-compose exec api-server python -c "print('hello')"

# Check service health
docker-compose exec api-server curl http://localhost:5000/health

# Go service compilation check
docker-compose exec hub-node go build ./...
```

### Database Operations

**Connect to database**:
```bash
# PostgreSQL
docker-compose exec postgres psql -U postgres -d tobogganing_dev

# MySQL
docker-compose exec mysql mysql -u root -p

# View schema
\dt                    # PostgreSQL tables
SHOW TABLES;           # MySQL tables
```

**Reset database**:
```bash
# Full reset (deletes all data)
docker-compose down -v
make db-init
make seed-mock-data
```

**Run migrations**:
```bash
# Auto-migrate on startup
docker-compose restart api-server

# Or manually run migration
docker-compose exec api-server python -m app.migrations
```

### Testing WireGuard Connectivity

```bash
# Start headend and client
docker-compose up -d hub-node native-client

# Check WireGuard interface
sudo ip addr show wg0

# Test tunnel connectivity
ping -c 4 10.0.0.2  # or client's assigned IP

# Monitor WireGuard statistics
sudo wg show

# Check connection tracking
sudo conntrack -L | grep wireguard
```

### Working with Git Branches

```bash
# Create feature branch
git checkout -b feature/new-feature-name

# Keep branch updated with main
git fetch origin
git rebase origin/main

# Clean commit history before PR
git rebase -i origin/main  # Interactive rebase

# Push branch
git push origin feature/new-feature-name
```

### Database Backups

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U postgres tobogganing_dev > backup.sql

# Restore from backup
docker-compose exec -T postgres psql -U postgres tobogganing_dev < backup.sql
```

---

## Troubleshooting

### Services Won't Start

**Check if ports are already in use**:
```bash
# Find what's using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>

# Or use different ports in .env
FLASK_PORT=5001
```

**Docker daemon not running**:
```bash
# macOS
open /Applications/Docker.app

# Linux
sudo systemctl start docker

# Windows (Docker Desktop)
# Start Docker Desktop from Applications
```

### Database Connection Error

```bash
# Verify database container is running
docker-compose ps postgres

# Check database credentials in .env
cat .env | grep DB_

# Connect to database directly
docker-compose exec postgres psql -U postgres -d postgres

# View logs
docker-compose logs postgres
```

### Manager API Won't Start

```bash
# Check logs
docker-compose logs api-server

# Verify database migration
docker-compose exec api-server python -c "from app import db; db.create_all()"

# Reset and rebuild
docker-compose down
docker-compose up -d --build api-server
```

### WireGuard Headend Issues

```bash
# Check WireGuard is available
sudo modprobe wireguard

# Verify headend is listening
docker-compose exec hub-node netstat -ulpn | grep 51820

# View headend logs
docker-compose logs -f hub-node

# Test manually
sudo wg-quick up wg-config.conf  # if wg-quick available
```

### Smoke Tests Failing

**Check which test failed**:
```bash
# Run individually
./tests/smoke/build/test-manager-build.sh
./tests/smoke/api/test-manager-health.sh
./tests/smoke/api/test-headend-health.sh
./tests/smoke/webui/test-pages-load.sh
```

**Common issues**:
- Service not healthy (logs: `docker-compose logs <service>`)
- Port not exposed (check docker-compose.yml)
- API endpoint not implemented
- Missing environment variables
- WireGuard interface creation failed

See [Testing Documentation - Smoke Tests](TESTING.md#smoke-tests) for detailed troubleshooting.

### Client VPN Connection Failures

```bash
# Check Manager can reach client
curl -X GET http://localhost:5000/api/v1/clients/

# Verify certificate was generated
docker-compose exec api-server ls -la /var/lib/tobogganing/certs/

# Check Headend is accepting connections
docker-compose exec hub-node netstat -tulpn | grep LISTEN

# Review connection logs
docker-compose logs -f native-client
docker-compose logs -f hub-node
```

### Out of Memory

```bash
# Check Docker memory usage
docker stats

# Limit memory for specific service
# Edit docker-compose.yml:
# services:
#   api-server:
#     mem_limit: 512m

# Restart services
docker-compose down && docker-compose up -d --build
```

---

## Tips & Best Practices

### Hot Reload Development

For fastest iteration:
```bash
# Start services once
docker-compose up -d

# Edit Python files → auto-reload (FLASK_DEBUG=1)
# Edit JavaScript files → hot reload (Webpack)
# Edit Go files → restart service
```

### Environment-Specific Configuration

```bash
# Development settings (auto-loaded)
.env              # Default development config
.env.local        # Local machine overrides (gitignored)

# Production settings (via secret management)
Kubernetes secrets
AWS Secrets Manager
HashiCorp Vault
```

### Code Organization

Keep project clean:
```bash
# Remove old branches
git branch -D old-branch

# Clean local Docker images
docker image prune -a

# Clean unused containers
docker container prune
```

### Performance Tips

```bash
# Use specific services to reduce memory usage
docker-compose up postgres api-server  # Skip Headend, WebUI

# Use lightweight testing
make smoke-test  # Instead of full test suite while developing

# Cache Docker layers by building in order of frequency of change
Dockerfile: base → dependencies → code → entrypoint
```

---

## Related Documentation

- **Testing**: [Testing Documentation](TESTING.md)
  - Mock data scripts
  - Smoke tests
  - Unit/integration/E2E tests
  - VPN testing strategies
  - Cross-architecture testing

- **Pre-Commit**: [Pre-Commit Checklist](PRE_COMMIT.md)
  - Linting requirements
  - Security scanning
  - Build verification
  - Test requirements

- **Architecture**: [Architecture Guide](ARCHITECTURE.md)
  - Multi-component design
  - Manager, Headend, Clients overview
  - Data flow and security model

- **API Documentation**: [API Reference](API.md)
  - Manager REST API endpoints
  - Authentication flows
  - Integration examples

---

**Last Updated**: 2026-01-06
**Maintained by**: Penguin Tech Inc
