import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const gate = fs.readFileSync(new URL("../src/components/RecoveryGate.jsx", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/SentriFaceApp.jsx", import.meta.url), "utf8");

test("disaster recovery requires an explicit risk acknowledgement", () => {
  assert.match(gate, /\/api\/recovery\/readiness/);
  assert.match(gate, /acknowledge_risk: true/);
  assert.match(gate, /Continue without disaster recovery/);
  assert.match(gate, /I understand that this machine has no usable disaster-recovery copy/);
  assert.match(gate, /disabled=\{!riskAccepted\}/);
});

test("the application keeps warning until disaster recovery is ready", () => {
  assert.match(app, /!state\.profile\.recovery_readiness\?\.ready/);
  assert.match(app, /Disaster recovery is not ready/);
  assert.match(app, /An administrator can configure recovery from Advanced/);
});
