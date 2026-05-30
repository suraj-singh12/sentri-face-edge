from __future__ import annotations

import hashlib
import random
from pathlib import Path

from sentriface.models import DetectedFace, Embedding, FaceBox


class WholeImageFaceDetector:
    """Development detector that treats the whole image as one face.

    It lets workflow/storage code run before ONNX models are added.
    """

    def detect(self, image_path: Path) -> list[DetectedFace]:
        if not image_path.exists():
            raise FileNotFoundError(image_path)
        return [
            DetectedFace(
                box=FaceBox(x=0, y=0, width=0, height=0, confidence=1.0),
                quality_score=1.0,
                crop_path=None,
            )
        ]


class HashFaceEmbedder:
    """Deterministic placeholder embedder for tests and early UI work."""

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def encode(self, image_path: Path, face: DetectedFace) -> Embedding:
        seed_material = image_path.read_bytes() + repr(face.box).encode("utf-8")
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "little")
        rng = random.Random(seed)
        values = [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
        norm = sum(value * value for value in values) ** 0.5 or 1.0
        return tuple(value / norm for value in values)

