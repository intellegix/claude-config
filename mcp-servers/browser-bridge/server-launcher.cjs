#!/usr/bin/env node
/**
 * ESM Launcher with crash diagnostics.
 *
 * Catches import-level failures (e.g., better-sqlite3 native binding mismatch)
 * that would otherwise die silently before any ESM code runs.
 * Logs to ~/.claude/mcp-debug.log for post-mortem analysis.
 */
const fs = require('fs');
const path = require('path');
const os = require('os');
const { pathToFileURL } = require('url');

const debugLogPath = path.join(os.homedir(), '.claude', 'mcp-debug.log');

// Rotate log if > 5MB (runs once per startup)
const MAX_LOG_SIZE = 5 * 1024 * 1024;
try {
  if (fs.existsSync(debugLogPath) && fs.statSync(debugLogPath).size > MAX_LOG_SIZE) {
    const oldPath = debugLogPath + '.old';
    if (fs.existsSync(oldPath)) fs.unlinkSync(oldPath);
    fs.renameSync(debugLogPath, oldPath);
  }
} catch (_) { /* ignore rotation errors */ }

function debugLog(msg) {
  try {
    fs.appendFileSync(debugLogPath, `${new Date().toISOString()} [PID:${process.pid}] ${msg}\n`);
  } catch (_) { /* ignore fs errors */ }
}

debugLog(`=== LAUNCHER START === cwd=${process.cwd()} argv=${process.argv.join(' ')} ppid=${process.ppid} node=${process.version}`);

// Forward all args (--standalone, etc.) to the ESM entry point
// Must convert to file:// URL for Windows ESM compatibility
const serverPath = path.join(__dirname, 'server.js');
const serverUrl = pathToFileURL(serverPath).href;

debugLog(`importing ${serverUrl}`);

import(serverUrl).then(() => {
  debugLog('ESM import resolved — server.js is running');
}).catch((err) => {
  debugLog(`FATAL: ESM import failed: ${err.stack || err.message || err}`);
  process.stderr.write(`[BrowserBridge] Launcher fatal: ${err.message}\n`);
  process.exit(1);
});
