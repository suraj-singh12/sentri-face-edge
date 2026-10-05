import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MantineProvider } from '@mantine/core';
import { createServer } from 'vite';
let server, References;
before(async()=>{server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});References=(await server.ssrLoadModule('/src/views/RecognitionReferences.jsx')).RecognitionReferences;});
after(async()=>server?.close());
function render(props={}) {
  const previous=globalThis.document;
  globalThis.document={querySelector:()=>null};
  try {return renderToStaticMarkup(React.createElement(MantineProvider,{env:'test'},React.createElement(References,{opened:true,onClose:()=>{},person:{person_id:'alice',name:'Alice'},actions:{},canMutate:true,...props})));}
  finally {if(previous===undefined)delete globalThis.document;else globalThis.document=previous;}
}
test('shared reference bootstrap requires cropped-image instruction and explicit context declaration',()=>{
 const html=render({startAdding:true});
 assert.match(html,/No reliable Encounter context is available/);
 assert.match(html,/cropped image containing only this person/);
 assert.match(html,/Do not upload group or scene photographs/);
 assert.match(html,/no Encounter, sighting, recurrence, relationship or Event history/);
 assert.match(html,/Select cropped Reference image/);
 assert.match(html,/disabled=""/);
});
test('reference management exposes source counts, retirement and derived ownership warning',()=>{
 const html=render({data:{active_count:1,references:[{reference_id:'r1',active:true,recognition_state:'GOOD',recognition_conflict:true},{reference_id:'r2',active:false,recognition_state:'PROOF_ONLY'}]}});
 assert.match(html,/1 \/ 4 active sources/);assert.match(html,/Retired References/);
 assert.match(html,/>Retire</);assert.match(html,/>Restore Reference</);
 assert.match(html,/shares a biometric sample/);assert.match(html,/excluded from recognition/);
});
test('read-only and cap constrain the same reference controls',()=>{
 for(const props of [{canMutate:false},{data:{active_count:4}}]) {
  const html=render(props);
  const button=html.match(/<button[^]*?Add Reference Only<\/span>[^]*?<\/button>/)?.[0];
  assert.ok(button);assert.match(button,/disabled=""/);
 }
});
