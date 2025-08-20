# SASEWaddle Quick Start Guide

## Prerequisites

- Docker and Docker Compose
- Go 1.21+ (for building from source)
- Python 3.12+ (for Manager development)
- Node.js 18+ (for website development)

## Quick Start with Docker Compose

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/SASEWaddle.git
cd SASEWaddle
```

### 2. Configure Environment

Copy the example environment file and adjust settings:

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Start the Stack

```bash
# Start all services
docker-compose -f docker-compose.local.yml up -d

# Check status
docker-compose -f docker-compose.local.yml ps

# View logs
docker-compose -f docker-compose.local.yml logs -f
```

### 4. Access Services

- **Manager Portal**: http://localhost:8000
  - Default admin credentials are shown in logs on first startup
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
  - Default: admin/admin

## Building from Source

### Build All Components

```bash
make build
```

### Build Individual Components

```bash
# Manager Service
make build-manager

# Headend Proxy
make build-headend

# Native Client
make build-client

# Website
make build-website
```

## Testing

### Run All Tests

```bash
make test
```

### Run Specific Tests

```bash
# Go tests
make test-go

# Python tests  
make test-python
```

## Deployment

### Production with Kubernetes

```bash
# Apply Kubernetes manifests
kubectl apply -f deploy/kubernetes/

# Check deployment status
kubectl get pods -n sasewaddle
```

### Production with Docker Swarm

```bash
# Initialize swarm (if needed)
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.production.yml sasewaddle

# Check services
docker service ls
```

## Client Installation

### Docker Client

```bash
docker run -d \
  --name sasewaddle-client \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -e MANAGER_URL=https://manager.example.com \
  -e API_KEY=your-api-key \
  sasewaddle/client:latest
```

### Native Client

#### Linux/macOS

```bash
# Download binary
curl -L https://github.com/yourusername/SASEWaddle/releases/latest/download/sasewaddle-client-$(uname -s)-$(uname -m) -o sasewaddle-client
chmod +x sasewaddle-client

# Run with config
./sasewaddle-client --config config.yaml
```

#### Windows

```powershell
# Download from releases page
# Run with administrator privileges
sasewaddle-client.exe --config config.yaml
```

## Configuration

### Manager Service

Configuration via environment variables:

```bash
# Database
DB_TYPE=mysql                    # mysql, postgresql, sqlite
DB_HOST=localhost
DB_PORT=3306
DB_USER=sasewaddle
DB_PASSWORD=secure_password
DB_NAME=sasewaddle

# Redis
REDIS_URL=redis://localhost:6379

# Security
JWT_SECRET=your-secret-key
SESSION_TIMEOUT_HOURS=8
```

### Headend Server

```bash
# Manager connection
MANAGER_URL=http://manager:8000
HEADEND_AUTH_TOKEN=your-token

# Traffic mirroring
TRAFFIC_MIRROR_ENABLED=true
TRAFFIC_MIRROR_DESTINATIONS=10.0.0.100:4789

# Syslog
HEADEND_SYSLOG_ENABLED=true
HEADEND_SYSLOG_SERVER=syslog.example.com:514
```

## Monitoring

### Prometheus Metrics

Available at `/metrics` endpoints:

- Manager: http://localhost:8001/metrics
- Headend: http://localhost:8080/metrics

### Health Checks

- Manager: http://localhost:8000/healthz
- Headend: http://localhost:8080/healthz

### Logs

```bash
# View all logs
docker-compose -f docker-compose.local.yml logs

# View specific service logs
docker-compose -f docker-compose.local.yml logs manager
docker-compose -f docker-compose.local.yml logs headend-us-east
```

## Troubleshooting

### Common Issues

1. **Port conflicts**: Check if ports are already in use
   ```bash
   netstat -tulpn | grep -E '8000|3306|6379'
   ```

2. **Database connection issues**: Verify database is running
   ```bash
   docker-compose -f docker-compose.local.yml ps mysql
   ```

3. **WireGuard module not loaded**: 
   ```bash
   # Linux
   sudo modprobe wireguard
   
   # Check if loaded
   lsmod | grep wireguard
   ```

### Debug Mode

Enable debug logging:

```bash
# Set in environment
export LOG_LEVEL=DEBUG

# Or in docker-compose
environment:
  LOG_LEVEL: DEBUG
```

## Getting Help

- Documentation: [docs/](../docs/)
- Issues: [GitHub Issues](https://github.com/yourusername/SASEWaddle/issues)
- Community: [Discord/Slack]

## Next Steps

- [Architecture Overview](ARCHITECTURE.md)
- [Admin Guide](ADMIN_GUIDE.md)
- [Developer Guide](DEVELOPER_GUIDE.md)
- [API Reference](API_REFERENCE.md)