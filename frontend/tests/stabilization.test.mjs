import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { COUNTRY_OPTIONS, filterCountries } from "../src/countries.js";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("offline country picker browses and filters after three characters", () => {
  const options = COUNTRY_OPTIONS.map((label) => ({ label, value: label }));
  assert.ok(options.length >= 190);
  assert.ok(options.some((item) => item.value === "India"));
  assert.equal(filterCountries({ options, search: "" }), options);
  assert.equal(filterCountries({ options, search: "in" }), options);
  assert.ok(filterCountries({ options, search: "IND" }).some((item) => item.value === "India"));
  assert.ok(filterCountries({ options, search: "iNd" }).length < options.length);
  assert.equal(filterCountries({ options, search: "" }), options);
  const picker = read("../src/components/CountrySelect.jsx");
  assert.match(picker, /searchable/);
  assert.match(picker, /filter=\{filterCountries\}/);
  assert.match(picker, /onChange=\{\(selected\) => onChange\(selected \|\| ""\)\}/);
});

test("every person profile entry uses the effective API default", () => {
  const people = read("../src/hooks/usePeopleController.js");
  const recognize = read("../src/hooks/useRecognizeController.js");
  const queue = read("../src/hooks/useQueueController.js");
  for (const caller of [people, recognize, queue]) {
    assert.match(caller, /\/api\/person\?person_id=/);
  }
  assert.match(read("../../src/sentriface/api_server.py"), /get\("view", \["effective"\]\)/);
});

test("new-person draft is discarded before selecting an existing person", () => {
  const queue = read("../src/views/QueueView.jsx");
  const controller = read("../src/hooks/useQueueController.js");
  assert.match(queue, /const choosePerson = \(person\) => \{\s*onSelectExisting\(\);/);
  assert.match(controller, /const queueSelectExisting = \(\) => \{[\s\S]*setQueueAccepted\(false\);[\s\S]*setQueueFollowup\(null\);/);
  assert.match(queue, /onNewPerson=\{\(\) => \{[\s\S]*setManualPerson\(null\);/);
});

test("form scroll is requested by deliberate actions only", () => {
  const hook = read("../src/hooks/useIntentionalFormScroll.js");
  assert.match(hook, /pendingRef\.current/);
  assert.match(hook, /scrollIntoView/);
  assert.doesNotMatch(hook, /setTimeout/);
  assert.match(read("../src/views/RecognizeView.jsx"), /scrollToFollowup\(\)/);
  assert.match(read("../src/views/QueueView.jsx"), /scrollToFollowup\(\)/);
});

test("developer metrics are hidden and shared panels retain readable widths", () => {
  assert.doesNotMatch(read("../src/views/RecognizeView.jsx"), /<Metrics /);
  const css = read("../src/sentriface-interface.css");
  assert.match(css, /\.recognize-complete-button\s*\{[^}]*min-height:\s*58px;[^}]*flex-shrink:\s*0;/s);
  assert.match(css, /\.debug-workspace\s*\{[^}]*container-type:\s*inline-size;/s);
  assert.match(css, /@container \(max-width: 760px\)/);
});
