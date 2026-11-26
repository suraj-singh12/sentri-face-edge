#!/usr/bin/env bash
# Fetch the third-party research assets used by the Issue #89 experiments.
# Nothing fetched here is committed. Both are non-commercial research material:
#   * InsightFace buffalo_s (SCRFD-500MF detector, MobileFaceNet recognizer)
#     - admitted into each disposable authority as "noncommercial-research".
#   * Labeled Faces in the Wild (funneled) - genuine face photographs.
# Review the supplier terms before use; delete the assets afterwards.
set -euo pipefail
ASSETS="${ISSUE89_ASSETS:-/projects/sandbox/assets}"
mkdir -p "$ASSETS"
cd "$ASSETS"
curl -sSL -o buffalo_s.zip https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip
unzip -o -q buffalo_s.zip -d buffalo_s
rm -f buffalo_s.zip buffalo_s/1k3d68.onnx buffalo_s/2d106det.onnx buffalo_s/genderage.onnx
curl -sSL -o lfw.tgz https://ndownloader.figshare.com/files/5976015
tar xzf lfw.tgz && rm lfw.tgz
# Expected SHA-256 (verified during the recorded run):
sha256sum buffalo_s/det_500m.onnx buffalo_s/w600k_mbf.onnx
