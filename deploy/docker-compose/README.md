# SASEWaddle Docker Compose Deployment

This directory contains Docker Compose configurations for deploying SASEWaddle in different environments.

## Files

- `docker-compose.yml` - Production deployment configuration
- `docker-compose.dev.yml` - Development deployment configuration
- `.env.example` - Environment variables template
- `config/` - Configuration files for services

## Quick Start

### Development Deployment

1. **Clone and configure**:
   ```bash
   git clone https://github.com/your-org/sasewaddle.git
   cd sasewaddle/deploy/docker-compose
   cp .env.example .env
   ```

2. **Edit environment variables**:
   ```bash
   nano .env
   # Modify passwords, domains, and other settings
   ```

3. **Start development environment**:
   ```bash
   docker-compose -f docker-compose.dev.yml up -d
   ```

4. **Access services**:
   - Manager API: http://localhost:8000
   - Headend Proxy: http://localhost:8080
   - Redis: localhost:6379

5. **Include development tools**:
   ```bash
   docker-compose -f docker-compose.dev.yml --profile tools up -d
   ```
   - Adminer: http://localhost:8081
   - Redis Commander: http://localhost:8082
   - Mailhog: http://localhost:8025

### Production Deployment

1. **Prepare environment**:
   ```bash
   cp .env.example .env
   nano .env  # Configure production settings
   ```

2. **Create configuration directories**:
   ```bash
   mkdir -p config/{nginx,prometheus,grafana}
   ```

3. **Generate SSL certificates**:
   ```bash
   # Using Let's Encrypt (recommended)
   certbot certonly --standalone -d manager.yourdomain.com
   certbot certonly --standalone -d headend.yourdomain.com
   
   # Or generate self-signed for testing
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout config/nginx/ssl/key.pem \
     -out config/nginx/ssl/cert.pem
   ```

4. **Start production services**:
   ```bash
   docker-compose up -d
   ```

5. **Start with monitoring**:
   ```bash
   docker-compose --profile monitoring up -d
   ```

6. **Start with nginx proxy**:
   ```bash
   docker-compose --profile proxy up -d
   ```

## Service Profiles

- **Default**: Core services (redis, manager, headend)
- **monitoring**: Adds Prometheus and Grafana
- **proxy**: Adds NGINX reverse proxy
- **tools**: Development tools (dev environment only)
- **testing**: Test client container (dev environment only)

## Configuration

### Environment Variables

Key environment variables to configure:

```bash
# Security (REQUIRED - change these!)
REDIS_PASSWORD=your-secure-redis-password
JWT_SECRET=your-super-secret-jwt-key
ADMIN_PASSWORD=your-secure-admin-password

# Domains
MANAGER_DOMAIN=manager.yourdomain.com
HEADEND_DOMAIN=headend.yourdomain.com

# Ports
MANAGER_PORT=8000
WIREGUARD_PORT=51820
HEADEND_PROXY_PORT=8080

# Cluster
CLUSTER_ID=production
LOG_LEVEL=info
```

### Configuration Files

Create configuration files in the `config/` directory:

#### NGINX Configuration (`config/nginx/nginx.conf`)
```nginx
events {
    worker_connections 1024;
}

http {
    upstream manager {
        server manager:8000;
    }
    
    upstream headend {
        server headend:8080;
    }
    
    server {
        listen 80;
        server_name manager.yourdomain.com;
        return 301 https://$server_name$request_uri;
    }
    
    server {
        listen 443 ssl;
        server_name manager.yourdomain.com;
        
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        
        location / {
            proxy_pass http://manager;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

#### Prometheus Configuration (`config/prometheus/prometheus.yml`)
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'sasewaddle-manager'
    static_configs:
      - targets: ['manager:8000']
    metrics_path: /metrics

  - job_name: 'sasewaddle-headend'
    static_configs:
      - targets: ['headend:8080']
    metrics_path: /metrics
```

## Management

### Starting Services
```bash
# All services
docker-compose up -d

# Specific service
docker-compose up -d manager

# With profiles
docker-compose --profile monitoring up -d
```

### Stopping Services
```bash
# All services
docker-compose down

# With data removal
docker-compose down -v
```

### Viewing Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f manager

# Last 100 lines
docker-compose logs --tail 100 headend
```

### Scaling Services
```bash
# Scale manager to 3 instances
docker-compose up -d --scale manager=3

# Note: headend cannot be scaled due to WireGuard constraints
```

### Health Checks
```bash
# Check service health
docker-compose ps

# Check specific service
docker inspect sasewaddle-manager --format='{{.State.Health.Status}}'
```

## Backup and Recovery

### Data Backup
```bash
# Create backup
docker run --rm -v sasewaddle_manager_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/manager-data-$(date +%Y%m%d).tar.gz -C /data .

docker run --rm -v sasewaddle_manager_certs:/data -v $(pwd):/backup alpine \
  tar czf /backup/manager-certs-$(date +%Y%m%d).tar.gz -C /data .
```

### Data Restore
```bash
# Restore backup
docker run --rm -v sasewaddle_manager_data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/manager-data-backup.tar.gz -C /data
```

## Troubleshooting

### Common Issues

1. **Permission denied for /dev/net/tun**:
   ```bash
   sudo modprobe tun
   sudo chmod 666 /dev/net/tun
   ```

2. **WireGuard interface creation failed**:
   - Ensure kernel modules are loaded: `modprobe wireguard`
   - Check container has CAP_NET_ADMIN: `cap_add: - NET_ADMIN`

3. **Cannot bind to port**:
   - Check if port is already in use: `netstat -tulpn | grep :51820`
   - Change port in `.env` file

4. **DNS resolution issues**:
   ```bash
   # Check container networking
   docker network ls
   docker network inspect sasewaddle_sasewaddle-internal
   ```

### Logs and Debugging
```bash
# Container logs
docker-compose logs -f manager
docker-compose logs -f headend

# Container shell access
docker-compose exec manager /bin/bash
docker-compose exec headend /bin/sh

# Service status
docker-compose ps
docker stats
```

## Security Notes

1. **Change default passwords** in `.env` file
2. **Use SSL/TLS** for production deployments
3. **Secure Redis** with authentication
4. **Network isolation** using Docker networks
5. **Regular updates** of container images
6. **Backup encryption** for sensitive data

## Production Recommendations

1. Use external databases for high availability
2. Implement log aggregation (ELK stack)
3. Set up monitoring and alerting
4. Configure automated backups
5. Use secrets management (Docker Secrets, HashiCorp Vault)
6. Implement health checks and auto-restart policies
7. Configure resource limits and monitoring