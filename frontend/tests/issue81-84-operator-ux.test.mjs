import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("Attach Media review keeps target Event context visible", async () => {
  const queue = await read("../src/views/QueueView.jsx");
  assert.match(queue, /Attaching media to \{activeEncounter\.event_details\?\.event_occasion/);
  assert.match(queue, /activeEncounter\.event_details\?\.date/);
  assert.match(queue, /activeEncounter\.event_details\?\.place_seen/);
  assert.match(queue, /EncounterRelations review=\{activeEncounter\}[\s\S]*targetDetails=/);
});

test("long Person Notes have an explicit read-only expansion path", async () => {
  const people = await read("../src/views/PeopleView.jsx");
  const css = await read("../src/sentriface-interface.css");
  assert.match(people, /Read full note/);
  assert.match(people, /aria-expanded=\{expanded\}/);
  assert.match(css, /people-profile-note-expanded/);
  assert.match(css, /max-height: none/);
});

test("Person Graph edges are keyboard selectable", async () => {
  const graph = await read("../src/views/PersonGraphView.jsx");
  assert.match(graph, /role="button" tabIndex=\{0\} aria-label=\{`Inspect relationship evidence/);
  assert.match(graph, /event\.key.*Enter.* /s);
  assert.match(graph, /onClick=\{choose\}/);
});

test("read-only roles see the permission boundary instead of a dead end", async () => {
  const [people, events] = await Promise.all([read("../src/views/PeopleView.jsx"), read("../src/views/EventsView.jsx")]);
  assert.match(people, /Read-only access: profile editing, notes, face management/);
  assert.match(events, /Read-only access: Attach Media and Event corrections/);
});
