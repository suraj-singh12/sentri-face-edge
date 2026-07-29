import assert from "node:assert/strict";
import test from "node:test";

import { matchDisplay, recognitionText } from "../src/utils.js";


test("identity matches are presented as similarity, not probability", () => {
  const cases = [
    ["strong", "Ada - strong similarity"],
    ["likely", "Ada - moderate similarity"],
    ["possible", "Ada - possible similarity"],
    ["weak", "Ada - weak similarity"],
  ];
  for (const [classification, expected] of cases) {
    const match = { name: "Ada", is_known: true, classification };
    assert.equal(recognitionText(match), expected);
    const display = matchDisplay(match);
    assert.match(display.badge, /Similarity/);
    assert.equal("stars" in display, false);
    assert.doesNotMatch(`${expected} ${display.badge} ${display.guidance}`, /confidence|probability|likely|maybe|\d\/5/i);
  }
});