# 📚 SASEWaddle API Documentation

> **Version**: 1.1.0  
> **Last Updated**: 2025-08-21

## 📋 Table of Contents

- [🔐 Authentication](#-authentication)
- [🎛️ Manager API](#️-manager-api)
- [🌐 Headend API](#-headend-api)
- [🖥️ Web Portal API](#️-web-portal-api)
- [📊 Analytics API](#-analytics-api)
- [🔥 Firewall API](#-firewall-api)
- [🌍 Network Management API](#-network-management-api)
- [📦 Backup API](#-backup-api)

---

## 🔐 Authentication

### JWT Authentication

All API endpoints (except public health checks) require JWT authentication.

**Request Header:**
```http
Authorization: Bearer <jwt_token>
```

**Token Generation:**
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_at": "2025-08-22T12:00:00Z",
  "user": {
    "id": "user-123",
    "username": "admin",
    "role": "admin"
  }
}
```

---

## 🎛️ Manager API

### Client Management

#### Register New Client
```http
POST /api/v1/clients/register
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "client-001",
  "type": "native",
  "cluster_id": "cluster-us-east",
  "public_key": "..."
}
```

#### Get Client Configuration
```http
GET /api/v1/clients/{client_id}/config
Authorization: Bearer <token>
```

**Response:**
```json
{
  "client_id": "client-001",
  "wireguard": {
    "private_key": "...",
    "address": "10.0.0.2/32",
    "dns": ["1.1.1.1", "8.8.8.8"]
  },
  "endpoints": [
    {
      "public_key": "...",
      "endpoint": "headend1.example.com:51820",
      "allowed_ips": ["0.0.0.0/0"]
    }
  ]
}
```

#### Revoke Client Access
```http
POST /api/v1/clients/{client_id}/revoke
Authorization: Bearer <token>
```

### Certificate Management

#### Generate Certificates
```http
POST /api/v1/certs/generate
Authorization: Bearer <token>
Content-Type: application/json

{
  "type": "client",
  "subject": "CN=client-001",
  "validity_days": 365
}
```

#### List Certificates
```http
GET /api/v1/certs
Authorization: Bearer <token>
```

#### Revoke Certificate
```http
POST /api/v1/certs/{serial}/revoke
Authorization: Bearer <token>
```

### System Status

#### Health Check (Authenticated)
```http
GET /health
Authorization: Bearer <token>
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.1.0",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "wireguard": "healthy"
  },
  "timestamp": "2025-08-21T10:00:00Z"
}
```

#### Kubernetes Health Check
```http
GET /healthz
```

**Response:**
```
OK
```

#### Prometheus Metrics
```http
GET /metrics
Authorization: Bearer <metrics_token>
```

---

## 🌐 Headend API

### Authentication

#### Authenticate User/Service
```http
POST /api/v1/auth
Content-Type: application/json

{
  "token": "jwt_token",
  "certificate": "base64_encoded_cert"
}
```

### Tunnel Management

#### List Active Tunnels
```http
GET /api/v1/tunnels
Authorization: Bearer <headend_token>
```

**Response:**
```json
{
  "tunnels": [
    {
      "peer_id": "client-001",
      "public_key": "...",
      "endpoint": "203.0.113.1:51820",
      "last_handshake": "2025-08-21T09:58:00Z",
      "rx_bytes": 1048576,
      "tx_bytes": 2097152
    }
  ]
}
```

### Routing Configuration

#### Configure Routes
```http
POST /api/v1/routes
Authorization: Bearer <headend_token>
Content-Type: application/json

{
  "routes": [
    {
      "destination": "10.0.0.0/8",
      "gateway": "10.0.0.1",
      "interface": "wg0"
    }
  ]
}
```

---

## 🖥️ Web Portal API

### User Management

#### Create User (Admin Only)
```http
POST /api/web/user
Authorization: Bearer <token>
Content-Type: application/json

{
  "username": "newuser",
  "email": "user@example.com",
  "password": "secure_password",
  "role": "reporter"
}
```

#### Toggle User Status
```http
POST /api/web/user/{user_id}/toggle
Authorization: Bearer <token>
```

### Dashboard Statistics

#### Get Real-time Stats
```http
GET /api/web/stats
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_clients": 150,
  "active_connections": 87,
  "total_bandwidth": 1073741824,
  "auth_success_rate": 98.5,
  "top_endpoints": [
    {
      "endpoint": "headend1.example.com",
      "connections": 45
    }
  ]
}
```

---

## 📊 Analytics API

### Headend Analytics

#### Get Headend Details
```http
GET /api/analytics/headend/{headend_id}/details
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "headend_id": "headend-001",
    "hostname": "headend1.example.com",
    "status": "healthy",
    "connection_stats": {
      "active_connections": 45,
      "total_connections": 1250,
      "bytes_proxied": 5368709120
    },
    "system_metrics": {
      "cpu_usage_percent": 35,
      "memory_usage_mb": 2048,
      "disk_usage_percent": 45
    }
  }
}
```

### Client Analytics

#### Get Client Details
```http
GET /api/analytics/client/{client_id}/details
Authorization: Bearer <token>
```

---

## 🔥 Firewall API

### Rule Management

#### Create Firewall Rule
```http
POST /api/web/firewall/rule
Authorization: Bearer <token>
Content-Type: application/json

{
  "user_id": "user-123",
  "rule_type": "domain",
  "name": "Allow Internal Sites",
  "domain": "*.internal.company.com",
  "action": "allow",
  "priority": 10
}
```

#### Delete Firewall Rule
```http
DELETE /api/web/firewall/rule/{rule_id}
Authorization: Bearer <token>
```

#### Get User Rules
```http
GET /api/web/firewall/user/{user_id}/rules
Authorization: Bearer <token>
```

### Access Testing

#### Test Access
```http
POST /api/web/firewall/check
Authorization: Bearer <token>
Content-Type: application/json

{
  "user_id": "user-123",
  "target": "internal.company.com",
  "port": 443,
  "protocol": "tcp"
}
```

**Response:**
```json
{
  "allowed": true,
  "matched_rule": {
    "id": "rule-456",
    "name": "Allow Internal Sites",
    "type": "domain"
  }
}
```

#### Export Rules for Headend
```http
GET /api/web/firewall/user/{user_id}/export
Authorization: Bearer <token>
```

---

## 🌍 Network Management API

### VRF Management

#### Create VRF
```http
POST /api/web/network/vrf
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "customer-a",
  "description": "Customer A Network",
  "rd": "65000:100",
  "ip_ranges": ["10.1.0.0/16", "192.168.100.0/24"]
}
```

#### Delete VRF
```http
DELETE /api/web/network/vrf/{vrf_id}
Authorization: Bearer <token>
```

### OSPF Configuration

#### Configure OSPF for VRF
```http
PUT /api/web/network/vrf/{vrf_id}/ospf
Authorization: Bearer <token>
Content-Type: application/json

{
  "area_id": "0.0.0.0",
  "area_type": "backbone",
  "networks": ["10.1.0.0/16"],
  "auth_type": "md5",
  "auth_key": "secret"
}
```

#### Get FRR Configuration
```http
GET /api/web/network/vrf/{vrf_id}/config
Authorization: Bearer <token>
```

#### Get OSPF Neighbors
```http
GET /api/web/network/vrf/{vrf_id}/neighbors
Authorization: Bearer <token>
```

### Port Configuration

#### Get Headend Port Configuration
```http
GET /api/web/ports/headend/{headend_id}
Authorization: Bearer <token>
```

#### Update Port Configuration
```http
POST /api/web/ports/headend/{headend_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "tcp_ranges": "8080-8090,9000,9500-9600",
  "udp_ranges": "5000-5100,6000",
  "cluster_id": "cluster-us-east"
}
```

---

## 📦 Backup API

### Backup Operations

#### Create Backup
```http
POST /api/v1/backup/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "backup_type": "full",
  "compress": true,
  "encrypt": true,
  "storage": "s3"
}
```

#### List Backups
```http
GET /api/v1/backup/list
Authorization: Bearer <token>
```

#### Restore Backup
```http
POST /api/v1/backup/restore
Authorization: Bearer <token>
Content-Type: application/json

{
  "backup_id": "backup-20250821-100000",
  "verify_checksum": true
}
```

#### Schedule Backup
```http
POST /api/v1/backup/schedule
Authorization: Bearer <token>
Content-Type: application/json

{
  "cron": "0 2 * * *",
  "backup_type": "incremental",
  "retention_days": 30
}
```

---

## 📝 Error Responses

All API endpoints return consistent error responses:

```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {
    "field": "Additional error details"
  },
  "timestamp": "2025-08-21T10:00:00Z"
}
```

**Common Error Codes:**
- `401`: Unauthorized - Invalid or missing authentication
- `403`: Forbidden - Insufficient permissions
- `404`: Not Found - Resource does not exist
- `400`: Bad Request - Invalid request parameters
- `500`: Internal Server Error - Server-side error

---

## 🔄 Rate Limiting

API endpoints are rate-limited to prevent abuse:

- **Default**: 100 requests per minute per IP
- **Authenticated**: 1000 requests per minute per user
- **Admin**: 5000 requests per minute

Rate limit headers are included in responses:
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1692619200
```

---

## 📖 Additional Resources

- [OpenAPI Specification](/api/docs)
- [Postman Collection](https://github.com/your-org/sasewaddle/tree/main/docs/postman)
- [SDK Documentation](./SDK.md)
- [Webhook Events](./WEBHOOKS.md)

---

*For support and questions, contact the development team or open an issue on [GitHub](https://github.com/your-org/sasewaddle)*