import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { recognitionReviewReady } from '../src/reviewState.js';

// Frontend half of the rule in tests/fixtures/review_completion_contract.json; the backend half is tests/test_review_completion_contract.py.
const contract = JSON.parse(readFileSync(new URL('../../tests/fixtures/review_completion_contract.json', import.meta.url), 'utf8'));

test('Complete Review readiness matches the shared backend completion contract', () => {
  for (const item of contract.cases) {
    const faces = item.decisions.map((_, index) => ({ index }));
    const decisions = Object.fromEntries(item.decisions.map((decision, index) => [index, decision]).filter(([, decision]) => decision !== null));
    assert.equal(recognitionReviewReady(faces, decisions), item.frontend_ready, item.name);
    assert.equal(item.frontend_ready, item.backend_error === null, item.name);
  }
});
