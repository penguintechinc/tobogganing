import express from 'express';

const app = express();
app.use(express.json());

// Helper to create a JWT-shaped token
function createToken(sub = 'u', tenant = 't', role = 'admin') {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({
    sub,
    tenant,
    role,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600 * 24 * 365,
  })).toString('base64url');
  const signature = 'mock_signature';
  return `${header}.${payload}.${signature}`;
}

// POST /api/v1/auth/login
app.post('/api/v1/auth/login', (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) {
    return res.status(400).json({ error: 'Missing email or password' });
  }

  if (email === 'test@example.com' && password === 'testpass') {
    return res.status(200).json({
      access_token: createToken('test-user', 'test-tenant', 'admin'),
      refresh_token: createToken('test-user', 'test-tenant', 'admin'),
      expires_in: 3600,
      token_type: 'Bearer',
    });
  }

  res.status(401).json({ error: 'Invalid credentials' });
});


// GET /api/v1/perftest_cluster/devices — two rows for smoke assertions
app.get('/api/v1/perftest_cluster/devices', (req, res) => {
  res.status(200).json({
    devices: [
      { id: 'd1', name: 'edge-nyc-1', org_unit_id: 'ou1', status: 'active', last_heartbeat: new Date().toISOString(), created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
      { id: 'd2', name: 'edge-lon-1', org_unit_id: 'ou1', status: 'inactive', last_heartbeat: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ],
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

// GET /api/v1/sdwan/clusters — empty list exercises the empty state
app.get('/api/v1/sdwan/clusters', (req, res) => {
  res.status(200).json({ clusters: [], meta: { version: 1, timestamp: new Date().toISOString() } });
});

// GET /api/v1/perftest_c2c/endpoints — one row
app.get('/api/v1/perftest_c2c/endpoints', (req, res) => {
  res.status(200).json({
    endpoints: [
      { id: 'e1', name: 'us-east-node', region: 'us-east', visibility: 'public', provider: 'aws', health_status: 'healthy', enabled: true, engine_url: 'https://e1.example.com', target: 't', created_at: new Date().toISOString() },
    ],
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

// GET /api/v1/portal/manifest
app.get('/api/v1/portal/manifest', (req, res) => {
  res.status(200).json({
    modules: [
      {
        name: 'sase',
        nav: [
          { label: 'Clusters', path: '/api/v1/sdwan/clusters', icon: 'server' },
          { label: 'Status', path: '/api/v1/sdwan/status', icon: 'activity' },
        ],
        flags: {},
      },
      {
        name: 'perftest_c2c',
        nav: [
          { label: 'C2C Nodes', path: '/api/v1/perftest_c2c/endpoints', icon: 'globe' },
        ],
        flags: {},
      },
      {
        name: 'perftest_cluster',
        nav: [
          { label: 'Devices', path: '/api/v1/perftest_cluster/devices', icon: 'laptop' },
          { label: 'Tests', path: '/api/v1/perftest_cluster/tests', icon: 'activity' },
          { label: 'Stats', path: '/api/v1/perftest_cluster/stats', icon: 'bar-chart-2' },
        ],
        flags: {
          'tobogganing.perftest_cluster.devices': true,
          'tobogganing.perftest_cluster.tests': true,
          'tobogganing.perftest_cluster.stats': true,
        },
      },
      {
        name: 'netsvcs',
        nav: [
          { label: 'Zones', path: '/api/v1/netsvcs/zones', icon: 'globe' },
          { label: 'DNS Servers', path: '/api/v1/netsvcs/dns-servers', icon: 'server' },
          { label: 'Analytics', path: '/api/v1/netsvcs/analytics', icon: 'bar-chart' },
        ],
        flags: {
          'tobogganing.netsvcs.zones': true,
          'tobogganing.netsvcs.dns-servers': true,
          'tobogganing.netsvcs.analytics': true,
        },
      },
      {
        name: 'threatintel',
        nav: [
          { label: 'IOC Check', path: '/api/v1/threatintel/blocklist/check', icon: 'search' },
          { label: 'Feeds', path: '/api/v1/threatintel/feeds', icon: 'refresh-cw' },
          { label: 'Blocklist', path: '/api/v1/threatintel/blocklist', icon: 'alert-circle' },
        ],
        flags: {
          'tobogganing.threatintel.ioc-check': true,
          'tobogganing.threatintel.feeds': true,
          'tobogganing.threatintel.blocklist': true,
        },
      },
    ],
    role: 'admin',
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

// ---------------------------------------------------------------------------
// netsvcs (DNS) — zones, records, servers, analytics
// ---------------------------------------------------------------------------

const mockZones = [
  { id: 'z1', name: 'example.com', visibility: 'public', description: 'Primary zone', created_at: new Date().toISOString() },
  { id: 'z2', name: 'internal.example.com', visibility: 'internal', description: null, created_at: new Date().toISOString() },
  { id: 'z3', name: 'staging.example.com', visibility: 'restricted', description: 'Staging zone', created_at: new Date().toISOString() },
];

const mockRecordsByZone = {
  z1: [
    { id: 'r1', name: 'www', type: 'A', value: '203.0.113.10', ttl: 300, created_at: new Date().toISOString(), priority: null, weight: null, port: null },
    { id: 'r2', name: 'mail', type: 'MX', value: 'mail.example.com', ttl: 3600, created_at: new Date().toISOString(), priority: 10, weight: null, port: null },
    { id: 'r3', name: 'api', type: 'A', value: '203.0.113.11', ttl: 300, created_at: new Date().toISOString(), priority: null, weight: null, port: null },
  ],
};

app.get('/api/v1/netsvcs/zones', (req, res) => {
  res.status(200).json({ zones: mockZones, meta: { version: 1, timestamp: new Date().toISOString() } });
});

app.post('/api/v1/netsvcs/zones', (req, res) => {
  const { name, visibility = 'public', description = null } = req.body || {};
  if (!name) return res.status(400).json({ error: 'Missing required field: name' });
  res.status(201).json({ id: 'z-new', name, visibility, description, created_at: new Date().toISOString() });
});

app.get('/api/v1/netsvcs/zones/:zoneId', (req, res) => {
  const zone = mockZones.find((z) => z.id === req.params.zoneId);
  if (!zone) return res.status(404).json({ error: 'Zone not found' });
  res.status(200).json(zone);
});

app.delete('/api/v1/netsvcs/zones/:zoneId', (req, res) => {
  res.status(200).json({ message: 'Zone deleted successfully', meta: { version: 1, timestamp: new Date().toISOString() } });
});

app.get('/api/v1/netsvcs/zones/:zoneId/records', (req, res) => {
  const records = mockRecordsByZone[req.params.zoneId] || [];
  res.status(200).json({ records, meta: { version: 1, timestamp: new Date().toISOString() } });
});

app.post('/api/v1/netsvcs/zones/:zoneId/records', (req, res) => {
  const { name, type, value, ttl = 300, priority = null, weight = null, port = null } = req.body || {};
  if (!name || !type || !value) return res.status(400).json({ error: 'Missing required record field' });
  res.status(201).json({ id: 'r-new', name, type, value, ttl, created_at: new Date().toISOString(), priority, weight, port });
});

app.delete('/api/v1/netsvcs/zones/:zoneId/records/:recordId', (req, res) => {
  res.status(200).json({ message: 'Record deleted successfully', meta: { version: 1, timestamp: new Date().toISOString() } });
});

const mockDnsServers = [
  { id: 's1', name: 'resolver-us-west-1', status: 'online', version: '1.2.0', region: 'us-west', hostname: 'resolver-us-west-1.internal', last_heartbeat: new Date().toISOString(), created_at: new Date().toISOString() },
  { id: 's2', name: 'resolver-eu-central-1', status: 'online', version: '1.2.0', region: 'eu-central', hostname: 'resolver-eu-central-1.internal', last_heartbeat: new Date().toISOString(), created_at: new Date().toISOString() },
  { id: 's3', name: 'resolver-ap-south-1', status: 'offline', version: '1.1.5', region: 'ap-south', hostname: 'resolver-ap-south-1.internal', last_heartbeat: null, created_at: new Date().toISOString() },
];

app.get('/api/v1/netsvcs/dns-servers', (req, res) => {
  res.status(200).json({ servers: mockDnsServers, meta: { version: 1, timestamp: new Date().toISOString() } });
});

app.get('/api/v1/netsvcs/dns-servers/:serverId', (req, res) => {
  const server = mockDnsServers.find((s) => s.id === req.params.serverId);
  if (!server) return res.status(404).json({ error: 'DNS server not found' });
  res.status(200).json(server);
});

app.delete('/api/v1/netsvcs/dns-servers/:serverId', (req, res) => {
  res.status(200).json({ message: 'DNS server deleted successfully', meta: { version: 1, timestamp: new Date().toISOString() } });
});

app.get('/api/v1/netsvcs/dns-servers/:serverId/metrics', (req, res) => {
  res.status(200).json({
    metrics: [
      { server_id: req.params.serverId, timestamp: new Date().toISOString(), queries_total: 12500, cache_hits: 10800, errors: 12, avg_response_ms: 4.2 },
      { server_id: req.params.serverId, timestamp: new Date(Date.now() - 3600000).toISOString(), queries_total: 11800, cache_hits: 10100, errors: 9, avg_response_ms: 4.6 },
    ],
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

app.get('/api/v1/netsvcs/analytics/summary', (req, res) => {
  res.status(200).json({
    metrics: [
      { key: 'zones', value: mockZones.length },
      { key: 'records', value: 6 },
      { key: 'servers', value: mockDnsServers.length },
      { key: 'queries_24h', value: 48200 },
    ],
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

app.get('/api/v1/netsvcs/analytics/queries', (req, res) => {
  res.status(200).json({
    total_queries: 48200,
    total_cache_hits: 41000,
    total_errors: 35,
    cache_hit_rate: 85.0,
    timeline: [
      { timestamp: new Date(Date.now() - 7200000).toISOString(), queries: 15800 },
      { timestamp: new Date(Date.now() - 3600000).toISOString(), queries: 16400 },
      { timestamp: new Date().toISOString(), queries: 16000 },
    ],
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

app.get('/api/v1/netsvcs/analytics/performance', (req, res) => {
  res.status(200).json({
    metrics: [
      { metric: 'avg_response_ms', value: 4.4 },
      { metric: 'p95_response_ms', value: 9.1 },
      { metric: 'p99_response_ms', value: 15.3 },
    ],
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

app.get('/api/v1/netsvcs/analytics/servers', (req, res) => {
  res.status(200).json({
    servers: mockDnsServers.map((s, i) => ({
      server_id: s.id,
      server_name: s.name,
      queries: 16000 - i * 500,
      cache_hits: 13600 - i * 400,
      errors: 5 + i,
      avg_response_ms: 4.0 + i * 0.5,
    })),
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

// ---------------------------------------------------------------------------
// threatintel — feeds, blocklist
// ---------------------------------------------------------------------------

const mockFeedSources = [
  { id: 'f1', name: 'spamhaus-drop', source_type: 'csv', url: 'https://feeds.example.com/spamhaus-drop.csv', enabled: true, last_refresh_at: new Date().toISOString(), last_refresh_status: 'success', last_refresh_error: null, created_at: new Date().toISOString() },
  { id: 'f2', name: 'misp-community', source_type: 'misp', url: 'https://misp.example.com/export.json', enabled: true, last_refresh_at: new Date(Date.now() - 3600000).toISOString(), last_refresh_status: 'success', last_refresh_error: null, created_at: new Date().toISOString() },
  { id: 'f3', name: 'taxii-collection-1', source_type: 'taxii', url: 'https://taxii.example.com/collections/1/objects', enabled: false, last_refresh_at: new Date(Date.now() - 86400000).toISOString(), last_refresh_status: 'failed', last_refresh_error: 'feed fetch failed', created_at: new Date().toISOString() },
];

app.get('/api/v1/threatintel/feeds', (req, res) => {
  res.status(200).json({ sources: mockFeedSources, meta: { version: 1, timestamp: new Date().toISOString() } });
});

app.post('/api/v1/threatintel/feeds', (req, res) => {
  const { name, source_type, url, enabled = true } = req.body || {};
  if (!name || !source_type || !url) return res.status(400).json({ error: 'Missing required feed source field' });
  res.status(201).json({
    id: 'f-new', name, source_type, url, enabled,
    last_refresh_at: null, last_refresh_status: null, last_refresh_error: null,
    created_at: new Date().toISOString(),
  });
});

app.delete('/api/v1/threatintel/feeds/:sourceId', (req, res) => {
  res.status(200).json({ message: 'Feed source deleted successfully', meta: { version: 1, timestamp: new Date().toISOString() } });
});

app.post('/api/v1/threatintel/feeds/:sourceId/refresh', (req, res) => {
  res.status(200).json({ id: req.params.sourceId, status: 'completed', added: 12, updated: 3, errors: 0, meta: { version: 1, timestamp: new Date().toISOString() } });
});

const mockBlocklistEntries = [
  { id: 'b1', indicator_type: 'domain', value: 'malicious-example.com', source: 'spamhaus-drop', confidence: 95, active: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
  { id: 'b2', indicator_type: 'ip', value: '198.51.100.23', source: 'misp-community', confidence: 80, active: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
  { id: 'b3', indicator_type: 'domain', value: 'phishing-example.net', source: 'manual', confidence: 100, active: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
];

app.get('/api/v1/threatintel/blocklist', (req, res) => {
  res.status(200).json({
    entries: mockBlocklistEntries,
    meta: { version: 1, timestamp: new Date().toISOString(), total: mockBlocklistEntries.length, limit: 50, offset: 0 },
  });
});

app.post('/api/v1/threatintel/blocklist', (req, res) => {
  const { indicator_type, value, source = 'manual', confidence = 100 } = req.body || {};
  if (!indicator_type || !value) return res.status(400).json({ error: 'Missing required blocklist field' });
  res.status(201).json({
    id: 'b-new', indicator_type, value, source, confidence, active: true,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  });
});

app.delete('/api/v1/threatintel/blocklist/:entryId', (req, res) => {
  res.status(200).json({ message: 'Blocklist entry removed successfully', meta: { version: 1, timestamp: new Date().toISOString() } });
});

// GET /api/v1/threatintel/blocklist/check — IOC lookup used by the IOC Check page
app.get('/api/v1/threatintel/blocklist/check', (req, res) => {
  const { type, value } = req.query;
  if (!type || !value) return res.status(400).json({ error: 'Missing required query parameters: type, value' });
  const match = mockBlocklistEntries.find((e) => e.indicator_type === type && e.value === value);
  if (!match) return res.status(404).json({ error: 'IOC not found in blocklist' });
  res.status(200).json({
    ioc_type: match.indicator_type,
    value: match.value,
    severity: 'high',
    source: match.source,
    stix_id: `indicator--${match.id}`,
    first_seen: Math.floor(Date.now() / 1000) - 86400,
    expiry: null,
  });
});

export default app;
