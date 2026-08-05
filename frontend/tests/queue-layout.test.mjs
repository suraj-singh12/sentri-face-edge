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

test("weak queue matches use a human-controlled People picker", () => {
  assert.match(queue, /automaticBest[\s\S]*automaticKnown[\s\S]*weakMatch/);
  assert.match(queue, /"Weak match"/);
  assert.match(queue, />Browse People</);
  assert.match(queue, /function PeoplePicker/);
  assert.match(queue, />New person</);
  assert.match(queue, /visiblePeople\.map/);
  assert.match(queue, /setManualPerson\(null\);[\s\S]*onGalleryBack\(\);[\s\S]*onNewPerson\(\);/);
  assert.match(queue, /person\.match\?\.classification === "unknown"/);
  assert.match(queue, /#\{person\.match\.rank\}/);
  assert.match(queue, /onClick=\{\(\) => onAcceptExisting\(best\)\}/);
  assert.match(queue, /View reference photos/);
  assert.doesNotMatch(queue, /face\?\.crop_path \|\| face\?\.source_image/);
  assert.match(css, /\.queue-person-picker-card\s*\{[^}]*min-height:\s*210px;/s);
  assert.match(css, /\.queue-person-picker-photo\s*\{[^}]*height:\s*132px;/s);
});

test("processing progress stays visually primary without clipping its details", () => {
  assert.match(queue, /className="queue-review-list" data-processing=\{isProcessing \|\| undefined\}/);
  assert.match(queue, /<Stack gap="md">[\s\S]*queue-processing-source/);
  assert.match(css, /\.queue-processing-card\s*\{[^}]*flex:\s*0 0 auto;[^}]*padding:\s*16px 20px !important;/s);
  assert.match(css, /\.queue-processing-stat\s*\{[^}]*min-height:\s*52px;/s);
  assert.match(css, /\.queue-groups-pending-card\s*\{[^}]*min-height:\s*88px;/s);
  assert.match(css, /\.queue-groups-pending-card\s*>\s*\.mantine-Group-root\s*\{[^}]*min-height:\s*62px;/s);
  assert.match(queue, /\{\[0, 1, 2\]\.map/);
});
