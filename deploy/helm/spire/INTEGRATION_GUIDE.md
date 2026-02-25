# SPIRE Integration Guide for Tobogganing

This guide explains how to integrate SPIRE workload identity with Tobogganing services (hub-api, hub-router, hub-webui).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Kubernetes Cluster                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              SPIRE System (spire-system)              │   │
│  │                                                        │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │  SPIRE Server (StatefulSet)                  │    │   │
│  │  │  - Trust domain: primary.tobogganing.io      │    │   │
│  │  │  - Manages SVIDs and policies                │    │   │
│  │  │  - Listens on :8081 (gRPC)                   │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  │                       ↓                                 │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │  SPIRE Agent (DaemonSet - every node)        │    │   │
│  │  │  - Socket: /run/spire/sockets/agent.sock     │    │   │
│  │  │  - Attests workloads locally                 │    │   │
│  │  │  - Distributes SVIDs                         │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Application Services                        │   │
│  │                                                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │   │
│  │  │ hub-api  │  │hub-router│  │ hub-webui│           │   │
│  │  │(Flask)   │  │  (Go)    │  │ (React)  │           │   │
│  │  │          │  │          │  │          │           │   │
│  │  │Fetch SVID│  │Fetch SVID│  │Auth via  │           │   │
│  │  │from agent│  │from agent│  │hub-api   │           │   │
│  │  │socket    │  │socket    │  │          │           │   │
│  │  └──────────┘  └──────────┘  └──────────┘           │   │
│  │       ↑               ↑              ↑                │   │
│  │       └───────────────┴──────────────┘                │   │
│  │       mTLS with SVID certificates                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Phase 1: Deploy SPIRE

### 1.1 Install SPIRE
```bash
# Deploy SPIRE with default configuration
helm install spire ./deploy/helm/spire \
  -n spire-system \
  --create-namespace \
  --set spire.enabled=true

# For bare-metal environments
helm install spire ./deploy/helm/spire \
  -n spire-system \
  --create-namespace \
  -f values-baremetal.yaml

# For federated multi-cluster
helm install spire ./deploy/helm/spire \
  -n spire-system \
  --create-namespace \
  -f values-federated.yaml
```

### 1.2 Verify SPIRE Deployment
```bash
# Check server
kubectl get statefulset -n spire-system tobogganing-spire-server
kubectl logs -n spire-system -l component=server

# Check agents
kubectl get daemonset -n spire-system tobogganing-spire-agent
kubectl logs -n spire-system -l component=agent

# Verify bundle ConfigMap
kubectl get configmap -n spire-system spire-bundle -o yaml
```

## Phase 2: Create Registration Entries

### 2.1 Register hub-api
```bash
# Get SPIRE server pod
SPIRE_SERVER_POD=$(kubectl get pod -n spire-system \
  -l component=server -o jsonpath='{.items[0].metadata.name}')

# Register hub-api service
kubectl exec -n spire-system $SPIRE_SERVER_POD -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID "spiffe://default.tobogganing.io/hub/api" \
  -parentID "spiffe://default.tobogganing.io/k8s/sat" \
  -selector k8s:ns:default \
  -selector k8s:sa:hub-api

# Register hub-api with different namespace
kubectl exec -n spire-system $SPIRE_SERVER_POD -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID "spiffe://default.tobogganing.io/hub/api" \
  -parentID "spiffe://default.tobogganing.io/k8s/sat" \
  -selector k8s:ns:production \
  -selector k8s:sa:hub-api
```

### 2.2 Register hub-router
```bash
# Register hub-router service
kubectl exec -n spire-system $SPIRE_SERVER_POD -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID "spiffe://default.tobogganing.io/hub/router" \
  -parentID "spiffe://default.tobogganing.io/k8s/sat" \
  -selector k8s:ns:default \
  -selector k8s:sa:hub-router
```

### 2.3 List Registration Entries
```bash
kubectl exec -n spire-system $SPIRE_SERVER_POD -- \
  /opt/spire/bin/spire-server entry list
```

## Phase 3: Update hub-api (Python/Flask)

### 3.1 Install spire-agent Client Library
```bash
pip install pyspiffe
```

### 3.2 Fetch X.509 SVID in hub-api
```python
# services/hub-api/auth/svid_manager.py
from pyspiffe import WorkloadApiClient
import ssl
from pathlib import Path

class SVIDManager:
    def __init__(self, socket_path="/run/spire/sockets/agent.sock"):
        self.socket_path = socket_path
        self.client = WorkloadApiClient(socket_path=socket_path)

    def get_x509_svid(self):
        """Fetch X.509 SVID from SPIRE agent"""
        return self.client.fetch_x509_svid()

    def get_tls_context(self):
        """Create SSL context with SVID certificate"""
        svid = self.get_x509_svid()

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        # Write certificate to temp file
        cert_path = Path("/tmp/hub-api-svid.pem")
        key_path = Path("/tmp/hub-api-key.pem")

        cert_path.write_text(svid.cert_pem)
        key_path.write_text(svid.private_key_pem)

        context.load_cert_chain(str(cert_path), str(key_path))
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True

        # Load bundle for peer verification
        bundle_path = Path("/run/spire/bundle/ca_bundle.crt")
        if bundle_path.exists():
            context.load_verify_locations(str(bundle_path))

        return context, svid

# services/hub-api/app.py
from auth.svid_manager import SVIDManager

svid_manager = SVIDManager()

@action('secure_endpoint')
def secure_endpoint():
    """Endpoint protected by SVID"""
    context, svid = svid_manager.get_tls_context()
    return {"status": "success", "svid_id": svid.spiffe_id}
```

### 3.3 Update API Client for mTLS
```python
# services/hub-api/client/router_client.py
import requests
from auth.svid_manager import SVIDManager

class RouterClient:
    def __init__(self, router_url="https://hub-router:8443"):
        self.router_url = router_url
        self.svid_manager = SVIDManager()
        self.session = requests.Session()

    def _setup_mtls(self):
        """Setup mTLS for hub-router communication"""
        context, svid = self.svid_manager.get_tls_context()
        adapter = requests.adapters.HTTPAdapter(ssl_context=context)
        self.session.mount('https://', adapter)
        return self.session

    def create_policy(self, policy_data):
        """Create policy with mTLS"""
        session = self._setup_mtls()
        response = session.post(
            f"{self.router_url}/api/policies",
            json=policy_data,
            verify="/run/spire/bundle/ca_bundle.crt"
        )
        return response.json()
```

## Phase 4: Update hub-router (Go)

### 4.1 Import SPIRE Go Library
```go
// services/hub-router/go.mod
require (
    github.com/spiffe/go-spiffe/v2 v2.1.7
)
```

### 4.2 Fetch X.509 SVID in hub-router
```go
// services/hub-router/internal/auth/svid.go
package auth

import (
    "context"
    "log"

    "github.com/spiffe/go-spiffe/v2/workloadapi"
)

type SVIDManager struct {
    socketPath string
    source     *workloadapi.X509Source
}

func NewSVIDManager(socketPath string) (*SVIDManager, error) {
    ctx := context.Background()
    source, err := workloadapi.NewX509Source(
        ctx,
        workloadapi.WithSocketPath(socketPath),
    )
    if err != nil {
        log.Fatalf("Unable to create X509Source: %v", err)
        return nil, err
    }

    return &SVIDManager{
        socketPath: socketPath,
        source:     source,
    }, nil
}

func (s *SVIDManager) GetX509SVID(ctx context.Context) (*workloadapi.X509SVID, error) {
    return s.source.GetX509SVID(ctx)
}

func (s *SVIDManager) GetTLSConfig(ctx context.Context) (*tls.Config, error) {
    return s.source.GetX509SVIDConfig(ctx)
}

func (s *SVIDManager) Close() error {
    return s.source.Close()
}
```

### 4.3 Update Proxy Middleware for mTLS
```go
// services/hub-router/proxy/middleware/auth.go
package middleware

import (
    "net/http"
    "context"

    "tobogganing/internal/auth"
)

var svidManager *auth.SVIDManager

func init() {
    var err error
    svidManager, err = auth.NewSVIDManager("/run/spire/sockets/agent.sock")
    if err != nil {
        log.Fatalf("Failed to initialize SPIRE SVID manager: %v", err)
    }
}

func AuthMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        ctx := r.Context()

        // Get SVID from context
        svid, err := svidManager.GetX509SVID(ctx)
        if err != nil {
            http.Error(w, "Failed to get SVID", http.StatusUnauthorized)
            return
        }

        // Store SVID in request context
        ctx = context.WithValue(ctx, "svid", svid)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}
```

### 4.4 Setup mTLS Server
```go
// services/hub-router/proxy/main.go
package main

import (
    "log"
    "net/http"
    "context"

    "github.com/spiffe/go-spiffe/v2/workloadapi"
)

func main() {
    ctx := context.Background()

    // Create X509 source
    source, err := workloadapi.NewX509Source(
        ctx,
        workloadapi.WithSocketPath("/run/spire/sockets/agent.sock"),
    )
    if err != nil {
        log.Fatalf("Unable to create X509Source: %v", err)
    }
    defer source.Close()

    // Get TLS config
    tlsConfig := source.GetX509SVIDConfig(ctx)

    // Create server with mTLS
    server := &http.Server{
        Addr:      ":8443",
        TLSConfig: tlsConfig,
        Handler:   setupRoutes(),
    }

    // Start HTTPS server
    log.Printf("Starting mTLS server on %s", server.Addr)
    log.Fatal(server.ListenAndServeTLS("", ""))
}

func setupRoutes() http.Handler {
    mux := http.NewServeMux()

    // Add routes
    mux.HandleFunc("/health", healthHandler)
    mux.HandleFunc("/api/policies", policiesHandler)

    return mux
}
```

## Phase 5: Validate Integration

### 5.1 Test SVID Fetching
```bash
# Exec into hub-api pod
kubectl exec -it deployment/hub-api -- bash

# Test SPIRE agent connection
/opt/spire/bin/spire-agent api fetch x509 \
  -socketPath /run/spire/sockets/agent.sock \
  -print

# Should show certificate with SPIFFE ID
```

### 5.2 Test mTLS Communication
```bash
# Get hub-router service
kubectl port-forward svc/hub-router 8443:8443 &

# Test from another pod
kubectl run test-client --image=alpine:latest -it -- sh
apk add curl
curl -v https://hub-router:8443/health \
  --cacert /run/spire/bundle/ca_bundle.crt
```

### 5.3 Monitor SPIRE Logs
```bash
# Watch server logs
kubectl logs -n spire-system -l component=server -f

# Watch agent logs
kubectl logs -n spire-system -l component=agent -f

# Check for SVID issuance
grep "SVID" <(kubectl logs -n spire-system -l component=server -f)
```

## Phase 6: Multi-Cluster Federation (Optional)

### 6.1 Setup Secondary Cluster
On secondary cluster:
```bash
helm install spire ./deploy/helm/spire \
  -n spire-system \
  --create-namespace \
  --set spire.enabled=true \
  --set "spire.trustDomain=secondary.tobogganing.io"
```

### 6.2 Configure Federation
Update primary cluster values:
```yaml
federation:
  enabled: true
  bundleEndpoints:
    - address: "https://secondary-spire.example.com:8443"
      trustDomain: "secondary.tobogganing.io"
```

Apply:
```bash
helm upgrade spire ./deploy/helm/spire \
  -n spire-system \
  -f values-federated.yaml
```

### 6.3 Validate Federation
```bash
# Check bundle from secondary cluster
kubectl get configmap -n spire-system spire-bundle -o yaml | \
  grep -A 50 "secondary.tobogganing.io"
```

## Troubleshooting

### SVIDs Not Being Issued
```bash
# Check SPIRE server logs
kubectl logs -n spire-system -l component=server | grep -i svid

# Verify registration entries
kubectl exec -n spire-system <server-pod> -- \
  /opt/spire/bin/spire-server entry list

# Check workload attestation
kubectl logs -n spire-system -l component=agent | grep -i workload
```

### mTLS Connection Failures
```bash
# Verify bundle is available
kubectl get configmap -n spire-system spire-bundle

# Check certificate expiration
openssl x509 -in <(kubectl get configmap -n spire-system spire-bundle \
  -o jsonpath='{.data.ca_bundle\.crt}') -noout -dates

# Test connectivity
kubectl run -it --rm test -- curl -v https://hub-router:8443/health
```

### Socket Access Issues
```bash
# Verify socket exists
kubectl exec <pod> -- ls -la /run/spire/sockets/

# Check permissions
kubectl exec <pod> -- stat /run/spire/sockets/agent.sock

# Verify agent is running
kubectl get daemonset -n spire-system tobogganing-spire-agent
```

## Security Best Practices

1. **Enable Federation TLS**: Use certificate pinning for bundle endpoints
2. **Audit Logging**: Enable SPIRE server audit logging
3. **RBAC**: Limit access to SPIRE ConfigMaps and Secrets
4. **Network Policy**: Restrict traffic to SPIRE ports
5. **Secret Rotation**: Rotate SVID certificates regularly
6. **Monitoring**: Alert on authentication failures

## References

- SPIRE Python: https://github.com/spiffe/py-spiffe
- SPIRE Go: https://github.com/spiffe/go-spiffe
- SPIFFE Specification: https://github.com/spiffe/spiffe
- Tobogganing: https://github.com/penguintechinc/tobogganing
