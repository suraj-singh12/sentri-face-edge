import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const controller = fs.readFileSync(new URL("../src/hooks/useRecoveryController.js", import.meta.url), "utf8");
const panel = fs.readFileSync(new URL("../src/views/RecoveryPanel.jsx", import.meta.url), "utf8");
const debugView = fs.readFileSync(new URL("../src/views/DebugView.jsx", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/SentriFaceApp.jsx", import.meta.url), "utf8");

test("P11-E is visible only through the recovery capability", () => {
  assert.match(debugView, /capabilitySet\.has\("recovery"\).*Integrity & recovery/);
  assert.match(debugView, /section === "integrity"[\s\S]*<RecoveryPanel/);
  assert.match(app, /can\("recovery"\)/);
  assert.match(app, /recovery=\{state\.recovery\}/);
});

test("P11-E prepares server actions before execution and sends no client-built repair target", () => {
  assert.match(controller, /\/api\/integrity\/check/);
  assert.match(controller, /report_token: report\.report_token,[\s\S]*action_id: action\.action_id/);
  assert.match(controller, /token: plan\.token,[\s\S]*operation_id: plan\.operationId,[\s\S]*reason/);
  assert.doesNotMatch(controller, /survivor_person_id|referenced_person_id|note_id|canonical_person_id/);
  assert.match(panel, /\{plan\.summary\}/);
  assert.match(panel, /values=\{plan\.expected_changes\}/);
  assert.match(panel, /Execute prepared action/);
});

test("stale state clears the plan and committed postcheck failure remains factual", () => {
  assert.match(controller, /stale_precondition[\s\S]*setPlan\(null\)/);
  assert.match(controller, /postcheck_failed_after_commit/);
  assert.match(controller, /The operation committed, but post-operation integrity verification failed/);
  assert.match(panel, /Operation committed; verification failed/);
  assert.match(panel, /no automatic follow-up ran/);
});

test("P11-E has no polling and applies no optimistic domain mutation", () => {
  assert.doesNotMatch(controller, /setInterval|setTimeout|useEffect/);
  assert.doesNotMatch(panel, /setInterval|setTimeout/);
  assert.match(controller, /setReport\(executed\.integrity_report \|\| null\)/);
  assert.match(controller, /operationId: crypto\.randomUUID\(\)/);
  assert.match(controller, /operation_id: plan\.operationId/);
});

test("the bounded recovery components are explicit", () => {
  for (const component of [
    "RecoveryPanel",
    "IntegritySummary",
    "IntegrityFindingList",
    "IntegrityFindingDetail",
    "RecoveryActionPlanModal",
    "RecoveryResultPanel",
  ]) {
    assert.match(panel, new RegExp(`export function ${component}`));
  }
});
