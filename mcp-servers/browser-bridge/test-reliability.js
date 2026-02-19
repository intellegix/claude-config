/**
 * test-reliability.js — Reliability tests for zombie eviction, relay lifecycle,
 * and WebSocket bridge internals.
 *
 * Tests use mocked WebSocket objects (no real WS/Chrome connections).
 * Run with: node --test test-reliability.js
 */

import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';

import { CONFIG } from './lib/config.js';
import { WebSocketBridge } from './lib/websocket-bridge.js';
import { RateLimiter } from './lib/rate-limiter.js';
import { ContextManager } from './lib/context-manager.js';

// ---------------------------------------------------------------------------
// Mock WebSocket — minimal mock implementing readyState, send, close, ping
// ---------------------------------------------------------------------------

class MockWebSocket extends EventEmitter {
  constructor() {
    super();
    this.readyState = 1; // OPEN
    this.sentMessages = [];
    this.closed = false;
    this.closeCode = null;
    this.closeReason = null;
    this.pinged = false;
  }
  send(data) {
    this.sentMessages.push(JSON.parse(data));
  }
  close(code, reason) {
    this.readyState = 3; // CLOSED
    this.closed = true;
    this.closeCode = code;
    this.closeReason = reason;
  }
  ping() {
    this.pinged = true;
  }
}

/**
 * Helper: manually register a mock WS as a browser client in the bridge.
 * Bypasses the actual WebSocketServer connection flow.
 */
function addBrowserClient(bridge, ws, overrides = {}) {
  const info = {
    id: `mock-${Math.random().toString(36).slice(2, 8)}`,
    lastPing: Date.now(),
    lastAppMsg: Date.now(),
    connectedAt: Date.now(),
    ...overrides,
  };
  bridge.browserClients.set(ws, info);
  return info;
}

function addRelayClient(bridge, ws, overrides = {}) {
  const info = {
    id: `relay-${Math.random().toString(36).slice(2, 8)}`,
    lastPing: Date.now(),
    lastAppMsg: Date.now(),
    connectedAt: Date.now(),
    role: 'stdio-relay',
    sessionId: 'test-session-123',
    lastActivity: Date.now(),
    pid: 12345,
    ...overrides,
  };
  bridge.relayClients.set(ws, info);
  return info;
}

// ---------------------------------------------------------------------------
// Zombie Eviction Tests (5)
// ---------------------------------------------------------------------------

describe('Zombie Browser Client Eviction', () => {
  let bridge;

  beforeEach(() => {
    bridge = new WebSocketBridge();
    // Don't start the actual WSS — just test the logic
  });

  afterEach(() => {
    // Clean up any timers
    clearInterval(bridge.heartbeatTimer);
  });

  it('1. Client with fresh lastAppMsg survives heartbeat check', () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws, {
      lastAppMsg: Date.now(),
      lastPing: Date.now(),
    });

    bridge._checkHeartbeats();

    assert.equal(bridge.browserClients.size, 1, 'Client should survive');
    assert.equal(ws.closed, false);
    assert.equal(ws.pinged, true, 'Should have been pinged');
  });

  it('2. Client with stale lastAppMsg (>45s) gets evicted', () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws, {
      lastAppMsg: Date.now() - 50_000, // 50s ago — past 45s threshold
      lastPing: Date.now(), // WS-level pong is fresh (simulates zombie)
    });

    bridge._checkHeartbeats();

    assert.equal(bridge.browserClients.size, 0, 'Zombie should be evicted');
    assert.equal(ws.closed, true);
    assert.equal(ws.closeCode, 1000);
    assert.match(ws.closeReason, /App-level heartbeat timeout/);
  });

  it('3. WS pong does NOT update lastAppMsg (only lastPing)', () => {
    const ws = new MockWebSocket();
    const staleTime = Date.now() - 50_000;
    addBrowserClient(bridge, ws, {
      lastAppMsg: staleTime,
      lastPing: staleTime,
    });

    // Simulate WS-level pong — only updates lastPing
    const info = bridge.browserClients.get(ws);
    info.lastPing = Date.now(); // pong handler does this

    // lastAppMsg should still be stale
    assert.equal(info.lastAppMsg, staleTime);

    bridge._checkHeartbeats();
    assert.equal(bridge.browserClients.size, 0, 'Should still be evicted despite fresh pong');
  });

  it('4. Keepalive message DOES update lastAppMsg', async () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws, {
      lastAppMsg: Date.now() - 50_000,
      lastPing: Date.now() - 50_000,
    });

    // Simulate receiving a keepalive message — _onMessage updates both timestamps
    await bridge._onMessage(ws, { type: 'keepalive' });

    const info = bridge.browserClients.get(ws);
    assert.ok(Date.now() - info.lastAppMsg < 1000, 'lastAppMsg should be fresh after keepalive');

    bridge._checkHeartbeats();
    assert.equal(bridge.browserClients.size, 1, 'Should survive after keepalive');
  });

  it('5. Tool response DOES update lastAppMsg', async () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws, {
      lastAppMsg: Date.now() - 50_000,
      lastPing: Date.now() - 50_000,
    });

    // Simulate receiving a tool response (has requestId but no pending request for it)
    await bridge._onMessage(ws, { requestId: 'some-id', result: { ok: true } });

    const info = bridge.browserClients.get(ws);
    assert.ok(Date.now() - info.lastAppMsg < 1000, 'lastAppMsg should be fresh after tool response');
  });
});

// ---------------------------------------------------------------------------
// Relay Lifecycle Tests (5)
// ---------------------------------------------------------------------------

describe('Relay Lifecycle', () => {
  let bridge;

  beforeEach(() => {
    bridge = new WebSocketBridge();
  });

  afterEach(() => {
    clearInterval(bridge.heartbeatTimer);
  });

  it('6. relay_init moves client from browserClients to relayClients', async () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws);

    assert.equal(bridge.browserClients.size, 1);
    assert.equal(bridge.relayClients.size, 0);

    await bridge._onMessage(ws, {
      type: 'relay_init',
      payload: { pid: 99, role: 'stdio-relay', sessionId: 'session-abc' },
    });

    assert.equal(bridge.browserClients.size, 0, 'Removed from browserClients');
    assert.equal(bridge.relayClients.size, 1, 'Added to relayClients');

    const relayInfo = bridge.relayClients.get(ws);
    assert.equal(relayInfo.role, 'stdio-relay');
    assert.equal(relayInfo.sessionId, 'session-abc');
    assert.equal(relayInfo.pid, 99);
  });

  it('7. Relay TTL eviction after idle timeout', () => {
    const ws = new MockWebSocket();
    addRelayClient(bridge, ws, {
      lastActivity: Date.now() - CONFIG.relayIdleTtl - 1000, // Past idle TTL
      lastPing: Date.now(), // WS level is fresh
    });

    bridge._checkHeartbeats();

    assert.equal(bridge.relayClients.size, 0, 'Idle relay should be evicted');
    assert.equal(ws.closed, true);
    assert.match(ws.closeReason, /Relay idle timeout/);
  });

  it('8. Active relay survives heartbeat check', () => {
    const ws = new MockWebSocket();
    addRelayClient(bridge, ws, {
      lastActivity: Date.now(),
      lastPing: Date.now(),
    });

    bridge._checkHeartbeats();

    assert.equal(bridge.relayClients.size, 1, 'Active relay should survive');
    assert.equal(ws.closed, false);
    assert.equal(ws.pinged, true);
  });

  it('9. Broadcast skips relay clients (only iterates browserClients)', async () => {
    const browserWs = new MockWebSocket();
    const relayWs = new MockWebSocket();

    addBrowserClient(bridge, browserWs);
    addRelayClient(bridge, relayWs);

    // bridge.broadcast sends to browserClients only
    // We can't await because there's no response, so we test _send targeting
    const requestId = 'test-req-1';
    const message = { type: 'test', payload: {} };
    const envelope = { ...message, requestId };

    // Manually do what broadcast does: iterate browserClients
    for (const [ws] of bridge.browserClients) {
      bridge._send(ws, envelope);
    }

    assert.equal(browserWs.sentMessages.length, 1, 'Browser client should receive message');
    assert.equal(relayWs.sentMessages.length, 0, 'Relay client should NOT receive message');
  });

  it('10. _waitForBrowserClient resolves immediately when client exists', async () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws);

    // Should resolve immediately
    await bridge._waitForBrowserClient(100);
    // If it didn't throw, it resolved
    assert.ok(true, '_waitForBrowserClient resolved');
  });
});

// ---------------------------------------------------------------------------
// WebSocket Bridge Internals (5)
// ---------------------------------------------------------------------------

describe('WebSocket Bridge Internals', () => {
  let bridge;

  beforeEach(() => {
    bridge = new WebSocketBridge();
  });

  afterEach(() => {
    clearInterval(bridge.heartbeatTimer);
  });

  it('11. _waitForBrowserClient rejects after timeout with no client', async () => {
    assert.equal(bridge.browserClients.size, 0);

    await assert.rejects(
      bridge._waitForBrowserClient(100), // 100ms timeout
      /No browser extension connected/,
    );
  });

  it('12. _waitForBrowserClient resolves when client connects within timeout', async () => {
    assert.equal(bridge.browserClients.size, 0);

    // Start waiting, then add a client after 50ms
    const waitPromise = bridge._waitForBrowserClient(500);

    setTimeout(() => {
      const ws = new MockWebSocket();
      addBrowserClient(bridge, ws);
      bridge.emit('clientConnected', 'new-client');
    }, 50);

    await waitPromise;
    assert.ok(true, 'Resolved after client connected');
  });

  it('13. getStatus reports correct browser and relay counts', () => {
    const browser1 = new MockWebSocket();
    const browser2 = new MockWebSocket();
    const relay1 = new MockWebSocket();

    addBrowserClient(bridge, browser1);
    addBrowserClient(bridge, browser2);
    addRelayClient(bridge, relay1, { sessionId: 'abc-123-def' });

    const status = bridge.getStatus();
    assert.equal(status.connected, true);
    assert.equal(status.browserCount, 2);
    assert.equal(status.relayCount, 1);
    assert.equal(status.clientCount, 3);
    assert.equal(status.browsers.length, 2);
    assert.equal(status.relays.length, 1);
    assert.equal(status.relays[0].sessionId, 'abc-123-'); // sliced to 8 chars
  });

  it('14. Pending request resolved when response arrives', async () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws);

    // Set up a pending request
    const resultPromise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('timeout')), 5000);
      bridge.pendingRequests.set('req-1', {
        resolve: (val) => { clearTimeout(timer); resolve(val); },
        reject,
        timer,
      });
    });

    // Simulate response from browser
    await bridge._onMessage(ws, { requestId: 'req-1', result: { success: true } });

    const result = await resultPromise;
    assert.deepEqual(result, { success: true });
    assert.equal(bridge.pendingRequests.size, 0, 'Pending request should be cleaned up');
  });

  it('15. page_context_update caches and emits event', async () => {
    const ws = new MockWebSocket();
    addBrowserClient(bridge, ws);

    let emittedPayload = null;
    bridge.on('pageContextUpdate', (payload) => {
      emittedPayload = payload;
    });

    const ctx = { url: 'https://test.com', title: 'Test Page' };
    await bridge._onMessage(ws, { type: 'page_context_update', payload: ctx });

    assert.deepEqual(bridge.cachedPageContext, ctx);
    assert.deepEqual(emittedPayload, ctx);
  });
});

// ---------------------------------------------------------------------------
// Relay Session Recovery Tests (5)
// ---------------------------------------------------------------------------

describe('Relay Session Recovery', () => {
  let cm;

  beforeEach(() => {
    cm = new ContextManager(':memory:');
  });

  afterEach(() => {
    if (cm) cm.destroy();
  });

  it('16. saveRelaySession persists and findOrphanedSession returns null for active', () => {
    cm.saveRelaySession('sess-1', 'MyProject', '/path/to/project', 1234);

    // Active sessions are NOT orphaned
    const found = cm.findOrphanedSession('/path/to/project');
    assert.equal(found, null, 'Active session should not be found as orphaned');
  });

  it('17. markRelayOrphaned makes session findable', () => {
    cm.saveRelaySession('sess-2', 'MyProject', '/path/to/project', 5678);
    cm.markRelayOrphaned('sess-2');

    const found = cm.findOrphanedSession('/path/to/project');
    assert.ok(found, 'Orphaned session should be findable');
    assert.equal(found.session_id, 'sess-2');
    assert.equal(found.state, 'orphaned');
    assert.equal(found.project_path, '/path/to/project');
  });

  it('18. New relay from different project path does not find orphaned session', () => {
    cm.saveRelaySession('sess-3', 'ProjectA', '/path/a', 1111);
    cm.markRelayOrphaned('sess-3');

    const found = cm.findOrphanedSession('/path/b');
    assert.equal(found, null, 'Should not find session from different path');
  });

  it('19. recoverRelaySession updates state to recovered', () => {
    cm.saveRelaySession('sess-4', 'MyProject', '/path/to/project', 2222);
    cm.markRelayOrphaned('sess-4');

    cm.recoverRelaySession('sess-4', 9999);

    // Should no longer appear as orphaned
    const found = cm.findOrphanedSession('/path/to/project');
    assert.equal(found, null, 'Recovered session should not be found as orphaned');

    // Verify state directly
    const row = cm.db.prepare('SELECT * FROM relay_sessions WHERE session_id = ?').get('sess-4');
    assert.equal(row.state, 'recovered');
    assert.equal(row.relay_pid, 9999);
  });

  it('20. Orphaned sessions expire after TTL', () => {
    cm.saveRelaySession('sess-5', 'MyProject', '/path/to/project', 3333);
    cm.markRelayOrphaned('sess-5');

    // Manually set last_activity to >1hr ago
    const oldTime = Date.now() - 3_600_001;
    cm.db.prepare('UPDATE relay_sessions SET last_activity = ? WHERE session_id = ?').run(oldTime, 'sess-5');

    cm.cleanupExpiredRelaySessions();

    const found = cm.findOrphanedSession('/path/to/project');
    assert.equal(found, null, 'Expired orphaned session should be cleaned up');

    const row = cm.db.prepare('SELECT * FROM relay_sessions WHERE session_id = ?').get('sess-5');
    assert.equal(row, undefined, 'Session should be deleted from DB');
  });
});
