/**
 * Keepalive page — shows active Claude sessions and lets the user close Chrome.
 */

const sessionList = document.getElementById('sessions');
const closeBtn = document.getElementById('closeBtn');

function renderSessions(sessions) {
  sessionList.textContent = '';

  if (!sessions || sessions.length === 0) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = 'No active sessions';
    sessionList.appendChild(li);
    return;
  }

  for (const s of sessions) {
    const li = document.createElement('li');
    li.className = 'session-item';

    const dot = document.createElement('span');
    dot.className = 'session-dot';

    const label = document.createElement('span');
    label.className = 'session-label';
    label.textContent = s.label;

    const tabs = document.createElement('span');
    tabs.className = 'session-tabs';
    tabs.textContent = `${s.tabCount} tab${s.tabCount !== 1 ? 's' : ''}`;

    li.appendChild(dot);
    li.appendChild(label);
    li.appendChild(tabs);
    sessionList.appendChild(li);
  }
}

function refresh() {
  chrome.runtime.sendMessage({ type: 'getActiveSessions' }, (response) => {
    if (chrome.runtime.lastError) return;
    renderSessions(response?.sessions);
  });
}

// Initial load + periodic refresh
refresh();
setInterval(refresh, 5000);

// Close Chrome button — closing this window allows Chrome to exit
closeBtn.addEventListener('click', () => window.close());
