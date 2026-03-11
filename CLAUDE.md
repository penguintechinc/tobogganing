# Project Template - Claude Code Context

## 🚫 DO NOT MODIFY THIS FILE OR `.claude/` STANDARDS

**These are centralized template files that will be overwritten when standards are updated.**

- ❌ **NEVER edit** `CLAUDE.md`, `.claude/*.md`, `docs/STANDARDS.md`, or `docs/standards/*.md`
- ✅ **CREATE NEW FILES** for app-specific context:
  - `docs/APP_STANDARDS.md` - App-specific architecture, requirements, context
  - `.claude/{subject}.local.md` - Project-specific overrides (e.g., `architecture.local.md`, `python.local.md`)

**App-Specific Addendums to Standardized Files:**

If your app needs to add exceptions, clarifications, or context to standardized `.claude/` files (e.g., `react.md`, `python.md`, `testing.md`), **DO NOT edit those files**. Instead, create a `.local` variant:

- `react.md` (standardized) → Create `react.local.md` for app-specific React patterns
- `python.md` (standardized) → Create `python.local.md` for app-specific Python decisions
- `testing.md` (standardized) → Create `testing.local.md` for app-specific test requirements
- `security.md` (standardized) → Create `security.local.md` for app-specific security rules

**Example `.local` file structure:**
```markdown
# React (App-Specific Addendums)

## Additional Requirements for [ProjectName]
- Custom build process for feature X
- Performance constraints for Y
- Team-specific patterns for Z
```

This keeps standardized files clean while allowing each app to extend them without conflicts. Local addendums will NOT be overwritten by standard updates.

**Local Repository Overrides:**

This repository may contain `.local.md` variant files that provide project-specific overrides or addendums:
- `CLAUDE.local.md` - Project-specific additions or clarifications to this CLAUDE.md
- `.claude/*.local.md` - Project-specific overrides to standardized `.claude/` rules

**Always check for and read `.local.md` files** alongside standard files to ensure you have the complete context for this specific repository.

---

## MCP Servers

- **mem0**: Persistent memory across sessions. At the start of each session, `search_memories` for relevant context before asking the user to re-explain anything. Use `add_memory` whenever you discover project architecture, coding conventions, debugging insights, key decisions, or user preferences. Use `update_memory` when prior context changes. Save information like: "This project uses PostgreSQL with Prisma", "Tests run with pytest -v", "Auth uses JWT validated in middleware". When in doubt, save it, future sessions benefit from over-remembering.

---

## ⚠️ CRITICAL RULES - READ FIRST

**Git Rules:**
- **NEVER commit** unless explicitly requested
- **NEVER push** to remote repositories - only push when explicitly asked
- **NEVER ask about pushing** - do not suggest or prompt for git push operations
- **NEVER edit code directly on `main`** — always work on a feature branch
- **CHECK current branch before any code change**: if on `main`, create and switch to a feature branch first (`git checkout -b feature/<name>`)
- Run security scans before commit

**Code Quality:**
- ALL code must pass linting before commit
- No hardcoded secrets or credentials
- Input validation mandatory
- **NEVER ignore pre-existing issues** — if you encounter existing bugs, failing tests, lint errors, TODOs marked as broken, or code that violates standards while working on an unrelated task, **fix them or explicitly flag them to the user**. Do not silently work around them or pretend they are not there. Leaving known issues in place is not acceptable

**Tool Usage:**
- **NEVER use `sed`, `awk`, `cat`, `head`, `tail`, `echo`, `grep`, `find`, or `rg` via Bash** when a dedicated tool exists — use the dedicated tools instead:
  - Read files → **Read** tool (not `cat`, `head`, `tail`)
  - Edit files → **Edit** tool (not `sed`, `awk`)
  - Write/create files → **Write** tool (not `echo >`, `cat <<EOF`)
  - Search file contents → **Grep** tool (not `grep`, `rg`)
  - Find files by name → **Glob** tool (not `find`, `ls`)
- Only fall back to Bash for these commands when the dedicated tool genuinely cannot accomplish the task (e.g., piped shell pipelines, complex transformations)
- This reduces unnecessary approval prompts and keeps operations auditable

📚 **Complete Technical Standards**: See [`.claude/`](.claude/) directory for all language-specific, database, architecture, container image, Kubernetes, and development standards.

📚 **Orchestration Model Rules**: See [`.claude/orchestration.md`](.claude/orchestration.md) for complete orchestration details — main model role (planning, delegating, validating), task agent model selection (Haiku vs Sonnet), output requirements, and concurrency limits.

📚 **Testing Standards**: See [`.claude/testing.md`](.claude/testing.md) for complete testing framework — Test Controller CLI, test categories (build, unit, integration, functional, e2e, security, api, performance), smoke test designations, per-container requirements, and test execution order.

---

**⚠️ Important**: Application-specific context should be added to `docs/APP_STANDARDS.md` instead of this file. This allows the template CLAUDE.md to be updated across all projects without losing app-specific information. See `docs/APP_STANDARDS.md` for app-specific architecture, requirements, and context.

## Project Overview

This is a comprehensive project template incorporating best practices and patterns from Penguin Tech Inc projects. It provides a standardized foundation for multi-language projects with enterprise-grade infrastructure and integrated licensing.

**Template Features:**
- Multi-language support with consistent standards
- Enterprise security and licensing integration
- Comprehensive CI/CD pipeline
- Production-ready containerization
- Monitoring and observability
- Version management system
- PenguinTech License Server integration

📚 **Technology Stack & Standards**: See [`.claude/technology.md`](.claude/technology.md) for complete language selection, framework, infrastructure, database, security, API design, performance optimization, and container standards.

📚 **License Server Integration**: See [`.claude/licensing.md`](.claude/licensing.md) for PenguinTech License Server integration details, including license key format, endpoints, environment variables, and release-mode activation.

📚 **WaddleAI Integration**: See [`.claude/waddleai-integration.md`](.claude/waddleai-integration.md) for AI capabilities integration, including when to use WaddleAI, service communication patterns, license gating, and Docker Compose setup.

## Project Structure

```
project-name/
├── .github/             # CI/CD pipelines and templates
│   └── workflows/       # GitHub Actions workflows
├── services/            # Microservices (separate containers by default)
│   ├── backend-api/     # API backend service
│   ├── high-perf/       # High-performance service (optional)
│   ├── frontend/        # Frontend service
│   └── connector/       # Integration services (placeholder)
├── shared/              # Shared components
├── infrastructure/      # Infrastructure as code
├── scripts/             # Utility scripts
├── tests/               # Test suites (unit, integration, e2e, performance, smoke)
│   ├── smoke/           # Smoke tests (build, run, API, page loads)
│   ├── api/             # API tests
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── e2e/             # End-to-end tests
├── docs/                # Documentation
├── config/              # Configuration files
├── docker-compose.yml   # Production environment
├── docker-compose.dev.yml # Local development
├── Makefile             # Build automation
├── .version             # Version tracking
└── CLAUDE.md            # This file
```

**Default Roles**: Admin (full access), Maintainer (read/write, no user mgmt), Viewer (read-only)
**Team Roles**: Owner, Admin, Member, Viewer (team-scoped permissions)

📚 **Architecture diagram and details**: See [`.claude/technology.md`](.claude/technology.md) and [Architecture Standards](docs/standards/ARCHITECTURE.md)

## Version Management System

**Format**: `vMajor.Minor.Patch.build`
- **Major**: Breaking changes, API changes, removed features
- **Minor**: Significant new features and functionality additions
- **Patch**: Minor updates, bug fixes, security patches
- **Build**: Epoch64 timestamp of build time

### ⚠️ Version Increment Rule

**Only increment Major/Minor/Patch when the current version already has a published git tag and/or GitHub release.** If no tag/release exists for the current version yet, update only the build epoch.

**Rationale:** Incrementing a version before the current one ships creates gaps in the published sequence (e.g., `v1.2.1` → `v1.2.4` with no `v1.2.2` or `v1.2.3` ever released). Consumers, changelogs, and package managers see these gaps as missing releases, which is confusing and looks like a mistake.

**Decision flow:**
1. Check if the current `.version` is already tagged: `git tag --list "$(cat .version | cut -d. -f1-3)*"`
2. If **no tag exists** → only update the build epoch: `./scripts/version/update-version.sh`
3. If **a tag already exists** → safe to increment: `./scripts/version/update-version.sh patch|minor|major`

**Update Commands**:
```bash
./scripts/version/update-version.sh          # Update build epoch ONLY (use when no tag yet)
./scripts/version/update-version.sh patch    # Increment patch (only after current version is tagged)
./scripts/version/update-version.sh minor    # Increment minor (only after current version is tagged)
./scripts/version/update-version.sh major    # Increment major (only after current version is tagged)
```

## Development Workflow

### Quick Start

```bash
git clone <repository-url>
cd project-name
make setup                    # Install dependencies
make dev                      # Start development environment
make seed-mock-data          # Populate with 3-4 test items per feature
```

### Essential Documentation (Complete for Your Project)

Before starting development on this template, projects MUST complete and maintain these three critical documentation files:

**📚 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - LOCAL DEVELOPMENT SETUP GUIDE
- Prerequisites and installation for your tech stack
- Environment configuration specifics
- Starting your services locally
- Development workflow with mock data injection
- Common developer tasks and troubleshooting
- Tips for your specific architecture

**📚 [docs/TESTING.md](docs/TESTING.md)** - TESTING & VALIDATION GUIDE
- Mock data scripts (3-4 items per feature pattern)
- Smoke tests (mandatory verification)
- Unit, integration, and E2E testing
- Performance testing procedures
- Cross-architecture testing with QEMU
- Pre-commit test execution order

**📚 [docs/PRE_COMMIT.md](docs/PRE_COMMIT.md)** - PRE-COMMIT CHECKLIST
- Required steps before every git commit
- Smoke tests (mandatory, <2 min)
- Mock data seeding for feature testing
- Screenshot capture with realistic data
- Security scanning requirements
- Build and test verification steps

**🔄 Workflow**: DEVELOPMENT.md → TESTING.md → PRE_COMMIT.md (integrated flow)
- Developers follow DEVELOPMENT.md to set up locally
- Reference TESTING.md for testing patterns and mock data
- Run PRE_COMMIT.md checklist before commits (includes smoke tests + screenshots)

### Essential Commands
```bash
# Development
make dev                      # Start development services
make test                     # Run all tests
make lint                     # Run linting
make build                    # Build all services
make clean                    # Clean build artifacts

# Production
make docker-build             # Build containers
make docker-push              # Push to registry
make deploy-dev               # Deploy to development
make deploy-prod              # Deploy to production

# Testing (see .claude/testing.md for full framework)
./scripts/test-controller.sh <type> [container]  # Unified test entry point
make test-unit               # Run unit tests
make test-integration        # Run integration tests
make test-e2e                # Run end-to-end tests
make test-functional         # Run functional tests (APIs, pages, tabs, modals, buttons)
make test-security           # Run security tests (gosec, bandit, npm audit, trivy)
make smoke-test              # Run smoke tests (curated subset, <2 min, pre-commit)

# License Management
make license-validate        # Validate license
make license-check-features  # Check available features
```

📚 **Critical Development Rules**: See [`.claude/development-rules.md`](.claude/development-rules.md) for complete development philosophy, red flags, quality checklist, security requirements, linting standards, and build deployment rules.

### Documentation Standards
- **README.md**: Keep as overview and pointer to comprehensive docs/ folder
- **docs/ folder**: Create comprehensive documentation for all aspects
- **RELEASE_NOTES.md**: Maintain in docs/ folder, prepend new version releases to top
- Update CLAUDE.md when adding significant context
- **Build status badges**: Always include in README.md
- **ASCII art**: Include catchy, project-appropriate ASCII art in README
- **Company homepage**: Point to www.penguintech.io
- **License**: All projects use Limited AGPL3 with preamble for fair use

### File Size Limits
- **Maximum file size**: 25,000 characters for ALL code and markdown files
- **Split large files**: Decompose into modules, libraries, or separate documents
- **CLAUDE.md exception**: Maximum 39,000 characters (only exception to 25K rule)
- **High-level approach**: CLAUDE.md contains high-level context and references detailed docs
- **Documentation strategy**: Create detailed documentation in `docs/` folder and link to them from CLAUDE.md
- **Keep focused**: Critical context, architectural decisions, and workflow instructions only
- **User approval required**: ALWAYS ask user permission before splitting CLAUDE.md files
- **Use Task Agents**: Utilize task agents (subagents) to be more expedient and efficient when making changes to large files, updating or reviewing multiple files, or performing complex multi-step operations

📚 **Task Agent Orchestration**: See [`.claude/orchestration.md`](.claude/orchestration.md) for complete details on orchestration model, task agent selection, response requirements, and concurrency limits.

## Development Standards

**⚠️ Documentation Structure:**
- **Company-wide standards**: [docs/STANDARDS.md](docs/STANDARDS.md) (index) + [docs/standards/](docs/standards/) (detailed categories)
- **App-specific standards**: [docs/APP_STANDARDS.md](docs/APP_STANDARDS.md) (application-specific architecture, requirements, context)

Comprehensive development standards are organized by category in `docs/standards/` directory. The main STANDARDS.md serves as an index with quick reference.

📚 **Complete Standards Documentation**: [Development Standards](docs/STANDARDS.md) | [Technology Stack](`.claude/technology.md`) | [Development Rules](`.claude/development-rules.md`) | [Git Workflow](`.claude/git-workflow.md`)

📚 **Application Architecture**: See [`.claude/technology.md`](.claude/technology.md) for microservices architecture patterns and [Architecture Standards](docs/standards/ARCHITECTURE.md) for detailed architecture guidance.

📚 **Integration Patterns**: See [Standards Index](docs/STANDARDS.md) | [Authentication](docs/standards/AUTHENTICATION.md) | [Database](docs/standards/DATABASE.md) for complete code examples and integration patterns.

## Website Integration Requirements

**Required websites**: Marketing/Sales (Node.js) + Documentation (Markdown)

**Design**: Multi-page, modern aesthetic, subtle gradients, responsive, performance-focused

**Repository**: Sparse checkout submodule from `github.com/penguintechinc/website` with `{app_name}/` and `{app_name}-docs/` folders

## Troubleshooting & Support

**Common Issues**: Port conflicts, database connections, license validation, build failures, test failures

**Quick Debug**: `docker-compose logs -f <service>` | `make debug` | `make health`

**Support**: support@penguintech.io | sales@penguintech.io | https://status.penguintech.io

📚 **Detailed troubleshooting**: [Standards Index](docs/STANDARDS.md) | [License Guide](docs/licensing/license-server-integration.md)

## CI/CD & Workflows

**Build Tags**: `beta-<epoch64>` (main) | `alpha-<epoch64>` (other) | `vX.X.X-beta` (version release) | `vX.X.X` (tagged release)

**Version**: `.version` file in root, semver format, monitored by all workflows

**Deployment Hosts**:
- **Alpha/Local**: `https://{repo_name_lowercase}.localhost.local` (local K8s)
  - Deployed via Kustomize to `--context local-alpha`
- **Beta/Development**: `https://{repo_name_lowercase}.penguintech.cloud` (if online)
  - Example: `project-template` → `https://project-template.penguintech.cloud`
  - Deployed from `main` branch with `beta-*` tags
- **Production**: Either custom domain or PenguinCloud subdomain
  - **Custom Domain**: Application-specific (e.g., `https://waddlebot.io`)
  - **PenguinCloud**: `https://{repo_name_lowercase}.penguincloud.io`
  - Deployed from tagged releases (`vX.X.X`)

📚 **Git Workflow & Pre-Commit**: See [`.claude/git-workflow.md`](.claude/git-workflow.md) for complete pre-commit checklist, security scanning requirements, API testing, screenshot updates, smoke tests, and code change application procedures.

## Template Customization

**Adding Languages/Services**: Create in `services/`, add Dockerfile, update CI/CD, add linting/testing, update docs.

**Enterprise Integration**: License server, multi-tenancy, usage tracking, audit logging, monitoring.

📚 **Detailed customization guides**: [Standards Index](docs/STANDARDS.md)


## License & Legal

**License File**: `LICENSE.md` (located at project root)

**License Type**: Limited AGPL-3.0 with commercial use restrictions and Contributor Employer Exception

The `LICENSE.md` file is located at the project root following industry standards. This project uses a modified AGPL-3.0 license with additional exceptions for commercial use and special provisions for companies employing contributors.


---

**Template Version**: 1.3.0
**Last Updated**: 2025-12-03
**Maintained by**: Penguin Tech Inc
**License Server**: https://license.penguintech.io

**Key Updates in v1.3.0:**
- Three-container architecture: Flask backend, Go backend, WebUI shell
- WebUI shell with Node.js + React, role-based access (Admin, Maintainer, Viewer)
- Flask backend with PyDAL, JWT auth, user management
- Go backend with XDP/AF_XDP support, NUMA-aware memory pools
- GitHub Actions workflows for multi-arch builds (AMD64, ARM64)
- Gold text theme by default, Elder sidebar pattern, WaddlePerf tabs
- Docker Compose updated for new architecture

**Key Updates in v1.2.0:**
- Web UI and API as separate containers by default
- Mandatory linting for all languages (flake8, ansible-lint, eslint, etc.)
- CodeQL inspection compliance required
- Multi-database support by design (all PyDAL databases + MariaDB Galera)
- DB_TYPE environment variable with input validation
- Flask as sole web framework (PyDAL for database abstraction)

**Key Updates in v1.1.0:**
- Flask-Security-Too mandatory for authentication
- ReactJS as standard frontend framework
- Python 3.13 vs Go decision criteria
- XDP/AF_XDP guidance for high-performance networking
- WaddleAI integration patterns
- Release-mode license enforcement
- Performance optimization requirements (dataclasses with slots)

*This template provides a production-ready foundation for enterprise software development with comprehensive tooling, security, operational capabilities, and integrated licensing management.*
