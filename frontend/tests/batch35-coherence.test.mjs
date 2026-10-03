import test from 'node:test';
import assert from 'node:assert/strict';
import { acceptedDecision, finalDecision, recognitionReviewReady, actionableQueueGroups, reconcileQueueSelection } from '../src/reviewState.js';

test('deferred decisions never count as accepted or final', () => {
  for (const decision of [undefined, null, 'SKIP']) {
    assert.equal(acceptedDecision(decision), false); assert.equal(finalDecision(decision), false);
    assert.equal(recognitionReviewReady([{index:1},{index:2}], {1:'ACCEPT_EXISTING_PERSON',2:decision}), false);
  }
  assert.equal(finalDecision('EXCLUDE'), true); assert.equal(acceptedDecision('EXCLUDE'), false);
  assert.equal(recognitionReviewReady([{index:1},{index:2}], {1:'ACCEPT_NEW_PERSON',2:'EXCLUDE'}), true);
  assert.equal(recognitionReviewReady([{index:1}], {1:'EXCLUDE'}), false);
});
test('queue progress counts actionable faces, independent of uploaded/finalized media', () => {
  const groups=[{group_id:'g',faces:[{source_image:'old.jpg'},{source_image:'new.jpg'}]}];
  const media=[{media_path:'old.jpg',finalized_encounter:{observation_id:'o'}},{media_path:'new.jpg'}];
  assert.equal(actionableQueueGroups(groups,media,false)[0].faces.length,1);
  assert.equal(actionableQueueGroups(groups,[{media_path:'old.jpg',excluded:true}],false).length,0);
  assert.equal(actionableQueueGroups(groups,media,true)[0].faces.length,2);
});
test('a background refresh reconciles the live selection rather than its request-time snapshot', () => {
  const groups=[{group_id:'new',faces:[{init_face_id:'live'}]}];
  const result=reconcileQueueSelection(groups,'new',['live','removed']);
  assert.equal(result.group.group_id,'new'); assert.deepEqual(result.faces,['live']);
  assert.equal(reconcileQueueSelection(groups,'gone',[]).group,null);
});
