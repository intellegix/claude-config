/**
 * test-handlers.js — Unit tests for tool handler routing, validation, and result transformation
 *
 * Tests the _handleToolCall routing logic in isolation by importing Validator from lib/
 * and replicating the routing code. Also tests _withSession injection and screenshot
 * result transformation.
 *
 * Run with: node --test test-handlers.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { Validator } from './lib/validator.js';

// ---------------------------------------------------------------------------
// Test helpers — routing logic replicated from server.js for isolated testing
// ---------------------------------------------------------------------------

// Simulates _withSession()
function withSession(payload) {
  return { ...payload, sessionId: 'test-session-id', projectLabel: 'TestProject' };
}

/**
 * Replicate the routing logic of _handleToolCall without actually calling bridge.broadcast.
 * Returns { broadcastType, broadcastPayload, broadcastTimeout } or throws on validation error.
 * For tools that don't broadcast (council_read, council_metrics), returns { directResult: ... }.
 */
function routeToolCall(name, args) {
  const CONFIG_requestTimeout = 15_000;

  switch (name) {
    case 'browser_execute': {
      const action = Validator.action(args.action, ['click', 'type', 'hover', 'focus', 'blur', 'select', 'check', 'uncheck']);
      const selector = Validator.selector(args.selector);
      const text = args.text !== undefined ? Validator.text(args.text, 50_000) : undefined;
      const value = args.value !== undefined ? Validator.text(args.value, 1000) : undefined;
      const tabId = Validator.tabId(args.tabId);
      return {
        broadcastType: 'action_request',
        broadcastPayload: withSession({ action, selector, text, value, tabId }),
        broadcastTimeout: CONFIG_requestTimeout,
      };
    }

    case 'browser_navigate': {
      const url = Validator.url(args.url);
      const tabId = Validator.tabId(args.tabId);
      return {
        broadcastType: 'navigate',
        broadcastPayload: withSession({ url, tabId }),
        broadcastTimeout: CONFIG_requestTimeout,
      };
    }

    case 'browser_screenshot': {
      const format = Validator.action(args.format || 'png', ['png', 'jpeg']);
      const quality = args.quality !== undefined ? Validator.timeout(args.quality, 1, 100, 80) : undefined;
      const fullPage = Validator.boolean(args.fullPage);
      const selector = args.selector ? Validator.selector(args.selector) : undefined;
      const savePath = args.savePath ? Validator.text(args.savePath, 500) : undefined;
      const tabId = Validator.tabId(args.tabId);
      let broadcastType = 'screenshot';
      let timeout = CONFIG_requestTimeout;

      if (fullPage) {
        broadcastType = 'screenshot_full_page';
        timeout = 120_000;
      } else if (selector) {
        broadcastType = 'screenshot_element';
        timeout = 30_000;
      }

      return {
        broadcastType,
        broadcastPayload: withSession({ tabId, format, quality, selector }),
        broadcastTimeout: timeout,
      };
    }

    case 'browser_evaluate': {
      const expression = Validator.expression(args.expression);
      const tabId = Validator.tabId(args.tabId);
      const returnByValue = Validator.boolean(args.returnByValue, true);
      return {
        broadcastType: 'evaluate',
        broadcastPayload: withSession({ expression, tabId, returnByValue }),
        broadcastTimeout: 30_000,
      };
    }

    case 'browser_console_messages': {
      const tabId = Validator.tabId(args.tabId);
      const clear = Validator.boolean(args.clear);
      const level = args.level ? Validator.action(args.level, ['all', 'log', 'warning', 'error', 'info']) : 'all';
      const limit = Validator.timeout(args.limit, 1, 500, 100);
      return {
        broadcastType: 'get_console_messages',
        broadcastPayload: withSession({ level, limit, tabId }),
        broadcastTimeout: CONFIG_requestTimeout,
      };
    }

    case 'browser_handle_dialog': {
      const action = Validator.action(args.action, ['accept', 'dismiss', 'send']);
      const text = args.text !== undefined ? Validator.text(args.text, 10_000) : undefined;
      const tabId = Validator.tabId(args.tabId);
      return {
        broadcastType: 'handle_dialog',
        broadcastPayload: withSession({ action, text, tabId }),
        broadcastTimeout: 10_000,
      };
    }

    case 'browser_insert_text': {
      const selector = Validator.selector(args.selector);
      const text = Validator.text(args.text);
      const append = Validator.boolean(args.append);
      const tabId = Validator.tabId(args.tabId);
      return {
        broadcastType: 'action_request',
        broadcastPayload: withSession({ action: 'insertText', selector, text, append, tabId }),
        broadcastTimeout: 30_000,
      };
    }

    case 'browser_cdp_type': {
      const text = Validator.text(args.text, 10_000);
      const selector = args.selector ? Validator.selector(args.selector) : undefined;
      const delay = Validator.timeout(args.delay, 0, 1000, 50);
      const tabId = Validator.tabId(args.tabId);
      const timeout = Math.max(15_000, text.length * (delay + 100));
      return {
        broadcastType: 'cdp_type',
        broadcastPayload: withSession({ text, selector, delay, tabId }),
        broadcastTimeout: timeout,
      };
    }

    case 'browser_press_key': {
      const key = Validator.key(args.key);
      const selector = args.selector ? Validator.selector(args.selector) : undefined;
      const tabId = Validator.tabId(args.tabId);
      return {
        broadcastType: 'action_request',
        broadcastPayload: withSession({ action: 'pressKey', key, selector, modifiers: args.modifiers, tabId }),
        broadcastTimeout: CONFIG_requestTimeout,
      };
    }

    case 'browser_wait_for_stable': {
      const selector = Validator.selector(args.selector);
      const actionTimeout = Validator.timeout(args.timeout, 1000, 300_000, 180_000);
      const stableMs = Validator.timeout(args.stableMs, 100, 60_000, 8_000);
      const pollInterval = Validator.timeout(args.pollInterval, 100, 30_000, 2_000);
      const tabId = Validator.tabId(args.tabId);
      return {
        broadcastType: 'action_request',
        broadcastPayload: withSession({ action: 'waitForStable', selector, stableMs, timeout: actionTimeout, pollInterval, tabId }),
        broadcastTimeout: actionTimeout + 5000,
      };
    }

    case 'browser_close_session':
      return {
        broadcastType: 'session_cleanup',
        broadcastPayload: withSession({}),
        broadcastTimeout: 5000,
      };

    case 'browser_close_tabs': {
      const tabIds = Validator.array(args.tabIds, 'tabIds');
      tabIds.forEach((id, i) => { if (typeof id !== 'number' || id <= 0) throw new Error(`tabIds[${i}] must be a positive number`); });
      return {
        broadcastType: 'close_tabs',
        broadcastPayload: withSession({ tabIds }),
        broadcastTimeout: 5000,
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

/** Replicate screenshot result transformation from server.js */
function transformScreenshotResult(broadcastResult, format, savePath) {
  let base64 = broadcastResult.screenshot || '';
  if (base64.startsWith('data:')) {
    base64 = base64.split(',')[1];
  }
  const mimeType = format === 'jpeg' ? 'image/jpeg' : 'image/png';
  const meta = {};
  if (broadcastResult.width) meta.width = broadcastResult.width;
  if (broadcastResult.height) meta.height = broadcastResult.height;
  if (broadcastResult.warning) meta.warning = broadcastResult.warning;
  return { _screenshotData: { base64, mimeType, meta } };
}

// ============================================================================
// Tests
// ============================================================================

describe('Tool Handler Routing', () => {
  // --- Navigation & Tab routing ---
  describe('browser_navigate', () => {
    it('routes with URL → broadcasts navigate type', () => {
      const result = routeToolCall('browser_navigate', { url: 'https://example.com' });
      assert.equal(result.broadcastType, 'navigate');
      assert.equal(result.broadcastPayload.url, 'https://example.com');
      assert.ok(result.broadcastPayload.sessionId);
      assert.ok(result.broadcastPayload.projectLabel);
    });

    it('includes tabId in broadcast when provided', () => {
      const result = routeToolCall('browser_navigate', { url: 'https://example.com', tabId: 42 });
      assert.equal(result.broadcastPayload.tabId, 42);
    });

    it('throws validation error for missing URL', () => {
      assert.throws(
        () => routeToolCall('browser_navigate', {}),
        /URL must be a non-empty string/
      );
    });
  });

  // --- Screenshot routing ---
  describe('browser_screenshot', () => {
    it('default (no args) → broadcasts screenshot type with 15s timeout', () => {
      const result = routeToolCall('browser_screenshot', {});
      assert.equal(result.broadcastType, 'screenshot');
      assert.equal(result.broadcastTimeout, 15_000);
    });

    it('with selector → broadcasts screenshot_element with 30s timeout', () => {
      const result = routeToolCall('browser_screenshot', { selector: '#main' });
      assert.equal(result.broadcastType, 'screenshot_element');
      assert.equal(result.broadcastTimeout, 30_000);
      assert.equal(result.broadcastPayload.selector, '#main');
    });

    it('with fullPage → broadcasts screenshot_full_page with 120s timeout', () => {
      const result = routeToolCall('browser_screenshot', { fullPage: true });
      assert.equal(result.broadcastType, 'screenshot_full_page');
      assert.equal(result.broadcastTimeout, 120_000);
    });

    it('rejects invalid format', () => {
      assert.throws(
        () => routeToolCall('browser_screenshot', { format: 'bmp' }),
        /Invalid action: bmp/
      );
    });
  });

  // --- DOM action routing ---
  describe('browser_execute', () => {
    it('click + selector → broadcasts action_request with correct shape', () => {
      const result = routeToolCall('browser_execute', { action: 'click', selector: '#btn' });
      assert.equal(result.broadcastType, 'action_request');
      assert.equal(result.broadcastPayload.action, 'click');
      assert.equal(result.broadcastPayload.selector, '#btn');
    });

    it('throws for missing selector', () => {
      assert.throws(
        () => routeToolCall('browser_execute', { action: 'click' }),
        /Selector must be a non-empty string/
      );
    });

    it('throws for invalid action', () => {
      assert.throws(
        () => routeToolCall('browser_execute', { action: 'doubleclick', selector: '#btn' }),
        /Invalid action: doubleclick/
      );
    });
  });

  // --- CDP tools routing ---
  describe('CDP tools', () => {
    it('browser_evaluate with expression → broadcasts evaluate type', () => {
      const result = routeToolCall('browser_evaluate', { expression: 'document.title' });
      assert.equal(result.broadcastType, 'evaluate');
      assert.equal(result.broadcastPayload.expression, 'document.title');
      assert.equal(result.broadcastPayload.returnByValue, true);
      assert.equal(result.broadcastTimeout, 30_000);
    });

    it('browser_console_messages with level filter → broadcasts get_console_messages', () => {
      const result = routeToolCall('browser_console_messages', { level: 'error', limit: 50 });
      assert.equal(result.broadcastType, 'get_console_messages');
      assert.equal(result.broadcastPayload.level, 'error');
      assert.equal(result.broadcastPayload.limit, 50);
    });

    it('browser_handle_dialog with action=accept → broadcasts handle_dialog', () => {
      const result = routeToolCall('browser_handle_dialog', { action: 'accept' });
      assert.equal(result.broadcastType, 'handle_dialog');
      assert.equal(result.broadcastPayload.action, 'accept');
      assert.equal(result.broadcastTimeout, 10_000);
    });
  });

  // --- Input tools ---
  describe('Input tools', () => {
    it('browser_insert_text → broadcasts action_request with insertText action', () => {
      const result = routeToolCall('browser_insert_text', { selector: 'textarea', text: 'hello' });
      assert.equal(result.broadcastType, 'action_request');
      assert.equal(result.broadcastPayload.action, 'insertText');
      assert.equal(result.broadcastPayload.selector, 'textarea');
      assert.equal(result.broadcastPayload.text, 'hello');
      assert.equal(result.broadcastPayload.append, false);
    });

    it('browser_cdp_type → broadcasts cdp_type', () => {
      const result = routeToolCall('browser_cdp_type', { text: '/council' });
      assert.equal(result.broadcastType, 'cdp_type');
      assert.equal(result.broadcastPayload.text, '/council');
      assert.equal(result.broadcastPayload.delay, 50);
      assert.ok(result.broadcastTimeout >= 15_000);
    });
  });

  // --- Session injection ---
  describe('Session injection', () => {
    it('every broadcast payload includes sessionId and projectLabel', () => {
      const tools = [
        ['browser_navigate', { url: 'https://x.com' }],
        ['browser_execute', { action: 'click', selector: '#x' }],
        ['browser_evaluate', { expression: '1+1' }],
        ['browser_screenshot', {}],
        ['browser_close_session', {}],
      ];

      for (const [name, args] of tools) {
        const result = routeToolCall(name, args);
        assert.ok(result.broadcastPayload.sessionId, `${name} missing sessionId`);
        assert.ok(result.broadcastPayload.projectLabel, `${name} missing projectLabel`);
      }
    });

    it('unknown tool throws descriptive error', () => {
      assert.throws(
        () => routeToolCall('browser_teleport', {}),
        /Unknown tool: browser_teleport/
      );
    });
  });

  // --- Additional routing tests ---
  describe('Additional routing', () => {
    it('browser_press_key routes as action_request with pressKey', () => {
      const result = routeToolCall('browser_press_key', { key: 'Enter' });
      assert.equal(result.broadcastType, 'action_request');
      assert.equal(result.broadcastPayload.action, 'pressKey');
      assert.equal(result.broadcastPayload.key, 'Enter');
    });

    it('browser_wait_for_stable timeout = actionTimeout + 5000', () => {
      const result = routeToolCall('browser_wait_for_stable', { selector: '#content', timeout: 60000 });
      assert.equal(result.broadcastType, 'action_request');
      assert.equal(result.broadcastPayload.action, 'waitForStable');
      assert.equal(result.broadcastTimeout, 65000);
    });

    it('browser_close_tabs validates tabIds array', () => {
      assert.throws(
        () => routeToolCall('browser_close_tabs', { tabIds: [] }),
        /tabIds must be a non-empty array/
      );
      assert.throws(
        () => routeToolCall('browser_close_tabs', { tabIds: [0] }),
        /tabIds\[0\] must be a positive number/
      );
    });
  });
});

describe('Screenshot Result Transformation', () => {
  it('strips data URL prefix from base64', () => {
    const result = transformScreenshotResult(
      { screenshot: 'data:image/png;base64,AAAA' },
      'png',
    );
    assert.equal(result._screenshotData.base64, 'AAAA');
    assert.equal(result._screenshotData.mimeType, 'image/png');
  });

  it('preserves raw base64 (no data URL prefix)', () => {
    const result = transformScreenshotResult({ screenshot: 'BBBB' }, 'png');
    assert.equal(result._screenshotData.base64, 'BBBB');
  });

  it('includes width/height/warning in meta when present', () => {
    const result = transformScreenshotResult(
      { screenshot: 'XX', width: 1920, height: 1080, warning: 'test warn' },
      'jpeg',
    );
    assert.equal(result._screenshotData.meta.width, 1920);
    assert.equal(result._screenshotData.meta.height, 1080);
    assert.equal(result._screenshotData.meta.warning, 'test warn');
    assert.equal(result._screenshotData.mimeType, 'image/jpeg');
  });
});
