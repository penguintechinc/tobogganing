FROM golang:1.23-bookworm@sha256:167053a2bb901972bf2c1611f8f52c44d5fe7e762e5cab213708d82c421614db AS builder

WORKDIR /build

# Install build dependencies
# CGO needed for wgctrl (WireGuard netlink bindings)
# - gcc: C compiler
# - libc6-dev: glibc headers (replaces musl-dev; hub-router uses glibc, not musl)
# - linux-libc-dev: kernel userspace headers for netlink
# apt version pinning is build-fragile across bookworm point releases; base image digest-pinned
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    git gcc libc6-dev linux-libc-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy go mod files and download dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the Go application
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -ldflags="-w -s" -o headend-proxy ./proxy

# Production image
FROM debian:bookworm-slim@sha256:60eac759739651111db372c07be67863818726f754804b8707c90979bda511df

# Install runtime dependencies
# apt version pinning is build-fragile across bookworm point releases; base image digest-pinned
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools \
    iptables \
    iproute2 \
    openssl \
    ca-certificates \
    iputils-ping \
    curl \
    jq \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app /etc/wireguard /certs /config

# Copy application and scripts
COPY --from=builder /build/headend-proxy /app/
COPY wireguard/scripts/ /app/scripts/
COPY entrypoint.sh /app/

# Set permissions
RUN chmod +x /app/headend-proxy /app/entrypoint.sh /app/scripts/*.sh

# Create wireguard user and group
RUN groupadd -r wireguard && useradd -r -g wireguard wireguard

# Set ownership
RUN chown -R wireguard:wireguard /etc/wireguard /certs /app /config

# Expose ports
# 51820: WireGuard VPN
# 8443: HTTPS proxy
# 8444: TCP proxy
# 8445: UDP proxy
# 9090: Metrics
EXPOSE 51820/udp 8443/tcp 8444/tcp 8445/udp 9090/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/bin/sh", "-c", "curl -f http://localhost:9090/health || exit 1"]

# Environment defaults
ENV CLUSTER_ID=""
# empty placeholder; real value injected at runtime via secret, never baked in
# hadolint ignore=DL3064
ENV CLUSTER_API_KEY=""
ENV MANAGER_URL="http://manager:8000"
ENV HEADEND_AUTH_TYPE="jwt"
ENV HEADEND_LOG_LEVEL="info"
ENV HEADEND_MIRROR_ENABLED="false"

WORKDIR /app
# non-root 'wireguard' user created above; name intentional (numeric-UID is a host-resolvability nicety)
# hadolint ignore=DL3066
USER wireguard
ENTRYPOINT ["/app/entrypoint.sh"]
