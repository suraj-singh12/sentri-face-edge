from __future__ import annotations

from sentriface.models import Embedding, EmbeddingRecord, Match


class LinearFaceIndex:
    """Tiny-gallery cosine index.

    This is dependency-free and good enough while the gallery is small. Swap it
    for hnswlib when identities grow or profiling says search is hot.
    """

    def __init__(self) -> None:
        self._records: list[EmbeddingRecord] = []

    def rebuild(self, embeddings: list[EmbeddingRecord]) -> None:
        self._records = list(embeddings)

    def add(self, record: EmbeddingRecord) -> None:
        self._records.append(record)

    def search(self, vector: Embedding, top_k: int) -> list[Match]:
        scored = [
            Match(
                person_id=record.person_id,
                embedding_id=record.embedding_id,
                score=_cosine(vector, record.vector),
            )
            for record in self._records
        ]
        scored.sort(key=lambda match: match.score, reverse=True)
        return scored[:top_k]


def _cosine(left: Embedding, right: Embedding) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match")
    return sum(a * b for a, b in zip(left, right))
