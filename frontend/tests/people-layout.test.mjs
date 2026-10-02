import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("people grid preserves the existing compact visual layout", async () => {
  const [view, css] = await Promise.all([read("../src/views/PeopleView.jsx"), read("../src/sentriface-interface.css")]);
  assert.match(view, /<Card withBorder radius="md" p="xs" className=\{cardClass\}>/);
  assert.match(css, /\.people-card-grid\s*\{[^}]*minmax\(265px, 1fr\)/s);
  assert.match(css, /\.image-frame--peopleCard\s*\{[^}]*height: 76px;/s);
});

test("collection intelligence is rendered from backend presentation and ordering", async () => {
  const view = await read("../src/views/PeopleView.jsx");
  assert.match(view, /peopleReadModel\?\.statistics/);
  assert.match(view, /peopleReadModel\?\.sort_orders/);
  assert.match(view, /person\.presentation\?\.group_labels/);
  assert.match(view, /person\.presentation\?\.priority_label/);
  assert.doesNotMatch(view, /priorityScore|sightingFrequencyScore|frequentlySeenScore/);
});

test("profile uses normalized sightings, relationships, notes, and journal activity", async () => {
  const view = await read("../src/views/PeopleView.jsx");
  assert.match(view, /const latestSightings = payload\.sightings \|\| \[\]/);
  assert.match(view, /const relationships = payload\.relationships \|\| \[\]/);
  assert.match(view, /const activity = payload\.activity \|\| \[\]/);
  assert.match(view, /const profileNote = payload\.profile_note/);
  assert.match(view, /note\.mentions \|\| \[\]/);
  assert.doesNotMatch(view, /payload\.associations|payload\.changes|management_events/);
});

test("notes preserve backend mention identities and never match names to links", async () => {
  const view = await read("../src/views/PeopleView.jsx");
  assert.match(view, /profileNote\.mentioned_person_ids/);
  assert.match(view, /sameIds\(selectedNoteMentionIds, previousMentionIds\)/);
  assert.match(view, /mention\.occurrence_id/);
  assert.match(view, /mention\.effective_person_id/);
  assert.doesNotMatch(view, /associationByName|escapeRegExp/);
});

test("lifecycle and graph interactions consume explicit backend permissions", async () => {
  const [view, graphView, controller] = await Promise.all([
    read("../src/views/PeopleView.jsx"),
    read("../src/views/PersonGraphView.jsx"),
    read("../src/hooks/usePeopleController.js"),
  ]);
  assert.match(view, /requirePersonContract\(payload\.person\)/);
  assert.match(graphView, /node\.allowed_actions/);
  assert.match(graphView, /data-lifecycle=\{node\.lifecycle_status\}/);
  assert.match(controller, /\/api\/person-graph/);
  assert.match(controller, /\/api\/graph-revision/);
  assert.doesNotMatch(controller, /setInterval|addEventListener\(["']focus/);
  assert.doesNotMatch(controller, /\/api\/person-relationship-graph/);
  assert.doesNotMatch(view, /personLifecycleStatus|metadata\?\.merged_into/);
  assert.doesNotMatch(view, /createRelationshipGraph|mergeRelationshipGraph|relationshipGraphCollections/);
});

test("Manual Association controls use normalized evidence commands", async () => {
  const [view, controller] = await Promise.all([read("../src/views/PeopleView.jsx"), read("../src/hooks/usePeopleController.js")]);
  assert.equal((view.match(/>\s*Open Person Graph\s*<\/Button>/g) || []).length, 2);
  assert.doesNotMatch(view, /Link person|Remove association|Create placeholder/);
  assert.match(controller, /apiPost\("\/api\/person-association"/);
  assert.match(controller, /evidence_id: evidenceId/);
  assert.doesNotMatch(controller, /createPersonAssociation|removePersonAssociation/);
});
