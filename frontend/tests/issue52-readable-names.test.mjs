import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("decision-point names stay on one line with the full name on hover", async () => {
  const [shared, people, recognize, queue] = await Promise.all([
    read("../src/components/Shared.jsx"),
    read("../src/views/PeopleView.jsx"),
    read("../src/views/RecognizeView.jsx"),
    read("../src/views/QueueView.jsx"),
  ]);
  assert.match(shared, /export function PersonName[\s\S]*<Tooltip label=\{name\}[\s\S]*truncate="end"/);
  for (const source of [people, recognize, queue]) {
    assert.doesNotMatch(source, /<Text fw=\{800\} (?:truncate|lineClamp=\{\d\})>\{person\.name\}/);
    assert.match(source, /<PersonName name=\{person\.name\}/);
  }
  assert.doesNotMatch(people, /lineClamp=\{2\}/);
});

test("People cards show the full name on keyboard focus and keep badges off the name line", async () => {
  const people = await read("../src/views/PeopleView.jsx");
  assert.match(people, /<Tooltip label=\{person\.name\} \{\.\.\.NAME_TOOLTIP_PROPS\} events=\{\{ hover: false, focus: canOpen, touch: false \}\}>\s*<Box component=\{canOpen \? "button" : "div"\}/);
  assert.match(people, /<PersonName name=\{person\.name\} fw=\{800\} focusable=\{!canOpen\} \/>\s*\{historical && <Badge[^>]*flexShrink: 0/);
});

test("full-name tooltips wrap unbroken names inside the viewport", async () => {
  const shared = await read("../src/components/Shared.jsx");
  assert.match(shared, /maw: "min\(320px, calc\(100vw - 32px\)\)"/);
  assert.match(shared, /overflowWrap: "anywhere"/);
});
