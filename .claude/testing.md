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
