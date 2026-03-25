# ☸️ Kubernetes Guide - Container Orchestration Made Human

Part of [Development Standards](../STANDARDS.md)

## What is K8s, Really?

Think of Kubernetes like a smart manager for your containers. You tell it "I need 3 copies of my app running," and it makes sure exactly 3 are always up. If one crashes? K8s spins up a new one. Need to update your code? K8s rolls it out without breaking anything. That's the magic.

**Key concepts you'll use:**
- **Pods**: Smallest unit (one or more containers)
- **Deployments**: Manage running multiple pod copies with updates
- **Services**: Network access to your pods
- **Ingress**: Route external traffic to your services
- **Namespaces**: Separate environments (dev, staging, prod)

## 🖥️ Environments & Contexts

We use **three separate K8s clusters** — one per environment. Each has its own kubectl context. Always pass `--context` on every command; never change the global context.

| Environment | Cluster | Context | Namespace | Deploy Method |
|-------------|---------|---------|-----------|---------------|
| **Alpha** (local) | MicroK8s on your machine | `local-alpha` | `{product}` | Kustomize |
| **Beta** (shared dev) | Remote dal2 cluster | `dal2-beta` | `{product}` | Helm |
| **Prod** (production) | Per-repo production cluster | `{repo}-prod` | `{product}` | Helm |

**The namespace is always the product name — never append the environment:**

```bash
# ✅ CORRECT
kubectl --context local-alpha get pods -n myapp
kubectl --context dal2-beta get pods -n myapp

# ❌ WRONG — don't append -alpha, -beta, -dev, etc.
kubectl get pods -n myapp-beta   # wrong namespace
kubectl config use-context dal2-beta  # never change global context
```

## 🐧 Local Development with MicroK8s

**MicroK8s is the standard local Kubernetes cluster** for Ubuntu/Debian developers. It includes a built-in image registry at `localhost:32000` so you can push images without any external registry setup.

```bash
# Install
sudo snap install microk8s --classic

# Enable required addons
microk8s enable registry ingress dns

# Set up context alias
microk8s config | kubectl config --kubeconfig ~/.kube/config merge -
```

**Build, push, and deploy locally:**

```bash
# Build and push your image to the local registry
docker build -t localhost:32000/flask-backend:latest ./services/flask-backend
docker push localhost:32000/flask-backend:latest

# Deploy via Kustomize (always pass --context)
kubectl apply --context local-alpha -k k8s/kustomize/overlays/alpha

# Watch pods come up
kubectl --context local-alpha get pods -n myapp --watch
```

> Other options: Docker Desktop K8s (Mac/Windows), Podman Desktop (cross-platform)

## 🚀 Your First Deployment (Step-by-Step)

**1. Set up your K8s files:**

Create the directory structure:
```
k8s/
├── helm/
│   ├── Chart.yaml
│   ├── values.yaml          # Shared defaults
│   ├── values-alpha.yaml    # Local dev overrides
│   ├── values-beta.yaml     # Beta overrides
│   ├── values-prod.yaml     # Production overrides
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml
│       └── ingress.yaml
└── kustomize/
    ├── base/
    │   ├── kustomization.yaml
    │   ├── deployment.yaml
    │   └── service.yaml
    └── overlays/
        ├── alpha/
        ├── beta/
        └── prod/
```

**2. Deploy to alpha (local):**

```bash
# Build and push image first
docker build -t localhost:32000/myapp:latest ./services/myapp
docker push localhost:32000/myapp:latest

# Deploy via Kustomize (namespace = product name, no -alpha suffix)
kubectl apply --context local-alpha -k k8s/kustomize/overlays/alpha

# Check it worked (always pass --context)
kubectl --context local-alpha get pods -n myapp
```

**3. Deploy to beta (uses CI-built images from ghcr.io):**

```bash
# Use the deploy script — it pulls CI images automatically
./scripts/deploy-beta.sh

# Or deploy a specific CI-built tag
./scripts/deploy-beta.sh --tag beta-1710000000
```

**4. Roll back if needed:**

```bash
helm rollback myapp 1 --kube-context dal2-beta --namespace myapp
```

## 📦 Helm Charts Explained Simply

Helm is like npm for Kubernetes. You write a template once, then customize it with different values for different environments.

**Chart.yaml** - Your app's ID card:
```yaml
apiVersion: v2
name: myapp
description: My awesome app
version: 1.0.0
appVersion: "1.0.0"
```

**values.yaml** - Configuration knobs you can twist:
```yaml
replicaCount: 2                    # Run 2 copies
image:
  repository: ghcr.io/penguintechinc/myapp
  tag: "latest"

resources:
  limits:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
```

**values-dev.yaml** - Override for development:
```yaml
replicaCount: 1              # Save resources, run just 1
autoscaling:
  enabled: false
app:
  env: development
  debug: true
```

**values-prod.yaml** - Override for production:
```yaml
replicaCount: 3              # More copies for reliability
autoscaling:
  enabled: true
  maxReplicas: 20
app:
  env: production
  debug: false
```

Templates use these values: `{{ .Values.replicaCount }}` becomes the actual number.

## 📦 Image Registry Architecture

Each environment pulls images from a different registry. **Never manually build and push beta or prod images** — CI does that automatically.

| Environment | Registry | How images get there | Pinning |
|-------------|----------|---------------------|---------|
| **Alpha** (local) | `localhost:32000` | You build and push manually | Version tag OK for PenguinTech; digest for external |
| **Beta** | `ghcr.io/{org}/{repo}/{service}` | CI builds on release branches (`beta-<epoch>` tag) | Version tag OK for PenguinTech; digest for external |
| **Gamma** (pre-release) | `ghcr.io/{org}/{repo}/{service}` | CI builds on `main` branch (`gamma-<epoch>` tag) | Version tag OK for PenguinTech; digest for external |
| **Prod** | `ghcr.io/{org}/{repo}/{service}` | CI builds on version tags (`v1.2.3`) | SHA256 digest required for all images |
| ~~Legacy~~ | ~~`registry-dal2.penguintech.io`~~ | Deprecated — do not push here | — |

**Why ghcr.io for beta/prod?** CI builds are reproducible: multi-arch (amd64+arm64), consistent caching, same base image freshness every time. A locally-built image on your laptop won't match CI — architectures, library versions, and OS patches differ.

### Setting Up the Pull Secret (One-Time)

Beta and prod clusters need a credential to pull from `ghcr.io`. Run this once per cluster/namespace:

```bash
# Set up the pull secret on beta
./scripts/setup-ghcr-pull-secret.sh --context dal2-beta --namespace myapp

# Or on local alpha (if testing ghcr.io images there)
./scripts/setup-ghcr-pull-secret.sh --context local-alpha --namespace myapp
```

This creates a `ghcr-pull-secret` Kubernetes secret. Your Helm values must reference it:

```yaml
# values-beta.yaml
imagePullSecrets:
  - name: ghcr-pull-secret
```

### Beta Deployment Flow

```
Developer pushes to v1.2.x release branch
        ↓
GitHub Actions builds image (linux/amd64 + linux/arm64)
        ↓
Image pushed to ghcr.io/.../flask-backend:beta-1710000000
        ↓
deploy-beta.sh queries ghcr.io for latest beta tag
        ↓
helm upgrade --install ... --set image.tag=beta-1710000000
        ↓
Pods pull from ghcr.io (via ghcr-pull-secret)
```

```bash
# Deploy latest CI-built beta image
./scripts/deploy-beta.sh

# Deploy a specific CI-built tag
./scripts/deploy-beta.sh --tag beta-1710000000

# Clean deploy (uninstall + redeploy)
./scripts/deploy-beta.sh --clean

# Last resort fallback (deprecated — use only when CI is down)
./scripts/deploy-beta.sh --local
```

## 📌 Image Pinning Requirements

**Mutable tags (`latest`, `stable`, branch names) are forbidden.** They resolve to different images silently over time, pulling in upstream changes, CVEs, or breaking changes without warning.

| Image Type | Alpha | Beta | Production |
|------------|-------|------|------------|
| **External images** (postgres, redis, nginx) | SHA256 digest required | SHA256 digest required | SHA256 digest required |
| **PenguinTech images** (ghcr.io/penguintechinc/*) | Version tag OK | Version tag OK | SHA256 digest required |

### How to Get a Digest

```bash
# Pull and inspect
docker pull python:3.13-slim-bookworm
docker inspect python:3.13-slim-bookworm --format='{{index .RepoDigests 0}}'
# → python@sha256:abc123...

# Or with crane (no pull needed — faster)
crane digest python:3.13-slim-bookworm
```

### Kustomize Examples

**Alpha/Beta — PenguinTech images (version tag is OK):**
```yaml
# k8s/kustomize/overlays/beta/kustomization.yaml
images:
  - name: flask-backend
    newName: ghcr.io/penguintechinc/myapp/flask-backend
    newTag: beta-1710000000      # tag is acceptable for alpha/beta
```

**Production — PenguinTech images (digest required):**
```yaml
# k8s/kustomize/overlays/prod/kustomization.yaml
images:
  - name: flask-backend
    newName: ghcr.io/penguintechinc/myapp/flask-backend
    digest: sha256:<digest>      # digest required in production
```

**All environments — External dependency images (digest always required):**
```yaml
# Even in alpha, external images must use a digest
images:
  - name: postgres
    newName: postgres
    newTag: ""
    digest: sha256:<digest>
```

### Helm Values (Production)

```yaml
# values-prod.yaml
image:
  repository: ghcr.io/penguintechinc/myapp/flask-backend
  tag: ""                        # leave empty when using digest
  digest: sha256:<digest>        # required in production
```

### Keeping Digests Up-to-Date

Configure **Renovate** or **Dependabot** to open PRs when digest updates are available:
- **Renovate**: Enable the `docker` manager with `pinDigests: true`
- **Dependabot**: Use `ecosystem: docker` in `.github/dependabot.yml`

Don't update digests manually — let automation handle it so updates are reviewed and tested via PRs.

## 🎯 Common K8s Patterns We Use

### Deployments - Keep Your App Running

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: myapp
        image: ghcr.io/penguintechinc/myapp:v1.0.0
        ports:
        - containerPort: 5000
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
```

### Services - Expose Your App Internally

```yaml
apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  type: ClusterIP
  selector:
    app: myapp
  ports:
  - port: 80
    targetPort: 5000
```

### Ingress - Route External Traffic

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
spec:
  ingressClassName: nginx
  rules:
  - host: myapp.penguintech.cloud
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: myapp
            port:
              number: 80
```

## 🌐 Production Domains & Routing

### Domain Strategy by Environment

Production deployments use registered `.app` domains as the canonical URL, with `.penguincloud.io` subdomains redirecting.

| Repo | `.app` Domain (Canonical) | `.penguincloud.io` (Redirects) |
|------|--------------------------|-------------------------------|
| articdbm | `articdbm.app` | `articdbm.penguincloud.io` |
| darwin | `darwincode.app` | `darwin.penguincloud.io` |
| elder | `elderrms.app` | `elder.penguincloud.io` |
| icecharts | `icecharts.app` | `icecharts.penguincloud.io` |
| killkrill | `killkrill.app` | `killkrill.penguincloud.io` |
| marchproxy | `marchproxy.app` | `marchproxy.penguincloud.io` |
| skauswatch | `skauswatch.app` | `skauswatch.penguincloud.io` |
| squawk | `squawkmgr.app` | `squawk.penguincloud.io` |
| tobogganing | `tobogganing.app` | `tobogganing.penguincloud.io` |
| waddlebot | `waddles.app` | `waddlebot.penguincloud.io` |

**Rule**: If your product has a registered `.app` domain, use it as the canonical production URL. The `.penguincloud.io` subdomain provides a fallback and should redirect to the `.app` domain.

### Domain Usage by Environment

| Environment | Domain Pattern | Example |
|-------------|---|---|
| **Alpha** (Local) | `.localhost.local` | `myapp.localhost.local` |
| **Beta** (Development) | `.penguintech.cloud` | `myapp.penguintech.cloud` |
| **Prod** (Production) | `.app` (canonical) or `.penguincloud.io` | `myapp.app` → `myapp.penguincloud.io` |

## 🚀 XDP Deployment Profiles for Go Services

Go services support XDP/AF_XDP for high-performance packet processing. Because XDP requires elevated Linux capabilities, K8s manifests must support **two deployment profiles** controlled via Helm values.

### Standard Profile (Cilium CNI Handles XDP)

Use this profile when your cluster runs **Cilium CNI with XDP acceleration enabled**. The application is built with `-tags noxdp` and requires no special privileges.

```yaml
# values-alpha.yaml, values-beta.yaml, or values-prod.yaml
xdp:
  enabled: false    # Cilium CNI provides XDP acceleration
  buildTags: noxdp

securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  capabilities: {}
```

**When to use**: All Penguin Tech managed clusters (alpha, beta, prod) run Cilium with XDP. Use this profile by default.

### XDP Profile (Application-Managed XDP)

Use this profile when the **application manages its own XDP/AF_XDP stack** and the cluster does NOT have Cilium XDP. This requires elevated Linux capabilities and host network access.

```yaml
# values.yaml (custom deployments only)
xdp:
  enabled: true     # Application manages XDP stack
  buildTags: xdp

securityContext:
  runAsUser: 0                           # XDP requires root
  allowPrivilegeEscalation: true
  capabilities:
    add:
      - NET_ADMIN   # Required for XDP program attachment
      - SYS_ADMIN   # Required for BPF map operations
      - BPF         # Required for BPF syscalls (kernel 5.8+)
      - NET_RAW     # Required for raw socket/AF_XDP access

hostNetwork: true                        # Required for direct NIC access
```

**When to use**: Only for on-premise or custom cluster deployments without Cilium XDP. Document the cluster's XDP strategy in deployment guides.

### Helm Template Pattern

Use this conditional template pattern in your deployment manifests:

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Values.app.name }}
spec:
  template:
    spec:
      securityContext:
        {{- if .Values.xdp.enabled }}
        # XDP Profile: Application-managed
        runAsUser: 0
        allowPrivilegeEscalation: true
        capabilities:
          add: [NET_ADMIN, SYS_ADMIN, BPF, NET_RAW]
        {{- else }}
        # Standard Profile: Cilium-managed
        runAsNonRoot: true
        runAsUser: 1000
        allowPrivilegeEscalation: false
        {{- end }}

      {{- if .Values.xdp.enabled }}
      hostNetwork: true
      {{- end }}

      containers:
      - name: {{ .Values.app.name }}
        env:
        - name: XDP_MODE
          value: {{ if .Values.xdp.enabled }}"native"{{ else }}"cilium"{{ end }}
```

**Default**: Set `xdp.enabled: false` in base `values.yaml` for Penguin Tech deployments. Override only if deploying to a non-Cilium cluster.

## 🔒 Cilium CNI Preference

**Cilium is the preferred Container Network Interface (CNI) for all Penguin Tech K8s clusters.** Cilium provides:

- **eBPF-based NetworkPolicy enforcement** — Network policies are enforced at the kernel level, not userspace proxies
- **XDP acceleration** — Packet filtering and load balancing at the XDP layer without application code changes
- **Service mesh capabilities** — Automatic service-to-service encryption (mTLS) and observability
- **High performance** — Lower latency, higher throughput than traditional CNI plugins

### Cilium and XDP

By default, Cilium handles XDP offloading transparently. Applications do NOT need to manage XDP themselves when running on Cilium clusters. Deploy with the **Standard Profile** (`xdp.enabled: false`) on all Penguin Tech managed clusters.

**Rule**: If you see XDP-related errors in production, check that Cilium is installed and healthy:

```bash
kubectl get pods -n kube-system | grep cilium
kubectl logs -n kube-system -l k8s-app=cilium --tail=50
```

### NetworkPolicy and Cilium

Always define Kubernetes NetworkPolicies in your deployments. Cilium enforces them at the eBPF level:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-ingress
spec:
  podSelector: {}
  policyTypes:
  - Ingress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
spec:
  podSelector:
    matchLabels:
      tier: backend
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          tier: frontend
    ports:
    - protocol: TCP
      port: 5000
```

Cilium will compile these policies into BPF programs and enforce them in the kernel.

## 🔧 Troubleshooting K8s (Common Fixes)

**Pod stuck in "Pending"?**
```bash
# Always pass --context; namespace = product name only (no -prod/-beta suffix)
kubectl --context {context} describe pod myapp-xyz -n myapp
# Check: resource limits, node capacity, node affinity
```

**Pod crashing repeatedly?**
```bash
kubectl --context {context} logs myapp-xyz -n myapp
kubectl --context {context} logs myapp-xyz -n myapp --previous  # See last run
```

**Can't reach my service?**
```bash
# Test from inside cluster
kubectl --context {context} run -it --rm debug --image=busybox --restart=Never -- \
  wget -O- http://myapp.myapp.svc.cluster.local
```

**Deployment not rolling out?**
```bash
kubectl --context {context} rollout status deployment/myapp -n myapp
kubectl --context {context} rollout history deployment/myapp -n myapp
```

## 📊 Monitoring Your Pods

**Check pod status at a glance:**
```bash
# Replace {context} with local-alpha, dal2-beta, or {repo}-prod
kubectl --context {context} get pods -n myapp
kubectl --context {context} get pods -n myapp -o wide
```

**Watch pod events in real-time:**
```bash
kubectl --context {context} get events -n myapp --sort-by='.lastTimestamp'
```

**View logs:**
```bash
kubectl --context {context} logs -n myapp -l app=myapp --tail=100 -f
```

**Resource usage:**
```bash
kubectl --context {context} top pods -n myapp
kubectl --context {context} top nodes
```

## 💻 Local Development (MicroK8s)

**MicroK8s** is the standard — see setup instructions at the top of this guide. Other options:

| Tool | Platform | Notes |
|------|----------|-------|
| **MicroK8s** (recommended) | Ubuntu/Debian | `sudo snap install microk8s --classic` |
| Docker Desktop | Mac/Windows | Enable K8s in settings |
| Podman Desktop | Cross-platform | Enable K8s in settings |

**Test your Helm chart before deploying:**
```bash
helm lint ./k8s/helm                    # Check syntax
helm template myapp ./k8s/helm          # See final YAML
helm install myapp ./k8s/helm --dry-run --debug  # Mock deploy
```

## ✅ Before Deploying to Production

1. **Validate your YAML**
   ```bash
   helm lint ./k8s/helm
   kubectl kustomize k8s/kustomize/overlays/prod  # Preview without deploying
   ```

2. **Set resource limits** (always!)
   ```yaml
   resources:
     requests:
       cpu: 250m
       memory: 256Mi
     limits:
       cpu: 500m
       memory: 512Mi
   ```

3. **Add health checks** (liveness & readiness probes)
   ```yaml
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
   ```

4. **Security matters**
   ```yaml
   securityContext:
     runAsNonRoot: true
     runAsUser: 1000
     allowPrivilegeEscalation: false
   ```

5. **Never commit secrets** - use external secret stores (Vault, Sealed Secrets)

## 📚 Quick Reference

| Task | Command |
|------|---------|
| Deploy to alpha | `kubectl apply --context local-alpha -k k8s/kustomize/overlays/alpha` |
| Deploy to beta | `./scripts/deploy-beta.sh` |
| Deploy to prod | `helm upgrade --install myapp ./k8s/helm --kube-context {repo}-prod --namespace myapp --values ./k8s/helm/values-prod.yaml` |
| Update prod | `helm upgrade myapp ./k8s/helm --kube-context {repo}-prod --namespace myapp --values ./k8s/helm/values-prod.yaml` |
| Rollback | `helm rollback myapp 1 --kube-context dal2-beta --namespace myapp` |
| View logs | `kubectl --context dal2-beta logs -n myapp -l app=myapp -f` |
| Check status | `kubectl --context dal2-beta get pods -n myapp` |
| Delete release | `helm uninstall myapp --kube-context dal2-beta --namespace myapp` |

## 🎯 Key Principles

1. **One location**: All K8s files live in `k8s/` directory
2. **Support both**: Helm (beta/prod) AND Kustomize (alpha) — both must deploy the full product
3. **Namespace = product name only**: Never append `-alpha`, `-beta`, `-dev`, or `-prod`
4. **Always pass `--context`**: Never change the global kubeconfig context
5. **CI builds beta/prod images**: Never manually build and push to ghcr.io — let CI do it
6. **Alpha uses `localhost:32000`**: Build locally, push to MicroK8s registry
7. **Always set limits**: CPU and memory requests/limits required
8. **Always health check**: Liveness + readiness probes mandatory
9. **Secure by default**: Non-root users, no privilege escalation
10. **Test first**: Lint + dry-run before deploying

📚 **Related Standards**: [Architecture](ARCHITECTURE.md) | [Testing Phase 3](TESTING.md#phase-3-deployment--live-testing-k8s)
