# OpenZiti Overlay Integration Guide

## Overview

**OpenZiti** is an open-source, zero-trust overlay networking platform. This guide covers how to optionally integrate OpenZiti with Tobogganing as an alternative or complement to WireGuard for environments requiring application-embedded zero-trust networking.

## What is OpenZiti?

OpenZiti provides:
- Open-source zero-trust overlay network
- Application-embedded identity (no appliances required)
- Fine-grained, policy-driven access control
- Encrypted tunneling with mutual TLS
- Support for traditional and modern applications

## Why OpenZiti with Tobogganing?

OpenZiti complements Tobogganing's unified networking layer by:

1. **Alternative overlay**: Use OpenZiti instead of WireGuard for zero-trust architectures
2. **Application embedding**: Embed OpenZiti SDK directly in applications
3. **Policy-driven access**: Fine-grained policy enforcement at application level
4. **Legacy support**: Wrap legacy applications without OS-level VPN
5. **Multi-overlay support**: Run both WireGuard and OpenZiti simultaneously

### Use Cases

- **Microservices**: Embed OpenZiti SDK in containerized services
- **Legacy applications**: Wrap applications that don't support WireGuard
- **Application-level zero trust**: Fine-grained per-app identity and access
- **Compliance**: Satisfy requirements for application-level encryption and identity

## Architecture

Tobogganing's **OverlayProvider** interface supports multiple overlay implementations:

```go
// OverlayProvider interface (hub-router and native client)
type OverlayProvider interface {
    // Identify provider
    Name() string

    // Initialize provider with config
    Initialize(ctx context.Context, cfg ProviderConfig) error

    // Connect to overlay network
    Connect(ctx context.Context, clientID string) (OverlayConnection, error)

    // Disconnect from overlay
    Disconnect(ctx context.Context, clientID string) error

    // Route packet through overlay
    HandlePacket(ctx context.Context, pkt *Packet) error

    // Export metrics (Prometheus)
    Metrics() map[string]interface{}

    // Graceful shutdown
    Close() error
}
```

### Implementation Structure

```
OverlayManager
├── WireGuardProvider
│   └── wireguard.go (existing WG implementation)
└── OpenZitiProvider (build-tag: openziti)
    ├── controller.go (controller communication)
    ├── identity.go (identity enrollment)
    ├── session.go (session management)
    └── routing.go (packet routing)
```

## Build Configuration

### Compile With OpenZiti Support

OpenZiti support is gated behind a build tag to keep base builds lightweight:

```bash
# Build with OpenZiti overlay support
go build -tags openziti ./cmd/hub-router

# Build without OpenZiti (default, smaller binary)
go build ./cmd/hub-router
```

### Dependencies

When building with OpenZiti tag, adds dependencies:

```go
require (
    github.com/openziti/sdk-golang v0.20.0
    github.com/openziti/edge v0.25.0
)
```

Keep these in `go.mod` for optional inclusion; they're only imported when `openziti` tag present.

## Configuration

### Hub-Router Configuration

Enable OpenZiti overlay in hub-router:

```yaml
# deploy/kubernetes/values-hub-router.yaml
overlay:
  type: "openziti"  # or "wireguard" (default)
  openziti:
    controller_url: "https://ziti-controller.example.com:6262"
    # Identity file for hub-router controller enrollment
    identity_file: "/etc/tobogganing/ziti-identity.json"
    # Optional: controller certificate
    controller_ca_cert: "/etc/tobogganing/ziti-controller-ca.pem"
    # Session refresh interval
    session_refresh_interval: "1h"
    # Dial timeout
    dial_timeout: "30s"
```

Environment variables:

```bash
# Enable OpenZiti overlay
HUB_ROUTER_OVERLAY_TYPE=openziti

# OpenZiti controller endpoint
HUB_ROUTER_OPENZITI_CONTROLLER_URL=https://ziti-controller.example.com:6262

# Hub-router identity file (path inside container/pod)
HUB_ROUTER_OPENZITI_IDENTITY_FILE=/etc/tobogganing/ziti-identity.json

# Optional: controller CA certificate
HUB_ROUTER_OPENZITI_CONTROLLER_CA_CERT=/etc/tobogganing/ziti-controller-ca.pem
```

### Native Client Configuration

Enable OpenZiti on native clients:

```yaml
# ~/.tobogganing/config.yaml
overlay_type: "openziti"  # or "wireguard" (default)
openziti:
  controller_url: "https://ziti-controller.example.com:6262"
  # Identity file (enrolled by admin)
  identity_file: "~/.tobogganing/ziti-client-identity.json"
  # Auto-enroll if identity missing
  auto_enroll: true
```

### Policy Rules with OpenZiti Scope

Policy rules now support `openziti` scope:

```python
# Create policy with OpenZiti scope
{
    "name": "microservice-access",
    "scope": "openziti",  # Use OpenZiti overlay
    "protocol": "tcp",
    "action": "allow",
    "source_services": ["frontend-api"],
    "dest_services": ["backend-api"],
    "tenant_id": "tenant-uuid",
    "priority": 100
}
```

Scope values:
- `wireguard`: Use WireGuard overlay (default)
- `openziti`: Use OpenZiti overlay
- `k8s`: Use Kubernetes network policies
- `both`: Use both WireGuard and K8s network policies

### Helm Configuration

Configure OpenZiti in Kubernetes:

```yaml
# deploy/kubernetes/values.yaml
openziti:
  enabled: true
  # Include OpenZiti as sub-chart (optional)
  subchart:
    enabled: false  # Use external OpenZiti controller
    # Or deploy OpenZiti in-cluster:
    # enabled: true
    # image: ghcr.io/openziti/controller:latest
    # replicas: 2

hub-router:
  overlay:
    type: "openziti"
    openziti:
      controllerUrl: "http://ziti-controller:6262"
      identityFile: "/var/secrets/ziti/hub-router-identity.json"
      controllerCaCert: "/var/secrets/ziti/controller-ca.pem"
  # Mount OpenZiti identity secret
  volumeMounts:
    - name: ziti-identity
      mountPath: /var/secrets/ziti
      readOnly: true
  volumes:
    - name: ziti-identity
      secret:
        secretName: ziti-hub-router-identity
```

## Identity Enrollment

### Hub-Router Identity

Hub-router needs an enrolled identity in the OpenZiti controller:

```bash
# 1. Generate enrollment token on OpenZiti controller
ziti edge create identity device hub-router-prod \
  --role-attributes "tobogganing,hub-router"

# 2. Create JWT enrollment token
ziti edge create enrollment-token device hub-router-prod \
  --output-file hub-router-enrollment.jwt

# 3. Enroll identity using JWT
ziti-cli enroll \
  -e hub-router-enrollment.jwt \
  -o hub-router-identity.json \
  -k https://ziti-controller.example.com:6262

# 4. Store identity in Kubernetes secret
kubectl create secret generic ziti-hub-router-identity \
  --from-file=hub-router-identity.json \
  -n tobogganing
```

### Client Identity

Clients are enrolled with their identity:

```bash
# Generate enrollment token for client
ziti edge create identity device client-001 \
  --role-attributes "tobogganing,client"

ziti edge create enrollment-token device client-001 \
  --output-file client-enrollment.jwt

# Client uses token to auto-enroll
tobogganing-client openziti enroll \
  --token client-enrollment.jwt
```

## Multi-Overlay Routing

Run both WireGuard and OpenZiti simultaneously via OverlayManager:

```yaml
# Router policy based on scope
overlay_manager:
  enabled: true
  providers:
    - type: "wireguard"
      enabled: true
      config: {...}
    - type: "openziti"
      enabled: true
      config: {...}

  # Route by policy scope
  routing:
    wireguard:
      policies:
        - scope: "wireguard"
        - scope: "both"
    openziti:
      policies:
        - scope: "openziti"
        - scope: "both"
```

Packet routing logic:

```go
func (om *OverlayManager) RoutePacket(pkt *Packet, scope string) error {
    switch scope {
    case "wireguard":
        return om.wireguardProvider.HandlePacket(pkt)
    case "openziti":
        return om.openzitiProvider.HandlePacket(pkt)
    case "both":
        // Route to both overlays
        om.wireguardProvider.HandlePacket(pkt)
        return om.openzitiProvider.HandlePacket(pkt)
    default:
        return fmt.Errorf("unknown scope: %s", scope)
    }
}
```

## Policy Enforcement

### Service-to-Service Policies

Define fine-grained service access policies:

```python
# API endpoint: POST /api/v1/policies/service
{
    "name": "frontend-to-backend",
    "scope": "openziti",
    "protocol": "tcp",
    "action": "allow",
    "source_identity": "frontend-service",
    "dest_service": "backend-api:8080",
    "dest_port": "8080",
    "tenant_id": "tenant-123"
}
```

### Service Definitions

Services represent applications or groups of services:

```bash
# Define backend-api service
ziti edge create service backend-api \
  --role-attributes "tobogganing,backend"

# Add service policy
ziti edge create service-policy backend-access \
  --service-roles "@backend-api" \
  --identity-roles "@tobogganing" \
  --policy-type "Bind"
```

## Metrics & Monitoring

### Prometheus Metrics

OpenZiti provider exports metrics:

```prometheus
# Sessions established
tobogganing_openziti_sessions_total{
  client="client-001",
  service="backend-api"
} 5

# Active sessions
tobogganing_openziti_sessions_active{
  service="backend-api"
} 3

# Session duration (seconds)
tobogganing_openziti_session_duration_seconds{
  quantile="0.95",
  service="backend-api"
} 3600

# Packets routed
tobogganing_openziti_packets_total{
  direction="ingress",
  service="backend-api"
} 50000

# Bytes transferred
tobogganing_openziti_bytes_total{
  direction="egress",
  service="backend-api"
} 1048576
```

## Troubleshooting

### OpenZiti Provider Not Available

**Symptom**: `unknown overlay type: openziti`

**Fix**: Build with OpenZiti support:
```bash
go build -tags openziti ./cmd/hub-router
```

### Identity Enrollment Failed

**Symptom**: Hub-router fails to connect to OpenZiti controller

**Check**:
1. Verify controller URL: `curl https://ziti-controller.example.com:6262/health`
2. Check identity file exists: `cat /etc/tobogganing/ziti-identity.json`
3. Verify controller CA cert if required
4. Check hub-router logs for enrollment errors

**Fix**:
```bash
# Re-enroll identity
ziti-cli enroll \
  -e hub-router-enrollment.jwt \
  -o /etc/tobogganing/ziti-identity.json
```

### Services Not Reachable

**Symptom**: Packets routed via OpenZiti but fail to reach destination

**Check**:
1. Verify service exists in controller: `ziti edge list services`
2. Verify policy allows access: `ziti edge list service-policies`
3. Check client identity has correct role attributes
4. Monitor hub-router logs for routing errors

**Fix**:
```bash
# Create service if missing
ziti edge create service backend-api

# Add service policy
ziti edge create service-policy backend-access \
  --service-roles "@backend-api" \
  --identity-roles "@client" \
  --policy-type "Dial"
```

### High Latency on OpenZiti

**Symptom**: OpenZiti packets have higher latency than WireGuard

**Note**: OpenZiti adds application-level crypto, expected ~5-10ms overhead

**Optimize**:
```bash
# Monitor OpenZiti session performance
ziti edge list sessions

# Consider hybrid approach: Use WireGuard for high-speed,
# OpenZiti for application-embedded access
```

## Migration from WireGuard

To migrate services to OpenZiti overlay:

1. **Deploy OpenZiti** controller and infrastructure
2. **Enable OpenZiti** build tag in hub-router and clients
3. **Create OpenZiti policies** mirroring WireGuard policies
4. **Enroll identities** for hub-router and clients
5. **Test OpenZiti routing** with canary policies
6. **Gradually migrate** policies by changing scope from `wireguard` to `openziti`
7. **Monitor metrics** during migration
8. **Keep WireGuard enabled** as fallback during transition

Example migration policy:

```python
# Start with dual scope
{
    "name": "backend-access-hybrid",
    "scope": "both",  # Route via both overlays
    "source": "frontend",
    "dest": "backend-api",
    "action": "allow"
}

# Later, migrate to OpenZiti-only
{
    "name": "backend-access-openziti",
    "scope": "openziti",  # OpenZiti only
    "source": "frontend",
    "dest": "backend-api",
    "action": "allow"
}
```

## Related Documentation

- [Unified Networking Architecture](./ARCHITECTURE.md#unified-networking)
- [Policy Engine & Rules](./ARCHITECTURE.md#policy-rules)
- [Overlay Provider Interface](./ARCHITECTURE.md#overlay-provider)
- [OpenZiti Official Docs](https://docs.openziti.io/)

