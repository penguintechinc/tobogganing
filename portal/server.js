import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';
import http from 'http';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const server = http.createServer(app);

const PORT = process.env.PORT || 3000;
const CORE_API_URL = process.env.CORE_API_URL || 'http://localhost:8080';

// Serve static files from dist/
app.use(express.static(join(__dirname, 'dist'), {
  maxAge: '1h',
  etag: false,
  lastModified: false,
}));

// Health check endpoint
app.get('/healthz', (_req, res) => {
  res.status(200).json({ status: 'ok' });
});

// Proxy /api/* requests to core API
app.use('/api', createProxyMiddleware({
  target: CORE_API_URL,
  changeOrigin: true,
  ws: true,
}));

// SPA fallback: for non-/api GETs, serve index.html
app.get('*', (_req, res) => {
  res.sendFile(join(__dirname, 'dist', 'index.html'));
});

server.listen(PORT, () => {
  console.log(`[Portal] listening on port ${PORT}`);
  console.log(`[Portal] proxying /api to ${CORE_API_URL}`);
});
