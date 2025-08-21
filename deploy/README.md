# SASEWaddle Deployment Guide

This directory contains deployment configurations and documentation for SASEWaddle across different environments and platforms.

## Deployment Options

### 1. Kubernetes (Production)
- **Path**: `kubernetes/`
- **Best for**: Production environments, high availability
- **Features**: Auto-scaling, load balancing, persistent storage, monitoring

### 2. Docker Compose (Development/Small Production)
- **Path**: `docker-compose/`
- **Best for**: Development, testing, small production deployments
- **Features**: Easy setup, local development, quick testing

### 3. Terraform (Cloud Infrastructure)
- **Path**: `terraform/`
- **Best for**: Cloud deployments with infrastructure as code
- **Features**: AWS EKS, RDS, ElastiCache, Load Balancers, DNS

## Quick Start

### Development Environment (Docker Compose)

```bash
# Clone repository
git clone https://github.com/your-org/sasewaddle.git
cd sasewaddle/deploy/docker-compose

# Configure environment
cp .env.example .env
nano .env  # Edit configuration

# Start services
docker-compose -f docker-compose.dev.yml up -d

# Access services
# Manager: http://localhost:8000
# WireGuard: UDP 51820
# Proxy: http://localhost:8080
```

### Production Environment (Kubernetes)

```bash
# Navigate to Kubernetes configs
cd sasewaddle/deploy/kubernetes

# Review and customize configurations
nano configmap.yaml
nano secrets.yaml

# Deploy to cluster
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml
kubectl apply -f .

# Check deployment
kubectl get pods -n sasewaddle
kubectl get services -n sasewaddle
```

### Cloud Deployment (Terraform)

```bash
# Navigate to Terraform configs
cd sasewaddle/deploy/terraform

# Configure variables
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars

# Initialize and deploy
terraform init
terraform plan
terraform apply

# Get connection info
terraform output connection_info
```

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Clients       │    │   Load Balancer  │    │   Kubernetes    │
│                 │    │                  │    │   Cluster       │
│ ┌─────────────┐ │    │ ┌──────────────┐ │    │ ┌─────────────┐ │
│ │ Native App  │─┼────┼─│ Manager ALB  │─┼────┼─│ Manager     │ │
│ └─────────────┘ │    │ └──────────────┘ │    │ │ Service     │ │
│ ┌─────────────┐ │    │ ┌──────────────┐ │    │ └─────────────┘ │
│ │ Docker      │─┼────┼─│ Headend NLB  │─┼────┼─│ Headend     │ │
│ │ Container   │ │    │ │ (WireGuard)  │ │    │ │ Service     │ │
│ └─────────────┘ │    │ └──────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └──────────────────┘    │ ┌─────────────┐ │
                                               │ │ Redis       │ │
                                               │ └─────────────┘ │
                                               └─────────────────┘
```

## Component Overview

### Manager Service
- **Purpose**: Central orchestration and certificate management
- **Technology**: Python 3.12 + py4web + asyncio
- **Database**: SQLite (local) or PostgreSQL (production)
- **Caching**: Redis for session management and JWT tokens
- **Features**:
  - REST API for client management
  - Web interface for administration
  - Certificate generation and rotation
  - Multi-datacenter orchestration
  - SSO/SAML2 integration

### Headend Server
- **Purpose**: WireGuard termination and traffic proxy
- **Technology**: Go + WireGuard + multi-protocol proxy
- **Features**:
  - WireGuard VPN server
  - HTTP/HTTPS/TCP/UDP proxy with authentication
  - Traffic mirroring for IDS/IPS
  - High-performance concurrent connections
  - External IdP integration

### Client Applications
- **Docker Client**: Containerized for easy deployment
- **Native Client**: Cross-platform binaries (Mac, Windows, Linux)
- **Features**:
  - Automatic configuration from Manager
  - Certificate-based authentication
  - Health monitoring and auto-reconnect
  - GUI and CLI interfaces

## Configuration

### Environment Variables

Key configuration variables across all deployment methods:

```bash
# Core Configuration
MANAGER_URL=https://manager.example.com:8000
CLUSTER_ID=production
LOG_LEVEL=info

# Authentication
JWT_SECRET=your-super-secret-jwt-key
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=secure-password
REDIS_PASSWORD=secure-redis-password

# WireGuard
WIREGUARD_NETWORK=10.200.0.0/16
WIREGUARD_PORT=51820

# Traffic Mirroring (optional)
TRAFFIC_MIRROR_ENABLED=true
TRAFFIC_MIRROR_DESTINATIONS=10.0.0.100:4789
TRAFFIC_MIRROR_PROTOCOL=VXLAN
```

### Network Requirements

#### Ports
- **51820/UDP**: WireGuard VPN
- **8000/TCP**: Manager API and Web UI
- **8080/TCP**: Headend HTTP/HTTPS proxy
- **6379/TCP**: Redis (internal)

#### Firewall Rules
```bash
# Allow WireGuard
ufw allow 51820/udp

# Allow Manager API
ufw allow 8000/tcp

# Allow Headend proxy
ufw allow 8080/tcp

# Internal communication (if needed)
ufw allow from 10.200.0.0/16
```

## Security Considerations

### 1. Certificate Management
- X.509 certificates for WireGuard authentication
- Automatic certificate rotation
- Certificate revocation support
- Secure key storage

### 2. Authentication
- Dual authentication: certificates + JWT/SSO
- Integration with external IdPs (SAML2, OAuth2)
- Role-based access control
- Session management with Redis

### 3. Network Security
- Zero Trust Network Architecture (ZTNA)
- Network segmentation with WireGuard
- Traffic encryption and authentication
- Network policies in Kubernetes

### 4. Data Protection
- Secrets management (Kubernetes Secrets, AWS Secrets Manager)
- Encrypted storage volumes
- TLS everywhere
- Audit logging

## Monitoring and Observability

### Metrics
- Prometheus metrics collection
- Grafana dashboards
- Custom SASEWaddle metrics:
  - Active connections
  - Certificate expiry
  - Authentication failures
  - Traffic throughput

### Logging
- Structured logging (JSON)
- Log aggregation (ELK stack compatible)
- Audit trails
- Error tracking

### Health Checks
- Kubernetes liveness/readiness probes
- Docker Compose health checks
- Application-level health endpoints
- Certificate validity monitoring

## Backup and Recovery

### Data Backup
```bash
# Manager data
kubectl create job backup-manager --from=cronjob/backup-manager

# Redis data
kubectl exec -it redis-pod -- redis-cli --rdb /tmp/backup.rdb

# Certificates
kubectl exec -it manager-pod -- tar czf /tmp/certs.tar.gz /app/certs
```

### Disaster Recovery
1. **Infrastructure**: Terraform for reproducible infrastructure
2. **Configuration**: GitOps with configuration in version control
3. **Data**: Automated backups to S3/cloud storage
4. **Certificates**: Certificate Authority backup and recovery

## Scaling and Performance

### Horizontal Scaling
- **Manager**: 2+ instances with shared Redis
- **Headend**: Limited by WireGuard interface (use multiple clusters)
- **Redis**: Clustering for high availability

### Vertical Scaling
- **Manager**: CPU/memory based on API load
- **Headend**: Network I/O intensive, needs higher bandwidth
- **Redis**: Memory-based on session storage needs

### Performance Tuning
```yaml
# Kubernetes resource requests/limits
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "1"
```

## Troubleshooting

### Common Issues

1. **WireGuard interface creation failed**
   ```bash
   # Check kernel modules
   lsmod | grep wireguard
   modprobe wireguard
   
   # Check container permissions
   kubectl describe pod headend-pod
   ```

2. **Certificate authentication failed**
   ```bash
   # Check certificate validity
   kubectl exec -it manager-pod -- openssl x509 -in /app/certs/client.crt -text -noout
   
   # Regenerate certificates
   kubectl exec -it manager-pod -- python -m manager.tools.regen_certs
   ```

3. **Redis connection issues**
   ```bash
   # Test Redis connectivity
   kubectl exec -it redis-pod -- redis-cli ping
   
   # Check authentication
   kubectl exec -it redis-pod -- redis-cli -a $REDIS_PASSWORD ping
   ```

### Debug Commands

```bash
# Kubernetes
kubectl logs -f deployment/manager -n sasewaddle
kubectl logs -f deployment/headend -n sasewaddle
kubectl describe pod -l app=manager -n sasewaddle

# Docker Compose
docker-compose logs -f manager
docker-compose logs -f headend
docker-compose exec manager /bin/bash

# Application logs
tail -f /app/logs/manager.log
journalctl -u wireguard-wg0 -f
```

## Support and Documentation

- **Issues**: https://github.com/your-org/sasewaddle/issues
- **Documentation**: https://docs.sasewaddle.com
- **API Reference**: https://api.sasewaddle.com/docs
- **Community**: https://community.sasewaddle.com

## License

SASEWaddle is open source software. See [LICENSE](../LICENSE) for details.