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
  assert.match(html,/1 deferred/);
  assert.match(html,/Review deferred now \(1\)/);
});
