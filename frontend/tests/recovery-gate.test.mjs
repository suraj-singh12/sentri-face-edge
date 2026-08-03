import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const gate = fs.readFileSync(new URL("../src/components/RecoveryGate.jsx", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/SentriFaceApp.jsx", import.meta.url), "utf8");

test("skipping the safety copy requires an explicit risk acknowledgement", () => {
  assert.match(gate, /\/api\/recovery\/readiness/);
  assert.match(gate, /\/api\/recovery\/destinations/);
  assert.match(gate, /Choose a connected drive/);
  assert.match(gate, /No separate drive was found/);
  assert.match(gate, /acknowledge_risk: true/);
  assert.match(gate, /Skip for now/);
  assert.match(gate, /my data may not be recoverable without a safety copy/);
  assert.match(gate, /disabled=\{!riskAccepted\}/);
});

test("the application keeps warning until the safety copy is ready", () => {
  assert.match(app, /!state\.profile\.recovery_readiness\?\.ready/);
  assert.match(app, /Your safety copy needs attention/);
  assert.match(app, /owner can check it under Settings/);
  assert.match(app, /className="shell-notice"/);
  assert.match(app, /actions\.setActiveView\("debug"\)/);
});
