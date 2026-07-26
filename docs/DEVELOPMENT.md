# Tobogganing - Local Development Setup Guide

This guide covers everything needed to set up a local development environment for Tobogganing.

## Prerequisites

### Required Software

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.13+ | hub-api runtime |
| Go | 1.24+ | hub-router runtime |
| Node.js | 22+ | hub-webui build and development |
| Docker | 24+ | Container builds and local services |
| Docker Compose | v2+ | Multi-service orchestration |
| Make | any | Build automation |
| Git | 2.40+ | Version control |

### Optional Software

| Tool | Version | Purpose |
|------|---------|---------|
| golangci-lint | 1.55+ | Go linting |
| kubectl | 1.28+ | Kubernetes deployment |
| Helm | 3.13+ | Kubernetes package management |
| Terraform | 1.6+ | Infrastructure provisioning |

### System Requirements

- **OS**: Linux (recommended), macOS, or WSL2 on Windows
- **CPU**: 4+ cores recommended (XDP development requires Linux)
- **RAM**: 8 GB minimum, 16 GB recommended
- **Disk**: 10 GB free space for dependencies and container images
- **Network**: Internet access for dependency downloads

**Note on XDP development**: The hub-router's XDP/AF_XDP data plane requires a Linux kernel 5.15+ with eBPF support. On macOS or WSL2, the XDP components will not function, but the rest of the hub-router can be developed and tested without them.

## Clone and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/penguintechinc/tobogganing.git
cd tobogganing
```

### 2. Install All Dependencies

```bash
make setup
```

This runs the following for each service:
- **hub-api**: `pip install -r requirements.txt` (consider using a virtual environment)
- **hub-router**: `go mod download`
- **hub-webui**: `npm ci`
- **client**: `go mod download`

### 3. Manual Setup (Alternative)

If `make setup` does not suit your workflow, install each service manually.

**hub-api:**
```bash
cd services/hub-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**hub-router:**
```bash
cd services/hub-router
go mod download
```

**hub-webui:**
```bash
cd services/hub-webui
npm ci
```

## Environment Configuration

### Create Environment File

Copy the example environment file and customize it:

```bash
cp .env.example .env
```

### Key Environment Variables

```bash
# General
TOBOGGANING_ENV=development
TOBOGGANING_VERSION=v2.0.0
LOG_LEVEL=DEBUG

# hub-api
HUB_API_HOST=0.0.0.0
HUB_API_PORT=8080
HUB_API_SECRET_KEY=dev-secret-change-in-production
HUB_API_JWT_SECRET=dev-jwt-secret-change-in-production
HUB_API_JWT_EXPIRY=3600

# Database
DB_TYPE=sqlite
DB_URI=sqlite://data/tobogganing.db
# For PostgreSQL:
# DB_TYPE=postgres
# DB_URI=postgres://tobogganing:password@localhost:5432/tobogganing

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# hub-router
HUB_ROUTER_GRPC_PORT=50051
HUB_ROUTER_HEALTH_PORT=9090
HUB_ROUTER_API_ENDPOINT=http://localhost:8080
HUB_ROUTER_XDP_ENABLED=false
HUB_ROUTER_WIREGUARD_PORT=51820

# hub-webui
VITE_API_URL=http://localhost:8080
VITE_WS_URL=ws://localhost:8080

# License (optional for development)
LICENSE_KEY=
LICENSE_SERVER_URL=https://license.penguintech.io
```

**Note**: Never commit `.env` files. The `.gitignore` already excludes them.

## Starting Services

### Option 1: Docker Compose (Recommended)

Start the full development environment with all supporting services:

```bash
make dev
```

This starts:
- **hub-api** at http://localhost:8080
- **hub-webui** at http://localhost:3000
- **Redis** at localhost:6379
- **Redis Commander** at http://localhost:8081
- **Adminer** at http://localhost:8082

To view logs:
```bash
make dev-logs
```

To stop:
```bash
make dev-down
```

To restart:
```bash
make dev-restart
```

### Option 2: Run Services Individually

For tighter development loops, run each service directly on the host.

**Start Redis first** (required by hub-api):
```bash
docker run -d --name tobogganing-redis -p 6379:6379 redis:7-bookworm
```

**hub-api:**
```bash
cd services/hub-api
source .venv/bin/activate  # if using venv
python main.py
# Starts on http://localhost:8080
```

**hub-router:**
```bash
cd services/hub-router
go run ./proxy
# Starts gRPC on :50051, health on :9090
```

**hub-webui:**
```bash
cd services/hub-webui
npm run dev
# Starts on http://localhost:3000 with hot reload
```

## Individual Service Development

### hub-api Development

The hub-api uses Quart (async Flask-compatible framework) with uvicorn.

**Running with auto-reload:**
```bash
cd services/hub-api
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

**Running tests:**
```bash
cd services/hub-api
python -m pytest tests/ -v --cov=.
```

**Linting:**
```bash
cd services/hub-api
python -m flake8 .
python -m black --check .
python -m isort --check-only .
python -m mypy .
python -m bandit -r . -x tests
```

**Auto-formatting:**
```bash
cd services/hub-api
python -m black .
python -m isort .
```

**Database operations:**
```bash
# Initialize database
make db-reset

# Run migrations
make db-migrate
```

### hub-router Development

The hub-router is a Go service requiring CGO for XDP functionality.

**Building:**
```bash
cd services/hub-router
CGO_ENABLED=1 go build -o build/hub-router ./proxy
```

**Running:**
```bash
cd services/hub-router
go run ./proxy
```

**Running tests:**
```bash
cd services/hub-router
go test -v -race ./...
```

**Linting:**
```bash
cd services/hub-router
golangci-lint run
```

**XDP development** (Linux only):
```bash
# Compile eBPF program
cd services/hub-router/bpf
clang -O2 -target bpf -c xdp_filter.c -o xdp_filter.o

# Run with XDP enabled (requires root or CAP_NET_ADMIN)
sudo HUB_ROUTER_XDP_ENABLED=true go run ./proxy
```

### hub-webui Development

The hub-webui uses React with Vite for fast development.

**Running with hot reload:**
```bash
cd services/hub-webui
npm run dev
# Opens at http://localhost:3000
```

**Running tests:**
```bash
cd services/hub-webui
npx vitest --run
```

**Linting:**
```bash
cd services/hub-webui
npm run lint
```

**Formatting:**
```bash
cd services/hub-webui
npm run format
```

**Building for production:**
```bash
cd services/hub-webui
npm run build
# Output in dist/
```

**Previewing production build:**
```bash
cd services/hub-webui
npm run preview
```

## Mock Data Seeding

Seed the development database with realistic test data:

```bash
make seed-mock-data
```

This creates 3-4 items for each feature:

- **Users**: admin@example.com (Admin), maintainer@example.com (Maintainer), viewer@example.com (Viewer), contractor@example.com (Viewer)
- **Groups**: Engineering, Operations, Contractors
- **Hubs**: hub-us-east-1, hub-eu-west-1, hub-ap-southeast-1
- **Policies**: Allow-Web (ports 80/443), Block-Social (domain-based), Engineering-Internal (group + CIDR), Contractor-Limited (user + port restrictions)
- **Clients**: 3-4 registered client devices across different platforms

Default credentials for development:
- **Admin**: admin@example.com / admin123
- **Maintainer**: maintainer@example.com / maintain123
- **Viewer**: viewer@example.com / view123

## Common Developer Tasks

### Adding a New API Endpoint

1. Create the route handler in `services/hub-api/api/`
2. Add request/response models in the handler using Pydantic
3. Register the route in the Quart blueprint
4. Write tests in `services/hub-api/tests/`
5. Update the hub-webui if the endpoint needs a UI

### Adding a New Policy Dimension

1. Update the policy protobuf definition (if using proto files)
2. Update the hub-api policy model and validation
3. Update the hub-router policy engine at `services/hub-router/internal/policy/engine.go`
4. Add XDP filter logic if the dimension can be evaluated in kernel space
5. Update the hub-webui policy editor
6. Write tests at all three levels

### Adding a New Hub Router Feature

1. Implement in `services/hub-router/internal/`
2. Add gRPC interface if hub-api communication is needed
3. Add Prometheus metrics for observability
4. Write Go tests with race detection: `go test -race ./...`
5. Document the feature in hub-webui if user-facing

### Generating Development Certificates

```bash
make certs-generate
```

This creates self-signed certificates in `./certs/` for local TLS development.

## Docker Builds

### Build All Images

```bash
make docker-build
```

### Build Individual Images

```bash
docker build -t tobogganing/hub-api:latest ./services/hub-api
docker build -t tobogganing/hub-router:latest ./services/hub-router
docker build -t tobogganing/hub-webui:latest ./services/hub-webui
```

### Multi-Architecture Builds

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t tobogganing/hub-api:latest ./services/hub-api
```

## Troubleshooting

### hub-api will not start

- Verify Python 3.13+ is installed: `python --version`
- Check that Redis is running: `redis-cli ping` should return `PONG`
- Verify the `.env` file exists and has correct database settings
- Check port 8080 is not in use: `lsof -i :8080`

### hub-router build fails

- Verify Go 1.24+ is installed: `go version`
- Ensure CGO is enabled: `CGO_ENABLED=1`
- On Linux, install eBPF development headers: `apt-get install libbpf-dev`
- Check port 50051 (gRPC) and 9090 (health) are available

### hub-webui shows connection errors

- Verify hub-api is running and accessible at the URL in `VITE_API_URL`
- Check browser console for CORS errors
- Ensure the API proxy configuration in `vite.config.ts` is correct

### Docker Compose issues

- Check Docker daemon is running: `docker info`
- Ensure ports 8080, 3000, 6379, 8081, 8082 are free
- Remove old containers: `docker compose -f docker-compose.dev.yml down -v`
- Rebuild images: `docker compose -f docker-compose.dev.yml build --no-cache`

### XDP errors (Linux only)

- Verify kernel version 5.15+: `uname -r`
- Check eBPF support: `ls /sys/fs/bpf/`
- Ensure `CAP_NET_ADMIN` capability or run with `sudo`
- Check that the network interface supports XDP: `ip link show`

### Database issues

- Reset the development database: `make db-reset`
- Check SQLite file permissions: `ls -la services/hub-api/data/`
- For PostgreSQL, verify the connection string and that the server is running

### General debugging

```bash
# Check all service health
make health

# Run full troubleshooting checks
make troubleshoot

# View Docker container logs
make dev-logs

# Check environment info
make env-info
```

## IDE Setup

### VS Code Recommended Extensions

- **Python**: ms-python.python, ms-python.black-formatter, ms-python.isort
- **Go**: golang.go
- **TypeScript/React**: dbaeumer.vscode-eslint, esbenp.prettier-vscode
- **Docker**: ms-azuretools.vscode-docker
- **Protobuf**: zxh404.vscode-proto3

### VS Code Workspace Settings

Create `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "./services/hub-api/.venv/bin/python",
  "python.formatting.provider": "black",
  "go.toolsManagement.autoUpdate": true,
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter"
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[typescriptreact]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  }
}
```

## Next Steps

After setting up your development environment:

1. Seed mock data: `make seed-mock-data`
2. Open the WebUI at http://localhost:3000 and log in with admin credentials
3. Explore the API at http://localhost:8080/api/v1/
4. Read the [Testing Guide](TESTING.md) for test procedures
5. Review the [Pre-Commit Checklist](PRE_COMMIT.md) before making commits
6. Check [APP_STANDARDS.md](APP_STANDARDS.md) for architecture decisions and conventions
