# 🔌 Integrations Guide - Connecting All The Things

Part of [Development Standards](../STANDARDS.md)

---

## Overview

This guide covers integrating your application with external services and platforms. We support three major integrations to power your apps:

- **🤖 WaddleAI** - AI and machine learning features (optional, when you need smarts)
- **🚦 MarchProxy** - Load balancing and API gateway (recommended for production)
- **🔑 License Server** - Feature gating and entitlements (enterprise control)

Each integration is optional depending on your needs, but when you use them, follow these patterns.

---

## 🚦 MarchProxy (Load Balancer & API Gateway)

Your app runs behind **MarchProxy** (`~/code/MarchProxy`) for routing, load balancing, and API gateway features.

**Important:** Don't include MarchProxy in your `docker-compose.yml` - it's external infrastructure managed separately. Just generate config files and import them via MarchProxy's API.

### How It Works

1. Your services run in containers (Flask API, Go backend, React WebUI)
2. MarchProxy handles routing, TLS termination, and load balancing
3. You generate config files describing your services
4. Import config via MarchProxy REST API
5. MarchProxy routes traffic to your containers

### Service Configuration

Generate service definitions in `config/marchproxy/services.json`:

```json
{
  "services": [
    {
      "name": "myapp-flask-api",
      "ip_fqdn": "flask-backend",
      "port": 8080,
      "protocol": "http",
      "collection": "myapp",
      "auth_type": "jwt",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/healthz",
      "health_check_interval": 30
    },
    {
      "name": "myapp-go-backend",
      "ip_fqdn": "go-backend",
      "port": 50051,
      "protocol": "grpc",
      "collection": "myapp",
      "auth_type": "none",
      "health_check_enabled": true,
      "health_check_path": "/grpc.health.v1.Health/Check",
      "health_check_interval": 10
    },
    {
      "name": "myapp-webui",
      "ip_fqdn": "webui",
      "port": 80,
      "protocol": "http",
      "collection": "myapp",
      "health_check_enabled": true,
      "health_check_path": "/"
    }
  ]
}
```

**Key fields:**
- `name`: Use `{app_name}-{service}` for easy filtering
- `protocol`: `http` (REST), `grpc` (high-performance), `tcp` (raw)
- `auth_type`: `jwt` (external APIs), `none` (internal gRPC)
- `health_check_enabled`: Always true for production

### Route Configuration

Define routes in `config/marchproxy/mappings.json`:

```json
{
  "mappings": [
    {
      "name": "myapp-external-api",
      "description": "External REST API access",
      "source_services": ["external"],
      "dest_services": ["myapp-flask-api"],
      "listen_port": 443,
      "protocol": "https",
      "path_prefix": "/api/v1"
    },
    {
      "name": "myapp-webui-access",
      "description": "WebUI frontend access",
      "source_services": ["external"],
      "dest_services": ["myapp-webui"],
      "listen_port": 443,
      "protocol": "https",
      "path_prefix": "/"
    }
  ]
}
```

### Python Config Generator

Auto-generate MarchProxy config from your app settings:

```python
"""Generate MarchProxy import configuration"""
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class MarchProxyService:
    name: str
    ip_fqdn: str
    port: int
    protocol: str = "http"
    collection: Optional[str] = None
    auth_type: str = "none"
    health_check_enabled: bool = True
    health_check_path: str = "/healthz"
    health_check_interval: int = 30

def generate_marchproxy_config(app_name: str, services: list[MarchProxyService]) -> dict:
    """Generate MarchProxy-compatible configuration"""
    return {
        "services": [asdict(s) for s in services],
        "metadata": {
            "app_name": app_name,
            "generated_by": "project-template",
            "version": os.getenv("APP_VERSION", "0.0.0")
        }
    }

def write_marchproxy_config(config: dict, output_dir: str = "config/marchproxy"):
    """Write configuration to file"""
    os.makedirs(output_dir, exist_ok=True)
    with open(f"{output_dir}/import-config.json", "w") as f:
        json.dump(config, f, indent=2)

# Example usage
if __name__ == "__main__":
    services = [
        MarchProxyService(
            name="myapp-flask-api",
            ip_fqdn="flask-backend",
            port=8080,
            protocol="http",
            auth_type="jwt"
        ),
        MarchProxyService(
            name="myapp-go-backend",
            ip_fqdn="go-backend",
            port=50051,
            protocol="grpc"
        ),
    ]
    config = generate_marchproxy_config("myapp", services)
    write_marchproxy_config(config)
```

### Import Script

Create `scripts/marchproxy-import.sh` to import your config:

```bash
#!/bin/bash
MARCHPROXY_API="${MARCHPROXY_API:-http://localhost:8000}"
CLUSTER_API_KEY="${CLUSTER_API_KEY:-}"

if [ -z "$CLUSTER_API_KEY" ]; then
    echo "Error: CLUSTER_API_KEY environment variable required"
    exit 1
fi

curl -X POST "$MARCHPROXY_API/api/v1/services/import" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CLUSTER_API_KEY" \
    -d @config/marchproxy/import-config.json

echo "MarchProxy configuration imported"
```

### MarchProxy API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/services` | POST | Create a service |
| `/api/v1/services/import` | POST | Bulk import services |
| `/api/v1/services` | GET | List all services |
| `/api/v1/services/{id}` | PUT | Update service |
| `/api/v1/services/{id}` | DELETE | Delete service |
| `/api/v1/config/{cluster_id}` | GET | Get cluster config |

📚 **Full docs:** See `~/code/MarchProxy/api-server/README.md`

---

## 🤖 WaddleAI Integration

Add AI superpowers to your app with WaddleAI - NLP, ML inference, chatbots, and more.

### When to Use WaddleAI

Consider WaddleAI if your app needs:
- Natural language processing (sentiment analysis, text classification)
- Machine learning model inference
- Chatbots or conversational interfaces
- Document understanding and extraction
- Predictive analytics
- AI-powered automation

**Not needed?** Skip it. It's optional and only adds complexity if you don't use it.

### Architecture Pattern

WaddleAI runs as a separate microservice in your docker-compose:

```
services/
├── flask-backend/     # Your Flask API
├── webui/            # Your React frontend
├── go-backend/       # Optional: High-performance backend
└── ai/               # Optional: WaddleAI service (if using AI)
```

### Setup Steps

**1. Add WaddleAI to your project:**

```bash
git submodule add ~/code/WaddleAI services/ai/waddleai
```

**2. Update docker-compose.dev.yml:**

```yaml
version: '3.8'

services:
  flask-backend:
    build: ./services/flask-backend
    environment:
      - WADDLEAI_URL=http://waddleai:8000
    depends_on:
      - waddleai

  waddleai:
    build: ./services/ai/waddleai
    environment:
      - MODEL_PATH=/models
      - MAX_WORKERS=4
    volumes:
      - ai-models:/models
    # Internal only - not exposed to host

volumes:
  ai-models:
```

**3. Python API client for Flask backend:**

```python
import os
import httpx
from typing import Dict, Any, Optional

class WaddleAIClient:
    """Client for WaddleAI service"""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv('WADDLEAI_URL', 'http://localhost:8000')
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def analyze_text(self, text: str, task: str = "sentiment") -> Dict[str, Any]:
        """Analyze text with AI model"""
        response = await self.client.post(
            "/api/v1/analyze",
            json={"text": text, "task": task}
        )
        response.raise_for_status()
        return response.json()

    async def generate_response(self, prompt: str, context: Optional[str] = None) -> str:
        """Generate AI response"""
        response = await self.client.post(
            "/api/v1/generate",
            json={"prompt": prompt, "context": context}
        )
        response.raise_for_status()
        return response.json()["response"]

    async def close(self):
        await self.client.aclose()

# Flask integration
from flask import Flask, request, jsonify
from shared.licensing import requires_feature

app = Flask(__name__)
ai_client = WaddleAIClient()

@app.route('/api/v1/ai/analyze', methods=['POST'])
@auth_required()
@requires_feature('ai_analysis')  # License-gate AI features
async def ai_analyze():
    """AI-powered analysis - enterprise feature"""
    data = request.get_json()
    result = await ai_client.analyze_text(data['text'], data.get('task', 'sentiment'))
    return jsonify(result)
```

**4. React component to use AI features:**

```javascript
import { useState } from 'react';
import { apiClient } from '../services/apiClient';

const aiService = {
  analyzeText: (text, task = 'sentiment') =>
    apiClient.post('/api/v1/ai/analyze', { text, task })
};

export const AIAnalyzer = () => {
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);

  return (
    <div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} />
      <button onClick={async () => {
        const res = await aiService.analyzeText(text);
        setResult(res.data);
      }}>Analyze</button>
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
};
```

### AI Features License Gating

AI features should be enterprise/professional tier only:

```python
# Define feature tiers
AI_FEATURES = {
    'ai_analysis': 'professional',      # Professional tier+
    'ai_generation': 'professional',    # Professional tier+
    'ai_training': 'enterprise',        # Enterprise only
    'ai_custom_models': 'enterprise'    # Enterprise only
}

# Check what's available
from shared.licensing import license_client

def check_ai_features():
    """Check available AI features based on license"""
    features = {}
    for feature, required_tier in AI_FEATURES.items():
        features[feature] = license_client.has_feature(feature)
    return features
```

### Environment Variables

```bash
# WaddleAI service configuration
WADDLEAI_URL=http://waddleai:8000
WADDLEAI_API_KEY=optional-api-key
WADDLEAI_MODEL_PATH=/models
WADDLEAI_MAX_WORKERS=4
WADDLEAI_TIMEOUT=30

# License-gated AI features
AI_FEATURES_ENABLED=true
```

### Important Notes

1. **Optional**: Only add if you actually need AI features
2. **License-gated**: Make AI enterprise/professional tier
3. **Resource-intensive**: Monitor GPU/CPU usage if using inference
4. **Isolated**: Separate container prevents resource conflicts
5. **Docs**: See `~/code/WaddleAI` for detailed integration

---

## 🔑 License Server Integration

PenguinTech License Server manages feature entitlements and licensing at `https://license.penguintech.io`.

### Why License Server?

- **Feature gating**: Enable/disable features based on subscription tier
- **Entitlement checking**: Know what customers are licensed for
- **Usage tracking**: Report active users, storage, teams
- **Tier enforcement**: Community, Professional, Enterprise

### Environment Setup

```bash
# License Configuration
LICENSE_KEY=PENG-XXXX-XXXX-XXXX-XXXX-ABCD
LICENSE_SERVER_URL=https://license.penguintech.io
PRODUCT_NAME=project-template
RELEASE_MODE=false  # Dev: false (all features), Prod: true (enforce license)
```

### Validation Flow

On startup:
1. Read license key from environment
2. Call license server to validate
3. Get back: tier, features[], expiration, limits
4. Cache result locally
5. Run hourly keepalive with usage stats

Error handling:
- **Validation fails (RELEASE_MODE=true)**: Exit with error
- **Validation fails (RELEASE_MODE=false)**: Warn, continue (development)
- **Network error**: Cache previous result, retry on next startup
- **Feature not entitled**: Return 403 Forbidden

### Feature Gating

```python
# Python: Check feature entitlement
from app.license import license_manager

@require_feature('sso_integration')
def enable_sso():
    # Only runs if license allows SSO
    pass

# Manual check
if license_manager.is_feature_enabled('audit_logs'):
    # Log important actions
    pass
```

### Tiers and Features

```
Community (free):
├── Basic auth (email/password)
├── Up to 5 users
└── Single team

Professional:
├── Community features +
├── SSO/OAuth2
├── Multiple teams
├── API keys
└── Audit logging

Enterprise:
├── Professional features +
├── Custom SAML
├── Advanced analytics
└── Priority support
```

### Keepalive Check-in

Every hour, report usage to license server:

```python
{
  "license_key": "PENG-XXXX-XXXX-XXXX-XXXX-ABCD",
  "product": "project-template",
  "usage": {
    "active_users": 42,
    "team_count": 8,
    "storage_gb": 125
  }
}
```

---

## 🔧 Configuration Management

All integrations and system settings follow one pattern: **Environment variables for bootstrap, database for runtime**.

### Setup Process

1. **Docker startup** → Read environment variables
2. **Validate** → Check formats, required fields
3. **Database check** → See if config already exists
4. **Initialize** → Write validated config to database
5. **Runtime** → Use database config (takes precedence)

### Database Schema

Create `config` table for storing configuration:

```sql
CREATE TABLE config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(255) UNIQUE NOT NULL,
    config_value TEXT NOT NULL,
    config_type VARCHAR(50) NOT NULL,  -- 'string', 'integer', 'boolean', 'json'
    category VARCHAR(100) NOT NULL,    -- 'integration', 'system', 'security', etc.
    description TEXT,
    is_sensitive BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255),           -- User who made the change
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_config_category ON config(category);
CREATE INDEX idx_config_key ON config(config_key);
```

### PyDAL Table Definition

```python
db.define_table('config',
    Field('config_key', 'string', unique=True, required=True),
    Field('config_value', 'text', required=True),
    Field('config_type', 'string', requires=IS_IN_SET(['string', 'integer', 'boolean', 'json'])),
    Field('category', 'string', requires=IS_IN_SET(['integration', 'system', 'security', 'database', 'email'])),
    Field('description', 'text'),
    Field('is_sensitive', 'boolean', default=False),
    Field('last_updated', 'datetime', default=request.now, update=request.now),
    Field('updated_by', 'string'),
    Field('created_at', 'datetime', default=request.now),
    migrate=True
)
```

### Bootstrap Function

```python
import os, json

def bootstrap_configuration(db):
    """Bootstrap config from env vars on first run"""
    mappings = {
        'smtp_host': ('SMTP_HOST', 'email', 'string', 'SMTP server', False),
        'waddleai_url': ('WADDLEAI_URL', 'integration', 'string', 'WaddleAI endpoint', False),
    }

    for key, (env, cat, typ, desc, sens) in mappings.items():
        if not db(db.config.config_key == key).select().first():
            val = os.getenv(env)
            if val and (v := validate_config(val, typ)):
                db.config.insert(
                    config_key=key, config_value=str(v), config_type=typ,
                    category=cat, description=desc, is_sensitive=sens, updated_by='system'
                )
    db.commit()

def validate_config(value, config_type):
    """Validate and parse config value"""
    try:
        if config_type == 'integer': return int(value)
        elif config_type == 'boolean': return value.lower() in ['true', '1', 'yes']
        elif config_type == 'json': return json.dumps(json.loads(value))
        else: return value
    except: return None
```

### Admin API Endpoints

Expose configuration management to admins only:

```python
from flask import Flask, request, jsonify
from flask_security import auth_required, roles_required, current_user

@app.route('/api/v1/config', methods=['GET'])
@auth_required()
@roles_required('admin')
def list_config():
    """List all configurations (masks sensitive values)"""
    configs = db(db.config).select(orderby=db.config.category)
    return jsonify({'configs': [{
        'key': c.config_key,
        'value': '***SENSITIVE***' if c.is_sensitive else c.config_value,
        'type': c.config_type,
        'category': c.category,
        'description': c.description
    } for c in configs]})

@app.route('/api/v1/config/<config_key>', methods=['PUT'])
@auth_required()
@roles_required('admin')
def update_config(config_key):
    """Update configuration value"""
    config = db(db.config.config_key == config_key).select().first()
    if not config:
        return jsonify({'error': 'Not found'}), 404

    validated = validate_config(request.get_json().get('value'), config.config_type)
    if validated is None:
        return jsonify({'error': 'Invalid value'}), 400

    config.update_record(config_value=str(validated), updated_by=current_user.email)
    db.commit()
    return jsonify({'message': 'Updated'})
```

### Settings Page (React)

```jsx
import { useState, useEffect } from 'react';
import { apiClient } from '../../services/apiClient';

export function ConfigurationPage() {
  const [configs, setConfigs] = useState([]);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    (async () => {
      const res = await apiClient.get('/api/v1/config');
      setConfigs(res.data.configs);
    })();
  }, []);

  const handleUpdate = async (key, value) => {
    try {
      await apiClient.put(`/api/v1/config/${key}`, { value });
      setEditing(null);
    } catch (err) {
      alert('Failed to update');
    }
  };

  return (
    <div>
      <h1>System Configuration</h1>
      <table>
        <thead>
          <tr>
            <th>Setting</th>
            <th>Value</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {configs.map((c) => (
            <tr key={c.key}>
              <td><code>{c.key}</code></td>
              <td>
                {editing === c.key ? (
                  <input type="text" defaultValue={c.value}
                    onBlur={(e) => handleUpdate(c.key, e.target.value)} />
                ) : (
                  c.value
                )}
              </td>
              <td>
                <button onClick={() => setEditing(c.key)}>Edit</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Security Best Practices

1. **Sensitive values**: Mark passwords/API keys as `is_sensitive=True`
2. **Mask in responses**: Never return sensitive values in APIs
3. **Authorization**: Only global admins can modify config
4. **Validation**: Always validate before saving
5. **Audit trail**: Log who changed what and when
6. **Encryption**: Consider encrypting sensitive values in database

### Configuration Categories

- `integration` - External service integrations (WaddleAI, MarchProxy)
- `email` - SMTP and email settings
- `security` - Security settings (TLS, auth)
- `database` - Database connection settings
- `system` - General system settings
- `license` - License server configuration

---

## Key Principles

1. **Bootstrap from Environment**: Initial config from Docker env vars
2. **Database as Source of Truth**: Config stored and retrieved from database
3. **Admin-Only Management**: Global admins control configuration
4. **Runtime Updates**: Changes effective without restart
5. **Audit Trail**: Track all changes with user and timestamp
6. **Validation**: Validate all input before storing
7. **Security**: Mask and encrypt sensitive values

📚 **Related:** [Database Standards](DATABASE.md) | [Authentication Standards](AUTHENTICATION.md) | [Security Standards](SECURITY.md)
