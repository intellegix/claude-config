/**
 * Configuration constants and debug logging for Claude Browser Bridge.
 */

import { join } from 'node:path';
import { homedir } from 'node:os';
import { appendFileSync, existsSync, statSync, unlinkSync, renameSync } from 'node:fs';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export const CONFIG = {
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
// Debug logging — writes to ~/.claude/mcp-debug.log for crash diagnostics
// ---------------------------------------------------------------------------

const _debugLogPath = join(homedir(), '.claude', 'mcp-debug.log');

// Rotate log if > 5MB (runs once per startup)
const _MAX_LOG_SIZE = 5 * 1024 * 1024;
try {
  if (existsSync(_debugLogPath) && statSync(_debugLogPath).size > _MAX_LOG_SIZE) {
    const oldPath = _debugLogPath + '.old';
    if (existsSync(oldPath)) unlinkSync(oldPath);
    renameSync(_debugLogPath, oldPath);
  }
} catch (_) { /* ignore rotation errors */ }

export function _debugLog(msg) {
  try {
    appendFileSync(_debugLogPath, `${new Date().toISOString()} [PID:${process.pid}] ${msg}\n`);
  } catch (_) { /* ignore */ }
}
