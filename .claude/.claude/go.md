# Go Language Standards

## ⚠️ CRITICAL RULES

**ONLY use Go for high-traffic, performance-critical applications:**
- Applications handling >10K requests/second
- Network-intensive services requiring <10ms latency
- CPU-bound operations requiring maximum throughput
- Memory-constrained deployments

**Default to Python 3.13** for most applications. Use Go when performance profiling proves necessary.

## Version Requirements

- **Target**: Go 1.24.x (latest patch - currently 1.24.2+)
- **Minimum**: Go 1.24.2
- **Fallback**: Go 1.23.x only if compatibility constraints prevent 1.24.x adoption
- **Update `go.mod` line 1**: `go 1.24.2` as baseline

## When to Use Go

**Only evaluate Go for:**
- >10K req/sec throughput requirements
- <10ms latency requirements
- Real-time processing pipelines
- Systems requiring minimal memory footprint
- CPU-bound operations (encryption, compression, data processing)

**Start with Python**, profile performance, then migrate only if measurements prove necessary.

## Database Requirements

**MANDATORY: Cross-database support (PostgreSQL, MySQL, MariaDB, SQLite)**

**Required Libraries:**
- **GORM**: Primary ORM for cross-DB support
  - `gorm.io/gorm` - Core ORM
  - `gorm.io/driver/postgres` - PostgreSQL driver
  - `gorm.io/driver/mysql` - MySQL/MariaDB driver
  - `gorm.io/driver/sqlite` - SQLite driver

**Alternative:** `sqlx` (sqlc) for lightweight SQL mapping if GORM adds overhead

**Requirements:**
- Thread-safe operations with connection pooling
- Support all four databases with identical schema
- Proper error handling and retry logic
- Environment variable configuration for DB selection

## High-Performance Networking

### XDP/AF_XDP Guidance

**Only consider XDP/AF_XDP for extreme network requirements:**

| Packets/Sec | Approach | When to Use |
|-------------|----------|------------|
| < 10K | Standard sockets | Most applications |
| 10K - 100K | Optimized sockets | Profile first |
| 100K+ | XDP/AF_XDP | Kernel bypass needed |

**AF_XDP (Recommended for user-space):**
- Zero-copy packet processing
- Direct NIC-to-user-space access
- Ultra-low latency (<100μs)
- Use `github.com/asavie/xdp` or similar

**XDP (Kernel-space):**
- Earliest stack processing point
- DDoS mitigation, load balancing
- eBPF programs via `github.com/cilium/ebpf`

**NUMA-Aware Optimization:**
- Memory pools aligned to NUMA nodes
- CPU affinity for goroutines on performance-critical paths
- Connection pooling per NUMA node

## Concurrency Patterns

**Leverage goroutines and channels:**
- Goroutines for concurrent operations (very lightweight)
- Channels for safe inter-goroutine communication
- `sync.Pool` for zero-allocation object reuse
- `sync.Map` for concurrent map operations
- Proper context propagation for cancellation/timeouts

```go
import (
    "context"
    "github.com/gin-gonic/gin"
)

// Proper context usage with timeout
func handleRequest(ctx context.Context) {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()
    // Use ctx for all operations
}
```

## Linting Requirements

**MANDATORY: All Go code must pass golangci-lint**

Required linters:
- `staticcheck` - Static analysis
- `gosec` - Security scanning
- `errcheck` - Error handling verification
- `ineffassign` - Unused variable detection
- `gofmt` - Code formatting

**Commands:**
```bash
golangci-lint run ./...
gosec ./...
go fmt ./...
go vet ./...
```

**Pre-commit:** Fix all lint errors before commit - no exceptions.

## Build & Docker Standards

**Multi-stage Docker builds MANDATORY:**
- Build stage: Full Go toolchain, dependencies
- Runtime stage: Minimal `debian:bookworm-slim` or `debian:bookworm-slim`
- Final size should be <50MB for most services

**Version injection at build time:**
```bash
go build -ldflags="-X main.Version=$(cat .version)"
```

## Testing Requirements

- Unit tests with network isolation and mocked dependencies
- Integration tests for database operations
- Performance benchmarks for high-traffic paths
- Coverage target: >80% for critical paths

```bash
go test -v -cover ./...
go test -run BenchmarkName -bench=. -benchmem
```

---

**See Also:**
- [LANGUAGE_SELECTION.md](../docs/standards/LANGUAGE_SELECTION.md)
- [PERFORMANCE.md](../docs/standards/PERFORMANCE.md)
- Go backend service: `/services/go-backend/`
