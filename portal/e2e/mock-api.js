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

// GET /api/v1/sase/clusters — empty list exercises the empty state
app.get('/api/v1/sase/clusters', (req, res) => {
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
          { label: 'Clusters', path: '/api/v1/sase/clusters', icon: 'server' },
          { label: 'Status', path: '/api/v1/sase/status', icon: 'activity' },
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
    ],
    role: 'admin',
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

export default app;
