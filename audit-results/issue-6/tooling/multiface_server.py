"""Issue #6 Pass 3 audit launcher: disposable dev server with a synthetic multi-face seam.

Audit fixture only; no product source is changed. The dev WholeImageFaceDetector is
patched in this process so a generated image yields width // 240 equal vertical
"faces" (images narrower than 240 px yield none). HashFaceEmbedder seeds on image
bytes plus box, so each strip gets a distinct deterministic vector. This exercises
multi-face review/finalization wiring, never recognition accuracy.

Usage (repo root, disposable data dir only):
  PYTHONPATH=src .venv312/bin/python <this file> --data-dir <new-dir> --port 8765
"""
import argparse
from pathlib import Path

from sentriface.components import dev_components
from sentriface.components.dev_components import _image_size
from sentriface.models import DetectedFace, FaceBox

STRIP = 240


def _detect(self, image_path: Path):
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    width, height = _image_size(image_path, self.storage_key)
    return [
        DetectedFace(box=FaceBox(x=i * STRIP, y=0, width=STRIP, height=height, confidence=1.0), quality_score=1.0, crop_path=None)
        for i in range(width // STRIP)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    dev_components.WholeImageFaceDetector.detect = _detect
    from sentriface.api_server import create_server

    server = create_server(port=args.port, data_dir=args.data_dir, runtime="dev")
    print(f"serving http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
