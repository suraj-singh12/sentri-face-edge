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
    deleted_at: str | None = None
    enrollment_status: str = "enrolled"


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
class RecognitionDetail:
    detail_id: str
    embedding_id: str
    person_id: str
    image_id: str
    name: str
    decision: str
    seen_date: str
    seen_time: str
    place_seen: str
    individual_count: int
    event_occasion: str
    image_path: str | None = None
    rank: str | None = None
    country: str | None = None
    importance: str | None = None
    added_by: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class PersonChange:
    change_id: str
    person_id: str
    previous_name: str
    new_name: str
    previous_rank: str | None = None
    new_rank: str | None = None
    previous_country: str | None = None
    new_country: str | None = None
    previous_importance: str | None = None
    new_importance: str | None = None
    previous_status: str | None = None
    new_status: str | None = None
    editor_name: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Match:
    person_id: str
    score: float
    embedding_id: str


@dataclass(frozen=True)
class PersonMatch:
    person_id: str
    score: float
    embedding_ids: tuple[str, ...]
    embeddings_matched: int


@dataclass(frozen=True)
class PersonSummary:
    person: Person
    embedding_count: int
    sighting_count: int = 0
    last_seen_at: str | None = None


@dataclass(frozen=True)
class PersonAssociation:
    association_id: str
    source_person_id: str
    target_person_id: str
    relationship_type: str = "ASSOCIATED_WITH"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    created_by: str = ""


@dataclass(frozen=True)
class RankedPersonCandidate:
    summary: PersonSummary
    match: PersonMatch | None
    embeddings: tuple[EmbeddingRecord, ...]


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
    matches: list[PersonMatch]
    decision: MatchDecision
    quality: QualityReport | None = None


@dataclass(frozen=True)
class PendingAddition:
    pending_id: str
    source_image: str
    face: DetectedFace
    vector: Embedding
    matches: list[PersonMatch]
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
