import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { backupLabel } from "../src/utils.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("backup rows name what made the backup instead of raw reasons", () => {
  assert.equal(backupLabel({ reason: null }), "Manual backup");
  assert.equal(backupLabel({ reason: null, imported_from_backup_id: "x" }), "Imported backup");
  assert.equal(backupLabel({ reason: "before-person-delete-1a2b" }), "Safety copy before deleting a person");
  assert.equal(backupLabel({ reason: "before-face-permanent-delete-9" }), "Safety copy before erasing a face");
  assert.equal(backupLabel({ reason: "before-face-delete-9" }), "Safety copy before removing a face");
  assert.equal(backupLabel({ reason: "before-schema-migration-v35" }), "Safety copy before upgrading SentriFace data");
  assert.equal(backupLabel({ reason: "automatic-recovery" }), "First recovery backup");
  assert.equal(backupLabel({ reason: "something-new" }), "Backup");
});

test("duplicate import warns first and only Import anyway allows the second copy", async () => {
  const [appData, app, debug] = await Promise.all([
    read("../src/hooks/useAppData.js"),
    read("../src/SentriFaceApp.jsx"),
    read("../src/views/DebugView.jsx"),
  ]);
  assert.match(appData, /if \(error\.code === "backup_already_present"\) \{\s*setDuplicateImport/);
  assert.match(appData, /query\.set\("allow_duplicate", "1"\)/);
  assert.match(appData, /query\.set\("approved_removals", approvedRemovals\.join\(","\)\)/);
  assert.match(appData, /approvedRemovals: retentionRemoves\.map\(\(backup\) => backup\.backup_id\)/);
  assert.match(app, /This backup is already in the list/);
  assert.match(app, />Import anyway</);
  assert.match(app, /retentionRemoves\?\.length[\s\S]*SentriFace keeps up to/);
  assert.doesNotMatch(debug, /<Text size="xs" c="dimmed">\{backup\.backup_id\}<\/Text>/);
  assert.match(debug, /Copy reference for support/);
});

test("rename conflicts stay under the Name field and World later pages link back", async () => {
  const [people, peopleView, world] = await Promise.all([
    read("../src/hooks/usePeopleController.js"),
    read("../src/views/PeopleView.jsx"),
    read("../src/views/WorldView.jsx"),
  ]);
  assert.match(people, /error\.reason !== "placeholder_name_taken"/);
  assert.match(peopleView, /error\?\.reason === "placeholder_name_taken"[\s\S]*Nothing was saved\./);
  assert.match(world, /state\.pageNumber > 1 && !page\.returned_count/);
  assert.match(world, /Back to first page/);
});
