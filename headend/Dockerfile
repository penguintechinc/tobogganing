FROM golang:1.23-alpine AS builder

WORKDIR /build

# Install build dependencies
RUN apk add --no-cache git gcc musl-dev linux-headers

# Copy go mod files and download dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the Go application
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -ldflags="-w -s" -o headend-proxy ./proxy

# Production image
FROM alpine:3.19

# Install runtime dependencies
RUN apk add --no-cache \
    wireguard-tools \
    iptables \
    ip6tables \
    iproute2 \
    openssl \
    ca-certificates \
    tcpdump \
    curl \
    jq \
    bash \
    && rm -rf /var/cache/apk/*

# Create directories
RUN mkdir -p /app /etc/wireguard /certs /config

# Copy application and scripts
COPY --from=builder /build/headend-proxy /app/
COPY wireguard/scripts/ /app/scripts/
COPY entrypoint.sh /app/

# Set permissions
RUN chmod +x /app/headend-proxy /app/entrypoint.sh /app/scripts/*.sh

# Create wireguard user
RUN addgroup -S wireguard && adduser -S -G wireguard wireguard

# Set ownership
RUN chown -R wireguard:wireguard /etc/wireguard /certs

# Expose ports
# 51820: WireGuard VPN
# 8443: HTTPS proxy
# 8444: TCP proxy  
# 8445: UDP proxy
# 9090: Metrics
EXPOSE 51820/udp 8443/tcp 8444/tcp 8445/udp 9090/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

# Environment defaults
ENV CLUSTER_ID=""
ENV CLUSTER_API_KEY=""
ENV MANAGER_URL="http://manager:8000"
ENV HEADEND_AUTH_TYPE="jwt"
ENV HEADEND_LOG_LEVEL="info"
ENV HEADEND_MIRROR_ENABLED="false"

WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]