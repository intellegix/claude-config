/**
 * test-context-manager.js — Unit tests for ContextManager SQLite persistence
 *
 * Copies ContextManager implementation from server.js locally since it's not exported.
 * Run with: node test-context-manager.js
 */

import assert from 'node:assert/strict';
import { describe, it, afterEach } from 'node:test';
import Database from 'better-sqlite3';
import { randomUUID } from 'node:crypto';

// ---------------------------------------------------------------------------
// Local copy of ContextManager (server.js doesn't export it)
// ---------------------------------------------------------------------------

const CONFIG = {
  dbPath: ':memory:',
  cleanupInterval: 300_000, // 5 min
};

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
    const sql = `
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
    `;
    this.db.exec(sql);
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
// Test Suite
// ---------------------------------------------------------------------------

describe('ContextManager — SQLite persistence', () => {
  let manager;

  afterEach(() => {
    if (manager) manager.destroy();
  });

  it('Constructor creates in-memory SQLite DB with correct schema', () => {
    manager = new ContextManager(':memory:');

    // Check tables exist
    const tables = manager.db.prepare(`
      SELECT name FROM sqlite_master WHERE type='table' ORDER BY name
    `).all().map(r => r.name);

    assert.deepEqual(tables, ['context_snapshots', 'conversations', 'messages']);

    // Check conversations table columns
    const convColumns = manager.db.prepare('PRAGMA table_info(conversations)').all();
    const convColNames = convColumns.map(c => c.name);
    assert.deepEqual(convColNames, ['id', 'title', 'created_at', 'updated_at']);

    // Check messages table columns
    const msgColumns = manager.db.prepare('PRAGMA table_info(messages)').all();
    const msgColNames = msgColumns.map(c => c.name);
    assert.deepEqual(msgColNames, ['id', 'conversation_id', 'role', 'content', 'timestamp']);

    // Check snapshots table columns
    const snapColumns = manager.db.prepare('PRAGMA table_info(context_snapshots)').all();
    const snapColNames = snapColumns.map(c => c.name);
    assert.deepEqual(snapColNames, ['id', 'url', 'title', 'content', 'tab_id', 'timestamp']);
  });

  it('createConversation() inserts and returns a UUID string', () => {
    manager = new ContextManager(':memory:');

    const convId = manager.createConversation('Test Conversation');

    // UUID format: 8-4-4-4-12 hex chars
    assert.match(convId, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);

    // Verify inserted
    const row = manager.db.prepare('SELECT * FROM conversations WHERE id = ?').get(convId);
    assert.equal(row.id, convId);
    assert.equal(row.title, 'Test Conversation');
    assert.ok(row.created_at > 0);
    assert.equal(row.created_at, row.updated_at);
  });

  it('getConversation() retrieves conversation with empty messages array', () => {
    manager = new ContextManager(':memory:');

    const convId = manager.createConversation('My Conversation');
    const conv = manager.getConversation(convId);

    assert.equal(conv.id, convId);
    assert.equal(conv.title, 'My Conversation');
    assert.ok(conv.created_at > 0);
    assert.ok(conv.updated_at > 0);
    assert.deepEqual(conv.messages, []);
  });

  it('addMessage() appends to conversation, messages retrieved in order', () => {
    manager = new ContextManager(':memory:');

    const convId = manager.createConversation('Chat');

    // Add messages in order
    const msg1Id = manager.addMessage(convId, 'user', 'Hello');
    const msg2Id = manager.addMessage(convId, 'assistant', 'Hi there!');
    const msg3Id = manager.addMessage(convId, 'user', 'How are you?');

    // Verify UUIDs
    assert.match(msg1Id, /^[0-9a-f]{8}-/i);
    assert.match(msg2Id, /^[0-9a-f]{8}-/i);
    assert.match(msg3Id, /^[0-9a-f]{8}-/i);

    // Retrieve conversation
    const conv = manager.getConversation(convId);
    assert.equal(conv.messages.length, 3);

    // Check order and content
    assert.equal(conv.messages[0].id, msg1Id);
    assert.equal(conv.messages[0].role, 'user');
    assert.equal(conv.messages[0].content, 'Hello');

    assert.equal(conv.messages[1].id, msg2Id);
    assert.equal(conv.messages[1].role, 'assistant');
    assert.equal(conv.messages[1].content, 'Hi there!');

    assert.equal(conv.messages[2].id, msg3Id);
    assert.equal(conv.messages[2].role, 'user');
    assert.equal(conv.messages[2].content, 'How are you?');

    // Timestamps should be in ascending order
    assert.ok(conv.messages[0].timestamp <= conv.messages[1].timestamp);
    assert.ok(conv.messages[1].timestamp <= conv.messages[2].timestamp);
  });

  it('saveSnapshot() stores page context with JSON stringified content', () => {
    manager = new ContextManager(':memory:');

    const pageData = {
      url: 'https://example.com',
      title: 'Example Page',
      tabId: 42,
      extra: { foo: 'bar', nested: [1, 2, 3] }
    };

    const snapId = manager.saveSnapshot(pageData);

    // Verify UUID
    assert.match(snapId, /^[0-9a-f]{8}-/i);

    // Retrieve from DB
    const row = manager.db.prepare('SELECT * FROM context_snapshots WHERE id = ?').get(snapId);
    assert.equal(row.id, snapId);
    assert.equal(row.url, 'https://example.com');
    assert.equal(row.title, 'Example Page');
    assert.equal(row.tab_id, 42);

    // Content should be JSON stringified
    const parsed = JSON.parse(row.content);
    assert.deepEqual(parsed, pageData);
    assert.ok(row.timestamp > 0);
  });

  it('getLatestSnapshot() returns most recent snapshot', () => {
    manager = new ContextManager(':memory:');

    // Save first snapshot
    manager.saveSnapshot({ url: 'https://first.com', title: 'First' });

    // Wait 5ms to ensure different timestamp
    const waitMs = 5;
    const start = Date.now();
    while (Date.now() - start < waitMs);

    // Save second snapshot
    manager.saveSnapshot({ url: 'https://second.com', title: 'Second' });

    // Get latest
    const latest = manager.getLatestSnapshot();
    assert.equal(latest.url, 'https://second.com');
    assert.equal(latest.title, 'Second');
  });

  it('cleanup() removes records older than 24h', () => {
    manager = new ContextManager(':memory:');

    const now = Date.now();
    const old = now - 86_400_000 - 1000; // 24h + 1s ago

    // Insert old conversation (directly manipulate updated_at)
    const oldConvId = randomUUID();
    manager.db.prepare('INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)')
      .run(oldConvId, 'Old', old, old);

    // Insert fresh conversation
    const freshConvId = manager.createConversation('Fresh');

    // Insert old message
    const oldMsgId = randomUUID();
    manager.db.prepare('INSERT INTO messages (id, conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)')
      .run(oldMsgId, freshConvId, 'user', 'Old message', old);

    // Insert fresh message
    manager.addMessage(freshConvId, 'user', 'Fresh message');

    // Insert old snapshot
    const oldSnapId = randomUUID();
    manager.db.prepare('INSERT INTO context_snapshots (id, url, title, content, tab_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)')
      .run(oldSnapId, 'https://old.com', 'Old', '{}', null, old);

    // Insert fresh snapshot
    manager.saveSnapshot({ url: 'https://fresh.com', title: 'Fresh' });

    // Verify counts before cleanup
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM conversations').get().c, 2);
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM messages').get().c, 2);
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM context_snapshots').get().c, 2);

    // Run cleanup
    manager.cleanup();

    // Verify old records removed
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM conversations WHERE id = ?').get(oldConvId).c, 0);
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM messages WHERE id = ?').get(oldMsgId).c, 0);
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM context_snapshots WHERE id = ?').get(oldSnapId).c, 0);

    // Verify fresh records remain
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM conversations WHERE id = ?').get(freshConvId).c, 1);
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM messages WHERE content = ?').get('Fresh message').c, 1);
    assert.equal(manager.db.prepare('SELECT COUNT(*) as c FROM context_snapshots WHERE url = ?').get('https://fresh.com').c, 1);
  });

  it('Empty DB: getConversation returns null, getLatestSnapshot returns null', () => {
    manager = new ContextManager(':memory:');

    const conv = manager.getConversation('nonexistent-id');
    assert.equal(conv, null);

    const snap = manager.getLatestSnapshot();
    assert.equal(snap, null);
  });

  it('Multiple snapshots — getLatestSnapshot returns newest', () => {
    manager = new ContextManager(':memory:');

    // Save 3 snapshots with small delays
    manager.saveSnapshot({ url: 'https://first.com', title: 'First' });

    let start = Date.now();
    while (Date.now() - start < 5);

    manager.saveSnapshot({ url: 'https://second.com', title: 'Second' });

    start = Date.now();
    while (Date.now() - start < 5);

    manager.saveSnapshot({ url: 'https://third.com', title: 'Third' });

    // Latest should be third
    const latest = manager.getLatestSnapshot();
    assert.equal(latest.url, 'https://third.com');
    assert.equal(latest.title, 'Third');

    // Verify all 3 exist
    const count = manager.db.prepare('SELECT COUNT(*) as c FROM context_snapshots').get().c;
    assert.equal(count, 3);
  });

  it('Schema has correct indexes', () => {
    manager = new ContextManager(':memory:');

    // Query sqlite_master for indexes
    const indexes = manager.db.prepare(`
      SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name
    `).all();

    // Expected: idx_messages_conv on messages, idx_snapshots_ts on context_snapshots
    assert.equal(indexes.length, 2);

    const indexNames = indexes.map(i => i.name);
    assert.ok(indexNames.includes('idx_messages_conv'));
    assert.ok(indexNames.includes('idx_snapshots_ts'));

    // Verify index on correct table
    const msgIndex = indexes.find(i => i.name === 'idx_messages_conv');
    assert.equal(msgIndex.tbl_name, 'messages');

    const snapIndex = indexes.find(i => i.name === 'idx_snapshots_ts');
    assert.equal(snapIndex.tbl_name, 'context_snapshots');
  });

  it('destroy() clears cleanup timer and closes DB', () => {
    manager = new ContextManager(':memory:');

    // Verify timer exists
    assert.ok(manager.cleanupTimer);

    // Destroy
    manager.destroy();

    // Timer should be cleared (can't easily verify with clearInterval, but no error thrown)
    // DB should be closed (subsequent ops would throw)
    assert.throws(() => {
      manager.db.prepare('SELECT 1').get();
    });
  });
});
