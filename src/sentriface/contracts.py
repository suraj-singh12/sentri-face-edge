from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sentriface.models import (
    DetectedFace,
    Embedding,
    EmbeddingRecord,
    InitFace,
    InitGroup,
    InitSession,
    PendingAddition,
    Person,
    PersonChange,
    PersonSummary,
    RecognitionDetail,
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

    def create_person(self, name: str, metadata: dict | None = None) -> Person:
        """Create a person record."""

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

    def get_person(self, person_id: str) -> Person | None:
        """Load one person by id."""

    def list_persons(self) -> list[PersonSummary]:
        """List active people with summary counts."""

    def list_embeddings_for_person(self, person_id: str) -> list[EmbeddingRecord]:
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
    ) -> PersonChange:
        """Update editable person profile fields and keep a change record."""

    def list_person_changes(self, person_id: str) -> list[PersonChange]:
        """List profile changes for one person, newest first."""

    def delete_person(self, person_id: str) -> None:
        """Soft-delete one person."""

    def delete_embedding(self, embedding_id: str) -> None:
        """Delete one embedding record."""

    def move_embedding(self, embedding_id: str, person_id: str) -> None:
        """Move one embedding to another person."""

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
