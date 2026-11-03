# SentriFace Edge — source development

## Linux explicit source ONNX and recovery

`./run.sh models` and `./run.sh onnx` use the existing isolated source authority selected by `SENTRIFACE_DEV_DATA_DIR`. Linux source ONNX admission remains explicit, Git-checkout only, unpackaged/uncompiled, and loopback-only. Real SCRFD/ArcFace models, calibration and downstream encrypted SQLCipher/storage are unchanged; no systemd path or unavailable-vault fallback is introduced.

The Linux source master key and recovery code persist under that authority with owner-only custody. Recovery-code custody is a separate authority-bound AES-GCM protected file (`.sentriface-linux-source-recovery`), encrypted with the authority's existing master key. It is excluded from backup media closure; the normal external recovery kit remains required. Missing configured, corrupt, wrong-authority or unsafe custody fails closed. A normal fresh source root gets independent random key material; a root deliberately initialized by a verified recovery kit adopts the original key identity required by portable backup validation.

For fresh-authority recovery, prepare verified models without first starting a new encrypted authority, then run `./run.sh onnx --recover-kit /local/path/sentriface-recovery-kit.json` with the isolated root selected. Enter the supported recovery code at the prompt, authenticate through the normal product flow, import the encrypted backup and restore normally. An existing incompatible authority/key is never silently overwritten. macOS/Windows OS-vault recovery and packaged/hardened custody are unchanged. Development reset removes only its intended source authority, including these custody records; external kits/exports and unrelated authorities are unaffected.

## macOS

Use this workflow to run SentriFace Edge directly from a Git checkout. Install
Python 3.12 first. Git is required to obtain the repository. The
launcher creates and maintains the repository-local `.venv312`; it does not
install Python or modify a global Python environment.

### Synthetic development

Start the no-model synthetic runtime:

```bash
./run.sh
```

The explicit equivalent is:

```bash
./run.sh dev
```

Use synthetic mode for UI, account, workflow, backup, recovery, and domain
development. Face results are deliberately synthetic, and no ONNX model files
are needed. Open `http://127.0.0.1:8765` and stop the server with `Control-C`.
The zero-argument command starts the same mode as `./run.sh dev` without an
argument-parsing warning. Use `./run.sh dev --port PORT` if the default port is
already occupied.

### Real ONNX development

Use ONNX mode when validating the actual local detector and recognizer stack.
On first use, either start `./run.sh onnx`, sign in, and complete Model Setup,
or install an operator-supplied local pair with SHA-256 declarations. For the
currently present repository model files:

```bash
DETECTOR="$PWD/models/det_500m.onnx"
RECOGNIZER="$PWD/models/w600k_r50.onnx"

./run.sh models \
  --detector-source "$DETECTOR" \
  --detector-sha256 "$(shasum -a 256 "$DETECTOR" | awk '{print $1}')" \
  --recognizer-source "$RECOGNIZER" \
  --recognizer-sha256 "$(shasum -a 256 "$RECOGNIZER" | awk '{print $1}')" \
  --usage-basis noncommercial-research \
  --authorized-by "$USER" \
  --accept-model-responsibility
```

Then start the real runtime:

```bash
./run.sh onnx
```

Model onboarding copies and verifies local operator-supplied files into the
development model authority. It does not download weights or bypass model
validation, calibration, or usage declarations. Source ONNX mode retains the
loopback listener and application socket guard, but does not have the packaged
macOS App Sandbox boundary.

### Data, frontend, and reset

Development data lives at:

```text
~/Library/Application Support/SentriFace-Dev
```

It contains a separate database, Keychain identity, logs, backups, media, and
model authority. Installed-product data remains separate at:

```text
~/Library/Application Support/SentriFace
```

The launcher refuses to use the installed-product location. To intentionally
remove only the default development authority, run:

```bash
./run.sh reset
```

It displays the target path and requires the exact confirmation `RESET-DEV`.
If `SENTRIFACE_DEV_DATA_DIR` is set to a custom development location, normal
launches use it, but `reset` refuses it so that it cannot remove an unverified
path. Reset removes the complete default development authority, including
read-only model bundles created during onboarding and the exact development
storage and recovery Keychain identities. It restores owner permissions as
needed, never follows symlinks, refuses paths owned by another user or mounted
inside the authority, and does not use `sudo`. The installed-product directory
and its Keychain identities are outside the reset scope.

If file removal fails, the database key remains in Keychain so the existing
encrypted database is still readable. If Keychain cleanup fails after file
removal, rerun `./run.sh reset` to finish credential cleanup. A successful
reset followed by `./run.sh` starts with no prior development accounts,
database, media, or model authority. The repository source, `.venv312`, and
external ONNX source files are not part of development data and remain in place.
Use the existing `--yes` option only in a controlled disposable test setup.

Normal source launches use the existing compiled frontend and do not require
Node.js. When editing frontend source, use:

```bash
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

If the launcher reports an incomplete `.venv312`, remove that virtual
environment and rerun `./run.sh`. If Python 3.12 is unavailable,
install it and rerun. A second process using the same development data root is
refused; stop the first process with `Control-C` before launching again.

## Windows

Use this workflow from a Windows 11 AMD64 checkout. Install 64-bit AMD64 Python
3.12 first. The launcher creates and maintains repository-local
`.venv312`; it neither installs Python nor modifies global Python packages. The
normal source launch uses the already-built frontend and does not require Node.

### Synthetic development

Start the no-model runtime from PowerShell:

```powershell
.\run.ps1
```

The explicit equivalent is `.\run.ps1 dev`. Open
`http://127.0.0.1:8765`, create the first local administrator when needed, and
stop the server with `Control-C`. Synthetic mode supports accounts, UI and
navigation, Queue/People/Person Graph/World workflow structure, notes, backups,
recovery, and normal domain behavior without ONNX weights. Recognition results
are deliberately synthetic.

If local PowerShell policy blocks repository scripts, use the process-scoped
fallback; it does not change machine or user execution policy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

### Real ONNX development

Onboard the operator-supplied local pair with exact SHA-256 declarations. This
copies the files into development model authority and preserves P13 immutable
candidate, usage declaration, calibration, activation, and rollback semantics:

```powershell
$detector = (Resolve-Path .\models\det_500m.onnx).Path
$recognizer = (Resolve-Path .\models\w600k_r50.onnx).Path
$calibration = (Resolve-Path .\models\calibration-w600k_r50.json).Path

.\run.ps1 models `
  --detector-source $detector `
  --detector-sha256 (Get-FileHash $detector -Algorithm SHA256).Hash `
  --recognizer-source $recognizer `
  --recognizer-sha256 (Get-FileHash $recognizer -Algorithm SHA256).Hash `
  --calibration-source $calibration `
  --calibration-sha256 (Get-FileHash $calibration -Algorithm SHA256).Hash `
  --usage-basis noncommercial-research `
  --authorized-by $env:USERNAME `
  --accept-model-responsibility
```

Use only a usage basis and calibration appropriate to the supplied models. Then
start real CPU inference:

```powershell
.\run.ps1 onnx
```

Source ONNX mode retains loopback binding and the in-process outbound socket
guard. It explicitly warns that a Git checkout does not have the packaged
exact-executable Windows Firewall boundary; packaged ONNX mode remains
fail-closed on that OS policy.

### Data isolation and reset

Windows source data lives exactly at:

```text
%LOCALAPPDATA%\SentriFace-Dev
```

It has a separate SQLCipher database, path-derived Credential Manager identity,
logs, backups, protected media, model authority, uploads, receipts, and lock.
Installed-product authority remains `%LOCALAPPDATA%\SentriFace`. The launcher
refuses a development override that equals, contains, or is contained by the
product path.

To remove only the default development authority:

```powershell
.\run.ps1 reset
```

The command displays the exact target and requires `RESET-DEV`. It refuses
custom roots and reparse points, removes only the exact hashed development
storage/recovery vault identities, verifies their deletion, and then removes
the development files. `--yes` is reserved for controlled automation.

### Frontend development

Node is needed only for frontend dependency, test, and build work:

```powershell
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

### Troubleshooting

- An incomplete `.venv312` is refused. Remove only that repository-local
  directory, then launch again.
- Install a supported 64-bit AMD64 Python 3.12 if no Python 3.12 candidate is
  found; the launcher will not install Python automatically.
- `Another SentriFace process already owns this data store` means the first
  source process is still running or did not finish shutting down. Stop it and
  retry; do not delete the lock while a process is live.
- A model checksum, declaration, calibration, or compatibility failure is a P13
  refusal. Correct the local inputs and onboard them again; do not copy loose
  files around model authority.
- A production-path refusal is intentional. Do not work around it with an
  environment alias, junction, or nested directory.

## QA Foundation #17

### Fresh macOS VM setup

Use Python **3.12** (the package rejects 3.11) and a Node version allowed by
`frontend/package.json`; CI uses Node 22. Inspect existing tools before installing
anything. A managed environment may already provide working Git, Python and Node
outside `PATH`; use those explicit executable paths when available. On a bare Mac,
`xcode-select --install` supplies Git, but requires operator interaction and may be
unavailable from Apple's update server. Do not repeatedly retry that failure or
disable security controls. Install Python from python.org's signed macOS installer
and Node from nodejs.org only if needed. Verify the Python installer with
`pkgutil --check-signature` and the Node archive against the vendor's
`SHASUMS256.txt`; a Node archive can be extracted locally without administrator
access. Homebrew is not required.

With the selected Git/Node tools on `PATH`, and `python3.12` pointing to the
selected supported interpreter:

```bash
git clone --branch qa/issue-17-foundation --single-branch https://github.com/suraj-singh12/sentri-face-edge.git
cd sentri-face-edge
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -e ".[test,qa]"
python -m playwright install chromium
npm --prefix frontend ci
```

Keep the normal logged-in macOS Keychain available; permit any OS vault prompts
through the ordinary operator flow. On a small VM, run backend and browser suites
sequentially to avoid resource contention. No system Python changes or global pip
installation are needed. The real QA command below uses the existing built UI.

### Journey and local assets

The 21-area inventory remains `tests/qa_coverage.json`. On 2026-10-29, the macOS
26.0 arm64 VM passed two fresh real QA-J01 runs at final revision `b81d451`, using
operator-authorized InsightFace SCRFD-500MF/ArcFace R50 models and an
operator-reviewed Scarlett Johansson enrollment/query pair from Commons.
Both runs verified independent People/Events/World results, rejected deliberately
incorrect location truth, verified persistence after source restart, and completed
disposable data/vault cleanup; [all five final-SHA CI jobs passed](https://github.com/suraj-singh12/sentri-face-edge/actions/runs/40905213311). This is [PR #23](https://github.com/suraj-singh12/sentri-face-edge/pull/23), merged as `6a9ec82` after final-head `6eda54a` passed all five CI jobs. Private SHA-bound JSON/JUnit, traces, model hashes
and photo hashes remain in local `qa-fixtures/runs/`; no biometric assets are
published. The first real attempt exposed a QA modal-refresh race, fixed by waiting
for the Reference UI to finish refreshing before closing it.
QA-J01 now implements source launch, UI owner/Person creation, Reference enrollment,
query inference, permitted operator confirmation, Encounter completion, independent
People/Events/World reads, an intentional wrong-location negative control, and
restart verification. It runs **twice with fresh isolated data** by default.

Install the optional browser dependency in your existing source environment:

```bash
python -m pip install -e ".[test,qa]"
python -m playwright install chromium
```

The single journey command is:

```bash
python scripts/qa_foundation.py --disposable --fixtures qa-fixtures/marvel-actors --actor "Scarlett Johansson" --models-config qa-fixtures/models.json
```

Use `--chromium /path/to/chromium` for an already installed browser, `--headed`
for visible execution, or `--repeat 1` for one diagnostic run. `--date` and
`--location` select independent QA scenario truth (default 2026-10-29 / QA London),
not a claim about when the source photograph was taken. The command never accepts
an existing database/data root or a remote application URL. `--disposable` explicitly
selects a randomly created temporary authority. It uses the same source entry point
as run.sh/run.ps1, normal authentication and model admission; it never edits SQL or
copies user credentials. Temporary authorities are removed after success or failure;
macOS/Windows QA-specific vault entries are removed only after the data is gone.
OS vault prompts must be permitted normally. Platform acceptance remains separate.

Place a **local operator declaration** at `qa-fixtures/models.json`, for example:

```json
{
  "detector_source": "/authorized/local/det_500m.onnx",
  "detector_sha256": "REPLACE_WITH_EXACT_SHA256",
  "recognizer_source": "/authorized/local/w600k_r50.onnx",
  "recognizer_sha256": "REPLACE_WITH_EXACT_SHA256",
  "usage_basis": "noncommercial-research",
  "authorized_by": "REPLACE_WITH_AUTHORIZED_OPERATOR",
  "accept_model_responsibility": true
}
```

Choose the actual authorized usage basis; commercial-license/permissive-license
inputs also need the licensor/license_reference or license_name fields required
by normal `sentriface.model_setup`. Optional calibration_source/calibration_sha256
are passed through unchanged. Relative source paths resolve beside the declaration.
QA does not obtain model weights or grant model rights. Model admission and real
runtime readiness must succeed; a synthetic runtime cannot satisfy attestation.
Model status and the normal local bundle authority bind runtime hashes to inputs.

Use the existing Commons collector when your network permits it:

```bash
python scripts/fetch_marvel_photos.py --per-actor 8
python scripts/fetch_marvel_photos.py --verify
python scripts/fetch_marvel_photos.py --restore
```

The earlier implementation environment received proxy HTTP 403 from both Commons
hosts; the macOS VM could reach both on 2026-10-29 and download candidates with the
existing collector. Search labels still require review: `Chris Evans` also returns
UK Parliament namesake portraits, and different crops can share one original photo.
Never treat different filenames or hashes as proof of distinct photographic scenes.
A practical alternative when downloads are unavailable is operator-provided licensed local photos:
place them at `qa-fixtures/marvel-actors/actor/enrollment.jpg` and `actor/query.jpg`,
and save a version-1 `manifest.json` using the same downloader schema. Each record
needs `id`, `actor`, `file` (two safe path components), pinned `sha256`, `author`,
`license`, a source `page` URL **or** `source_record` identifying the local permission/
archive record, `reviewed: true`, `reviewer`, descriptive `review_notes`, and `split`
(`enrollment` or `query`). Public sources should retain source URL, license URL and
attribution/credit. An enrollment record also requires `reference_no_context: true`:
visually verify a cropped single-face image with no reliable Encounter context.
The query must be a different genuine photograph of the same verified actor.

Calculate hashes with `python -c "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('LOCAL_PHOTO').read_bytes()).hexdigest())"`.
Never infer identity from search results alone. Review identity, real photographic
content (no drawing/CGI), visible faces, pose, expression, lighting, age and quality.
The runner validates decoded images, provenance, reviewed status and distinct hashes;
it cannot replace visual identity verification. Local images are restored from the
operator's own archive; remote `--restore` is for saved downloadable sources only.
Keep the complete manifest and asset archive together outside Git. The initial
implementation lacked assets; the macOS acceptance run used the authorized local
pair described above. Other downloaded candidates remain unreviewed.

Exit codes are 0/PASS, 1/FAIL and 2/BLOCKED. Missing assets, rejected model admission,
an unavailable browser, or unsuitable recognition fixtures cannot report PASS.
Wrong recognized identity or durable domain disagreement reports FAIL. A low-quality
or unknown recognition result reports BLOCKED with the actual inference retained,
not an operator-forced match. Before finalization, the test also checks that proposals
and Reference Only created no occurrences. One confirmed actor creates one Encounter,
one media occurrence and one World frequent-seen support record; no pair relationship
is expected for a single participant. The `/api/encounters` projection backs the Events
UI; `/api/events` is the transient diagnostic log, not historical occurrence authority.

Local evidence is under ignored `qa-fixtures/runs/<run-id>/`: JSON/JUnit, separate
run traces/screenshots, admission/application logs, exact commit/dirty state,
model and fixture hashes, inference timings, expected/actual fields, precise failure
step and negative-control mismatch. Successful execution verifies the saved media
bytes and reads again after restarting the actual application. Traces can contain
photos and session data: **never upload this directory to public CI/artifacts**.
A real PASS is not claimed until the journey executes with genuine assets; green
mechanism tests do not establish biometric acceptance. #22 is unchanged.

Run the offline machinery tests with existing pytest:

```bash
python -m pytest -q tests/test_marvel_photo_fetcher.py tests/test_qa_foundation.py tests/test_qa_journey.py
```

The two optional actual-browser mechanism checks (no biometric inference) run when
`SENTRIFACE_QA_CHROMIUM` names an installed browser. They exercise actual UI Person
creation and normal source startup/restart, and verify that missing models/synthetic
runtime are rejected. For example on Linux:

```bash
SENTRIFACE_QA_CHROMIUM=/usr/bin/chromium python -m pytest -q tests/test_qa_journey.py
```

To observe an intentionally failing expected-result comparison directly (exit 1):

```bash
python -c "import sys; sys.path.insert(0, 'scripts'); from qa_foundation import assert_expected; assert_expected({'participants':['person-b']}, {'participants':['person-a']})"
```

Expected diagnostic: `result.participants[0]: expected 'person-b', actual 'person-a'`.
The real journey separately applies deliberately wrong location truth to the same
persisted-read verifier and requires that precise mismatch before reporting PASS.

### CI summaries and repeatable reporting (#18)

Open a PR's **Checks → CI and Windows packaging → run Summary**. Each of the
existing five jobs writes a compact native GitHub summary: outcome, platform,
executed test pass/fail/skip totals, recorded command duration and exact **checked-out**
SHA. A PR checkout normally tests GitHub's merge commit; that SHA can differ from
the PR head. Packaging runs nested backend/frontend regressions inside `build_release.ps1`;
separate structured totals are unavailable, so open its build-step log for those results.
The summary shows at most three distinct failure groups. All failures, test IDs,
source declarations, coverage IDs and stage exit codes are in the job's
`qa-<check>-<OS>` artifact (`report.json`, schema version 1; `summary.md`).

Read the failure category before interpreting impact:

- **test/product behavior:** an executed assertion failed; this alone does not
  establish a product defect or root cause.
- **environment/setup:** dependency installation or toolchain preparation failed.
- **test infrastructure:** JUnit or a Node hook reports a harness/fixture error.
- **unknown:** evidence cannot establish the category; investigate the failed step.
- **BLOCKED/skipped:** execution was unavailable or not meaningful. Skips never
  count as passes. Cancellation is always **CANCELLED**, even with partial passes.

Backend results use pytest JUnit. Frontend results use a small serializer of
Node 22's native test events alongside its normal console reporter, in one suite
execution with no dependency. Node 22's built-in JUnit reporter omits parent-test
assertions after nested children; native events retain those failures and count
all tests (including parents), while skips/todos remain separate.

The first explanation names the actual source-verified test and location where
available, a safe error/comparison, curated coverage purpose when applicable,
and one investigation step. Numeric comparisons without explicit expected/actual
labels retain their original operand order. Unknown impact requires investigation.
Only identical raw failure signatures at the same source location are grouped;
all group members remain in JSON. Multiple subtest/teardown diagnostics within
one JUnit testcase are all retained, with a diagnostic index; totals count the
failed testcase once. Dynamic/unverified test names or parameter
values are withheld, with an availability indicator; use the original JUnit/test
output in the failing step log to identify those cases. Source lines point to test
declarations, not guessed assertion locations.

For deeper evidence, expand the failed step log. Backend reproduction:
`python -m pytest -q tests/test_example.py::test_name` (replace with the reported
ID); frontend: `npm --prefix frontend test`; build: `npm --prefix frontend run build`;
Windows packaging: `powershell -NoProfile -File .\build_release.ps1` on a prepared
Windows machine. Use the reported SHA and the same Python 3.12 / Node 22 toolchain.
Packaging failures also identify the last failing literal `Invoke-Checked` stage
from `build_release.ps1`, with its verified source declaration. Other build text
stays in the existing step logs. The Windows packaging job also publishes the separately named `SentriFaceEdge-Windows-x64-unsigned-engineering-candidate` artifact after the release inspection and checksum verification succeed. Download it from the Actions run artifacts. It contains only the installer, its `.sha256` file and a minimal manifest linking the installer hash to the tested commit. The release build regenerates frontend assets; the manifest records whether those generated tracked files changed. Other source changes prevent publication. From the extracted directory, run `sha256sum -c SentriFaceEdge-2.0.0-x64-unsigned-pretag-rc.exe.sha256` (or compare `Get-FileHash -Algorithm SHA256 <installer>` with that file in PowerShell). It is an unsigned engineering candidate, not a signed production release or model-acceptance claim. Artifacts expire after seven days; private QA fixtures, logs and traces are not uploaded.

Public artifacts expire after **7 days**. The reporter never copies arbitrary
JUnit text, assertion objects, environment variables, application logs, absolute
paths, model hashes, photos, model weights, licenses, credentials, storage or
private Playwright traces. Public diagnostics allow only source-declared test
names/locations, curated coverage metadata, known error classes and bounded
numeric/bool/null comparisons. Other details are explicitly withheld. Raw JUnit and Node event JSON
are **not uploaded**. Original CI command logs still use GitHub's existing log
access/retention; keep real operator data out of public CI. Command exit codes
are preserved, summaries run with `always()`, and reporter failure emits a minimal
fallback and fails its step. If the runner is forcibly terminated, a summary or
artifact may be unavailable. No extra aggregator or permissions are required. Status is a snapshot at publication:
GitHub can fail/cancel a job during later action cleanup, after reporting ran. The
final job conclusion in Checks takes precedence, including later cancellation;
this report cannot predict post-job outcomes. This boundary was observed during
a real concurrency cancellation in #18 verification.

Longer QA remains local on an authorized machine. Reuse the Foundation setup and
reviewed fixtures/model declaration above, then run (PowerShell or bash):

```text
python scripts/qa_foundation.py --expected-sha FULL_40_CHARACTER_HEAD_SHA --phase Foundation --test QA-J01 --density journey-only --repeat 2 --disposable --fixtures LOCAL_FIXTURES --models-config LOCAL_MODEL_DECLARATION --evidence-output qa-fixtures/runs
```

`--expected-sha` binds this invocation to checked-out HEAD; a mismatch or dirty
tracked source produces BLOCKED/exit 2 **before any fixture/model execution**.
The legacy invocation remains usable without the optional SHA flag; use it for
repeatable campaigns. Nothing switches/resets branches. Evidence output must
remain beneath ignored `qa-fixtures/`; the runner creates a unique subdirectory.
Existing private QA-J01 `report.json`/`junit.xml`, traces and photographs stay under
operator custody. Do not upload these local reports to public Actions: they are
not sanitized CI reports.

Foundation remains **QA-J01 / journey-only / 1 or 2 repetitions**. Normal and
Moderate now have additional bounded selections described below. Full photographic
Sparse/Regular/Dense and Advanced campaigns remain unqualified; unsupported density
choices are refused, never silently downsized. No model/photo downloads or heavy
workflow are added. Historical host results do not qualify another revision/host.


## Normal User QA #19

Reuse the supported Python 3.12 source environment, installed frontend, Playwright
Chromium and normal macOS Keychain. Run on a clean issue branch. Only J01 needs
reviewed distinct genuine photos and the existing permitted local model
declaration (see Foundation prerequisites above). Nothing is downloaded by this
campaign. The normal runner continues J02 and focused checks if those biometric
inputs are unavailable; J01 is NOT RUN with the precise blocker in its report.

```bash
python scripts/qa_foundation.py --phase Normal --test Normal --expected-sha FULL_40_CHARACTER_HEAD_SHA --disposable --actor "Scarlett Johansson" --fixtures qa-fixtures/marvel-actors --models-config qa-fixtures/models.json --date 2026-11-02
```

For J02 alone, omit the photo/model arguments and select `--phase Normal --test
QA-J02`. Foundation's existing `--test QA-J01` command and default two fresh runs
are preserved. Normal runs each of the two journeys once; `--repeat` applies to
Foundation J01 only. `--density journey-only` describes the genuine baseline;
Regular/Dense read comparisons are separately labeled domain fixtures, never
biometric acceptance. No full Sparse photographic campaign is inferred from one
reviewed pair.

The existing ignored `qa-fixtures/runs/<run>/report.json` adds `acceptance` for all
twelve entries: PASS only when every linked executed test/journey passed, FAIL
when evidence contradicted truth, PARTIAL when some evidence passed but the rest
is incomplete, NOT RUN when none executed. BLOCKED describes a missing prerequisite
and maps to NOT RUN/PARTIAL, never product failure or PASS. Exit 0 means selected
scope passed, 1 means execution failed, 2 means acceptance is incomplete. A J02-only
success leaves the full matrix incomplete. The report records source SHA, dirty
state, platform, per-test outcomes, journey proofs, timings and requested/created/
independently verified quantities. JUnit, application logs and browser evidence
remain private; use the existing `ci_report.py` allowlist for CI publication.

Available session lock/unlock is **Sign out / Sign in**. No dedicated lock control
exists in this revision. J02 checks that a signed-out mutation is rejected and
that saved identity remains unchanged. Fixtures are prepared using domain methods
on this run's exact disposable encrypted database while the app is stopped;
operator UI actions are separately recorded. Source dev mode performs no inference
in J02. J01 requires admitted real ONNX, encrypted authority and offline guards.
Cleanup removes only the random QA directory and its exact storage/recovery vault
entries and verifies the credentials are absent. Failure assertions, screenshots,
traces and model/photo details must stay local. No report should be copied wholesale
into GitHub. Review and reproduce failures before classifying a product defect.


### Executed checkpoint — 2026-11-02

Clean source `f1a37bebd82d8d7f1799eef7783ce8276a16d4ef`, macOS 26.0 arm64:
Normal campaign **PASS** in 47.638 s. N01, N02, N03, N04, N05, N06, N07, N08,
N09, N10, J01 and J02 each passed its linked executed checks. The focused campaign
ran 19 tests; J02 took 21.837 s and genuine J01 19.976 s. Reference ownership and
eligibility, exact saved query bytes, participants, occurrences, People/World reads,
wrong-location rejection, proof navigation, refresh/restart and exact credential
cleanup passed. These are execution results, not operator acceptance. The draft PR
records the final head rerun and GitHub's distinct tested merge SHA; this checkpoint
does not substitute for either.

| Dataset | Requested People / photos / Encounters | Created and independently verified | Limits |
| --- | --- | --- | --- |
| Genuine journey-only J01 | 1 / 2 / 1 | 1 / 2 / 1 | One reviewed distinct pair; real admitted ONNX |
| J02 domain journey | 2 / 0 / 2 | 2 / 0 / 2 | Media-free deterministic occurrences; no inference |
| Sparse | 3 / 6 / 2 | Not attempted as a full profile | Only 2 of 10 local candidate photos are reviewed; one actor |
| Regular domain reads | 25 / 80 / 30 | 25 / 0 / 30 | No photographic acceptance; Event pagination and World discovery only |
| Dense domain reads | 100 / 350 / 120 | 100 / 0 / 120 | Same two operations; zero photographic evidence |

Regular/Dense first/repeat/reopen timings are retained in private report properties;
Event pagination was approximately 2–3 / 7–8 ms, World discovery approximately
2–3 / 11–12 ms respectively. These are local observations without pass thresholds.
Repeated reads and reopening preserved every occurrence and all audited database
rows. Additional genuine photo acquisition/review and Windows qualification are
outside this execution.

At the same source checkpoint: backend **893 passed / 89 skipped / 137 subtests
passed**; frontend **140 passed**, production build and dependency check passed;
QA/report/oracle machinery **88 passed / 2 opt-in browser checks skipped**. The
campaign's two live browser journeys actually ran separately. Existing platform
and obsolete-suite skips are not acceptance passes. The existing frontend bundle
size advisory remains; generated assets did not change.

QA defects found and corrected during implementation: missing Explore evidence
selection, accidental fixture-class test collection, source-command fixture import,
and omitted normal safety-copy acknowledgment. Their affected tests/journeys were
rerun; no product defect was established. All private photos/models/licenses,
credentials, raw assertions, traces and authority files remain outside Git.


## Moderate User QA #20

Start from the latest hardening HEAD after operator authorization. On the supported
source environment and a clean issue branch:

```bash
python scripts/qa_foundation.py --phase Moderate --test Moderate --expected-sha FULL_40_CHARACTER_HEAD_SHA --disposable --actor "Scarlett Johansson" --fixtures qa-fixtures/marvel-actors --models-config qa-fixtures/models.json --date 2026-11-03
```

Reuse the existing authorized local photos/model declaration; nothing is acquired.
C01/C02 use source dev mode **without invoking synthetic inference**, with explicit
completed-review fixture setup while the app is stopped. People, participant and
Relations forms use the real UI; Person Notes/manual decisions also use actual
HTTP services. Domain media paths are fixture provenance, not photographic bytes.
A supplemental genuine source ONNX run corrects the saved Encounter's location,
checks its exact original query hash and repeats reads after a second restart.
Missing assets/browser/runtime are recorded as BLOCKED/NOT RUN and never PASS;
a genuine executed assertion failure fails the campaign. The optional biometric
result is separate from the ten correction entries.

`--test M01` through `M08`, `C01`, or `C02` executes only that entry's linked tests
and journeys. The full matrix remains incomplete (exit 2) unless all required
evidence actually ran. Exit 1 preserves test/infrastructure failures, including a
nonzero focused command even if all emitted testcases passed. Missing or skipped
linked evidence produces NOT RUN/PARTIAL. Moderate JSON records all ten rows,
source SHA/environment, per-test execution, browser/domain flags, independent
historical proofs, exact occurrence/evidence IDs, datasets and limitations. JUnit
contains the overall campaign and ten entry results. All raw reports, model/photo
hashes, authority paths, assertions, traces and screenshots remain under the
existing ignored private `qa-fixtures/runs/<run>/` directory. Do not upload them.

Focused checks include metadata date/time/location revisions; participant
reassign/add/remove; Attach ownership, stale-plan retry and cancel; Relations
INCLUDE/EXCLUDE with retained independent manual/Note sources; Event, Sighting and
Person selected/literal mentions; archive/restore; authorization, invalid/stale
requests, idempotence and existing transaction atomicity checks. Original review
and media provenance is separate from effective presence. C01 checks the pure
FACE_ASSIGNMENT regression as well as actual UI correction. Read comparisons
include Encounter, Events, Person Events/Sightings, canonical Person Graph,
Current World/Explore relationships, clusters and exact supporting evidence,
7/30/90-day Frequent/Recent/Multiple Locations, refresh/restart and supported
storage-service graph rebuild while the app is stopped.

Unsupported dedicated Sighting-edit UI/HTTP and in-place Manual endpoint editing
are NOT RUN with source-contract evidence; existing domain note revisions and
manual retire/create are covered. No feature is added to satisfy QA. No new
scale/performance run is attempted without correction-specific risk. The genuine
Sparse/Regular/Dense photographic profiles remain NOT RUN; domain fixture counts
never substitute for photographs. Windows/installer and Advanced QA are separate.


### Executed Moderate checkpoint — 2026-11-03

Clean source `dfea5def6c5347b1c72f35ce5442268ef3bcf3f3`, macOS 26.0 arm64:
M01–M08 and C01–C02 **PASS** against their linked executed evidence. Campaign
86.368 s; 33 focused tests passed, C01 19.796 s, C02 24.251 s, plus a fresh
real-ONNX saved-Encounter correction. Private evidence reference
`qa-fixtures/runs/5d29b2cd91e044089d428d727ef7d718/`: `report.json`,
`focused.xml`, `junit.xml`, C01/C02 traces and biometric correction/restart trace.
This checkpoint predates final proof-record refinements; final PR-head rerun and
GitHub tested merge SHA are reported on the PR and Issue #20.

C01's independently expected A→B correction yielded B's two legitimate Encounters
at X/Y and no A presence, duplicated occurrence, self-edge or manufactured pair.
The pure FACE_ASSIGNMENT domain path rechecked #22/#24 independently from the live
UI REASSIGN path. Actual metadata UI revisions and selected Event mentions retained
historical A mentions without presence or relationship evidence. C02 retained
manual support across EXCLUDE, retained co-observation across manual/Note removal,
and distinguished literal from selected Person/Sighting references. Domain Attach
added media to the same Encounter without adding presence/occurrences; existing
stale-target retry/cancel regressions passed. Refresh, fresh source restart,
supported domain graph rebuild and exact credential cleanup passed. Genuine
correction retained original query bytes after its second source restart.

| Authority | Requested People / genuine photos / Encounters | Created and verified | Evidence limit |
| --- | --- | --- | --- |
| C01 domain and browser, separately | 2 / 0 / 2 | 2 / 0 / 2 each | Two deterministic face/media records, no inference |
| C02 browser | 2 / 0 / 1 | 2 / 0 / 1 | Deterministic completed-review fixture, UI/API decisions |
| C02 domain | 2 / 0 / 1 | 2 / 0 / 1 | Three media records after attachment, zero genuine photos |
| Supplemental genuine ONNX | 1 / 2 / 1 | 1 / 2 / 1 | Existing reviewed distinct pair; saved-location correction |
| Full Sparse 3/6/2 | NOT RUN | Not claimed | Only the existing one-Person reviewed pair reused |
| Regular 25/80/30 and Dense 100/350/120 | NOT RUN | Not claimed | No additional correction-specific scale risk identified |

Broader regression: **910 backend passed / 89 existing skips / 137 subtests**,
**140 frontend passed**, production build passed (existing bundle-size advisory).
QA/report/oracle subset: **105 passed / 2 opt-in mechanism skips**; actual browser
journeys and ONNX ran separately. A stale reporter test still rejecting Moderate,
a wrong UI selector and non-UUID QA operation IDs were QA implementation defects,
corrected and rerun. No product defect was confirmed; no production code changed.
Unsupported dedicated Sighting-edit UI/HTTP and in-place Manual endpoint editing
remain explicitly NOT RUN. Evidence is ready for operator review after final-head
verification; no Moderate acceptance, merge or Advanced authorization is inferred.
