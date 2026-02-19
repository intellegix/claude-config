/**
 * Validator — input validation helpers for MCP tool arguments.
 */

export const Validator = {
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
