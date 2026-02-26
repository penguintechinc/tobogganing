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

## Token & Secret Hygiene in Scripts and Shell

### The Shell History Leak (The Demo Disaster)

**The danger:** Tokens and passwords passed as command-line arguments are permanently written to `~/.bash_history` — and are visible to anyone on the same machine via `ps aux` while the process runs.

**Bad code:**
```bash
# DON'T DO THIS! The token lives in your shell history forever.
curl -H "Authorization: Bearer ghp_abc123XYZ" https://api.github.com/user
my-tool --api-key "sk-live-abc123" --action deploy

# Also bad: literal value in an export ends up in history too
export MY_TOKEN="sk-live-abc123"
```

**How we protect:** Read tokens from environment variables, files, or stdin — never type or interpolate literal values on the command line.

```bash
# ✅ Token already in the environment; nothing sensitive in history
curl -H "Authorization: Bearer $MY_TOKEN" https://api.github.com/user

# ✅ Tools that accept --password-stdin keep secrets out of the process list
echo "$DOCKER_TOKEN" | docker login --username "$DOCKER_USER" --password-stdin

# ✅ Silent interactive prompt (no echo, not stored in history)
read -rsp "API token: " MY_TOKEN && export MY_TOKEN
```

**In Python** — read from the environment, never from `sys.argv` or `argparse`:
```python
import os

# ✅ Never visible in shell history or process list
token = os.environ["MY_API_TOKEN"]

# ❌ DON'T DO THIS — shows up in `ps aux` and shell history
# parser.add_argument('--token')
```

**In Go** — same rule:
```go
// ✅ Read from environment
token := os.Getenv("MY_API_TOKEN")

// ❌ Don't accept secrets via flag.String or os.Args
```

### Don't Log Secrets

Even if a token never hits the command line, it can leak through logs:

```python
# ❌ Full token in logs — survives forever in log aggregators
logger.debug(f"Using token: {api_token}")

# ✅ Log only a masked representation
masked = f"{api_token[:4]}****{api_token[-4:]}"
logger.debug(f"Using token: {masked}")
```

**CI/CD pipelines:** Register secrets as masked variables in GitHub Actions / GitLab CI — the platform will automatically scrub them from all log output.

### Quick Checklist Before a Demo or Screen Share

- [ ] Tokens are loaded from `.env` files or a secrets vault, not typed in the terminal
- [ ] Terminal history doesn't contain any recent token/password commands (`history | grep token`)
- [ ] Log output is visible — check it doesn't print raw secrets
- [ ] No credential files are open in your editor's visible tabs
- [ ] **Over-the-shoulder / camera aware:** close or minimise any terminal, file, or browser tab containing secrets before screen sharing or recording — assume any visible text can be read, paused, or zoomed by viewers

---

## Authentication & Authorization

### OIDC Claims & Scopes - The Universal Standard

All permission checks — API endpoints, internal service calls, UI feature gates, and every access control decision — must use OIDC-style claims and scopes. There are no exceptions for "internal only" paths or "admin shortcuts." This ensures authorization logic is consistent, testable, auditable, and federation-ready.

**Why OIDC claims matter:** They're structured, standardized, and portable. Ad-hoc role strings scattered through code are not. One claim model everywhere means you can trust your security boundary.

#### Roles as Pre-Bundled Scope Sets

Think of roles like this: `admin`, `maintainer`, and `viewer` are not magic strings — they're named bundles of scopes. The auth service expands them into actual scopes when the token is issued. After that, your code never checks role names again. You only check scopes.

**The role tiers (at every layer):**

| Layer | Notes |
|---|---|
| **Global** | Broadest — applies across the whole app |
| **Team** | Scoped to a specific team |
| **Resource** | Scoped to a specific resource |
| **Tenant** | Always present — single-tenant apps use one fixed tenant |

**Pre-bundled scope definitions (expanded at token issuance):**
```
admin      → *:read *:write *:admin *:delete settings:write users:admin
maintainer → *:read *:write teams:read reports:read analytics:read
viewer     → *:read  (reporters may also carry reports:write)
```

Narrower layers restrict, never expand, scopes from broader layers.

**Mandatory JWT claim set (all tokens, internal and external):**
```json
{
  "sub":    "<user-or-service-id>",
  "iss":    "https://<auth-service>",
  "aud":    ["<target-service>"],
  "iat":    1234567890,
  "exp":    1234567890,
  "scope":  "users:read reports:write",
  "tenant": "<tenant-id>",
  "teams":  ["<team-id>"],
  "roles":  ["maintainer"]
}
```

> `roles` is informational/audit only — all authorization decisions use `scope`.

**Authorization rules:**
- Every API endpoint declares its **required scope(s)** — enforced via middleware, never hardcoded inline
- Internal service-to-service calls use machine JWTs with their own scopes — never bypass auth
- UI feature gates read from the token `scope` claim, not separate role lookups
- `scope` uses `resource:action` format (e.g., `users:read`, `reports:write`)
- Never branch on role names in application code — check scopes only

**Standard Scopes Pattern:**
```
users:read        users:write       users:admin       users:delete
reports:read      reports:write
analytics:read    analytics:admin
teams:read        teams:write       teams:admin
settings:read     settings:write
service:internal  service:admin
```

### Three-Tier Role System (Deprecated - Use Scopes Instead)

The following is maintained for reference on role tiers, but **authorization decisions MUST be made on scopes, not role names.**

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

### Tenant Isolation - A Hard Security Boundary

**Every application must implement the tenant layer.** Even if your app only serves one organization (single-tenant), the `tenant` claim is still present, still validated, and still enforced. This future-proofs your data model and auth stack for multi-tenancy without a rewrite.

**Tenant enforcement is mandatory and non-negotiable at every layer.**

**The rules:**
- **Every token carries a `tenant` claim** — requests without a valid tenant claim are rejected immediately
- **Tenant middleware runs first**, before any scope or role check — tenant mismatch is an instant 403 Forbidden
- **No cross-tenant data access** — all database queries, cache lookups, and service calls must be scoped to the token's `tenant` claim
- **Tenant claim is issued by auth service only** — never trust a tenant ID from the request body, query param, or header. Always extract from the validated JWT
- **Admin tokens are not exempt** — even `admin` role tokens are tenant-scoped unless explicitly issued as a cross-tenant super-admin token (which must be short-lived and fully audit logged)

**What this looks like in code:**

```python
# ❌ NEVER: Query without tenant filter
users = db(db.users.active == True).select()

# ✅ ALWAYS: Extract tenant from JWT and apply it at the ORM layer
@app.route('/api/v1/users', methods=['GET'])
@require_scope('users:read')
def list_users():
    tenant_id = request.user.get('tenant')  # From validated JWT
    users = db((db.users.active == True) & (db.users.tenant == tenant_id)).select()
    return jsonify({'data': users})
```

**Single-tenant apps still use tenant claims:**

Even if your app will never scale to multi-tenancy, single-tenant apps use one fixed tenant ID — usually hardcoded or loaded from config. The same validation rules apply. This makes the auth layer migration-proof.

### Session & Token Security

- JWT tokens expire (1 hour for access, refresh tokens for long-lived access)
- Secure cookies with `HttpOnly`, `Secure`, `SameSite=Strict` flags
- Multi-factor authentication support (2FA codes, biometric, U2F keys)
- Passwords hashed with bcrypt (Flask-Security-Too handles this)

## Kubernetes Network Security

Kubernetes network policies are your firewall inside the cluster. Set them up correctly and you've built a fortress. Skip them and you've left the front door open.

### Default Deny Inter-Namespace Traffic (All Environments)

**Every namespace MUST have a default deny NetworkPolicy for inter-namespace traffic.** Pods within the same namespace can talk freely, but cross-namespace traffic is blocked by default unless explicitly allowed. This applies to **all environments** including local development and alpha.

**Apply this policy to every namespace at creation:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-cross-namespace
spec:
  podSelector: {}          # Applies to all pods in the namespace
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector: {}  # Allow intra-namespace only
  egress:
    - to:
        - podSelector: {}  # Allow intra-namespace only
    - to:                  # Allow DNS resolution (required for service discovery)
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

**When you need cross-namespace communication** (e.g., a backend namespace reaching a database namespace), create an explicit NetworkPolicy that allows only the specific source/destination namespace and port. Never a blanket allow-all.

### No Direct External Access — Ingress/Gateway Only (Beta & Production)

**In beta and production, services MUST NOT be exposed directly via NodePort, HostPort, or `externalIPs`.** All external traffic must enter the cluster through a managed ingress controller, API gateway, or service mesh proxy.

> **Alpha/local development is exempt** — NodePort and HostPort are fine for local work.

```
❌ NEVER (beta/prod): type: NodePort
❌ NEVER (beta/prod): hostPort on container specs
❌ NEVER (beta/prod): externalIPs on Service resources
❌ NEVER (beta/prod): hostNetwork: true (except for CNI/system DaemonSets)
✅ ALWAYS (beta/prod): Ingress resource or Gateway API backed by a managed controller
✅ ALWAYS (beta/prod): type: ClusterIP (default) for application services
✅ ALWAYS (beta/prod): TLS termination at the ingress/gateway layer
```

**Why:** NodePort and HostPort bypass centralized access control, TLS termination, rate limiting, and observability. Direct exposure also leaks cluster node IPs and opens attack surface on every node.

### Cilium CNI for Network Policy Enforcement

**Cilium is always preferred** for enforcing network policies over node-level iptables. It provides:
- Transparent, kernel-level enforcement (eBPF)
- Better observability and audit logging
- Support for more granular policies (DNS filtering, Layer 7 rules)
- Superior performance compared to iptables

Use Cilium as your CNI in all environments where network policy enforcement matters (dev, beta, production).

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
- [ ] Logs don't contain passwords or secrets — tokens masked (e.g. `tok_****1234`)
- [ ] Tokens/secrets read from env vars or files — never passed as CLI arguments
- [ ] Dependencies updated to patched versions
- [ ] Each microservice/container has its own database account (no shared credentials)

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

## Authentication Model by Communication Type

Security boundaries shift when services talk to each other, so authentication methods must match the communication channel.

### User → Service: OIDC/OAuth2 with JWT

**The standard for all user-to-service communication.**

Every user request carries a JWT issued by the OIDC provider with claims (scopes, tenant, teams) that drive all authorization decisions. This JWT is the golden ticket — it contains everything the service needs to know about what the user can do.

**What the JWT includes:**
```json
{
  "sub": "<user-id>",
  "iss": "https://<auth-service>",
  "aud": ["<target-service>"],
  "scope": "users:read reports:write",
  "tenant": "<tenant-id>",
  "teams": ["<team-id>"],
  "exp": 1234567890
}
```

**Why OIDC/OAuth2:**
- Standardized, portable across organizations
- Scopes baked into the token for granular permission checking
- Supports federation and SSO
- Refresh tokens for long-lived sessions without exposing access tokens

### Service → Service: SPIFFE/SPIRE (Preferred) or OIDC Machine JWTs

**Two approaches, with SPIFFE/SPIRE preferred.**

#### SPIFFE/SPIRE (Preferred)

SPIFFE provides automatic identity issuance to services without managing static secrets. SPIRE (the SPIFFE runtime) watches your infrastructure (Kubernetes, VMs, etc.) and automatically issues short-lived X.509 SVIDs (certificates) to each service.

**Why SPIFFE/SPIRE is superior:**
- **Automatic identity** — services receive a SPIFFE ID and X.509 certificate without managing API keys or secrets
- **mTLS by default** — every service-to-service call is mutually authenticated and encrypted
- **Short-lived credentials** — SVIDs rotate automatically (typically every hour), eliminating long-lived API keys
- **Platform-agnostic** — works across Kubernetes, VMs, and bare metal with the same trust domain
- **No secret distribution** — SPIRE handles credential lifecycle end-to-end; you never touch raw secrets

**SPIFFE identity format:**
```
spiffe://penguintech.io/<environment>/<service>

# Examples:
spiffe://penguintech.io/beta/backend-api
spiffe://penguintech.io/prod/license-server
spiffe://penguintech.io/alpha/connector
```

**Service-to-service authorization** still uses scopes. When using SPIFFE/SPIRE, the SPIFFE ID maps to a set of scopes in a policy engine (e.g., OPA). Authorization middleware then checks scopes just like it does for user tokens.

#### OIDC Machine JWTs (Acceptable Alternative)

If SPIFFE/SPIRE isn't available, OIDC machine JWTs are acceptable. Services authenticate using a service account JWT that includes:

```json
{
  "sub": "<service-account-id>",
  "iss": "https://<auth-service>",
  "aud": ["<target-service>"],
  "scope": "service:internal reports:write",
  "tenant": "<tenant-id>"
}
```

The service reads this JWT from a mounted secret or environment variable and presents it on outbound calls. Less elegant than SPIFFE (because secrets still exist), but simpler to deploy in constrained environments.

### Never Rules

Service-to-service communication has hard boundaries:

```
❌ NEVER: Service-to-service calls without authentication (no auth bypass)
❌ NEVER: Long-lived static API keys or shared secrets between services
✅ ALWAYS: SPIFFE/SPIRE mTLS (preferred) or OIDC machine JWTs for service identity
✅ ALWAYS: Scope-based authorization regardless of identity method
```

**No exceptions.** Even "internal only" services are authenticated and scoped.

## Learn More

- [OWASP Top 10](https://owasp.org/www-project-top-ten/) - The most critical web security risks
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework) - Industry standards
- [Flask-Security-Too Docs](https://flask-security-too.readthedocs.io/) - Our auth framework
- [PyDAL Security](https://py4web.io/chapter-13#security) - Database protection
- [SQLAlchemy Security](https://docs.sqlalchemy.org/en/14/faq/security.html) - ORM safety
