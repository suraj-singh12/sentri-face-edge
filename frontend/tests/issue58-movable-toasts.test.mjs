import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  NARROW_WIDTH,
  TOAST_POSITION_KEY,
  placeToastStack,
  readSavedToastPosition,
  toastPositionFromRect,
} from "../src/utils/toastPlacement.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
const wide = { width: 1280, height: 800 };
const memory = (value) => ({ getItem: (key) => (key === TOAST_POSITION_KEY ? value : null) });
const overlaps = (stack, height, dialog) =>
  stack.left < dialog.right && stack.left + stack.width > dialog.left && stack.top < dialog.bottom && stack.top + height > dialog.top;

test("the stack opens at the top right, below the header", () => {
  const place = placeToastStack({ viewport: wide, saved: null, stackHeight: 120 });
  assert.equal(place.left + place.width, 1280 - 16);
  assert.equal(place.top, 84);
  assert.equal(place.width, 440);
  assert.equal(place.dialog, false);
});

test("a moved position is saved as a share of the window and survives resizing", () => {
  const viewport = wide;
  const saved = toastPositionFromRect({ left: 200, top: 520, width: 440, height: 150 }, viewport);
  const back = placeToastStack({ viewport, saved, stackHeight: 150 });
  assert.ok(Math.abs(back.left - 200) < 0.5);
  assert.ok(Math.abs(back.top - 520) < 0.5);
  const smaller = placeToastStack({ viewport: { width: 900, height: 600 }, saved, stackHeight: 150 });
  assert.ok(smaller.left >= 16 && smaller.left + smaller.width <= 900 - 16);
  assert.ok(smaller.top >= 8 && smaller.top + 150 <= 600 - 8);
});

test("unreadable or missing saved positions fall back to the default", () => {
  assert.equal(readSavedToastPosition(memory(null)), null);
  assert.equal(readSavedToastPosition(memory("not json")), null);
  assert.equal(readSavedToastPosition(memory('{"x":"a","y":1}')), null);
  assert.deepEqual(readSavedToastPosition(memory('{"x":4,"y":-1}')), { x: 1, y: 0 });
});

test("the stack never overlaps an open dialog when there is room", () => {
  const dialog = { left: 420, right: 860, top: 216, bottom: 580 };
  const home = placeToastStack({ viewport: wide, saved: null, stackHeight: 300, dialogs: [dialog] });
  assert.equal(home.dialog, true);
  assert.ok(!overlaps(home, 300, dialog));

  const saved = toastPositionFromRect({ left: 420, top: 260, width: 440, height: 200 }, wide);
  const moved = placeToastStack({ viewport: wide, saved, stackHeight: 200, dialogs: [dialog] });
  assert.ok(!overlaps(moved, 200, dialog));

  const wideDialog = { left: 100, right: 1180, top: 300, bottom: 560 };
  const above = placeToastStack({ viewport: wide, saved: toastPositionFromRect({ left: 500, top: 380, width: 440, height: 120 }, wide), stackHeight: 120, dialogs: [wideDialog] });
  assert.ok(!overlaps(above, 120, wideDialog));
});

test("with no free space the stack stays put and the dialog is drawn above it", async () => {
  const dialog = { left: 0, right: 1280, top: 0, bottom: 800 };
  const place = placeToastStack({ viewport: wide, saved: null, stackHeight: 120, dialogs: [dialog] });
  assert.equal(place.top, 84);
  assert.equal(place.dialog, true);
  const [css, stack] = await Promise.all([read("../src/sentriface-interface.css"), read("../src/components/ToastStack.jsx")]);
  assert.match(css, /\.mantine-Modal-overlay \{\s*z-index: calc\(var\(--overlay-z-index, 200\) - 1\) !important;/);
  assert.match(stack, /zIndex=\{TOAST_Z_INDEX\}/);
});

test("narrow windows use the full width and move only up and down", () => {
  const narrow = { width: 390, height: 844 };
  assert.ok(narrow.width < NARROW_WIDTH);
  const saved = { x: 0, y: 0.7 };
  const place = placeToastStack({ viewport: narrow, saved, stackHeight: 140 });
  assert.equal(place.narrow, true);
  assert.equal(place.left, 16);
  assert.equal(place.width, 390 - 32);
  assert.ok(Math.abs(place.top - (0.7 * 844 - 140)) < 0.5);
});

test("operators drag the toast itself and reset beside the close button", async () => {
  const [stack, client, app] = await Promise.all([
    read("../src/components/ToastStack.jsx"),
    read("../src/hooks/useApiClient.js"),
    read("../src/SentriFaceApp.jsx"),
  ]);
  assert.match(app, /<ToastStack \/>/);
  assert.doesNotMatch(app, /<Notifications /);
  assert.match(stack, /allowDragDismiss=\{false\}/);
  assert.match(stack, /position="top-right"/);
  assert.match(stack, /\.mantine-Notification-root`\)/);
  assert.match(stack, /closest\("button, a, input, textarea, select"\)/);
  assert.match(stack, /if \(state\.narrow && saved\) next\.x = saved\.x;/);
  assert.match(stack, /aria-label="Move messages back to the top right"/);
  assert.match(stack, /window\.localStorage\.removeItem\(TOAST_POSITION_KEY\)/);
  assert.match(stack, /moved: Boolean\(saved\) && !placement\?\.dialog/);
  assert.doesNotMatch(stack, /tabIndex|onKeyDown|role="/);
  assert.match(client, /message: createElement\(ToastContent, null, message\)/);
});

test("toasts use only the approved colors, with yellow shown as orange", async () => {
  const client = await read("../src/hooks/useApiClient.js");
  assert.match(client, /const TOAST_COLORS = \{ red: "red", orange: "orange", yellow: "orange", teal: "teal", gray: "gray" \};/);
  assert.match(client, /color: TOAST_COLORS\[color\] \|\| "gray"/);
  assert.match(client, /autoClose: options\.autoClose \?\? 4500/);
});
