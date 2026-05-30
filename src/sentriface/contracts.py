from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sentriface.models import DetectedFace, Embedding, EmbeddingRecord, PendingAddition, Person


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

    def save_pending_addition(self, pending: PendingAddition) -> None:
        """Persist a pending face addition for later review."""

    def get_pending_addition(self, pending_id: str) -> PendingAddition | None:
        """Load a pending addition by id."""

    def list_pending_additions(self) -> list[PendingAddition]:
        """Load pending additions waiting for review."""

    def delete_pending_addition(self, pending_id: str) -> None:
        """Remove a pending addition after review."""
