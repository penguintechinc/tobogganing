# Architecture Standards

Part of [Development Standards](../STANDARDS.md)

## Microservices Architecture

**ALWAYS use microservices architecture for application development**

### Three-Container Architecture

This template provides three base containers representing the core footprints:

| Container | Technology | Purpose | When to Use |
|-----------|------------|---------|-------------|
| **flask-backend** | Flask + PyDAL | Standard APIs, auth, CRUD | <10K req/sec, business logic |
| **go-backend** | Go + XDP/AF_XDP | High-performance networking | >10K req/sec, <10ms latency |
| **webui** | Node.js + React | Frontend shell | All frontend applications |

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NGINX (optional)                               │
└─────────────────────────────────────────────────────────────────────────────┘
          │                        │                          │
┌─────────┴─────────┐   ┌─────────┴─────────┐   ┌────────────┴────────────┐
│  WebUI Container  │   │  Flask Backend    │   │    Go Backend           │
│  (Node.js/React)  │   │  (Flask/PyDAL)    │   │    (XDP/AF_XDP)         │
│                   │   │                   │   │                         │
│ - React SPA       │   │ - /api/v1/auth/*  │   │ - High-perf networking  │
│ - Proxies to APIs │   │ - /api/v1/users/* │   │ - XDP packet processing │
│ - Static assets   │   │ - /api/v1/hello   │   │ - AF_XDP zero-copy      │
│ - Port 3000       │   │ - Port 5000       │   │ - NUMA-aware memory     │
└───────────────────┘   └───────────────────┘   │ - Port 8080             │
                                │              └─────────────────────────┘
                       ┌────────┴────────┐
                       │   PostgreSQL    │
                       └─────────────────┘
```

### Container Details

1. **WebUI Container** (Node.js + React)
   - Express server proxies API calls to backends
   - React SPA with role-based navigation
   - Elder-style collapsible sidebar
   - WaddlePerf-style tab navigation
   - Gold (amber-400) text theme

2. **Flask Backend** (Flask + PyDAL)
   - JWT authentication with bcrypt
   - User management CRUD (Admin only)
   - Role-based access: Admin, Maintainer, Viewer
   - PyDAL for multi-database support
   - Health check endpoints

3. **Go Backend** (Go + XDP/AF_XDP)
   - XDP for kernel-level packet processing
   - AF_XDP for zero-copy user-space I/O
   - NUMA-aware memory allocation
   - Memory slot pools for packet buffers
   - Prometheus metrics

4. **Connector Container** (placeholder)
   - External system integration
   - Background job processing

### Default Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full access: user CRUD, settings, all features |
| **Maintainer** | Read/write access to resources, no user management |
| **Viewer** | Read-only access to resources |

### Design Principles

- **Single Responsibility**: Each container has one clear purpose
- **Independent Deployment**: Services can be updated independently
- **API-First Design**: All inter-service communication via well-defined APIs
- **Data Isolation**: Each service owns its data
- **Fault Isolation**: Failure in one service doesn't cascade
- **Scalability**: Scale individual services based on demand

### Service Communication Patterns

#### Inter-Container Communication (Within Cluster)

**MUST use gRPC or HTTP/3 (QUIC) for all container-to-container communication:**

| Protocol | Use Case | Benefits |
|----------|----------|----------|
| **gRPC** | Service-to-service RPC calls | Binary protocol, streaming, code generation |
| **HTTP/3 (QUIC)** | High-throughput data transfer | 0-RTT, multiplexing, built-in encryption |

```python
# Example: Flask backend calling Go backend via gRPC
import grpc
from generated import backend_pb2, backend_pb2_grpc

def call_go_backend(request_data):
    """Internal service call using gRPC"""
    channel = grpc.insecure_channel('go-backend:50051')  # Docker network
    stub = backend_pb2_grpc.BackendServiceStub(channel)
    response = stub.ProcessData(backend_pb2.DataRequest(data=request_data))
    return response
```

**Why NOT REST for internal communication:**
- Higher latency due to text-based JSON serialization
- No streaming support
- More overhead for frequent service-to-service calls

#### External Communication (Clients, Integrations)

**MUST use REST API over HTTPS for all external-facing endpoints:**

| Protocol | Use Case | Benefits |
|----------|----------|----------|
| **REST/HTTPS** | Client apps, third-party integrations | Universal compatibility, human-readable, well-documented |

```python
# Example: Flask REST endpoint for external clients
@app.route('/api/v1/users', methods=['GET'])
def get_users():
    """External API endpoint - REST over HTTPS"""
    users = db(db.auth_user.active == True).select()
    return jsonify({'users': [u.as_dict() for u in users]})
```

**When to use REST externally:**
- Client-facing APIs (web, mobile apps)
- Third-party integrations and webhooks
- Public API access
- Documentation and developer experience priority

#### Communication Summary

| Direction | Protocol | Port | Example |
|-----------|----------|------|---------|
| WebUI → Flask Backend | REST/HTTPS | 8080 | External client requests |
| Flask → Go Backend | gRPC | 50051 | Internal high-perf operations |
| Go → Flask | gRPC or HTTP/3 | 50051/443 | Internal callbacks |
| External Client → WebUI | HTTPS | 443 | Browser/mobile access |
| External API → Flask | REST/HTTPS | 8080 | Third-party integrations |

#### Asynchronous Communication

- **Message Queues**: Kafka, RabbitMQ for event-driven architecture
- **Use for**: Background jobs, event sourcing, decoupled processing

#### Infrastructure

- **Service Discovery**: Docker networking or service mesh
- **Circuit Breakers**: Fallback mechanisms for failures
- **API Gateway**: MarchProxy for routing external traffic (see below)

### MarchProxy API Gateway Integration

Applications are expected to run behind **MarchProxy** (`~/code/MarchProxy`) for API gateway and load balancing functionality.

**IMPORTANT:** Do NOT include MarchProxy in the application's `docker-compose.yml` - it's external infrastructure managed separately.

#### Configuration Export

Generate MarchProxy-compatible import configuration files in `config/marchproxy/`:

```
config/
└── marchproxy/
    ├── services.json          # Service definitions
    ├── mappings.json          # Route mappings
    └── import-config.json     # Combined import file
```

#### Service Definition Format

```json
{
  "services": [
    {
      "name": "myapp-flask-api",
      "ip_fqdn": "flask-backend",
      "port": 8080,
      "protocol": "http",
      "collection": "myapp",
      "auth_type": "jwt",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/healthz",
      "health_check_interval": 30
    },
    {
      "name": "myapp-go-backend",
      "ip_fqdn": "go-backend",
      "port": 50051,
      "protocol": "grpc",
      "collection": "myapp",
      "auth_type": "none",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/grpc.health.v1.Health/Check",
      "health_check_interval": 10
    },
    {
      "name": "myapp-webui",
      "ip_fqdn": "webui",
      "port": 80,
      "protocol": "http",
      "collection": "myapp",
      "auth_type": "none",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/",
      "health_check_interval": 30
    }
  ]
}
```

#### Mapping Definition Format

```json
{
  "mappings": [
    {
      "name": "myapp-external-api",
      "description": "External REST API access",
      "source_services": ["external"],
      "dest_services": ["myapp-flask-api"],
      "listen_port": 443,
      "protocol": "https",
      "path_prefix": "/api/v1"
    },
    {
      "name": "myapp-webui-access",
      "description": "WebUI frontend access",
      "source_services": ["external"],
      "dest_services": ["myapp-webui"],
      "listen_port": 443,
      "protocol": "https",
      "path_prefix": "/"
    }
  ]
}
```

#### Import Script

Create `scripts/marchproxy-import.sh`:

```bash
#!/bin/bash
# Import service configuration into MarchProxy

MARCHPROXY_API="${MARCHPROXY_API:-http://localhost:8000}"
CLUSTER_API_KEY="${CLUSTER_API_KEY:-}"

if [ -z "$CLUSTER_API_KEY" ]; then
    echo "Error: CLUSTER_API_KEY environment variable required"
    exit 1
fi

# Import services
curl -X POST "$MARCHPROXY_API/api/v1/services/import" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CLUSTER_API_KEY" \
    -d @config/marchproxy/import-config.json

echo "MarchProxy configuration imported"
```

#### Python Configuration Generator

```python
"""Generate MarchProxy import configuration from application settings"""
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class MarchProxyService:
    name: str
    ip_fqdn: str
    port: int
    protocol: str = "http"
    collection: Optional[str] = None
    auth_type: str = "none"
    tls_enabled: bool = False
    health_check_enabled: bool = True
    health_check_path: str = "/healthz"
    health_check_interval: int = 30

def generate_marchproxy_config(app_name: str, services: list[MarchProxyService]) -> dict:
    """Generate MarchProxy-compatible import configuration"""
    return {
        "services": [asdict(s) for s in services],
        "metadata": {
            "app_name": app_name,
            "generated_by": "project-template",
            "version": os.getenv("APP_VERSION", "0.0.0")
        }
    }

def write_marchproxy_config(config: dict, output_dir: str = "config/marchproxy"):
    """Write configuration files for MarchProxy import"""
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/import-config.json", "w") as f:
        json.dump(config, f, indent=2)

# Example usage
if __name__ == "__main__":
    services = [
        MarchProxyService(
            name="myapp-flask-api",
            ip_fqdn="flask-backend",
            port=8080,
            protocol="http",
            collection="myapp",
            auth_type="jwt"
        ),
        MarchProxyService(
            name="myapp-go-backend",
            ip_fqdn="go-backend",
            port=50051,
            protocol="grpc",
            collection="myapp"
        ),
    ]

    config = generate_marchproxy_config("myapp", services)
    write_marchproxy_config(config)
```

#### Integration Notes

1. **Service Names**: Use `{app_name}-{service}` naming convention for easy filtering
2. **Collection**: Group all app services under same collection for bulk operations
3. **Protocol Selection**:
   - `http`/`https`: REST API endpoints (Flask)
   - `grpc`: Internal high-performance services (Go backend)
   - `tcp`: Raw TCP connections
4. **Health Checks**: Always enable for production services
5. **Auth Type**: Use `jwt` for external-facing APIs, `none` for internal gRPC

#### MarchProxy API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/services` | POST | Create service |
| `/api/v1/services/import` | POST | Bulk import services |
| `/api/v1/services` | GET | List services |
| `/api/v1/services/{id}` | PUT | Update service |
| `/api/v1/services/{id}` | DELETE | Delete service |
| `/api/v1/config/{cluster_id}` | GET | Get cluster config |

📚 **Full MarchProxy Documentation**: See `~/code/MarchProxy/api-server/README.md`

### Container Organization

```
project-name/
├── services/
│   ├── flask-backend/      # Flask + PyDAL backend (auth, users, APIs)
│   ├── go-backend/         # Go high-performance backend (XDP, NUMA)
│   ├── webui/              # Node.js + React frontend shell
│   └── connector/          # Integration services (placeholder)
```

---

## Docker Standards

### Build Standards

**All builds MUST be executed within Docker containers:**

```bash
# Go builds (using debian-slim)
docker run --rm -v $(pwd):/app -w /app golang:1.24-slim go build -o bin/app

# Python builds (using debian-slim)
docker run --rm -v $(pwd):/app -w /app python:3.13-slim pip install -r requirements.txt
```

**Use multi-stage builds with debian-slim:**
```dockerfile
FROM golang:1.24-slim AS builder
FROM debian:stable-slim AS runtime

FROM python:3.13-slim AS builder
FROM debian:stable-slim AS runtime
```

### Docker Compose Standards

**ALWAYS create docker-compose.dev.yml for local development**

**Prefer Docker networks over host ports:**
- Minimize host port exposure
- Only expose ports for developer access
- Use named Docker networks for service-to-service communication

```yaml
# docker-compose.dev.yml
version: '3.8'

networks:
  app-network:
    driver: bridge
  db-network:
    driver: bridge

services:
  app:
    build: ./apps/app
    networks:
      - app-network
      - db-network
    ports:
      - "8080:8080"  # Only expose for developer access
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/appdb

  postgres:
    image: postgres:16-alpine
    networks:
      - db-network
    # NO ports exposed to host - only accessible via Docker network
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=appdb
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
```

### Multi-Arch Build Strategy

GitHub Actions should use multi-arch builds:
```yaml
- uses: docker/build-push-action@v4
  with:
    platforms: linux/amd64,linux/arm64
    context: ./apps/app
    file: ./apps/app/Dockerfile
```

### Cross-Architecture Testing

**Before final commit, test on alternate architecture:**

- **If developing on amd64**: Use QEMU to build and test arm64 (`docker buildx build --platform linux/arm64 ...`)
- **If developing on arm64**: Use QEMU to build and test amd64 (`docker buildx build --platform linux/amd64 ...`)
- Ensures multi-architecture compatibility and prevents platform-specific bugs
- Command: `docker buildx build --platform linux/amd64,linux/arm64 -t image:tag --push .`

### Health Check Standards

**CRITICAL: Use native container code for health checks, NOT curl/wget**

Most minimal container images (debian-slim, alpine, distroless) do NOT include `curl` or `wget`. Health checks MUST use the native language runtime already in the container.

#### Docker HEALTHCHECK Directive

**Python Containers:**
```dockerfile
# ❌ BAD - curl not available in python:3.13-slim
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/healthz || exit 1

# ✅ GOOD - use Python's built-in http.client
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import http.client; \
    conn = http.client.HTTPConnection('localhost', 5000); \
    conn.request('GET', '/healthz'); \
    r = conn.getresponse(); \
    exit(0 if r.status == 200 else 1)"
```

**Go Containers:**
```dockerfile
# ❌ BAD - curl not available in distroless or debian-slim
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/healthz || exit 1

# ✅ GOOD - create small health check binary
# In Dockerfile multi-stage build:
FROM golang:1.24-slim AS builder
WORKDIR /app
COPY . .
RUN go build -o app ./cmd/app
RUN go build -o healthcheck ./cmd/healthcheck  # Build health check binary

FROM debian:stable-slim
COPY --from=builder /app/app /app/app
COPY --from=builder /app/healthcheck /usr/local/bin/healthcheck

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["/usr/local/bin/healthcheck"]

# cmd/healthcheck/main.go:
# package main
# import ("net/http"; "os")
# func main() {
#   resp, err := http.Get("http://localhost:8080/healthz")
#   if err != nil || resp.StatusCode != 200 { os.Exit(1) }
#   os.Exit(0)
# }
```

**Node.js Containers:**
```dockerfile
# ❌ BAD - curl not available in node:18-slim
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:3000/healthz || exit 1

# ✅ GOOD - use Node's built-in http module
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/healthz', \
    (r) => process.exit(r.statusCode === 200 ? 0 : 1)) \
    .on('error', () => process.exit(1))"
```

#### Docker Compose Health Checks

**Python service:**
```yaml
services:
  flask-backend:
    build: ./services/flask-backend
    healthcheck:
      test: ["CMD", "python3", "-c", "import http.client; conn = http.client.HTTPConnection('localhost', 5000); conn.request('GET', '/healthz'); r = conn.getresponse(); exit(0 if r.status == 200 else 1)"]
      interval: 30s
      timeout: 3s
      start_period: 5s
      retries: 3
```

**Go service:**
```yaml
services:
  go-backend:
    build: ./services/go-backend
    healthcheck:
      test: ["CMD", "/usr/local/bin/healthcheck"]
      interval: 30s
      timeout: 3s
      start_period: 5s
      retries: 3
```

**Node.js service:**
```yaml
services:
  webui:
    build: ./services/webui
    healthcheck:
      test: ["CMD", "node", "-e", "require('http').get('http://localhost:3000/healthz', (r) => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"]
      interval: 30s
      timeout: 3s
      start_period: 5s
      retries: 3
```

#### Health Check Endpoints

All services MUST implement a `/healthz` endpoint:

**Flask:**
```python
@app.route('/healthz')
def health_check():
    """Health check endpoint for container orchestration"""
    return {'status': 'healthy'}, 200
```

**Go:**
```go
func healthHandler(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
    w.Write([]byte(`{"status":"healthy"}`))
}

// In main():
http.HandleFunc("/healthz", healthHandler)
```

**Node.js/Express:**
```javascript
app.get('/healthz', (req, res) => {
  res.status(200).json({ status: 'healthy' });
});
```

#### Key Principles

1. **Never add curl/wget**: Don't install additional packages just for health checks
2. **Use native runtime**: Python, Go, Node.js are already in the container
3. **Keep it simple**: Health checks should be fast and lightweight
4. **Standard endpoint**: Use `/healthz` for HTTP health checks
5. **Proper exit codes**: Exit 0 for healthy, exit 1 for unhealthy
6. **gRPC health**: Use standard gRPC health check protocol for gRPC services
