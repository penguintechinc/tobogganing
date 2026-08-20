# Multi-stage Dockerfile for node-agent: Rust SASE connectivity + netsvcs-edge agent
# Builder stage: Compiles the static musl binary
# Runtime stage: Minimal Debian container with non-root user, CAP_NET_ADMIN + CAP_NET_BIND_SERVICE

# BUILDER STAGE: Compile static musl binary
# NOTE: Build context should be the worktree root, not agents/node-agent/
# Example: docker build -f agents/node-agent/Dockerfile -t node-agent:p4 .
FROM rust:1.98-slim-bookworm@sha256:94e9efa4033213dbb70d4f665527e7ece3944ddb7ba1dd2e43f6fd6e2490af58 AS builder

WORKDIR /build

# Install musl toolchain for static Linux target (versions locked by rust:1.98-slim-bookworm base image)
# hadolint ignore=DL3059
RUN apt-get update && apt-get install -y --no-install-recommends \
    musl-tools=1.2.5-1 \
    && rm -rf /var/lib/apt/lists/*

# Add musl target
# hadolint ignore=DL3059
RUN rustup target add x86_64-unknown-linux-musl

# Copy workspace and crate manifests from worktree root
# Note: build.rs expects proto at /proto (4 levels up from /build/crates/transport)
COPY agents/node-agent/Cargo.toml agents/node-agent/Cargo.lock ./
COPY agents/node-agent/crates ./crates
COPY proto /proto

# Build the agent binary statically linked (release profile with lto, strip, etc.)
# The profile.release in Cargo.toml sets: lto=true, codegen-units=1, strip=true, panic="abort"
# hadolint ignore=DL3059
RUN cargo build --release --target x86_64-unknown-linux-musl -p node-agent

# Extract the binary name from Cargo.toml for clarity; the agent crate's bin is "node-agent"
# hadolint ignore=DL3059
RUN cp /build/target/x86_64-unknown-linux-musl/release/node-agent /tmp/node-agent


# RUNTIME STAGE: Minimal Debian container with non-root user
FROM debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241

WORKDIR /

# Create a dedicated non-root user for the agent (uid 11000, no shell, system user)
RUN groupadd --system node-agent && \
    useradd --system --gid node-agent --uid 11000 node-agent

# Copy the statically linked binary from builder
COPY --from=builder /tmp/node-agent /usr/local/bin/node-agent
RUN chmod 755 /usr/local/bin/node-agent

# Set the non-root user (numeric UID for hadolint compliance)
USER 11000

# Expose DNS port for netsvcs-edge (informational; actual port binding requires NET_BIND_SERVICE cap)
EXPOSE 53/udp 53/tcp

# HEALTHCHECK: Invoke the binary's built-in `healthz` subcommand
# The agent binary supports `node-agent healthz` to check readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/usr/local/bin/node-agent", "healthz"]

# ROOT EXCEPTION (approved): The pod requires CAP_NET_ADMIN (WireGuard TUN device access)
# and CAP_NET_BIND_SERVICE (:53 DNS binding). These are declared in the Helm securityContext
# and are the only privileged capabilities needed; the process itself runs as non-root uid 11000.
# The agent handles all networking via the capabilities, not privilege escalation.

# Default entrypoint: run the agent in the mode specified by NODE_AGENT_MODE env var
# (DaemonSet or Edge; typically set via Helm values)
# Use JSON array form for proper signal handling in containers
ENTRYPOINT ["/usr/local/bin/node-agent"]
CMD ["run"]
