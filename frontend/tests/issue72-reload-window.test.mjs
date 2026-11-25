import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('a reloaded tab names the window it replaces, read once and removed', () => {
  const client = source('hooks/useApiClient.js');
  const read = client.match(/function readReloadedFrom\(\) \{[\s\S]*?\n\}/)[0];
  assert.match(read, /sessionStorage\.getItem\(RELOADED_FROM_KEY\)/);
  assert.match(read, /sessionStorage\.removeItem\(RELOADED_FROM_KEY\)/);
  assert.match(client, /export const RELOADED_FROM_WINDOW_ID = readReloadedFrom\(\);/);
  // Written in exactly one place, which only the pagehide handler calls.
  assert.equal(client.match(/sessionStorage\.setItem/g).length, 1);
  assert.match(client, /export function rememberWindowForReload\(\) \{\s*try \{ window\.sessionStorage\.setItem\(RELOADED_FROM_KEY, WINDOW_ID\)/);
});

test('only the active window remembers itself, and only while it unloads', () => {
  const gate = source('components/AuthGate.jsx');
  assert.equal(gate.match(/rememberWindowForReload\(\)/g).length, 1);
  assert.match(gate, /const release = \(\) => \{\s*if \(!windowActive\.current\) return;\s*rememberWindowForReload\(\);\s*releaseWindow\(\);/);
  assert.match(gate, /addEventListener\("pagehide", release\)/);
  assert.match(gate, /"X-SentriFace-Reloaded-From": RELOADED_FROM_WINDOW_ID/);
});

test('the first load re-checks at about 1 s and 3 s behind the loading screen', () => {
  const gate = source('components/AuthGate.jsx');
  assert.match(gate, /for \(const delay of \[0, 1000, 2000\]\)/);
  assert.match(gate, /if \(!\(next\?\.authenticated && next\.window === "in_use"\)\) break;/);
  assert.match(gate, /Opening the local vault\.\.\./);
  // No repeated re-check on the blocked screen; the heartbeat stays as it was.
  assert.doesNotMatch(gate, /5000|5_000/);
  assert.match(gate, /\(status\?\.window_heartbeat_seconds \|\| 15\) \* 1000/);
});
