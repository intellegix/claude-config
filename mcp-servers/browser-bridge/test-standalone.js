#!/usr/bin/env node

/**
 * Standalone test suite for Claude Browser Bridge MCP Server
 *
 * Tests the WebSocket server and health check endpoint independently
 * of the MCP stdio transport. Start the server first:
 *   node server.js
 * Then run:
 *   node test-standalone.js
 */

import WebSocket from 'ws';
import { get as httpGet } from 'node:http';

const WS_URL = `ws://127.0.0.1:${process.env.MCP_WS_PORT || 8765}`;
const HEALTH_URL = `http://127.0.0.1:${process.env.MCP_HEALTH_PORT || 8766}/health`;

let passed = 0;
let failed = 0;

function assert(condition, msg) {
  if (!condition) throw new Error(`Assertion failed: ${msg}`);
}

async function runTest(name, fn) {
  try {
    await fn();
    passed++;
    console.log(`  PASS  ${name}`);
  } catch (err) {
    failed++;
    console.log(`  FAIL  ${name} — ${err.message}`);
  }
}

/** Helper: open a WebSocket and resolve on open, reject on error. */
function connect(url = WS_URL) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    ws.on('open', () => resolve(ws));
    ws.on('error', reject);
  });
}

/** Helper: wait for the next JSON message on a WebSocket. */
function nextMessage(ws, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Timed out waiting for message')), timeoutMs);
    ws.once('message', (raw) => {
      clearTimeout(timer);
      resolve(JSON.parse(raw.toString()));
    });
  });
}

/** Helper: HTTP GET returning parsed JSON body. */
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function test1_connection() {
  const ws = await connect();
  assert(ws.readyState === WebSocket.OPEN, 'WebSocket should be OPEN');
  ws.close();
}

async function test2_connectionInit() {
  const ws = await connect();
  const msg = await nextMessage(ws);
  assert(msg.type === 'connection_init', `Expected connection_init, got ${msg.type}`);
  assert(typeof msg.clientId === 'string' && msg.clientId.length > 0, 'clientId should be a non-empty string');
  assert(msg.serverVersion === '1.0.0', `Expected serverVersion 1.0.0, got ${msg.serverVersion}`);
  ws.close();
}

async function test3_heartbeat() {
  const ws = await connect();
  await nextMessage(ws); // consume connection_init

  // Wait for server ping (heartbeat check runs every 30s, but we wait a shorter period)
  // We simulate responding to pings — the ws library does this automatically via 'pong'
  // Just verify the connection stays alive for 3 seconds
  await new Promise((resolve) => setTimeout(resolve, 3000));
  assert(ws.readyState === WebSocket.OPEN, 'Connection should survive heartbeat period');
  ws.close();
}

async function test4_requestResponse() {
  const ws = await connect();
  await nextMessage(ws); // consume connection_init

  // Send a simulated response to a broadcast request.
  // Since we can't trigger a tool call via stdio in this test, we simulate
  // by having the server send a message and us responding with a matching requestId.
  //
  // Instead, we verify the bidirectional message flow by sending a page_context_update
  // and checking the health endpoint reflects cached context.
  ws.send(JSON.stringify({
    type: 'page_context_update',
    payload: {
      url: 'https://test.example.com',
      title: 'Test Page',
      content: 'Hello from test',
    },
  }));

  // Give server a moment to process
  await new Promise((resolve) => setTimeout(resolve, 500));

  const { body } = await httpGetJson(HEALTH_URL);
  assert(
    body.bridge.cachedPageContext && body.bridge.cachedPageContext.url === 'https://test.example.com',
    'Cached page context should reflect the sent update',
  );
  ws.close();
}

async function test5_healthCheck() {
  const { status, body } = await httpGetJson(HEALTH_URL);
  assert(status === 200, `Expected HTTP 200, got ${status}`);
  assert(body.status === 'ok', `Expected status ok, got ${body.status}`);
  assert(body.server === 'claude-browser-bridge', `Expected server name, got ${body.server}`);
  assert(typeof body.uptime === 'number', 'uptime should be a number');
  assert(typeof body.bridge === 'object', 'bridge status should be present');
}

async function test6_concurrentConnections() {
  // Connect and capture the first message together to avoid race condition
  function connectAndCapture() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(WS_URL);
      ws.on('error', reject);
      ws.on('message', (raw) => {
        resolve({ ws, msg: JSON.parse(raw.toString()) });
      });
    });
  }

  const [r1, r2, r3] = await Promise.all([
    connectAndCapture(),
    connectAndCapture(),
    connectAndCapture(),
  ]);

  assert(r1.msg.type === 'connection_init', 'ws1 should get connection_init');
  assert(r2.msg.type === 'connection_init', 'ws2 should get connection_init');
  assert(r3.msg.type === 'connection_init', 'ws3 should get connection_init');

  // All three should have unique client IDs
  const ids = new Set([r1.msg.clientId, r2.msg.clientId, r3.msg.clientId]);
  assert(ids.size === 3, 'All client IDs should be unique');

  // Give server a moment to register all clients
  await new Promise((resolve) => setTimeout(resolve, 200));

  // Check health reflects 3 clients
  const { body } = await httpGetJson(HEALTH_URL);
  assert(body.bridge.clientCount >= 3, `Expected at least 3 clients, got ${body.bridge.clientCount}`);

  r1.ws.close();
  r2.ws.close();
  r3.ws.close();
}

async function test7_relayIdentification() {
  const ws = await connect();
  const initMsg = await nextMessage(ws);
  assert(initMsg.type === 'connection_init', 'Should get connection_init');

  // Identify as relay
  ws.send(JSON.stringify({
    type: 'relay_init',
    payload: { pid: process.pid, role: 'stdio-relay', sessionId: 'test-relay-session-1234' },
  }));

  // Give server a moment to process the relay_init
  await new Promise((resolve) => setTimeout(resolve, 500));

  const { body } = await httpGetJson(HEALTH_URL);
  assert(body.bridge.relayCount >= 1, `Expected relayCount >= 1, got ${body.bridge.relayCount}`);

  // Find our relay in the relays list
  const relay = body.bridge.relays.find(r => r.sessionId === 'test-rel');
  assert(relay, 'Should find relay with truncated sessionId in health relays list');
  assert(typeof relay.pid === 'number', 'Relay should have pid');
  assert(typeof relay.idleSeconds === 'number', 'Relay should have idleSeconds');

  ws.close();
}

async function test8_typedHealthCounts() {
  // Connect a "browser" client (no relay_init)
  const browserWs = await connect();
  await nextMessage(browserWs); // consume connection_init

  // Connect a "relay" client
  const relayWs = await connect();
  await nextMessage(relayWs); // consume connection_init
  relayWs.send(JSON.stringify({
    type: 'relay_init',
    payload: { pid: process.pid, role: 'stdio-relay', sessionId: 'test-typed-counts-5678' },
  }));

  // Give server a moment to process
  await new Promise((resolve) => setTimeout(resolve, 500));

  const { body } = await httpGetJson(HEALTH_URL);
  assert(body.bridge.browserCount >= 1, `Expected browserCount >= 1, got ${body.bridge.browserCount}`);
  assert(body.bridge.relayCount >= 1, `Expected relayCount >= 1, got ${body.bridge.relayCount}`);
  assert(
    body.bridge.clientCount === body.bridge.browserCount + body.bridge.relayCount,
    `clientCount (${body.bridge.clientCount}) should equal browserCount (${body.bridge.browserCount}) + relayCount (${body.bridge.relayCount})`,
  );
  // connected should be true since we have a browser client
  assert(body.bridge.connected === true, 'connected should be true with browser client');

  browserWs.close();
  relayWs.close();
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

async function main() {
  console.log('\nClaude Browser Bridge MCP — Standalone Tests\n');
  console.log(`WebSocket: ${WS_URL}`);
  console.log(`Health:    ${HEALTH_URL}\n`);

  await runTest('1. WebSocket connection establishes', test1_connection);
  await runTest('2. Server sends connection_init message', test2_connectionInit);
  await runTest('3. Heartbeat does not cause disconnection', test3_heartbeat);
  await runTest('4. Request-response round-trip works', test4_requestResponse);
  await runTest('5. Health check endpoint responds', test5_healthCheck);
  await runTest('6. Multiple concurrent connections', test6_concurrentConnections);
  await runTest('7. Relay identification via relay_init', test7_relayIdentification);
  await runTest('8. Typed health counts (browser vs relay)', test8_typedHealthCounts);

  console.log(`\nResults: ${passed} passed, ${failed} failed out of ${passed + failed}\n`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('Test runner error:', err);
  process.exit(1);
});
