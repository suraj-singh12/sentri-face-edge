import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const queue = fs.readFileSync(new URL("../src/views/QueueView.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/sentriface-interface.css", import.meta.url), "utf8");

test("incoming review photos scroll without cropping or shrinking thumbnails", () => {
  assert.match(queue, /queue-review-panel queue-incoming-panel/);
  assert.match(css, /\.queue-incoming-panel\s*\{[^}]*display:\s*flex;[^}]*overflow:\s*hidden;/s);
  assert.match(css, /\.queue-photo-selection-grid\s*\{[^}]*flex:\s*1 1 0;[^}]*height:\s*0;[^}]*overflow-y:\s*scroll;[^}]*grid-auto-rows:\s*max-content;/s);
  assert.match(css, /\.queue-incoming-panel\s*\{[^}]*height:\s*clamp\(430px, calc\(100dvh - 500px\), 600px\);/s);
  assert.match(css, /\.queue-selection-card\s*\{[^}]*min-height:\s*244px;[^}]*flex-shrink:\s*0;/s);
  assert.match(css, /\.queue-selection-image\s*\{[^}]*height:\s*200px !important;[^}]*min-height:\s*200px;[^}]*max-height:\s*200px;/s);
  assert.match(queue, /alt="incoming face"[\s\S]*className="queue-selection-image"[\s\S]*fit="contain"[\s\S]*h=\{200\}/);
  assert.match(queue, /face\.source_image \|\| face\.image_path \|\| face\.crop_path/);
  assert.match(css, /\.queue-selection-image\s*\{[^}]*min-height:\s*200px;[^}]*object-fit:\s*contain;/s);
  assert.match(css, /\.queue-selection-image img\s*\{[^}]*object-fit:\s*contain;/s);
});

test("comparison identity card and photo grid cannot collapse into each other", () => {
  assert.match(css, /\.queue-reference-person\s*\{[^}]*flex:\s*0 0 auto;[^}]*min-height:\s*76px;/s);
  assert.match(css, /\.queue-compare-overview\s*>\s*\.mantine-Grid-root\s*\{[^}]*flex:\s*0 0 auto;/s);
});
