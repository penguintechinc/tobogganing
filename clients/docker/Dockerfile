# Multi-architecture Docker client for Tobogganing SASE solution
FROM debian:bookworm-slim@sha256:f06537653ac770703bc45b4b113475bd402f451e85223f0f2837acbf89ab020a

# Install runtime dependencies for WireGuard client and SASE functionality
RUN apt-get update && apt-get install -y \
    wireguard-tools \
    iptables \
    iproute2 \
    curl \
    jq \
    openssl \
    ca-certificates \
    bash \
    dnsutils \
    tcpdump \
    && rm -rf /var/lib/apt/lists/*

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
RUN useradd -m -s /bin/bash tobogganing

# Set ownership of relevant directories
RUN chown -R tobogganing:tobogganing /etc/wireguard /certs /config

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
LABEL org.opencontainers.image.title="Tobogganing Docker Client"
LABEL org.opencontainers.image.description="Multi-architecture SASE client with WireGuard VPN and dual authentication"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.vendor="Tobogganing"

# Health check to ensure client connectivity
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD /app/scripts/health-check.sh || exit 1

# Expose WireGuard port (though typically this client initiates connections)
EXPOSE 51820/udp

# Set working directory and entrypoint
WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]