# 🌐 API Guide - How Our Services Talk

Part of [Development Standards](../STANDARDS.md)

Think of APIs like postal services: REST is standard mail (reliable, understood everywhere), gRPC is like express shipping (faster, direct service-to-service), and HTTP/3 is like teleportation for the impatient.

## 🎯 API Design Principles

**Keep it Simple. Keep it Flexible. Keep it Versioned.**

1. **💡 Simple**: Clear resource-based URLs, minimize complexity
2. **💡 Extensible**: Build for tomorrow - flexible inputs, backward-compatible responses
3. **💡 Reuse**: Don't reinvent the wheel - leverage existing APIs instead of creating duplicates
4. **💡 Versioned**: Multiple API versions so old clients don't break

## 🔌 REST vs gRPC: Which One to Use?

### 🌐 REST (External Communication)
**Use when**: Talking to external clients, browsers, third-party services
- **What it is**: HTTP requests with JSON, like a web browser visiting a website
- **Speed**: Fast enough for most cases, simpler to debug
- **Example**: Your React frontend calling `/api/v2/users`

```
Client → REST API → Backend
↓
Easy to curl, inspect in browser, test with Postman
```

### ⚡ gRPC (Internal Communication)
**Use when**: Services talking to each other inside your cluster
- **What it is**: Binary protocol over HTTP/2, like a super-efficient inter-process call
- **Speed**: 2-10x faster than REST, lower bandwidth
- **Example**: `teams-api` calling `go-backend` for analytics

```
teams-api → (gRPC) → go-backend
↓
Fast, efficient, automatic serialization
```

## 📝 Creating Your First Endpoint

### Step 1: Plan Your Resource
```python
# What are we exposing?
# Users, Products, Teams, Orders, etc.
# Keep it simple: /api/v2/users
```

### Step 2: Write the Flask Route
```python
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/api/v2/users', methods=['GET', 'POST'])
def users():
    if request.method == 'GET':
        all_users = fetch_users()  # Your database call
        return jsonify({
            'status': 'success',
            'data': all_users,
            'meta': {'total': len(all_users)}
        })

    elif request.method == 'POST':
        new_user = create_user(request.json)
        return jsonify({
            'status': 'created',
            'data': new_user
        }), 201  # 201 = Created

@app.route('/api/v2/users/<int:user_id>', methods=['GET', 'PUT', 'DELETE'])
def user_detail(user_id):
    if request.method == 'GET':
        user = fetch_user(user_id)
        if not user:
            return jsonify({'status': 'error', 'error': 'Not found'}), 404
        return jsonify({'status': 'success', 'data': user})

    elif request.method == 'PUT':
        updated = update_user(user_id, request.json)
        return jsonify({'status': 'success', 'data': updated})

    elif request.method == 'DELETE':
        delete_user(user_id)
        return '', 204  # 204 = No content
```

### Step 3: Test It
```bash
# GET all users
curl http://localhost:5000/api/v2/users

# POST new user
curl -X POST http://localhost:5000/api/v2/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice","email":"alice@example.com"}'

# GET single user
curl http://localhost:5000/api/v2/users/1

# DELETE user
curl -X DELETE http://localhost:5000/api/v2/users/1
```

## 📍 Versioning: Why `/api/v1/` AND `/api/v2/` Exist

**The Problem**: You release v2 with amazing new features, but old clients still expect v1 format. They break. Users are upset.

**The Solution**: Run both versions simultaneously.

```
Client 1 (v1) → /api/v1/users → Old format (simple)
Client 2 (v2) → /api/v2/users → New format (enhanced metadata)
```

### Version Numbers in URLs
```
✓ /api/v1/users    (correct - version in URL)
✓ /api/v2/users    (correct - newer version)
✗ /api/users?v=1   (wrong - version in query params)
```

### Version Lifecycle (N-2 Model)
- **Current (v2)**: Fully supported, active development
- **Previous (v1)**: Bug fixes and security patches only
- **Two Back**: Security patches only
- **Older**: Sunset warning headers, then deleted

**Timeline Example**:
- Month 0: Release v2 alongside v1
- Months 1-12: Both fully supported
- Month 13: v1 returns deprecation headers
- Month 14: v1 shut down

## 📊 Request/Response Examples

### GET Users List
```bash
# Request
GET /api/v2/users?limit=10&offset=0

# Response (200 OK)
{
  "status": "success",
  "data": [
    {"id": 1, "name": "Alice", "email": "alice@company.com"},
    {"id": 2, "name": "Bob", "email": "bob@company.com"}
  ],
  "meta": {
    "version": 2,
    "total": 2,
    "limit": 10,
    "offset": 0
  }
}
```

### CREATE New User
```bash
# Request
POST /api/v2/users
Content-Type: application/json

{
  "name": "Charlie",
  "email": "charlie@company.com"
}

# Response (201 Created)
{
  "status": "created",
  "data": {
    "id": 3,
    "name": "Charlie",
    "email": "charlie@company.com",
    "created_at": "2025-01-22T10:30:00Z"
  }
}
```

### UPDATE User
```bash
# Request
PUT /api/v2/users/1
Content-Type: application/json

{
  "name": "Alice Updated",
  "email": "alice.new@company.com"
}

# Response (200 OK)
{
  "status": "success",
  "data": {
    "id": 1,
    "name": "Alice Updated",
    "email": "alice.new@company.com"
  }
}
```

## ❌ Error Handling Done Right

**Always return consistent error responses:**

```python
@app.route('/api/v2/users/<int:user_id>', methods=['GET'])
def user_detail(user_id):
    user = fetch_user(user_id)

    if not user:
        return jsonify({
            'status': 'error',
            'error': 'user_not_found',
            'message': f'User {user_id} does not exist',
            'meta': {'version': 2}
        }), 404

    if not user.is_active:
        return jsonify({
            'status': 'error',
            'error': 'user_inactive',
            'message': 'This user account is inactive',
            'meta': {'version': 2}
        }), 403

    return jsonify({'status': 'success', 'data': user})
```

### Common HTTP Status Codes
- **200**: OK - request succeeded
- **201**: Created - new resource created
- **204**: No Content - deletion succeeded
- **400**: Bad Request - invalid input
- **401**: Unauthorized - authentication failed
- **403**: Forbidden - authenticated but no permission
- **404**: Not Found - resource doesn't exist
- **409**: Conflict - data conflict (duplicate email, etc.)
- **500**: Server Error - something broke

## 💡 Tips for Good API Design

**💡 Tip 1: Consistent Response Format**
Always wrap responses in `{status, data, meta}` structure.

**💡 Tip 2: Use HTTP Verbs Correctly**
- GET: Read data (safe, no side effects)
- POST: Create new resource
- PUT: Update existing resource
- DELETE: Remove resource
- PATCH: Partial update

**💡 Tip 3: Version Your APIs**
Never ship v1 without planning for v2.

**💡 Tip 4: Validate Input**
Bad data in = bad data out. Validate requests early.

**💡 Tip 5: Document with Examples**
Include curl examples and real responses in your docs.

## 🧪 Testing Your APIs

### Unit Test Example
```python
import pytest
from app import app, create_user

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_get_users(client):
    response = client.get('/api/v2/users')
    assert response.status_code == 200
    assert response.json['status'] == 'success'
    assert isinstance(response.json['data'], list)

def test_create_user(client):
    response = client.post('/api/v2/users', json={
        'name': 'Test User',
        'email': 'test@example.com'
    })
    assert response.status_code == 201
    assert response.json['status'] == 'created'
    assert response.json['data']['name'] == 'Test User'

def test_user_not_found(client):
    response = client.get('/api/v2/users/999')
    assert response.status_code == 404
    assert response.json['status'] == 'error'
```

### Integration Test Example
```python
def test_user_lifecycle(client):
    # Create
    create_resp = client.post('/api/v2/users', json={
        'name': 'John', 'email': 'john@example.com'
    })
    user_id = create_resp.json['data']['id']

    # Read
    get_resp = client.get(f'/api/v2/users/{user_id}')
    assert get_resp.json['data']['name'] == 'John'

    # Update
    update_resp = client.put(f'/api/v2/users/{user_id}', json={
        'name': 'John Updated'
    })
    assert update_resp.json['data']['name'] == 'John Updated'

    # Delete
    delete_resp = client.delete(f'/api/v2/users/{user_id}')
    assert delete_resp.status_code == 204
```

## 🔧 Configuration

**Environment Variables:**
```bash
HTTP_PORT=8080                # REST API port
GRPC_PORT=50051               # gRPC port
HTTP1_ENABLED=true            # Enable HTTP/1.1
HTTP2_ENABLED=true            # Enable HTTP/2
HTTP3_ENABLED=false           # Enable HTTP/3/QUIC (optional)
GRPC_ENABLED=true             # Enable gRPC
```

## 📚 Quick Reference

| Protocol | Use Case | Speed | Format |
|----------|----------|-------|--------|
| REST | External clients, browsers | Good | JSON |
| gRPC | Internal service calls | Excellent | Protobuf |
| HTTP/3 | High-traffic (>10K req/sec) | Best | JSON/Protobuf |

## 🎓 Learning Resources

**Understanding APIs:**
- [REST API Best Practices](https://restfulapi.net/)
- [gRPC Documentation](https://grpc.io/)
- [HTTP Status Codes](https://httpwg.org/specs/rfc7231.html#status.codes)

**Tools for Testing:**
- **curl**: Command-line HTTP client
- **Postman**: GUI for API testing
- **insomnia**: Modern API client
- **pytest**: Python testing framework
