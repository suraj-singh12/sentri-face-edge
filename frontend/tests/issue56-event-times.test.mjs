import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';

let server, utils, eventDateTime;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  utils = await server.ssrLoadModule('/src/utils.js');
  ({ eventDateTime } = await server.ssrLoadModule('/src/views/EventsView.jsx'));
});
after(async () => { await server?.close(); });

test('date-only Event shows Time unknown, never a clock time', () => {
  assert.equal(utils.formatEventWhen({ date: '2026-11-22', time_precision: 'unknown', start_time: null }), '2026-11-22 · Time unknown');
  assert.equal(utils.formatEventWhen({ date: '2026-11-22' }), '2026-11-22 · Time unknown');
  assert.equal(eventDateTime({ observed_at: '2026-11-22', time_precision: 'unknown' }), '2026-11-22 · Time unknown');
  assert.equal(utils.formatSeenDateTime({ date: '2026-11-22', time: '' }), '2026-11-22 · Time unknown');
});

test('date plus recorded time shows that time and range only', () => {
  const time = { date: '2026-11-22', time_precision: 'exact', start_time: '10:00', end_time: '11:00' };
  assert.equal(utils.formatEventWhen(time), '2026-11-22 · 10:00–11:00');
  assert.equal(utils.formatEventWhen({ ...time, end_time: null }), '2026-11-22 · 10:00');
  assert.equal(eventDateTime({ observed_at: '2026-11-22T10:00:00', time_precision: 'exact', start_time: '10:00', end_time: '11:00' }), '2026-11-22 · 10:00–11:00');
  assert.equal(utils.formatSeenDateTime({ date: '2026-11-22', time: '10:00', end_time: '11:00', time_precision: 'exact' }), '2026-11-22 · 10:00–11:00');
});

test('approximate time stays visibly approximate', () => {
  assert.equal(utils.formatEventWhen({ date: '2026-11-22', time_precision: 'approximate', start_time: '10:00' }), '2026-11-22 · About 10:00');
  assert.equal(utils.formatSeenDateTime({ date: '2026-11-22', time: '10:00', time_precision: 'approximate' }), '2026-11-22 · About 10:00');
});

test('missing Event date shows Date unknown and no time', () => {
  assert.equal(utils.formatEventWhen({ date: null, time_precision: 'unknown' }), 'Date unknown');
  assert.equal(utils.formatEventWhen(undefined), 'Date unknown');
  assert.equal(eventDateTime({ observed_at: null, time_precision: 'unknown' }), 'Date unknown');
  assert.equal(utils.formatSeenDateTime({ date: '' }), 'Date unknown');
  assert.equal(utils.formatEventDate(null), 'Date unknown');
  assert.equal(utils.formatOccurrence({ occurred_at: '2026-11-23T08:00:00', event_time: { date: null, time_precision: 'unknown' } }), 'Date unknown');
});

test('summary dates are date only and never shift a stored date', () => {
  assert.equal(utils.formatEventDate('2026-11-22'), '2026-11-22');
  assert.equal(utils.formatEventDate('2026-11-22T10:00:00'), '2026-11-22');
  assert.match(utils.formatEventDate('2026-11-22T04:30:00+00:00'), /^\d{4}-\d{2}-\d{2}$/);
});

test('World Event rows use the Event time, not a midnight clock', () => {
  const item = { occurred_at: '2026-11-22', event_time: { date: '2026-11-22', time_precision: 'unknown', start_time: null, end_time: null } };
  assert.equal(utils.formatOccurrence(item), '2026-11-22 · Time unknown');
});

test('no World or Person Graph surface formats an Event time with a generic clock', () => {
  for (const file of ['WorldEventDrilldownView', 'WorldPersonDrilldownView', 'WorldEvidenceDrilldownView', 'ClusterDrilldownView', 'WorldExploreView', 'WorldRelationshipProof', 'PersonGraphView']) {
    const source = readFileSync(new URL(`../src/views/${file}.jsx`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /formatDateTime\(\w+\.occurred_at\)|occurred_at\.slice\(0, 10\)|function formatGraphDate|toLocaleString\(\)/, file);
  }
  const preview = readFileSync(new URL('../src/components/WorldMediaPreview.jsx', import.meta.url), 'utf8');
  assert.match(preview, /formatOccurrence\(item\)/);
});
