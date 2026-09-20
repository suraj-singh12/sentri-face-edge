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

Windows source-development launcher support is planned and not yet implemented.
Do not infer macOS commands or data paths for Windows.

## Planned workflow placeholder

- Launcher command: not yet implemented.
- Synthetic mode: not yet implemented.
- ONNX mode: not yet implemented.
- Development-data location: not yet implemented.
- Reset command: not yet implemented.
- Frontend development: not yet documented for a Windows source launcher.
- Troubleshooting: not yet documented for a Windows source launcher.
