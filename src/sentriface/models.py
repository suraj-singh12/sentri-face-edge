from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


Embedding = tuple[float, ...]
Landmarks = tuple[tuple[float, float], ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class FaceBox:
    x: int
    y: int
    width: int
    height: int
    confidence: float


@dataclass(frozen=True)
class DetectedFace:
    box: FaceBox
    quality_score: float
    landmarks: Landmarks | None = None
    crop_path: str | None = None


@dataclass(frozen=True)
class Person:
    person_id: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class EmbeddingRecord:
    embedding_id: str
    person_id: str
    vector: Embedding
    quality_score: float
    source_image: str | None = None
    crop_path: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Match:
    person_id: str
    score: float
    embedding_id: str


class MatchDecision(str, Enum):
    STRONG = "strong"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class QualityStatus(str, Enum):
    GOOD = "good"
    WARN = "warn"
    BAD = "bad"


@dataclass(frozen=True)
class QualityReport:
    status: QualityStatus
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecognitionResult:
    face: DetectedFace
    matches: list[Match]
    decision: MatchDecision
    quality: QualityReport | None = None


@dataclass(frozen=True)
class PendingAddition:
    pending_id: str
    source_image: str
    face: DetectedFace
    vector: Embedding
    matches: list[Match]
    decision: MatchDecision
    quality: QualityReport
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class RejectedFace:
    source_image: str
    face: DetectedFace
    quality: QualityReport


@dataclass(frozen=True)
class InitFace:
    init_face_id: str
    session_id: str
    group_id: str
    source_image: str
    face: DetectedFace
    vector: Embedding
    quality: QualityReport
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class InitSession:
    session_id: str
    source_path: str
    status: str
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class InitGroup:
    group_id: str
    session_id: str
    faces: list[InitFace]
    status: str = "pending"
