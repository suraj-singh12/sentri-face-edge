import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const queue = fs.readFileSync(new URL("../src/views/QueueView.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/sentriface-interface.css", import.meta.url), "utf8");

test("incoming review photos and Encounter actions use one reachable page scroll", () => {
  assert.match(queue, /queue-review-panel queue-incoming-panel/);
  assert.match(css, /Review Photos uses the page scroll[\s\S]*\.queue-photo-selection-grid\s*\{\s*flex:\s*none;/s);
  assert.match(css, /\.queue-review-actionbar\s*\{\s*position:\s*sticky;\s*bottom:\s*12px;/s);
  assert.match(css, /\.queue-face-image-wrap img\s*\{[^}]*max-height:\s*200px;/s);
  assert.match(queue, /aria-label="Current face boundary"/);
  assert.match(queue, /naturalWidth[\s\S]*naturalHeight[\s\S]*100 \* box\.x \/ dimensions\.width/);
  assert.match(queue, /face\.source_image \|\| face\.image_path \|\| face\.crop_path/);
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
  assert.match(queue, /onClick=\{\(\) => \{ scrollToFollowup\(\); onAcceptExisting\(best\); \}\}/);
  assert.match(queue, /const choosePerson = \(person\) => \{\s*onSelectExisting\(\);/);
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
