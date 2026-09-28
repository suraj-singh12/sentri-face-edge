from __future__ import annotations

from typing import Any

from sentriface.models import EmbeddingRecord


def embedding_record_payload(record: EmbeddingRecord) -> dict[str, Any]:
    """Serialize one embedding without hiding its historical owner."""
    return {
        "embedding_id": record.embedding_id,
        "person_id": record.person_id,
        "raw_person_id": record.person_id,
        "canonical_person_id": record.canonical_person_id or record.person_id,
        "quality_score": record.quality_score,
        "recognition_state": record.recognition_state,
        "source_image": record.source_image,
        "crop_path": record.crop_path,
        "created_at": record.created_at,
    }
