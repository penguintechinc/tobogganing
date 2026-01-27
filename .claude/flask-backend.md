# Flask Backend Service Standards

## ⚠️ CRITICAL RULES

1. **Flask + Flask-Security-Too**: MANDATORY authentication for ALL Flask applications
2. **PyDAL for Runtime**: ALL runtime database queries MUST use PyDAL (SQLAlchemy only for schema)
3. **REST API Versioning**: `/api/v{major}/endpoint` format is REQUIRED
4. **JWT Authentication**: Default for API requests with RBAC using scopes
5. **Multi-Database Support**: PostgreSQL, MySQL, MariaDB Galera, SQLite ALL required

## Authentication & Authorization

### Flask-Security-Too Setup

- Mandatory for user authentication and session management
- Provides RBAC, password hashing (bcrypt), email confirmation, 2FA
- Integrates with PyDAL datastore for user/role management
- Create default admin on startup: `admin@localhost.local` / `admin123`

### Role-Based Access Control

**Global Roles (Default):**
- **Admin**: Full system access
- **Maintainer**: Read/write, no user management
- **Viewer**: Read-only access

**Team Roles (Team-scoped):**
- **Owner**: Full team control
- **Admin**: Manage members and settings
- **Member**: Normal access
- **Viewer**: Read-only team access

### JWT & OAuth2 Scopes

- Use JWT for stateless API authentication
- Implement scope-based permissions: `read`, `write`, `admin`
- Combine with roles for fine-grained access control
- SSO (SAML/OAuth2): License-gate as enterprise feature

## Database Standards

### Dual-Library Architecture

**SQLAlchemy**: Schema definition and migrations only
- Define models for table structure
- Run Alembic migrations for schema changes
- NOT used for runtime queries

**PyDAL**: All runtime database operations
- Connection pooling with configurable pool size
- Thread-safe per-thread or per-request instances
- Define tables matching SQLAlchemy schema
- Automatic migrations enabled: `migrate=True`

### Database Support

- **PostgreSQL** (default): Primary production database
- **MySQL**: Full support for MySQL 8.0+
- **MariaDB Galera**: Cluster support with WSREP handling
- **SQLite**: Development and lightweight deployments

Use environment variables: `DB_TYPE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_POOL_SIZE`

### Connection Management

- Wait for database readiness on startup with retry logic
- Connection pooling: `pool_size = (2 * CPU_cores) + disk_spindles`
- Thread-local storage for multi-threaded contexts
- Proper lifecycle management and connection cleanup

## API Design

### REST API Structure

- Format: `/api/v{major}/endpoint`
- Support HTTP/1.1 minimum, HTTP/2 preferred
- Resource-based design with proper HTTP methods
- JSON request/response format
- Proper HTTP status codes (200, 201, 400, 404, 500)

### Version Management

- **Current**: Active development, fully supported
- **N-1**: Bug fixes and security patches
- **N-2**: Critical security patches only
- **N-3+**: Deprecated with warning headers
- Maintain minimum 12-month deprecation timeline

### Response Format

Include metadata in all responses:
```json
{
  "status": "success",
  "data": {...},
  "meta": {
    "version": 2,
    "timestamp": "2025-01-22T00:00:00Z"
  }
}
```

## Password Management

### Features Required

- **Change Password**: Always available in user profile (no SMTP needed)
- **Forgot Password**: Requires SMTP configuration
- Token expiration: Default 1 hour
- Password reset via email with time-limited tokens
- New password must differ from current

### Configuration

```bash
SECURITY_RECOVERABLE=true
SECURITY_RESET_PASSWORD_WITHIN=1 hour
SECURITY_CHANGEABLE=true
SECURITY_SEND_PASSWORD_RESET_EMAIL=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
```

## Login Page Standards

1. **Logo**: 300px height, placed above form
2. **NO Default Credentials**: Never display or pre-fill credentials
3. **Form Elements**: Email, password (masked), remember me, forgot password link
4. **SSO Buttons**: Optional if enterprise features enabled
5. **Mobile Responsive**: Scale logo down on mobile (<768px)

## Development Best Practices

- No hardcoded secrets or credentials
- Input validation mandatory on all endpoints
- Proper error handling with informative messages
- Logging and monitoring in place
- Security scanning before commit (bandit, safety check)
- Code must pass linting (flake8, black, isort, mypy)

## License Gating

- SSO features: Enterprise-only via license server
- Check feature entitlements: `license_client.has_feature()`
- Graceful degradation when features unavailable
- Reference: docs/licensing/license-server-integration.md
