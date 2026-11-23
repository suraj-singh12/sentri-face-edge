import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('encounter corrections report success and failure with toasts', () => {
  const controller = source('hooks/useSentriFaceController.js');
  assert.match(controller, /const subject = changes\.event_details \? "Encounter details" : changes\.participant_correction \? "Participants" : "Relations";/);
  assert.match(controller, /apiPost\("\/api\/encounter-correct", [^\n]*\{ silent: true \}\)/);
  assert.match(controller, /showToast\(error\?\.message \|\| "The correction was not saved\.", "red", \{ title: `\$\{subject\} not corrected` \}\)/);
  assert.match(controller, /showToast\("The correction was saved[^"]*", "teal", \{ title: `\$\{subject\} corrected` \}\)/);
  assert.match(controller, /title: "No changes to save"/);
  assert.match(source('SentriFaceApp.jsx'), /onNoChanges=\{actions\.notifyNoCorrectionChanges\}/);
});

test('unchanged corrections are not sent to the server', () => {
  const events = source('views/EventsView.jsx');
  assert.match(events, /if \(sameEventDetails\(detail\.event_details, eventDetails\)\) \{\s*onNoChanges\?\.\(\);\s*setMode\(null\);\s*return;/);
  const modal = source('components/EncounterManagementModal.jsx');
  assert.match(modal, /mode === "relations" && pairs\.every\(\(pair\) => existing\[pair\.key\] === valueFor\(pair\)\)\) \{\s*onNoChanges\?\.\(\);\s*onClose\(\);\s*return;/);
});
