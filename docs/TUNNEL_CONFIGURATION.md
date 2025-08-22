# 🚇 Tunnel Configuration Guide

## 📋 Overview

Tobogganing supports both **full tunnel** and **split tunnel** configurations for client connections. This allows administrators to control which traffic flows through the VPN tunnel and which traffic goes directly to the internet.

## 🎯 Tunnel Modes

### Full Tunnel (Default)
- **All traffic** flows through the VPN tunnel
- Provides maximum security and control
- All internet traffic is inspected and filtered
- Default configuration for new clients

### Split Tunnel
- **Selected traffic** bypasses the VPN tunnel
- Specified domains and IP ranges go directly to internet
- Reduces bandwidth usage on VPN infrastructure
- Useful for trusted services and local resources

## 🛠️ Configuration

### API Endpoint

Update a client's tunnel configuration using the REST API:

```bash
PUT /api/v1/clients/{client_id}/tunnel-config
Authorization: Bearer {api_key_or_jwt_token}
Content-Type: application/json
```

### Request Body

```json
{
  "tunnel_mode": "split",
  "split_tunnel_routes": [
    "*.example.com",
    "192.168.1.0/24",
    "10.0.0.0/8",
    "2001:db8::/32",
    "trusted-service.com"
  ]
}
```

### Supported Route Formats

| Type | Example | Description |
|------|---------|-------------|
| **Domain** | `example.com` | Exact domain match |
| **Wildcard Domain** | `*.example.com` | All subdomains |
| **IPv4 Address** | `192.168.1.1` | Single IPv4 address |
| **IPv4 CIDR** | `192.168.0.0/16` | IPv4 network range |
| **IPv6 Address** | `2001:db8::1` | Single IPv6 address |
| **IPv6 CIDR** | `2001:db8::/32` | IPv6 network range |

## 💻 Examples

### Enable Split Tunnel for Local Network

Allow direct access to local network while routing all other traffic through VPN:

```bash
curl -X PUT https://manager.example.com/api/v1/clients/client-123/tunnel-config \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tunnel_mode": "split",
    "split_tunnel_routes": [
      "192.168.1.0/24",
      "10.0.0.0/8"
    ]
  }'
```

### Enable Split Tunnel for Cloud Services

Bypass VPN for specific cloud services:

```bash
curl -X PUT https://manager.example.com/api/v1/clients/client-123/tunnel-config \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tunnel_mode": "split",
    "split_tunnel_routes": [
      "*.amazonaws.com",
      "*.azure.com",
      "*.googleapis.com"
    ]
  }'
```

### Switch Back to Full Tunnel

```bash
curl -X PUT https://manager.example.com/api/v1/clients/client-123/tunnel-config \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tunnel_mode": "full",
    "split_tunnel_routes": []
  }'
```

## 🔒 Security Considerations

### ⚠️ Split Tunnel Risks
- Traffic bypassing the tunnel is **not inspected** by security policies
- Direct internet traffic may be **visible to ISPs**
- Bypassed traffic **not protected** by corporate firewall
- May expose internal IP addresses to external services

### ✅ Best Practices
1. **Default to full tunnel** for maximum security
2. Only enable split tunnel for **trusted services**
3. **Regularly review** split tunnel configurations
4. **Monitor** bypassed traffic destinations
5. Use split tunnel for **performance optimization** only when necessary

## 📊 Monitoring

### Check Current Configuration

The current tunnel configuration is returned when fetching client config:

```bash
GET /api/v1/clients/{client_id}/config
Authorization: Bearer {api_key}
```

Response includes:
```json
{
  "client_id": "client-123",
  "tunnel_mode": "split",
  "split_tunnel_routes": [
    "192.168.1.0/24",
    "*.example.com"
  ],
  ...
}
```

### Metrics

Monitor tunnel usage through Prometheus metrics:
- `tobogganing_client_bytes_sent` - Bytes sent through tunnel
- `tobogganing_client_bytes_received` - Bytes received through tunnel
- `tobogganing_client_connection_uptime_seconds` - Tunnel uptime

## 🎭 Use Cases

### Corporate Environment
- Full tunnel for **remote employees**
- Split tunnel for **branch offices** with local servers
- Full tunnel for **contractors** and third-party access

### Development Teams
- Split tunnel for **local development** servers
- Bypass for **CI/CD** systems
- Full tunnel for **production** access

### Performance Optimization
- Bypass **streaming services** to reduce VPN load
- Direct access to **CDN endpoints**
- Local **printer and device** access

## 🔧 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **Routes not applied** | Restart client after configuration change |
| **DNS resolution issues** | Check if DNS server is in bypass list |
| **Slow performance** | Consider split tunnel for high-bandwidth services |
| **Can't access local resources** | Add local network to split tunnel routes |

### Validation

The API validates all routes before accepting configuration:
- Domains must be valid format
- IP addresses must be valid IPv4 or IPv6
- CIDR ranges must have valid network masks

Invalid routes return `400 Bad Request` with error details.

## 📝 Related Documentation

- [API Documentation](./API.md)
- [Client Installation](./CLIENT_INSTALLATION.md)
- [Network Architecture](./ARCHITECTURE.md)
- [Security Features](./FEATURES.md)