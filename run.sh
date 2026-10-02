#!/bin/zsh

# macOS source-development entry point. This intentionally has a different
# authority root from the installed product so both can run on the same Mac.
set -euo pipefail

PROJECT_DIR="${0:A:h}"
VENV_DIR="$PROJECT_DIR/.venv312"
PYTHON="$VENV_DIR/bin/python"
DEV_DATA_DIR="${SENTRIFACE_DEV_DATA_DIR:-$HOME/Library/Application Support/SentriFace-Dev}"
DEFAULT_DEV_DATA_DIR="$HOME/Library/Application Support/SentriFace-Dev"
PRODUCTION_DATA_DIR="$HOME/Library/Application Support/SentriFace"
MODE="${1:-dev}"

usage() {
  cat <<'EOF'
Usage: ./run.sh [dev|onnx|models|reset|help] [model-setup options]

  dev     Start the synthetic, no-model source runtime (default).
  onnx    Start the real ONNX source runtime using this development authority.
  models  Install operator-supplied models into this development authority.
  reset   Remove only this development authority after an explicit confirmation.

Set SENTRIFACE_DEV_DATA_DIR to use a different development authority. It must
not be the installed-product SentriFace data directory.
EOF
}

if [[ "$DEV_DATA_DIR:A" == "$PRODUCTION_DATA_DIR:A" ]]; then
  print -u2 "Refusing to use the installed-product data directory for source development."
  exit 2
fi

case "$MODE" in
  help|-h|--help)
    usage
    exit 0
    ;;
  dev|onnx|models|reset)
    if (( $# > 0 )); then shift; fi
    ;;
  *)
    print -u2 "Unknown source-development mode: $MODE"
    usage >&2
    exit 2
    ;;
esac

if [[ "$MODE" == "reset" ]]; then
  if [[ "$DEV_DATA_DIR:A" != "$DEFAULT_DEV_DATA_DIR:A" ]]; then
    print -u2 "For safety, reset is available only for the default SentriFace-Dev data directory."
    print -u2 "Remove a custom SENTRIFACE_DEV_DATA_DIR only after independently verifying its path."
    exit 2
  fi
  if [[ "${1:-}" != "--yes" ]]; then
    print "This removes only: $DEV_DATA_DIR"
    print -n "Type RESET-DEV to continue: "
    read -r confirmation
    [[ "$confirmation" == "RESET-DEV" ]] || { print "Development reset cancelled."; exit 0; }
  fi
  RESET_PYTHON="$PYTHON"
  if [[ ! -x "$RESET_PYTHON" ]]; then
    RESET_PYTHON="$(command -v python3.12 || command -v python3.11 || command -v python3)"
  fi
  if [[ "$OSTYPE" == linux* ]]; then
    "$RESET_PYTHON" "$PROJECT_DIR/scripts/reset_macos_dev_authority.py" "$DEV_DATA_DIR" --linux-source
  else
    "$RESET_PYTHON" "$PROJECT_DIR/scripts/reset_macos_dev_authority.py" "$DEV_DATA_DIR"
  fi
  print "Removed SentriFace source-development data: $DEV_DATA_DIR"
  exit 0
fi

cd "$PROJECT_DIR"

if [[ -e "$VENV_DIR" && ! -x "$PYTHON" ]]; then
  print -u2 "The repository virtual environment is incomplete: $VENV_DIR"
  print -u2 "Remove that virtual environment and run ./run.sh again."
  exit 2
fi

if [[ ! -x "$PYTHON" ]]; then
  for candidate in python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)' >/dev/null 2>&1; then
        "$candidate" -m venv "$VENV_DIR"
        break
      fi
    fi
  done
fi

if [[ ! -x "$PYTHON" ]]; then
  print -u2 "SentriFace source development requires Python 3.11 or 3.12. Install one, then run ./run.sh again."
  exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)' >/dev/null 2>&1; then
  print -u2 "The repository virtual environment must use Python 3.11 or 3.12: $PYTHON"
  exit 2
fi

DEPENDENCY_FINGERPRINT="$(shasum -a 256 pyproject.toml | awk '{print $1}')"
FINGERPRINT_FILE="$VENV_DIR/.sentriface-dependencies.sha256"
if [[ ! -f "$FINGERPRINT_FILE" ]] \
  || [[ "$(<"$FINGERPRINT_FILE")" != "$DEPENDENCY_FINGERPRINT" ]] \
  || ! "$PYTHON" -c 'import cv2, onnxruntime, pytest, sentriface, sqlcipher3' >/dev/null 2>&1; then
  print "Installing or updating repository development dependencies..."
  "$PYTHON" -m pip install -e ".[test]"
  print -r -- "$DEPENDENCY_FINGERPRINT" > "$FINGERPRINT_FILE"
fi

print "SentriFace source mode: $MODE"
print "Source-development data: $DEV_DATA_DIR"
print "Installed-product data remains separate: $PRODUCTION_DATA_DIR"

case "$MODE" in
  dev)
    exec "$PYTHON" -m sentriface.ui --runtime dev --data-dir "$DEV_DATA_DIR" "$@"
    ;;
  onnx)
    exec "$PYTHON" -m sentriface.ui --runtime onnx --allow-unpackaged-source-onnx --data-dir "$DEV_DATA_DIR" "$@"
    ;;
  models)
    exec "$PYTHON" -m sentriface.model_setup --models-dir "$DEV_DATA_DIR/models" "$@"
    ;;
esac
