# Tobogganing - Pre-Commit Checklist

This checklist must be completed before every git commit. Follow the steps in order. The entire checklist should take 5-10 minutes for typical changes.

## Quick Reference

```bash
# Run the full pre-commit sequence
make smoke-test && make seed-mock-data && make lint && make test-unit && make security-scan && make build
```

## Step 1: Smoke Tests (< 2 minutes)

Smoke tests verify that the build is not broken. These are mandatory and must pass.

```bash
make smoke-test
```

**What this verifies:**
- All three services compile/build without errors
- Docker images build successfully (if Docker changes were made)
- Health endpoints respond correctly
- Database connectivity works
- Redis connectivity works

**If smoke tests fail**: Fix the build error before proceeding. Do not commit broken builds.

## Step 2: Seed Mock Data and Verify

Populate the development environment with test data and verify it renders correctly in the UI.

```bash
make seed-mock-data
```

**Verify in the WebUI** (http://localhost:3000):
- Dashboard loads and displays hub status
- Users list shows all 4 test users with correct roles
- Policies list shows all 4 test policies
- Hub list shows all 3 regional hubs

**If mock data fails**: Check database connectivity and migration status with `make db-reset && make db-migrate`.

## Step 3: Run Linting

All code must pass linting before commit. No exceptions.

### hub-api (Python)

```bash
make lint-hub-api
```

Individual lint tools:
```bash
cd services/hub-api

# Style checking
python -m flake8 .

# Code formatting verification
python -m black --check .

# Import ordering verification
python -m isort --check-only .

# Type checking
python -m mypy .

# Security static analysis
python -m bandit -r . -x tests
```

**Auto-fix formatting issues:**
```bash
cd services/hub-api
python -m black .
python -m isort .
```

### hub-router (Go)

```bash
make lint-hub-router
```

Or directly:
```bash
cd services/hub-router
golangci-lint run
```

**Auto-fix where possible:**
```bash
cd services/hub-router
golangci-lint run --fix
gofmt -w .
```

### hub-webui (React/TypeScript)

```bash
make lint-hub-webui
```

Or directly:
```bash
cd services/hub-webui
npm run lint
```

**Auto-fix where possible:**
```bash
cd services/hub-webui
npm run lint -- --fix
npm run format
```

### Run All Linting at Once

```bash
make lint
```

**If linting fails**: Fix all reported issues. Do not use `// nolint`, `# noqa`, or `eslint-disable` comments unless there is a documented justification in the code.

## Step 4: Run Unit Tests

All unit tests must pass for the services affected by your changes.

### If you changed hub-api code:

```bash
make test-hub-api
```

### If you changed hub-router code:

```bash
make test-hub-router
```

### If you changed hub-webui code:

```bash
make test-hub-webui
```

### Run all unit tests:

```bash
make test-unit
```

**Verify:**
- All tests pass (no failures or errors)
- No race conditions detected (hub-router uses `-race` flag)
- Coverage does not decrease for changed files

**If tests fail**: Fix the failing tests or the code they test. Do not skip or disable tests without team approval.

## Step 5: Security Scan

Security scanning catches vulnerabilities in code and dependencies.

```bash
make security-scan
```

This runs:

| Tool | Service | What it checks |
|------|---------|----------------|
| bandit | hub-api | Python security anti-patterns |
| pip-audit | hub-api | Python dependency vulnerabilities |
| gosec | hub-router | Go security issues |
| npm audit | hub-webui | JavaScript dependency vulnerabilities |
| trivy | All | Container image and filesystem vulnerabilities |

**If security scan finds issues:**
- **Critical/High severity**: Must be fixed before commit
- **Medium severity**: Should be fixed; document in commit message if deferring
- **Low/Info severity**: Fix when practical; acceptable to commit with these

**Common security fixes:**
```bash
# Python dependency updates
cd services/hub-api && pip install --upgrade <package>

# Go dependency updates
cd services/hub-router && go get -u <package>

# JavaScript dependency updates
cd services/hub-webui && npm audit fix
```

## Step 6: Build Verification

Verify that the production build succeeds for all changed services.

```bash
make build
```

For Docker images (if Dockerfile changes or dependency changes):

```bash
make docker-build
```

**Verify:**
- Build completes without errors or warnings
- No new deprecation warnings introduced
- Output artifacts are the expected size (not suspiciously small or large)

## Step 7: Screenshot Updates

If your change affects the WebUI, capture updated screenshots with realistic mock data displayed.

1. Ensure mock data is seeded (Step 2)
2. Navigate to the affected pages in the WebUI
3. Capture screenshots showing the change
4. Save screenshots to `docs/screenshots/` with descriptive names
5. Include screenshots in the pull request description

**Screenshot naming convention:**
```
docs/screenshots/{page}-{feature}-{date}.png
# Examples:
docs/screenshots/dashboard-hub-status-2026-02-08.png
docs/screenshots/policy-editor-cidr-rule-2026-02-08.png
```

## Commit Message Format

After all checks pass, create your commit with a descriptive message:

```
<type>(<scope>): <short description>

<detailed description of what changed and why>

Tested:
- [ ] Smoke tests pass
- [ ] Linting clean
- [ ] Unit tests pass
- [ ] Security scan clean
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `security`

**Scopes**: `hub-api`, `hub-router`, `hub-webui`, `client`, `infra`, `ci`, `docs`

**Examples:**
```
feat(hub-api): add SCIM provisioning endpoint for user sync

Implements the SCIM 2.0 protocol for automated user and group
provisioning from external identity providers. This is a
license-gated premium feature.

Tested:
- [x] Smoke tests pass
- [x] Linting clean
- [x] Unit tests pass (12 new tests)
- [x] Security scan clean
```

```
fix(hub-router): resolve race condition in policy evaluation cache

Fixed a data race when concurrent goroutines accessed the policy
cache during a policy update. Added sync.RWMutex protection and
verified with go test -race.

Tested:
- [x] Smoke tests pass
- [x] Linting clean
- [x] Unit tests pass (race detector clean)
- [x] Security scan clean
```

## Full Quality Assurance (Optional)

For larger changes or before release, run the complete QA suite:

```bash
make qa
```

This combines linting, all tests (unit + integration + e2e), and security scanning. Takes approximately 15-20 minutes.

## Quick Checklist Summary

Copy this into your workflow:

```
Pre-Commit Checklist:
[ ] 1. make smoke-test          - builds and health checks pass
[ ] 2. make seed-mock-data      - mock data loads correctly
[ ] 3. make lint                - all linting passes
[ ] 4. make test-unit           - all unit tests pass
[ ] 5. make security-scan       - no critical/high findings
[ ] 6. make build               - production build succeeds
[ ] 7. Screenshots updated      - if WebUI changes (with mock data visible)
```
