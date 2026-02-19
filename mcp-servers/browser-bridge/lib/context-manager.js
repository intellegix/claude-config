/**
 * ContextManager — SQLite persistence layer for conversations and context snapshots.
 */

import Database from 'better-sqlite3';
import { randomUUID } from 'node:crypto';
import { CONFIG } from './config.js';

export class ContextManager {
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

      CREATE TABLE IF NOT EXISTS relay_sessions (
        session_id TEXT PRIMARY KEY,
        project_label TEXT NOT NULL,
        project_path TEXT NOT NULL,
        relay_pid INTEGER,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
        last_activity INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
        state TEXT NOT NULL DEFAULT 'active'
      );

      CREATE INDEX IF NOT EXISTS idx_messages_conv
        ON messages(conversation_id);
      CREATE INDEX IF NOT EXISTS idx_snapshots_ts
        ON context_snapshots(timestamp);
      CREATE INDEX IF NOT EXISTS idx_relay_sessions_path
        ON relay_sessions(project_path, state);
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

  // --- Relay session persistence ---

  saveRelaySession(sessionId, projectLabel, projectPath, relayPid) {
    const now = Date.now();
    this.db.prepare(`
      INSERT OR REPLACE INTO relay_sessions (session_id, project_label, project_path, relay_pid, created_at, last_activity, state)
      VALUES (?, ?, ?, ?, ?, ?, 'active')
    `).run(sessionId, projectLabel, projectPath, relayPid, now, now);
  }

  markRelayOrphaned(sessionId) {
    this.db.prepare(`
      UPDATE relay_sessions SET state = 'orphaned', last_activity = ? WHERE session_id = ?
    `).run(Date.now(), sessionId);
  }

  findOrphanedSession(projectPath) {
    return this.db.prepare(`
      SELECT * FROM relay_sessions WHERE project_path = ? AND state = 'orphaned'
      ORDER BY last_activity DESC LIMIT 1
    `).get(projectPath) || null;
  }

  recoverRelaySession(sessionId, newRelayPid) {
    this.db.prepare(`
      UPDATE relay_sessions SET state = 'recovered', relay_pid = ?, last_activity = ?
      WHERE session_id = ?
    `).run(newRelayPid, Date.now(), sessionId);
  }

  cleanupExpiredRelaySessions(ttlMs = 3_600_000) {
    const cutoff = Date.now() - ttlMs;
    this.db.prepare(`
      DELETE FROM relay_sessions WHERE state = 'orphaned' AND last_activity < ?
    `).run(cutoff);
  }

  // --- Cleanup ---

  cleanup() {
    const cutoff = Date.now() - 86_400_000; // 24 hours
    this.db.prepare('DELETE FROM context_snapshots WHERE timestamp < ?').run(cutoff);
    this.db.prepare('DELETE FROM messages WHERE timestamp < ?').run(cutoff);
    this.db.prepare('DELETE FROM conversations WHERE updated_at < ?').run(cutoff);
    this.cleanupExpiredRelaySessions();
  }

  destroy() {
    clearInterval(this.cleanupTimer);
    try { this.db.close(); } catch { /* already closed */ }
  }
}
