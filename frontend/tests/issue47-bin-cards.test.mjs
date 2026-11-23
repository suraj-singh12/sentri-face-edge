import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const people = fs.readFileSync(new URL("../src/views/PeopleView.jsx", import.meta.url), "utf8");

test("Bin cards have no favorite star", () => {
  assert.match(people, /\{isBinned\(person\) \? null : <ActionIcon[\s\S]*?className="people-card-star"/);
});

test("the Archived collection is titled Archived", () => {
  assert.match(people, /filter === "bin" \? "Bin" : filter === "archived" \? "Archived" : "People"/);
});
