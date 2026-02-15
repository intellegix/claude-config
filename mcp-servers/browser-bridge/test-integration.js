/**
 * test-integration.js — WebSocket bridge integration tests
 *
 * Tests relay mode, request correlation, session cleanup, and timeout handling.
 * Requires the server running: node server.js --standalone
 * Run with: node test-integration.js
 */

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert';
import WebSocket from 'ws';
import { get as httpGet } from 'node:http';
import { randomUUID } from 'node:crypto';

const WS_URL = `ws://127.0.0.1:${process.env.MCP_WS_PORT || 8765}`;
const HEALTH_URL = `http://127.0.0.1:${process.env.MCP_HEALTH_PORT || 8766}/health`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Open a WebSocket and resolve once it receives connection_init. */
function connectAndInit(url = WS_URL) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url, { maxPayload: 50_000_000 });
    const timer = setTimeout(() => reject(new Error('Connection timed out')), 5000);
    ws.on('error', (err) => { clearTimeout(timer); reject(err); });
    ws.on('message', (raw) => {
      clearTimeout(timer);
      const msg = JSON.parse(raw.toString());
      if (msg.type === 'connection_init') {
        resolve({ ws, clientId: msg.clientId });
      }
    });
  });
}

/** Wait for the next JSON message matching an optional filter. */
function nextMessage(ws, filter, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      ws.removeListener('message', handler);
      reject(new Error('Timed out waiting for message'));
    }, timeoutMs);

    function handler(raw) {
      const msg = JSON.parse(raw.toString());
      if (!filter || filter(msg)) {
        clearTimeout(timer);
        ws.removeListener('message', handler);
        resolve(msg);
      }
    }
    ws.on('message', handler);
  });
}

/** HTTP GET returning parsed JSON body. */
function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    httpGet(url, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch {
          reject(new Error(`Invalid JSON: ${data}`));
        }
      });
    }).on('error', reject);
  });
}

/** Send relay_init to mark a WS client as a relay. */
function sendRelayInit(ws, sessionId) {
  ws.send(JSON.stringify({
    type: 'relay_init',
    payload: { pid: process.pid, role: 'stdio-relay', sessionId },
  }));
}

/** Small delay helper. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WebSocket Bridge Integration', () => {

  // 1. Relay init identification
  describe('relay_init', () => {
    it('marks client as relay and appears in health status', async () => {
      const { ws } = await connectAndInit();
      const sessionId = randomUUID();
      sendRelayInit(ws, sessionId);
      await sleep(300);

      // Health endpoint should show the relay client
      const { body } = await httpGetJson(HEALTH_URL);
      assert.ok(body.bridge.clientCount >= 1, 'At least 1 client connected');

      ws.close();
      await sleep(200);
    });
  });

  // 2. Relay forward → browser → relay response
  describe('relay_forward flow', () => {
    it('routes relay request to browser client and returns response', async () => {
      // Connect browser client (no relay_init)
      const browser = await connectAndInit();

      // Connect relay client
      const relay = await connectAndInit();
      const sessionId = randomUUID();
      sendRelayInit(relay.ws, sessionId);
      await sleep(300);

      // Relay sends a relay_forward request
      const relayRequestId = randomUUID();
      relay.ws.send(JSON.stringify({
        type: 'relay_forward',
        requestId: relayRequestId,
        payload: {
          type: 'get_tabs',
          payload: { sessionId },
        },
        timeout: 5000,
      }));

      // Browser should receive the forwarded message
      const forwarded = await nextMessage(browser.ws, (m) => m.type === 'get_tabs');
      assert.ok(forwarded.requestId, 'Forwarded message has a requestId');
      assert.ok(forwarded.payload?.sessionId === sessionId, 'SessionId preserved in forwarded payload');

      // Browser responds with matching requestId
      browser.ws.send(JSON.stringify({
        requestId: forwarded.requestId,
        result: { tabs: [{ id: 1, url: 'https://test.com', title: 'Test' }] },
      }));

      // Relay should receive the response with its original requestId
      const response = await nextMessage(relay.ws, (m) => m.requestId === relayRequestId);
      assert.ok(response.result, 'Relay received result');
      assert.strictEqual(response.result.tabs[0].url, 'https://test.com');

      relay.ws.close();
      browser.ws.close();
      await sleep(200);
    });
  });

  // 3. Relay forward completes round-trip for any message type
  describe('relay_forward round-trip', () => {
    it('completes round-trip even for non-standard message types', async () => {
      const relay = await connectAndInit();
      sendRelayInit(relay.ws, randomUUID());
      await sleep(300);

      // Send a relay_forward — any connected client (extension or test browser) may respond
      const relayRequestId = randomUUID();
      relay.ws.send(JSON.stringify({
        type: 'relay_forward',
        requestId: relayRequestId,
        payload: { type: 'get_tabs', payload: {} },
        timeout: 5000,
      }));

      // Relay should get SOME response (result or error) proving the round-trip works
      const response = await nextMessage(relay.ws, (m) => m.requestId === relayRequestId, 8000);
      assert.ok(
        response.result !== undefined || response.error !== undefined,
        'Relay should receive either result or error',
      );

      relay.ws.close();
      await sleep(200);
    });
  });

  // 4. Session cleanup on relay disconnect
  describe('session_cleanup on relay disconnect', () => {
    it('sends cleanup message to browser when relay disconnects', async () => {
      const sessionId = randomUUID();

      // Connect browser first
      const browser = await connectAndInit();

      // Connect relay with sessionId
      const relay = await connectAndInit();
      sendRelayInit(relay.ws, sessionId);
      await sleep(500);

      // Set up listener for session_cleanup BEFORE disconnecting
      const cleanupPromise = nextMessage(
        browser.ws,
        (m) => m.type === 'session_cleanup',
        5000,
      );

      // Disconnect the relay
      relay.ws.close(1000);

      // Browser should receive session_cleanup
      const cleanup = await cleanupPromise;
      assert.strictEqual(cleanup.type, 'session_cleanup');
      assert.strictEqual(cleanup.payload.sessionId, sessionId);

      browser.ws.close();
      await sleep(200);
    });
  });

  // 5. Page context update reflected in health
  describe('page_context_update', () => {
    it('caches page context and exposes via health endpoint', async () => {
      const { ws } = await connectAndInit();

      const testUrl = `https://integration-test-${Date.now()}.example.com`;
      ws.send(JSON.stringify({
        type: 'page_context_update',
        payload: { url: testUrl, title: 'Integration Test Page', content: 'test' },
      }));

      await sleep(500);

      const { body } = await httpGetJson(HEALTH_URL);
      assert.ok(body.bridge.cachedPageContext, 'Page context should be cached');
      assert.strictEqual(body.bridge.cachedPageContext.url, testUrl);
      assert.strictEqual(body.bridge.cachedPageContext.title, 'Integration Test Page');

      ws.close();
      await sleep(200);
    });
  });

  // 6. Multiple concurrent relay_forwards with correct routing
  describe('concurrent relay_forwards', () => {
    it('routes multiple in-flight requests to correct relays', async () => {
      // Connect browser
      const browser = await connectAndInit();

      // Connect two relays
      const relay1 = await connectAndInit();
      sendRelayInit(relay1.ws, randomUUID());
      const relay2 = await connectAndInit();
      sendRelayInit(relay2.ws, randomUUID());
      await sleep(300);

      // Both relays send relay_forward simultaneously
      const reqId1 = randomUUID();
      const reqId2 = randomUUID();

      relay1.ws.send(JSON.stringify({
        type: 'relay_forward',
        requestId: reqId1,
        payload: { type: 'get_context', payload: { marker: 'relay1' } },
        timeout: 5000,
      }));

      relay2.ws.send(JSON.stringify({
        type: 'relay_forward',
        requestId: reqId2,
        payload: { type: 'get_context', payload: { marker: 'relay2' } },
        timeout: 5000,
      }));

      // Browser receives both forwarded requests — collect them
      const msgs = [];
      const collectPromise = new Promise((resolve) => {
        function handler(raw) {
          const msg = JSON.parse(raw.toString());
          if (msg.type === 'get_context' && msg.requestId) {
            msgs.push(msg);
            if (msgs.length === 2) {
              browser.ws.removeListener('message', handler);
              resolve();
            }
          }
        }
        browser.ws.on('message', handler);
        setTimeout(() => {
          browser.ws.removeListener('message', handler);
          resolve();
        }, 3000);
      });

      await collectPromise;
      assert.strictEqual(msgs.length, 2, 'Browser should receive 2 forwarded requests');

      // Respond to each with different data
      for (const msg of msgs) {
        browser.ws.send(JSON.stringify({
          requestId: msg.requestId,
          result: { source: msg.payload?.marker || 'unknown' },
        }));
      }

      // Each relay should get its own response
      const resp1 = await nextMessage(relay1.ws, (m) => m.requestId === reqId1);
      const resp2 = await nextMessage(relay2.ws, (m) => m.requestId === reqId2);

      assert.ok(resp1.result, 'Relay 1 should get a result');
      assert.ok(resp2.result, 'Relay 2 should get a result');
      assert.strictEqual(resp1.result.source, 'relay1');
      assert.strictEqual(resp2.result.source, 'relay2');

      relay1.ws.close();
      relay2.ws.close();
      browser.ws.close();
      await sleep(200);
    });
  });

  // 7. Sequential relay requests — verify multiple round-trips work
  describe('sequential relay requests', () => {
    it('handles multiple sequential relay_forward round-trips correctly', async () => {
      const browser = await connectAndInit();
      const relay = await connectAndInit();
      sendRelayInit(relay.ws, randomUUID());
      await sleep(300);

      // Send 3 sequential requests
      for (let i = 0; i < 3; i++) {
        const reqId = randomUUID();
        relay.ws.send(JSON.stringify({
          type: 'relay_forward',
          requestId: reqId,
          payload: { type: 'get_context', payload: { iteration: i } },
          timeout: 5000,
        }));

        // Browser receives and responds
        const forwarded = await nextMessage(browser.ws, (m) => m.type === 'get_context', 3000);
        browser.ws.send(JSON.stringify({
          requestId: forwarded.requestId,
          result: { iteration: forwarded.payload?.iteration, url: `https://test-${i}.com` },
        }));

        // Relay gets correct response
        const resp = await nextMessage(relay.ws, (m) => m.requestId === reqId, 3000);
        assert.ok(resp.result, `Round-trip ${i + 1} should return result`);
        assert.strictEqual(resp.result.url, `https://test-${i}.com`);
      }

      relay.ws.close();
      browser.ws.close();
      await sleep(200);
    });
  });

  // 8. Health endpoint reports version and bridge status
  describe('health endpoint', () => {
    it('returns valid health status with bridge info', async () => {
      const { status, body } = await httpGetJson(HEALTH_URL);
      assert.strictEqual(status, 200);
      assert.strictEqual(body.status, 'ok');
      assert.strictEqual(body.server, 'claude-browser-bridge');
      assert.ok(typeof body.uptime === 'number');
      assert.ok(body.bridge, 'Health should include bridge status');
      assert.ok(typeof body.bridge.clientCount === 'number');
      // rateLimit only present in server v1.1.0+ (Phase 2.5 hardening)
      if (body.version === '1.1.0') {
        assert.ok(body.rateLimit, 'v1.1.0+ should include rateLimit');
        assert.strictEqual(body.rateLimit.maxPerMinute, 60);
      }
    });
  });

  // 9. Relay forward with no browser client returns error
  describe('no-browser-connected error', () => {
    it('returns error when relay_forward has no browser to route to', async () => {
      // Grab baseline browser count to check if any real browser is connected
      const baseline = await httpGetJson(HEALTH_URL);
      const hasBrowser = baseline.body.bridge.browserCount > 0;

      if (hasBrowser) {
        // If a real browser extension is connected, we can't test the "no browser"
        // path without disconnecting it. Skip gracefully.
        return;
      }

      // Connect relay only (no browser client)
      const relay = await connectAndInit();
      sendRelayInit(relay.ws, randomUUID());
      await sleep(300);

      const reqId = randomUUID();
      relay.ws.send(JSON.stringify({
        type: 'relay_forward',
        requestId: reqId,
        payload: { type: 'get_tabs', payload: {} },
        timeout: 3000,
      }));

      // Should get an error response (not hang forever)
      const resp = await nextMessage(relay.ws, (m) => m.requestId === reqId, 10000);
      assert.ok(resp.error, 'Should receive error when no browser client connected');

      relay.ws.close();
      await sleep(200);
    });
  });

  // 10. Broadcast isolation — relays never receive broadcast messages
  describe('broadcast isolation', () => {
    it('relay does not receive messages broadcast to browser clients', async () => {
      // Connect browser and relay
      const browser = await connectAndInit();
      const relay = await connectAndInit();
      sendRelayInit(relay.ws, randomUUID());
      await sleep(300);

      // Browser sends page_context_update (triggers server-side cache, not broadcast)
      // To test broadcast isolation we need a different approach:
      // Send a message FROM a second relay, which should route to browser only
      const relay2 = await connectAndInit();
      sendRelayInit(relay2.ws, randomUUID());
      await sleep(300);

      const reqId = randomUUID();
      relay2.ws.send(JSON.stringify({
        type: 'relay_forward',
        requestId: reqId,
        payload: { type: 'get_context', payload: { test: 'isolation' } },
        timeout: 5000,
      }));

      // Browser should receive the forwarded message
      const forwarded = await nextMessage(browser.ws, (m) => m.type === 'get_context', 3000);
      assert.ok(forwarded.requestId, 'Browser received forwarded message');

      // First relay should NOT receive the forwarded message
      // We verify by waiting briefly and checking no message arrived
      let relayGotMessage = false;
      const relayListener = (raw) => {
        const msg = JSON.parse(raw.toString());
        if (msg.type === 'get_context') relayGotMessage = true;
      };
      relay.ws.on('message', relayListener);
      await sleep(1000);
      relay.ws.removeListener('message', relayListener);

      assert.strictEqual(relayGotMessage, false, 'Relay should NOT receive broadcast intended for browsers');

      // Clean up: respond to browser so relay2 doesn't timeout
      browser.ws.send(JSON.stringify({
        requestId: forwarded.requestId,
        result: { url: 'https://test.com' },
      }));
      await sleep(200);

      relay.ws.close();
      relay2.ws.close();
      browser.ws.close();
      await sleep(200);
    });
  });

  // 11. Relay lastActivity tracking
  describe('relay lastActivity tracking', () => {
    it('relay_forward updates lastActivity and is reflected in health', async () => {
      const browser = await connectAndInit();
      const relay = await connectAndInit();
      const sessionId = 'actTrack-' + Date.now();
      sendRelayInit(relay.ws, sessionId);
      await sleep(500);

      // Check initial idle time (health truncates sessionId to 8 chars)
      const h1 = await httpGetJson(HEALTH_URL);
      const r1 = h1.body.bridge.relays?.find(r => r.sessionId === 'actTrack');
      assert.ok(r1, 'Relay should appear in health relays list');
      const idle1 = r1.idleSeconds;

      // Wait a bit, then send a relay_forward to update activity
      await sleep(2000);
      const reqId = randomUUID();
      relay.ws.send(JSON.stringify({
        type: 'relay_forward',
        requestId: reqId,
        payload: { type: 'get_context', payload: {} },
        timeout: 5000,
      }));

      // Browser responds
      const forwarded = await nextMessage(browser.ws, (m) => m.type === 'get_context', 3000);
      browser.ws.send(JSON.stringify({
        requestId: forwarded.requestId,
        result: { url: 'https://activity-test.com' },
      }));
      await sleep(500);

      // Check idle time again — should be reset (lower than before)
      const h2 = await httpGetJson(HEALTH_URL);
      const r2 = h2.body.bridge.relays?.find(r => r.sessionId === 'actTrack');
      assert.ok(r2, 'Relay should still be in health after activity');
      assert.ok(r2.idleSeconds <= 2, `Idle should be reset after activity, got ${r2.idleSeconds}s`);

      relay.ws.close();
      browser.ws.close();
      await sleep(200);
    });
  });

  // 12. Typed client counts — browser vs relay separation
  describe('typed client counts', () => {
    it('health correctly counts browser and relay clients separately', async () => {
      // Record baseline
      const baseline = await httpGetJson(HEALTH_URL);
      const baseBrowser = baseline.body.bridge.browserCount;
      const baseRelay = baseline.body.bridge.relayCount;

      // Add 2 browser clients and 1 relay
      const b1 = await connectAndInit();
      const b2 = await connectAndInit();
      const r1 = await connectAndInit();
      sendRelayInit(r1.ws, randomUUID());
      await sleep(500);

      const after = await httpGetJson(HEALTH_URL);
      assert.strictEqual(after.body.bridge.browserCount, baseBrowser + 2, 'Should add 2 browser clients');
      assert.strictEqual(after.body.bridge.relayCount, baseRelay + 1, 'Should add 1 relay client');
      assert.strictEqual(
        after.body.bridge.clientCount,
        after.body.bridge.browserCount + after.body.bridge.relayCount,
        'clientCount = browserCount + relayCount',
      );

      b1.ws.close();
      b2.ws.close();
      r1.ws.close();
      await sleep(200);
    });
  });
});
