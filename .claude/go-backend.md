# Go Backend Service Standards

## ⚠️ CRITICAL RULES

**ONLY use Go backend for applications with these EXACT criteria:**
- Traffic: >10K requests/second
- Latency: <10ms required response times
- Networking: High-performance, packet-intensive operations

**For all other cases, use Flask backend (Python).** Go adds complexity and maintenance burden. Justify Go usage in code comments if you diverge.

---

## Language & Version Requirements

- **Go 1.24.x** (latest patch: 1.24.2+) - REQUIRED
- Fallback: Go 1.23.x only if 1.24.x unavailable
- All builds must execute within Docker containers (golang:1.24-slim)

---

## Use Cases

**ONLY appropriate for:**
1. Ultra-high-throughput services (>10K req/sec)
2. Low-latency networking critical (<10ms)
3. Packet-level processing (>100K packets/sec)
4. CPU-intensive operations requiring max throughput

**NOT for:**
- Standard REST APIs (use Flask)
- Business logic and CRUD operations (use Flask)
- Simple integrations (use Flask)

---

## Database Support

**Required: Multi-database support via GORM or sqlx**

Support all databases by default:
- PostgreSQL (primary/default)
- MySQL 8.0+
- MariaDB Galera (with WSREP, auto-increment, transaction handling)
- SQLite (development/lightweight)

**Environment Variable:**
```bash
DB_TYPE=postgresql  # Sets database type and connection string format
```

**Example: GORM Multi-DB Connection**
```go
var db *gorm.DB

switch os.Getenv("DB_TYPE") {
case "mysql":
    db, _ = gorm.Open(mysql.Open(os.Getenv("DATABASE_URL")))
case "sqlite":
    db, _ = gorm.Open(sqlite.Open(os.Getenv("DATABASE_URL")))
default: // postgresql
    db, _ = gorm.Open(postgres.Open(os.Getenv("DATABASE_URL")))
}
```

---

## Inter-Container Communication

**gRPC REQUIRED for container-to-container communication:**
- Preferred: gRPC with Protocol Buffers (.proto files)
- Use: Internal APIs between microservices
- Port: 50051 (standard gRPC port)
- Fallback: REST over HTTP/2 only if gRPC unavailable

**External Communication:**
- Use: REST API over HTTPS for client-facing endpoints
- Format: `/api/v{major}/endpoint` (versioned)
- Port: 8080 (standard REST API port)

---

## High-Performance Networking

**XDP/AF_XDP for extreme requirements ONLY:**

| Packets/Sec | Technology | Justification |
|-------------|------------|---------------|
| <100K | Standard Go networking | Sufficient for most cases |
| 100K-500K | Consider XDP | Profile first, evaluate complexity |
| >500K | XDP/AF_XDP required | Performance-critical only |

**XDP (Kernel-level):**
- Packet filtering, DDoS mitigation, load balancing
- Requires: Linux 4.8+, BPF bytecode (C + eBPF)
- Language: Typically C with Go integration

**AF_XDP (User-space Zero-copy):**
- Custom network protocols, ultra-low latency (<1ms)
- Zero-copy socket for packet processing
- Language: Go with asavie/xdp or similar library

---

## Code Quality & Linting

**golangci-lint** (mandatory):
```bash
golangci-lint run ./...
```

Required linters:
- `staticcheck` - Static analysis
- `gosec` - Security issues
- `errcheck` - Unchecked error returns
- `ineffassign` - Ineffective assignments
- `unused` - Unused variables/functions

---

## Performance Patterns

**Required concurrency patterns:**

1. **Goroutines** - Concurrent operations
2. **Channels** - Safe communication between goroutines
3. **sync.Pool** - Object pooling for memory efficiency
4. **sync.Map** - Concurrent key-value storage
5. **Context** - Cancellation, timeouts, deadline propagation

**NUMA-aware memory pools** (if >10K req/sec):
```go
// Pre-allocate buffers for packet processing
type BufferPool struct {
    buffers chan []byte
}

func NewBufferPool(size, bufferSize int) *BufferPool {
    return &BufferPool{
        buffers: make(chan []byte, size),
    }
}
```

---

## Monitoring & Metrics

**Prometheus metrics required:**
- Request/response times (histograms)
- Error rates (counters)
- Goroutine count (gauges)
- Memory usage (gauges)
- Packet processing rate (counters, for networking services)

**Metrics port:** 9090 (standard)

---

## Deployment Requirements

**Docker multi-stage builds:**
```dockerfile
FROM golang:1.24-slim AS builder
WORKDIR /app
COPY . .
RUN go build -o app

FROM debian:stable-slim
COPY --from=builder /app/app /app
HEALTHCHECK --interval=30s --timeout=3s \
  CMD ["/usr/local/bin/healthcheck"]
EXPOSE 8080
CMD ["/app"]
```

**Health checks:** Use native Go binary, NOT curl
**Multi-arch:** Build for linux/amd64 and linux/arm64

---

## Security Requirements

- Input validation mandatory
- Error handling for all operations
- TLS 1.2+ for all external communication
- JWT authentication for REST endpoints
- gRPC health checks enabled
- Security scanning: `gosec ./...` before commit
- CodeQL compliance required

---

## Testing Requirements

- Unit tests: Mocked dependencies, isolated
- Integration tests: Container interactions
- Smoke tests: Build, run, health checks, API endpoints
- Performance tests: Throughput, latency benchmarks

