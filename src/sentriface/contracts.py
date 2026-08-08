from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sentriface.models import (
    DetectedFace,
    Embedding,
    EmbeddingRecord,
    GlobalGraphProjection,
    GraphConnection,
    InitFace,
    InitGroup,
    InitSession,
    Note,
    NoteRevision,
    Observation,
    ObservationMedia,
    ObservationParticipant,
    PendingAddition,
    PhotoReview,
    Person,
    PersonAssociation,
    PersonChange,
    PersonSummary,
    RecognitionDetail,
    RelationshipEvidence,
)


class FaceDetector(Protocol):
    def detect(self, image_path: Path) -> list[DetectedFace]:
        """Find faces in an image."""


class FaceEmbedder(Protocol):
    def encode(self, image_path: Path, face: DetectedFace) -> Embedding:
        """Convert an aligned face crop into a normalized vector."""


class FaceIndex(Protocol):
    def rebuild(self, embeddings: list[EmbeddingRecord]) -> None:
        """Replace the searchable index with current DB embeddings."""

    def add(self, record: EmbeddingRecord) -> None:
        """Add one embedding to the searchable index."""

    def search(self, vector: Embedding, top_k: int) -> list[Match]:
        """Return nearest identities by cosine similarity."""


class IdentityStore(Protocol):
    def initialize(self) -> None:
        """Create or migrate durable storage."""

    def create_person(
        self,
        name: str,
        metadata: dict | None = None,
        notes: str = "",
        identity_status: str = "IDENTIFIED",
    ) -> Person:
        """Create a person record."""

    def create_placeholder_person(
        self,
        name: str,
        metadata: dict | None,
        editor_name: str,
        operation_id: str,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> Person:
        """Create an identity-only person with no biometric data."""

    def add_embedding(
        self,
        person_id: str,
        vector: Embedding,
        quality_score: float,
        source_image: str | None = None,
        crop_path: str | None = None,
    ) -> EmbeddingRecord:
        """Persist an embedding for a person."""

    def list_embeddings(self) -> list[EmbeddingRecord]:
        """Load all embedding records."""

    def get_person(self, person_id: str, include_archived: bool = False) -> Person | None:
        """Load one person by id."""

    def list_persons(self, archived: bool = False) -> list[PersonSummary]:
        """List active or archived people with summary counts."""

    def list_embeddings_for_person(
        self,
        person_id: str,
        include_archived: bool = False,
    ) -> list[EmbeddingRecord]:
        """List embeddings belonging to one person."""

    def rename_person(self, person_id: str, name: str) -> None:
        """Rename one person."""

    def update_person_profile(
        self,
        person_id: str,
        name: str,
        rank: str | None,
        country: str | None,
        importance: str | None,
        editor_name: str,
        tags: list[str] | None = None,
        operation_id: str | None = None,
    ) -> PersonChange:
        """Update editable person profile fields and keep a change record."""

    def update_person_notes(
        self, person_id: str, notes: str, expected_previous_notes: str,
        editor_name: str, operation_id: str, mentioned_person_ids: list[str] | None = None,
        *, actor: dict | None = None, source: str | None = None,
    ) -> tuple[bool, Person, PersonChange | None]:
        """Update profile notes with optimistic concurrency and change history."""

    def create_note(
        self,
        owner_person_id: str,
        content: str,
        operation_id: str,
        *,
        mentioned_person_ids: list[str] | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        """Create one revisioned profile note and its explicit references atomically."""

    def update_note(
        self,
        note_id: str,
        content: str,
        operation_id: str,
        *,
        mentioned_person_ids: list[str] | None = None,
        expected_revision_number: int | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        """Append a note revision and reconcile its explicit references atomically."""

    def get_note(self, note_id: str, include_retired: bool = False) -> Note | None:
        """Load the current state of one note."""

    def get_person_note(
        self, person_id: str, include_retired: bool = False,
    ) -> Note | None:
        """Load the current revisioned profile note for one person."""

    def list_note_revisions(self, note_id: str) -> list[NoteRevision]:
        """List immutable note revisions oldest first."""

    def retire_note(
        self,
        note_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        """Retire a note and only its active NOTE_REFERENCE evidence."""

    def list_person_changes(self, person_id: str) -> list[PersonChange]:
        """List profile changes for one person, newest first."""

    def list_person_operations(self, person_id: str) -> list[dict]:
        """List lifecycle operations involving one person, newest first."""

    def create_person_association(
        self,
        source_person_id: str,
        target_person_id: str,
        actor_name: str,
        operation_id: str,
    ) -> PersonAssociation:
        """Create one undirected human-entered association."""

    def create_placeholder_association(
        self,
        source_person_id: str,
        name: str,
        metadata: dict | None,
        actor_name: str,
        operation_id: str,
    ) -> tuple[Person, PersonAssociation]:
        """Atomically create a placeholder and associate it with a person."""

    def list_person_associations(
        self,
        person_id: str,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[PersonAssociation]:
        """List undirected associations involving a person."""

    def remove_person_association(
        self,
        association_id: str,
        actor_name: str,
        operation_id: str,
    ) -> dict:
        """Remove an association without deleting either person."""

    def get_person_operation(self, operation_id: str, operation_type: str) -> dict | None:
        """Load a prior idempotent operation result, if one exists."""

    def begin_operation(
        self,
        operation_type: str,
        *,
        operation_id: str | None = None,
        actor: dict | None = None,
        source: str | None = None,
        context: dict | None = None,
        affected_entities: list[dict] | None = None,
        details: dict | None = None,
    ) -> dict:
        """Create a globally journaled operation in STARTED state."""

    def mark_operation_committed(self, operation_id: str, details: dict | None = None) -> dict:
        """Mark a started operation committed."""

    def mark_operation_failed(self, operation_id: str, details: dict | None = None) -> dict:
        """Mark a started operation failed."""

    def mark_operation_rolled_back(self, operation_id: str, details: dict | None = None) -> dict:
        """Mark a started or failed operation rolled back."""

    def mark_operation_reverted(self, operation_id: str, details: dict | None = None) -> dict:
        """Mark a committed operation reverted by a later operation."""

    def get_operation(self, operation_id: str) -> dict | None:
        """Load one global operation and its append-only status history."""

    def list_recent_operations(self, limit: int = 50) -> list[dict]:
        """List recent global operations, newest first."""

    def create_observation(
        self,
        operation_id: str,
        *,
        observed_at: str | None = None,
        location: str | None = None,
        context: dict | None = None,
        source: str | None = None,
        actor: dict | None = None,
        participant_ids: list[str] | None = None,
        media: list[dict] | None = None,
    ) -> Observation:
        """Create one draft observation, optionally with initial media and participants."""

    def get_observation(self, observation_id: str) -> Observation | None:
        """Load one observation."""

    def create_photo_review(
        self, review_id: str, media_id: str, faces: list[dict], **values,
    ) -> PhotoReview:
        """Create non-authoritative staged review state."""

    def set_photo_review_face_decision(
        self, review_id: str, face_id: str, decision: str, **values,
    ) -> PhotoReview:
        """Persist a non-authoritative final decision for one staged face."""

    def get_photo_review(self, review_id: str) -> PhotoReview | None:
        """Load staged review state and face decisions."""

    def cancel_photo_review(self, review_id: str) -> PhotoReview:
        """Abandon staged state without creating authoritative records."""

    def complete_photo_review(
        self, review_id: str, operation_id: str, **values,
    ) -> dict:
        """Atomically commit the authoritative result of one complete review."""

    def update_observation(
        self,
        observation_id: str,
        operation_id: str,
        *,
        observed_at: str | None = None,
        location: str | None = None,
        context: dict | None = None,
        source: str | None = None,
        actor: dict | None = None,
    ) -> Observation:
        """Update context fields while an observation is draft."""

    def attach_observation_media(
        self,
        observation_id: str,
        media_id: str,
        operation_id: str,
        *,
        media_path: str | None = None,
        source: str | None = None,
        actor: dict | None = None,
    ) -> ObservationMedia:
        """Attach an existing durable media reference to a draft observation."""

    def add_observation_participant(
        self,
        observation_id: str,
        person_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> ObservationParticipant:
        """Idempotently add one historical identity to a draft observation."""

    def remove_observation_participant(
        self,
        observation_id: str,
        person_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> dict:
        """Remove one participant while the observation is draft."""

    def list_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        """List participants with original and current canonical identity."""

    def list_observation_media(self, observation_id: str) -> list[ObservationMedia]:
        """List durable media memberships for one observation."""

    def list_observations_for_person(self, person_id: str) -> list[Observation]:
        """List observations retaining this exact historical participant identity."""

    def list_observations_for_media(self, media_id: str) -> list[Observation]:
        """List observations containing a media identifier."""

    def record_observation_evidence(
        self,
        observation_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        """Idempotently derive co-observation evidence from one finalized observation."""

    def deactivate_relationship_evidence(
        self,
        evidence_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> RelationshipEvidence:
        """Deactivate one evidence item without erasing its provenance."""

    def deactivate_relationship_evidence_for_source(
        self,
        evidence_type: str,
        source_entity_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        """Deactivate all evidence from one source without erasing provenance."""

    def get_person_neighbors(self, person_id: str) -> list[GraphConnection]:
        """Load projected connections for a person's current canonical identity."""

    def get_connection_evidence(
        self,
        source_person_id: str,
        target_person_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[RelationshipEvidence]:
        """Explain one current canonical connection with normalized evidence."""

    def get_global_graph_projection(self) -> GlobalGraphProjection:
        """Load all identity nodes and derived connections in the one global graph."""

    def rebuild_graph_projection(
        self,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> dict:
        """Deterministically replace the projection from active normalized evidence."""

    def validate_graph_projection(self) -> dict:
        """Compare the current projection with normalized evidence."""

    def get_embedding_lifecycle(self, embedding_id: str) -> dict | None:
        """Load face ownership and deletion state."""

    def get_person_lifecycle(self, person_id: str) -> dict | None:
        """Load lifecycle, identity, biometric, and canonical state for one person."""

    def resolve_canonical_person_id(self, person_id: str) -> str:
        """Resolve a person through any canonical identity chain."""

    def list_historical_persons(self) -> list[PersonSummary]:
        """List archived, deleted, and merged historical identities."""

    def archive_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        """Atomically archive one person."""

    def restore_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        """Atomically restore one archived person."""

    def soft_delete_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        """Atomically tombstone one person while retaining historical data."""

    def set_canonical_person_id(
        self,
        person_id: str,
        canonical_person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        """Store a canonical mapping without performing identity merge transfer work."""

    def list_file_references_for_person(self, person_id: str) -> list[str]:
        """List image and crop paths owned or referenced by one person."""

    def permanently_delete_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        """Compatibility entry point that tombstones a person without historical erasure."""

    def delete_embedding(self, embedding_id: str, operation_id: str) -> dict:
        """Atomically soft-delete an embedding while retaining linked details."""

    def list_deleted_embeddings(self) -> list[dict]:
        """List soft-deleted faces and their retention metadata."""

    def restore_deleted_embedding(self, embedding_id: str, operation_id: str) -> dict:
        """Restore one soft-deleted face."""

    def permanently_delete_embedding(self, embedding_id: str, operation_id: str) -> dict:
        """Erase a soft-deleted face and linked details from the live library."""

    def list_expired_deleted_embedding_ids(self, now: str | None = None) -> list[str]:
        """List soft-deleted faces whose retention period has elapsed."""

    def purge_expired_deleted_embeddings(
        self,
        embedding_ids: list[str],
        operation_id: str,
        now: str | None = None,
    ) -> dict:
        """Purge an expired-face batch atomically."""

    def move_embedding(self, embedding_id: str, person_id: str, operation_id: str) -> dict:
        """Atomically move one embedding and its recognition details."""

    def update_person_preferences(
        self,
        person_id: str,
        operation_id: str,
        favorite: bool | None = None,
        representative_embedding_id: str | None = None,
    ) -> dict:
        """Persist favorite and representative-photo preferences."""

    def list_recognition_details_for_person(self, person_id: str) -> list[RecognitionDetail]:
        """Load recognition details for all embeddings of one person."""

    def add_recognition_detail(
        self,
        embedding_id: str,
        person_id: str,
        image_id: str,
        name: str,
        decision: str,
        seen_date: str,
        seen_time: str,
        place_seen: str,
        individual_count: int,
        event_occasion: str,
        image_path: str | None = None,
        rank: str | None = None,
        country: str | None = None,
        importance: str | None = None,
        added_by: str | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
        recognition_detail: dict | None = None,
        operation_id: str | None = None,
    ) -> RecognitionDetail:
        """Persist visit/event details for a recognition tied to an embedding."""

    def backup_to(self, target_path: Path) -> None:
        """Create a durable copy of the database."""

    def save_pending_addition(self, pending: PendingAddition) -> None:
        """Persist a pending face addition for later review."""

    def get_pending_addition(self, pending_id: str) -> PendingAddition | None:
        """Load a pending addition by id."""

    def list_pending_additions(self) -> list[PendingAddition]:
        """Load pending additions waiting for review."""

    def list_all_file_references(self) -> list[str]:
        """List every path still referenced by durable or pending state."""

    def confirm_pending_addition(
        self,
        pending_id: str,
        operation_id: str,
        *,
        person_id: str | None = None,
        name: str | None = None,
        metadata: dict | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> tuple[Person, EmbeddingRecord]:
        """Atomically and idempotently confirm one pending face."""
    def delete_pending_addition(self, pending_id: str) -> None:
        """Remove a pending addition after review."""

    def create_init_session(self, source_path: str) -> InitSession:
        """Create a durable initialization review session."""

    def save_init_faces(self, faces: list[InitFace]) -> None:
        """Persist clustered initialization faces."""

    def get_init_session(self, session_id: str) -> InitSession | None:
        """Load one initialization session."""

    def list_init_sessions(self) -> list[InitSession]:
        """List durable initialization sessions."""

    def delete_init_session(self, session_id: str) -> None:
        """Delete an initialization session and its review records."""

    def list_init_groups(self, session_id: str) -> list[InitGroup]:
        """List grouped faces in an initialization session."""

    def confirm_init_faces_atomic(
        self,
        session_id: str,
        group_id: str,
        init_face_ids: list[str],
        operation_id: str,
        *,
        person_id: str | None = None,
        name: str | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> dict:
        """Atomically and idempotently confirm selected queue faces."""
    def delete_init_faces(self, init_face_ids: list[str]) -> None:
        """Remove reviewed faces from an initialization/queue group."""

    def update_init_face_groups(self, assignments: dict[str, str]) -> None:
        """Move pending initialization/queue faces into review groups."""

    def add_init_face_person_exclusions(
        self,
        session_id: str,
        init_face_ids: list[str],
        person_id: str,
    ) -> None:
        """Suppress a person suggestion for pending queue faces."""

    def list_init_face_person_exclusions(
        self,
        session_id: str,
        init_face_ids: list[str],
    ) -> dict[str, set[str]]:
        """Load suppressed person suggestions for queue faces."""

    def mark_init_group_status(self, session_id: str, group_id: str, status: str) -> None:
        """Mark an initialization group reviewed or rejected."""
