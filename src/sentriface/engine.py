from __future__ import annotations

import uuid
from pathlib import Path

from sentriface.components.image_ops import load_bgr_image
from sentriface.components.quality import FaceQualityEvaluator
from sentriface.config import RuntimeConfig
from sentriface.contracts import FaceDetector, FaceEmbedder, FaceIndex, IdentityStore
from sentriface.models import (
    Match,
    MatchDecision,
    PendingAddition,
    Person,
    QualityStatus,
    RejectedFace,
    RecognitionResult,
)


class FaceEngine:
    def __init__(
        self,
        config: RuntimeConfig,
        detector: FaceDetector,
        embedder: FaceEmbedder,
        index: FaceIndex,
        store: IdentityStore,
    ) -> None:
        self.config = config
        self.detector = detector
        self.embedder = embedder
        self.index = index
        self.store = store
        self.quality = FaceQualityEvaluator(config)

    def initialize(self) -> None:
        self.store.initialize()
        self.index.rebuild(self.store.list_embeddings())

    def recognize(self, image_path: Path) -> list[RecognitionResult]:
        results: list[RecognitionResult] = []
        image = load_bgr_image(image_path)
        for face in self.detector.detect(image_path):
            quality = self.quality.evaluate(image, face)
            vector = self.embedder.encode(image_path, face)
            matches = self.index.search(vector, self.config.top_k)
            results.append(
                RecognitionResult(
                    face=face,
                    matches=matches,
                    decision=self._decide(matches),
                    quality=quality,
                )
            )
        return results

    def prepare_additions(self, image_path: Path, allow_bad_quality: bool = False) -> list[PendingAddition]:
        prepared = self.prepare_additions_with_rejections(image_path, allow_bad_quality)
        return prepared.accepted

    def prepare_additions_with_rejections(
        self,
        image_path: Path,
        allow_bad_quality: bool = False,
    ) -> "PreparedAdditions":
        additions: list[PendingAddition] = []
        rejected: list[RejectedFace] = []
        image = load_bgr_image(image_path)
        for face in self.detector.detect(image_path):
            quality = self.quality.evaluate(image, face)
            if quality.status == QualityStatus.BAD and not allow_bad_quality:
                rejected.append(
                    RejectedFace(
                        source_image=str(image_path),
                        face=face,
                        quality=quality,
                    )
                )
                continue
            vector = self.embedder.encode(image_path, face)
            matches = self.index.search(vector, self.config.top_k)
            additions.append(
                PendingAddition(
                    pending_id=str(uuid.uuid4()),
                    source_image=str(image_path),
                    face=face,
                    vector=vector,
                    matches=matches,
                    decision=self._decide(matches),
                    quality=quality,
                )
            )
        return PreparedAdditions(accepted=additions, rejected=rejected)

    def queue_additions(self, image_path: Path, allow_bad_quality: bool = False) -> "PreparedAdditions":
        prepared = self.prepare_additions_with_rejections(image_path, allow_bad_quality)
        for pending in prepared.accepted:
            self.store.save_pending_addition(pending)
        return prepared

    def list_pending_additions(self) -> list[PendingAddition]:
        return self.store.list_pending_additions()

    def get_person(self, person_id: str) -> Person | None:
        return self.store.get_person(person_id)

    def confirm_new_person(
        self,
        pending: PendingAddition,
        name: str,
        metadata: dict | None = None,
    ) -> str:
        person = self.store.create_person(name=name, metadata=metadata)
        record = self.store.add_embedding(
            person_id=person.person_id,
            vector=pending.vector,
            quality_score=pending.face.quality_score,
            source_image=pending.source_image,
            crop_path=pending.face.crop_path,
        )
        self.index.add(record)
        self.store.delete_pending_addition(pending.pending_id)
        return person.person_id

    def confirm_existing_person(self, pending: PendingAddition, person_id: str) -> str:
        record = self.store.add_embedding(
            person_id=person_id,
            vector=pending.vector,
            quality_score=pending.face.quality_score,
            source_image=pending.source_image,
            crop_path=pending.face.crop_path,
        )
        self.index.add(record)
        self.store.delete_pending_addition(pending.pending_id)
        return record.embedding_id

    def confirm_pending_as_new_person(self, pending_id: str, name: str) -> str:
        pending = self.store.get_pending_addition(pending_id)
        if pending is None:
            raise KeyError(f"Unknown pending addition: {pending_id}")
        return self.confirm_new_person(pending, name)

    def confirm_pending_as_existing_person(self, pending_id: str, person_id: str) -> str:
        pending = self.store.get_pending_addition(pending_id)
        if pending is None:
            raise KeyError(f"Unknown pending addition: {pending_id}")
        if self.store.get_person(person_id) is None:
            raise KeyError(f"Unknown person: {person_id}")
        return self.confirm_existing_person(pending, person_id)

    def reject_pending_addition(self, pending_id: str) -> None:
        self.store.delete_pending_addition(pending_id)

    def _decide(self, matches: list[Match]) -> MatchDecision:
        if not matches:
            return MatchDecision.UNKNOWN
        best = matches[0].score
        if best >= self.config.high_confidence:
            return MatchDecision.STRONG
        if best >= self.config.medium_confidence:
            return MatchDecision.AMBIGUOUS
        return MatchDecision.UNKNOWN


class PreparedAdditions:
    def __init__(self, accepted: list[PendingAddition], rejected: list[RejectedFace]) -> None:
        self.accepted = accepted
        self.rejected = rejected
