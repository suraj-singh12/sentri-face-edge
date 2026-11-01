import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

test('CI events retain parent assertions and distinguish skipped tests', () => {
  const directory = mkdtempSync(join(tmpdir(), 'sentriface-ci-control-'));
  try {
    const fixture = join(directory, 'control.mjs');
    writeFileSync(fixture, `import test from 'node:test';
import assert from 'node:assert/strict';
test('controlled parent', async t => {
  await t.test('passing child', () => assert.equal(1, 1));
  assert.equal(1, 2);
});
test('skipped control', {skip: 'fixture disabled'}, () => {});
`);
    const environment = { ...process.env };
    delete environment.NODE_TEST_CONTEXT;
    const reporter = new URL('../../scripts/node_ci_reporter.mjs', import.meta.url).href;
    const run = spawnSync(process.execPath, ['--test', '--test-reporter=' + reporter, fixture], {
      encoding: 'utf8', env: environment,
    });
    assert.equal(run.status, 1, run.stderr);
    const rows = run.stdout.trim().split('\n').map(line => JSON.parse(line));
    const parent = rows.find(row => row.name === 'controlled parent');
    assert.equal(parent.event, 'test:fail');
    assert.equal(parent.expected, 2);
    assert.equal(parent.actual, 1);
    assert.equal(rows.find(row => row.name === 'passing child').event, 'test:pass');
    assert.equal(rows.find(row => row.name === 'skipped control').skipped, true);
  } finally {
    rmSync(directory, {recursive: true, force: true});
  }
});
