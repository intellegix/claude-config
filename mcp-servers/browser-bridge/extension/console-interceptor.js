/**
 * Console message interceptor — runs in the MAIN world so it patches the
 * page's actual console object (not the content script's isolated copy).
 * Messages are read back via CDP Runtime.evaluate in background.js.
 */
(function () {
  if (window.__claudeConsoleMessages) return;
  window.__claudeConsoleMessages = [];
  var MAX = 500;
  var methods = ['log', 'warn', 'error', 'info'];
  for (var i = 0; i < methods.length; i++) {
    (function (m) {
      var orig = console[m].bind(console);
      console[m] = function () {
        var args = Array.prototype.slice.call(arguments);
        window.__claudeConsoleMessages.push({
          level: m === 'warn' ? 'warning' : m,
          text: args
            .map(function (a) {
              try {
                return typeof a === 'object' ? JSON.stringify(a) : String(a);
              } catch (e) {
                return String(a);
              }
            })
            .join(' '),
          timestamp: Date.now(),
        });
        if (window.__claudeConsoleMessages.length > MAX)
          window.__claudeConsoleMessages.shift();
        return orig.apply(console, arguments);
      };
    })(methods[i]);
  }
})();
