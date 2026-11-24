import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../src/', import.meta.url));
const sources = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const path = join(dir, entry.name);
  if (entry.isDirectory()) return sources(path);
  return /\.(jsx?|mjs)$/.test(entry.name) && !entry.name.includes('.test.') ? [path] : [];
});
// Comments may use the internal domain name; every other word in source can reach the screen.
const codeLines = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '').split('\n').filter((line) => !line.trim().startsWith('//'));

test('screen wording says Event and Skip for now, never Encounter or Defer', () => {
  const offenders = sources(root).flatMap((file) => codeLines(readFileSync(file, 'utf8'))
    .filter((line) => /\bEncounters?\b|\b[Dd]efer(s|red|ring)?\b/.test(line))
    .map((line) => `${file.slice(root.length)}: ${line.trim().slice(0, 120)}`));
  assert.deepEqual(offenders, []);
});

test('postponed reviews and backup restore use the approved labels', () => {
  const recognize = readFileSync(join(root, 'views/RecognizeView.jsx'), 'utf8');
  assert.match(recognize, /Skip for now\s*<Text[^>]*>Come back to this face later</);
  assert.match(recognize, /"SKIP" \? "Skipped"/);
  const queue = readFileSync(join(root, 'views/QueueView.jsx'), 'utf8');
  assert.match(queue, /Review skipped now \(/);
  const debug = readFileSync(join(root, 'views/DebugView.jsx'), 'utf8');
  assert.match(debug, /label=\{backup\.restorable \? "Restore from Backup…"/);
  assert.match(debug, /aria-label=\{`Restore from Backup… \$\{formatDateTime\(backup\.created_at\)\}`\}/);
});
