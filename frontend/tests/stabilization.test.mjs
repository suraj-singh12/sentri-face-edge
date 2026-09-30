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
    assert.match(caller, /&view=/);
  }
  assert.match(read("../../src/sentriface/api_server.py"), /get\("view", \["effective"\]\)/);
});

test("sighting mention suggestions load People outside the People tab and submit selected IDs", () => {
  const appData = read("../src/hooks/useAppData.js");
  const form = read("../src/components/RecognitionFollowupForm.jsx");
  for (const controller of ["useRecognizeController.js", "useQueueController.js"]) {
    assert.match(read(`../src/hooks/${controller}`), /mentioned_person_ids:/);
  }
  assert.match(appData, /\["people", "recognize", "queue", "encounters"\]\.includes\(activeView\)/);
  assert.match(form, /mentionQuery\.length < 3/);
  assert.match(form, /person\.person_id/);
  assert.match(form, /onChange\("mentionedPersonIds"/);
});

test("review followups submit shared Encounter metadata", () => {
  const recognize = read("../src/hooks/useRecognizeController.js");
  const queue = read("../src/hooks/useQueueController.js");
  assert.match(recognize, /encounterMetadata:/);
  assert.match(recognize, /encounterLocked: Boolean/);
  for (const controller of [recognize, queue]) {
    assert.match(controller, /event_context:/);
    assert.match(controller, /event_notes:/);
    assert.match(controller, /end_time:/);
    assert.match(controller, /time_precision:/);
  }
});

test("Event popup confirms before person resolution and keeps person fields", () => {
  const eventForm = read("../src/components/EncounterDetailsModal.jsx");
  const personForm = read("../src/components/RecognitionFollowupForm.jsx");
  const recognize = read("../src/views/RecognizeView.jsx");
  const queue = read("../src/views/QueueView.jsx");
  assert.match(eventForm, /Confirm Event/);
  assert.match(eventForm, /eventMentionedPersonIds/);
  assert.match(eventForm, /query\.length < 3/);
  assert.match(recognize, /!recognition\?\.encounterMetadata/);
  assert.match(queue, /activeEncounter\?\.phase === "EVENT" && eventDetails\?\.reviewId !== activeEncounter\.review_id/);
  assert.match(read("../src/hooks/useQueueController.js"), /\/api\/queue-encounter-event/);
  assert.match(read("../src/hooks/useQueueController.js"), /setQueueEvent\(null\);\s*setQueueEventDraft\(null\);/);
  for (const field of ["Rank", "Name", "Tag", "Added by", "Sighting Notes", "With how many individuals"]) {
    assert.ok(personForm.includes(field), field);
  }
  assert.match(personForm, /Inherited Encounter/);
  assert.doesNotMatch(personForm, /<TextInput[^>]*label="Date"/);
  assert.doesNotMatch(personForm, /<Textarea label="Event notes"/);
});

test("quality search policy and poor-face decisions are independent", () => {
  const recognize = read("../src/hooks/useRecognizeController.js");
  const queue = read("../src/hooks/useQueueController.js");
  const recognizeView = read("../src/views/RecognizeView.jsx");
  const personForm = read("../src/components/RecognitionFollowupForm.jsx");
  for (const controller of [recognize, queue]) assert.match(controller, /quality_only:/);
  assert.match(recognize, /embedding_state:/);
  assert.match(queue, /quality_choices:/);
  assert.match(recognizeView, /No, keep as proof only/);
  assert.match(recognizeView, /Yes, accept low-quality face/);
  assert.match(personForm, /POOR_ACCEPTED/);
  assert.match(personForm, /PROOF_ONLY/);
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

test("Encounter grouping precedes identity cards and permits valid photos beside finalized conflicts", () => {
  const queue = read("../src/views/QueueView.jsx");
  const controller = read("../src/hooks/useQueueController.js");
  assert.match(queue, /encounterMedia\.length > 0 && encounterReviews\.length === 0 && !\["running", "cancelling"\]/);
  assert.match(queue, /NumberInput label="How many\?"/);
  assert.match(queue, /const canSuggest = folders\.length > 1/);
  assert.match(queue, /title=\{canSuggest \? "Suggest Encounters from the uploaded folder structure"/);
  assert.match(queue, /data-conflict=\{Boolean\(item\.finalized_encounter\)/);
  assert.match(queue, /aria-label=\{`Remove photo/);
  assert.match(queue, /const usable = ordered\.filter\(\(item\) => !item\.excluded && !item\.finalized_encounter\)/);
  assert.match(queue, /disabled=\{!usable\.length \|\| !validBuckets/);
  assert.match(controller, /onPlanEncounters|planQueueEncounters/);
});

test("Skip defers Encounter groups while Relations and proof-only review keep explicit state", () => {
  const queue = read("../src/views/QueueView.jsx");
  const controller = read("../src/hooks/useQueueController.js");
  assert.match(controller, /const queueSkipGroup = async \(\) => \{[\s\S]*apiPost\("\/api\/queue-skip"/);
  assert.match(controller, /await loadQueueGroups\(queueSelectedGroup\.session_id\)/);
  assert.match(queue, /encounterReview=\{Boolean\(activeEncounter\)\}/);
  assert.match(queue, /!encounterReview && sessionId/);
  assert.match(queue, /aria-pressed=\{decisions\.get\(key\) === "INCLUDE"\}/);
  assert.match(queue, /aria-pressed=\{decisions\.get\(key\) === "EXCLUDE"\}/);
  assert.match(queue, /proofOnlyDuplicateCandidates\.map/);
  assert.match(controller, /\/api\/proof-only-duplicate-check/);
});

test("review decisions reconcile refreshed groups and persist selection and preference at the backend", () => {
  const controller = read("../src/hooks/useQueueController.js");
  assert.match(controller, /planQueueEncounters:[\s\S]*await loadQueueGroups\(queueSessionId\)/);
  assert.match(controller, /current\.filter\(\(id\) => liveIds\.has\(id\)\)/);
  assert.match(controller, /followupRef\.current\?\.faceIds\?\.some/);
  assert.match(controller, /apiPost\("\/api\/queue-media-selection"/);
  assert.match(controller, /apiPost\("\/api\/queue-quality-policy"/);
  assert.match(controller, /review_id: activeEncounter\?\.review_id/);
  assert.match(controller, /draftPersonKey: candidate\.draft_person_key/);
  assert.doesNotMatch(controller, /group\.draft_matches\?\.\[0\]/);
});

test("new-person submission validates the current form and never emits the old fill-details notification", () => {
  const controller = read("../src/hooks/useQueueController.js");
  assert.match(controller, /followupRef\.current = \{ \.\.\.followupRef\.current, \[field\]: value \}/);
  assert.match(controller, /const queueFollowup = followupRef\.current && \{ \.\.\.followupRef\.current \}/);
  assert.match(controller, /Required: \$\{missing\.join/);
  assert.match(controller, /Number\.isInteger\(Number\(queueFollowup\.individualCount\)\)/);
  assert.doesNotMatch(controller, /Fill new person details/);
  const client = read("../src/hooks/useApiClient.js");
  assert.match(client, /autoClose: options\.autoClose \?\? 4500/);
  assert.doesNotMatch(client, /autoClose: false/);
});

test("Peek In uses an existing crop or stored coordinates and keeps explicit decisions in modals", () => {
  const queue = read("../src/views/QueueView.jsx");
  assert.match(queue, />Peek In</);
  assert.match(queue, /onClose=\{\(\) => setPeek\(null\)\}/);
  assert.match(queue, /Math\.min\(250 \/ box\.width, 250 \/ box\.height\)/);
  assert.match(queue, /face\.crop_path \|\| !scale/);
  assert.match(queue, /transformOrigin: "top left"/);
  assert.match(queue, /best\?\.draft_created && <Badge>Drafted/);
  assert.match(queue, /Modal opened=\{proofOnlyDuplicateCandidates\.length > 0\} onClose=\{\(\) => \{\}\}/);
  assert.doesNotMatch(queue, /const \[removed, setRemoved\]/);
});

test("Person Graph hover explains canonical Encounter counts and note direction", () => {
  const graph = read("../src/views/PersonGraphView.jsx");
  assert.match(graph, /setHovered\(connection \? \{ type: "edge", value: connection \}/);
  assert.match(graph, /provenance\.distinct_encounter_count/);
  assert.match(graph, /provenance\.latest_shared_encounter_at/);
  assert.match(graph, /provenance\.note_reference_direction_counts/);
});
