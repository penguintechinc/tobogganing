# Security Standards - Keeping Your App Safe

Part of [Development Standards](../STANDARDS.md)

Security isn't about being paranoid—it's about making smart choices so your users can trust you. This guide walks through common threats and how we defend against them.

## Common Vulnerabilities (The Cautionary Tales)

### The SQL Injection Attack
**The danger:** A bad actor sneaks SQL code into a form field, tricking your database into doing things you never intended.

**Example of bad code:**
```python
# DON'T DO THIS!
query = f"SELECT * FROM users WHERE username = '{user_input}'"
```

Someone types: `' OR '1'='1` → Suddenly they can see all users!

**How we protect:** Use parameterized queries with PyDAL (never concatenate user input):
```python
# DO THIS!
users = db((db.users.username == user_input)).select()
```

PyDAL automatically sanitizes inputs. Safe and simple.

### Cross-Site Scripting (XSS) - The Script Injection
**The danger:** Attackers inject JavaScript that runs in other users' browsers.

**Bad code:**
```python
# DON'T DO THIS!
return f"<div>{user_comment}</div>"  # User could add: <script>steal_cookies()</script>
```

**How we protect:**
- Always escape user content before displaying: `{{ user_comment | escape }}`
- Use modern frameworks (React) that escape by default
- Never use `dangerouslySetInnerHTML` unless you really know what you're doing

### CSRF (Cross-Site Request Forgery) - The Invisible Button Click
**The danger:** A malicious site tricks your user into performing actions on your app without realizing it.

**How we protect:** Flask handles this with CSRF tokens automatically. Every form submission validates that the request actually came from your app, not some attacker's website.

## Secrets Management - Where Passwords Live

Never hardcode secrets. Never. Ever.

**Safe approach:**
```python
import os

# Read from environment variables
DATABASE_URL = os.getenv('DATABASE_URL')
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')

# Development: Use .env file (add to .gitignore!)
# Production: Set via container environment or secrets manager
```

**Files to keep OUT of git:**
- `.env` - Local development secrets
- `.env.local` - Any user-specific overrides
- `credentials.json` - Service account keys
- `*.key` - Private keys

These belong in `.gitignore` and should be managed by your CI/CD system or secrets vault.

## Authentication & Authorization

### Three-Tier Role System

**Global Level** (organization-wide):
- **Admin**: Full access everywhere, manage users
- **Maintainer**: Read/write on resources, no user management
- **Viewer**: Read-only access

**Container/Team Level** (per service):
- **Team Admin**: Full access within this team
- **Team Maintainer**: Read/write for this team
- **Team Viewer**: Read-only for this team

**Resource Level** (specific items):
- **Owner**: Full control
- **Editor**: Can read and modify
- **Viewer**: Can only read

### OAuth2-Style Scopes (Granular Permissions)

Think of scopes like keys to different rooms in your building:

```python
# Available scopes
SCOPES = {
    'users:read': 'View user list',
    'users:write': 'Create/update users',
    'users:admin': 'Delete users, change roles',
    'reports:read': 'View reports',
    'reports:write': 'Create/edit reports',
}

# Admin has all keys, Viewer only has read keys
ROLE_SCOPES = {
    'admin': ['users:read', 'users:write', 'users:admin', 'reports:read', 'reports:write'],
    'viewer': ['users:read', 'reports:read'],
}
```

**Implementation:**
```python
from functools import wraps
from flask import request

def require_scope(*required_scopes):
    """Only allow users with specific scopes"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = request.user  # Set by auth middleware
            user_scopes = user.get_scopes()

            if not any(scope in user_scopes for scope in required_scopes):
                return {'error': 'Insufficient permissions'}, 403

            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/api/v1/users', methods=['GET'])
@require_scope('users:read')
def list_users():
    """Only people with 'users:read' can see this"""
    users = db.users.select().fetchall()
    return jsonify({'data': users})
```

**JWT tokens carry scopes:**
```python
import jwt

def create_access_token(user, scopes):
    payload = {
        'sub': user.id,
        'email': user.email,
        'scopes': scopes,  # Include the actual permissions
        'exp': datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')
```

### API Client Scopes

Third-party apps and service accounts get scopes too:

```python
@app.route('/api/v1/clients', methods=['POST'])
@require_scope('users:admin')
def create_api_client():
    """Generate API key with limited permissions"""
    data = request.get_json()
    api_key = generate_secure_key()

    client = {
        'name': data.get('name'),
        'api_key_hash': hash_api_key(api_key),
        'scopes': data.get('scopes', []),  # Limited permissions
    }
    db.api_clients.insert(**client)
    return {'api_key': api_key}  # Only shown once!
```

### Session & Token Security

- JWT tokens expire (1 hour for access, refresh tokens for long-lived access)
- Secure cookies with `HttpOnly`, `Secure`, `SameSite=Strict` flags
- Multi-factor authentication support (2FA codes, biometric, U2F keys)
- Passwords hashed with bcrypt (Flask-Security-Too handles this)

## Encryption & TLS

**What to enforce:**
- **TLS 1.2 minimum** (TLS 1.3 preferred) for all external connections
- HTTPS everywhere—no plain HTTP in production
- HTTP/3 (QUIC) for high-performance scenarios (optional, newer feature)

**Why it matters:** TLS encrypts data in transit, preventing eavesdropping. HTTPS with a valid certificate proves your app is actually your app.

## Input Validation - Trust No One

Every input is potentially dangerous. Validate everything:

```python
from wtforms import StringField, validators

class UserForm:
    email = StringField('Email', [
        validators.Email(),  # Valid email format
        validators.Length(min=5, max=120),
    ])
    username = StringField('Username', [
        validators.Length(min=3, max=20),
        validators.Regexp(r'^[a-zA-Z0-9_]+$'),  # Only alphanumeric + underscore
    ])
    age = IntegerField('Age', [
        validators.NumberRange(min=13, max=120),  # Sensible range
    ])
```

**Server-side always:** Client-side validation is nice for UX, but never trust it. Always validate on the server where attackers can't bypass it.

## Security Scanning Tools

Run these regularly (especially before commits):

### Python Security
```bash
# Check dependencies for known vulnerabilities
pip install safety bandit
safety check                    # CVE database check
bandit -r .                    # Find security issues in code
bandit -r services/flask-backend/
```

### Node.js Security
```bash
# Built-in npm auditing
npm audit                      # List vulnerabilities
npm audit fix                  # Auto-fix what can be fixed
```

### Go Security
```bash
# Install gosec
go install github.com/securego/gosec/v2/cmd/gosec@latest
gosec ./...                    # Scan all packages
```

### General - Dependency Monitoring
- **Dependabot**: GitHub automatically checks for outdated packages (enabled by default)
- **Socket.dev**: Advanced threat detection for supply chain attacks
- Check both before committing dependency updates!

## Pre-Deploy Security Checklist

Before every commit and deploy:

- [ ] Run `npm audit` / `safety check` / `gosec` - no vulnerabilities
- [ ] No hardcoded secrets (passwords, API keys, tokens) in code
- [ ] SQL injection protection: Using parameterized queries, not string concatenation
- [ ] XSS protection: User content escaped before display
- [ ] CSRF tokens enabled on all state-changing endpoints
- [ ] Input validation on all endpoints
- [ ] Authentication required for protected endpoints
- [ ] Authorization checked with appropriate scopes/roles
- [ ] TLS enabled for all external communication
- [ ] Passwords hashed (bcrypt, not plaintext)
- [ ] API keys hidden (environment variables, not hardcoded)
- [ ] Error messages don't leak sensitive info (no "user admin@company.com not found")
- [ ] Logs don't contain passwords or secrets
- [ ] Dependencies updated to patched versions

## Found a Vulnerability?

**If you discover a security issue:**

1. **Don't panic** - You found it, that's good!
2. **Don't broadcast it** - Don't post on public channels
3. **Report privately**: Email `security@penguintech.io` with:
   - What you found
   - How to reproduce it
   - What impact it could have
4. **Give us time** - We'll acknowledge within 24 hours, fix ASAP
5. **Coordination** - We'll credit you in security advisories (if you want)

## Learn More

- [OWASP Top 10](https://owasp.org/www-project-top-ten/) - The most critical web security risks
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework) - Industry standards
- [Flask-Security-Too Docs](https://flask-security-too.readthedocs.io/) - Our auth framework
- [PyDAL Security](https://py4web.io/chapter-13#security) - Database protection
- [SQLAlchemy Security](https://docs.sqlalchemy.org/en/14/faq/security.html) - ORM safety
