/**
 * Health check HTTP server for Claude Browser Bridge.
 */

import { createServer as createHttpServer } from 'node:http';
import { CONFIG } from './config.js';

/**
 * Create and start the health check HTTP server.
 * @param {import('./websocket-bridge.js').WebSocketBridge} bridge
 * @param {import('./rate-limiter.js').RateLimiter} rateLimiter
 * @returns {Promise<import('node:http').Server>}
 */
export function startHealthServer(bridge, rateLimiter) {
  return new Promise((resolve, reject) => {
    const server = createHttpServer((req, res) => {
      if (req.url === '/' || req.url === '/health') {
        const status = bridge.getStatus();
        const body = JSON.stringify({
          status: 'ok',
          server: 'claude-browser-bridge',
          version: '1.1.0',
          uptime: process.uptime(),
          bridge: status,
          rateLimit: { maxPerMinute: rateLimiter.maxTokens, activeSessions: rateLimiter.buckets.size },
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(body);
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    });

    server.once('error', (err) => {
      console.error('[HealthCheck] Server error:', err.message);
      reject(err);
    });

    server.listen(CONFIG.healthPort, CONFIG.wsHost, () => {
      console.error(`[HealthCheck] Listening on http://${CONFIG.wsHost}:${CONFIG.healthPort}/health`);
      // Re-attach persistent error handler after successful bind
      server.on('error', (err) => {
        console.error('[HealthCheck] Server error:', err.message);
      });
      resolve(server);
    });
  });
}
