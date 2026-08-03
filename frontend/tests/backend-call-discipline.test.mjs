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

test("tab navigation cannot fail on a replaced lazy-loaded chunk", async () => {
  const app = await read("../src/SentriFaceApp.jsx");

  assert.doesNotMatch(app, /lazy\(\(\) => import\(/);
  assert.match(app, /import \{ PeopleView \} from "\.\/views\/PeopleView\.jsx"/);
  assert.match(app, /import \{ QueueView \} from "\.\/views\/QueueView\.jsx"/);
});
