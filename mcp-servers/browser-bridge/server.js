#!/usr/bin/env node

/**
 * Claude Browser Bridge MCP Server v1.0
 *
 * Bidirectional bridge between Claude Code CLI and Chrome extension via WebSocket.
 * Replaces native messaging with a clean localhost WebSocket approach.
 *
 * Components:
 *   - ContextManager: SQLite-backed conversation/context persistence
 *   - WebSocketBridge: ws server on 127.0.0.1:8765 for Chrome extension connections
 *   - BrowserBridgeServer: MCP protocol handler with tool/resource definitions
 *   - Health check HTTP server on port 8766
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { WebSocketServer, WebSocket } from 'ws';
import Database from 'better-sqlite3';
import { createServer as createHttpServer } from 'node:http';
import { randomUUID } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { writeFileSync, readFileSync, mkdirSync, existsSync } from 'node:fs';
import { basename, dirname, join, resolve as pathResolve } from 'node:path';
import { homedir } from 'node:os';
import { execFileSync, spawn } from 'node:child_process';
import { appendFileSync, existsSync as fsExistsSync, statSync, unlinkSync, renameSync } from 'node:fs';

// ---------------------------------------------------------------------------
// Debug logging — writes to ~/.claude/mcp-debug.log for crash diagnostics
// ---------------------------------------------------------------------------

const _debugLogPath = join(homedir(), '.claude', 'mcp-debug.log');

// Rotate log if > 5MB (runs once per startup)
const _MAX_LOG_SIZE = 5 * 1024 * 1024;
try {
  if (fsExistsSync(_debugLogPath) && statSync(_debugLogPath).size > _MAX_LOG_SIZE) {
    const oldPath = _debugLogPath + '.old';
    if (fsExistsSync(oldPath)) unlinkSync(oldPath);
    renameSync(_debugLogPath, oldPath);
  }
} catch (_) { /* ignore rotation errors */ }

function _debugLog(msg) {
  try {
    appendFileSync(_debugLogPath, `${new Date().toISOString()} [PID:${process.pid}] ${msg}\n`);
  } catch (_) { /* ignore */ }
}
_debugLog(`imports OK — cwd=${process.cwd()} argv=${process.argv.join(' ')} ppid=${process.ppid}`);

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const CONFIG = {
  wsPort: parseInt(process.env.MCP_WS_PORT || '8765', 10),
  wsHost: '127.0.0.1',
  healthPort: parseInt(process.env.MCP_HEALTH_PORT || '8766', 10),
  requestTimeout: 15_000,
  heartbeatTimeout: 120_000,
  heartbeatCheck: 45_000,
  maxMessageSize: 50_000_000, // 50 MB — screenshots can be large
  dbPath: process.env.MCP_DB_PATH || ':memory:',
  cleanupInterval: 300_000, // 5 min
  relayIdleTtl: 900_000, // 15 minutes — evict idle relay clients
};

// ---------------------------------------------------------------------------
// Validator — input validation helpers
// ---------------------------------------------------------------------------

const Validator = {
  selector(val) {
    if (typeof val !== 'string' || val.trim().length === 0) throw new Error('Selector must be a non-empty string');
    if (val.length > 500) throw new Error('Selector too long (max 500 chars)');
    return val.trim();
  },
  url(val) {
    if (typeof val !== 'string' || val.trim().length === 0) throw new Error('URL must be a non-empty string');
    if (val.length > 2048) throw new Error('URL too long (max 2048 chars)');
    return val.trim();
  },
  text(val, maxLen = 100_000) {
    if (typeof val !== 'string') throw new Error('Text must be a string');
    if (val.length > maxLen) throw new Error(`Text too long (max ${maxLen} chars)`);
    return val;
  },
  expression(val) {
    if (typeof val !== 'string' || val.trim().length === 0) throw new Error('Expression must be a non-empty string');
    if (val.length > 100_000) throw new Error('Expression too long (max 100000 chars)');
    return val;
  },
  timeout(val, min = 100, max = 300_000, def = 15_000) {
    if (val === undefined || val === null) return def;
    const n = Number(val);
    if (isNaN(n) || n < min || n > max) throw new Error(`Timeout must be ${min}-${max}ms`);
    return n;
  },
  boolean(val, def = false) {
    if (val === undefined || val === null) return def;
    return !!val;
  },
  tabId(val) {
    if (val === undefined || val === null) return undefined;
    const n = Number(val);
    if (isNaN(n) || n <= 0) throw new Error('Invalid tabId');
    return n;
  },
  action(val, allowed) {
    if (typeof val !== 'string') throw new Error('Action must be a string');
    if (!allowed.includes(val)) throw new Error(`Invalid action: ${val}. Must be one of: ${allowed.join(', ')}`);
    return val;
  },
  object(val, name = 'value') {
    if (!val || typeof val !== 'object' || Array.isArray(val)) throw new Error(`${name} must be a non-empty object`);
    return val;
  },
  array(val, name = 'value') {
    if (!Array.isArray(val) || val.length === 0) throw new Error(`${name} must be a non-empty array`);
    return val;
  },
  key(val) {
    if (typeof val !== 'string' || val.length === 0) throw new Error('Key must be a non-empty string');
    if (val.length > 50) throw new Error('Key too long (max 50 chars)');
    return val;
  },
};

// ---------------------------------------------------------------------------
// Logger — structured JSON logging to stderr
// ---------------------------------------------------------------------------

class Logger {
  constructor(level = 'info') {
    this.levels = { debug: 0, info: 1, warn: 2, error: 3 };
    this.level = this.levels[level] ?? 1;
  }
  _log(level, msg, meta = {}) {
    if (this.levels[level] < this.level) return;
    const entry = {
      ts: new Date().toISOString(),
      level,
      msg,
      ...meta,
    };
    process.stderr.write(JSON.stringify(entry) + '\n');
  }
  debug(msg, meta) { this._log('debug', msg, meta); }
  info(msg, meta) { this._log('info', msg, meta); }
  warn(msg, meta) { this._log('warn', msg, meta); }
  error(msg, meta) { this._log('error', msg, meta); }
}

const log = new Logger(process.env.MCP_LOG_LEVEL || 'info');

/** Strip long text values from args for safe logging */
function sanitizeArgs(args) {
  if (!args || typeof args !== 'object') return args;
  const out = {};
  for (const [k, v] of Object.entries(args)) {
    if (typeof v === 'string' && v.length > 200) {
      out[k] = `[text: ${v.length} chars]`;
    } else if (typeof v === 'object' && v !== null) {
      out[k] = '[object]';
    } else {
      out[k] = v;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// RateLimiter — token bucket algorithm
// ---------------------------------------------------------------------------

class RateLimiter {
  constructor(maxTokens = 60, refillRate = 1) {
    this.buckets = new Map();
    this.maxTokens = maxTokens;
    this.refillRate = refillRate; // tokens per second
  }
  check(clientId) {
    const now = Date.now();
    let bucket = this.buckets.get(clientId);
    if (!bucket) {
      bucket = { tokens: this.maxTokens, lastRefill: now };
      this.buckets.set(clientId, bucket);
    }
    const elapsed = (now - bucket.lastRefill) / 1000;
    bucket.tokens = Math.min(this.maxTokens, bucket.tokens + elapsed * this.refillRate);
    bucket.lastRefill = now;
    if (bucket.tokens < 1) return false;
    bucket.tokens--;
    return true;
  }
}

const rateLimiter = new RateLimiter(60, 1);

// ---------------------------------------------------------------------------
// ContextManager — SQLite persistence layer
// ---------------------------------------------------------------------------

class ContextManager {
  constructor(dbPath = CONFIG.dbPath) {
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('synchronous = NORMAL');
    this.db.pragma('cache_size = 1000');
    this._initSchema();
    this.cleanupTimer = setInterval(() => this.cleanup(), CONFIG.cleanupInterval);
  }

  _initSchema() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );

      CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
      );

      CREATE TABLE IF NOT EXISTS context_snapshots (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        content TEXT,
        tab_id INTEGER,
        timestamp INTEGER NOT NULL
      );

      CREATE INDEX IF NOT EXISTS idx_messages_conv
        ON messages(conversation_id);
      CREATE INDEX IF NOT EXISTS idx_snapshots_ts
        ON context_snapshots(timestamp);
    `);
  }

  // --- Conversation CRUD ---

  createConversation(title = 'Untitled') {
    const id = randomUUID();
    const now = Date.now();
    this.db
      .prepare('INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)')
      .run(id, title, now, now);
    return id;
  }

  addMessage(conversationId, role, content) {
    const id = randomUUID();
    this.db
      .prepare('INSERT INTO messages (id, conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)')
      .run(id, conversationId, role, content, Date.now());
    return id;
  }

  getConversation(conversationId) {
    const conv = this.db
      .prepare('SELECT * FROM conversations WHERE id = ?')
      .get(conversationId);
    if (!conv) return null;
    const messages = this.db
      .prepare('SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp')
      .all(conversationId);
    return { ...conv, messages };
  }

  // --- Context snapshots ---

  saveSnapshot(data) {
    const id = randomUUID();
    this.db
      .prepare('INSERT INTO context_snapshots (id, url, title, content, tab_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)')
      .run(id, data.url || '', data.title || '', JSON.stringify(data), data.tabId || null, Date.now());
    return id;
  }

  getLatestSnapshot() {
    return this.db
      .prepare('SELECT * FROM context_snapshots ORDER BY timestamp DESC LIMIT 1')
      .get() || null;
  }

  // --- Cleanup ---

  cleanup() {
    const cutoff = Date.now() - 86_400_000; // 24 hours
    this.db.prepare('DELETE FROM context_snapshots WHERE timestamp < ?').run(cutoff);
    this.db.prepare('DELETE FROM messages WHERE timestamp < ?').run(cutoff);
    this.db.prepare('DELETE FROM conversations WHERE updated_at < ?').run(cutoff);
  }

  destroy() {
    clearInterval(this.cleanupTimer);
    try { this.db.close(); } catch { /* already closed */ }
  }
}

// ---------------------------------------------------------------------------
// WebSocketBridge — manages Chrome extension connections
// ---------------------------------------------------------------------------

class WebSocketBridge extends EventEmitter {
  constructor() {
    super();
    this.wss = null;
    this.browserClients = new Map();     // ws -> { id, lastPing, connectedAt }
    this.relayClients = new Map();       // ws -> { id, lastPing, connectedAt, role, sessionId, lastActivity, pid }
    this.pendingRequests = new Map();     // requestId -> { resolve, reject, timer }
    this.heartbeatTimer = null;
    this.cachedPageContext = null;
  }

  start() {
    return new Promise((resolve, reject) => {
      this.wss = new WebSocketServer({
        host: CONFIG.wsHost,
        port: CONFIG.wsPort,
        maxPayload: CONFIG.maxMessageSize,
      });

      this.wss.once('listening', () => {
        console.error(`[WebSocketBridge] Listening on ws://${CONFIG.wsHost}:${CONFIG.wsPort}`);
        // Re-attach persistent error handler after successful bind
        this.wss.on('error', (err) => {
          console.error('[WebSocketBridge] Server error:', err.message);
        });
        resolve();
      });

      this.wss.once('error', (err) => {
        console.error('[WebSocketBridge] Server error:', err.message);
        reject(err);
      });

      this.wss.on('connection', (ws) => this._onConnection(ws));
      this.heartbeatTimer = setInterval(() => this._checkHeartbeats(), CONFIG.heartbeatCheck);
    });
  }

  _onConnection(ws) {
    const clientId = randomUUID();
    this.browserClients.set(ws, { id: clientId, lastPing: Date.now(), connectedAt: Date.now() });

    // Send connection init
    this._send(ws, { type: 'connection_init', clientId, serverVersion: '1.0.0' });

    ws.on('message', (raw) => {
      try {
        const msg = JSON.parse(raw.toString());
        this._onMessage(ws, msg);
      } catch {
        console.error('[WebSocketBridge] Bad JSON from client');
      }
    });

    ws.on('pong', () => {
      const info = this.browserClients.get(ws) || this.relayClients.get(ws);
      if (info) info.lastPing = Date.now();
    });

    ws.on('close', () => {
      const closingInfo = this.browserClients.get(ws) || this.relayClients.get(ws);
      this.browserClients.delete(ws);
      this.relayClients.delete(ws);
      this.emit('clientDisconnected', clientId);
      log.info('ws_close', { clientId, browsers: this.browserClients.size, relays: this.relayClients.size });

      // When a relay disconnects, tell browser clients to close its session tabs
      if (closingInfo && closingInfo.role === 'stdio-relay' && closingInfo.sessionId) {
        const cleanup = { type: 'session_cleanup', payload: { sessionId: closingInfo.sessionId } };
        for (const [clientWs] of this.browserClients) {
          this._send(clientWs, cleanup);
        }
        console.error(`[WebSocketBridge] Sent session_cleanup for relay session ${closingInfo.sessionId.slice(0, 8)}`);
      }
    });

    ws.on('error', (err) => {
      console.error(`[WebSocketBridge] Client ${clientId} error:`, err.message);
    });

    this.emit('clientConnected', clientId);
    log.info('ws_connect', { clientId, browsers: this.browserClients.size, relays: this.relayClients.size });
  }

  async _onMessage(ws, msg) {
    // Update last activity
    const info = this.browserClients.get(ws) || this.relayClients.get(ws);
    if (info) info.lastPing = Date.now();

    // Handle relay client identification — move from browserClients to relayClients
    if (msg.type === 'relay_init') {
      const browserInfo = this.browserClients.get(ws);
      if (browserInfo) {
        this.browserClients.delete(ws);
        browserInfo.role = 'stdio-relay';
        browserInfo.sessionId = msg.payload?.sessionId;
        browserInfo.lastActivity = Date.now();
        browserInfo.pid = msg.payload?.pid;
        this.relayClients.set(ws, browserInfo);
      }
      log.info('relay_connect', { clientId: browserInfo?.id, pid: msg.payload?.pid, sessionId: msg.payload?.sessionId?.slice(0, 8), totalRelays: this.relayClients.size });
      return;
    }

    // Handle relay-forwarded tool calls — route to browser clients via broadcast
    if (msg.type === 'relay_forward') {
      // Track relay activity for idle TTL
      const relayInfo = this.relayClients.get(ws);
      if (relayInfo) relayInfo.lastActivity = Date.now();

      const relayRequestId = msg.requestId;
      const timeout = msg.timeout || CONFIG.requestTimeout;

      // Wait for a browser client if none connected (e.g. extension reconnecting)
      if (this.browserClients.size === 0) {
        try {
          await this._waitForBrowserClient();
        } catch {
          this._send(ws, { requestId: relayRequestId, error: 'No browser extension connected' });
          return;
        }
      }

      // Use a fresh requestId for the browser broadcast to avoid collision
      const browserRequestId = randomUUID();
      const envelope = { ...msg.payload, requestId: browserRequestId };

      const timer = setTimeout(() => {
        this.pendingRequests.delete(browserRequestId);
        this._send(ws, { requestId: relayRequestId, error: `Request timed out after ${timeout}ms` });
      }, timeout);

      this.pendingRequests.set(browserRequestId, {
        resolve: (result) => {
          this._send(ws, { requestId: relayRequestId, result });
        },
        reject: (err) => {
          this._send(ws, { requestId: relayRequestId, error: err.message });
        },
        timer,
      });

      for (const [clientWs] of this.browserClients) {
        this._send(clientWs, envelope);
      }
      return;
    }

    // Handle response to a pending request
    if (msg.requestId && this.pendingRequests.has(msg.requestId)) {
      const pending = this.pendingRequests.get(msg.requestId);
      this.pendingRequests.delete(msg.requestId);
      clearTimeout(pending.timer);
      if (msg.error) {
        pending.reject(new Error(msg.error));
      } else {
        pending.resolve(msg.result || msg);
      }
      return;
    }

    // Handle browser-initiated events
    if (msg.type === 'page_context_update') {
      this.cachedPageContext = msg.payload;
      this.emit('pageContextUpdate', msg.payload);
      return;
    }

    if (msg.type === 'pong' || msg.type === 'keepalive') {
      return; // heartbeat responses
    }

    // Forward unhandled events
    this.emit('message', msg);
  }

  /**
   * Wait up to `timeoutMs` for at least one non-relay browser client to connect.
   * Resolves immediately if one is already present.
   */
  _waitForBrowserClient(timeoutMs = 5000) {
    if (this.browserClients.size > 0) return Promise.resolve();

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.removeListener('clientConnected', onClient);
        reject(new Error('No browser extension connected'));
      }, timeoutMs);

      const onClient = () => {
        if (this.browserClients.size > 0) {
          clearTimeout(timer);
          this.removeListener('clientConnected', onClient);
          resolve();
        }
      };
      this.on('clientConnected', onClient);
    });
  }

  /**
   * Send a request to all connected browser extensions and await the first response.
   */
  async broadcast(message, timeout = CONFIG.requestTimeout) {
    await this._waitForBrowserClient();

    const requestId = randomUUID();
    const envelope = { ...message, requestId };
    log.debug('broadcast', { requestId, type: message.type });

    return new Promise((resolve, reject) => {
      const broadcastStart = Date.now();
      const timer = setTimeout(() => {
        this.pendingRequests.delete(requestId);
        log.warn('broadcast_timeout', { requestId, type: message.type, timeout });
        reject(new Error(`Request timed out after ${timeout}ms`));
      }, timeout);

      this.pendingRequests.set(requestId, {
        resolve: (result) => {
          log.debug('broadcast_response', { requestId, duration: Date.now() - broadcastStart });
          resolve(result);
        },
        reject,
        timer,
      });

      for (const [ws] of this.browserClients) {
        this._send(ws, envelope);
      }
    });
  }

  _send(ws, data) {
    if (ws.readyState === 1 /* OPEN */) {
      ws.send(JSON.stringify(data));
    }
  }

  _checkHeartbeats() {
    const now = Date.now();
    // Browser clients — standard heartbeat
    for (const [ws, info] of this.browserClients) {
      if (now - info.lastPing > CONFIG.heartbeatTimeout) {
        log.warn('ws_heartbeat_timeout', { clientId: info.id });
        ws.close(1000, 'Heartbeat timeout');
        this.browserClients.delete(ws);
      } else {
        ws.ping();
      }
    }
    // Relay clients — heartbeat + idle TTL eviction
    for (const [ws, info] of this.relayClients) {
      if (now - info.lastPing > CONFIG.heartbeatTimeout) {
        log.warn('ws_heartbeat_timeout', { clientId: info.id, type: 'relay' });
        ws.close(1000, 'Heartbeat timeout');
        this.relayClients.delete(ws);
      } else if (now - (info.lastActivity || info.connectedAt) > CONFIG.relayIdleTtl) {
        log.warn('relay_idle_evict', { clientId: info.id, sessionId: info.sessionId?.slice(0, 8), idleMin: Math.round((now - (info.lastActivity || info.connectedAt)) / 60000) });
        ws.close(1000, 'Relay idle timeout');
        this.relayClients.delete(ws);
      } else {
        ws.ping();
      }
    }
  }

  getStatus() {
    const now = Date.now();
    return {
      connected: this.browserClients.size > 0,
      clientCount: this.browserClients.size + this.relayClients.size,
      browserCount: this.browserClients.size,
      relayCount: this.relayClients.size,
      browsers: [...this.browserClients.values()].map(c => ({
        id: c.id,
        connectedAt: c.connectedAt,
        lastPing: c.lastPing,
      })),
      relays: [...this.relayClients.values()].map(c => ({
        id: c.id,
        connectedAt: c.connectedAt,
        lastPing: c.lastPing,
        sessionId: c.sessionId?.slice(0, 8),
        pid: c.pid,
        idleSeconds: Math.round((now - (c.lastActivity || c.connectedAt)) / 1000),
      })),
      cachedPageContext: this.cachedPageContext
        ? { url: this.cachedPageContext.url, title: this.cachedPageContext.title }
        : null,
    };
  }

  stop() {
    clearInterval(this.heartbeatTimer);
    for (const [ws] of this.browserClients) ws.close(1000, 'Server shutting down');
    for (const [ws] of this.relayClients) ws.close(1000, 'Server shutting down');
    for (const [, pending] of this.pendingRequests) {
      clearTimeout(pending.timer);
      pending.reject(new Error('Server shutting down'));
    }
    this.pendingRequests.clear();
    this.browserClients.clear();
    this.relayClients.clear();
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }
  }
}

// ---------------------------------------------------------------------------
// BrowserBridgeServer — MCP protocol handler
// ---------------------------------------------------------------------------

class BrowserBridgeServer {
  constructor() {
    _debugLog('constructor entered');
    this.contextManager = new ContextManager();
    this.bridge = new WebSocketBridge();
    this.healthServer = null;
    this.sessionId = randomUUID(); // Unique per CLI instance — used for tab group isolation
    this.projectLabel = basename(process.cwd()); // e.g. "Intellegix Chrome Ext"

    this.server = new Server(
      { name: 'claude-browser-bridge', version: '1.0.0' },
      { capabilities: { tools: {}, resources: {} } },
    );

    this._registerTools();
    this._registerResources();
    this._registerBridgeEvents();
    _debugLog(`constructor OK — sessionId=${this.sessionId} project=${this.projectLabel}`);
  }

  /** Inject sessionId and projectLabel into a payload object for tab group routing */
  _withSession(payload) {
    return { ...payload, sessionId: this.sessionId, projectLabel: this.projectLabel };
  }

  // -----------------------------------------------------------------------
  // Tool definitions
  // -----------------------------------------------------------------------

  _registerTools() {
    // --- List tools ---
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        {
          name: 'browser_execute',
          description: 'Execute a DOM action in the browser (click, type, etc.)',
          inputSchema: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['click', 'type', 'hover', 'focus', 'blur', 'select', 'check', 'uncheck'],
                description: 'DOM action to perform',
              },
              selector: { type: 'string', description: 'CSS selector targeting the element' },
              text: { type: 'string', description: 'Text to type (for "type" action)' },
              value: { type: 'string', description: 'Value to set (for "select" action)' },
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
            },
            required: ['action', 'selector'],
          },
        },
        {
          name: 'browser_navigate',
          description: 'Navigate the browser to a URL',
          inputSchema: {
            type: 'object',
            properties: {
              url: { type: 'string', description: 'URL to navigate to' },
              tabId: { type: 'number', description: 'Tab to navigate (uses active tab if omitted)' },
            },
            required: ['url'],
          },
        },
        {
          name: 'browser_get_context',
          description: 'Get the current page context (URL, title, selected text, meta)',
          inputSchema: {
            type: 'object',
            properties: {
              tabId: { type: 'number', description: 'Tab to query (uses active tab if omitted)' },
            },
          },
        },
        {
          name: 'browser_screenshot',
          description: 'Capture a screenshot of the current visible tab, a specific element, or the full scrollable page',
          inputSchema: {
            type: 'object',
            properties: {
              tabId: { type: 'number', description: 'Tab to capture (uses active tab if omitted)' },
              format: { type: 'string', enum: ['png', 'jpeg'], default: 'png' },
              quality: { type: 'number', description: 'JPEG quality 0-100 (only for jpeg format)' },
              selector: { type: 'string', description: 'CSS selector — capture only this element (cropped)' },
              fullPage: { type: 'boolean', description: 'Capture the entire scrollable page (stitched strips)' },
              savePath: { type: 'string', description: 'Absolute file path to save the screenshot to disk' },
            },
          },
        },
        {
          name: 'browser_sync_context',
          description: 'Sync conversation context between CLI and browser',
          inputSchema: {
            type: 'object',
            properties: {
              conversationId: { type: 'string', description: 'Conversation ID to sync' },
              messages: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    role: { type: 'string' },
                    content: { type: 'string' },
                  },
                },
                description: 'Messages to sync',
              },
            },
            required: ['conversationId', 'messages'],
          },
        },
        {
          name: 'browser_wait_for_element',
          description: 'Wait for a DOM element to appear (MutationObserver-based)',
          inputSchema: {
            type: 'object',
            properties: {
              selector: { type: 'string', description: 'CSS selector to wait for' },
              timeout: { type: 'number', description: 'Max wait time in ms (default 10000)', default: 10000 },
              tabId: { type: 'number', description: 'Target tab ID' },
            },
            required: ['selector'],
          },
        },
        {
          name: 'browser_fill_form',
          description: 'Fill multiple form fields in one call',
          inputSchema: {
            type: 'object',
            properties: {
              fields: {
                type: 'object',
                description: 'Map of selector to value pairs to fill',
                additionalProperties: { type: 'string' },
              },
              tabId: { type: 'number', description: 'Target tab ID' },
            },
            required: ['fields'],
          },
        },
        {
          name: 'browser_get_tabs',
          description: 'List all open browser tabs',
          inputSchema: { type: 'object', properties: {} },
        },
        {
          name: 'browser_switch_tab',
          description: 'Activate a specific browser tab',
          inputSchema: {
            type: 'object',
            properties: {
              tabId: { type: 'number', description: 'Tab ID to activate' },
            },
            required: ['tabId'],
          },
        },
        {
          name: 'browser_extract_data',
          description: 'Extract structured data from the page using CSS selectors',
          inputSchema: {
            type: 'object',
            properties: {
              selectors: {
                type: 'object',
                description: 'Map of field name to CSS selector for extraction',
                additionalProperties: { type: 'string' },
              },
              tabId: { type: 'number', description: 'Target tab ID' },
            },
            required: ['selectors'],
          },
        },
        {
          name: 'browser_scroll',
          description: 'Scroll the page to an element or by a specific amount',
          inputSchema: {
            type: 'object',
            properties: {
              selector: { type: 'string', description: 'CSS selector to scroll into view' },
              direction: { type: 'string', enum: ['up', 'down', 'left', 'right'] },
              amount: { type: 'number', description: 'Pixels to scroll (default 500)', default: 500 },
              tabId: { type: 'number', description: 'Target tab ID' },
            },
          },
        },
        {
          name: 'browser_close_session',
          description: 'Close all browser tabs opened by this Claude session. IMPORTANT: You MUST call this tool when you are finished with all browser automation work to prevent tab clutter. Always call this as your final browser action.',
          inputSchema: { type: 'object', properties: {} },
        },
        {
          name: 'browser_close_tabs',
          description: 'Close specific browser tabs by their IDs',
          inputSchema: {
            type: 'object',
            properties: {
              tabIds: {
                type: 'array',
                items: { type: 'number' },
                description: 'Array of tab IDs to close',
              },
            },
            required: ['tabIds'],
          },
        },
        {
          name: 'browser_select',
          description: 'Select an option from a dropdown/select element',
          inputSchema: {
            type: 'object',
            properties: {
              selector: { type: 'string', description: 'CSS selector for the select element' },
              value: { type: 'string', description: 'Option value or visible text to select' },
              tabId: { type: 'number', description: 'Target tab ID' },
            },
            required: ['selector', 'value'],
          },
        },
        {
          name: 'browser_evaluate',
          description: 'Execute arbitrary JavaScript in the page context and return the result. Useful for reading cookies, localStorage, DOM state, or running custom logic.',
          inputSchema: {
            type: 'object',
            properties: {
              expression: { type: 'string', description: 'JavaScript expression to evaluate in the page context' },
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
              returnByValue: { type: 'boolean', description: 'Whether to return the result by value (default true). Set false for large DOM objects.', default: true },
            },
            required: ['expression'],
          },
        },
        {
          name: 'browser_console_messages',
          description: 'Retrieve captured console log/warning/error/info messages from the page. Useful for debugging page errors and application state.',
          inputSchema: {
            type: 'object',
            properties: {
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
              level: { type: 'string', enum: ['all', 'log', 'warning', 'error', 'info'], description: 'Filter by log level (default: all)', default: 'all' },
              limit: { type: 'number', description: 'Max number of messages to return (default 100)', default: 100 },
              clear: { type: 'boolean', description: 'Clear the message buffer after reading', default: false },
            },
          },
        },
        {
          name: 'browser_press_key',
          description: 'Send a keyboard event to the page or a specific element. Supports named keys (Enter, Escape, Tab, ArrowUp, etc.) and modifier combinations.',
          inputSchema: {
            type: 'object',
            properties: {
              key: { type: 'string', description: 'Key name: Enter, Escape, Tab, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Backspace, Delete, Space, Home, End, PageUp, PageDown, or a single character' },
              selector: { type: 'string', description: 'CSS selector to focus before pressing key (optional)' },
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
              modifiers: {
                type: 'object',
                description: 'Modifier keys to hold during keypress',
                properties: {
                  ctrl: { type: 'boolean' },
                  shift: { type: 'boolean' },
                  alt: { type: 'boolean' },
                  meta: { type: 'boolean' },
                },
              },
            },
            required: ['key'],
          },
        },
        {
          name: 'browser_handle_dialog',
          description: 'Dismiss or accept a JavaScript alert/confirm/prompt dialog that is blocking automation. Must be called while the dialog is showing.',
          inputSchema: {
            type: 'object',
            properties: {
              action: { type: 'string', enum: ['accept', 'dismiss', 'send'], description: 'accept: click OK, dismiss: click Cancel, send: type text and click OK (for prompt dialogs)' },
              text: { type: 'string', description: 'Text to enter in a prompt dialog (only used with action: "send")' },
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
            },
            required: ['action'],
          },
        },
        {
          name: 'browser_insert_text',
          description: 'Insert text into React/framework-controlled inputs using a multi-strategy fallback chain (native setter, execCommand, clipboard paste, direct value). More reliable than browser_execute type for modern web apps.',
          inputSchema: {
            type: 'object',
            properties: {
              selector: { type: 'string', description: 'CSS selector for the target input/textarea/contenteditable element' },
              text: { type: 'string', description: 'The text to insert' },
              append: { type: 'boolean', description: 'If true, append to existing content instead of replacing (default: false)' },
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
            },
            required: ['selector', 'text'],
          },
        },
        {
          name: 'browser_cdp_type',
          description: 'Type text using CDP Input.dispatchKeyEvent — produces trusted keyboard events that trigger React and framework event handlers. Use this when browser_insert_text or browser_execute type fails to trigger slash commands, autocomplete, or other keyboard-driven UI.',
          inputSchema: {
            type: 'object',
            properties: {
              text: { type: 'string', description: 'The text to type character by character' },
              selector: { type: 'string', description: 'CSS selector to focus before typing (optional)' },
              delay: { type: 'number', description: 'Milliseconds between keystrokes (default: 50)' },
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
            },
            required: ['text'],
          },
        },
        {
          name: 'browser_wait_for_stable',
          description: 'Wait for streaming/dynamic content to stabilize. Polls an element\'s textContent and resolves when unchanged for the specified duration. Useful for waiting on LLM streaming responses, live feeds, or any content that updates incrementally.',
          inputSchema: {
            type: 'object',
            properties: {
              selector: { type: 'string', description: 'CSS selector for the element whose content to monitor' },
              stableMs: { type: 'number', description: 'Milliseconds of no change required to consider content stable (default: 8000)' },
              timeout: { type: 'number', description: 'Maximum wait time in milliseconds before returning with timedOut: true (default: 180000)' },
              pollInterval: { type: 'number', description: 'How often to check content in milliseconds (default: 2000)' },
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
            },
            required: ['selector'],
          },
        },
        {
          name: 'browser_activate_council',
          description: 'Activate Perplexity Model Council mode on the current page. Types /council slash command using trusted CDP keyboard events, waits for command palette, presses Enter, and verifies activation. Requires Perplexity Max subscription and /council shortcut configured in Perplexity settings.',
          inputSchema: {
            type: 'object',
            properties: {
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
            },
          },
        },
        {
          name: 'browser_export_council_md',
          description: "Click Perplexity's native 'Export as Markdown' from the three-dot menu on a council response page. Downloads the .md file to the browser's default downloads folder. Use after a council response has finished streaming.",
          inputSchema: {
            type: 'object',
            properties: {
              tabId: { type: 'number', description: 'Target tab ID (uses active tab if omitted)' },
            },
          },
        },
        {
          name: 'browser_add_to_space',
          description: "Add the current Perplexity thread to a Space. Opens the three-dot menu → 'Add to Space' → 'Choose Space' modal. Can list available spaces, add to an existing space by name (fuzzy match), or create a new space.",
          inputSchema: {
            type: 'object',
            properties: {
              spaceName: { type: 'string', description: 'Name of the space to add to. If omitted, returns list of available spaces.' },
              createIfMissing: { type: 'boolean', description: 'If true and spaceName not found, create a new space with that name. Default false.' },
              tabId: { type: 'number', description: 'Target tab ID (uses active session tab if omitted)' },
            },
          },
        },
        {
          name: 'council_query',
          description: 'Query 3 AI models (GPT-5.2, Claude Sonnet 4.5, Gemini 3 Pro) via Perplexity API or Playwright browser automation, then synthesize. Runs externally as subprocess — zero context tokens during execution. Results cached to ~/.claude/council-cache/. Returns synthesis only (~3-5K tokens). Default mode: browser ($0, uses Perplexity login).',
          inputSchema: {
            type: 'object',
            properties: {
              query: { type: 'string', description: 'The question or analysis request for the multi-model council' },
              mode: { type: 'string', enum: ['api', 'direct', 'browser', 'auto'], description: 'Query mode. browser: Playwright UI automation (reliable, ~90s, $0). api: Perplexity API + Opus synthesis (fast, ~20s, requires API keys). direct: Provider APIs directly. auto: try api, fallback to browser. Default: browser.' },
              includeContext: { type: 'boolean', description: 'Include project context (git log, CLAUDE.md, MEMORY.md). Default: true.' },
              headful: { type: 'boolean', description: 'Run browser in visible mode (browser/auto modes only). Default: false.' },
              opusSynthesis: { type: 'boolean', description: 'Run Opus 4.6 re-synthesis on browser results (requires ANTHROPIC_API_KEY). Default: false.' },
              autoPlan: { type: 'boolean', description: 'Automatically enter plan mode after receiving council results to study implementation. Default: true.' },
            },
            required: ['query'],
          },
        },
        {
          name: 'research_query',
          description: "Run a deep research query on Perplexity using /research mode via Playwright browser automation. Similar to council_query but uses Perplexity's deep research mode instead of multi-model council. Returns a comprehensive, single-thread research synthesis with citations. Good fallback when council mode defaults to single-model. Cost: $0 (uses Perplexity login session). Time: ~60-120s.",
          inputSchema: {
            type: 'object',
            properties: {
              query: { type: 'string', description: 'The research question or analysis request' },
              includeContext: { type: 'boolean', description: 'Include project context (git log, CLAUDE.md, MEMORY.md). Default: true.' },
              headful: { type: 'boolean', description: 'Run browser in visible mode. Default: false.' },
              opusSynthesis: { type: 'boolean', description: 'Run Opus 4.6 re-synthesis on results (requires ANTHROPIC_API_KEY). Default: false.' },
            },
            required: ['query'],
          },
        },
        {
          name: 'council_metrics',
          description: 'Get operational metrics from the council pipeline run log. Shows degradation ratio, avg cost, per-mode breakdown, error rate. Read-only — no network calls. Use to check pipeline health.',
          inputSchema: {
            type: 'object',
            properties: {},
          },
        },
        {
          name: 'council_read',
          description: 'Read cached council results from the most recent council_query. No network calls, no subprocess — pure file read. Use after council_query to retrieve results at different detail levels.',
          inputSchema: {
            type: 'object',
            properties: {
              level: { type: 'string', enum: ['synthesis', 'full', 'gpt-5.2', 'claude-sonnet-4.5', 'gemini-3-pro'], description: 'Detail level. synthesis: Opus analysis only (~3K tokens). full: all model responses + synthesis. Or a model name for one response. Default: synthesis.' },
            },
          },
        },
      ],
    }));

    // --- Call tool handler ---
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;
      const start = Date.now();
      log.info('tool_call', { tool: name, sessionId: this.sessionId, args: sanitizeArgs(args) });

      // Rate limiting
      if (!rateLimiter.check(this.sessionId)) {
        log.warn('rate_limited', { tool: name, sessionId: this.sessionId });
        return {
          content: [{ type: 'text', text: 'Error: Rate limit exceeded (60 req/min). Please wait.' }],
          isError: true,
        };
      }

      try {
        const result = await this._handleToolCall(name, args || {});
        log.info('tool_result', { tool: name, duration: Date.now() - start, success: true });

        // Screenshot results carry _screenshotData — return as MCP image content
        if (result && result._screenshotData) {
          const { base64, mimeType, meta } = result._screenshotData;
          const content = [
            { type: 'image', data: base64, mimeType },
          ];
          if (meta && Object.keys(meta).length > 0) {
            content.push({ type: 'text', text: JSON.stringify(meta, null, 2) });
          }
          return { content };
        }

        return {
          content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
        };
      } catch (err) {
        log.error('tool_error', { tool: name, duration: Date.now() - start, error: err.message });
        return {
          content: [{ type: 'text', text: `Error: ${err.message}` }],
          isError: true,
        };
      }
    });
  }

  async _handleToolCall(name, args) {
    switch (name) {
      case 'browser_execute': {
        const action = Validator.action(args.action, ['click', 'type', 'hover', 'focus', 'blur', 'select', 'check', 'uncheck']);
        const selector = Validator.selector(args.selector);
        const text = args.text !== undefined ? Validator.text(args.text, 50_000) : undefined;
        const value = args.value !== undefined ? Validator.text(args.value, 1000) : undefined;
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast({
          type: 'action_request',
          payload: this._withSession({ action, selector, text, value, tabId }),
        });
      }

      case 'browser_navigate': {
        const url = Validator.url(args.url);
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast({
          type: 'navigate',
          payload: this._withSession({ url, tabId }),
        });
      }

      case 'browser_get_context': {
        const tabId = Validator.tabId(args.tabId);
        try {
          const live = await this.bridge.broadcast(
            { type: 'get_context', payload: this._withSession({ tabId }) },
            5000,
          );
          return live;
        } catch {
          const snapshot = this.contextManager.getLatestSnapshot();
          if (snapshot) {
            return { source: 'cache', ...JSON.parse(snapshot.content) };
          }
          throw new Error('No browser context available (extension not connected and no cache)');
        }
      }

      case 'browser_screenshot': {
        const format = Validator.action(args.format || 'png', ['png', 'jpeg']);
        const mimeType = format === 'jpeg' ? 'image/jpeg' : 'image/png';
        const quality = args.quality !== undefined ? Validator.timeout(args.quality, 1, 100, 80) : undefined;
        const fullPage = Validator.boolean(args.fullPage);
        const selector = args.selector ? Validator.selector(args.selector) : undefined;
        const savePath = args.savePath ? Validator.text(args.savePath, 500) : undefined;
        const tabId = Validator.tabId(args.tabId);
        let broadcastType = 'screenshot';
        let timeout = CONFIG.requestTimeout;

        if (fullPage) {
          broadcastType = 'screenshot_full_page';
          timeout = 120_000;
        } else if (selector) {
          broadcastType = 'screenshot_element';
          timeout = 30_000;
        }

        const result = await this.bridge.broadcast(
          {
            type: broadcastType,
            payload: this._withSession({ tabId, format, quality, selector }),
          },
          timeout,
        );

        let base64 = result.screenshot || '';
        if (base64.startsWith('data:')) {
          base64 = base64.split(',')[1];
        }

        const meta = {};
        if (result.width) meta.width = result.width;
        if (result.height) meta.height = result.height;
        if (result.warning) meta.warning = result.warning;

        if (savePath) {
          try {
            const absPath = pathResolve(savePath);
            mkdirSync(dirname(absPath), { recursive: true });
            writeFileSync(absPath, Buffer.from(base64, 'base64'));
            meta.savedTo = absPath;
          } catch (saveErr) {
            meta.saveError = saveErr.message;
          }
        }

        return { _screenshotData: { base64, mimeType, meta } };
      }

      case 'browser_sync_context': {
        Validator.text(args.conversationId, 200);
        Validator.array(args.messages, 'messages');
        let convId = args.conversationId;
        const conv = this.contextManager.getConversation(convId);
        if (!conv) {
          convId = this.contextManager.createConversation(`sync-${convId}`);
        }
        for (const msg of args.messages) {
          this.contextManager.addMessage(convId, msg.role, msg.content);
        }
        try {
          await this.bridge.broadcast({
            type: 'context_sync',
            payload: this._withSession({ conversationId: convId, messages: args.messages }),
          });
        } catch { /* browser not connected, still saved locally */ }
        return { conversationId: convId, messageCount: args.messages.length, synced: true };
      }

      case 'browser_wait_for_element': {
        const selector = Validator.selector(args.selector);
        const timeout = Validator.timeout(args.timeout, 100, 60_000, 10_000);
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast(
          {
            type: 'action_request',
            payload: this._withSession({ action: 'waitForElement', selector, timeout, tabId }),
          },
          timeout + 2000,
        );
      }

      case 'browser_fill_form': {
        const fields = Validator.object(args.fields, 'fields');
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast({
          type: 'action_request',
          payload: this._withSession({ action: 'fillForm', fields, tabId }),
        });
      }

      case 'browser_get_tabs':
        return this.bridge.broadcast({ type: 'get_tabs', payload: this._withSession({}) });

      case 'browser_switch_tab': {
        const tabId = Validator.tabId(args.tabId);
        if (!tabId) throw new Error('tabId is required');
        return this.bridge.broadcast({
          type: 'switch_tab',
          payload: this._withSession({ tabId }),
        });
      }

      case 'browser_extract_data': {
        const selectors = Validator.object(args.selectors, 'selectors');
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast({
          type: 'action_request',
          payload: this._withSession({ action: 'extractData', selectors, tabId }),
        });
      }

      case 'browser_scroll': {
        const selector = args.selector ? Validator.selector(args.selector) : undefined;
        const direction = args.direction ? Validator.action(args.direction, ['up', 'down', 'left', 'right']) : undefined;
        const amount = Validator.timeout(args.amount, 1, 10_000, 500);
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast({
          type: 'action_request',
          payload: this._withSession({
            action: 'scroll',
            selector,
            direction,
            amount,
            tabId,
          }),
        });
      }

      case 'browser_close_session':
        return this.bridge.broadcast(
          { type: 'session_cleanup', payload: this._withSession({}) },
          5000,
        );

      case 'browser_close_tabs': {
        const tabIds = Validator.array(args.tabIds, 'tabIds');
        tabIds.forEach((id, i) => { if (typeof id !== 'number' || id <= 0) throw new Error(`tabIds[${i}] must be a positive number`); });
        return this.bridge.broadcast(
          { type: 'close_tabs', payload: this._withSession({ tabIds }) },
          5000,
        );
      }

      case 'browser_select': {
        const selector = Validator.selector(args.selector);
        const tabId = Validator.tabId(args.tabId);
        Validator.text(args.value, 1000);
        return this.bridge.broadcast({
          type: 'action_request',
          payload: this._withSession({ action: 'selectOption', selector, value: args.value, tabId }),
        });
      }

      case 'browser_evaluate': {
        const expression = Validator.expression(args.expression);
        const tabId = Validator.tabId(args.tabId);
        const returnByValue = Validator.boolean(args.returnByValue, true);
        return this.bridge.broadcast(
          {
            type: 'evaluate',
            payload: this._withSession({ expression, tabId, returnByValue }),
          },
          30_000,
        );
      }

      case 'browser_console_messages': {
        const tabId = Validator.tabId(args.tabId);
        const clear = Validator.boolean(args.clear);
        const level = args.level ? Validator.action(args.level, ['all', 'log', 'warning', 'error', 'info']) : 'all';
        const limit = Validator.timeout(args.limit, 1, 500, 100);
        const result = await this.bridge.broadcast({
          type: 'get_console_messages',
          payload: this._withSession({ level, limit, tabId }),
        });
        if (clear && result && result.success) {
          try {
            await this.bridge.broadcast({
              type: 'evaluate',
              payload: this._withSession({
                expression: 'window.__claudeConsoleMessages = []; true;',
                tabId,
              }),
            }, 5000);
          } catch { /* non-fatal */ }
        }
        return result;
      }

      case 'browser_press_key': {
        const key = Validator.key(args.key);
        const selector = args.selector ? Validator.selector(args.selector) : undefined;
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast({
          type: 'action_request',
          payload: this._withSession({ action: 'pressKey', key, selector, modifiers: args.modifiers, tabId }),
        });
      }

      case 'browser_handle_dialog': {
        const action = Validator.action(args.action, ['accept', 'dismiss', 'send']);
        const text = args.text !== undefined ? Validator.text(args.text, 10_000) : undefined;
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast(
          {
            type: 'handle_dialog',
            payload: this._withSession({ action, text, tabId }),
          },
          10_000,
        );
      }

      case 'browser_insert_text': {
        const selector = Validator.selector(args.selector);
        const text = Validator.text(args.text);
        const append = Validator.boolean(args.append);
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast(
          {
            type: 'action_request',
            payload: this._withSession({ action: 'insertText', selector, text, append, tabId }),
          },
          30_000,
        );
      }

      case 'browser_cdp_type': {
        const text = Validator.text(args.text, 10_000);
        const selector = args.selector ? Validator.selector(args.selector) : undefined;
        const delay = Validator.timeout(args.delay, 0, 1000, 50);
        const tabId = Validator.tabId(args.tabId);
        const timeout = Math.max(15_000, text.length * (delay + 100));
        return this.bridge.broadcast(
          {
            type: 'cdp_type',
            payload: this._withSession({ text, selector, delay, tabId }),
          },
          timeout,
        );
      }

      case 'browser_wait_for_stable': {
        const selector = Validator.selector(args.selector);
        const actionTimeout = Validator.timeout(args.timeout, 1000, 300_000, 180_000);
        const stableMs = Validator.timeout(args.stableMs, 100, 60_000, 8_000);
        const pollInterval = Validator.timeout(args.pollInterval, 100, 30_000, 2_000);
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast(
          {
            type: 'action_request',
            payload: this._withSession({ action: 'waitForStable', selector, stableMs, timeout: actionTimeout, pollInterval, tabId }),
          },
          actionTimeout + 5000,
        );
      }

      case 'browser_activate_council': {
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast(
          { type: 'activate_council', payload: this._withSession({ tabId }) },
          15_000,
        );
      }

      case 'browser_export_council_md': {
        const tabId = Validator.tabId(args.tabId);
        return this.bridge.broadcast(
          { type: 'export_council_md', payload: this._withSession({ tabId }) },
          15_000,
        );
      }

      case 'browser_add_to_space': {
        const tabId = Validator.tabId(args.tabId);
        const spaceName = args.spaceName ? Validator.text(args.spaceName, 200) : undefined;
        const createIfMissing = Validator.boolean(args.createIfMissing);
        return this.bridge.broadcast(
          { type: 'add_to_space', payload: this._withSession({ tabId, spaceName, createIfMissing }) },
          20_000,
        );
      }

      case 'research_query':
      case 'council_query': {
        const query = Validator.text(args.query, 10_000);
        const isResearch = name === 'research_query';
        const validModes = ['api', 'direct', 'browser', 'auto'];
        // Default to browser mode (no API keys needed). research_query always uses browser.
        const mode = isResearch ? 'browser' : (validModes.includes(args.mode) ? args.mode : 'browser');
        const includeContext = Validator.boolean(args.includeContext, true);
        const scriptDir = join(homedir(), '.claude', 'council-automation');
        const cacheDir = join(homedir(), '.claude', 'council-cache');

        // Ensure cache dir exists
        mkdirSync(cacheDir, { recursive: true });

        // Generate session context if requested
        if (includeContext) {
          try {
            const ctxOut = execFileSync('python', [join(scriptDir, 'session_context.py'), process.cwd()], {
              timeout: 10_000,
              encoding: 'utf-8',
              env: { ...process.env },
            });
            writeFileSync(join(cacheDir, 'session_context.md'), ctxOut, 'utf-8');
          } catch (ctxErr) {
            log.warn('council_context_failed', { error: ctxErr.message });
            // Non-fatal — query will proceed without context
          }
        }

        const scriptArgs = [join(scriptDir, 'council_query.py'), '--mode', mode];
        if (includeContext && existsSync(join(cacheDir, 'session_context.md'))) {
          scriptArgs.push('--context-file', join(cacheDir, 'session_context.md'));
        }
        if (args.headful) scriptArgs.push('--headful');
        if (args.opusSynthesis) scriptArgs.push('--opus-synthesis');
        if (isResearch) scriptArgs.push('--perplexity-mode', 'research');
        scriptArgs.push(query);

        // Browser/auto modes need longer timeout; research mode needs even more (deep research does multiple rounds)
        const timeout = isResearch ? 300_000 : (mode === 'browser' || mode === 'auto') ? 210_000 : 150_000;
        const result = execFileSync('python', scriptArgs, {
          timeout,
          encoding: 'utf-8',
          env: { ...process.env },
          cwd: scriptDir,
        });
        // Check for browser busy error (concurrent session holding the profile lock)
        if (result.includes('BROWSER_BUSY')) {
          return {
            error: 'Another browser council/research session is active. Wait ~2 min or use --mode api.',
            code: 'BROWSER_BUSY',
          };
        }
        return { synthesis: result };
      }

      case 'council_metrics': {
        const scriptDir = join(homedir(), '.claude', 'council-automation');
        const result = execFileSync('python', [
          join(scriptDir, 'council_metrics.py'), '--json',
        ], {
          timeout: 10_000,
          encoding: 'utf-8',
          env: { ...process.env },
          cwd: scriptDir,
        });
        return JSON.parse(result);
      }

      case 'council_read': {
        const level = args.level || 'synthesis';
        const scriptDir = join(homedir(), '.claude', 'council-automation');

        const result = execFileSync('python', [
          join(scriptDir, 'council_query.py'),
          level === 'full' ? '--read-full' : level === 'synthesis' ? '--read' : '--read-model',
          ...(level !== 'full' && level !== 'synthesis' ? [level] : []),
        ], {
          timeout: 10_000,
          encoding: 'utf-8',
          env: { ...process.env },
          cwd: scriptDir,
        });
        return JSON.parse(result);
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  }

  // -----------------------------------------------------------------------
  // Resource definitions
  // -----------------------------------------------------------------------

  _registerResources() {
    this.server.setRequestHandler(ListResourcesRequestSchema, async () => ({
      resources: [
        {
          uri: 'browser://current-page',
          name: 'Current Page Context',
          description: 'Latest cached browser page context (URL, title, content)',
          mimeType: 'application/json',
        },
        {
          uri: 'browser://connection-status',
          name: 'Bridge Connection Status',
          description: 'WebSocket bridge and extension connection health',
          mimeType: 'application/json',
        },
      ],
    }));

    this.server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
      const { uri } = request.params;

      if (uri === 'browser://current-page') {
        const ctx = this.bridge.cachedPageContext;
        const snapshot = this.contextManager.getLatestSnapshot();
        const data = ctx || (snapshot ? JSON.parse(snapshot.content) : { message: 'No page context available' });
        return {
          contents: [{ uri, mimeType: 'application/json', text: JSON.stringify(data, null, 2) }],
        };
      }

      if (uri === 'browser://connection-status') {
        return {
          contents: [{
            uri,
            mimeType: 'application/json',
            text: JSON.stringify(this.bridge.getStatus(), null, 2),
          }],
        };
      }

      throw new Error(`Unknown resource: ${uri}`);
    });
  }

  // -----------------------------------------------------------------------
  // Bridge event handlers
  // -----------------------------------------------------------------------

  _registerBridgeEvents() {
    this.bridge.on('pageContextUpdate', (payload) => {
      try {
        this.contextManager.saveSnapshot(payload);
      } catch (err) {
        console.error('[BrowserBridge] Failed to save context snapshot:', err.message);
      }
    });

    this.bridge.on('clientConnected', (clientId) => {
      console.error(`[BrowserBridge] Extension connected: ${clientId}`);
    });

    this.bridge.on('clientDisconnected', (clientId) => {
      console.error(`[BrowserBridge] Extension disconnected: ${clientId}`);
    });
  }

  // -----------------------------------------------------------------------
  // Health check HTTP server
  // -----------------------------------------------------------------------

  _startHealthServer() {
    return new Promise((resolve, reject) => {
      this.healthServer = createHttpServer((req, res) => {
        if (req.url === '/' || req.url === '/health') {
          const status = this.bridge.getStatus();
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

      this.healthServer.once('error', (err) => {
        console.error('[HealthCheck] Server error:', err.message);
        reject(err);
      });

      this.healthServer.listen(CONFIG.healthPort, CONFIG.wsHost, () => {
        console.error(`[HealthCheck] Listening on http://${CONFIG.wsHost}:${CONFIG.healthPort}/health`);
        // Re-attach persistent error handler after successful bind
        this.healthServer.on('error', (err) => {
          console.error('[HealthCheck] Server error:', err.message);
        });
        resolve();
      });
    });
  }

  // -----------------------------------------------------------------------
  // Relay mode — connect to existing WS server as client
  // -----------------------------------------------------------------------

  _connectAsRelay() {
    _debugLog(`_connectAsRelay() entered — target ws://${CONFIG.wsHost}:${CONFIG.wsPort}`);
    return new Promise((resolve, reject) => {
      const wsUrl = `ws://${CONFIG.wsHost}:${CONFIG.wsPort}`;
      this._relayWs = null;
      this._relayPending = new Map();
      this._relayReconnectTimer = null;
      this._relayConnected = false;

      const connect = (isInitial = false) => {
        _debugLog(`_connectAsRelay() connect() isInitial=${isInitial}`);
        const ws = new WebSocket(wsUrl, { maxPayload: CONFIG.maxMessageSize });

        ws.on('open', () => {
          this._relayWs = ws;
          this._relayConnected = true;
          _debugLog('_connectAsRelay() WS open — sending relay_init');
          console.error('[BrowserBridge] Relay connected to primary WS server');

          // Identify as relay, not browser extension — include sessionId for cleanup on disconnect
          ws.send(JSON.stringify({
            type: 'relay_init',
            payload: { pid: process.pid, role: 'stdio-relay', sessionId: this.sessionId },
          }));

          if (isInitial) resolve();
        });

        ws.on('message', (data) => {
          try {
            const msg = JSON.parse(data.toString());

            // Handle responses to our forwarded requests
            if (msg.requestId && this._relayPending.has(msg.requestId)) {
              const pending = this._relayPending.get(msg.requestId);
              this._relayPending.delete(msg.requestId);
              clearTimeout(pending.timer);
              if (msg.error) {
                pending.reject(new Error(msg.error));
              } else {
                pending.resolve(msg.result);
              }
              return;
            }

            // Ignore connection_init from primary server
            if (msg.type === 'connection_init') return;
          } catch (e) {
            console.error('[BrowserBridge] Relay parse error:', e.message);
          }
        });

        ws.on('close', () => {
          this._relayConnected = false;
          this._relayWs = null;
          console.error('[BrowserBridge] Relay disconnected — reconnecting in 3s');
          // Reject all pending requests
          for (const [id, pending] of this._relayPending) {
            clearTimeout(pending.timer);
            pending.reject(new Error('Relay connection lost'));
          }
          this._relayPending.clear();
          this._relayReconnectTimer = setTimeout(() => connect(false), 3000);
        });

        ws.on('error', (err) => {
          _debugLog(`_connectAsRelay() WS error: ${err.code || err.message} isInitial=${isInitial} connected=${this._relayConnected}`);
          console.error('[BrowserBridge] Relay WS error:', err.message);
          if (isInitial && !this._relayConnected) {
            reject(err);
          }
        });
      };

      connect(true);

      // --- Relay death detection ---
      // Strategy 1: stdin close (primary — OS closes pipe when parent dies)
      // NOTE: Do NOT call process.stdin.resume() here! StdioServerTransport
      // reads MCP messages from stdin. Calling resume() before the transport
      // is connected puts stdin into flowing mode, discarding the MCP
      // initialize handshake. The 'end'/'close' listeners work because
      // StdioServerTransport resumes stdin when it starts reading.
      const stdinCleanup = () => {
        _debugLog('relay stdin closed — parent exited');
        console.error('[BrowserBridge] Relay stdin closed — parent exited, shutting down');
        clearTimeout(this._relayReconnectTimer);
        if (this._ppidCheckTimer) clearInterval(this._ppidCheckTimer);
        if (this._relayWs) this._relayWs.close(1000, 'Parent process exited');
        process.exit(0);
      };
      process.stdin.on('end', stdinCleanup);
      process.stdin.on('close', stdinCleanup);

      // Strategy 2: PPID polling (backup — catches edge cases on Windows/Git Bash)
      const parentPid = process.ppid;
      this._ppidCheckTimer = setInterval(() => {
        try {
          process.kill(parentPid, 0); // signal 0 = existence check, no actual signal sent
        } catch (e) {
          if (e.code === 'ESRCH') {
            console.error(`[BrowserBridge] Relay parent PID ${parentPid} gone — shutting down`);
            clearInterval(this._ppidCheckTimer);
            clearTimeout(this._relayReconnectTimer);
            if (this._relayWs) this._relayWs.close(1000, 'Parent process exited');
            process.exit(0);
          }
        }
      }, 10_000);

      // Override bridge.broadcast to relay through the primary server
      const originalBroadcast = this.bridge.broadcast.bind(this.bridge);
      this.bridge.broadcast = (message, timeout = CONFIG.requestTimeout) => {
        if (!this._relayWs || this._relayWs.readyState !== WebSocket.OPEN) {
          return Promise.reject(new Error('Relay not connected to primary server'));
        }

        const requestId = randomUUID();

        return new Promise((resolve, reject) => {
          const timer = setTimeout(() => {
            this._relayPending.delete(requestId);
            reject(new Error(`Relay request timed out after ${timeout}ms`));
          }, timeout);

          this._relayPending.set(requestId, { resolve, reject, timer });

          this._relayWs.send(JSON.stringify({
            type: 'relay_forward',
            requestId,
            payload: message,
            timeout,
          }));
        });
      };

      // Override bridge.getStatus for relay mode
      this.bridge.getStatus = () => ({
        connected: this._relayConnected,
        mode: 'relay',
        relayTarget: wsUrl,
        clientCount: this._relayConnected ? 1 : 0,
        clients: [],
        cachedPageContext: this.bridge.cachedPageContext,
      });
    });
  }

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  async start() {
    const isStandalone = process.argv.includes('--standalone');
    _debugLog(`start() entered — standalone=${isStandalone}`);

    try {
      await this.bridge.start();
      await this._startHealthServer();
      _debugLog('start() primary mode — WS+Health bound OK');
      console.error('[BrowserBridge] Primary mode — owns WebSocket + Health servers');
    } catch (err) {
      if (err.code === 'EADDRINUSE' && !isStandalone) {
        _debugLog(`start() EADDRINUSE — switching to relay mode`);
        console.error('[BrowserBridge] Ports in use — connecting as relay client');
        await this._connectAsRelay();
        _debugLog('start() relay connected OK');
      } else {
        _debugLog(`start() FATAL bind error: ${err.code || err.message}`);
        throw err;
      }
    }

    if (!isStandalone) {
      _debugLog('start() connecting MCP stdio transport...');
      const transport = new StdioServerTransport();
      await this.server.connect(transport);
      _debugLog('start() MCP stdio connected — server ready');
      console.error('[BrowserBridge] MCP server started (stdio transport)');
    } else {
      _debugLog('start() standalone mode — no stdio');
      console.error('[BrowserBridge] Running in standalone mode (WebSocket + Health only)');
    }
  }

  async shutdown() {
    console.error('[BrowserBridge] Shutting down...');

    // Notify extension to close this session's tabs
    try {
      await this.bridge.broadcast(
        { type: 'session_cleanup', payload: this._withSession({}) },
        3000,
      );
    } catch { /* extension may not be connected */ }

    // Clean up relay if in relay mode
    if (this._ppidCheckTimer) clearInterval(this._ppidCheckTimer);
    if (this._relayReconnectTimer) clearTimeout(this._relayReconnectTimer);
    if (this._relayWs) {
      this._relayWs.close(1000, 'Relay shutting down');
      this._relayWs = null;
    }
    if (this._relayPending) {
      for (const [, pending] of this._relayPending) {
        clearTimeout(pending.timer);
        pending.reject(new Error('Server shutting down'));
      }
      this._relayPending.clear();
    }

    this.bridge.stop();
    this.contextManager.destroy();

    if (this.healthServer) {
      await new Promise((resolve) => this.healthServer.close(resolve));
    }

    await this.server.close();
    console.error('[BrowserBridge] Shutdown complete');
  }
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

_debugLog('creating BrowserBridgeServer instance...');
const serverInstance = new BrowserBridgeServer();

async function main() {
  await serverInstance.start();
}

// Graceful shutdown
function handleShutdown(signal) {
  _debugLog(`shutdown signal: ${signal}`);
  console.error(`\n[BrowserBridge] Received ${signal}, shutting down...`);
  serverInstance.shutdown().then(() => process.exit(0)).catch(() => process.exit(1));
}

process.on('SIGINT', () => handleShutdown('SIGINT'));
process.on('SIGTERM', () => handleShutdown('SIGTERM'));
process.on('uncaughtException', (err) => {
  _debugLog(`UNCAUGHT: ${err.stack || err.message}`);
  console.error('[BrowserBridge] Uncaught exception:', err);
});
process.on('unhandledRejection', (err) => {
  _debugLog(`UNHANDLED_REJECTION: ${err?.stack || err?.message || err}`);
  console.error('[BrowserBridge] Unhandled rejection:', err);
});

main().catch((err) => {
  _debugLog(`main() FATAL: ${err.stack || err.message}`);
  console.error('[BrowserBridge] Fatal error:', err);
  process.exit(1);
});
