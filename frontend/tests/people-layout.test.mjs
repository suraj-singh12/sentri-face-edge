import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("people grid uses compact cards without shrinking face photos", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/sentriface-interface.css", import.meta.url), "utf8");

  assert.match(view, /<Card withBorder radius="md" p="xs" className=\{cardClass\}>/);
  assert.doesNotMatch(view, /Photos available/);
  assert.match(css, /\.people-card-grid\s*\{[^}]*minmax\(265px, 1fr\)/s);
  assert.match(css, /\.image-frame--peopleCard\s*\{[^}]*height: 76px;/s);
});

test("people library exposes all requested grouping and sorting modes", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");

  for (const label of ["None", "Country", "Rank", "Priority", "Sightings Frequency", "Frequently Seen"]) {
    assert.match(view, new RegExp(`>${label}<`));
  }
  for (const label of ["Newest Added", "Name", "Most Sightings", "Recently Seen"]) {
    assert.match(view, new RegExp(`>${label}<`));
  }
  assert.match(view, /function groupPeople\(/);
  assert.match(view, /function frequentlySeenScore\(/);
  assert.match(view, /<Collapse expanded=\{!closed\}>/);
});

test("profile and management history share the horizontal card flow", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/sentriface-interface.css", import.meta.url), "utf8");

  assert.match(view, /\.\.\.managementEvents\.map\(normalizeManagementChange\)/);
  assert.match(view, /filteredHistoryCards\.map\(\(change, index\)/);
  assert.match(view, /change\.kind === "profile"/);
  assert.match(view, /onClick=\{\(\) => setHistoryView\("list"\)\}/);
  assert.match(view, /onClick=\{\(\) => setHistoryFilter\("metadata"\)\}/);
  assert.match(view, /historyChangeMatchesFilter/);
  assert.match(css, /\.people-change-timeline\[data-view="list"\]/);
  assert.match(css, /\.people-change-history-shell\s*\{[^}]*height:\s*clamp\(420px, calc\(100dvh - 390px\), 520px\);/s);
  assert.match(css, /\.people-change-history-panel\s*\{[^}]*display:\s*flex;[^}]*overflow:\s*hidden;/s);
  assert.match(css, /\.people-change-timeline\s*\{[^}]*flex:\s*1 1 auto;[^}]*min-height:\s*0;/s);
  assert.doesNotMatch(view, />Management Activity</);
});

test("placeholder people use the existing neutral avatar and clear biometric labels", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const controller = await readFile(new URL("../src/hooks/usePeopleController.js", import.meta.url), "utf8");

  assert.match(view, /Add without photo/);
  assert.match(view, /No photograph · No biometric data/);
  assert.match(view, /No biometric data is stored for this person\./);
  assert.match(view, /\["status", "Biometric status", change\.previous_status, change\.new_status\]/);
  assert.match(view, /<IconUser size=\{44\}/);
  assert.match(controller, /apiPost\("\/api\/person-create"/);
  assert.match(controller, /apiPost\("\/api\/person-notes"/);
  assert.match(view, />\s*Add photograph\s*<\/Button>/);
});

test("placeholder photograph enrollment uses atomic review finalisation", async () => {
  const app = await readFile(new URL("../src/SentriFaceApp.jsx", import.meta.url), "utf8");
  const recognize = await readFile(new URL("../src/views/RecognizeView.jsx", import.meta.url), "utf8");
  const controller = await readFile(new URL("../src/hooks/useRecognizeController.js", import.meta.url), "utf8");
  const peopleController = await readFile(new URL("../src/hooks/usePeopleController.js", import.meta.url), "utf8");

  assert.match(app, /actions\.startExistingPersonEnrollment\(person\)/);
  assert.match(recognize, /Adding a photograph to \$\{targetPerson\.name\}/);
  assert.match(recognize, /No new person will be created/);
  assert.match(recognize, /This face resembles another person/);
  assert.match(recognize, /SentriFace will not merge either profile/);
  assert.match(recognize, /conflict_acknowledged: true/);
  assert.match(controller, /person_id: person\.person_id/);
  assert.match(controller, /apiPost\("\/api\/photo-review-decision"/);
  assert.match(controller, /apiPost\("\/api\/photo-review-complete"/);
  assert.match(controller, /target_person_id: recognitionTargetPerson\?\.person_id/);
  assert.doesNotMatch(controller, /apiPost\("\/api\/placeholder-enroll"/);
  assert.match(controller, /result\.created_people/);
  assert.match(peopleController, /apiPost\("\/api\/person-photo-move"/);
  assert.doesNotMatch(peopleController, /Move Face is temporarily unavailable until P7/);
});

test("person profiles provide explicit @ association linking and safe removal", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const controller = await readFile(new URL("../src/hooks/usePeopleController.js", import.meta.url), "utf8");

  assert.match(view, /<Tabs\.Tab value="associations">Associations \(\{associations\.length\}\)<\/Tabs\.Tab>/);
  assert.match(view, /placeholder="@Name"/);
  assert.match(view, />\s*Link person\s*</);
  assert.match(view, /Create placeholder “\{searchText\}”/);
  assert.match(view, />\s*View Relationship Graph\s*<\/Button>/);
  assert.match(view, /function RelationshipGraphModal/);
  assert.match(view, /Show direct associations/);
  assert.match(view, /Graph display limit reached/);
  assert.match(controller, /\/api\/person-association-neighbors/);
  assert.match(view, /Matching people are already linked or refer to this profile\./);
  assert.match(view, /normalizedSearch\.length >= 3/);
  assert.match(view, /association\.association_origin === "automatic_mention" \? "Mention-linked" : "Manually linked"/);
  assert.match(view, /person\.representative_image \? \(/);
  assert.match(view, /This removes only the association\. Neither person nor their photos, biometric data, or history will be deleted\./);
  assert.match(view, /const associationHistorical = personLifecycleStatus\(association\.person\) !== "ACTIVE"/);
  assert.match(view, /if \(!associationHistorical\) onOpen\(association\.person\.person_id, \{ archived: false \}\)/);
  assert.doesNotMatch(controller, /apiPost\("\/api\/person-association"/);
  assert.doesNotMatch(controller, /apiPost\("\/api\/person-association-placeholder"/);
  assert.doesNotMatch(controller, /apiPost\("\/api\/person-association-remove"/);
  assert.match(controller, /Manual associations are temporarily unavailable/);
});

test("person lifecycle states remain explicit and historical graph nodes are non-clickable", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const data = await readFile(new URL("../src/hooks/useAppData.js", import.meta.url), "utf8");

  assert.match(view, /\["ACTIVE", "ARCHIVED", "DELETED", "MERGED"\]/);
  assert.match(view, /const canRestore = lifecycleStatus === "ARCHIVED"/);
  assert.match(view, /disabled=\{isHistorical\}/);
  assert.match(view, /personLifecycleStatus\(node\) !== "ACTIVE"/);
  assert.match(data, /lifecycle_status: "ARCHIVED"/);
  assert.match(data, /lifecycle_status: "ACTIVE"/);
});

test("person and sighting notes use explicit saves and local write responses", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/sentriface-interface.css", import.meta.url), "utf8");
  const followup = await readFile(new URL("../src/components/RecognitionFollowupForm.jsx", import.meta.url), "utf8");
  const controller = await readFile(new URL("../src/hooks/usePeopleController.js", import.meta.url), "utf8");

  assert.match(view, /<Text size="sm" fw=\{800\} mb="xs">Notes<\/Text>/);
  assert.match(view, /rightSection=\{<IconChevronDown size=\{14\} \/>\}>Edit<\/Button>/);
  assert.match(view, /onClick=\{openProfileEdit\}>Edit profile<\/Menu\.Item>/);
  assert.match(view, /onClick=\{openNotesEdit\}>Edit notes<\/Menu\.Item>/);
  assert.match(view, /function ProfileNoteSummary/);
  assert.match(view, /className="people-note-person-chip"/);
  assert.match(view, /title="Edit Person"/);
  assert.match(view, /title="Edit Notes"/);
  assert.match(view, /activeMentionQuery\.length < 3/);
  assert.match(view, /replaceNoteMentionQuery/);
  assert.match(view, /@\(\[\^@,\\n\]\*\)\$\/\)/);
  assert.match(view, /`\$\{prefix\}@\$\{personName\}, `/);
  assert.match(view, /No exact person named “\{activeMentionQuery\}”/);
  assert.match(view, />\s*Create profile\s*<\/Button>/);
  assert.match(view, /This creates an unknown identity/);
  assert.match(view, /Create profile without photo/);
  assert.match(view, /function PlaceholderPersonFields/);
  for (const label of ["Rank", "Name", "Country", "Importance", "Date", "Time", "Place Seen", "With how many individuals", "Event\/Occasion", "Added by"]) {
    assert.match(view, new RegExp(`required[^>]*label="${label}"`));
  }
  assert.match(view, /importance: NEW_PERSON_IMPORTANCE_OPTIONS\[1\]/);
  assert.match(view, /suggestions\.map\(\(candidate\)/);
  assert.match(view, /mention an existing person/);
  assert.match(view, /const createdPerson = await onCreateIdentifiedPerson\(notePlaceholderValues\)/);
  assert.match(view, /createdPerson\.person_id/);
  assert.match(view, /className="people-profile-notes"/);
  assert.match(css, /\.people-profile-hero\s*\{[^}]*grid-template-columns:\s*164px minmax\(240px, 1fr\) minmax\(300px, 420px\)/s);
  assert.match(followup, /Notes for this sighting \/ photo/);
  assert.match(followup, /mentionQuery\.length < 3/);
  assert.match(followup, /mentionedPersonIds/);
  assert.match(followup, /`\$\{prefix\}@\$\{name\}, `/);
  assert.match(controller, /apiPost\("\/api\/person-notes"/);
  for (const field of ["seen_date", "seen_time", "place_seen", "individual_count", "event_occasion", "added_by"]) {
    assert.match(controller, new RegExp(`${field}:`));
  }
  assert.doesNotMatch(controller, /savePersonNotes[\s\S]{0,1200}loadPerson\(/);
});
