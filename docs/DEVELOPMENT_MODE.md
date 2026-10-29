# macOS

## Linux explicit source ONNX and recovery

`./run.sh models` and `./run.sh onnx` use the existing isolated source authority selected by `SENTRIFACE_DEV_DATA_DIR`. Linux source ONNX admission remains explicit, Git-checkout only, unpackaged/uncompiled, and loopback-only. Real SCRFD/ArcFace models, calibration and downstream encrypted SQLCipher/storage are unchanged; no systemd path or unavailable-vault fallback is introduced.

The Linux source master key and recovery code persist under that authority with owner-only custody. Recovery-code custody is a separate authority-bound AES-GCM protected file (`.sentriface-linux-source-recovery`), encrypted with the authority's existing master key. It is excluded from backup media closure; the normal external recovery kit remains required. Missing configured, corrupt, wrong-authority or unsafe custody fails closed. A normal fresh source root gets independent random key material; a root deliberately initialized by a verified recovery kit adopts the original key identity required by portable backup validation.

For fresh-authority recovery, prepare verified models without first starting a new encrypted authority, then run `./run.sh onnx --recover-kit /local/path/sentriface-recovery-kit.json` with the isolated root selected. Enter the supported recovery code at the prompt, authenticate through the normal product flow, import the encrypted backup and restore normally. An existing incompatible authority/key is never silently overwritten. macOS/Windows OS-vault recovery and packaged/hardened custody are unchanged. Development reset removes only its intended source authority, including these custody records; external kits/exports and unrelated authorities are unaffected.

Use this workflow to run SentriFace Edge directly from a Git checkout. Install
Python 3.11 or 3.12 first. Git is required to obtain the repository. The
launcher creates and maintains the repository-local `.venv312`; it does not
install Python or modify a global Python environment.

## Synthetic development

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

## Real ONNX development

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

## Data, frontend, and reset

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
environment and rerun `./run.sh`. If Python 3.11 or 3.12 is unavailable,
install one and rerun. A second process using the same development data root is
refused; stop the first process with `Control-C` before launching again.

# Windows

Use this workflow from a Windows 11 AMD64 checkout. Install 64-bit AMD64 Python
3.11 or 3.12 first. The launcher creates and maintains repository-local
`.venv312`; it neither installs Python nor modifies global Python packages. The
normal source launch uses the already-built frontend and does not require Node.

## Synthetic development

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

## Real ONNX development

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

## Data isolation and reset

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

## Frontend development

Node is needed only for frontend dependency, test, and build work:

```powershell
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

## Troubleshooting

- An incomplete `.venv312` is refused. Remove only that repository-local
  directory, then launch again.
- Install a supported 64-bit AMD64 Python if no Python 3.11/3.12 candidate is
  found; the launcher will not install Python automatically.
- `Another SentriFace process already owns this data store` means the first
  source process is still running or did not finish shutting down. Stop it and
  retry; do not delete the lock while a process is live.
- A model checksum, declaration, calibration, or compatibility failure is a P13
  refusal. Correct the local inputs and onboard them again; do not copy loose
  files around model authority.
- A production-path refusal is intentional. Do not work around it with an
  environment alias, junction, or nested directory.

## QA Foundation #17 (partial; not acceptance-qualified)

Coverage inventory: `tests/qa_coverage.json`. `partial` means existing domain or
synthetic tests cover some operations; it does not mean real inference passed.
The compact inventory groups operations rather than assigning a test file per row.
Issues #18–#21 own expanded coverage; #22 remains a known product regression target.

Run the offline QA checks with the existing environment:

```bash
python -m pytest -q tests/test_marvel_photo_fetcher.py tests/test_qa_foundation.py
python scripts/qa_foundation.py --test QA-J01
```

The second command is currently **preflight only**, emits revision/dirty status and
BLOCKED JSON, and exits 2. Browser actions, runtime admission attestation and actual
People/Event/World read adapters are still missing. It cannot report PASS. The
comparison primitive has an isolated wrong-expectation test; this is mechanism
validation, not a real application defect-detection demonstration.

Photographs stay under ignored `qa-fixtures/`, never Actions artifacts:

```bash
python scripts/fetch_marvel_photos.py --per-actor 8
python scripts/fetch_marvel_photos.py --verify
python scripts/fetch_marvel_photos.py --restore
```

Use `--actors-file` (one name per line) and `--per-actor` to expand collection.
Requires the existing OpenCV/NumPy dependencies for decoded image validation.
Save manifest.json separately with the photos; restoration checks the pinned hash
and fails if a source changes. Exact-content duplicates are reported. Similar crops,
CGI and false identity labels still require visual review. Discovery title/license
filters produce **candidates**, never verified truth. For each usable photo, record
`reviewed: true`, `reviewer`, descriptive `review_notes` (identity, real photograph,
pose, expression, lighting, age, quality, all visible faces), and `split` of
`enrollment` or `query` only after review. A smoke pair needs distinct hashes for
the same actor. Group images need every visible identity independently annotated
before future group tests can use them. Preserve source URL, author, license and
SHA-256. Do not upload raw photos, models, databases, credentials or browser traces
containing them to public CI. Dataset profiles in the registry are plans, not
achieved collection sizes; this execution collected zero verified photos.

`disposable_data()` creates and removes only its own random temporary directory;
it accepts no reset path. Future browser launch must select that directory using
the existing source-development data option and normal authentication/model
onboarding above. Do not copy ordinary user credentials or reset user authorities.

To observe the comparator's intentional failure directly (exit 1), independently
of the passing regression test that asserts the exception:

```bash
python -c "import sys; sys.path.insert(0, 'scripts'); from qa_foundation import assert_expected; assert_expected({'participants':['person-b']}, {'participants':['person-a']})"
```

Expected diagnostic: `result.participants[0]: expected 'person-b', actual 'person-a'`.
These are ordinary mechanism-test identifiers, not fabricated inference results.
