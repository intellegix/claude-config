/**
 * Quick verification of error case + safety cap.
 * Usage: node test-verify.js
 */

import WebSocket from 'ws';
import { randomUUID } from 'node:crypto';

const WS_URL = 'ws://127.0.0.1:8765';

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
    ws.send(JSON.stringify({ type: 'relay_forward', requestId, payload: { type, payload }, timeout }));
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const ws = await connect();
  ws.send(JSON.stringify({ type: 'relay_init', payload: { pid: process.pid } }));
  await sleep(500);

  // Test 1: Error case — bad selector
  console.log('--- Test 1: Bad selector error ---');
  try {
    await relayRequest(ws, 'screenshot_element', { selector: '.nonexistent-element-xyz', format: 'png' });
    console.log('  FAIL: Should have thrown');
  } catch (err) {
    console.log(`  PASS: Error = "${err.message}"`);
  }

  await sleep(500);

  // Test 2: Safety cap — navigate to a very tall page and check dimensions
  console.log('\n--- Test 2: Safety cap (tall page) ---');
  try {
    await relayRequest(ws, 'navigate', { url: 'https://en.wikipedia.org/wiki/San_Diego' }, 20_000);
    await sleep(5000);
    const dims = await relayRequest(ws, 'action_request', { action: 'getPageDimensions' });
    const ratio = dims.scrollHeight / dims.viewportHeight;
    console.log(`  Page: ${dims.scrollHeight}px / ${dims.viewportHeight}px = ${ratio.toFixed(1)} viewports`);

    if (ratio > 30) {
      console.log('  Page exceeds 30 viewports — testing safety cap...');
      const result = await relayRequest(ws, 'screenshot_full_page', { format: 'jpeg', quality: 50 }, 120_000);
      if (result.warning) {
        console.log(`  PASS: Safety cap triggered — "${result.warning}"`);
      } else {
        console.log(`  INFO: Got full-page without warning (${result.width}x${result.height})`);
      }
    } else {
      console.log(`  INFO: Page is only ${ratio.toFixed(1)} viewports (< 30). Safety cap not triggered.`);
      console.log('  Testing full-page capture instead...');
      const result = await relayRequest(ws, 'screenshot_full_page', { format: 'jpeg', quality: 50 }, 120_000);
      if (result.success) {
        console.log(`  PASS: Full-page captured — ${result.width}x${result.height}`);
      }
    }
  } catch (err) {
    console.error(`  FAIL: ${err.message}`);
  }

  ws.close();
  console.log('\n=== Verification complete ===');
}

main().catch(console.error);
