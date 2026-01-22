# Architecture - The Big Picture

Part of [Development Standards](../STANDARDS.md)

## The System at a Glance

Welcome to the three-container architecture! This is where **simplicity meets power**. Instead of building one giant monolith, we split the work into three specialized containers that each do one thing really well.

Think of it like a restaurant:
- **WebUI** = The server taking orders and presenting the menu (your frontend)
- **Flask Backend** = The kitchen making dishes (your business logic & databases)
- **Go Backend** = The delivery truck for rush orders (when you need SPEED)

```
                    🌐 THE WORLD
                         ↓
        ┌────────────────────────────────────┐
        │   NGINX / MarchProxy (Optional)    │
        └────────────────────────────────────┘
                 ↙          ↓          ↘

    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │   🌐 WebUI   │  │  🐍 Flask    │  │   ⚡ Go      │
    │ Node+React   │  │  Backend     │  │   Backend    │
    │ Port 3000    │  │  Port 5000   │  │   Port 8080  │
    │              │  │              │  │              │
    │ • Frontend   │  │ • Auth       │  │ • Networking │
    │ • Routing    │  │ • CRUD APIs  │  │ • XDP/AF_XDP │
    │ • Serving    │  │ • Users      │  │ • NUMA speed │
    └──────────────┘  └──────────────┘  └──────────────┘
         ↓                   ↓                   ↓
    [requests]       [gRPC + REST]      [gRPC calls]
         ↓                   ↓                   ↓
         └───────────────────┴───────────────────┘
                         ↓
                   🗄️ PostgreSQL
                   (or MySQL, MariaDB, SQLite)
```

## Your Three Containers Explained Simply

### 🐍 Flask Backend - The Brains

**Technology:** Flask + PyDAL

**What it does:** Handles all the thinking work. Authentication, user management, databases, business logic. This is where your API lives.

**When to use:** Always. Default choice for <10K requests/second with business logic.

**What's inside:**
- JWT authentication with bcrypt hashing
- User management (create, edit, delete)
- Three default roles: **Admin** (everything), **Maintainer** (read/write, no users), **Viewer** (read-only)
- Multi-database support via PyDAL (PostgreSQL, MySQL, MariaDB, SQLite)
- Health checks and monitoring
- REST APIs under `/api/v1/`

**Example endpoints:**
```
POST   /api/v1/auth/login
GET    /api/v1/users
POST   /api/v1/users
PUT    /api/v1/users/{id}
DELETE /api/v1/users/{id}
GET    /healthz
```

### 🌐 WebUI - The Frontend Shell

**Technology:** Node.js + React

**What it does:** Shows the pretty interface. Takes user clicks, sends them to the Flask backend, displays results. Pure frontend.

**When to use:** Always, for every project.

**What's inside:**
- React single-page application (SPA)
- Express.js proxy to backend APIs
- Role-based navigation (Admin sees more than Viewer)
- Elder-style collapsible sidebar navigation
- WaddlePerf-style tab interface
- Gold text theme (amber-400)
- Static asset serving

**Serves on:** Port 3000

**How it talks to Flask:** Proxies HTTP/REST calls transparently. User clicks a button → WebUI sends REST request to Flask Backend.

### ⚡ Go Backend - The Speed Demon

**Technology:** Go + XDP/AF_XDP

**What it does:** Handles massive amounts of data with minimal latency. Only use when you NEED speed.

**When to use:** ONLY if you're handling >10K requests/second with <10ms latency requirements.

**What's inside:**
- XDP (eXpress Data Path): Kernel-level packet processing for blazing fast networking
- AF_XDP: Zero-copy socket operations
- NUMA-aware memory allocation (multi-socket systems)
- Memory slot pools for efficient buffer management
- Prometheus metrics for monitoring

**Serves on:** Port 8080 (or 50051 for gRPC)

**Important:** Don't use Go "just because." Use it only when performance profiling shows Python won't cut it.

### 🔗 Connector - The Integrations Placeholder

Template includes a placeholder for external integrations. Add here when you need to talk to outside systems (webhooks, third-party APIs, background jobs, etc.).

---

## How Everything Talks Together

### 🔄 Container Communication Patterns

#### External Clients → Your System
```
Browser/Mobile App
    ↓ HTTPS (REST)
WebUI (3000) ← external port exposed for user access
    ↓ Internal HTTP (REST)
Flask Backend (5000)
    ↓ Local Docker network
PostgreSQL
```

#### Inside the System (Service-to-Service)
```
WebUI ──────→ Flask Backend  [REST over local network]
Flask ──────→ Go Backend     [gRPC for speed]
Flask ──────→ PostgreSQL     [PyDAL connections]
```

### Protocol Selection: Keep It Simple

| Direction | Protocol | Why |
|-----------|----------|-----|
| **Outside → WebUI** | HTTPS/REST | People expect REST; easy to test with curl/Postman |
| **WebUI → Flask** | HTTP/REST | Simple, everyone knows it, no special tooling needed |
| **Flask → Go** | gRPC | Binary is fast, built-in streaming, low overhead |
| **Flask → Database** | PyDAL | Abstracts database details, handles pooling automatically |

**Golden Rule:** REST for anything crossing the container boundary to the outside world. gRPC for internal speed-critical calls. Plain database drivers for data layers.

---

## 🚀 Getting Everything Running Locally

### Step 1: One Command to Rule Them All

```bash
make dev
```

This starts all three containers, database, and everything you need.

**What happens:**
1. Flask Backend builds and starts (listens on port 5000)
2. WebUI builds and starts (listens on port 3000)
3. Go Backend builds and starts (if you have one)
4. PostgreSQL spins up
5. All connected on internal Docker network

### Step 2: Open Your Browser

```
http://localhost:3000
```

You're in! The WebUI is serving. Behind the scenes:
- WebUI sends your requests to Flask
- Flask queries the database
- Database returns data
- Flask sends back JSON
- WebUI shows you the results

### Step 3: Testing the APIs Directly

```bash
# Login and get a token
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin"}'

# Use token to get users
curl -X GET http://localhost:5000/api/v1/users \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Step 4: Seeding Test Data

```bash
make seed-mock-data
```

Populates your database with 3-4 sample items for each feature so you can see the app actually working with real-ish data.

### Step 5: Running Tests

```bash
# Smoke tests (fast, essential)
make smoke-test

# All tests
make test

# Specific category
make test-unit
make test-integration
make test-e2e
```

---

## ➕ Adding a New Service

Need a fourth container? Here's how:

### Step 1: Create the Service Folder

```bash
mkdir services/my-service
cd services/my-service
```

### Step 2: Add Your Code

Create your application (Node.js, Python, Go, whatever):

```bash
# Example: Node.js Express service
npm init -y
npm install express
cat > index.js << 'EOF'
const express = require('express');
const app = express();
app.get('/healthz', (req, res) => res.json({status: 'healthy'}));
app.listen(5050, () => console.log('Running on 5050'));
EOF
```

### Step 3: Create a Dockerfile

```dockerfile
FROM node:18-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
HEALTHCHECK --interval=30s --timeout=3s CMD node -e \
  "require('http').get('http://localhost:5050/healthz', \
   (r) => process.exit(r.statusCode === 200 ? 0 : 1))"
CMD ["node", "index.js"]
```

### Step 4: Add to Docker Compose

```yaml
# In docker-compose.dev.yml
services:
  my-service:
    build: ./services/my-service
    ports:
      - "5050:5050"
    networks:
      - app-network
    depends_on:
      postgres:
        condition: service_healthy
```

### Step 5: Update CI/CD

Add to `.github/workflows/` so it builds and tests automatically.

### Step 6: Register with MarchProxy

If this is a production service, add to `config/marchproxy/services.json`:

```json
{
  "name": "myapp-my-service",
  "ip_fqdn": "my-service",
  "port": 5050,
  "protocol": "http",
  "collection": "myapp"
}
```

### Step 7: Document It

Add section to this file explaining what it does!

---

## ❓ Architecture FAQ

### Q: Why three containers instead of one big app?

**A:** Separation of concerns! The WebUI scales independently of the API. The Go backend only runs when you need speed. One container going down doesn't take everything else with it. You can deploy just the API while keeping WebUI running.

### Q: Do I really need the Go backend?

**A:** Probably not right away. Start with Flask. Only add Go when:
- Your load tests show Flask hitting CPU limits
- You're genuinely handling >10K req/sec
- You profiled and found network as the bottleneck

**Don't add complexity you don't need.**

### Q: What if I only want two containers (no Go backend)?

**A:** Totally fine. Docker Compose won't break. Just don't include go-backend in your compose file. Most projects only need Flask + WebUI.

### Q: How do I add a database?

**A:** It's already there! PostgreSQL runs by default. To switch databases:

```bash
# Set environment variable before starting
export DB_TYPE=mysql  # or sqlite, mariadb
make dev
```

All database drivers are built in via PyDAL. It "just works."

### Q: Can I run this on Kubernetes?

**A:** Yes! Each service becomes a Deployment. Database becomes a StatefulSet. Services expose via ClusterIP internally, Ingress externally. That's advanced, but the template supports it—see the `infrastructure/` folder.

### Q: How do I know which protocol to use between services?

**A:** Simple rule:
- **Going outside the cluster?** REST/HTTPS
- **Inside the cluster, needs speed?** gRPC
- **Database operations?** Use the driver (PyDAL, etc.)

---

## 📈 Scaling: Simple Edition

### Vertical Scaling (Make One Container Bigger)
```bash
# Give Flask more resources
docker update --cpus="2" --memory="2g" flask-backend
```

Works for small growth, then you hit a wall.

### Horizontal Scaling (Add More Containers)

**Option 1: Locally with Docker Compose** (for testing)
```yaml
services:
  flask-backend:
    deploy:
      replicas: 3  # Run 3 copies
```

**Option 2: Kubernetes** (production)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flask-backend
spec:
  replicas: 3  # Start with 3 pods
  selector:
    matchLabels:
      app: flask-backend
```

### Caching Layer (Redis)

When Flask starts hitting the database too hard:

```bash
# Add Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

Then in Flask:
```python
from redis import Redis
cache = Redis(host='redis', port=6379)
# Cache frequently accessed data
```

### Database Scaling

- **Read-heavy?** Add read replicas (PostgreSQL replication)
- **Write-heavy?** Use MariaDB Galera for multi-master
- **Giant dataset?** Shard across databases (app-level or database-level)

**Start simple, scale when needed.**

---

## Standards Summary

✅ **DO:**
- Use REST for external APIs
- Use gRPC for internal high-performance calls
- Run database operations through PyDAL
- Implement `/healthz` endpoint in every service
- Keep services independent and focused
- Use Docker networks, not host ports
- Test on both amd64 and arm64 architectures

❌ **DON'T:**
- Hardcode service hostnames (use environment variables)
- Skip health checks
- Use curl in Dockerfiles for health checks (use native language)
- Build Go "for fun" if Flask would work
- Couple containers tightly (API-first design)
- Expose unnecessary ports to the host

---

**Enjoy building! Keep it simple, add complexity only when needed.** 🚀
