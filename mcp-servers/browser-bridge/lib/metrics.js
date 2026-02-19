/**
 * MetricsCollector — per-tool performance metrics with 1-hour rolling window.
 *
 * Zero dependencies. Memory bounded at ~180KB max at 60 req/min rate limit.
 */

const WINDOW_MS = 60 * 60 * 1000; // 1 hour
const PRUNE_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

export class MetricsCollector {
  constructor() {
    /** @type {Map<string, Array<{ts: number, duration: number, success: boolean, code?: string}>>} */
    this.events = new Map();
    this._pruneTimer = setInterval(() => this._prune(), PRUNE_INTERVAL_MS);
    if (this._pruneTimer.unref) this._pruneTimer.unref();
  }

  /**
   * Record a tool invocation.
   * @param {string} tool - Tool name
   * @param {number} duration - Duration in ms
   * @param {boolean} success - Whether the call succeeded
   * @param {string} [code] - Error code (only on failure)
   */
  record(tool, duration, success, code) {
    if (!this.events.has(tool)) this.events.set(tool, []);
    this.events.get(tool).push({ ts: Date.now(), duration, success, code });
  }

  /**
   * Return a snapshot of metrics within the rolling window.
   */
  getSnapshot() {
    const cutoff = Date.now() - WINDOW_MS;
    let totalCalls = 0;
    let totalErrors = 0;
    const perTool = {};

    for (const [tool, entries] of this.events) {
      const recent = entries.filter(e => e.ts > cutoff);
      if (recent.length === 0) continue;

      const successes = recent.filter(e => e.success).length;
      const failures = recent.length - successes;
      totalCalls += recent.length;
      totalErrors += failures;

      const durations = recent.map(e => e.duration).sort((a, b) => a - b);
      const avgDurationMs = Math.round(durations.reduce((s, d) => s + d, 0) / durations.length);
      const p95Index = Math.min(Math.floor(durations.length * 0.95), durations.length - 1);
      const p95DurationMs = durations[p95Index];

      // Error code breakdown for failures
      const errorCodes = {};
      for (const e of recent) {
        if (!e.success && e.code) {
          errorCodes[e.code] = (errorCodes[e.code] || 0) + 1;
        }
      }

      perTool[tool] = {
        calls: recent.length,
        successes,
        failures,
        avgDurationMs,
        p95DurationMs,
        ...(Object.keys(errorCodes).length > 0 && { errorCodes }),
      };
    }

    return { window: '1h', totalCalls, totalErrors, perTool };
  }

  /** Remove entries older than the rolling window. */
  _prune() {
    const cutoff = Date.now() - WINDOW_MS;
    for (const [tool, entries] of this.events) {
      const pruned = entries.filter(e => e.ts > cutoff);
      if (pruned.length === 0) {
        this.events.delete(tool);
      } else {
        this.events.set(tool, pruned);
      }
    }
  }

  destroy() {
    clearInterval(this._pruneTimer);
    this.events.clear();
  }
}
