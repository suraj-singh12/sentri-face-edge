# macOS

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
path.

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
