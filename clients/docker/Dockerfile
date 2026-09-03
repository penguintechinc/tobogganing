# Multi-architecture Docker client for SASEWaddle SASE solution
FROM alpine:3.19@sha256:6baf43584bcb78f2e5847d1de515f23499913ac9f12bdf834811a3145eb11ca1

# Install runtime dependencies for WireGuard client and SASE functionality
# hadolint ignore=DL3018
RUN apk add --no-cache \
    wireguard-tools \
    iptables \
    ip6tables \
    iproute2 \
    curl \
    jq \
    openssl \
    ca-certificates \
    bash \
    bind-tools \
    tcpdump \
    && rm -rf /var/cache/apk/*

# Create directories for configuration and certificates
RUN mkdir -p /app /etc/wireguard /certs /config

WORKDIR /app

# Copy client scripts and entrypoint
COPY scripts/ /app/scripts/
COPY entrypoint.sh /app/
COPY config/ /app/config/

# Set executable permissions
RUN chmod +x /app/entrypoint.sh /app/scripts/*.sh

# Create non-root user for security
RUN addgroup -S sasewaddle && adduser -S -G sasewaddle sasewaddle

# Set ownership of relevant directories
RUN chown -R sasewaddle:sasewaddle /etc/wireguard /certs /config

# Build-time configuration (sensitive args left empty; set at runtime via env)
ARG CLIENT_TYPE="client_docker"
ARG LOG_LEVEL="info"
ARG AUTO_CONNECT="true"
ARG HEARTBEAT_INTERVAL="30"
ARG CONFIG_REFRESH_INTERVAL="300"

# Labels for multi-architecture support
LABEL org.opencontainers.image.title="SASEWaddle Docker Client"
LABEL org.opencontainers.image.description="Multi-architecture SASE client with WireGuard VPN and dual authentication"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.vendor="SASEWaddle"

# Health check to ensure client connectivity
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["/bin/sh", "-c", "/app/scripts/health-check.sh || exit 1"]

# Expose WireGuard port (though typically this client initiates connections)
# Create non-root user for runtime
RUN addgroup -S appuser && adduser -S -G appuser appuser &&\
    chown -R appuser:appuser /app
EXPOSE 51820/udp

# Set working directory and entrypoint
WORKDIR /app
# hadolint ignore=DL3066
USER appuser
ENTRYPOINT ["/app/entrypoint.sh"]
