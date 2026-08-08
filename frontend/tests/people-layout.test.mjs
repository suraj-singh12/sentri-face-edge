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
  assert.match(controller, /apiPost\("\/api\/person-placeholder"/);
});

test("person profiles provide explicit @ association linking and safe removal", async () => {
  const view = await readFile(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");
  const controller = await readFile(new URL("../src/hooks/usePeopleController.js", import.meta.url), "utf8");

  assert.match(view, /<Tabs\.Tab value="associations">Associations \(\{associations\.length\}\)<\/Tabs\.Tab>/);
  assert.match(view, /placeholder="@Name"/);
  assert.match(view, />\s*Link person\s*</);
  assert.match(view, /Create placeholder “\{searchText\}”/);
  assert.match(view, /Matching people are already linked or refer to this profile\./);
  assert.match(view, /This removes only the association\. Neither person nor their photos, biometric data, or history will be deleted\./);
  assert.match(view, /onOpen\(association\.person\.person_id, \{ archived: Boolean\(association\.person\.archived\) \}\)/);
  assert.match(controller, /apiPost\("\/api\/person-association"/);
  assert.match(controller, /apiPost\("\/api\/person-association-placeholder"/);
  assert.match(controller, /apiPost\("\/api\/person-association-remove"/);
});
