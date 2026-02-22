/**
 * Claude Browser Bridge — Popup UI controller
 *
 * Displays connection status, health metrics, top tools, and session info.
 * Polls background service worker every 5 seconds while the popup is open.
 */

const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const clientIdEl = document.getElementById('clientId');
const metricsContent = document.getElementById('metricsContent');
const topToolsContent = document.getElementById('topToolsContent');
const sessionsContent = document.getElementById('sessionsContent');
const reconnectBtn = document.getElementById('reconnectBtn');

// ---------------------------------------------------------------------------
// Safe DOM helpers (no innerHTML — all content via textContent/createElement)
// ---------------------------------------------------------------------------

/** Create an element with optional className and textContent */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

/** Clear all children of a container */
function clear(container) {
  while (container.firstChild) container.removeChild(container.firstChild);
}

/** Build a metric item: label + value */
function metricItem(label, value, isError) {
  const div = el('div', 'metric-item');
  div.appendChild(el('span', 'label', label));
  div.appendChild(el('span', isError ? 'value error' : 'value', value));
  return div;
}

/** Build a tool row: name | calls | avg duration */
function toolRow(name, calls, avgMs) {
  const div = el('div', 'tool-row');
  div.appendChild(el('span', 'tool-name', name));
  div.appendChild(el('span', 'tool-calls', String(calls)));
  div.appendChild(el('span', 'tool-avg', fmtMs(avgMs)));
  return div;
}

/** Build a sessions row: label + value */
function sessionsRow(label, value) {
  const div = el('div', 'sessions-row');
  div.appendChild(el('span', 'label', label));
  div.appendChild(el('span', 'value', String(value)));
  return div;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/** Format milliseconds to human-readable duration */
function fmtMs(ms) {
  if (ms == null || isNaN(ms)) return '--';
  if (ms < 1000) return ms + 'ms';
  return (ms / 1000).toFixed(1) + 's';
}

/** Format error rate as percentage */
function fmtPct(errors, total) {
  if (!total) return '0%';
  return ((errors / total) * 100).toFixed(1) + '%';
}

// ---------------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------------

function updateStatus() {
  chrome.runtime.sendMessage({ type: 'getStatus' }, (response) => {
    if (chrome.runtime.lastError || !response) {
      statusDot.className = 'dot disconnected';
      statusText.textContent = 'Service worker inactive';
      clientIdEl.textContent = '';
      return;
    }

    if (response.connected) {
      statusDot.className = 'dot connected';
      statusText.textContent = 'Connected';
      clientIdEl.textContent = response.clientId
        ? `Client: ${response.clientId.slice(0, 8)}...`
        : '';
    } else {
      statusDot.className = 'dot disconnected';
      statusText.textContent = 'Disconnected';
      clientIdEl.textContent = '';
    }
  });
}

// ---------------------------------------------------------------------------
// Health & Metrics
// ---------------------------------------------------------------------------

function updateHealth() {
  chrome.runtime.sendMessage({ type: 'getHealth' }, (response) => {
    if (chrome.runtime.lastError) return;

    if (!response) {
      clear(metricsContent);
      metricsContent.appendChild(el('div', 'placeholder', 'Health endpoint unreachable'));
      clear(topToolsContent);
      topToolsContent.appendChild(el('div', 'placeholder', '--'));
      clear(sessionsContent);
      sessionsContent.appendChild(el('div', 'placeholder', '--'));
      return;
    }

    // Metrics section
    const m = response.metrics;
    if (m) {
      clear(metricsContent);
      metricsContent.appendChild(metricItem('Calls', String(m.totalCalls)));
      metricsContent.appendChild(metricItem(
        'Errors',
        m.totalErrors + ' (' + fmtPct(m.totalErrors, m.totalCalls) + ')',
        m.totalErrors > 0
      ));
      metricsContent.appendChild(metricItem('Avg', fmtMs(calcAvg(m))));
      metricsContent.appendChild(metricItem('P95', fmtMs(calcP95(m))));

      // Top tools section (top 3 by call count)
      const tools = m.perTool ? Object.entries(m.perTool) : [];
      tools.sort((a, b) => b[1].calls - a[1].calls);
      const top3 = tools.slice(0, 3);

      clear(topToolsContent);
      if (top3.length > 0) {
        for (const [name, t] of top3) {
          topToolsContent.appendChild(toolRow(name.replace('browser_', ''), t.calls, t.avgDurationMs));
        }
      } else {
        topToolsContent.appendChild(el('div', 'placeholder', 'No tool calls yet'));
      }
    } else {
      clear(metricsContent);
      metricsContent.appendChild(el('div', 'placeholder', 'No metrics available'));
      clear(topToolsContent);
      topToolsContent.appendChild(el('div', 'placeholder', '--'));
    }

    // Sessions section
    const b = response.bridge;
    clear(sessionsContent);
    if (b) {
      sessionsContent.appendChild(sessionsRow('Browsers', b.browserCount || 0));
      sessionsContent.appendChild(sessionsRow('Relays', b.relayCount || 0));
      if (b.relays && b.relays.length > 0) {
        for (const r of b.relays) {
          const detail = (r.sessionId || '--') + '... PID ' + (r.pid || '--') + ' (idle ' + (r.idleSeconds || 0) + 's)';
          sessionsContent.appendChild(el('div', 'relay-detail', detail));
        }
      }
    } else {
      sessionsContent.appendChild(el('div', 'placeholder', '--'));
    }
  });
}

/** Calculate weighted average duration across all tools */
function calcAvg(metrics) {
  if (!metrics.perTool) return null;
  let totalDur = 0, totalCalls = 0;
  for (const t of Object.values(metrics.perTool)) {
    totalDur += (t.avgDurationMs || 0) * t.calls;
    totalCalls += t.calls;
  }
  return totalCalls > 0 ? Math.round(totalDur / totalCalls) : null;
}

/** Get max p95 across all tools as an approximation */
function calcP95(metrics) {
  if (!metrics.perTool) return null;
  let maxP95 = 0;
  for (const t of Object.values(metrics.perTool)) {
    if (t.p95DurationMs > maxP95) maxP95 = t.p95DurationMs;
  }
  return maxP95 || null;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

reconnectBtn.addEventListener('click', () => {
  statusText.textContent = 'Reconnecting...';
  statusDot.className = 'dot disconnected';

  chrome.runtime.sendMessage({ type: 'reconnect' }, () => {
    setTimeout(() => {
      updateStatus();
      updateHealth();
    }, 2000);
  });
});

// ---------------------------------------------------------------------------
// Init & polling
// ---------------------------------------------------------------------------

updateStatus();
updateHealth();

const pollTimer = setInterval(() => {
  updateStatus();
  updateHealth();
}, 5000);

window.addEventListener('unload', () => {
  clearInterval(pollTimer);
});
