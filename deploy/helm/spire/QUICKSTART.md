# SPIRE Helm Chart Quick Start

Get SPIRE workload identity running in 5 minutes.

## Prerequisites

- Kubernetes 1.20+
- Helm 3.0+
- kubectl configured to access your cluster
- Persistent volume provisioner (default storage class)

## Installation Steps

### 1. Deploy SPIRE (2 minutes)

```bash
cd deploy/helm/spire

# Install SPIRE in spire-system namespace
helm install spire . \
  -n spire-system \
  --create-namespace \
  --set spire.enabled=true
```

### 2. Verify Deployment (1 minute)

```bash
# Check server is running
kubectl get statefulset -n spire-system
kubectl get pods -n spire-system -l component=server

# Check agents are running (should have one per node)
kubectl get daemonset -n spire-system
kubectl get pods -n spire-system -l component=agent

# Check bundle ConfigMap was created
kubectl get configmap -n spire-system spire-bundle
```

### 3. Create Service Registration (1 minute)

```bash
# Get SPIRE server pod name
SPIRE_POD=$(kubectl get pod -n spire-system \
  -l component=server -o jsonpath='{.items[0].metadata.name}')

# Register hub-api service
kubectl exec -n spire-system $SPIRE_POD -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID "spiffe://default.tobogganing.io/hub/api" \
  -parentID "spiffe://default.tobogganing.io/k8s/sat" \
  -selector k8s:ns:default \
  -selector k8s:sa:hub-api

# Register hub-router service
kubectl exec -n spire-system $SPIRE_POD -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID "spiffe://default.tobogganing.io/hub/router" \
  -parentID "spiffe://default.tobogganing.io/k8s/sat" \
  -selector k8s:ns:default \
  -selector k8s:sa:hub-router

# List all entries
kubectl exec -n spire-system $SPIRE_POD -- \
  /opt/spire/bin/spire-server entry list
```

### 4. Test SVID Issuance (1 minute)

```bash
# Create a test pod
kubectl run spire-test --image=alpine:latest -it -- sh

# Inside the pod, install curl
apk add curl

# Get X.509 SVID
/opt/spire/bin/spire-agent api fetch x509 \
  -socketPath /run/spire/sockets/agent.sock \
  -print

# You should see:
# Certificate:
#     Data:
#         X.509v3 Subject Alternative Name:
#             URI: spiffe://default.tobogganing.io/...
```

## Deployment Variants

### Bare-Metal Clusters
```bash
helm install spire . \
  -n spire-system \
  --create-namespace \
  -f values-baremetal.yaml
```

### Federated Multi-Cluster
```bash
helm install spire . \
  -n spire-system \
  --create-namespace \
  -f values-federated.yaml
```

## Common Commands

### Check SPIRE Status
```bash
# Server health
kubectl exec -n spire-system <server-pod> -- \
  /opt/spire/bin/spire-server healthcheck \
  -socketPath /tmp/spire-server/private/api.sock

# Agent health
kubectl exec -n spire-system <agent-pod> -- \
  /opt/spire/bin/spire-agent healthcheck \
  -socketPath /run/spire/sockets/agent.sock
```

### View Logs
```bash
# Server logs
kubectl logs -n spire-system -l component=server -f

# Agent logs on specific node
kubectl logs -n spire-system -l component=agent -f -n <node-name>
```

### Manage Service Entries
```bash
# List all entries
kubectl exec -n spire-system $SPIRE_POD -- \
  /opt/spire/bin/spire-server entry list

# Delete an entry
kubectl exec -n spire-system $SPIRE_POD -- \
  /opt/spire/bin/spire-server entry delete -entryID <id>
```

### Update Configuration
```bash
# Edit values and upgrade
helm upgrade spire . \
  -n spire-system \
  -f values-custom.yaml
```

### Uninstall SPIRE
```bash
helm uninstall spire -n spire-system
kubectl delete namespace spire-system
```

## Integration with Services

### For hub-api (Python/Flask)
See INTEGRATION_GUIDE.md Phase 3

```python
from pyspiffe import WorkloadApiClient

client = WorkloadApiClient(
    socket_path="/run/spire/sockets/agent.sock"
)
svid = client.fetch_x509_svid()
```

### For hub-router (Go)
See INTEGRATION_GUIDE.md Phase 4

```go
source, _ := workloadapi.NewX509Source(
    ctx,
    workloadapi.WithSocketPath("/run/spire/sockets/agent.sock"),
)
config := source.GetX509SVIDConfig(ctx)
```

## Troubleshooting

### SPIRE Server Won't Start
```bash
# Check logs
kubectl logs -n spire-system -l component=server

# Common issues:
# - PVC not provisioned: Check storage class exists
# - Port conflicts: Verify port 8081 is available
# - Permission denied: Check data directory ownership
```

### SVIDs Not Being Issued
```bash
# Verify entry exists
kubectl exec -n spire-system $SPIRE_POD -- \
  /opt/spire/bin/spire-server entry list | grep "hub/api"

# Check agent logs
kubectl logs -n spire-system -l component=agent | grep -i "workload\|attestation"

# Verify service account exists
kubectl get sa hub-api
```

### Bundle Not Available
```bash
# Check ConfigMap
kubectl get configmap -n spire-system spire-bundle

# View bundle contents
kubectl get configmap -n spire-system spire-bundle -o yaml | \
  grep "ca_bundle.crt" -A 20
```

## Next Steps

1. Review [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for service integration
2. Customize [values.yaml](values.yaml) for your environment
3. Set up [federation](values-federated.yaml) for multi-cluster
4. Monitor with Prometheus metrics
5. Read [README.md](README.md) for complete documentation

## Quick Reference

| Component | Port | Socket |
|-----------|------|--------|
| SPIRE Server | 8081 | - |
| SPIRE Agent | 8082 | /run/spire/sockets/agent.sock |
| Server Health | 8085 | - |
| Agent Health | 8086 | - |
| Agent Metrics | 9988 | - |

## Resources

- Full documentation: [README.md](README.md)
- Integration guide: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)
- Implementation details: [../SPIRE_IMPLEMENTATION_SUMMARY.md](../SPIRE_IMPLEMENTATION_SUMMARY.md)
- SPIRE docs: https://spiffe.io/spire/docs/
- SPIFFE spec: https://github.com/spiffe/spiffe
