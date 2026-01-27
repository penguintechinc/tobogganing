# Container Image Standards

## ⚠️ CRITICAL RULES

1. **Debian 12 (bookworm) ONLY** - all container images must use Debian-based images
2. **NEVER use Alpine** - causes glibc/musl compatibility issues, missing packages, debugging difficulties
3. **Use `-slim` variants** when available for smaller image sizes
4. **PostgreSQL 16.x** standard for all database containers
5. **Multi-arch builds required** - support both amd64 and arm64

---

## Base Image Selection

### Priority Order (MUST follow)

1. **Debian 12 (bookworm)** - PRIMARY, always use if available
2. **Debian 11 (bullseye)** - fallback if bookworm unavailable
3. **Debian 13 (trixie)** - fallback for newer packages
4. **Ubuntu LTS** - ONLY if no Debian option exists
5. ❌ **NEVER Alpine** - forbidden, causes too many issues

---

## Standard Images

| Service | Image | Notes |
|---------|-------|-------|
| PostgreSQL | `postgres:16-bookworm` | Primary database |
| MySQL | `mysql:8.0-debian` | Alternative database |
| Redis | `redis:7-bookworm` | Cache/session store |
| Python | `python:3.13-slim-bookworm` | Flask backend |
| Node.js | `node:18-bookworm-slim` | WebUI build |
| Nginx | `nginx:stable-bookworm-slim` | Reverse proxy |
| Go | `golang:1.24-bookworm` | Build stage only |
| Runtime | `debian:bookworm-slim` | Go runtime stage |

---

## Dockerfile Patterns

### Python Service
```dockerfile
FROM python:3.13-slim-bookworm AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

FROM python:3.13-slim-bookworm
WORKDIR /app
COPY --from=builder /app /app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
```

### Go Service
```dockerfile
FROM golang:1.24-bookworm AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app/server

FROM debian:bookworm-slim
COPY --from=builder /app/server /server
CMD ["/server"]
```

### Node.js/React Service
```dockerfile
FROM node:18-bookworm-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-bookworm-slim
COPY --from=builder /app/dist /usr/share/nginx/html
```

---

## Why Not Alpine?

❌ **glibc vs musl** - Many Python packages require glibc, Alpine uses musl
❌ **Missing packages** - Common tools often unavailable or different versions
❌ **Debugging harder** - No bash by default, limited tooling
❌ **DNS issues** - Known DNS resolution problems in some scenarios
❌ **Build failures** - C extensions often fail to compile

✅ **Debian-slim** - Only ~30MB larger than Alpine but zero compatibility issues

---

## Docker Compose Example

```yaml
services:
  postgres:
    image: postgres:16-bookworm

  redis:
    image: redis:7-bookworm

  api:
    build:
      context: ./services/flask-backend
    # Uses python:3.13-slim-bookworm internally

  web:
    image: nginx:stable-bookworm-slim
```
