# Testing Standards

## ⚠️ CRITICAL RULES

1. **Run smoke tests before commit** - build, run, API health, page loads
2. **Mock data required** - 3-4 items per feature for realistic testing
3. **All tests must pass** before marking tasks complete
4. **Cross-architecture testing** - test on alternate arch (amd64/arm64) before final commit

---

## Beta Testing Infrastructure

### Docker Registry

**Beta registry**: `registry-dal2.penguintech.io`

Push beta images here for testing in the beta Kubernetes cluster:
```bash
docker tag myapp:latest registry-dal2.penguintech.io/myapp:beta-<epoch64>
docker push registry-dal2.penguintech.io/myapp:beta-<epoch64>
```

### Beta Domains

**Pattern**: `{repo_name}.penguintech.io`

All beta products are deployed behind Cloudflare at this domain pattern.

Example: `project-template` repo → `https://project-template.penguintech.io`

### Beta Smoke Tests (Bypassing Cloudflare)

For beta smoke tests, bypass Cloudflare's antibot/WAF by hitting the origin load balancer directly:

**Origin LB**: `dal2.penguintech.io`

Use the `Host` header to route to the correct service:

```bash
# Bypass Cloudflare for beta smoke tests
curl -H "Host: project-template.penguintech.io" https://dal2.penguintech.io/api/v1/health

# Example with full request
curl -X GET \
  -H "Host: {repo_name}.penguintech.io" \
  -H "Content-Type: application/json" \
  https://dal2.penguintech.io/api/v1/health
```

**Why bypass Cloudflare?**
- Avoids antibot detection during automated tests
- Bypasses WAF rules that may block test traffic
- Direct access for CI/CD pipeline smoke tests
- Faster response times for health checks

---

## Test Types

| Type | Purpose | When to Run |
|------|---------|-------------|
| **Smoke** | Build, run, health checks | Every commit |
| **Unit** | Individual functions | Every commit |
| **Integration** | Component interactions | Before PR |
| **E2E** | Full user workflows | Before release |
| **Performance** | Load/stress testing | Before release |

---

## Mock Data

Seed 3-4 realistic items per feature:
```bash
make seed-mock-data
```

---

## Running Tests

```bash
make smoke-test        # Quick verification
make test-unit         # Unit tests
make test-integration  # Integration tests
make test-e2e          # End-to-end tests
make test              # All tests
```

---

## Kubernetes Testing

### Kubectl Context Naming

**CRITICAL**: Use postfixes to identify environments:
- `{repo}-alpha` - Local K8s (minikube/docker/podman)
- `{repo}-beta` - Beta cluster (registry-dal2)
- `{repo}-prod` - Production cluster

```bash
# Check current context
kubectl config current-context

# Switch context
kubectl config use-context {repo}-alpha
kubectl config use-context {repo}-beta
```

### Alpha Testing (Local K8s)

Alpha uses local Kubernetes. If not available, install one of:

| Option | Platform | Install Command |
|--------|----------|-----------------|
| **MicroK8s** (recommended) | Ubuntu/Debian | `sudo snap install microk8s --classic` |
| **Minikube** | Cross-platform | Download `.deb` from minikube releases |
| **Docker Desktop** | Mac/Windows | Enable K8s in settings |
| **Podman Desktop** | Cross-platform | Enable K8s in settings |

```bash
# MicroK8s setup (recommended for Ubuntu/Debian)
sudo snap install microk8s --classic
microk8s status --wait-ready
microk8s enable dns ingress storage
alias kubectl='microk8s kubectl'

# Deploy to alpha
helm upgrade --install {svc} ./k8s/helm/{service} \
  --namespace {repo} --create-namespace \
  --values ./k8s/helm/{service}/values-dev.yaml
```

### Beta Cluster Deployment

Beta uses separate remote cluster from production.

```bash
# Switch to beta context
kubectl config use-context {repo}-beta

# Tag and push to beta registry
docker tag {image}:latest registry-dal2.penguintech.io/{repo}/{image}:beta-$(date +%s)
docker push registry-dal2.penguintech.io/{repo}/{image}:beta-*

# Deploy
helm upgrade --install {svc} ./k8s/helm/{service} \
  --namespace {repo} --create-namespace \
  --values ./k8s/helm/{service}/values-dev.yaml
```

### Validate & Verify

```bash
# Validate before deploy
helm lint ./k8s/helm/{service}
kubectl apply --dry-run=client -k k8s/kustomize/overlays/{env}

# Verify after deploy
kubectl get pods -n {namespace}
kubectl logs -n {namespace} -l app={service} --tail=50
kubectl rollout status deployment/{service} -n {namespace}
```
