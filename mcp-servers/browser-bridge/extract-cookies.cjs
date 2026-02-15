// Extract all cookies (including httpOnly) via extension's get_all_cookies handler
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');

const ws = new WebSocket('ws://127.0.0.1:8765');
const rid = 'cookie-extract-' + Date.now();

ws.on('open', () => {
  console.log('Connected, requesting cookies...');
  ws.send(JSON.stringify({
    type: 'get_all_cookies',
    requestId: rid,
    payload: { domain: '.perplexity.ai' }
  }));
});

ws.on('message', (data) => {
  const msg = JSON.parse(data.toString());
  if (msg.type === 'connection_init') {
    console.log('Handshake received, clientId:', msg.clientId);
    return;
  }
  if (msg.requestId === rid) {
    const cookies = msg.result?.cookies || [];
    console.log(`Got ${cookies.length} cookies`);

    for (const c of cookies) {
      console.log(`  ${c.name}: httpOnly=${c.httpOnly}, secure=${c.secure}`);
    }

    // Convert to Playwright format
    const playwrightCookies = cookies.map(c => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      secure: c.secure,
      httpOnly: c.httpOnly,
      sameSite: c.sameSite === 'unspecified' ? 'Lax' : c.sameSite,
      expires: c.expirationDate || -1,
    }));

    const outPath = path.join(require('os').homedir(), '.claude', 'config', 'playwright-session.json');
    fs.writeFileSync(outPath, JSON.stringify(playwrightCookies, null, 2));
    console.log(`Saved ${playwrightCookies.length} cookies to ${outPath}`);

    ws.close();
  }
});

setTimeout(() => { console.log('Timeout - reload extension in chrome://extensions first'); ws.close(); process.exit(1); }, 10000);
