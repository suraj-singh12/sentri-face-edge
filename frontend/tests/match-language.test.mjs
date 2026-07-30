import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { matchDisplay, recognitionText } from "../src/utils.js";


test("identity matches use calibrated plain-language tiers without numeric scores", () => {
  const cases = [
    ["strong", "Ada - Strong Match", "Strong Match"],
    ["likely", "Ada - Likely Match", "Likely Match"],
    ["possible", "Ada - Maybe Match", "Maybe Match"],
    ["weak", "Ada - No Match", "No Match"],
  ];
  for (const [classification, expected, badge] of cases) {
    const match = { name: "Ada", is_known: true, classification };
    assert.equal(recognitionText(match), expected);
    const display = matchDisplay(match);
    assert.equal(display.badge, badge);
    assert.equal("stars" in display, false);
    assert.doesNotMatch(`${expected} ${display.badge} ${display.guidance}`, /confidence|probability|\d+\.\d+|\d\/5/i);
  }
});

test("user-facing recognition screens do not render raw similarity numbers", () => {
  const shared = fs.readFileSync(new URL("../src/components/Shared.jsx", import.meta.url), "utf8");
  const queue = fs.readFileSync(new URL("../src/views/QueueView.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(shared, /score\.toFixed|similarity score|Cosine similarity/i);
  assert.doesNotMatch(queue, /score\.toFixed|similarity \{/i);
});