import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const app = read("../src/SentriFaceApp.jsx");
const hook = read("../src/hooks/useLicenseController.js");
const panel = read("../src/views/LicensePanel.jsx");
const debug = read("../src/views/DebugView.jsx");

test("license UI uses only server status and signed token activation", () => {
  assert.match(hook, /apiGet\("\/api\/license\/status"/);
  assert.match(hook, /apiPost\("\/api\/license\/activate", \{ token \}/);
  assert.doesNotMatch(hook + panel, /license_id\s*:/);
  assert.doesNotMatch(hook + panel, /machine\s*:/);
  assert.doesNotMatch(hook + panel, /key_id\s*:/);
});

test("unlicensed mode renders a recovery shell rather than a startup gate", () => {
  assert.match(app, /licenseRestricted \? \["debug"\] : VIEWS/);
  assert.match(app, /Backup.*restore.*integrity recovery.*support remain available/s);
  assert.match(debug, /License & activation/);
  assert.match(debug, /Backups & restore/);
  assert.match(debug, /Integrity & recovery/);
  assert.doesNotMatch(app, /if \(licenseRestricted\) return/);
});

test("frontend activation is capability gated and never displays stored token", () => {
  assert.match(debug, /capabilitySet\.has\("license_administer"\)/);
  assert.match(panel, /canActivate/);
  assert.doesNotMatch(panel, /status\?\.token|license\.token/);
});
