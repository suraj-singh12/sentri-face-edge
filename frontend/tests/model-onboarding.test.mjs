import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("signed-in model onboarding presents research and commercial local-only paths", async () => {
  const gate = await readFile(new URL("../src/components/ModelGate.jsx", import.meta.url), "utf8");
  const app = await readFile(new URL("../src/SentriFaceApp.jsx", import.meta.url), "utf8");
  assert.match(gate, /Research only/);
  assert.match(gate, /Commercial use/);
  assert.match(gate, /Local file path/);
  assert.match(gate, /SHA-256/);
  assert.match(gate, /Calibration threshold file \(optional\)/);
  assert.match(gate, /built-in thresholds/);
  assert.match(gate, /accepted InsightFace provider baseline/);
  assert.match(gate, /Example values for this selection/);
  assert.match(gate, /Download setup example/);
  assert.match(gate, /Download calibration example/);
  assert.match(gate, /URL.createObjectURL/);
  assert.match(gate, /representative_dataset/);
  assert.match(gate, /Angle-bracket values are placeholders, never evidence/);
  assert.match(gate, /SentriFace never downloads or uploads model files/);
  assert.match(gate, /sentriface-models-required/);
  assert.doesNotMatch(gate, /https?:\/\//);
  assert.match(app, /<AuthGate>.*<ModelGate/s);
});