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

## 🚀 Your First Deployment (Step-by-Step)

**1. Set up your K8s files:**

Create the directory structure:
```
k8s/
├── helm/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── values-dev.yaml
│   ├── values-prod.yaml
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
        ├── dev/
        ├── staging/
        └── prod/
```

**2. Deploy to dev (super simple):**

```bash
# Using Helm
helm install myapp ./k8s/helm \
  --namespace myapp-dev \
  --create-namespace \
  --values ./k8s/helm/values-dev.yaml

# Check it worked
kubectl get pods -n myapp-dev
```

**3. Update your app:**

```bash
helm upgrade myapp ./k8s/helm \
  --namespace myapp-dev \
  --values ./k8s/helm/values-dev.yaml
```

**4. Oops, roll back if needed:**

```bash
helm rollback myapp 1 --namespace myapp-dev
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
kubectl describe pod myapp-xyz -n myapp-prod
# Check: resource limits, node capacity, node affinity
```

**Pod crashing repeatedly?**
```bash
kubectl logs myapp-xyz -n myapp-prod
kubectl logs myapp-xyz -n myapp-prod --previous  # See last run
```

**Can't reach my service?**
```bash
# Test from inside cluster
kubectl run -it --rm debug --image=busybox --restart=Never -- \
  wget -O- http://myapp.myapp-prod.svc.cluster.local
```

**Deployment not rolling out?**
```bash
kubectl rollout status deployment/myapp -n myapp-prod
kubectl rollout history deployment/myapp -n myapp-prod
```

## 📊 Monitoring Your Pods

**Check pod status at a glance:**
```bash
kubectl get pods -n myapp-prod
kubectl get pods -n myapp-prod -o wide  # More details
```

**Watch pod events in real-time:**
```bash
kubectl get events -n myapp-prod --sort-by='.lastTimestamp'
```

**View logs:**
```bash
kubectl logs -n myapp-prod -l app=myapp --tail=100 -f
```

**Resource usage:**
```bash
kubectl top pods -n myapp-prod
kubectl top nodes
```

## 💻 Local Development (Testing Before Real K8s)

**Minikube** - Kubernetes on your laptop:
```bash
minikube start
# Your local K8s cluster is ready!

minikube stop    # Clean up when done
```

**Kind** - Docker-based K8s (lighter):
```bash
kind create cluster --name dev
kubectl cluster-info --context kind-dev
```

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
   kubectl kustomize k8s/kustomize/overlays/prod
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
| Deploy | `helm install myapp ./k8s/helm --namespace myapp-prod --values ./k8s/helm/values-prod.yaml` |
| Update | `helm upgrade myapp ./k8s/helm --namespace myapp-prod --values ./k8s/helm/values-prod.yaml` |
| Rollback | `helm rollback myapp 1 --namespace myapp-prod` |
| View logs | `kubectl logs -n myapp-prod -l app=myapp -f` |
| Check status | `kubectl get pods -n myapp-prod` |
| Delete release | `helm uninstall myapp --namespace myapp-prod` |

## 🎯 Key Principles

1. **One location**: All K8s files live in `k8s/` directory
2. **Support both**: Helm (preferred) + Kustomize (alternatives)
3. **Environment isolation**: Separate namespaces for dev/staging/prod
4. **Always set limits**: CPU and memory requests/limits required
5. **Always health check**: Liveness + readiness probes mandatory
6. **Secure by default**: Non-root users, no privilege escalation
7. **Test first**: Lint + dry-run before deploying
8. **Keep it simple**: K8s is powerful, but don't overcomplicate

📚 **Related Standards**: [Architecture](ARCHITECTURE.md) | [Testing Phase 3](TESTING.md#phase-3-deployment--live-testing-k8s)
