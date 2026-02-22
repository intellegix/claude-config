/**
 * Test full-page screenshot via WebSocket relay protocol.
 *
 * Uses CDP (Page.captureScreenshot) in background.js — no Chrome focus
 * requirement, no scroll-stitch loop, no offscreen canvas.
 *
 * Usage: node test-fullpage.js
 */

import WebSocket from 'ws';
import { randomUUID } from 'node:crypto';
import { writeFileSync } from 'node:fs';

const WS_URL = 'ws://127.0.0.1:8765';
const SAVE_DIR = process.env.USERPROFILE
  ? `${process.env.USERPROFILE}\\Desktop`
  : `${process.env.HOME}/Desktop`;

function connect() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(WS_URL, { maxPayload: 50_000_000 });
    ws.on('open', () => resolve(ws));
    ws.on('error', reject);
  });
}

function relayRequest(ws, type, payload, timeout = 30_000) {
  return new Promise((resolve, reject) => {
    const requestId = randomUUID();
    const timer = setTimeout(() => {
      ws.off('message', handler);
      reject(new Error(`Timeout after ${timeout}ms`));
    }, timeout);

    const handler = (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.requestId === requestId) {
          clearTimeout(timer);
          ws.off('message', handler);
          if (msg.error) reject(new Error(msg.error));
          else resolve(msg.result);
        }
      } catch {}
    };

    ws.on('message', handler);
    ws.send(JSON.stringify({
      type: 'relay_forward',
      requestId,
      payload: { type, payload },
      timeout,
    }));
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function saveScreenshot(result, filename) {
  const base64 = result.screenshot.replace(/^data:image\/\w+;base64,/, '');
  const buf = Buffer.from(base64, 'base64');
  const path = `${SAVE_DIR}\\${filename}`;
  writeFileSync(path, buf);
  console.log(`  Saved: ${path}`);
  console.log(`  Size: ${Math.round(buf.length / 1024)}KB`);
  if (result.width) console.log(`  Dimensions: ${result.width} x ${result.height}`);
  if (result.warning) console.log(`  WARNING: ${result.warning}`);
}

async function main() {
  console.log('Connecting to WebSocket server...');
  const ws = await connect();
  console.log('Connected.');

  ws.send(JSON.stringify({ type: 'relay_init', payload: { pid: process.pid } }));
  await sleep(500);
  console.log('Registered as relay client.\n');

  // Navigate to a long Wikipedia page
  console.log('--- Step 0: Navigate ---');
  try {
    const nav = await relayRequest(ws, 'navigate', {
      url: 'https://en.wikipedia.org/wiki/WebSocket',
    }, 20_000);
    console.log('Navigate:', nav.success ? 'OK' : JSON.stringify(nav));
  } catch (err) {
    console.error('Navigate error:', err.message);
  }

  console.log('Waiting 5s for page to load...');
  await sleep(5000);

  // Page dimensions
  console.log('\n--- Step 1: Page dimensions ---');
  try {
    const dims = await relayRequest(ws, 'action_request', { action: 'getPageDimensions' });
    const strips = Math.ceil(dims.scrollHeight / dims.viewportHeight);
    console.log(`  scrollHeight: ${dims.scrollHeight}px`);
    console.log(`  viewportHeight: ${dims.viewportHeight}px`);
    console.log(`  viewportWidth: ${dims.viewportWidth}px`);
    console.log(`  DPR: ${dims.dpr}`);
    console.log(`  Equivalent strips: ${strips} (not needed with CDP)`);
  } catch (err) {
    console.error('Dimensions error:', err.message);
  }

  // Viewport screenshot (CDP, no focus needed)
  console.log('\n--- Step 2: Viewport screenshot ---');
  const vpStart = Date.now();
  try {
    const vpResult = await relayRequest(ws, 'screenshot', { format: 'jpeg', quality: 80 });
    console.log(`  Time: ${((Date.now() - vpStart) / 1000).toFixed(1)}s`);
    if (vpResult.success) saveScreenshot(vpResult, 'test-viewport.jpg');
  } catch (err) {
    console.error('  Viewport error:', err.message);
  }

  await sleep(500);

  // Full-page screenshot (CDP captureBeyondViewport — single call, no stitching)
  console.log('\n--- Step 3: FULL-PAGE screenshot (CDP) ---');
  const fpStart = Date.now();
  try {
    const fpResult = await relayRequest(ws, 'screenshot_full_page', { format: 'jpeg', quality: 80 }, 120_000);
    console.log(`  Time: ${((Date.now() - fpStart) / 1000).toFixed(1)}s`);
    if (fpResult.success) saveScreenshot(fpResult, 'test-fullpage.jpg');
  } catch (err) {
    console.error(`  Full-page error (${((Date.now() - fpStart) / 1000).toFixed(1)}s):`, err.message);
  }

  await sleep(500);

  // Element screenshot (CDP clip — no offscreen crop needed)
  console.log('\n--- Step 4: Element screenshot (h1) ---');
  const elStart = Date.now();
  try {
    const elResult = await relayRequest(ws, 'screenshot_element', {
      format: 'png',
      selector: 'h1',
    }, 30_000);
    console.log(`  Time: ${((Date.now() - elStart) / 1000).toFixed(1)}s`);
    if (elResult.success) saveScreenshot(elResult, 'test-element.png');
  } catch (err) {
    console.error('  Element error:', err.message);
  }

  await sleep(500);

  // Element screenshot of something below the fold (tests captureBeyondViewport)
  console.log('\n--- Step 5: Element screenshot (below fold — #References or #See_also) ---');
  const belowStart = Date.now();
  try {
    const belowResult = await relayRequest(ws, 'screenshot_element', {
      format: 'png',
      selector: '#References, #See_also, #External_links',
    }, 30_000);
    console.log(`  Time: ${((Date.now() - belowStart) / 1000).toFixed(1)}s`);
    if (belowResult.success) saveScreenshot(belowResult, 'test-below-fold.png');
  } catch (err) {
    console.error('  Below-fold element error:', err.message);
  }

  ws.close();
  console.log('\n=== All tests complete ===');
}

main().catch(console.error);
