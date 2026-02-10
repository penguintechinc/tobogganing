# SASEWaddle Analytics System

The SASEWaddle Analytics system provides comprehensive monitoring and reporting capabilities for the SASE infrastructure, including client operating system analytics, traffic monitoring, and advanced search functionality.

## Features

### 📊 Dashboard Analytics
- **OS Distribution**: Track client operating systems, versions, and architectures
- **Traffic Monitoring**: Monitor data flow across headends and regions  
- **System Health**: Real-time headend performance and connection metrics
- **Interactive Charts**: Visual representations using Chart.js

### 🔍 Advanced Search
- **Agent Search**: Find clients by hostname, OS, IP address, or client ID
- **Headend Search**: Locate headends by ID, hostname, region, or cluster
- **Flexible Filtering**: Filter by type (agents/headends), sort by various fields
- **Real-time Status**: Live status indicators (online, offline, healthy, critical)

### 📈 Data Collection
- **Client Metrics**: OS info, connection stats, traffic data, last seen timestamps
- **Headend Metrics**: System resources, connection counts, authentication stats
- **Historical Data**: Automated hourly and daily aggregation
- **Data Retention**: Configurable cleanup of old analytics data

## Database Schema

### Client Analytics Table
```sql
client_analytics:
- client_id (string): Unique client identifier
- hostname (string): Client hostname
- os_name (string): Operating system name (Windows, macOS, Linux, etc.)
- os_version (string): OS version (10.0.19041, 12.6.1, 5.15.0-56, etc.)
- architecture (string): CPU architecture (x64, arm64, x86)
- client_version (string): SASEWaddle client version
- ip_address (string): Client IP address
- connected_headend (string): Currently connected headend
- connection_duration (integer): Connection time in seconds
- bytes_sent/received (bigint): Traffic statistics
- packets_sent/received (bigint): Packet counts
- last_seen (datetime): Last activity timestamp
```

### Headend Analytics Table
```sql
headend_analytics:
- headend_id (string): Unique headend identifier
- hostname (string): Headend hostname
- region (string): Geographic region
- cluster_id (string): Cluster identifier
- version (string): Headend software version
- active_connections (integer): Current active connections
- total_connections (bigint): Cumulative connection count
- bytes_proxied (bigint): Total bytes proxied
- packets_proxied (bigint): Total packets proxied
- cpu_usage_percent (double): CPU utilization (0-100)
- memory_usage_mb (integer): Memory usage in MB
- disk_usage_percent (double): Disk utilization (0-100)
- network_errors (integer): Network error count
- auth_successes/failures (integer): Authentication statistics
- last_heartbeat (datetime): Last heartbeat timestamp
```

### Traffic Statistics Table
```sql
traffic_stats:
- stat_type (string): 'hourly', 'daily', 'monthly'
- timestamp (datetime): Time period start
- headend_id (string): Associated headend
- client_count (integer): Number of clients
- total_bytes (bigint): Aggregated traffic
- total_packets (bigint): Aggregated packets
- unique_users (integer): Distinct users
- avg_connection_duration (integer): Average connection time
- peak_concurrent_connections (integer): Peak connections
```

## API Endpoints

### Analytics APIs
- `GET /api/analytics/os-stats?days=7`: Get OS distribution statistics
- `GET /api/analytics/traffic-stats?days=7`: Get traffic statistics by headend
- `GET /api/analytics/search?q=term&type=all&sort=last_seen`: Search agents/headends
- `GET /api/analytics/dashboard/overview?days=7`: Get complete dashboard data

### Detail APIs
- `GET /api/analytics/client/{client_id}/details`: Detailed client information
- `GET /api/analytics/headend/{headend_id}/details`: Detailed headend information

### Data Recording APIs
- `POST /api/analytics/record/client`: Record client activity data
- `POST /api/analytics/record/headend`: Record headend statistics

## Web Interface

### Main Analytics Dashboard (`/analytics`)
- Summary cards showing key metrics
- OS distribution pie chart
- Traffic by region bar chart
- Search interface with real-time filtering
- Top performing headends table

### Client Detail Page (`/analytics/client/{client_id}`)
- System information (OS, version, architecture)
- Connection statistics (duration, traffic, packets)
- Network information (IP, connected headend)
- Activity timeline
- Real-time status indicator

### Headend Detail Page (`/analytics/headend/{headend_id}`)
- System metrics with progress bars (CPU, memory, disk)
- Connection and traffic statistics
- Authentication success/failure rates
- List of connected clients with quick access links
- Health status indicators

## Data Collection

### Client Data Collection
Clients and headends can submit analytics data via API:

```bash
curl -X POST http://manager:8000/api/analytics/record/client \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "client_id": "client-12345",
    "hostname": "user-laptop",
    "os_name": "Windows",
    "os_version": "10.0.19041",
    "architecture": "x64",
    "client_version": "1.2.3",
    "ip_address": "10.0.1.50",
    "connected_headend": "headend-us-east-1",
    "connection_duration": 3600,
    "bytes_sent": 1048576,
    "bytes_received": 2097152
  }'
```

### Headend Data Collection
```bash
curl -X POST http://manager:8000/api/analytics/record/headend \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HEADEND_API_KEY" \
  -d '{
    "headend_id": "headend-us-east-1",
    "hostname": "headend01.us-east.example.com",
    "region": "us-east-1",
    "cluster_id": "prod-cluster",
    "version": "1.2.3",
    "active_connections": 150,
    "total_connections": 5000,
    "bytes_proxied": 1073741824,
    "packets_proxied": 1000000,
    "cpu_usage_percent": 45.2,
    "memory_usage_mb": 2048,
    "disk_usage_percent": 78.5,
    "network_errors": 3,
    "auth_successes": 4950,
    "auth_failures": 50
  }'
```

## Data Aggregation

### Automated Aggregation
The analytics system includes automated data aggregation via cron job:

```bash
# Run every hour at minute 5
5 * * * * cd /app/manager && python3 scripts/analytics_aggregator.py
```

### Manual Aggregation
```bash
# Run aggregation script manually
python3 scripts/analytics_aggregator.py

# Aggregate specific time periods
python3 -c "
from scripts.analytics_aggregator import AnalyticsAggregator
from datetime import datetime, timedelta
agg = AnalyticsAggregator()
agg.aggregate_hourly_stats(datetime.utcnow() - timedelta(hours=2))
"
```

## Configuration

### Environment Variables
```bash
# Analytics Configuration
HEADEND_API_KEY=change_this_headend_api_key
ANALYTICS_RETENTION_DAYS=90
ANALYTICS_AGGREGATION_ENABLED=true
```

### Database Configuration
The analytics system uses the same PyDAL database configuration as the main Manager service. Tables are created automatically on first startup.

## Security

### Authentication
- Web interface requires user authentication with Reporter role or higher
- API endpoints require valid session tokens or API keys
- Headend data recording accepts API key authentication

### Data Privacy
- Client data is aggregated and anonymized where possible
- Personal information is limited to system identifiers
- Old data is automatically purged based on retention settings

### Access Control
- Role-based access control (Admin/Reporter permissions)
- API key rotation support for headend authentication
- Audit logging for sensitive operations

## Performance

### Database Optimization
- Indexes on frequently queried fields (client_id, headend_id, timestamps)
- Automated data cleanup to maintain performance
- Separate read replicas supported for high-load environments

### Caching
- Dashboard data cached for 5 minutes to reduce database load
- Search results cached based on query parameters
- Static assets served with appropriate cache headers

### Scalability
- Horizontal scaling supported via multiple Manager instances
- Database read replicas for analytics queries
- Optional Redis caching for frequently accessed data

## Monitoring

### Health Checks
- Analytics system health included in main Manager health endpoint
- Database connection monitoring
- Data freshness checks (alerts if data stops flowing)

### Metrics
- Prometheus metrics for analytics system performance
- Grafana dashboards for operational monitoring
- Alert rules for data pipeline failures

## Troubleshooting

### Common Issues

**No data showing in dashboard:**
- Check that clients/headends are sending analytics data
- Verify database connectivity and table creation
- Check aggregation script execution logs

**Search not returning results:**
- Verify search permissions (Reporter role required)
- Check database indexes are created
- Confirm data is being recorded with correct fields

**Performance issues:**
- Review database query performance
- Check if data cleanup is running regularly
- Consider adding read replicas for heavy analytics workloads

### Debug Commands
```bash
# Check database tables
python3 -c "from analytics import analytics_manager; print(analytics_manager.db.tables)"

# Verify data collection
python3 -c "
from analytics import analytics_manager
stats = analytics_manager.get_os_statistics(days_back=1)
print(f'Found {stats.get(\"total_clients\", 0)} clients')
"

# Test search functionality
python3 -c "
from analytics import analytics_manager
results = analytics_manager.search_agents_and_headends('test')
print(f'Found {len(results[\"agents\"])} agents, {len(results[\"headends\"])} headends')
"
```

## Development

### Adding New Metrics
1. Update database schema in `analytics/__init__.py`
2. Modify data collection APIs in `api/analytics_routes.py`
3. Update dashboard displays in `web/templates/analytics.html`
4. Add aggregation logic to `scripts/analytics_aggregator.py`

### Testing
```bash
# Run analytics tests
cd manager
python3 -m pytest tests/test_analytics.py -v

# Test API endpoints
curl -X GET http://localhost:8000/api/analytics/os-stats?days=1
```

## Future Enhancements

- Real-time alerting based on analytics thresholds
- Advanced ML-based anomaly detection
- Enhanced geolocation and mapping features
- Custom dashboard creation and sharing
- Export functionality for compliance reporting
- Advanced traffic flow analysis and visualization