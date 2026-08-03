import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("people grid uses compact cards without shrinking face photos", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/sentriface-interface.css", import.meta.url), "utf8");

  assert.match(view, /<Card withBorder radius="md" p="xs" className=\{cardClass\}>/);
  assert.doesNotMatch(view, /Photos available/);
  assert.match(css, /\.people-card-grid\s*\{[^}]*minmax\(176px, 1fr\)/s);
  assert.match(css, /\.image-frame--peopleCard\s*\{[^}]*height: 112px;/s);
});

test("profile and management history share the horizontal card flow", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");

  assert.match(view, /\.\.\.managementEvents\.map\(normalizeManagementChange\)/);
  assert.match(view, /historyCards\.map\(\(change, index\)/);
  assert.match(view, /change\.kind === "profile"/);
  assert.doesNotMatch(view, />Management Activity</);
});
