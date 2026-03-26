FROM golang:1.24-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    libc6-dev \
    linux-headers-generic \
    libelf-dev \
    libz-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy go mod files and download dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the Go application
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -ldflags="-w -s" -o headend-proxy ./proxy

# Build the healthcheck binary
RUN go build -o healthcheck ./cmd/healthcheck

# Production image
FROM debian:bookworm-slim@sha256:f06537653ac770703bc45b4b113475bd402f451e85223f0f2837acbf89ab020a

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    wireguard-tools \
    iptables \
    ip6tables \
    iproute2 \
    openssl \
    ca-certificates \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app /etc/wireguard /certs /config

# Copy application and scripts
COPY --from=builder /build/headend-proxy /app/
COPY --from=builder /build/healthcheck /app/
COPY wireguard/scripts/ /app/scripts/
COPY entrypoint.sh /app/

# Set permissions
RUN chmod +x /app/headend-proxy /app/healthcheck /app/entrypoint.sh /app/scripts/*.sh

# Create wireguard user
RUN addgroup --system wireguard && adduser --system --ingroup wireguard wireguard

# Set ownership
RUN chown -R wireguard:wireguard /etc/wireguard /certs

# Expose ports
# 51820: WireGuard VPN
# 8443: HTTPS proxy
# 8444: TCP proxy
# 8445: UDP proxy
# 9090: Metrics
EXPOSE 51820/udp 8443/tcp 8444/tcp 8445/udp 9090/tcp

# Health check using native Go binary
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /app/healthcheck

# Environment defaults
ENV CLUSTER_ID=""
ENV CLUSTER_API_KEY=""
ENV MANAGER_URL="http://hub-api:8080"
ENV HEADEND_AUTH_TYPE="jwt"
ENV HEADEND_LOG_LEVEL="info"
ENV HEADEND_MIRROR_ENABLED="false"

WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
