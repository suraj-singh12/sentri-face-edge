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
disposable data/vault cleanup; [all five final-SHA CI jobs passed](https://github.com/suraj-singh12/sentri-face-edge/actions/runs/40905213311). This is [draft PR #23](https://github.com/suraj-singh12/sentri-face-edge/pull/23), not yet merged. Private SHA-bound JSON/JUnit, traces, model hashes
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
