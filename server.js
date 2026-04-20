/**
 * Neumáticos Martinez – Servidor frontend Node.js + Express
 * Sirve los archivos estáticos y hace proxy de /api/* hacia Flask (puerto 5000).
 */

const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app  = express();
const PORT = process.env.PORT      || 8080;
const API  = process.env.FLASK_URL || 'http://127.0.0.1:5000';

// ── Proxy /api/* y /webhook/* y /setup/* → Flask ────────────
app.use(
  createProxyMiddleware({
    target: API,
    changeOrigin: true,
    pathFilter: ['/api', '/webhook', '/setup'],
    on: {
      proxyRes(proxyRes) {
        proxyRes.headers['x-accel-buffering'] = 'no';
      },
    },
  })
);

// ── Archivos estáticos (public/) ─────────────────────────────
app.use(express.static(path.join(__dirname, 'public'), {
  etag:         true,
  lastModified: true,
  maxAge:       '1h',
  setHeaders(res, filePath) {
    // Sin caché para el HTML principal
    if (filePath.endsWith('index.html')) {
      res.setHeader('Cache-Control', 'no-cache');
    }
  },
}));

// ── Fallback → index.html ────────────────────────────────────
app.get('*', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ── Arrancar ─────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log('='.repeat(60));
  console.log('  Neumáticos Martinez - Frontend Node.js');
  console.log('='.repeat(60));
  console.log(`  Interfaz web:  http://localhost:${PORT}`);
  console.log(`  API backend:   ${API}`);
  console.log('='.repeat(60));
});
