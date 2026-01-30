# Development Standards

Welcome to the Penguin Tech standards hub! 🐧 This is your go-to resource for building awesome, production-ready software.

> 🚫 **DO NOT MODIFY** this file or any files in `docs/standards/`. These are centralized template standards that will be overwritten when updated. For app-specific documentation, use [`docs/APP_STANDARDS.md`](APP_STANDARDS.md) instead.

## Getting Started

Ready to build something great? Here's your quick-start checklist:

- Read your language selection criteria (Python vs Go)
- Set up Flask-Security-Too for authentication
- Pick your database (PostgreSQL recommended)
- Design your APIs with versioning in mind
- Run the pre-commit checks before pushing code
- Make sure your tests pass (especially smoke tests!)

## Standards by Category

Here's what you'll find in our comprehensive standards library:

| Icon | Category | Focus Area |
|------|----------|-----------|
| 🐍 | [Language Selection](standards/LANGUAGE_SELECTION.md) | Python 3.13 or Go 1.24.x? We'll help you decide |
| 🔐 | [Authentication](standards/AUTHENTICATION.md) | Flask-Security-Too, RBAC, SSO, password magic |
| ⚛️ | [Frontend](standards/FRONTEND.md) | ReactJS patterns, hooks, components galore |
| 📦 | [React Libraries](standards/REACT_LIBS.md) | Shared components: LoginPageBuilder, FormModal, Sidebar |
| 🗄️ | [Database](standards/DATABASE.md) | PyDAL, SQLAlchemy, PostgreSQL + 3 others |
| 🔌 | [API & Protocols](standards/API_PROTOCOLS.md) | REST, gRPC, versioning, deprecation strategies |
| ⚡ | [Performance](standards/PERFORMANCE.md) | Dataclasses, asyncio, threading, blazing fast |
| 🏗️ | [Architecture](standards/ARCHITECTURE.md) | Microservices, Docker, multi-arch builds |
| ☸️ | [Kubernetes](standards/KUBERNETES.md) | Helm, Kustomize, cloud-native deployments |
| 🧪 | [Testing](standards/TESTING.md) | Unit, integration, E2E, smoke tests |
| 🛡️ | [Security](standards/SECURITY.md) | TLS, secrets management, vulnerability scanning |
| 📚 | [Documentation](standards/DOCUMENTATION.md) | READMEs, release notes, keeping it clean |
| 🎨 | [UI Design](standards/UI_DESIGN.md) | Components, patterns, responsive design |
| 📱 | [Mobile](standards/MOBILE.md) | Flutter, native modules, phone + tablet support |
| 🔗 | [Integrations](standards/INTEGRATIONS.md) | WaddleAI, MarchProxy, License Server |

## The Core Five (Most Important)

### 1. Language Selection: Python or Go?
Start with Python 3.13 for most applications. Go is for speed demons only (>10K req/sec). Profile first, switch only when you really need to.

> **Pro tip**: 9 out of 10 times, Python will do the job beautifully and get you to market faster.

[Learn more](standards/LANGUAGE_SELECTION.md)

### 2. Authentication: Flask-Security-Too
All Flask apps get security out of the box. RBAC, JWT, password reset, 2FA, even SSO for enterprise customers. Auto-creates an admin user on startup (credentials: admin@localhost.local / admin123).

> **Remember**: Never skip security. It's not "nice to have" - it's required.

[Learn more](standards/AUTHENTICATION.md)

### 3. Database: Multi-DB Support by Default
Use PyDAL for runtime operations (required) and SQLAlchemy for schema creation. We support PostgreSQL (your default), MySQL, MariaDB Galera, and SQLite. Choose via the `DB_TYPE` environment variable.

> **Key insight**: Pick PostgreSQL unless you have a specific reason not to. It's rock solid.

[Learn more](standards/DATABASE.md)

### 4. API Design: Version Everything
All REST APIs use `/api/v{major}/endpoint`. Inter-container communication prefers gRPC. Support at least 2 previous versions (current + 2 prior). Plan for deprecation from day one.

> **Best practice**: Design APIs for extensibility. Small, flexible inputs. Backward-compatible responses.

[Learn more](standards/API_PROTOCOLS.md)

### 5. Testing: Smoke Tests Are Non-Negotiable
Run smoke tests before every commit. They verify your build works, services start, APIs respond, and the UI loads. Five minutes of testing saves you hours of debugging later.

> **Golden rule**: If smoke tests pass, you can commit with confidence.

[Learn more](standards/TESTING.md)

## Pre-Commit Checklist

Before you commit, run this magic command:

```bash
./scripts/pre-commit/pre-commit.sh
```

Here's what it checks:

- [ ] Linters pass (flake8, eslint, golangci-lint, ansible-lint)
- [ ] Security scans are clean (gosec, bandit, npm audit, Trivy)
- [ ] No secrets leaked into code
- [ ] Smoke tests pass (build, run, API, UI loads)
- [ ] Full test suite passes
- [ ] Version updated if needed
- [ ] Docker builds successfully with debian-slim

> **Important**: Only commit when explicitly asked. Run this script, verify everything passes, then request approval. No shortcuts!

[Full pre-commit guide](PRE_COMMIT.md)

## Keep It Clean: File Size Limits

Files have limits for a reason (keeps things maintainable and fast):

- **Code and markdown**: Max 25,000 characters
- **CLAUDE.md**: Max 39,000 characters (only exception)
- **When you hit the limit**: Split into modules, separate documents, or a new file
- **Documentation strategy**: Detailed docs live in `docs/`, high-level context in CLAUDE.md

## App-Specific Standards

This document covers company-wide best practices. Your app is unique, so app-specific stuff goes in [`docs/APP_STANDARDS.md`](APP_STANDARDS.md):

- Custom architecture patterns
- Business logic requirements
- Domain-specific data models
- App-specific security rules
- Integration requirements unique to you
- Custom API endpoints
- Performance needs specific to your use case

> **Why split them?** So we can update template standards across all projects without losing your app-specific context. Everyone wins!

---

## Need More Details?

Dive into the individual standards documents for the full picture:

- [Language Selection](standards/LANGUAGE_SELECTION.md) - Python vs Go decision matrix
- [Authentication](standards/AUTHENTICATION.md) - Flask-Security-Too, RBAC, SSO
- [Frontend Development](standards/FRONTEND.md) - ReactJS patterns and best practices
- [React Libraries](standards/REACT_LIBS.md) - Shared components (LoginPageBuilder, FormModal, Sidebar)
- [Database Standards](standards/DATABASE.md) - PyDAL, multi-database support
- [API and Protocols](standards/API_PROTOCOLS.md) - REST, gRPC, versioning
- [Performance](standards/PERFORMANCE.md) - Optimization, concurrency, speed
- [Architecture](standards/ARCHITECTURE.md) - Microservices, Docker
- [Kubernetes](standards/KUBERNETES.md) - Helm, Kustomize, deployments
- [Testing](standards/TESTING.md) - Unit, integration, E2E, smoke tests
- [Security](standards/SECURITY.md) - TLS, secrets, scanning
- [Documentation](standards/DOCUMENTATION.md) - READMEs, release notes
- [UI Design](standards/UI_DESIGN.md) - Components, patterns, styling
- [Mobile](standards/MOBILE.md) - Flutter, native modules, iOS + Android, phone + tablet
- [Integrations](standards/INTEGRATIONS.md) - WaddleAI, MarchProxy, License Server

---

**Happy coding!** These standards exist to help you build reliable, secure, performant software. Questions? Check the docs. Still stuck? Ping your team!

**Template Version**: 1.3.0 | **Last Updated**: 2026-01-22 | **Maintained by**: Penguin Tech Inc
