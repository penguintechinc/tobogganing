# Multi-architecture Docker client for SASEWaddle SASE solution
FROM alpine:3.19

# Install runtime dependencies for WireGuard client and SASE functionality
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

# Environment variables for SASE client configuration
ENV MANAGER_URL=""
ENV CLIENT_API_KEY=""
ENV CLIENT_NAME=""
ENV CLIENT_TYPE="client_docker"
ENV LOG_LEVEL="info"
ENV AUTO_CONNECT="true"
ENV HEARTBEAT_INTERVAL="30"
ENV CONFIG_REFRESH_INTERVAL="300"

# Labels for multi-architecture support
LABEL org.opencontainers.image.title="SASEWaddle Docker Client"
LABEL org.opencontainers.image.description="Multi-architecture SASE client with WireGuard VPN and dual authentication"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.vendor="SASEWaddle"

# Health check to ensure client connectivity
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD /app/scripts/health-check.sh || exit 1

# Expose WireGuard port (though typically this client initiates connections)
EXPOSE 51820/udp

# Set working directory and entrypoint
WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]