import { droppedImageFiles, uploadRelativePath } from "../src/utils.js";
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const queue = fs.readFileSync(new URL("../src/views/QueueView.jsx", import.meta.url), "utf8");
const controller = fs.readFileSync(new URL("../src/hooks/useQueueController.js", import.meta.url), "utf8");

test("grouping suggestions use the server-reported uploaded subfolder", () => {
  assert.match(queue, /function groupingFolder\(item\) \{\s*if \(typeof item\?\.source_folder === "string"\) return item\.source_folder;/);
  assert.doesNotMatch(queue, /groupingFolder\(item\.media_path\)/);
});

test("a failed targeted retry reloads the same Attach Media draft", () => {
  assert.match(controller, /if \(options\.targetObservationId\) \{\s*try \{ await loadQueueSessions\(options\.sessionId \|\| ""\); \}/);
});

test("dropped nested folders keep each file's subfolder for upload", async () => {
  const fileEntry = (fullPath) => ({ isFile: true, fullPath, file: (resolve) => resolve({ name: fullPath.split("/").pop() }) });
  const dirEntry = (children) => {
    let read = false;
    return { isFile: false, isDirectory: true, createReader: () => ({ readEntries: (resolve) => { resolve(read ? [] : children); read = true; } }) };
  };
  const root = dirEntry([dirEntry([fileEntry("/Trip/Day1/a.png")]), dirEntry([fileEntry("/Trip/Day2/b.png")])]);
  const files = await droppedImageFiles({ items: [{ webkitGetAsEntry: () => root }] });
  assert.deepEqual(files.map(uploadRelativePath).sort(), ["Trip/Day1/a.png", "Trip/Day2/b.png"]);
  assert.equal(uploadRelativePath({ name: "solo.png" }), "solo.png");
  assert.equal(uploadRelativePath({ name: "x.png", webkitRelativePath: "Pick/x.png" }), "Pick/x.png");
});
