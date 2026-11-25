import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("stale correction errors offer an explicit current-Event reload", async () => {
  const [events, details, management] = await Promise.all([
    read("../src/views/EventsView.jsx"),
    read("../src/components/EncounterDetailsModal.jsx"),
    read("../src/components/EncounterManagementModal.jsx"),
  ]);
  assert.match(events, /onReload=\{\(\) => onOpen\(detail\.observation_id\)\}/);
  assert.match(events, /reloadCurrentEvent/);
  for (const source of [details, management]) {
    assert.match(source, /Reload current Event/);
    assert.match(source, /Reloading discards this unsaved correction/);
    assert.match(source, /stale\|changed\|reload/);
  }
});

test("changing correction context clears the previous submit error", async () => {
  const management = await read("../src/components/EncounterManagementModal.jsx");
  assert.match(management, /clearError\(\); setAction\(value\)/);
  assert.match(management, /clearError\(\); setPersonId\(value\)/);
  assert.match(management, /clearError\(\); setTargetId\(value\)/);
  assert.match(management, /clearError\(\); setDecisions/);
  const events = await read("../src/views/EventsView.jsx");
  assert.match(events, /setError\(""\); setValues/);
});
