# Kubernetes Deployment Standards

## Critical Rules

1. **Support BOTH methods** - Every project needs Helm v3 AND Kustomize
2. **Helm v3** = Packaged deployments (CI/CD, versioned releases)
3. **Kustomize** = Prescriptive deployments (GitOps, ArgoCD/Flux)
4. **Never hardcode secrets** - Use Vault, Sealed Secrets, or External Secrets Operator
5. **Always set resource limits** - CPU and memory requests/limits mandatory
6. **Always add health checks** - Liveness and readiness probes required

## Directory Structure

```
k8s/
├── helm/{service}/           # Helm v3 charts
│   ├── Chart.yaml
│   ├── values.yaml           # Default values
│   ├── values-{env}.yaml     # Environment overrides
│   └── templates/
├── kustomize/
│   ├── base/                 # Base manifests
│   └── overlays/{env}/       # Environment patches
└── manifests/                # Raw YAML (reference)
```

## Helm v3 Commands

```bash
helm lint ./k8s/helm/{service}                    # Validate
helm template {svc} ./k8s/helm/{service}          # Preview YAML
helm install {svc} ./k8s/helm/{service} \
  --namespace {ns} --create-namespace \
  --values ./k8s/helm/{service}/values-{env}.yaml  # Install
helm upgrade {svc} ./k8s/helm/{service} ...       # Update
helm rollback {svc} 1 --namespace {ns}            # Rollback
```

## Kustomize Commands

```bash
kubectl kustomize k8s/kustomize/overlays/{env}    # Preview
kubectl apply -k k8s/kustomize/overlays/{env}     # Deploy
kubectl delete -k k8s/kustomize/overlays/{env}    # Remove
```

## Required in All Deployments

```yaml
resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

livenessProbe:
  httpGet:
    path: /healthz
    port: 5000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /healthz
    port: 5000
  initialDelaySeconds: 5
  periodSeconds: 5

securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
```

## Kubectl Context Naming

**CRITICAL**: Always use context postfixes to identify environment:
- `{repo}-alpha` - Local K8s (dev machine)
- `{repo}-beta` - Beta/staging cluster
- `{repo}-prod` - Production cluster

```bash
kubectl config use-context {repo}-alpha   # Local testing
kubectl config use-context {repo}-beta    # Beta cluster
```

## Environments

| Env | Cluster | Replicas | CPU | Memory | Autoscaling |
|-----|---------|----------|-----|--------|-------------|
| alpha | Local K8s | 1 | 100m/250m | 128Mi/256Mi | Off |
| beta | Remote | 2 | 250m/500m | 256Mi/512Mi | Off |
| prod | Remote | 3+ | 500m/1000m | 512Mi/1Gi | On |

**Alpha** = Local K8s - MicroK8s (recommended), minikube, Docker/Podman Desktop
**Beta** = Remote cluster at `registry-dal2.penguintech.io`, domain `{repo}.penguintech.io`
**Prod** = Separate production cluster

**Local K8s install (Ubuntu/Debian)**: `sudo snap install microk8s --classic`

**Note**: Always target K8s for testing - docker compose causes compatibility issues.

## Related

- `docs/standards/KUBERNETES.md` - Human-readable guide
- `.claude/containers.md` - Container image standards
- `.claude/testing.md` - Beta infrastructure
