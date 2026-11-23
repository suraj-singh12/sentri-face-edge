import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('session-ended responses explain themselves instead of showing a generic error', () => {
  const client = source('hooks/useApiClient.js');
  assert.match(client, /SESSION_ENDED_CODES = \["authentication_required", "setup_required", "page_session_expired"\]/);
  assert.match(client, /new CustomEvent\("sentriface-reload-required"\)/);
  assert.match(client, /new CustomEvent\("sentriface-auth-required", \{ detail: payload\.session_ended \|\| null \}\)/);
  assert.match(client, /if \(SESSION_ENDED_CODES\.includes\(error\.code\)\) \{[\s\S]*?error\.notified = true;[\s\S]*?throw error;/);
  assert.match(source('hooks/useAppData.js'), /if \(!SESSION_ENDED_CODES\.includes\(error\?\.code\)\) \{\s*setConnectionError/);
});

test('sign-in shows why the session ended and a restart offers Reload', () => {
  const gate = source('components/AuthGate.jsx');
  assert.match(gate, /status\?\.session_ended \?[\s\S]*?title="Your session ended"[\s\S]*?status\.session_ended\.message/);
  assert.match(gate, /SentriFace was restarted/);
  assert.match(gate, /window\.location\.reload\(\)/);
  assert.match(gate, /addEventListener\("focus", recheck\)/);
  assert.match(gate, /JSON\.stringify\(current\) === JSON\.stringify\(next\) \? current : next/);
});
