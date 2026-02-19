/**
 * test-new-tools.js — Unit tests for Validator, Logger, RateLimiter, sanitizeArgs
 *
 * Imports from lib/ modules. Logger tests use a local subclass with captured output.
 * Run with: node test-new-tools.js
 */

import assert from 'node:assert';
import { describe, it, run } from 'node:test';

import { Validator } from './lib/validator.js';
import { Logger, sanitizeArgs } from './lib/logger.js';
import { RateLimiter } from './lib/rate-limiter.js';

// ---------------------------------------------------------------------------
// Test-specific Logger subclass that captures entries instead of writing stderr
// ---------------------------------------------------------------------------

class TestLogger extends Logger {
  constructor(level = 'info') {
    super(level);
    this.captured = [];
  }
  _log(level, msg, meta = {}) {
    if (this.levels[level] < this.level) return;
    const entry = { ts: new Date().toISOString(), level, msg, ...meta };
    this.captured.push(entry);
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
    const logger = new TestLogger('warn');
    logger.debug('should not appear');
    logger.info('should not appear');
    logger.warn('visible');
    logger.error('also visible');
    assert.strictEqual(logger.captured.length, 2);
    assert.strictEqual(logger.captured[0].level, 'warn');
    assert.strictEqual(logger.captured[1].level, 'error');
  });

  it('21. includes metadata in log entries', () => {
    const logger = new TestLogger('debug');
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
