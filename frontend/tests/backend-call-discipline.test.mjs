import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("successful operations update local state without broad refetches", async () => {
  const [people, recognize, queue, accounts] = await Promise.all([
    read("../src/hooks/usePeopleController.js"),
    read("../src/hooks/useRecognizeController.js"),
    read("../src/hooks/useQueueController.js"),
    read("../src/views/AccountsPanel.jsx"),
  ]);

  for (const controller of [people, recognize, queue]) {
    assert.doesNotMatch(controller, /loadEvents/);
    assert.doesNotMatch(controller, /loadPeople/);
  }
  assert.doesNotMatch(people, /refreshPersonAndLists/);
  assert.match(people, /updatePerson\(values\.personId/);
  assert.match(recognize, /upsertPerson\(/);
  assert.match(queue, /for \(const entry of entries\)/);
  assert.doesNotMatch(queue, /Promise\.all\(entries\.map/);
  assert.doesNotMatch(accounts, /await load\(\);/);
});

test("full refresh is explicit and sequential", async () => {
  const appData = await read("../src/hooks/useAppData.js");
  const refresh = appData.slice(appData.indexOf("const refreshAll"), appData.indexOf("const updatePerson"));

  assert.doesNotMatch(refresh, /Promise\.all/);
  assert.match(refresh, /activeView === "people"[\s\S]*await loadPeople[\s\S]*await loadDeletedFaces/);
  assert.match(refresh, /activeView === "debug"[\s\S]*await loadEvents[\s\S]*await loadBackups/);
});

test("idle screens do not poll or reload data they already hold", async () => {
  const [appData, modelGate, recoveryGate, controller, apiClient, queue] = await Promise.all([
    read("../src/hooks/useAppData.js"),
    read("../src/components/ModelGate.jsx"),
    read("../src/components/RecoveryGate.jsx"),
    read("../src/hooks/useSentriFaceController.js"),
    read("../src/hooks/useApiClient.js"),
    read("../src/hooks/useQueueController.js"),
  ]);

  assert.doesNotMatch(appData, /setInterval/);
  assert.match(appData, /loadedViews\.current\.has\("people"\)/);
  assert.match(appData, /loadedViews\.current\.has\("debug"\)/);
  assert.doesNotMatch(modelGate, /setInterval/);
  assert.match(recoveryGate, /readiness\.ready \|\| readiness\.acknowledged/);
  assert.match(controller, /enabled: canAdd && activeView === "queue"/);
  assert.match(apiClient, /GET_REQUESTS_IN_FLIGHT/);
  assert.match(queue, /progressRequestInFlight/);
  assert.match(queue, /}, 1000\);/);
  assert.match(queue, /if \(payload\.session_closed\) removeClosedQueueSession\(confirmedSessionId\)/);
  assert.match(queue, /setQueueSessionId\(""\)/);
});

test("queue People candidates rank only when the user opens Browse People", async () => {
  const [app, queueController, queueView] = await Promise.all([
    read("../src/SentriFaceApp.jsx"),
    read("../src/hooks/useQueueController.js"),
    read("../src/views/QueueView.jsx"),
  ]);

  assert.match(app, /onLoadPeopleCandidates=\{guarded\(actions\.loadQueuePeopleCandidates\)\}/);
  assert.match(queueController, /\/api\/queue-person-candidates\?session_id=/);
  assert.match(queueView, /const openPeoplePicker = async \(\) => \{[\s\S]*if \(peopleCandidatesGroupId === group\.group_id\) return;[\s\S]*await onLoadPeopleCandidates\(group\.session_id, group\.group_id\);/);
});

test("recognition People candidates rank only when Browse People is opened", async () => {
  const [app, recognizeController, recognizeView] = await Promise.all([
    read("../src/SentriFaceApp.jsx"),
    read("../src/hooks/useRecognizeController.js"),
    read("../src/views/RecognizeView.jsx"),
  ]);

  assert.match(app, /onLoadPeopleCandidates=\{guarded\(actions\.loadRecognitionPeopleCandidates\)\}/);
  assert.match(recognizeController, /apiPost\("\/api\/recognition-person-candidates"/);
  assert.match(recognizeView, /const openPeoplePicker = async \(faceIndex\) => \{[\s\S]*if \(peopleCandidates\[faceIndex\]\) return;[\s\S]*await onLoadPeopleCandidates\(faceIndex\);/);
});

test("tab navigation cannot fail on a replaced lazy-loaded chunk", async () => {
  const app = await read("../src/SentriFaceApp.jsx");

  assert.doesNotMatch(app, /lazy\(\(\) => import\(/);
  assert.match(app, /import \{ PeopleView \} from "\.\/views\/PeopleView\.jsx"/);
  assert.match(app, /import \{ QueueView \} from "\.\/views\/QueueView\.jsx"/);
});

test("About and support uses loaded data and only calls the backend for explicit export", async () => {
  const [view, panel, appData] = await Promise.all([
    read("../src/views/DebugView.jsx"),
    read("../src/views/AboutSupportPanel.jsx"),
    read("../src/hooks/useAppData.js"),
  ]);

  assert.match(view, /About & support/);
  assert.match(panel, /profile\.application/);
  assert.match(panel, /profile\?\.hardware/);
  assert.match(panel, /buildDiagnosticReport\(profile, events\)/);
  assert.doesNotMatch(panel, /support@sentriface/);
  assert.match(panel, /Suraj Singh/);
  assert.match(panel, /sentriface-support@gmail\.com/);
  assert.match(panel, /mailto:\$\{SUPPORT_EMAIL\}/);
  assert.match(panel, /copyText\(SUPPORT_EMAIL\)/);
  assert.doesNotMatch(panel, /apiGet|apiPost|apiDownload/);
  assert.match(appData, /const downloadSupportPackage = async \(\) => \{[\s\S]*"\/api\/support-package"/);
});

test("signed-in identity aligns with a consistent header control row", async () => {
  const [app, css] = await Promise.all([
    read("../src/SentriFaceApp.jsx"),
    read("../src/sentriface-interface.css"),
  ]);

  assert.match(app, /className="header-account-trigger"/);
  assert.match(app, /className="header-utility-group"/);
  assert.match(app, /className="header-actions"/);
  assert.match(app, /accountInitials\(user\.display_name \|\| user\.username\)/);
  assert.match(css, /\.header-utility-group,\s*\.header-account-trigger\s*\{[^}]*height:\s*44px;/s);
  assert.match(app, /<Menu\.Item leftSection=\{<IconKey size=\{16\} \/>\}[^\n]*Change password<\/Menu\.Item>/);
  assert.match(app, /<Menu\.Item color="red" leftSection=\{<IconLogout size=\{16\} \/>\}[^\n]*Sign out<\/Menu\.Item>/);
});

test("active and archived people can delete an entire profile without refetching", async () => {
  const [view, controller, appData] = await Promise.all([
    read("../src/views/PeopleView.jsx"),
    read("../src/hooks/usePeopleController.js"),
    read("../src/hooks/useAppData.js"),
  ]);

  assert.match(view, /Delete entire profile/);
  assert.match(view, /managementDialog === "delete-profile"/);
  assert.match(view, /disabled=\{deleteConfirmation !== "DELETE"\}/);
  assert.match(view, /disabled=\{profileDeleteConfirmation !== "DELETE"\}/);
  assert.match(controller, /apiPost\("\/api\/person-purge"/);
  assert.match(controller, /removePersonLocally\(personId\)/);
  assert.match(appData, /setArchivedPeople\(\(current\) => current\.filter\(\(item\) => item\.person_id !== personId\)\)/);
  assert.doesNotMatch(controller, /permanentlyDeletePerson[\s\S]{0,800}(?:loadPeople|refreshAll)\(/);
});

test("activity log sorts full timestamps newest first before pagination", async () => {
  const debugView = await read("../src/views/DebugView.jsx");

  assert.match(debugView, /snapshot\.map\(normalizeEvent\)\.sort\(compareEventsNewestFirst\)/);
  assert.match(debugView, /function compareEventsNewestFirst\(left, right\)/);
  assert.match(debugView, /return rightTime - leftTime;/);
  assert.match(debugView, /return right\.sourceIndex - left\.sourceIndex;/);
  assert.match(debugView, /const pageEvents = filteredEvents\.slice/);
});

test("new-person creator is retained in local state and profile history fallback", async () => {
  const [recognize, queue, utils] = await Promise.all([
    read("../src/hooks/useRecognizeController.js"),
    read("../src/hooks/useQueueController.js"),
    read("../src/utils.js"),
  ]);

  assert.match(recognize, /added_by: recognitionFollowup\.addedBy \|\| ""/);
  assert.match(queue, /added_by: queueFollowup\.addedBy \|\| ""/);
  assert.match(utils, /metadata\.added_by \|\| creatorDetail\.added_by \|\| ""/);
});

test("a recorded People merge can be undone with one narrow backend request", async () => {
  const [view, controller] = await Promise.all([
    read("../src/views/PeopleView.jsx"),
    read("../src/hooks/usePeopleController.js"),
  ]);

  assert.match(view, /Undo merge/);
  assert.match(view, /mergeEvent\?\.result\?\.undo_supported/);
  assert.match(view, /managementDialog === "undo-merge"/);
  assert.match(controller, /apiPost\("\/api\/person-merge-undo"/);
  assert.match(controller, /upsertPerson\(result\.source_person\)/);
  assert.match(controller, /upsertPerson\(result\.target_person\)/);
  assert.doesNotMatch(controller, /undoPeopleMerge[\s\S]{0,900}(?:loadPeople|loadPerson|refreshAll)\(/);
});

test("a newly archived merge opens immediately without requiring a tab refresh", async () => {
  const [view, appData] = await Promise.all([
    read("../src/views/PeopleView.jsx"),
    read("../src/hooks/useAppData.js"),
  ]);

  assert.match(appData, /archived:\s*true,[\s\S]*deleted_at:/);
  assert.match(appData, /archived:\s*false,\s*deleted_at:\s*null/);
  assert.match(view, /const isArchived = archived \|\| Boolean\(person\.archived \|\| person\.deleted_at\)/);
});
