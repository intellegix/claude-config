/**
 * Error codes and BridgeError for Claude Browser Bridge.
 *
 * Extension-originated codes propagate from background.js through the WS bridge.
 * Server-originated codes are added at the bridge/MCP layer.
 */

// Extension-originated codes (set in background.js error responses)
export const EXT_CODES = {
  CDP_ATTACH_FAILED: 'CDP_ATTACH_FAILED',
  FOCUS_FAILED: 'FOCUS_FAILED',
  NO_DIALOG: 'NO_DIALOG',
  MENU_NOT_FOUND: 'MENU_NOT_FOUND',
  EXPORT_NOT_FOUND: 'EXPORT_NOT_FOUND',
  ADD_TO_SPACE_NOT_FOUND: 'ADD_TO_SPACE_NOT_FOUND',
  MODAL_NOT_FOUND: 'MODAL_NOT_FOUND',
};

// Server-originated codes
export const SERVER_CODES = {
  TIMEOUT: 'TIMEOUT',
  NO_BROWSER: 'NO_BROWSER',
  RATE_LIMITED: 'RATE_LIMITED',
  UNKNOWN_TOOL: 'UNKNOWN_TOOL',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  BROWSER_BUSY: 'BROWSER_BUSY',
};

/**
 * Error subclass that carries a `.code` property through the stack.
 */
export class BridgeError extends Error {
  constructor(message, code) {
    super(message);
    this.name = 'BridgeError';
    this.code = code;
  }
}
