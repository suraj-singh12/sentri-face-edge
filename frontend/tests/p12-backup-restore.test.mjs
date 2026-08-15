import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("P12 restore eligibility remains backend-owned and sends only bounded intent", async () => {
  const [appData, debugView] = await Promise.all([
    read("../src/hooks/useAppData.js"),
    read("../src/views/DebugView.jsx"),
  ]);
  const restoreFlow = appData.slice(
    appData.indexOf("const requestRestoreBackup"),
    appData.indexOf("  return {", appData.indexOf("const requestRestoreBackup")),
  );
  assert.match(restoreFlow, /backup\?\.restorable/);
  assert.match(restoreFlow, /backup_id: backup\.backup_id/);
  assert.match(restoreFlow, /operation_id: crypto\.randomUUID\(\)/);
  assert.doesNotMatch(restoreFlow, /allow_incomplete|actor:|table:|column:|sql:/i);
  assert.match(debugView, /!backup\.restorable/);
});
