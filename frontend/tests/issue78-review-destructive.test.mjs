import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("destructive Event and face review actions use shared confirmations", async () => {
  const view = await read("../src/views/QueueView.jsx");
  assert.match(view, /discardEncounterOpen/);
  assert.match(view, /title="Discard this Event draft\?"/);
  assert.match(view, /Pending review decisions for this Event are removed/);
  assert.match(view, /clearFacesOpen/);
  assert.match(view, /title="Clear selected photos\?"/);
  assert.match(view, /discardFacesOpen/);
  assert.match(view, /title=\{selectedCount === 1 \? "Discard 1 selected face\?"/);
  assert.doesNotMatch(view, /onClick=\{onDiscardEncounter\}/);
  assert.doesNotMatch(view, /onClick=\{onClearFaces\}/);
});

test("group discard is not offered before Event details are complete", async () => {
  const view = await read("../src/views/QueueView.jsx");
  assert.match(view, /eventDetailsIncomplete=\{Boolean\(activeEncounter && !activeEncounter\.event_details_complete\)\}/);
  assert.match(view, /Complete Event details before discarding a group/);
});
