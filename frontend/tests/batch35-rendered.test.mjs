import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MantineProvider } from '@mantine/core';
import { createServer } from 'vite';
import { recognitionReviewReady } from '../src/reviewState.js';
let server, RecognizeView, MachineProfilePanel, QueueView;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  ({ RecognizeView } = await server.ssrLoadModule('/src/views/RecognizeView.jsx'));
  ({ MachineProfilePanel } = await server.ssrLoadModule('/src/views/MachineProfilePanel.jsx'));
  ({ QueueView } = await server.ssrLoadModule('/src/views/QueueView.jsx'));
});
after(async () => { await server?.close(); });
const render = (component, props) => renderToStaticMarkup(React.createElement(MantineProvider, {}, React.createElement(component, props)));
const face = (index) => ({ index, box: { x:0, y:0, width:30, height:30 }, quality:{status:'good',score:.9}, matches:[], decision:'unknown' });
function recognitionProps(decisions, targetPerson = null) {
  const faces=[face(1),face(2)];
  return { canAdd:true, recognition:{faces, encounterMetadata:{eventOccasion:'Saved Event'}}, selectedFaceIndex:1,
    recognitionAcceptedFaces:Object.keys(decisions).filter((id) => decisions[id].startsWith('ACCEPT_')).map(Number),
    recognitionFaceDecisions:decisions, recognitionReviewReady:recognitionReviewReady(faces,decisions), targetPerson };
}
const namedButton = (html, text) => [...html.matchAll(/<button\b[^]*?<\/button>/g)].map((m)=>m[0]).find((m)=>m.includes(text));
test('targeted pre-plan Attach drafts expose Retry/Cancel instead of ordinary Encounter grouping', () => {
  const props={queueSessions:[],queueGroups:[],queueSessionId:'staged',queueReviewStats:{},
    encounterMedia:[{media_id:'media',media_path:'',face_count:1}]};
  const owned=render(QueueView,{...props,attachment:{observation_id:'existing'}});
  assert.match(owned,/Retry Attach Media/);
  assert.match(owned,/Cancel Attach Media/);
  assert.doesNotMatch(owned,/Confirm Encounter grouping/);
  // Queue thumbnails obtain the session meta tag in the browser. Supply only
  // that DOM lookup while rendering the ordinary branch on the server.
  const originalDocument=globalThis.document;
  let ordinary;
  try {
    globalThis.document={querySelector:()=>null};
    ordinary=render(QueueView,props);
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document=originalDocument;
  }
  assert.match(ordinary,/Confirm Encounter grouping/);
  assert.doesNotMatch(ordinary,/Retry Attach Media/);
});
test('rendered deferred badge and completion distinguish Skip from accepted/discarded decisions', () => {
  const deferred=render(RecognizeView,recognitionProps({1:'SKIP',2:'ACCEPT_EXISTING_PERSON'}));
  assert.match(deferred,/>Deferred</);assert.match(namedButton(deferred,'Complete Review'),/disabled=""/);
  const discarded=render(RecognizeView,recognitionProps({1:'EXCLUDE',2:'ACCEPT_NEW_PERSON'}));
  assert.match(discarded,/>Discarded</);assert.doesNotMatch(namedButton(discarded,'Complete Review'),/disabled=""/);
});
test('old cached Person enrollment cannot bypass shared Reference Only admission', () => {
  const person={person_id:'target',name:'Explicit target',biometric_status:'NO_FACE'};
  const initial=render(RecognizeView,recognitionProps({},person));
  assert.match(initial,/Use Recognition References/);
  assert.equal(namedButton(initial,'Add Face 01 to'),undefined);
  const staged=render(RecognizeView,recognitionProps({1:'ACCEPT_EXISTING_PERSON',2:'EXCLUDE'},person));
  assert.equal(namedButton(staged,'Finish enrollment'),undefined);
  assert.ok(namedButton(staged,'Cancel older enrollment draft'));
  assert.equal(namedButton(staged,'Complete Review'),undefined);
});
test('source real-model status remains distinct from packaged network-boundary verification', () => {
  const html=render(MachineProfilePanel,{profile:{runtime:'onnx',hardware:{},index:{},offline_enforcement:{source_runtime_admitted:true,real_model_running:true,outbound_socket_guard:true,os_network_enforced:false}}});
  assert.match(html,/Source ONNX running/);assert.match(html,/not verified/);
  assert.doesNotMatch(html,/real-model startup blocked/);
});

test('accepted recognition identity comes from operator resolution, never an unrelated proposal', () => {
  const candidate={person_id:'proposal-a',name:'Proposal A',is_known:true,similarity:.95,embedding_ids:['ea']};
  for (const [decision,person_id,new_person_name,name] of [
    ['ACCEPT_EXISTING_PERSON','proposal-a',null,'Proposal A'],
    ['ACCEPT_EXISTING_PERSON','selected-b',null,'Selected B'],
    ['ACCEPT_NEW_PERSON',null,'New C','New C'],
  ]) {
    for (const status of ['good','bad']) {
      const props=recognitionProps({1:decision,2:'SKIP'});
      props.recognition.faces[0]={...face(1),quality:{status,score:.3},decision:'known',matches:[candidate]};
      props.recognition.faceResolutions={1:{decision,person_id,new_person_name,recognition_detail:{name}}};
      const html=render(RecognizeView,props);
      const summary=html.match(/class="recognition-face-summary"[^]*?<\/button>/)?.[0];
      assert.match(summary,new RegExp(`>${name}<`));
      assert.match(summary,/>Accepted</);
      assert.match(html,/>Deferred</);
      if (name !== 'Proposal A') assert.doesNotMatch(summary,/>Proposal A</);
      if (new_person_name) assert.match(html,/New Person · pending completion/);
      else assert.match(html,new RegExp(`ID ${person_id}`));
    }
  }
});

test('no proposal and different per-face resolutions retain accepted identities on server resume', async () => {
  const {recognitionReviewState}=await import('../src/reviewState.js');
  const saved={faces:[
    {face_id:'face-1',decision:'ACCEPT_EXISTING_PERSON',person_id:'b',recognition_detail:{name:'Resolved B'}},
    {face_id:'face-2',decision:'ACCEPT_NEW_PERSON',new_person_name:'Resolved C'},
  ]};
  // JSON roundtrip models persisted state; server reread replaces it on resume.
  const state=recognitionReviewState(JSON.parse(JSON.stringify(saved)));
  const props=recognitionProps(state.faceDecisions);
  props.recognition={...props.recognition,...state};
  const html=render(RecognizeView,props);
  assert.match(html,/>Resolved B</);assert.match(html,/>Resolved C</);
  const summaries=[...html.matchAll(/class="recognition-face-summary"[^]*?<\/button>/g)].map((m)=>m[0]);
  assert.equal(summaries.filter((summary)=>summary.includes('>Accepted<')).length,2);
  assert.doesNotMatch(html,/No match found/);
});
