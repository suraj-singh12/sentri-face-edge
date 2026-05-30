from __future__ import annotations

from typing import Any

from sentriface.config import RuntimeConfig
from sentriface.models import DetectedFace, QualityReport, QualityStatus


class FaceQualityEvaluator:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def evaluate(self, image: Any, face: DetectedFace) -> QualityReport:
        cv2 = _cv2()
        reasons: list[str] = []
        penalties = 0.0

        if face.box.confidence < self.config.min_detector_confidence:
            reasons.append("low_detector_confidence")
            penalties += 0.3

        if min(face.box.width, face.box.height) < self.config.min_face_size:
            reasons.append("face_too_small")
            penalties += 0.35

        height, width = image.shape[:2]
        x1 = face.box.x
        y1 = face.box.y
        x2 = face.box.x + face.box.width
        y2 = face.box.y + face.box.height
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            reasons.append("face_box_outside_image")
            penalties += 0.25

        crop = _safe_crop(image, face)
        if crop is None:
            return QualityReport(
                status=QualityStatus.BAD,
                score=0.0,
                reasons=("invalid_face_crop",),
            )

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean())

        if blur_score < self.config.blur_threshold:
            reasons.append("too_blurry")
            penalties += 0.3
        if brightness < self.config.dark_threshold:
            reasons.append("too_dark")
            penalties += 0.25
        if brightness > self.config.bright_threshold:
            reasons.append("too_bright")
            penalties += 0.25

        if face.landmarks is None:
            reasons.append("missing_landmarks")
            penalties += 0.1

        score = max(0.0, min(1.0, face.quality_score - penalties))
        if score < self.config.min_quality_score:
            status = QualityStatus.BAD
        elif score < self.config.warn_quality_score or reasons:
            status = QualityStatus.WARN
        else:
            status = QualityStatus.GOOD
        return QualityReport(status=status, score=score, reasons=tuple(reasons))


def _safe_crop(image: Any, face: DetectedFace) -> Any | None:
    height, width = image.shape[:2]
    x1 = max(0, face.box.x)
    y1 = max(0, face.box.y)
    x2 = min(width, face.box.x + face.box.width)
    y2 = min(height, face.box.y + face.box.height)
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def _cv2() -> Any:
    try:
        import cv2

        return cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required for face quality scoring. Install with: "
            "pip install opencv-python-headless"
        ) from exc

