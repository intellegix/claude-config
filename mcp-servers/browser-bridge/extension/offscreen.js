/**
 * Offscreen document — Layer 3 keepalive.
 *
 * Keeps the service worker alive with periodic pings.
 * Screenshot operations now use CDP (Page.captureScreenshot)
 * so canvas crop/stitch is no longer needed here.
 */

setInterval(() => {
  chrome.runtime.sendMessage({ keepAlive: true }).catch(() => {
    // Service worker may not be active yet; ignore
  });
}, 20_000);
