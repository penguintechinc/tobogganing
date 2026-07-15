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

// GET /api/v1/portal/manifest
app.get('/api/v1/portal/manifest', (req, res) => {
  res.status(200).json({
    modules: [
      {
        name: 'waddleperf_cluster',
        nav: [
          { label: 'Devices', path: '/api/v1/waddleperf_cluster/devices', icon: 'laptop' },
          { label: 'Tests', path: '/api/v1/waddleperf_cluster/tests', icon: 'activity' },
          { label: 'Stats', path: '/api/v1/waddleperf_cluster/stats', icon: 'bar-chart-2' },
        ],
        flags: {
          'tobogganing.waddleperf_cluster.devices': true,
          'tobogganing.waddleperf_cluster.tests': true,
          'tobogganing.waddleperf_cluster.stats': true,
        },
      },
    ],
    role: 'admin',
    meta: { version: 1, timestamp: new Date().toISOString() },
  });
});

export default app;
