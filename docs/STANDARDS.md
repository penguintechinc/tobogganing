# Development Standards

**⚠️ Important**: This is a company-wide standards document containing best practices and patterns that apply across all Penguin Tech Inc projects. **Application-specific standards, architecture decisions, requirements, and context should be documented in `docs/APP_STANDARDS.md` instead.** This separation allows the template STANDARDS.md to be updated across all projects without losing app-specific information.

## Overview

This document serves as an index to comprehensive development standards organized by category. Each category has detailed documentation in the `docs/standards/` directory.

## Quick Reference

| Category | File | Key Topics |
|----------|------|------------|
| **Language Selection** | [LANGUAGE_SELECTION.md](standards/LANGUAGE_SELECTION.md) | Python 3.13 vs Go 1.24.x decision criteria, traffic thresholds |
| **Authentication** | [AUTHENTICATION.md](standards/AUTHENTICATION.md) | Flask-Security-Too, RBAC, SSO, password reset, login UI |
| **Frontend** | [FRONTEND.md](standards/FRONTEND.md) | ReactJS patterns, API client, hooks, components |
| **Database** | [DATABASE.md](standards/DATABASE.md) | PyDAL, SQLAlchemy, multi-DB support, MariaDB Galera |
| **API & Protocols** | [API_PROTOCOLS.md](standards/API_PROTOCOLS.md) | REST, gRPC, HTTP/3, API versioning, deprecation |
| **Performance** | [PERFORMANCE.md](standards/PERFORMANCE.md) | Dataclasses, asyncio, threading, XDP/AF_XDP |
| **Architecture** | [ARCHITECTURE.md](standards/ARCHITECTURE.md) | Microservices, Docker, multi-arch builds, MarchProxy |
| **Kubernetes** | [KUBERNETES.md](standards/KUBERNETES.md) | Helm v3, Kustomize, K8s deployments, best practices |
| **Testing** | [TESTING.md](standards/TESTING.md) | Unit, integration, E2E, smoke tests, performance |
| **Security** | [SECURITY.md](standards/SECURITY.md) | TLS, secrets, vulnerability scanning, CodeQL |
| **Documentation** | [DOCUMENTATION.md](standards/DOCUMENTATION.md) | README, docs structure, release notes |
| **UI Design** | [UI_DESIGN.md](standards/UI_DESIGN.md) | Design patterns, components, styling, responsive |
| **Integrations** | [INTEGRATIONS.md](standards/INTEGRATIONS.md) | WaddleAI, MarchProxy, License Server patterns |

## Critical Standards Summary

### Language Selection (Case-by-Case)
- **Python 3.13**: Default for most applications (<10K req/sec)
- **Go 1.24.x**: Only for high-traffic/performance-critical (>10K req/sec)
- **Decision Matrix**: Profile first, start with Python, switch only when necessary

📚 **Details**: [standards/LANGUAGE_SELECTION.md](standards/LANGUAGE_SELECTION.md)

### Authentication (Mandatory)
- **Flask-Security-Too**: Required for ALL Flask applications
- **Features**: RBAC, JWT, password reset, 2FA, SSO (enterprise)
- **Default Admin**: Auto-created on startup (admin@localhost.local / admin123)
- **Password Reset**: Forgot password (SMTP required) + Change password (always available)

📚 **Details**: [standards/AUTHENTICATION.md](standards/AUTHENTICATION.md)

### Frontend (Mandatory)
- **ReactJS**: Required for ALL frontend applications
- **Node.js**: 18+ for build tooling
- **API Client**: Centralized axios client with auth interceptors

📚 **Details**: [standards/FRONTEND.md](standards/FRONTEND.md)

### Database (Mandatory)
- **PyDAL**: Runtime operations and migrations (mandatory)
- **SQLAlchemy**: Database initialization only
- **Multi-DB**: PostgreSQL (default), MySQL, MariaDB Galera, SQLite
- **DB_TYPE**: Environment variable for database selection

📚 **Details**: [standards/DATABASE.md](standards/DATABASE.md)

### API Design Principles
- **Versioning**: ALL APIs use `/api/v{major}/endpoint` format
- **REST**: External communication (clients, third-party)
- **gRPC**: Inter-container communication (preferred for performance)
- **HTTP/3**: Consider for high-performance scenarios (>10K req/sec)
- **Deprecation**: Support N-2 versions minimum (current + 2 previous)

📚 **Details**: [standards/API_PROTOCOLS.md](standards/API_PROTOCOLS.md)

### Performance Optimization
- **Dataclasses**: Use slots for 30-50% memory reduction
- **Type Hints**: Required for all Python code
- **Concurrency**:
  - `asyncio` for I/O-bound (>100 concurrent requests)
  - `threading` for blocking I/O and legacy integrations
  - `multiprocessing` for CPU-bound operations
- **Profile First**: Avoid premature optimization

📚 **Details**: [standards/PERFORMANCE.md](standards/PERFORMANCE.md)

### Microservices Architecture
- **Three-Container Pattern**: Flask backend, Go backend (optional), WebUI
- **Independent Deployment**: Each service has own Dockerfile
- **API-First Design**: Well-defined contracts between services
- **MarchProxy**: External API gateway/LB (not in default deployment)

📚 **Details**: [standards/ARCHITECTURE.md](standards/ARCHITECTURE.md)

### Docker Standards
- **Multi-Arch**: Build for amd64 and arm64
- **Base Images**: Debian-slim preferred
- **Cross-Architecture Testing**: Test on alternate arch before commit (QEMU)
- **Multi-Stage Builds**: Minimize image size

📚 **Details**: [standards/ARCHITECTURE.md](standards/ARCHITECTURE.md#docker-standards)

### Testing Requirements
- **Smoke Tests**: Build, run, API health, page loads (mandatory before commit)
- **Unit Tests**: Network isolated, mocked dependencies
- **Integration Tests**: Component interactions
- **E2E Tests**: Critical user workflows
- **Mock Data**: 3-4 items per feature/entity

📚 **Details**: [standards/TESTING.md](standards/TESTING.md)

### Security Standards
- **TLS**: 1.2 minimum, prefer TLS 1.3
- **Input Validation**: Mandatory for all inputs
- **Secrets**: Environment variables, never in code
- **Scanning**: Trivy, CodeQL (mandatory before commit)
- **Dependencies**: Monitor Dependabot, fix all vulnerabilities

📚 **Details**: [standards/SECURITY.md](standards/SECURITY.md)

## Pre-Commit Requirements

**CRITICAL - Run before every commit:**

```bash
./scripts/pre-commit/pre-commit.sh
```

**Checklist:**
1. ✅ All linters pass (flake8, eslint, golangci-lint, ansible-lint, etc.)
2. ✅ Security scans clean (gosec, bandit, npm audit, Trivy)
3. ✅ No secrets in code
4. ✅ Smoke tests pass (build, run, API, UI)
5. ✅ Full test suite passes
6. ✅ Version updated if needed
7. ✅ Docker builds successful (debian-slim base)

**Only commit when explicitly asked** — run pre-commit script, verify all checks pass, then wait for approval.

📚 **Complete checklist**: [PRE_COMMIT.md](PRE_COMMIT.md)

## File Size Limits

- **Maximum file size**: 25,000 characters for ALL code and markdown files
- **CLAUDE.md exception**: Maximum 39,000 characters (only exception)
- **Split large files**: Use modules, libraries, or separate documents
- **Documentation strategy**: Detailed docs in `docs/` folder, high-level context in CLAUDE.md

## Application-Specific Standards

**⚠️ IMPORTANT**: Application-specific standards, architectural decisions, requirements, and context belong in:

📚 **[docs/APP_STANDARDS.md](APP_STANDARDS.md)**

This includes:
- Application-specific architecture patterns
- Custom authentication/authorization rules
- Business logic requirements
- Domain-specific data models
- Integration requirements unique to your app
- Performance characteristics specific to your use case
- Custom API endpoints and contracts
- Application-specific security requirements

The separation between company-wide standards (this document) and app-specific standards (APP_STANDARDS.md) ensures:
- Template standards can be updated across all projects
- Application-specific context is preserved
- Clear separation of concerns
- Easier maintenance and updates

---

## Complete Standards Documentation

For comprehensive details on each category, refer to the individual standards documents in the `docs/standards/` directory:

- **[Language Selection Criteria](standards/LANGUAGE_SELECTION.md)** - Python vs Go decision matrix
- **[Authentication Standards](standards/AUTHENTICATION.md)** - Flask-Security-Too, RBAC, SSO, password reset
- **[Frontend Development Standards](standards/FRONTEND.md)** - ReactJS patterns and best practices
- **[Database Standards](standards/DATABASE.md)** - PyDAL, multi-database support, migrations
- **[API and Protocol Standards](standards/API_PROTOCOLS.md)** - REST, gRPC, versioning, deprecation
- **[Performance Standards](standards/PERFORMANCE.md)** - Optimization, concurrency, high-performance networking
- **[Architecture Standards](standards/ARCHITECTURE.md)** - Microservices, Docker, containerization
- **[Kubernetes Standards](standards/KUBERNETES.md)** - Helm, Kustomize, K8s deployments, best practices
- **[Testing Standards](standards/TESTING.md)** - Unit, integration, E2E, smoke, performance tests
- **[Security Standards](standards/SECURITY.md)** - TLS, secrets, scanning, vulnerability management
- **[Documentation Standards](standards/DOCUMENTATION.md)** - README, docs structure, release notes
- **[Web UI Design Standards](standards/UI_DESIGN.md)** - Design patterns, components, styling
- **[Integration Standards](standards/INTEGRATIONS.md)** - WaddleAI, MarchProxy, License Server

---

**Template Version**: 1.3.0
**Last Updated**: 2026-01-13
**Maintained by**: Penguin Tech Inc
