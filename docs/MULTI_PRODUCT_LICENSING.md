# 🔐 Multi-Product Licensing Guide

## 📋 Overview

The PenguinTech licensing system supports **multiple products under a single license key**. This allows customers to purchase one license that covers SASEWaddle, SquawkDNS, WaddleBot, and future products at different tiers.

## 🎯 Product Portfolio

### 🦭 SASEWaddle (VPN/SASE)
- **Community**: Core VPN features, unlimited clients/headends
- **Professional**: Adds metrics, advanced firewall, VRF/OSPF
- **Enterprise**: Adds SSO, LDAP, MFA, traffic mirroring, custom branding

### 🦆 SquawkDNS (DNS Filtering)
- **Community**: Basic DNS filtering, unlimited queries
- **Professional**: Advanced filtering, analytics, custom blocklists
- **Enterprise**: Threat intelligence, centralized management, SSO

### 🤖 WaddleBot (Chat Bot)
- **Community**: Basic chat commands, single server
- **Professional**: Multi-server, cloud storage, analytics
- **Enterprise**: Custom integrations, SSO, audit logging

### 🚀 Future Products
- Additional products will be added to the same licensing system
- Customers can upgrade individual products or add new ones to existing licenses

## 🔑 License Key Format

License keys work across **all products**:
```
PENG-XXXX-XXXX-XXXX-XXXX-YYYY
```

Where:
- `PENG` - PenguinTech product identifier
- `XXXX` - Random alphanumeric segments  
- `YYYY` - Checksum for validation

**Example**: `PENG-A1B2-C3D4-E5F6-G7H8-9IJK`

## 📊 Multi-Product License Examples

### Basic Bundle
```json
{
  "license_key": "PENG-A1B2-C3D4-E5F6-G7H8-9IJK",
  "customer": "Acme Corp",
  "products": {
    "sasewaddle": "community",
    "squawkdns": "professional"
  }
}
```

### Enterprise Bundle
```json
{
  "license_key": "PENG-ENT1-ERPX-2024-PROD-ABC1",
  "customer": "Enterprise Inc",
  "products": {
    "sasewaddle": "enterprise",
    "squawkdns": "enterprise", 
    "waddlebot": "professional"
  }
}
```

## 🔌 API Integration

### Universal Validation Endpoint

**All products** use the same validation endpoint:

```bash
POST https://license.penguintech.io/api/validate
Content-Type: application/json

{
  "license_key": "PENG-A1B2-C3D4-E5F6-G7H8-9IJK",
  "product": "sasewaddle"
}
```

**Response:**
```json
{
  "valid": true,
  "product": "sasewaddle",
  "tier": "professional",
  "features": [
    "wireguard_vpn",
    "client_metrics",
    "prometheus_export",
    "advanced_firewall"
  ],
  "all_products": {
    "sasewaddle": "professional",
    "squawkdns": "enterprise"
  },
  "expires_at": "2025-12-31T23:59:59Z"
}
```

### Feature Check Endpoint

```bash
POST https://license.penguintech.io/api/check_feature
Content-Type: application/json

{
  "license_key": "PENG-A1B2-C3D4-E5F6-G7H8-9IJK",
  "product": "sasewaddle",
  "feature": "client_metrics"
}
```

**Response:**
```json
{
  "enabled": true,
  "product": "sasewaddle",
  "tier": "professional",
  "message": "Feature enabled"
}
```

## 💻 Product Integration Examples

### SASEWaddle Integration
```python
import requests

def check_sasewaddle_license():
    response = requests.post(
        'https://license.penguintech.io/api/validate',
        json={
            'license_key': os.getenv('LICENSE_KEY'),
            'product': 'sasewaddle'
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        if data['valid']:
            return {
                'tier': data['tier'],
                'features': data['features'],
                'expires_at': data['expires_at']
            }
    
    return {'tier': 'community', 'features': get_community_features()}
```

### SquawkDNS Integration
```python
def check_squawkdns_feature(feature):
    response = requests.post(
        'https://license.penguintech.io/api/check_feature',
        json={
            'license_key': os.getenv('LICENSE_KEY'),
            'product': 'squawkdns',
            'feature': feature
        }
    )
    
    if response.status_code == 200:
        return response.json()['enabled']
    
    # Default to community features
    community_features = ['dns_server', 'basic_filtering', 'unlimited_queries']
    return feature in community_features
```

### WaddleBot Integration
```javascript
const checkWaddleBotLicense = async () => {
  try {
    const response = await fetch('https://license.penguintech.io/api/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        license_key: process.env.LICENSE_KEY,
        product: 'waddlebot'
      })
    });
    
    const data = await response.json();
    return data.valid ? data : { tier: 'community' };
  } catch (error) {
    return { tier: 'community' }; // Fallback to community
  }
};
```

## 🛒 License Management

### Sales Team Features

The license server provides management capabilities for creating multi-product licenses:

```python
# Create multi-product license
license_data = {
    'customer_name': 'Enterprise Corp',
    'customer_email': 'admin@enterprise.com',
    'organization': 'Enterprise Corp',
    'products': {
        'sasewaddle': 'enterprise',
        'squawkdns': 'professional',
        'waddlebot': 'community'
    },
    'expires_at': datetime(2025, 12, 31),
    'notes': 'Enterprise bundle with custom SASEWaddle tier'
}
```

### Product Addition

Add new products to existing licenses:
```python
# Add WaddleBot to existing SASEWaddle license
existing_license.products['waddlebot'] = 'professional'
```

### Tier Upgrades

Upgrade individual products:
```python
# Upgrade SquawkDNS from professional to enterprise
license.products['squawkdns'] = 'enterprise'
```

## 📈 Pricing Strategy

### Individual Products
- **Community**: Free (all products)
- **Professional**: $99/month per product
- **Enterprise**: $299/month per product

### Bundle Discounts
- **2 Products**: 15% discount
- **3+ Products**: 25% discount
- **Enterprise Bundle**: Custom pricing

### Example Pricing
```
Single Product Professional: $99/month
Two Product Bundle:         $168/month (15% off)
Three Product Bundle:       $222/month (25% off)
Enterprise Bundle:          Contact sales
```

## 🔍 Troubleshooting

### License Not Found for Product
```bash
# Check what products are available in your license
curl -X POST https://license.penguintech.io/api/validate \
  -H "Content-Type: application/json" \
  -d '{"license_key": "YOUR-LICENSE", "product": "sasewaddle"}'

# Response will show available_products if product not found
{
  "valid": false,
  "message": "Product 'waddlebot' not included in this license",
  "available_products": ["sasewaddle", "squawkdns"]
}
```

### Feature Not Available
```bash
# Check if feature requires higher tier
curl -X POST https://license.penguintech.io/api/check_feature \
  -H "Content-Type: application/json" \
  -d '{
    "license_key": "YOUR-LICENSE",
    "product": "sasewaddle", 
    "feature": "sso_authentication"
  }'
```

### Legacy Endpoint Support

Old endpoints still work for backward compatibility:
- `POST /api/sasewaddle/validate` → redirects to `/api/validate`
- `POST /api/sasewaddle/check_feature` → redirects to `/api/check_feature`

## 🔐 Security Features

### License Validation
- **Server-side validation**: All checks happen on license.penguintech.io
- **Caching**: Products cache validation for 1 hour to reduce API calls
- **Fallback**: Products gracefully fall back to community features if license server unreachable
- **Audit trail**: All validations are logged for compliance

### Rate Limiting
- **Per-license limits**: Prevent abuse of validation endpoints
- **IP-based limits**: Protect against brute force attacks
- **Graduated responses**: Temporary blocks for suspicious activity

## 📝 Migration Guide

### From Single-Product to Multi-Product

**Old SASEWaddle validation:**
```python
# Old way (still works)
response = requests.post(
    'https://license.penguintech.io/api/sasewaddle/validate',
    json={'license_key': LICENSE_KEY}
)
```

**New multi-product validation:**
```python
# New way (recommended)
response = requests.post(
    'https://license.penguintech.io/api/validate',
    json={
        'license_key': LICENSE_KEY,
        'product': 'sasewaddle'
    }
)
```

### Database Schema Migration

Sales teams need to migrate existing licenses:
```sql
-- Old schema had single product/tier
-- New schema uses JSON products field

UPDATE licenses 
SET products = JSON_OBJECT(
  COALESCE(product, 'squawkdns'), 
  COALESCE(license_tier, 'basic')
)
WHERE products IS NULL;
```

## 🔗 Related Documentation

- [SASEWaddle Licensing](./LICENSING.md) - SASEWaddle-specific licensing details
- [API Documentation](./API.md) - Technical API reference  
- [Authentication Guide](./AUTHENTICATION.md) - Authentication across products
- [License Server Documentation](https://github.com/penguintech/license-server) - Server setup and management