import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('every request names its window and an unloading window releases it', () => {
  const client = source('hooks/useApiClient.js');
  assert.match(client, /"X-SentriFace-Window": WINDOW_ID/);
  assert.match(client, /keepalive: true[\s\S]*?action: "release"/);
  assert.match(client, /WINDOW_CODES = \["window_in_use", "window_replaced"\]/);
});

test('the gate blocks a second window and offers Use this window', () => {
  const gate = source('components/AuthGate.jsx');
  assert.match(gate, /SentriFace is open in another window/);
  assert.match(gate, /SentriFace is now being used in another window/);
  assert.match(gate, /Use this window/);
  assert.match(gate, /action: "claim"/);
  assert.match(gate, /action: "heartbeat"/);
  assert.match(gate, /addEventListener\("pagehide", release\)/);
});

test('an administrator-set password is replaced before the app opens, without re-entering it', () => {
  const gate = source('components/AuthGate.jsx');
  assert.match(gate, /status\.user\?\.must_change_password/);
  assert.match(gate, /Choose a new password/);
  assert.match(gate, /An administrator set this password\. Choose your own before you continue\./);
  assert.match(gate, /\/api\/auth\/set-password", \{ new_password: newPassword \}/);
  assert.doesNotMatch(gate, /current_password: password/);
  assert.match(gate, /Save and continue/);
});

test('accounts show who must change their password', () => {
  const panel = source('views/AccountsPanel.jsx');
  assert.match(panel, /Must change password/);
  assert.match(panel, /They must choose a new password when they first sign in\./);
});
