import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MantineProvider } from '@mantine/core';
import { createServer } from 'vite';
import { recognitionReviewReady } from '../src/reviewState.js';
let server, RecognizeView, MachineProfilePanel;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  ({ RecognizeView } = await server.ssrLoadModule('/src/views/RecognizeView.jsx'));
  ({ MachineProfilePanel } = await server.ssrLoadModule('/src/views/MachineProfilePanel.jsx'));
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
test('rendered deferred badge and completion distinguish Skip from accepted/discarded decisions', () => {
  const deferred=render(RecognizeView,recognitionProps({1:'SKIP',2:'ACCEPT_EXISTING_PERSON'}));
  assert.match(deferred,/>Deferred</);assert.match(namedButton(deferred,'Complete Review'),/disabled=""/);
  const discarded=render(RecognizeView,recognitionProps({1:'EXCLUDE',2:'ACCEPT_NEW_PERSON'}));
  assert.match(discarded,/>Discarded</);assert.doesNotMatch(namedButton(discarded,'Complete Review'),/disabled=""/);
});
test('explicit Person enrollment needs no recognition-proposal fields and staged enrollment can retry', () => {
  const person={person_id:'target',name:'Explicit target',biometric_status:'NO_FACE'};
  const initial=render(RecognizeView,recognitionProps({},person));
  assert.doesNotMatch(namedButton(initial,'Add Face 01 to'),/disabled=""/);
  const staged=render(RecognizeView,recognitionProps({1:'ACCEPT_EXISTING_PERSON',2:'EXCLUDE'},person));
  assert.doesNotMatch(namedButton(staged,'Finish enrollment'),/disabled=""/);
  assert.equal(namedButton(staged,'Complete Review'),undefined);
});
test('source real-model status remains distinct from packaged network-boundary verification', () => {
  const html=render(MachineProfilePanel,{profile:{runtime:'onnx',hardware:{},index:{},offline_enforcement:{source_runtime_admitted:true,real_model_running:true,outbound_socket_guard:true,os_network_enforced:false}}});
  assert.match(html,/Source ONNX running/);assert.match(html,/not verified/);
  assert.doesNotMatch(html,/real-model startup blocked/);
});
