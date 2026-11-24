import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("shared confirmation never closes from outside and locks while running", async () => {
  const dialog = await read("../src/components/ConfirmDialog.jsx");
  assert.match(dialog, /closeOnClickOutside=\{false\}/);
  assert.match(dialog, /closeOnEscape=\{!locked\}/);
  assert.match(dialog, /closeButtonProps=\{\{ disabled: locked/);
  assert.match(dialog, /const matched = !typed \|\| typedValue === typed;/);
  assert.match(dialog, /if \(!canConfirm \|\| runningRef\.current\) return;/);
  assert.match(dialog, /<form onSubmit=\{submit\}/);
  assert.match(dialog, /error \? "Try again" : actionLabel/);
  assert.match(dialog, /failure\?\.code === "request_timeout"/);
  assert.match(dialog, /CONFIRM_TONE_COLORS = \{ danger: "red", caution: "orange", safe: "teal" \}/);
});

test("backup deletion uses the shared dialog instead of a browser prompt", async () => {
  const [appData, app] = await Promise.all([read("../src/hooks/useAppData.js"), read("../src/SentriFaceApp.jsx")]);
  assert.doesNotMatch(appData, /window\.prompt/);
  assert.match(appData, /new URLSearchParams\(\{ confirm: backupId \}\)/);
  assert.match(app, /opened=\{Boolean\(state\.backupDeleteTarget\)\}[\s\S]*typed="DELETE"/);
  assert.match(app, /This is your only verified backup\. Without it, you can't restore\./);
  assert.match(app, /onDeleteBackup=\{actions\.requestDeleteBackup\}/);
});

test("queue discard and Cancel Attach Media confirm first and let failures reach the dialog", async () => {
  const [queue, app] = await Promise.all([read("../src/views/QueueView.jsx"), read("../src/SentriFaceApp.jsx")]);
  assert.match(queue, /onClick=\{\(\) => setCancelAttachmentOpen\(true\)\}>Cancel Attach Media/);
  assert.match(queue, /cancelLabel="Keep draft"/);
  assert.match(app, /onCancelAttachment=\{actions\.cancelQueueAttachment\}/);
  assert.match(app, /onDiscardSession=\{actions\.discardQueueSession\}/);
});
