/**
 * Logger — structured JSON logging to stderr.
 */

export class Logger {
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

export const log = new Logger(process.env.MCP_LOG_LEVEL || 'info');

/** Strip long text values from args for safe logging */
export function sanitizeArgs(args) {
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
