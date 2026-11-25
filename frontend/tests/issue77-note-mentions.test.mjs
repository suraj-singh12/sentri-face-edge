import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { noteMentionIdsForContent } from "../src/utils.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("empty notes carry no selected mention ids", () => {
  assert.deepEqual(noteMentionIdsForContent("", ["person-a"]), []);
  assert.deepEqual(noteMentionIdsForContent("   \n", ["person-a"]), []);
  assert.deepEqual(noteMentionIdsForContent("A replacement note", ["person-a", "person-a", "person-b"]), ["person-a", "person-b"]);
});

test("note editor exposes selected mentions and sends the emptied-note removal", async () => {
  const view = await read("../src/views/PeopleView.jsx");
  assert.match(view, /Selected mentions/);
  assert.match(view, /Remove mention \$\{person\.name\}/);
  assert.match(view, /noteMentionIdsForContent\(notesDraft, selectedNoteMentionIds\)/);
  assert.match(view, /noteMentionDirectory/);
  assert.match(view, /mention\.raw_person_id/);
  assert.match(view, /payload\.person\.person_id, notesDraft, previousNotes, effectiveMentionIds/);
});
