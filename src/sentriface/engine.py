from __future__ import annotations

import uuid
from pathlib import Path

from sentriface.components.image_ops import load_bgr_image
from sentriface.components.quality import FaceQualityEvaluator
from sentriface.config import RuntimeConfig
from sentriface.contracts import FaceDetector, FaceEmbedder, FaceIndex, IdentityStore
from sentriface.metrics import MetricsCollector
from sentriface.models import (
    Match,
    MatchDecision,
    InitFace,
    InitGroup,
    InitSession,
    PendingAddition,
    Person,
    PersonMatch,
    PersonSummary,
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
        self.metrics = MetricsCollector()

    def initialize(self) -> None:
        with self.metrics.timer("db_initialize_ms"):
            self.store.initialize()
        with self.metrics.timer("db_list_embeddings_ms"):
            embeddings = self.store.list_embeddings()
        self.metrics.increment("embeddings_loaded", len(embeddings))
        with self.metrics.timer("index_rebuild_ms"):
            self.index.rebuild(embeddings)

    def recognize(self, image_path: Path) -> list[RecognitionResult]:
        results: list[RecognitionResult] = []
        with self.metrics.timer("total_recognize_ms"):
            with self.metrics.timer("image_load_ms"):
                image = load_bgr_image(image_path)
            with self.metrics.timer("detect_ms"):
                faces = self.detector.detect(image_path)
            self.metrics.increment("faces_detected", len(faces))
            for face in faces:
                with self.metrics.timer("quality_ms"):
                    quality = self.quality.evaluate(image, face)
                with self.metrics.timer("embed_ms"):
                    vector = self.embedder.encode(image_path, face)
                with self.metrics.timer("search_ms"):
                    matches = self._search_unique_people(vector)
                self.metrics.increment("faces_recognized")
                self.metrics.increment(f"quality_{quality.status.value}")
                results.append(
                    RecognitionResult(
                        face=face,
                        matches=matches,
                        decision=self._decide(matches),
                        quality=quality,
                    )
                )
        return results

    def metrics_snapshot(self) -> dict:
        return self.metrics.snapshot()

    def reset_metrics(self) -> None:
        self.metrics = MetricsCollector()

    def _process_additions(
        self,
        image_path: Path,
        allow_bad_quality: bool,
    ) -> "PreparedAdditions":
        additions: list[PendingAddition] = []
        rejected: list[RejectedFace] = []
        with self.metrics.timer("image_load_ms"):
            image = load_bgr_image(image_path)
        with self.metrics.timer("detect_ms"):
            faces = self.detector.detect(image_path)
        self.metrics.increment("faces_detected", len(faces))
        for face in faces:
            with self.metrics.timer("quality_ms"):
                quality = self.quality.evaluate(image, face)
            self.metrics.increment(f"quality_{quality.status.value}")
            if quality.status == QualityStatus.BAD and not allow_bad_quality:
                rejected.append(
                    RejectedFace(
                        source_image=str(image_path),
                        face=face,
                        quality=quality,
                    )
                )
                self.metrics.increment("faces_rejected")
                continue
            with self.metrics.timer("embed_ms"):
                vector = self.embedder.encode(image_path, face)
            with self.metrics.timer("search_ms"):
                matches = self._search_unique_people(vector)
            self.metrics.increment("faces_accepted")
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

    def prepare_additions(self, image_path: Path, allow_bad_quality: bool = False) -> list[PendingAddition]:
        prepared = self.prepare_additions_with_rejections(image_path, allow_bad_quality)
        return prepared.accepted

    def prepare_additions_with_rejections(
        self,
        image_path: Path,
        allow_bad_quality: bool = False,
    ) -> "PreparedAdditions":
        with self.metrics.timer("total_prepare_additions_ms"):
            return self._process_additions(image_path, allow_bad_quality)

    def queue_additions(self, image_path: Path, allow_bad_quality: bool = False) -> "PreparedAdditions":
        prepared = self.prepare_additions_with_rejections(image_path, allow_bad_quality)
        for pending in prepared.accepted:
            with self.metrics.timer("db_save_pending_ms"):
                self.store.save_pending_addition(pending)
        return prepared

    def list_pending_additions(self) -> list[PendingAddition]:
        with self.metrics.timer("db_list_pending_ms"):
            return self.store.list_pending_additions()

    def get_person(self, person_id: str) -> Person | None:
        with self.metrics.timer("db_get_person_ms"):
            return self.store.get_person(person_id)

    def list_persons(self) -> list[PersonSummary]:
        with self.metrics.timer("db_list_persons_ms"):
            return self.store.list_persons()

    def list_person_embeddings(self, person_id: str):
        if self.store.get_person(person_id) is None:
            raise KeyError(f"Unknown person: {person_id}")
        with self.metrics.timer("db_list_person_embeddings_ms"):
            return self.store.list_embeddings_for_person(person_id)

    def rename_person(self, person_id: str, name: str) -> None:
        with self.metrics.timer("db_rename_person_ms"):
            self.store.rename_person(person_id, name)

    def delete_person(self, person_id: str) -> None:
        with self.metrics.timer("db_delete_person_ms"):
            self.store.delete_person(person_id)
        self._rebuild_index()

    def delete_embedding(self, embedding_id: str) -> None:
        with self.metrics.timer("db_delete_embedding_ms"):
            self.store.delete_embedding(embedding_id)
        self._rebuild_index()

    def confirm_new_person(
        self,
        pending: PendingAddition,
        name: str,
        metadata: dict | None = None,
    ) -> str:
        with self.metrics.timer("db_create_person_ms"):
            person = self.store.create_person(name=name, metadata=metadata)
        with self.metrics.timer("db_add_embedding_ms"):
            record = self.store.add_embedding(
                person_id=person.person_id,
                vector=pending.vector,
                quality_score=pending.face.quality_score,
                source_image=pending.source_image,
                crop_path=pending.face.crop_path,
            )
        with self.metrics.timer("index_add_ms"):
            self.index.add(record)
        with self.metrics.timer("db_delete_pending_ms"):
            self.store.delete_pending_addition(pending.pending_id)
        return person.person_id

    def confirm_existing_person(self, pending: PendingAddition, person_id: str) -> str:
        with self.metrics.timer("db_add_embedding_ms"):
            record = self.store.add_embedding(
                person_id=person_id,
                vector=pending.vector,
                quality_score=pending.face.quality_score,
                source_image=pending.source_image,
                crop_path=pending.face.crop_path,
            )
        with self.metrics.timer("index_add_ms"):
            self.index.add(record)
        with self.metrics.timer("db_delete_pending_ms"):
            self.store.delete_pending_addition(pending.pending_id)
        return record.embedding_id

    def confirm_pending_as_new_person(self, pending_id: str, name: str) -> str:
        with self.metrics.timer("db_get_pending_ms"):
            pending = self.store.get_pending_addition(pending_id)
        if pending is None:
            raise KeyError(f"Unknown pending addition: {pending_id}")
        return self.confirm_new_person(pending, name)

    def confirm_pending_as_existing_person(self, pending_id: str, person_id: str) -> str:
        with self.metrics.timer("db_get_pending_ms"):
            pending = self.store.get_pending_addition(pending_id)
        if pending is None:
            raise KeyError(f"Unknown pending addition: {pending_id}")
        if self.store.get_person(person_id) is None:
            raise KeyError(f"Unknown person: {person_id}")
        return self.confirm_existing_person(pending, person_id)

    def reject_pending_addition(self, pending_id: str) -> None:
        with self.metrics.timer("db_delete_pending_ms"):
            self.store.delete_pending_addition(pending_id)

    def create_init_session(
        self,
        source_path: Path,
        allow_bad_quality: bool = False,
    ) -> InitSession:
        with self.metrics.timer("total_init_scan_ms"):
            with self.metrics.timer("db_create_init_session_ms"):
                session = self.store.create_init_session(str(source_path))
            image_paths = _iter_images(source_path)
            self.metrics.increment("images_scanned", len(image_paths))
            init_faces: list[InitFace] = []
            for image_path in image_paths:
                with self.metrics.timer("image_load_ms"):
                    image = load_bgr_image(image_path)
                with self.metrics.timer("detect_ms"):
                    faces = self.detector.detect(image_path)
                self.metrics.increment("faces_detected", len(faces))
                for face in faces:
                    with self.metrics.timer("quality_ms"):
                        quality = self.quality.evaluate(image, face)
                    self.metrics.increment(f"quality_{quality.status.value}")
                    if quality.status == QualityStatus.BAD and not allow_bad_quality:
                        self.metrics.increment("faces_rejected")
                        continue
                    with self.metrics.timer("embed_ms"):
                        vector = self.embedder.encode(image_path, face)
                    self.metrics.increment("faces_accepted")
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
            with self.metrics.timer("cluster_ms"):
                grouped = _assign_groups(init_faces, threshold=self.config.high_confidence)
            self.metrics.increment("init_groups", len({face.group_id for face in grouped}))
            with self.metrics.timer("db_save_init_faces_ms"):
                self.store.save_init_faces(grouped)
            return session

    def list_init_groups(self, session_id: str) -> list[InitGroup]:
        with self.metrics.timer("db_get_init_session_ms"):
            session = self.store.get_init_session(session_id)
        if session is None:
            raise KeyError(f"Unknown init session: {session_id}")
        with self.metrics.timer("db_list_init_groups_ms"):
            return self.store.list_init_groups(session_id)

    def confirm_init_group(self, session_id: str, group_id: str, name: str) -> str:
        group = self._get_init_group(session_id, group_id)
        if group.status != "pending":
            raise KeyError(f"Init group is not pending: {group_id}")
        with self.metrics.timer("db_create_person_ms"):
            person = self.store.create_person(name=name)
        for face in group.faces:
            with self.metrics.timer("db_add_embedding_ms"):
                record = self.store.add_embedding(
                    person_id=person.person_id,
                    vector=face.vector,
                    quality_score=face.quality.score,
                    source_image=face.source_image,
                    crop_path=face.face.crop_path,
                )
            with self.metrics.timer("index_add_ms"):
                self.index.add(record)
        with self.metrics.timer("db_mark_init_group_ms"):
            self.store.mark_init_group_status(session_id, group_id, "confirmed")
        return person.person_id

    def reject_init_group(self, session_id: str, group_id: str) -> None:
        self._get_init_group(session_id, group_id)
        with self.metrics.timer("db_mark_init_group_ms"):
            self.store.mark_init_group_status(session_id, group_id, "rejected")

    def _get_init_group(self, session_id: str, group_id: str) -> InitGroup:
        for group in self.list_init_groups(session_id):
            if group.group_id == group_id:
                return group
        raise KeyError(f"Unknown init group: {group_id}")

    def _rebuild_index(self) -> None:
        with self.metrics.timer("db_list_embeddings_ms"):
            embeddings = self.store.list_embeddings()
        with self.metrics.timer("index_rebuild_ms"):
            self.index.rebuild(embeddings)

    def _search_unique_people(self, vector) -> list[PersonMatch]:
        raw_matches = self.index.search(vector, max(self.config.top_k * 8, self.config.top_k))
        grouped: dict[str, list[Match]] = {}
        for match in raw_matches:
            grouped.setdefault(match.person_id, []).append(match)
        person_matches = [
            PersonMatch(
                person_id=person_id,
                score=max(match.score for match in matches),
                embedding_ids=tuple(match.embedding_id for match in matches),
                embeddings_matched=len(matches),
            )
            for person_id, matches in grouped.items()
        ]
        person_matches.sort(key=lambda match: match.score, reverse=True)
        return person_matches[: self.config.top_k]

    def _decide(self, matches: list[PersonMatch]) -> MatchDecision:
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
