# Security Standards

Part of [Development Standards](../STANDARDS.md)

## Input Validation

- ALL inputs MUST have appropriate validators
- Use framework-native validation (PyDAL validators, Go libraries)
- Implement XSS and SQL injection prevention
- Server-side validation for all client input
- CSRF protection using framework native features

## Authentication & Authorization

**Core Requirements:**
- Multi-factor authentication support
- Role-based access control (RBAC) with OAuth2-style scopes
- API key management with rotation
- JWT token validation with proper expiration
- Session management with secure cookies

**OAuth2-Style Scopes Model:**
- All APIs and user permissions MUST be scopable similar to OAuth2 scopes
- Scopes define granular permissions (e.g., `users:read`, `users:write`, `reports:read`, `analytics:admin`)
- Users and API clients receive tokens with specific scope sets
- Endpoints check requested operation against available scopes
- Scopes are hierarchical and composable

**Role-Based Access Control with Scopes:**

Implement three-tier role system at multiple levels:

1. **Global Level** - Organization-wide roles:
   - **Admin**: Full system access, user management, all scopes
   - **Maintainer**: Read/write access to resources, no user management, limited scopes
   - **Viewer**: Read-only access, minimal scopes (e.g., `:read` only)
   - **Custom Roles**: User-defined with selected scopes

2. **Container/Team Level** - Per service/team access:
   - **Team Admin**: Full access within container/team
   - **Team Maintainer**: Read/write within container/team
   - **Team Viewer**: Read-only within container/team
   - **Custom Roles**: Selected scopes for container context

3. **Resource Level** - Per-resource permissions:
   - **Owner**: Full control over specific resource
   - **Editor**: Read/write on specific resource
   - **Viewer**: Read-only on specific resource
   - **Custom Roles**: Specific scopes for resource

**Implementation Pattern:**

```python
# Define scopes for API endpoints
SCOPES = {
    'users:read': 'Read user data',
    'users:write': 'Create/update users',
    'users:admin': 'Delete users, manage roles',
    'reports:read': 'Read reports',
    'reports:write': 'Create/update reports',
    'analytics:read': 'Read analytics',
    'analytics:admin': 'Configure analytics',
}

# Role definitions with scope mappings
ROLE_SCOPES = {
    'global': {
        'admin': ['users:read', 'users:write', 'users:admin', 'reports:read', 'reports:write', 'analytics:read', 'analytics:admin'],
        'maintainer': ['users:read', 'users:write', 'reports:read', 'reports:write', 'analytics:read'],
        'viewer': ['users:read', 'reports:read', 'analytics:read'],
    },
    'container': {
        'admin': ['users:read', 'users:write', 'reports:read', 'reports:write'],
        'maintainer': ['users:read', 'reports:read', 'reports:write'],
        'viewer': ['users:read', 'reports:read'],
    },
}

from flask import Flask, request
from functools import wraps

app = Flask(__name__)

def require_scope(*required_scopes):
    """Decorator to check if user has required scopes"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get user from request context (from JWT token)
            user = request.user  # Set by authentication middleware
            user_scopes = user.get_scopes()

            # Check if user has at least one of required scopes
            has_scope = any(scope in user_scopes for scope in required_scopes)
            if not has_scope:
                return {'error': 'Insufficient permissions', 'required_scopes': required_scopes}, 403

            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/api/v1/users', methods=['GET'])
@require_scope('users:read')
def list_users():
    """List users - requires users:read scope"""
    users = db.users.select().fetchall()
    return jsonify({'data': users})

@app.route('/api/v1/users', methods=['POST'])
@require_scope('users:write')
def create_user():
    """Create user - requires users:write scope"""
    data = request.get_json()
    user = db.users.insert(**data)
    return jsonify({'data': user}), 201

@app.route('/api/v1/users/<int:user_id>', methods=['DELETE'])
@require_scope('users:admin')
def delete_user(user_id):
    """Delete user - requires users:admin scope"""
    db.users.delete(db.users.id == user_id)
    return '', 204
```

**Custom Roles with Scope Selection:**

```python
# Allow users to create custom roles
@app.route('/api/v1/roles/custom', methods=['POST'])
@require_scope('users:admin')
def create_custom_role():
    """Create custom role with selected scopes"""
    data = request.get_json()
    role_name = data.get('name')
    selected_scopes = data.get('scopes', [])

    # Validate requested scopes
    available_scopes = set(SCOPES.keys())
    if not set(selected_scopes).issubset(available_scopes):
        return {'error': 'Invalid scopes requested'}, 400

    # Create custom role
    custom_role = {
        'name': role_name,
        'scopes': selected_scopes,
        'level': data.get('level', 'container'),  # global, container, or resource
        'created_by': request.user.id,
    }
    db.custom_roles.insert(**custom_role)
    return jsonify({'data': custom_role}), 201

# Assign custom role to user
@app.route('/api/v1/users/<int:user_id>/roles', methods=['POST'])
@require_scope('users:admin')
def assign_role_to_user(user_id):
    """Assign role (standard or custom) to user"""
    data = request.get_json()
    role_id = data.get('role_id')
    scope = data.get('scope', 'global')  # global, container_id, or resource_id

    assignment = {
        'user_id': user_id,
        'role_id': role_id,
        'scope': scope,
    }
    db.role_assignments.insert(**assignment)
    return jsonify({'data': assignment}), 201
```

**JWT Token with Scopes:**

```python
import jwt
from datetime import datetime, timedelta

def create_access_token(user, scopes, expires_in=3600):
    """Create JWT token with scopes"""
    payload = {
        'sub': user.id,
        'user_email': user.email,
        'scopes': scopes,  # Include scopes in token
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return token

def verify_token(token):
    """Verify token and extract scopes"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.InvalidTokenError:
        return None
```

**API Client Scopes:**

API clients (service accounts, third-party integrations) should also have scope-based permissions:

```python
# Create API client with specific scopes
@app.route('/api/v1/clients', methods=['POST'])
@require_scope('users:admin')
def create_api_client():
    """Create API client with selected scopes"""
    data = request.get_json()
    client_name = data.get('name')
    client_scopes = data.get('scopes', [])

    # Generate API key
    api_key = generate_secure_key()

    client = {
        'name': client_name,
        'api_key': hash_api_key(api_key),
        'scopes': client_scopes,
        'created_by': request.user.id,
        'created_at': datetime.utcnow(),
    }
    db.api_clients.insert(**client)

    # Return plaintext API key only once
    return jsonify({
        'data': client,
        'api_key': api_key,  # Only shown once
    }), 201
```

## TLS/Encryption

- **TLS enforcement**: TLS 1.2 minimum, prefer TLS 1.3
- **Connection security**: Use HTTPS where possible
- **Modern protocols**: HTTP3/QUIC for high-performance
- **Standard security**: JWT, MFA, mTLS where applicable
- **Enterprise SSO**: SAML/OAuth2 as enterprise features

## Dependency Security

- **ALWAYS check Dependabot alerts** before commits
- **Monitor vulnerabilities** via Socket.dev
- **Mandatory security scanning** before dependency changes
- **Fix all security alerts immediately**
- **Version pinning**: Exact versions for security-critical dependencies

## Vulnerability Response Process

1. Identify affected packages and severity
2. Update to patched versions immediately
3. Test updated dependencies thoroughly
4. Document security fixes in commit messages
5. Verify no new vulnerabilities introduced
