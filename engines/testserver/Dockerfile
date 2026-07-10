# Build stage
FROM golang:1.25-bookworm@sha256:a9c020ee3d1508c7be5435c262434e3d3fc1d0e76a11afeb9ddae7d60bc86aa4 AS builder

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY cmd ./cmd
COPY internal ./internal

# Build binary
ARG TARGETOS=linux
ARG TARGETARCH=amd64
RUN CGO_ENABLED=1 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build \
    -ldflags="-s -w" \
    -o testserver \
    ./cmd/testserver

# Runtime stage
FROM debian:bookworm-slim@sha256:60eac759739651111db372c07be67863818726f754804b8707c90979bda511df

# Install runtime dependencies (ca-certificates for TLS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r app && useradd -r -g app -u 1000 app

WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/testserver .

# Set ownership
RUN chown -R app:app /app

# ROOT EXCEPTION (approved): NET_RAW required for ICMP raw sockets in network testing
USER app

EXPOSE 8080

# Health check via GET /health endpoint (K8s handles via liveness/readiness probes)

ENV PORT=8080 \
    AUTH_ENABLED=true \
    MAX_CONCURRENT_TESTS=100

CMD ["/app/testserver"]
