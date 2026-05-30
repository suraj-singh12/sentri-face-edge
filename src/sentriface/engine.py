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
    InitFace,
    InitGroup,
    InitSession,
    PendingAddition,
    Person,
    QualityStatus,
    RejectedFace,
    RecognitionResult,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


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

    def create_init_session(
        self,
        source_path: Path,
        allow_bad_quality: bool = False,
    ) -> InitSession:
        session = self.store.create_init_session(str(source_path))
        init_faces: list[InitFace] = []
        for image_path in _iter_images(source_path):
            image = load_bgr_image(image_path)
            for face in self.detector.detect(image_path):
                quality = self.quality.evaluate(image, face)
                if quality.status == QualityStatus.BAD and not allow_bad_quality:
                    continue
                vector = self.embedder.encode(image_path, face)
                init_faces.append(
                    InitFace(
                        init_face_id=str(uuid.uuid4()),
                        session_id=session.session_id,
                        group_id="unassigned",
                        source_image=str(image_path),
                        face=face,
                        vector=vector,
                        quality=quality,
                    )
                )
        grouped = _assign_groups(init_faces, threshold=self.config.high_confidence)
        self.store.save_init_faces(grouped)
        return session

    def list_init_groups(self, session_id: str) -> list[InitGroup]:
        if self.store.get_init_session(session_id) is None:
            raise KeyError(f"Unknown init session: {session_id}")
        return self.store.list_init_groups(session_id)

    def confirm_init_group(self, session_id: str, group_id: str, name: str) -> str:
        group = self._get_init_group(session_id, group_id)
        if group.status != "pending":
            raise KeyError(f"Init group is not pending: {group_id}")
        person = self.store.create_person(name=name)
        for face in group.faces:
            record = self.store.add_embedding(
                person_id=person.person_id,
                vector=face.vector,
                quality_score=face.quality.score,
                source_image=face.source_image,
                crop_path=face.face.crop_path,
            )
            self.index.add(record)
        self.store.mark_init_group_status(session_id, group_id, "confirmed")
        return person.person_id

    def reject_init_group(self, session_id: str, group_id: str) -> None:
        self._get_init_group(session_id, group_id)
        self.store.mark_init_group_status(session_id, group_id, "rejected")

    def _get_init_group(self, session_id: str, group_id: str) -> InitGroup:
        for group in self.list_init_groups(session_id):
            if group.group_id == group_id:
                return group
        raise KeyError(f"Unknown init group: {group_id}")

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


def _iter_images(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in IMAGE_EXTENSIONS else []
    if not source_path.exists():
        raise KeyError(f"Source path does not exist: {source_path}")
    return sorted(
        path
        for path in source_path.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _assign_groups(faces: list[InitFace], threshold: float) -> list[InitFace]:
    groups: list[list[InitFace]] = []
    for face in faces:
        best_group_index = None
        best_score = -1.0
        for index, group in enumerate(groups):
            score = max(_cosine(face.vector, existing.vector) for existing in group)
            if score > best_score:
                best_group_index = index
                best_score = score
        if best_group_index is None or best_score < threshold:
            groups.append([face])
        else:
            groups[best_group_index].append(face)

    assigned: list[InitFace] = []
    for index, group in enumerate(groups, start=1):
        group_id = f"group_{index:04d}"
        for face in group:
            assigned.append(
                InitFace(
                    init_face_id=face.init_face_id,
                    session_id=face.session_id,
                    group_id=group_id,
                    source_image=face.source_image,
                    face=face.face,
                    vector=face.vector,
                    quality=face.quality,
                    created_at=face.created_at,
                )
            )
    return assigned


def _cosine(left, right) -> float:
    return sum(a * b for a, b in zip(left, right))
