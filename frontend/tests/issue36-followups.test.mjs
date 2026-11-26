import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';
import { backupReminderDue, eventContextLabel, requiredFieldErrors } from '../src/utils.js';

let server, locationOptions, normalizeLocation, encounterDetailsErrors, followupErrors;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  ({ locationOptions, normalizeLocation } = await server.ssrLoadModule('/src/components/SavedLocationInput.jsx'));
  ({ encounterDetailsErrors } = await server.ssrLoadModule('/src/components/EncounterDetailsModal.jsx'));
  ({ followupErrors } = await server.ssrLoadModule('/src/components/RecognitionFollowupForm.jsx'));
});
after(async () => { await server?.close(); });
const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('location suggestions start at three letters and offer create only when nothing matches', () => {
  const loaded = { loaded: true };
  assert.deepEqual(locationOptions('pu', ['Pune'], loaded), ['Pune']);
  assert.deepEqual(locationOptions('pun', ['Pune', 'Pune HQ'], loaded), ['Pune', 'Pune HQ']);
  assert.deepEqual(locationOptions('Pune Office', [], loaded), ['Pune Office']);
  assert.deepEqual(locationOptions('Pune Office', [], { loaded: true, loading: true }), []);
  assert.deepEqual(locationOptions('Pune Office', [], {}), []);
  assert.equal(normalizeLocation('  Pune   HQ '), 'Pune HQ');
  assert.match(source('components/SavedLocationInput.jsx'), /Create “\{option\.value\}”/);
  assert.match(source('views/PeopleView.jsx'), /<SavedLocationInput[\s\S]*label="Place Seen"/);
  assert.match(source('views/PeopleView.jsx'), /import \{ SavedLocationInput \} from "\.\.\/components\/SavedLocationInput\.jsx";/);
});

test('required forms report missing fields inline instead of browser bubbles', () => {
  assert.deepEqual(requiredFieldErrors({ name: ' ', rank: 'Capt' }, [['name', 'Name'], ['rank', 'Rank']]), { name: 'Name is required' });
  assert.deepEqual(Object.keys(encounterDetailsErrors({ timePrecision: 'exact' })), ['eventOccasion', 'date', 'time', 'endTime', 'placeSeen']);
  assert.deepEqual(Object.keys(encounterDetailsErrors({ timePrecision: 'unknown' })), ['eventOccasion', 'date', 'placeSeen']);
  assert.deepEqual(encounterDetailsErrors({}, true), {});
  assert.deepEqual(Object.keys(followupErrors({ action: 'new' })), ['rank', 'name', 'country', 'importance', 'individualCount']);
  assert.deepEqual(Object.keys(followupErrors({ action: 'existing', individualCount: '2' })), []);
  assert.deepEqual(Object.keys(followupErrors({ action: 'existing', individualCount: '0' })), []);
  assert.deepEqual(Object.keys(followupErrors({ action: 'existing', individualCount: 0 })), []);
  for (const file of ['components/AuthGate.jsx', 'components/EncounterDetailsModal.jsx', 'components/RecognitionFollowupForm.jsx']) {
    assert.match(source(file), /noValidate/, file);
  }
});

test('raw identifiers and typed editor names are not shown to operators', () => {
  const people = source('views/PeopleView.jsx');
  assert.doesNotMatch(people, /ID: \{payload\.person\.person_id\}/);
  assert.doesNotMatch(people, /ID \{String\(person\.person_id/);
  assert.doesNotMatch(people, /label="Edited by"/);
  assert.doesNotMatch(source('hooks/usePeopleController.js'), /editor_name/);
  assert.match(source('views/QueueView.jsx'), /aria-label=\{`Select face \$\{index \+ 1\}`\}/);
  assert.doesNotMatch(source('components/Shared.jsx'), /Group ID/);
});

test('removal actions say what they remove', () => {
  const queue = source('views/QueueView.jsx');
  assert.match(queue, /Removes only the selected faces from this group/);
  assert.match(queue, /No faces or people are deleted/);
  assert.match(queue, /The photo file is not deleted/);
  assert.match(queue, /The 1 pending face in this group is removed\. Saved people stay\./);
  assert.doesNotMatch(queue, /removes all \{groupPendingDiscard/);
});

test('context labels use one Unknown spelling', () => {
  assert.equal(eventContextLabel('unknown'), 'Unknown');
  assert.equal(eventContextLabel(undefined), 'Unknown');
  assert.equal(eventContextLabel('public'), 'Public / group');
});

test('backup reminder appears only when data changed after the latest backup', () => {
  const backups = [{ created_at: '2026-11-21T21:00:00+05:30' }, { created_at: '2026-11-20T21:00:00+05:30' }];
  assert.equal(backupReminderDue('2026-11-21T16:00:00+00:00', backups), true);
  assert.equal(backupReminderDue('2026-11-21T15:00:00+00:00', backups), false);
  assert.equal(backupReminderDue('2026-11-21T15:00:00+00:00', []), true);
  assert.equal(backupReminderDue('', backups), false);
  assert.equal(backupReminderDue('2026-11-21T15:00:00+00:00', [{ created_at: '2026-11-21T21:00:00+05:30', complete: false }]), true);
  assert.equal(backupReminderDue('2026-11-21T15:00:00+00:00', [{ created_at: '2026-11-21T21:00:00+05:30', restorable: false }]), true);
  assert.match(source('SentriFaceApp.jsx'), /You have changes since your last backup/);
});

test("Activity Last Activity uses the formatted change date, not the raw timestamp", () => {
  const source = readFileSync(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  assert.match(source, /label="Last Activity" value=\{compactChangeDate\(activeHistory\?\.createdAt\)\}/);
});
