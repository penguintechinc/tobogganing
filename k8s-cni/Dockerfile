# Multi-stage Dockerfile for Tobogganing CNI Plugin
# Builds a lightweight, secure container with the CNI binary

# Build stage
FROM golang:1.23-alpine AS builder

# Install build dependencies
RUN apk add --no-cache \
    git \
    make \
    ca-certificates \
    tzdata \
    && update-ca-certificates

# Set working directory
WORKDIR /src

# Copy go mod files first for better caching
COPY go.mod go.sum ./
RUN go mod download && go mod verify

# Copy source code
COPY . .

# Build arguments
ARG VERSION=dev
ARG GIT_COMMIT=unknown
ARG TARGETOS=linux
ARG TARGETARCH=amd64

# Build the binary with optimizations
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build \
    -ldflags "-s -w -X main.BuildVersion=${VERSION} -X main.GitCommit=${GIT_COMMIT}" \
    -a -installsuffix cgo \
    -o tobogganing-cni \
    ./cmd/tobogganing-cni

# Verify the binary
RUN chmod +x tobogganing-cni && ./tobogganing-cni --help || true

# Final stage - minimal runtime image
FROM alpine:3.18

# Install runtime dependencies
RUN apk add --no-cache \
    ca-certificates \
    iptables \
    iproute2 \
    wireguard-tools \
    curl \
    jq \
    gettext \
    && rm -rf /var/cache/apk/*

# Create non-root user for security
RUN addgroup -g 1001 cni && \
    adduser -D -u 1001 -G cni -s /bin/sh cni

# Set up directories
RUN mkdir -p /opt/cni/bin \
    /etc/cni/net.d \
    /var/lib/cni \
    /var/log/tobogganing-cni \
    /etc/cni/net.d/tobogganing \
    && chown -R cni:cni /var/lib/cni /var/log/tobogganing-cni /etc/cni/net.d/tobogganing

# Copy binary from builder
COPY --from=builder /src/tobogganing-cni /tobogganing-cni

# Copy configuration templates
COPY examples/cni-config.json /etc/cni/tobogganing.conflist

# Copy entrypoint script
COPY <<EOF /entrypoint.sh
#!/bin/sh
set -e

# Check if running as init container (installing binary)
if [ "\$1" = "install" ]; then
    echo "Installing CNI binary to \${CNI_BIN_DIR:-/host/opt/cni/bin}..."
    cp /tobogganing-cni "\${CNI_BIN_DIR:-/host/opt/cni/bin}/tobogganing"
    chmod +x "\${CNI_BIN_DIR:-/host/opt/cni/bin}/tobogganing"
    echo "CNI binary installed successfully"
    exit 0
fi

# Check if running as config installer
if [ "\$1" = "config" ]; then
    echo "Installing CNI configuration..."
    
    # Substitute environment variables in config
    envsubst < /etc/cni/tobogganing.conflist > "\${CNI_CONF_DIR:-/host/etc/cni/net.d}/10-tobogganing.conflist"
    
    echo "CNI configuration installed successfully"
    
    # Keep running and monitor config file
    while true; do
        sleep 300
        if [ ! -f "\${CNI_CONF_DIR:-/host/etc/cni/net.d}/10-tobogganing.conflist" ]; then
            echo "CNI config missing, reinstalling..."
            envsubst < /etc/cni/tobogganing.conflist > "\${CNI_CONF_DIR:-/host/etc/cni/net.d}/10-tobogganing.conflist"
        fi
    done
fi

# Default: run the CNI binary
exec /tobogganing-cni "\$@"
EOF

RUN chmod +x /entrypoint.sh

# Set up proper permissions
RUN chown root:root /tobogganing-cni /entrypoint.sh && \
    chmod 755 /tobogganing-cni /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD /tobogganing-cni --version || exit 1

# Security: Run as root (required for network operations in Kubernetes)
# CNI plugins must run as root to manage network interfaces
USER root

# Labels for metadata
LABEL maintainer="Tobogganing Project <info@tobogganing.io>" \
      version="${VERSION}" \
      description="High-performance Kubernetes CNI plugin for Tobogganing SASE" \
      org.opencontainers.image.title="Tobogganing CNI" \
      org.opencontainers.image.description="Kubernetes CNI plugin with WireGuard and Zero Trust networking" \
      org.opencontainers.image.url="https://github.com/tobogganing/k8s-cni" \
      org.opencontainers.image.documentation="https://docs.tobogganing.io/cni" \
      org.opencontainers.image.source="https://github.com/tobogganing/k8s-cni" \
      org.opencontainers.image.vendor="Tobogganing Project" \
      org.opencontainers.image.licenses="MIT"

# Environment variables
ENV CNI_BIN_DIR="/opt/cni/bin" \
    CNI_CONF_DIR="/etc/cni/net.d" \
    TOBOGGANING_CNI_LOG_LEVEL="info" \
    TOBOGGANING_CNI_LOG_FORMAT="json"

# Default entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command shows help
CMD ["--help"]