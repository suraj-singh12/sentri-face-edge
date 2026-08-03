import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const queue = fs.readFileSync(new URL("../src/views/QueueView.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/sentriface-interface.css", import.meta.url), "utf8");

test("incoming review photos scroll without shrinking thumbnails", () => {
  assert.match(queue, /queue-review-panel queue-incoming-panel/);
  assert.match(css, /\.queue-incoming-panel\s*\{[^}]*display:\s*flex;[^}]*overflow:\s*hidden;/s);
  assert.match(css, /\.queue-photo-selection-grid\s*\{[^}]*flex:\s*1 1 auto;[^}]*overflow-y:\s*auto;/s);
  assert.match(queue, /alt="incoming face" fit="cover" h=\{132\}/);
});

test("comparison identity card and photo grid cannot collapse into each other", () => {
  assert.match(css, /\.queue-reference-person\s*\{[^}]*flex:\s*0 0 auto;[^}]*min-height:\s*76px;/s);
  assert.match(css, /\.queue-compare-overview\s*>\s*\.mantine-Grid-root\s*\{[^}]*flex:\s*0 0 auto;/s);
});
