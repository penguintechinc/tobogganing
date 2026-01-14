# Kubernetes Deployment Standards

Part of [Development Standards](../STANDARDS.md)

## Kubernetes Deployment Structure

**CRITICAL: All Kubernetes deployments MUST be in the `{PROJECT_ROOT}/k8s/` directory**

This standardized location ensures everyone knows where to find deployment manifests and configurations.

### Standard Directory Structure

```
k8s/
├── helm/                           # Helm v3 charts
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── values-dev.yaml            # Development overrides
│   ├── values-staging.yaml        # Staging overrides
│   ├── values-prod.yaml           # Production overrides
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       ├── configmap.yaml
│       ├── secret.yaml
│       └── _helpers.tpl
├── kustomize/                     # Kustomize manifests
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── namespace.yaml
│   ├── overlays/
│   │   ├── dev/
│   │   │   ├── kustomization.yaml
│   │   │   └── patches/
│   │   ├── staging/
│   │   │   ├── kustomization.yaml
│   │   │   └── patches/
│   │   └── prod/
│   │       ├── kustomization.yaml
│   │       └── patches/
│   └── components/              # Reusable components
└── manifests/                    # Raw kubectl manifests (optional)
    ├── namespace.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml
```

## Deployment Methods

Projects MUST support BOTH Helm and Kustomize deployment methods:

### Method 1: Helm v3 (Preferred)

**Why Helm**: Package management, versioning, rollback capabilities, templating

**Installation**:
```bash
# Deploy to development
helm install myapp ./k8s/helm \
  --namespace myapp-dev \
  --create-namespace \
  --values ./k8s/helm/values-dev.yaml

# Deploy to staging
helm install myapp ./k8s/helm \
  --namespace myapp-staging \
  --create-namespace \
  --values ./k8s/helm/values-staging.yaml

# Deploy to production
helm install myapp ./k8s/helm \
  --namespace myapp-prod \
  --create-namespace \
  --values ./k8s/helm/values-prod.yaml
```

**Upgrade**:
```bash
helm upgrade myapp ./k8s/helm \
  --namespace myapp-prod \
  --values ./k8s/helm/values-prod.yaml
```

**Rollback**:
```bash
helm rollback myapp 1 --namespace myapp-prod
```

### Method 2: Kustomize

**Why Kustomize**: Built into kubectl, declarative, no templating, patch-based

**Installation**:
```bash
# Deploy to development
kubectl apply -k k8s/kustomize/overlays/dev

# Deploy to staging
kubectl apply -k k8s/kustomize/overlays/staging

# Deploy to production
kubectl apply -k k8s/kustomize/overlays/prod
```

**Delete**:
```bash
kubectl delete -k k8s/kustomize/overlays/dev
```

### Method 3: Raw Manifests (kubectl)

**Why Raw Manifests**: Simple, explicit, no abstractions

**Installation**:
```bash
kubectl apply -f k8s/manifests/ --namespace myapp
```

## Helm Chart Standards

### Chart.yaml

```yaml
apiVersion: v2
name: myapp
description: My Application Helm Chart
type: application
version: 1.0.0  # Chart version
appVersion: "1.0.0"  # Application version
keywords:
  - myapp
  - flask
  - react
maintainers:
  - name: Penguin Tech Inc
    email: support@penguintech.io
```

### values.yaml

```yaml
# Global settings
replicaCount: 2

image:
  repository: ghcr.io/penguintechinc/myapp
  pullPolicy: IfNotPresent
  tag: "latest"

imagePullSecrets: []
nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  annotations: {}
  name: ""

podAnnotations: {}
podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000

securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  readOnlyRootFilesystem: false

service:
  type: ClusterIP
  port: 80
  targetPort: 5000

ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
  hosts:
    - host: myapp.penguintech.io
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: myapp-tls
      hosts:
        - myapp.penguintech.io

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
  targetMemoryUtilizationPercentage: 80

nodeSelector: {}
tolerations: []
affinity: {}

# Application-specific configuration
app:
  env: production
  debug: false
  logLevel: info

database:
  type: postgresql
  host: postgres.default.svc.cluster.local
  port: 5432
  name: myapp
  # Secrets should be in external secret store
  existingSecret: myapp-db-secret

redis:
  enabled: true
  host: redis.default.svc.cluster.local
  port: 6379
```

### Environment-Specific Values

**values-dev.yaml**:
```yaml
replicaCount: 1

image:
  tag: "beta-1234567890"

ingress:
  hosts:
    - host: myapp.penguintech.io

resources:
  limits:
    cpu: 200m
    memory: 256Mi
  requests:
    cpu: 100m
    memory: 128Mi

autoscaling:
  enabled: false

app:
  env: development
  debug: true
  logLevel: debug
```

**values-prod.yaml**:
```yaml
replicaCount: 3

image:
  tag: "v1.0.0"

ingress:
  hosts:
    - host: myapp.penguincloud.io

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20

app:
  env: production
  debug: false
  logLevel: warning
```

## Kustomize Standards

### base/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: myapp

resources:
  - namespace.yaml
  - deployment.yaml
  - service.yaml
  - configmap.yaml

commonLabels:
  app: myapp
  managed-by: kustomize

images:
  - name: myapp
    newName: ghcr.io/penguintechinc/myapp
    newTag: latest
```

### overlays/dev/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: myapp-dev

bases:
  - ../../base

namePrefix: dev-

replicas:
  - name: myapp
    count: 1

images:
  - name: myapp
    newTag: beta-1234567890

patchesStrategicMerge:
  - patches/deployment-patch.yaml

configMapGenerator:
  - name: myapp-config
    literals:
      - ENV=development
      - DEBUG=true
      - LOG_LEVEL=debug
```

### overlays/prod/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: myapp-prod

bases:
  - ../../base

namePrefix: prod-

replicas:
  - name: myapp
    count: 3

images:
  - name: myapp
    newTag: v1.0.0

patchesStrategicMerge:
  - patches/deployment-patch.yaml
  - patches/ingress-patch.yaml

configMapGenerator:
  - name: myapp-config
    literals:
      - ENV=production
      - DEBUG=false
      - LOG_LEVEL=warning
```

## Kubernetes Best Practices

### Resource Limits

**ALWAYS set resource requests and limits**:

```yaml
resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi
```

### Health Checks

**ALWAYS define liveness and readiness probes**:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 5000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /healthz
    port: 5000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

### Security

**Run as non-root user**:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

### Secrets Management

**Use external secret stores (Sealed Secrets, External Secrets Operator)**:

```yaml
# NEVER commit secrets to git
# Use external secret management
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: myapp-secrets
spec:
  secretStoreRef:
    name: vault
    kind: SecretStore
  target:
    name: myapp-secrets
  data:
    - secretKey: DB_PASSWORD
      remoteRef:
        key: myapp/database
        property: password
```

### Namespaces

**Use namespaces for environment isolation**:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: myapp-dev
  labels:
    environment: development
    app: myapp
---
apiVersion: v1
kind: Namespace
metadata:
  name: myapp-staging
  labels:
    environment: staging
    app: myapp
---
apiVersion: v1
kind: Namespace
metadata:
  name: myapp-prod
  labels:
    environment: production
    app: myapp
```

### Labels and Annotations

**Use consistent labeling**:

```yaml
metadata:
  labels:
    app: myapp
    component: backend
    environment: production
    version: v1.0.0
    managed-by: helm
  annotations:
    description: "Flask backend service"
    docs: "https://docs.penguintech.io/myapp"
```

## Deployment Validation

### Pre-Deployment Checks

```bash
# Validate Helm chart
helm lint ./k8s/helm

# Dry-run deployment
helm install myapp ./k8s/helm --dry-run --debug

# Template output
helm template myapp ./k8s/helm --values ./k8s/helm/values-prod.yaml

# Validate Kustomize
kubectl kustomize k8s/kustomize/overlays/prod

# Dry-run Kustomize
kubectl apply -k k8s/kustomize/overlays/prod --dry-run=client
```

### Post-Deployment Validation

```bash
# Check pods
kubectl get pods -n myapp-prod

# Check services
kubectl get svc -n myapp-prod

# Check ingress
kubectl get ingress -n myapp-prod

# Check logs
kubectl logs -n myapp-prod -l app=myapp --tail=100

# Describe deployment
kubectl describe deployment myapp -n myapp-prod
```

## CI/CD Integration

### GitHub Actions Deployment

```yaml
# .github/workflows/deploy.yml
name: Deploy to Kubernetes

on:
  push:
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Helm
        uses: azure/setup-helm@v3
        with:
          version: '3.12.0'

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBE_CONFIG }}

      - name: Deploy with Helm
        run: |
          helm upgrade --install myapp ./k8s/helm \
            --namespace myapp-prod \
            --create-namespace \
            --values ./k8s/helm/values-prod.yaml \
            --set image.tag=${{ github.ref_name }}
```

## Makefile Targets

**Add K8s deployment targets to Makefile**:

```makefile
# Kubernetes deployment targets
.PHONY: k8s-deploy-dev k8s-deploy-staging k8s-deploy-prod

k8s-deploy-dev:
	helm upgrade --install myapp ./k8s/helm \
		--namespace myapp-dev \
		--create-namespace \
		--values ./k8s/helm/values-dev.yaml

k8s-deploy-staging:
	helm upgrade --install myapp ./k8s/helm \
		--namespace myapp-staging \
		--create-namespace \
		--values ./k8s/helm/values-staging.yaml

k8s-deploy-prod:
	helm upgrade --install myapp ./k8s/helm \
		--namespace myapp-prod \
		--create-namespace \
		--values ./k8s/helm/values-prod.yaml

k8s-validate:
	helm lint ./k8s/helm
	kubectl kustomize k8s/kustomize/overlays/prod

k8s-delete-dev:
	helm uninstall myapp --namespace myapp-dev
```

## Key Principles

1. **Standardized Location**: All K8s files in `{PROJECT_ROOT}/k8s/` directory
2. **Dual Support**: Provide both Helm and Kustomize deployment options
3. **Environment Separation**: Use namespaces and value files per environment
4. **Resource Limits**: Always set requests and limits
5. **Health Checks**: Always define liveness and readiness probes
6. **Security**: Run as non-root, drop capabilities, use secret stores
7. **Validation**: Lint and dry-run before deployment
8. **Documentation**: Document deployment process in README

📚 **Related Standards**: [Architecture](ARCHITECTURE.md) | [Testing Phase 3](TESTING.md#phase-3-deployment--live-testing-k8s)
