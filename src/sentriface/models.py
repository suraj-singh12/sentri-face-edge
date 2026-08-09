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
    notes: str = ""
    lifecycle_status: str = "ACTIVE"
    canonical_person_id: str | None = None
    identity_status: str = "IDENTIFIED"
    biometric_status: str = "NO_FACE"


@dataclass(frozen=True)
class EmbeddingRecord:
    embedding_id: str
    person_id: str
    vector: Embedding
    quality_score: float
    source_image: str | None = None
    crop_path: str | None = None
    created_at: str = field(default_factory=utc_now)
    canonical_person_id: str | None = None


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
    notes: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    status: str = "DRAFT"
    observed_at: str | None = None
    location: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    created_operation_id: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    finalized_at: str | None = None


@dataclass(frozen=True)
class ObservationMedia:
    observation_id: str
    media_id: str
    media_path: str | None = None
    source: str | None = None
    operation_id: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ObservationParticipant:
    observation_id: str
    person_id: str
    canonical_person_id: str
    person_lifecycle_status: str
    source: str | None = None
    operation_id: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class IdentityCorrection:
    correction_id: str
    correction_type: str
    from_person_id: str
    to_person_id: str
    operation_id: str
    observation_id: str | None = None
    face_assignment_id: str | None = None
    embedding_id: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ObservationFaceAssignment:
    assignment_id: str
    observation_id: str
    review_id: str
    face_id: str
    embedding_id: str
    original_person_id: str
    created_operation_id: str
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Note:
    note_id: str
    owner_person_id: str
    status: str
    content: str
    revision_number: int
    mentioned_person_ids: tuple[str, ...] = ()
    subject_type: str = "PERSON"
    subject_id: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    retired_at: str | None = None
    canonical_owner_person_id: str | None = None
    effective_mentioned_person_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class NoteRevision:
    revision_id: str
    note_id: str
    revision_number: int
    content: str
    mentioned_person_ids: tuple[str, ...] = ()
    actor: dict[str, Any] = field(default_factory=dict)
    author_name: str = ""
    operation_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    effective_mentioned_person_ids: tuple[str, ...] = ()


class MergeAffectedAction(str, Enum):
    PRESERVE = "PRESERVE"
    REINTERPRET_CANONICAL_OWNER = "REINTERPRET_CANONICAL_OWNER"
    UNION_IN_CURRENT_VIEW = "UNION_IN_CURRENT_VIEW"
    SELECT_VALUE = "SELECT_VALUE"


class MergeConflictStrategy(str, Enum):
    KEEP_SOURCE = "KEEP_SOURCE"
    KEEP_TARGET = "KEEP_TARGET"
    COMBINE = "COMBINE"
    USER_SELECTED = "USER_SELECTED"


@dataclass(frozen=True)
class MergeAffectedItem:
    item_type: str
    item_id: str
    raw_owner_person_id: str | None
    effective_owner_person_id: str | None
    action: MergeAffectedAction
    before_state: dict[str, Any] = field(default_factory=dict)
    after_state: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def previous_person_id(self) -> str | None:
        return self.raw_owner_person_id

    @property
    def effective_person_id(self) -> str | None:
        return self.effective_owner_person_id


@dataclass(frozen=True)
class MergeConflictResolution:
    conflict_id: str
    category: str
    field_name: str
    source_value: Any
    target_value: Any
    strategy: MergeConflictStrategy
    selected_value: Any
    inverse_data: dict[str, Any]


@dataclass(frozen=True)
class MergeOperation:
    merge_operation_id: str
    source_person_id: str
    target_person_id: str
    actor: dict[str, Any]
    created_at: str
    previous_source_lifecycle_status: str
    previous_target_lifecycle_status: str
    previous_source_canonical_person_id: str | None
    previous_target_canonical_person_id: str | None
    reason: str | None
    context: dict[str, Any]
    operation_journal_id: str
    affected_items: tuple[MergeAffectedItem, ...] = ()
    conflicts: tuple[MergeConflictResolution, ...] = ()


@dataclass(frozen=True)
class RelationshipEvidence:
    evidence_id: str
    evidence_type: str
    source_entity_type: str
    source_entity_id: str
    evidence_revision_id: str
    source_person_id: str
    target_person_id: str
    relationship_type: str = "ASSOCIATED_WITH"
    directionality: str = "UNDIRECTED"
    active: bool = True
    source: str | None = None
    created_operation_id: str = ""
    created_at: str = field(default_factory=utc_now)
    deactivated_operation_id: str | None = None
    deactivated_at: str | None = None


@dataclass(frozen=True)
class GraphConnection:
    source_person_id: str
    target_person_id: str
    relationship_type: str
    directionality: str
    evidence_count: int
    evidence_types: tuple[str, ...]
    last_evidence_at: str


@dataclass(frozen=True)
class GraphNode:
    person_id: str
    canonical_person_id: str
    name: str
    lifecycle_status: str


@dataclass(frozen=True)
class GlobalGraphProjection:
    nodes: tuple[GraphNode, ...]
    connections: tuple[GraphConnection, ...]


@dataclass(frozen=True)
class Sighting:
    """One effective canonical person's presence in one finalized observation."""

    sighting_id: str
    observation_id: str
    canonical_person_id: str
    observed_at: str
    location: str | None
    context: dict[str, Any]
    source: str | None
    finalized_at: str | None
    media: tuple[ObservationMedia, ...] = ()
    raw_participant_person_ids: tuple[str, ...] = ()
    effective_participant_person_ids: tuple[str, ...] = ()
    correction_operation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemporalCount:
    period: str
    count: int


@dataclass(frozen=True)
class LocationCount:
    location: str
    count: int
    last_observed_at: str


@dataclass(frozen=True)
class PresenceAnalytics:
    observation_count: int
    first_seen_at: str | None
    last_seen_at: str | None
    frequency_per_30_days: float
    frequency_label: str
    timeline: tuple[TemporalCount, ...] = ()
    locations: tuple[LocationCount, ...] = ()
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationshipAnalytics:
    person_id: str
    source_person_id: str
    target_person_id: str
    relationship_type: str
    directionality: str
    evidence_count: int
    evidence_type_counts: dict[str, int]
    first_evidence_at: str
    last_evidence_at: str
    co_observation_count: int
    evidence: tuple[RelationshipEvidence, ...] = ()


@dataclass(frozen=True)
class PersonIntelligence:
    requested_person_id: str
    canonical_person_id: str
    lifecycle_status: str
    canonical_lifecycle_status: str
    biometric_status: str
    embedding_count: int
    confidence_summary: dict[str, Any]
    presence: PresenceAnalytics
    relationships: tuple[RelationshipAnalytics, ...]
    activity: tuple[dict[str, Any], ...]
    provenance: tuple[str, ...] = ()


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
    previous_notes: str | None = None
    new_notes: str | None = None
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
    first_seen_at: str | None = None
    frequency_per_30_days: float = 0.0
    frequency_label: str = "Never Seen"


@dataclass(frozen=True)
class PersonAssociation:
    association_id: str
    source_person_id: str
    target_person_id: str
    relationship_type: str = "ASSOCIATED_WITH"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    created_by: str = ""
    association_origin: str = "manual"


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


class ReviewDecision(str, Enum):
    ACCEPT_EXISTING_PERSON = "ACCEPT_EXISTING_PERSON"
    ACCEPT_NEW_PERSON = "ACCEPT_NEW_PERSON"
    EXCLUDE = "EXCLUDE"
    SKIP = "SKIP"


@dataclass(frozen=True)
class ReviewFaceDecision:
    review_id: str
    face_id: str
    staged_face_type: str
    staged_face_id: str
    decision: str | None = None
    person_id: str | None = None
    new_person_key: str | None = None
    new_person_name: str | None = None
    new_person_metadata: dict = field(default_factory=dict)
    notes: str = ""
    mentioned_person_ids: tuple[str, ...] = ()
    recognition_detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PhotoReview:
    review_id: str
    media_id: str
    media_path: str | None
    source: str
    status: str
    faces: tuple[ReviewFaceDecision, ...]
    created_at: str
    observation_id: str | None = None
    completed_operation_id: str | None = None
    completed_at: str | None = None
