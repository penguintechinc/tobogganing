# Integration Standards

Part of [Development Standards](../STANDARDS.md)

---

## MarchProxy API Gateway Integration

Applications are expected to run behind **MarchProxy** (`~/code/MarchProxy`) for API gateway and load balancing functionality.

**IMPORTANT:** Do NOT include MarchProxy in the application's `docker-compose.yml` - it's external infrastructure managed separately.

### Configuration Export

Generate MarchProxy-compatible import configuration files in `config/marchproxy/`:

```
config/
└── marchproxy/
    ├── services.json          # Service definitions
    ├── mappings.json          # Route mappings
    └── import-config.json     # Combined import file
```

### Service Definition Format

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
      "tls_enabled": false,
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
      "auth_type": "none",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/",
      "health_check_interval": 30
    }
  ]
}
```

### Mapping Definition Format

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

### Import Script

Create `scripts/marchproxy-import.sh`:

```bash
#!/bin/bash
# Import service configuration into MarchProxy

MARCHPROXY_API="${MARCHPROXY_API:-http://localhost:8000}"
CLUSTER_API_KEY="${CLUSTER_API_KEY:-}"

if [ -z "$CLUSTER_API_KEY" ]; then
    echo "Error: CLUSTER_API_KEY environment variable required"
    exit 1
fi

# Import services
curl -X POST "$MARCHPROXY_API/api/v1/services/import" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CLUSTER_API_KEY" \
    -d @config/marchproxy/import-config.json

echo "MarchProxy configuration imported"
```

### Python Configuration Generator

```python
"""Generate MarchProxy import configuration from application settings"""
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
    tls_enabled: bool = False
    health_check_enabled: bool = True
    health_check_path: str = "/healthz"
    health_check_interval: int = 30

def generate_marchproxy_config(app_name: str, services: list[MarchProxyService]) -> dict:
    """Generate MarchProxy-compatible import configuration"""
    return {
        "services": [asdict(s) for s in services],
        "metadata": {
            "app_name": app_name,
            "generated_by": "project-template",
            "version": os.getenv("APP_VERSION", "0.0.0")
        }
    }

def write_marchproxy_config(config: dict, output_dir: str = "config/marchproxy"):
    """Write configuration files for MarchProxy import"""
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
            collection="myapp",
            auth_type="jwt"
        ),
        MarchProxyService(
            name="myapp-go-backend",
            ip_fqdn="go-backend",
            port=50051,
            protocol="grpc",
            collection="myapp"
        ),
    ]

    config = generate_marchproxy_config("myapp", services)
    write_marchproxy_config(config)
```

### Integration Notes

1. **Service Names**: Use `{app_name}-{service}` naming convention for easy filtering
2. **Collection**: Group all app services under same collection for bulk operations
3. **Protocol Selection**:
   - `http`/`https`: REST API endpoints (Flask)
   - `grpc`: Internal high-performance services (Go backend)
   - `tcp`: Raw TCP connections
4. **Health Checks**: Always enable for production services
5. **Auth Type**: Use `jwt` for external-facing APIs, `none` for internal gRPC

### MarchProxy API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/services` | POST | Create service |
| `/api/v1/services/import` | POST | Bulk import services |
| `/api/v1/services` | GET | List services |
| `/api/v1/services/{id}` | PUT | Update service |
| `/api/v1/services/{id}` | DELETE | Delete service |
| `/api/v1/config/{cluster_id}` | GET | Get cluster config |

📚 **Full MarchProxy Documentation**: See `~/code/MarchProxy/api-server/README.md`

---

## WaddleAI Integration

**Optional AI capabilities - integrate only when AI features are required**

### When to Use WaddleAI

Consider WaddleAI integration for projects requiring:
- Natural language processing (NLP)
- Machine learning model inference
- AI-powered features and automation
- Intelligent data analysis
- Chatbots and conversational interfaces
- Document understanding and extraction
- Predictive analytics

### Architecture Pattern

**WaddleAI runs as a separate microservice:**

```
project-name/
├── services/
│   ├── api/           # Flask backend API
│   ├── webui/         # ReactJS frontend
│   ├── connector/     # Integration services
│   └── ai/            # WaddleAI service (optional)
```

### Integration Setup

**1. Reference WaddleAI from ~/code/WaddleAI:**

```bash
# Add as git submodule or copy required components
git submodule add ~/code/WaddleAI services/ai/waddleai
```

**2. Docker Compose Integration:**

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  api:
    build: ./services/api
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
    # Not exposed to host - internal network only

volumes:
  ai-models:
```

### API Client for WaddleAI

**Python integration in Flask backend:**

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

@app.route('/api/ai/analyze', methods=['POST'])
@auth_required()
@requires_feature('ai_analysis')  # License-gate AI features
async def ai_analyze():
    """AI-powered analysis - enterprise feature"""
    data = request.get_json()
    result = await ai_client.analyze_text(data['text'], data.get('task', 'sentiment'))
    return jsonify(result)
```

**ReactJS integration:**

```javascript
// src/services/aiClient.js
import { apiClient } from './apiClient';

export const aiService = {
  async analyzeText(text, task = 'sentiment') {
    const response = await apiClient.post('/api/ai/analyze', { text, task });
    return response.data;
  },

  async generateResponse(prompt, context = null) {
    const response = await apiClient.post('/api/ai/generate', { prompt, context });
    return response.data;
  }
};

// React component
import { useState } from 'react';
import { aiService } from '../services/aiClient';

export const AIAnalyzer = () => {
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);

  const handleAnalyze = async () => {
    const analysis = await aiService.analyzeText(text);
    setResult(analysis);
  };

  return (
    <div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} />
      <button onClick={handleAnalyze}>Analyze</button>
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
};
```

### License-Gating AI Features

**ALWAYS make AI features enterprise-only:**

```python
# License configuration
AI_FEATURES = {
    'ai_analysis': 'professional',      # Professional tier+
    'ai_generation': 'professional',    # Professional tier+
    'ai_training': 'enterprise',        # Enterprise tier only
    'ai_custom_models': 'enterprise'    # Enterprise tier only
}

# Feature checking
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

1. **Optional Integration**: Only add WaddleAI when AI features are needed
2. **License Gating**: AI features are typically enterprise/professional tier
3. **Performance**: AI inference can be resource-intensive - monitor usage
4. **Isolation**: Run WaddleAI as separate service for resource isolation
5. **Documentation**: Refer to WaddleAI documentation at `~/code/WaddleAI`
