import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { browsePeopleCandidates } from "../src/utils/profileBrowse.js";

const read = async (path) => readFile(new URL(path, import.meta.url), "utf8");

test("Browse keeps ranked biometric order and shows only actual NO_FACE profiles separately", () => {
  const ranked = [
    { person_id: "b", name: "B", biometric_status: "ENROLLED", match: { rank: 1, score: 0.9 } },
    { person_id: "n", name: "No Face", biometric_status: "NO_FACE", match: null },
    { person_id: "proof", name: "Proof Only", biometric_status: "ENROLLED", match: null },
    { person_id: "a", name: "A", biometric_status: "ENROLLED", match: { rank: 3, score: 0.8 } },
  ];
  assert.deepEqual(browsePeopleCandidates(ranked, [], "biometric"), [ranked[0], ranked[3]]);
  const people = [
    { person_id: "proof", name: "Proof Only", lifecycle_status: "ACTIVE", biometric_status: "ENROLLED" },
    { person_id: "z", name: "Zed", lifecycle_status: "ACTIVE", biometric_status: "NO_FACE" },
    { person_id: "archived", name: "Archived", lifecycle_status: "ARCHIVED", biometric_status: "NO_FACE" },
    { person_id: "a", name: "Alice", lifecycle_status: "ACTIVE", biometric_status: "NO_FACE" },
  ];
  assert.deepEqual(browsePeopleCandidates(ranked, people, "no_face").map((item) => item.person_id), ["a", "z"]);
});

test("both review surfaces expose the same profile selector and proof-only duplicate choice", async () => {
  for (const view of ["RecognizeView.jsx", "QueueView.jsx"]) {
    const source = await read(`../src/views/${view}`);
    assert.match(source, /PROFILE_BROWSE_MODES/);
    assert.match(source, /browsePeopleCandidates/);
    assert.match(source, /Possible existing profile/);
    assert.match(source, /Create new Person anyway/);
  }
  for (const controller of ["useRecognizeController.js", "useQueueController.js"]) {
    const source = await read(`../src/hooks/${controller}`);
    assert.match(source, /apiPost\("\/api\/proof-only-duplicate-check"/);
    assert.match(source, /proof_only_duplicate_override: createAnyway/);
  }
});

test("Events reads use one bounded backend query and never mutate graph state", async () => {
  const [events, appData, people] = await Promise.all([
    read("../src/views/EventsView.jsx"),
    read("../src/hooks/useAppData.js"),
    read("../src/views/PeopleView.jsx"),
  ]);
  assert.match(appData, /apiGet\(`\/api\/encounters\?/);
  assert.match(events, /Read-only history of finalized Encounters/);
  assert.match(events, /Mentioned: /);
  assert.match(people, /<Tabs\.Tab value="events">Events<\/Tabs\.Tab>/);
  assert.match(people, /person_status/);
});
