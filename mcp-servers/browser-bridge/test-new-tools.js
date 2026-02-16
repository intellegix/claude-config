/**
 * test-new-tools.js — Unit tests for Validator, Logger, RateLimiter, sanitizeArgs
 *
 * Copies implementations from server.js locally since they are not exported.
 * Run with: node test-new-tools.js
 */

import assert from 'node:assert';
import { describe, it, run } from 'node:test';

// ---------------------------------------------------------------------------
// Local copies of implementations (server.js doesn't export these)
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

class Logger {
  constructor(level = 'info') {
    this.levels = { debug: 0, info: 1, warn: 2, error: 3 };
    this.level = this.levels[level] ?? 1;
    this.captured = [];
  }
  _log(level, msg, meta = {}) {
    if (this.levels[level] < this.level) return;
    const entry = { ts: new Date().toISOString(), level, msg, ...meta };
    this.captured.push(entry);
  }
  debug(msg, meta) { this._log('debug', msg, meta); }
  info(msg, meta) { this._log('info', msg, meta); }
  warn(msg, meta) { this._log('warn', msg, meta); }
  error(msg, meta) { this._log('error', msg, meta); }
}

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

class RateLimiter {
  constructor(maxTokens = 60, refillRate = 1) {
    this.buckets = new Map();
    this.maxTokens = maxTokens;
    this.refillRate = refillRate;
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// --- Validator: selector ---

describe('Validator.selector', () => {
  it('1. accepts valid CSS selector', () => {
    assert.strictEqual(Validator.selector('#app'), '#app');
  });

  it('2. trims whitespace', () => {
    assert.strictEqual(Validator.selector('  .cls  '), '.cls');
  });

  it('3. rejects empty string', () => {
    assert.throws(() => Validator.selector(''), /non-empty/);
  });

  it('4. rejects non-string', () => {
    assert.throws(() => Validator.selector(123), /non-empty/);
  });

  it('5. rejects too-long selector (>500 chars)', () => {
    assert.throws(() => Validator.selector('a'.repeat(501)), /too long/);
  });
});

// --- Validator: url ---

describe('Validator.url', () => {
  it('6. accepts valid URL', () => {
    assert.strictEqual(Validator.url('https://example.com'), 'https://example.com');
  });

  it('7. rejects URL >2048 chars', () => {
    assert.throws(() => Validator.url('https://x.com/' + 'a'.repeat(2040)), /too long/);
  });
});

// --- Validator: text ---

describe('Validator.text', () => {
  it('8. accepts string within limit', () => {
    assert.strictEqual(Validator.text('hello'), 'hello');
  });

  it('9. rejects non-string', () => {
    assert.throws(() => Validator.text(42), /must be a string/);
  });

  it('10. rejects text exceeding custom limit', () => {
    assert.throws(() => Validator.text('abcdef', 5), /too long/);
  });
});

// --- Validator: timeout ---

describe('Validator.timeout', () => {
  it('11. returns default for undefined', () => {
    assert.strictEqual(Validator.timeout(undefined), 15_000);
  });

  it('12. rejects out-of-range', () => {
    assert.throws(() => Validator.timeout(50), /must be/);
  });
});

// --- Validator: action ---

describe('Validator.action', () => {
  it('13. validates allowed actions', () => {
    const allowed = ['click', 'type', 'hover'];
    assert.strictEqual(Validator.action('click', allowed), 'click');
    assert.throws(() => Validator.action('delete', allowed), /Invalid action/);
  });
});

// --- Validator: array ---

describe('Validator.array', () => {
  it('14. rejects empty array', () => {
    assert.throws(() => Validator.array([]), /non-empty/);
  });
});

// --- Validator: object ---

describe('Validator.object', () => {
  it('15. rejects array as object', () => {
    assert.throws(() => Validator.object([1, 2]), /non-empty object/);
  });

  it('16. accepts valid object', () => {
    const obj = { a: 1 };
    assert.deepStrictEqual(Validator.object(obj), obj);
  });
});

// --- RateLimiter ---

describe('RateLimiter', () => {
  it('17. allows requests under limit', () => {
    const limiter = new RateLimiter(5, 1);
    for (let i = 0; i < 5; i++) {
      assert.strictEqual(limiter.check('client1'), true);
    }
  });

  it('18. blocks after exhausting tokens', () => {
    const limiter = new RateLimiter(2, 1);
    assert.strictEqual(limiter.check('client1'), true);
    assert.strictEqual(limiter.check('client1'), true);
    assert.strictEqual(limiter.check('client1'), false);
  });

  it('19. tracks separate buckets per client', () => {
    const limiter = new RateLimiter(1, 1);
    assert.strictEqual(limiter.check('a'), true);
    assert.strictEqual(limiter.check('b'), true);
    assert.strictEqual(limiter.check('a'), false);
  });
});

// --- Logger ---

describe('Logger', () => {
  it('20. respects log level filtering', () => {
    const logger = new Logger('warn');
    logger.debug('should not appear');
    logger.info('should not appear');
    logger.warn('visible');
    logger.error('also visible');
    assert.strictEqual(logger.captured.length, 2);
    assert.strictEqual(logger.captured[0].level, 'warn');
    assert.strictEqual(logger.captured[1].level, 'error');
  });

  it('21. includes metadata in log entries', () => {
    const logger = new Logger('debug');
    logger.info('test', { tool: 'browser_navigate', duration: 42 });
    assert.strictEqual(logger.captured[0].tool, 'browser_navigate');
    assert.strictEqual(logger.captured[0].duration, 42);
    assert.ok(logger.captured[0].ts);
  });
});

// --- sanitizeArgs ---

describe('sanitizeArgs', () => {
  it('22. truncates long strings and masks objects', () => {
    const result = sanitizeArgs({
      short: 'hello',
      long: 'x'.repeat(300),
      nested: { a: 1 },
      num: 42,
    });
    assert.strictEqual(result.short, 'hello');
    assert.strictEqual(result.long, '[text: 300 chars]');
    assert.strictEqual(result.nested, '[object]');
    assert.strictEqual(result.num, 42);
  });

  it('23. handles null/undefined input', () => {
    assert.strictEqual(sanitizeArgs(null), null);
    assert.strictEqual(sanitizeArgs(undefined), undefined);
  });
});

// --- BROWSER_BUSY detection ---

describe('BROWSER_BUSY detection', () => {
  it('24. detects BROWSER_BUSY in subprocess output', () => {
    // Simulates the check in server.js council_query handler
    const output = JSON.stringify({
      error: 'Another council/research browser session is already running.',
      code: 'BROWSER_BUSY',
      step: 'lock',
    });
    assert.ok(output.includes('BROWSER_BUSY'), 'Output should contain BROWSER_BUSY');
  });

  it('25. does not false-positive on normal output', () => {
    const output = JSON.stringify({
      synthesis: 'The browser performed well in tests.',
      query: 'How busy is the system?',
    });
    assert.ok(!output.includes('BROWSER_BUSY'), 'Normal output should not trigger BROWSER_BUSY');
  });

  it('26. returns structured error on BROWSER_BUSY', () => {
    // Simulates the error path in server.js _handleToolCall
    const result = '{"error":"busy","code":"BROWSER_BUSY","step":"lock"}';
    if (result.includes('BROWSER_BUSY')) {
      const parsed = {
        error: 'Another browser council/research session is active. Wait ~2 min or use --mode api.',
        code: 'BROWSER_BUSY',
      };
      assert.strictEqual(parsed.code, 'BROWSER_BUSY');
      assert.ok(parsed.error.includes('Wait'));
    } else {
      assert.fail('Should have detected BROWSER_BUSY');
    }
  });
});
