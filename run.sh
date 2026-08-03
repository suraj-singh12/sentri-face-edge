#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
VENV_DIR="$PROJECT_DIR/.venv312"
PYTHON="$VENV_DIR/bin/python"

cd "$PROJECT_DIR"

if [[ ! -x "$PYTHON" ]]; then
  if ! command -v python3.12 >/dev/null 2>&1; then
    print -u2 "SentriFace requires Python 3.12. Install it, then run ./run.sh again."
    exit 1
  fi
  python3.12 -m venv "$VENV_DIR"
fi

if ! "$PYTHON" -c 'import sentriface, onnxruntime, cv2, sqlcipher3' >/dev/null 2>&1; then
  "$PYTHON" -m pip install -e .
fi

exec "$PYTHON" -m sentriface.ui \
  --runtime onnx \
  --allow-unpackaged-source-onnx \
  --detector-model "$PROJECT_DIR/models/det_500m.onnx" \
  --recognizer-model "$PROJECT_DIR/models/w600k_r50.onnx" \
  --data-dir "$PROJECT_DIR/data"
