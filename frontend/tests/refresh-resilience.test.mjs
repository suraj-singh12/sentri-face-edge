import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const appData = fs.readFileSync(new URL("../src/hooks/useAppData.js", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/SentriFaceApp.jsx", import.meta.url), "utf8");

test("manual refresh is bounded and visibly reports progress", () => {
  assert.match(appData, /refreshAll\(\{ timeoutMs: 8_000, silent: true \}\)/);
  assert.match(appData, /setRefreshing\(true\)/);
  assert.match(appData, /finally \{\s*setRefreshing\(false\)/);
  assert.match(app, /disabled=\{state\.refreshing\}/);
  assert.match(app, /state\.refreshing \? <Loader/);
});
