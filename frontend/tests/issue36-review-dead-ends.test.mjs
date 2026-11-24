import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MantineProvider } from '@mantine/core';
import { createServer } from 'vite';
import { recognitionReviewReady } from '../src/reviewState.js';
let server, RecognizeView, QueueView;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  ({ RecognizeView } = await server.ssrLoadModule('/src/views/RecognizeView.jsx'));
  ({ QueueView } = await server.ssrLoadModule('/src/views/QueueView.jsx'));
});
after(async () => { await server?.close(); });
const render = (component, props) => renderToStaticMarkup(React.createElement(MantineProvider, {}, React.createElement(component, props)));
const face = (index) => ({ index, box: { x:0, y:0, width:30, height:30 }, quality:{status:'good',score:.9}, matches:[], decision:'unknown' });
function recognitionProps(decisions) {
  const faces=[face(1),face(2)];
  return { canAdd:true, recognition:{faces, encounterMetadata:{eventOccasion:'Saved Event'}}, selectedFaceIndex:1,
    recognitionAcceptedFaces:Object.keys(decisions).filter((id) => decisions[id].startsWith('ACCEPT_')).map(Number),
    recognitionFaceDecisions:decisions, recognitionReviewReady:recognitionReviewReady(faces,decisions) };
}

test('disabled Complete Review explains what is missing instead of failing silently', () => {
  const skipped=render(RecognizeView,recognitionProps({1:'SKIP',2:'ACCEPT_NEW_PERSON'}));
  assert.match(skipped,/1 face still needs Accept or Discard/);
  const discarded=render(RecognizeView,recognitionProps({1:'EXCLUDE',2:'EXCLUDE'}));
  assert.match(discarded,/Every face is discarded, so there is nothing to save\. Use Clear/);
  const ready=render(RecognizeView,recognitionProps({1:'EXCLUDE',2:'ACCEPT_NEW_PERSON'}));
  assert.doesNotMatch(ready,/recognize-complete-hint/);
});

test('Event details can be cancelled from Check a photo and Review photos', () => {
  for (const file of ['../src/views/RecognizeView.jsx','../src/views/QueueView.jsx']) {
    const source=readFileSync(new URL(file, import.meta.url),'utf8');
    assert.match(source,/<EncounterDetailsModal opened=\{Boolean\([^\n]*onClose=\{on(Clear|Back)\} \/>/);
  }
});

test('deferred Encounter groups stay recoverable while other groups are pending', () => {
  const groups=[{group_id:'pending',session_id:'s',status:'pending',faces:[{init_face_id:'a',image_path:''}],matches:[]},
    {group_id:'deferred',session_id:'s',status:'skipped',faces:[{init_face_id:'b',image_path:''}],matches:[]}];
  const activeEncounter={review_id:'r',status:'IN_PROGRESS',phase:'IDENTITIES',sequence_number:0,identity_resolved:0,identity_total:2,
    event_details_complete:true,faces:[{face_id:'a'},{face_id:'b'}]};
  const originalDocument=globalThis.document;
  let html;
  try {
    globalThis.document={querySelector:()=>null};
    html=render(QueueView,{queueSessions:[],queueGroups:groups,visibleQueueGroups:groups,queueSessionId:'s',queueReviewStats:{},
      encounterReviews:[activeEncounter],activeEncounter,encounterMedia:[{media_id:'m',media_path:'',face_count:2}]});
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document=originalDocument;
  }
  assert.match(html,/1 skipped/);
  assert.match(html,/Review skipped now \(1\)/);
});

test('safety-copy folder hints match the platform and same-drive copies are flagged', async () => {
  const { backupFolderPlaceholder, SameDriveWarning } = await server.ssrLoadModule('/src/components/RecoveryGate.jsx');
  assert.equal(backupFolderPlaceholder('Mozilla/5.0 (Windows NT 10.0)'), 'E:\\SentriFace Backup');
  assert.match(backupFolderPlaceholder('Mozilla/5.0 (Macintosh; Intel Mac OS X)'), /^\/Volumes\//);
  assert.match(backupFolderPlaceholder('Mozilla/5.0 (X11; Linux x86_64)'), /^\/media\//);
  assert.match(render(SameDriveWarning,{}),/same drive as your SentriFace data/);
});

test('counts pluralize and unknown times read as unknown', async () => {
  const { plural, formatSeenDateTime } = await server.ssrLoadModule('/src/utils.js');
  assert.equal(plural(1, 'participant'), '1 participant');
  assert.equal(plural(2, 'participant'), '2 participants');
  assert.equal(formatSeenDateTime({ date: '2026-11-21' }), '2026-11-21 · Time unknown');
  assert.equal(formatSeenDateTime({ date: '2026-11-21', time: '10:30' }), '2026-11-21 · 10:30');
});

test('Review photos confirmation no longer requires a typed Added by', () => {
  const source = readFileSync(new URL('../src/hooks/useQueueController.js', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /Required: Added by/);
  assert.doesNotMatch(source, /\["addedBy", "Added by"\]/);
});

test('Review deferred now reloads Encounter-filtered groups so decided faces stay out of the queue', () => {
  const source=readFileSync(new URL('../src/hooks/useQueueController.js', import.meta.url),'utf8');
  const resume=source.slice(source.indexOf('const queueResumeSkipped'), source.indexOf('const queueRejectSuggestedMatch'));
  assert.match(resume,/if \(activeEncounter\) \{\s*selectedGroupIdRef\.current = "";\s*setQueueSelectedGroupId\(""\);\s*await loadQueueGroups\(queueSessionId\);\s*\} else setQueueGroups\(payload\.groups\);/);
});

test('Review photos session card does not show the raw session ID', () => {
  const source=readFileSync(new URL('../src/views/QueueView.jsx', import.meta.url),'utf8');
  assert.doesNotMatch(source,/>\{sessionId\}</);
  assert.match(source,/aria-label="Copy session ID"/);
});
