from __future__ import annotations

import threading

from sentriface.models import Embedding, EmbeddingRecord, Match


class HnswFaceIndex:
    """Thread-safe HNSW cosine index with exception-safe state publication."""

    backend_name = "hnswlib"

    def __init__(self, dimensions: int, initial_capacity: int = 64) -> None:
        self.dimensions = dimensions
        self._capacity = max(1, initial_capacity)
        self._index = None
        self._records: list[EmbeddingRecord] = []
        self._lock = threading.RLock()

    def rebuild(self, embeddings: list[EmbeddingRecord]) -> None:
        records = list(embeddings)
        for record in records:
            if len(record.vector) != self.dimensions:
                raise ValueError("Embedding dimensions do not match")
        with self._lock:
            # Build entirely in local variables. Readers keep seeing the prior,
            # valid generation if allocation or native construction fails.
            capacity = max(64, len(records) * 2, self._capacity)
            index = self._build(records, capacity)
            self._index = index
            self._records = records
            self._capacity = capacity

    def add(self, record: EmbeddingRecord) -> None:
        if len(record.vector) != self.dimensions:
            raise ValueError("Embedding dimensions do not match")
        with self._lock:
            # Rebuilding a new generation is deliberately conservative: a native
            # add/resize failure can never leave label mappings half-mutated.
            records = [*self._records, record]
            capacity = max(64, len(records) * 2, self._capacity)
            index = self._build(records, capacity)
            self._index = index
            self._records = records
            self._capacity = capacity

    def search(self, vector: Embedding, top_k: int) -> list[Match]:
        if len(vector) != self.dimensions:
            raise ValueError("Embedding dimensions do not match")
        with self._lock:
            if self._index is None or not self._records or top_k <= 0:
                return []
            count = min(top_k, len(self._records))
            labels, distances = self._index.knn_query(vector, k=count)
            return [
                Match(
                    person_id=(
                        self._records[int(label)].canonical_person_id
                        or self._records[int(label)].person_id
                    ),
                    embedding_id=self._records[int(label)].embedding_id,
                    score=max(-1.0, min(1.0, 1.0 - float(distance))),
                )
                for label, distance in zip(labels[0], distances[0])
            ]

    def _build(self, records: list[EmbeddingRecord], capacity: int):
        if not records:
            return None
        hnswlib = _hnswlib()
        index = hnswlib.Index(space="cosine", dim=self.dimensions)
        index.init_index(max_elements=capacity, ef_construction=200, M=16)
        index.add_items([record.vector for record in records], list(range(len(records))))
        index.set_ef(max(50, min(200, len(records))))
        return index


def _hnswlib():
    try:
        import hnswlib
        return hnswlib
    except ImportError:
        try:
            import qhnswlib
            return qhnswlib
        except ImportError as exc:
            raise RuntimeError(
                "The HNSW index profile requires qhnswlib (wheel) or hnswlib. "
                "Install with: pip install qhnswlib"
            ) from exc
