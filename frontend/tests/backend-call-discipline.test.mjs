import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("identity mutations invalidate authoritative People state", async () => {
  const [people, recognize, queue, appData] = await Promise.all([
    read("../src/hooks/usePeopleController.js"),
    read("../src/hooks/useRecognizeController.js"),
    read("../src/hooks/useQueueController.js"),
    read("../src/hooks/useAppData.js"),
  ]);
  assert.match(people, /await loadPeople\(\{ dedupe: false \}\)/);
  assert.match(recognize, /photo-review-complete[\s\S]*await loadPeople\(\{ dedupe: false \}\)/);
  assert.match(queue, /queue-confirm-(?:new|existing)[\s\S]*await loadPeople\(\{ dedupe: false \}\)/);
  assert.doesNotMatch(recognize, /upsertPerson|updatePerson/);
  assert.doesNotMatch(queue, /upsertPerson|updatePerson|created_at: new Date/);
  assert.doesNotMatch(appData, /archivePersonLocally|restorePersonLocally|removePersonLocally|upsertPerson/);
});

test("People read contract fails closed and retains backend collection intelligence", async () => {
  const [appData, utils] = await Promise.all([read("../src/hooks/useAppData.js"), read("../src/utils.js")]);
  assert.match(appData, /\.map\(requirePersonContract\)/);
  assert.match(appData, /statistics: payload\.statistics/);
  assert.match(appData, /sort_orders: payload\.sort_orders/);
  assert.match(utils, /\["ACTIVE", "ARCHIVED", "DELETED", "MERGED"\]\.includes\(person\.lifecycle_status\)/);
  assert.match(utils, /"canonical_person_id" in person/);
  assert.match(utils, /Array\.isArray\(person\.allowed_actions\)/);
});

test("full refresh remains explicit, sequential, and bounded by active view", async () => {
  const appData = await read("../src/hooks/useAppData.js");
  const refresh = appData.slice(appData.indexOf("const refreshAll"), appData.indexOf("const reloadAppData"));
  assert.doesNotMatch(refresh, /Promise\.all/);
  assert.match(refresh, /\["people", "recognize", "queue", "encounters"\]\.includes\(activeView\)[\s\S]*await loadPeople/);
  assert.match(refresh, /activeView === "people"[\s\S]*await loadDeletedFaces/);
  assert.match(refresh, /loadedViews\.current\.has\("people"\)/);
  assert.doesNotMatch(appData, /setInterval/);
});

test("candidate ranking remains a backend request initiated by interaction", async () => {
  const [recognize, queue] = await Promise.all([
    read("../src/hooks/useRecognizeController.js"),
    read("../src/hooks/useQueueController.js"),
  ]);
  assert.match(recognize, /apiPost\("\/api\/recognition-person-candidates"/);
  assert.match(queue, /\/api\/queue-person-candidates\?session_id=/);
});

test("profile updates use normalized metadata and authoritative reload", async () => {
  const [people, utils] = await Promise.all([read("../src/hooks/usePeopleController.js"), read("../src/utils.js")]);
  assert.match(people, /apiPost\("\/api\/person-update"/);
  assert.match(people, /await refreshPeopleProfile\(values\.personId\)/);
  assert.doesNotMatch(utils.slice(utils.indexOf("export function personProfile"), utils.indexOf("export function requirePersonContract")), /payload\.details|recognition_details/);
});
