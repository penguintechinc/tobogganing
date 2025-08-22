# Tobogganing Usage Guide

## 📋 Table of Contents

- [🚀 Quick Start](#-quick-start)
- [🐳 Docker Deployment](#-docker-deployment)
- [☁️ Kubernetes Deployment](#️-kubernetes-deployment)
- [🏗️ Terraform Infrastructure](#️-terraform-infrastructure)
- [📱 Mobile App Usage](#-mobile-app-usage)
- [💾 Storage & Persistence](#-storage--persistence)
- [⚙️ Configuration](#️-configuration)
- [🔧 Advanced Usage](#-advanced-usage)

---

## 🚀 Quick Start

### Docker Compose (Recommended for Testing)

```bash
# Clone repository
git clone https://github.com/penguintechinc/tobogganing.git
cd tobogganing

# Start all services
docker-compose -f deploy/docker-compose/docker-compose.dev.yml up -d

# Access services
# Manager UI: http://localhost:8000
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000
```

### Native Installation

```bash
# Build all components
./scripts/build-apps.sh

# Install and start manager
cd manager
python -m manager.main

# Install and start headend
cd headend
./build/headend

# Install native client
./clients/native/tobogganing-client init --manager-url http://localhost:8000
```

---

## 🐳 Docker Deployment

### Development Environment

```bash
# Start development stack
docker-compose -f deploy/docker-compose/docker-compose.dev.yml up -d

# View logs
docker-compose -f deploy/docker-compose/docker-compose.dev.yml logs -f

# Stop services
docker-compose -f deploy/docker-compose/docker-compose.dev.yml down
```

### Production Environment

```bash
# Production deployment
docker-compose -f deploy/docker-compose/docker-compose.prod.yml up -d

# Scale headend services
docker-compose -f deploy/docker-compose/docker-compose.prod.yml up -d --scale headend=3

# Health check
docker-compose -f deploy/docker-compose/docker-compose.prod.yml ps
```

### Docker Client

```bash
# Run Tobogganing client in Docker
docker run -d \
  --name tobogganing-client \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -e MANAGER_URL=https://manager.example.com:8000 \
  -e API_KEY=your-api-key \
  -v tobogganing-client-data:/app/data \
  tobogganing/client:latest

# Check client status
docker logs tobogganing-client

# Stop client
docker stop tobogganing-client
```

---

## ☁️ Kubernetes Deployment

### Basic Deployment

```bash
# Apply Kubernetes manifests
kubectl apply -f deploy/kubernetes/

# Check deployment status
kubectl get pods -n tobogganing

# View logs
kubectl logs -f deployment/manager -n tobogganing
```

### Helm Chart Deployment

```bash
# Add Tobogganing Helm repository
helm repo add tobogganing https://charts.tobogganing.com
helm repo update

# Install with Helm
helm install tobogganing tobogganing/tobogganing \
  --namespace tobogganing \
  --create-namespace \
  --values values.yaml

# Upgrade deployment
helm upgrade tobogganing tobogganing/tobogganing \
  --namespace tobogganing \
  --values values.yaml

# Check status
helm status tobogganing -n tobogganing
```

### Custom Values

```yaml
# values.yaml
manager:
  replicaCount: 2
  resources:
    limits:
      cpu: 2
      memory: 4Gi
    requests:
      cpu: 1
      memory: 2Gi

headend:
  replicaCount: 3
  service:
    type: LoadBalancer

database:
  type: postgresql
  host: postgres.example.com
  name: tobogganing

redis:
  enabled: true
  sentinel:
    enabled: true
```

---

## 🏗️ Terraform Infrastructure

### AWS Deployment

```bash
# Initialize Terraform
cd deploy/terraform/aws
terraform init

# Plan deployment
terraform plan -var-file="production.tfvars"

# Apply infrastructure
terraform apply -var-file="production.tfvars"

# Destroy infrastructure
terraform destroy -var-file="production.tfvars"
```

### Multi-Cloud Deployment

```bash
# Deploy to multiple regions
cd deploy/terraform/multi-cloud

# AWS + Azure + GCP
terraform workspace new production
terraform plan -var-file="multi-cloud.tfvars"
terraform apply -var-file="multi-cloud.tfvars"
```

---

## 📱 Mobile App Usage

### Android Development

```bash
# Set up Android Studio environment
./scripts/setup-android-studio.sh

# Build and deploy mobile app
./scripts/deploy-mobile.sh

# Start Android emulator
./scripts/setup-android-studio.sh --start-emulator

# Open project in Android Studio
~/open-tobogganing-mobile.sh
```

### Mobile App Installation

```bash
# Install APK to device
adb install -r clients/mobile/android/app/build/outputs/apk/debug/app-debug.apk

# Check device connection
adb devices

# View app logs
adb logcat | grep Tobogganing
```

### Mobile App Configuration

The mobile app requires the following configuration:

```json
{
  "manager_url": "https://manager.example.com:8000",
  "api_key": "your-api-key",
  "auto_connect": true,
  "biometric_auth": true
}
```

---

## 💾 Storage & Persistence

### Required Volumes for Persistence

#### Manager Service
```yaml
volumes:
  - tobogganing-manager-data:/app/data          # Application data
  - tobogganing-certificates:/app/certs         # Certificate storage
  - tobogganing-config:/app/config             # Configuration files
  - tobogganing-logs:/app/logs                 # Log files
```

#### Headend Service
```yaml
volumes:
  - tobogganing-headend-config:/app/config     # WireGuard configuration
  - tobogganing-headend-logs:/app/logs         # Traffic logs
```

#### Database
```yaml
volumes:
  - tobogganing-mysql-data:/var/lib/mysql      # MySQL data
  - tobogganing-redis-data:/data               # Redis data
```

### Optional Volumes for Advanced Usage

```yaml
volumes:
  # Backup storage
  - tobogganing-backups:/app/backups
  
  # Custom certificates
  - custom-ca-certs:/etc/ssl/certs
  
  # Monitoring data
  - prometheus-data:/prometheus
  - grafana-data:/var/lib/grafana
  
  # Traffic mirror data
  - traffic-mirror-logs:/var/log/traffic
```

### Backup Configuration

```bash
# Automated backups with S3
export BACKUP_S3_BUCKET=tobogganing-backups
export BACKUP_S3_REGION=us-east-1
export BACKUP_SCHEDULE="0 2 * * *"  # Daily at 2 AM

# Manual backup
docker exec manager python -m manager.backup create

# Restore from backup
docker exec manager python -m manager.backup restore backup-20231201.tar.gz
```

---

## ⚙️ Configuration

### Environment Variables

#### Manager Service
```bash
# Database configuration
DATABASE_URL=mysql://user:pass@host:3306/tobogganing
DB_READ_REPLICA_URL=mysql://user:pass@replica:3306/tobogganing

# Redis configuration
REDIS_URL=redis://localhost:6379
REDIS_CLUSTER_URLS=redis://node1:6379,redis://node2:6379

# Security settings
JWT_SECRET=your-super-secret-jwt-key
SESSION_TIMEOUT_HOURS=8
METRICS_TOKEN=prometheus-scraper-token

# Backup settings
BACKUP_S3_BUCKET=tobogganing-backups
BACKUP_S3_REGION=us-east-1
BACKUP_ENCRYPTION_KEY=your-backup-encryption-key

# Logging
LOG_LEVEL=info
SENTRY_DSN=https://your-sentry-dsn
```

#### Headend Server
```bash
# Manager connection
MANAGER_URL=http://manager:8000
HEADEND_AUTH_TOKEN=your-headend-auth-token

# WireGuard configuration
WIREGUARD_INTERFACE=wg0
WIREGUARD_PORT=51820
WIREGUARD_PEERS_MAX=1000

# Traffic mirroring
TRAFFIC_MIRROR_ENABLED=true
TRAFFIC_MIRROR_DESTINATIONS=10.0.0.100:4789,10.0.0.101:4789
TRAFFIC_MIRROR_PROTOCOL=VXLAN
TRAFFIC_MIRROR_SAMPLE_RATE=100

# Firewall settings
FIREWALL_ENABLED=true
FIREWALL_RULES_REFRESH_INTERVAL=300

# Syslog configuration
HEADEND_SYSLOG_ENABLED=true
HEADEND_SYSLOG_SERVER=syslog.example.com:514
HEADEND_SYSLOG_PROTOCOL=UDP

# Rate limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_RPS=1000
RATE_LIMIT_BURST=2000

# Security feeds
SECURITY_FEEDS_ENABLED=true
BLACKWEB_FEED_URL=https://blackweb.example.com/feed
SPAMHAUS_API_KEY=your-spamhaus-api-key
```

#### Client Configuration
```bash
# Manager connection
MANAGER_URL=https://manager.example.com:8000
API_KEY=your-client-api-key

# Connection settings
AUTO_CONNECT=true
RECONNECT_INTERVAL=30
CONNECTION_TIMEOUT=10

# Logging
LOG_LEVEL=info
LOG_FILE=/app/logs/client.log
```

### Command Line Arguments

#### Manager Service
```bash
python -m manager.main \
  --port 8000 \
  --workers 4 \
  --db-url mysql://user:pass@host/db \
  --redis-url redis://localhost:6379 \
  --log-level info
```

#### Headend Server
```bash
./headend \
  --listen 0.0.0.0:8080 \
  --wireguard-port 51820 \
  --manager-url http://manager:8000 \
  --config /etc/headend/config.yaml
```

#### Native Client
```bash
./tobogganing-client \
  --config /etc/tobogganing/client.yaml \
  --manager-url https://manager.example.com:8000 \
  --api-key your-api-key \
  --daemon
```

---

## 🔧 Advanced Usage

### Multi-Region Deployment

```bash
# Deploy across regions
# Region 1: US East
docker-compose -f docker-compose.us-east.yml up -d

# Region 2: EU West  
docker-compose -f docker-compose.eu-west.yml up -d

# Configure cross-region sync
export REGION_SYNC_ENABLED=true
export REGION_SYNC_PEERS=https://us-east.example.com,https://eu-west.example.com
```

### High Availability Configuration

```yaml
# docker-compose.ha.yml
services:
  manager:
    deploy:
      replicas: 3
      placement:
        max_replicas_per_node: 1
  
  headend:
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.role == worker
```

### Custom Certificate Authority

```bash
# Generate custom CA
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days 3650 -key ca-key.pem -sha256 -out ca.pem

# Configure manager to use custom CA
export CUSTOM_CA_CERT=/certs/ca.pem
export CUSTOM_CA_KEY=/certs/ca-key.pem
```

### Traffic Mirroring Setup

```bash
# Configure traffic mirroring to multiple destinations
export TRAFFIC_MIRROR_ENABLED=true
export TRAFFIC_MIRROR_DESTINATIONS="10.0.0.100:4789,10.0.0.101:4789"
export TRAFFIC_MIRROR_PROTOCOL=VXLAN
export TRAFFIC_MIRROR_FILTER="tcp port 80 or tcp port 443"
```

### Performance Tuning

```bash
# Optimize for high throughput
export HEADEND_WORKERS=8
export HEADEND_MAX_CONNECTIONS=10000
export HEADEND_BUFFER_SIZE=65536

# Optimize database connections
export DB_POOL_SIZE=20
export DB_MAX_OVERFLOW=30
export DB_POOL_TIMEOUT=30
```

### Monitoring & Alerting

```bash
# Configure Prometheus alerting
export PROMETHEUS_ALERT_MANAGER_URL=http://alertmanager:9093

# Configure Grafana notifications
export GRAFANA_NOTIFICATION_CHANNELS="slack,email,pagerduty"

# Custom metrics collection
export CUSTOM_METRICS_ENABLED=true
export CUSTOM_METRICS_INTERVAL=30
```

### Development Workflow

```bash
# Development setup
./scripts/setup-dev-environment.sh

# Build and test
./scripts/build-apps.sh
make test

# Deploy to development environment
docker-compose -f docker-compose.dev.yml up -d

# Run integration tests
make test-integration

# Deploy mobile app to emulator
./scripts/deploy-mobile.sh

# View development logs
docker-compose -f docker-compose.dev.yml logs -f
```

This comprehensive usage guide covers all aspects of deploying, configuring, and managing Tobogganing in various environments, from development to enterprise production deployments.