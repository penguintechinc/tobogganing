# Documentation Standards

Part of [Development Standards](../STANDARDS.md)

## README.md Standards

**ALWAYS include build status badges:**
- CI/CD pipeline status (GitHub Actions)
- Test coverage status (Codecov)
- Go Report Card (for Go projects)
- Version badge
- License badge (Limited AGPL3)

**ALWAYS include catchy ASCII art** below badges

**Company homepage**: Point to **www.penguintech.io**

**Quick Start Section - DEFAULT CREDENTIALS DOCUMENTATION:**

The README.md MUST include a Quick Start section documenting default credentials for development:

```markdown
## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Development Environment

Start all services:
```bash
make dev
```

Access the application at `http://localhost:3000`

**Default Development Credentials:**
- **Email**: `admin@localhost.local`
- **Password**: `admin123`

⚠️ **IMPORTANT**: Change these credentials in production. The default admin user is automatically created on first startup.

### Login
1. Navigate to `http://localhost:3000`
2. Enter default email: `admin@localhost.local`
3. Enter default password: `admin123`
4. Click Login

### Change Default Password
After first login, immediately change the admin password in Settings → Security.

### Production Deployment
See [Deployment Guide](docs/DEPLOYMENT.md) for production setup without default credentials.
```

**Key Points:**
- Default credentials MUST be documented in README Quick Start
- Default credentials MUST NOT be displayed on the login page itself
- Clearly mark credentials as for development only
- Warn about changing passwords in production
- Link to production deployment guide

## CLAUDE.md File Management

- **Maximum**: 35,000 characters
- **High-level approach**: Reference detailed docs
- **Documentation strategy**: Create detailed docs in `docs/` folder
- **Keep focused**: Critical context and workflow instructions only

## API Documentation

- Comprehensive endpoint documentation
- Request/response examples
- Error codes and handling
- Authentication requirements
- Rate limiting information

## Architecture Documentation

- System architecture diagrams
- Component interaction patterns
- Data flow documentation
- Decision records (ADRs)
