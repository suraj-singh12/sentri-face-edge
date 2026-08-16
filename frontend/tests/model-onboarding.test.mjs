import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("signed-in model onboarding browses local files and automates verification", async () => {
  const gate = await readFile(new URL("../src/components/ModelGate.jsx", import.meta.url), "utf8");
  const app = await readFile(new URL("../src/SentriFaceApp.jsx", import.meta.url), "utf8");
  assert.match(gate, /Personal or research/);
  assert.match(gate, /Business or paid use/);
  assert.match(gate, /Browse files/);
  assert.match(gate, /\/api\/models\/upload/);
  assert.match(gate, /detector_upload_id/);
  assert.match(gate, /recognizer_upload_id/);
  assert.doesNotMatch(gate, /detector_path|recognizer_path|uploaded\.path/);
  assert.match(gate, /Prepare setup/);
  assert.match(gate, /\/api\/models\/activation\/execute/);
  assert.match(gate, /\/api\/models\/activation\/prepare/);
  assert.match(gate, /candidate_bundles/);
  assert.match(gate, /token: preparation\.token/);
  assert.match(gate, /Activate verified bundle/);
  assert.doesNotMatch(gate, /actor:/);
  assert.doesNotMatch(gate, /setInterval|setTimeout/);
  assert.match(gate, /You do not need to type a path or create a checksum/);
  assert.match(gate, /researchMatch/);
  assert.match(gate, /create the matching settings automatically/);
  assert.doesNotMatch(gate, /digest=\{/);
  assert.doesNotMatch(gate, /Calibration is automatic/);
  assert.doesNotMatch(gate, /Local file path/);
  assert.doesNotMatch(gate, /onDigest/);
  assert.match(gate, /sentriface-models-required/);
  assert.doesNotMatch(gate, /https?:\/\//);
  assert.match(app, /<AuthGate>.*<ModelGate/s);
});
