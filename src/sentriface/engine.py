from __future__ import annotations

import uuid
import threading
from contextvars import ContextVar
from math import sqrt
from pathlib import Path
from typing import Callable

from sentriface.components.image_ops import load_bgr_image, save_face_crop
from sentriface.components.linear_index import LinearFaceIndex
from sentriface.cleanup_service import CleanupService
from sentriface.components.quality import FaceQualityEvaluator
from sentriface.config import RuntimeConfig
from sentriface.contracts import FaceDetector, FaceEmbedder, FaceIndex, IdentityStore
from sentriface.errors import InputImageError, QueueCancellationError
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.metrics import MetricsCollector
from sentriface.models import (
    FaceBox,
    Match,
    MatchDecision,
    InitFace,
    InitGroup,
    InitSession,
    Observation,
    ObservationMedia,
    ObservationParticipant,
    PendingAddition,
    Person,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PersonSummary,
    RankedPersonCandidate,
    QualityStatus,
    RejectedFace,
    RecognitionResult,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DUPLICATE_MATCH_SCORE = 0.9999
QUEUE_POSSIBLE_MATCH_THRESHOLD = 0.40
MAX_QUEUE_IMAGES = 10_000


class _SynchronizedFaceIndex:
    """Serializes reads and atomically swaps complete index generations."""

    def __init__(self, index: FaceIndex) -> None:
        self._index = index
        self._lock = threading.RLock()

    @property
    def backend_name(self) -> str:
        with self._lock:
            return str(getattr(self._index, "backend_name", type(self._index).__name__))

    def replace(self, index: FaceIndex) -> None:
        with self._lock:
            self._index = index

    def rebuild(self, embeddings):
        with self._lock:
            self._index.rebuild(embeddings)

    def add(self, record):
        with self._lock:
            self._index.add(record)

    def search(self, vector, top_k):
        with self._lock:
            return self._index.search(vector, top_k)

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
        self.index = _SynchronizedFaceIndex(index)
        self.store = store
        self.graph = GlobalIdentityGraphService(store)
        self.index_degraded_reason: str | None = (
            "requested backend unavailable"
            if config.index_backend != self.index.backend_name
            else None
        )
        self.quality = FaceQualityEvaluator(config)
        self._metrics_context: ContextVar[MetricsCollector | None] = ContextVar("sentriface_metrics", default=None)
        self.cleanup = CleanupService(
            config.data_dir,
            (
                config.data_dir / "uploads",
                config.face_dir / "pending",
                config.face_dir / "init",
                config.data_dir / "restored-media",
            ),
        )

    @property
    def metrics(self) -> MetricsCollector:
        collector = self._metrics_context.get()
        if collector is None:
            collector = MetricsCollector()
            self._metrics_context.set(collector)
        return collector
    def initialize(self) -> None:
        with self.metrics.timer("storage_prepare_ms"):
            self.config.data_dir.mkdir(parents=True, exist_ok=True)
            self.config.face_dir.mkdir(parents=True, exist_ok=True)
            self.config.index_dir.mkdir(parents=True, exist_ok=True)
        with self.metrics.timer("db_initialize_ms"):
            self.store.initialize()
        self.cleanup.retry_all(self.store.list_all_file_references)
        self._rebuild_index()
        self.metrics.increment("embeddings_loaded", len(self.store.list_embeddings()))

    def recognize(self, image_path: Path) -> list[RecognitionResult]:
        results: list[RecognitionResult] = []
        with self.metrics.timer("total_recognize_ms"):
            with self.metrics.timer("image_load_ms"):
                image = load_bgr_image(image_path, self.config.storage_key)
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
        self._metrics_context.set(MetricsCollector())
    def _process_additions(
        self,
        image_path: Path,
        allow_bad_quality: bool,
        face_index: int | None = None,
        expected_box: FaceBox | None = None,
    ) -> "PreparedAdditions":
        additions: list[PendingAddition] = []
        rejected: list[RejectedFace] = []
        canonical_source = _canonical_source_path(image_path, self.config.data_dir)
        with self.metrics.timer("image_load_ms"):
            image = load_bgr_image(image_path, self.config.storage_key)
        with self.metrics.timer("detect_ms"):
            faces = self.detector.detect(image_path)
        self.metrics.increment("faces_detected", len(faces))
        if face_index is not None:
            if face_index < 1 or face_index > len(faces):
                raise KeyError(f"Face {face_index} is no longer available in this image")
            selected_face = faces[face_index - 1]
            if expected_box is not None and _box_iou(selected_face.box, expected_box) < 0.5:
                selected_face = max(faces, key=lambda face: _box_iou(face.box, expected_box))
                if _box_iou(selected_face.box, expected_box) < 0.5:
                    raise KeyError(f"Face {face_index} is no longer available in this image")
            indexed_faces = [(face_index, selected_face)]
        else:
            indexed_faces = list(enumerate(faces, start=1))
        for _, face in indexed_faces:
            with self.metrics.timer("quality_ms"):
                quality = self.quality.evaluate(image, face)
            self.metrics.increment(f"quality_{quality.status.value}")
            if quality.status == QualityStatus.BAD and not allow_bad_quality:
                rejected.append(
                    RejectedFace(
                        source_image=canonical_source,
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
            pending_id = str(uuid.uuid4())
            with self.metrics.timer("crop_save_ms"):
                crop_path = save_face_crop(
                    image,
                    face,
                    self.config.face_dir / "pending" / f"{pending_id}.jpg",
                    storage_key=self.config.storage_key,
                )
            additions.append(
                PendingAddition(
                    pending_id=pending_id,
                    source_image=canonical_source,
                    face=_with_crop_path(face, crop_path),
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

    def prepare_face_addition(
        self,
        image_path: Path,
        face_index: int,
        allow_bad_quality: bool = False,
        expected_box: FaceBox | None = None,
    ) -> PendingAddition | None:
        """Prepare exactly the face selected in a previous recognition response."""
        with self.metrics.timer("total_prepare_additions_ms"):
            prepared = self._process_additions(
                image_path,
                allow_bad_quality,
                face_index=face_index,
                expected_box=expected_box,
            )
        return prepared.accepted[0] if prepared.accepted else None

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

    def get_person(self, person_id: str, include_archived: bool = False) -> Person | None:
        with self.metrics.timer("db_get_person_ms"):
            return self.store.get_person(person_id, include_archived=include_archived)

    def list_persons(self, archived: bool = False) -> list[PersonSummary]:
        with self.metrics.timer("db_list_persons_ms"):
            return self.store.list_persons(archived=archived)

    def create_placeholder_person(
        self,
        name: str,
        metadata: dict | None,
        editor_name: str,
        operation_id: str,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> Person:
        with self.metrics.timer("db_create_placeholder_person_ms"):
            return self.store.create_placeholder_person(
                name=name,
                metadata=metadata,
                editor_name=editor_name,
                operation_id=operation_id,
                notes=notes,
                mentioned_person_ids=mentioned_person_ids,
            )

    def list_person_embeddings(self, person_id: str, include_archived: bool = False):
        if self.store.get_person(person_id, include_archived=include_archived) is None:
            raise KeyError(f"Unknown person: {person_id}")
        with self.metrics.timer("db_list_person_embeddings_ms"):
            return self.store.list_embeddings_for_person(
                person_id,
                include_archived=include_archived,
            )

    def rename_person(self, person_id: str, name: str) -> None:
        with self.metrics.timer("db_rename_person_ms"):
            self.store.rename_person(person_id, name)

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
        with self.metrics.timer("db_update_person_profile_ms"):
            return self.store.update_person_profile(
                person_id=person_id,
                name=name,
                rank=rank,
                country=country,
                importance=importance,
                editor_name=editor_name,
                tags=tags,
                operation_id=operation_id,
            )

    def list_person_changes(
        self,
        person_id: str,
        include_archived: bool = False,
    ) -> list[PersonChange]:
        if self.store.get_person(person_id, include_archived=include_archived) is None:
            raise KeyError(f"Unknown person: {person_id}")
        with self.metrics.timer("db_list_person_changes_ms"):
            return self.store.list_person_changes(person_id)

    def update_person_notes(
        self, person_id: str, notes: str, expected_previous_notes: str,
        editor_name: str, operation_id: str, mentioned_person_ids: list[str] | None = None,
    ) -> tuple[bool, Person, PersonChange | None]:
        with self.metrics.timer("db_update_person_notes_ms"):
            return self.store.update_person_notes(
                person_id, notes, expected_previous_notes, editor_name, operation_id,
                mentioned_person_ids,
            )

    def list_person_operations(
        self,
        person_id: str,
        include_archived: bool = False,
    ) -> list[dict]:
        if self.store.get_person(person_id, include_archived=include_archived) is None:
            raise KeyError(f"Unknown person: {person_id}")
        with self.metrics.timer("db_list_person_operations_ms"):
            return self.store.list_person_operations(person_id)

    def create_person_association(
        self,
        source_person_id: str,
        target_person_id: str,
        actor_name: str,
        operation_id: str,
    ) -> PersonAssociation:
        with self.metrics.timer("db_create_person_association_ms"):
            return self.store.create_person_association(
                source_person_id,
                target_person_id,
                actor_name,
                operation_id,
            )

    def create_placeholder_association(
        self,
        source_person_id: str,
        name: str,
        metadata: dict | None,
        actor_name: str,
        operation_id: str,
    ) -> tuple[Person, PersonAssociation]:
        with self.metrics.timer("db_create_placeholder_association_ms"):
            return self.store.create_placeholder_association(
                source_person_id,
                name,
                metadata,
                actor_name,
                operation_id,
            )

    def list_person_associations(
        self,
        person_id: str,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[PersonAssociation]:
        with self.metrics.timer("db_list_person_associations_ms"):
            return self.store.list_person_associations(
                person_id,
                include_archived=include_archived,
                limit=limit,
            )

    def remove_person_association(
        self,
        association_id: str,
        actor_name: str,
        operation_id: str,
    ) -> dict:
        with self.metrics.timer("db_remove_person_association_ms"):
            return self.store.remove_person_association(
                association_id,
                actor_name,
                operation_id,
            )

    def get_person_operation(self, operation_id: str, operation_type: str) -> dict | None:
        return self.store.get_person_operation(operation_id, operation_type)

    def begin_operation(self, operation_type: str, **metadata) -> dict:
        return self.store.begin_operation(operation_type, **metadata)

    def mark_operation_committed(self, operation_id: str, details: dict | None = None) -> dict:
        return self.store.mark_operation_committed(operation_id, details)

    def mark_operation_failed(self, operation_id: str, details: dict | None = None) -> dict:
        return self.store.mark_operation_failed(operation_id, details)

    def mark_operation_rolled_back(self, operation_id: str, details: dict | None = None) -> dict:
        return self.store.mark_operation_rolled_back(operation_id, details)

    def mark_operation_reverted(self, operation_id: str, details: dict | None = None) -> dict:
        return self.store.mark_operation_reverted(operation_id, details)

    def get_operation(self, operation_id: str) -> dict | None:
        return self.store.get_operation(operation_id)

    def list_recent_operations(self, limit: int = 50) -> list[dict]:
        return self.store.list_recent_operations(limit)

    def create_observation(self, operation_id: str, **values) -> Observation:
        return self.store.create_observation(operation_id, **values)

    def get_observation(self, observation_id: str) -> Observation | None:
        return self.store.get_observation(observation_id)

    def update_observation(
        self, observation_id: str, operation_id: str, **values,
    ) -> Observation:
        return self.store.update_observation(observation_id, operation_id, **values)

    def attach_observation_media(
        self, observation_id: str, media_id: str, operation_id: str, **values,
    ) -> ObservationMedia:
        return self.store.attach_observation_media(
            observation_id, media_id, operation_id, **values,
        )

    def add_observation_participant(
        self, observation_id: str, person_id: str, operation_id: str, **values,
    ) -> ObservationParticipant:
        return self.store.add_observation_participant(
            observation_id, person_id, operation_id, **values,
        )

    def remove_observation_participant(
        self, observation_id: str, person_id: str, operation_id: str, **values,
    ) -> dict:
        return self.store.remove_observation_participant(
            observation_id, person_id, operation_id, **values,
        )

    def list_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        return self.store.list_observation_participants(observation_id)

    def list_observation_media(self, observation_id: str) -> list[ObservationMedia]:
        return self.store.list_observation_media(observation_id)

    def finalize_observation(
        self, observation_id: str, operation_id: str, **values,
    ) -> Observation:
        return self.store.finalize_observation(observation_id, operation_id, **values)

    def list_observations_for_person(self, person_id: str) -> list[Observation]:
        return self.store.list_observations_for_person(person_id)

    def list_observations_for_media(self, media_id: str) -> list[Observation]:
        return self.store.list_observations_for_media(media_id)

    def get_embedding_lifecycle(self, embedding_id: str) -> dict | None:
        return self.store.get_embedding_lifecycle(embedding_id)

    def get_person_lifecycle(self, person_id: str) -> dict | None:
        return self.store.get_person_lifecycle(person_id)

    def resolve_canonical_person_id(self, person_id: str) -> str:
        return self.store.resolve_canonical_person_id(person_id)

    def list_historical_persons(self) -> list[PersonSummary]:
        return self.store.list_historical_persons()

    def list_recognition_details_for_person(
        self,
        person_id: str,
        include_archived: bool = False,
    ):
        if self.store.get_person(person_id, include_archived=include_archived) is None:
            raise KeyError(f"Unknown person: {person_id}")
        with self.metrics.timer("db_list_recognition_details_for_person_ms"):
            return self.store.list_recognition_details_for_person(person_id)

    def archive_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        with self.metrics.timer("db_delete_person_ms"):
            result = self.store.archive_person(person_id, operation_id, actor, source)
        self._rebuild_index()
        return result

    def restore_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        with self.metrics.timer("db_restore_person_ms"):
            result = self.store.restore_person(person_id, operation_id, actor, source)
        self._rebuild_index()
        return result

    def soft_delete_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        with self.metrics.timer("db_purge_person_ms"):
            result = self.store.soft_delete_person(person_id, operation_id, actor, source)
        self._rebuild_index()
        return result

    def permanently_delete_person(
        self, person_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        with self.metrics.timer("db_purge_person_ms"):
            result = self.store.permanently_delete_person(person_id, operation_id, actor, source)
        self._rebuild_index()
        return result

    def set_canonical_person_id(
        self,
        person_id: str,
        canonical_person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        result = self.store.set_canonical_person_id(
            person_id, canonical_person_id, operation_id, actor, source,
        )
        self._rebuild_index()
        return result

    def delete_person(self, person_id: str) -> None:
        self.archive_person(person_id, str(uuid.uuid4()))

    def delete_embedding(self, embedding_id: str, operation_id: str | None = None) -> dict:
        with self.metrics.timer("db_soft_delete_embedding_ms"):
            result = self.store.delete_embedding(embedding_id, operation_id or str(uuid.uuid4()))
        self._rebuild_index()
        return result

    def list_deleted_embeddings(self) -> list[dict]:
        with self.metrics.timer("db_list_deleted_embeddings_ms"):
            return self.store.list_deleted_embeddings()

    def restore_deleted_embedding(
        self,
        embedding_id: str,
        operation_id: str | None = None,
    ) -> dict:
        with self.metrics.timer("db_restore_deleted_embedding_ms"):
            result = self.store.restore_deleted_embedding(
                embedding_id,
                operation_id or str(uuid.uuid4()),
            )
        self._rebuild_index()
        return result

    def permanently_delete_embedding(
        self,
        embedding_id: str,
        operation_id: str | None = None,
    ) -> dict:
        lifecycle = self.store.get_embedding_lifecycle(embedding_id)
        journal = self.cleanup.schedule(
            (
                lifecycle.get("source_image") if lifecycle else None,
                lifecycle.get("crop_path") if lifecycle else None,
            ),
            f"purge-embedding-{embedding_id}",
        )
        with self.metrics.timer("db_purge_deleted_embedding_ms"):
            result = self.store.permanently_delete_embedding(
                embedding_id,
                operation_id or str(uuid.uuid4()),
            )
        self._rebuild_index()
        self.cleanup.run(journal, self.store.list_all_file_references)
        return result

    def list_expired_deleted_embedding_ids(self, now: str | None = None) -> list[str]:
        return self.store.list_expired_deleted_embedding_ids(now)

    def purge_expired_deleted_embeddings(
        self,
        embedding_ids: list[str],
        operation_id: str,
        now: str | None = None,
    ) -> dict:
        lifecycles = [self.store.get_embedding_lifecycle(item) for item in embedding_ids]
        journal = self.cleanup.schedule(
            (
                path
                for lifecycle in lifecycles
                if lifecycle
                for path in (lifecycle.get("source_image"), lifecycle.get("crop_path"))
            ),
            f"purge-expired-{operation_id}",
        )
        with self.metrics.timer("db_purge_expired_embeddings_ms"):
            result = self.store.purge_expired_deleted_embeddings(
                embedding_ids,
                operation_id,
                now,
            )
        self._rebuild_index()
        self.cleanup.run(journal, self.store.list_all_file_references)
        return result

    def move_embedding(
        self,
        embedding_id: str,
        person_id: str,
        operation_id: str | None = None,
    ) -> dict:
        with self.metrics.timer("db_move_embedding_ms"):
            result = self.store.move_embedding(
                embedding_id,
                person_id,
                operation_id or str(uuid.uuid4()),
            )
        self._rebuild_index()
        return result

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
        operation_id: str | None = None,
    ) -> str:
        with self.metrics.timer("db_add_recognition_detail_ms"):
            detail = self.store.add_recognition_detail(
                embedding_id=embedding_id,
                person_id=person_id,
                image_id=image_id,
                image_path=image_path,
                name=name,
                decision=decision,
                seen_date=seen_date,
                seen_time=seen_time,
                place_seen=place_seen,
                individual_count=individual_count,
                event_occasion=event_occasion,
                rank=rank,
                country=country,
                importance=importance,
                added_by=added_by,
                notes=notes,
                mentioned_person_ids=mentioned_person_ids,
                operation_id=operation_id,
            )
        return detail.detail_id

    def merge_persons(
        self,
        source_person_id: str,
        target_person_id: str,
        operation_id: str | None = None,
    ) -> dict:
        result = self.store.merge_persons(
            source_person_id,
            target_person_id,
            operation_id or str(uuid.uuid4()),
        )
        self._rebuild_index()
        return result

    def undo_merge_persons(self, merge_operation_id: str, operation_id: str) -> dict:
        result = self.store.undo_merge_persons(merge_operation_id, operation_id)
        self._rebuild_index()
        return result

    def update_person_preferences(
        self,
        person_id: str,
        operation_id: str,
        favorite: bool | None = None,
        representative_embedding_id: str | None = None,
    ) -> dict:
        return self.store.update_person_preferences(
            person_id=person_id,
            operation_id=operation_id,
            favorite=favorite,
            representative_embedding_id=representative_embedding_id,
        )

    def backup_database(self, target_path: Path) -> None:
        with self.metrics.timer("db_backup_ms"):
            self.store.backup_to(target_path)

    def confirm_new_person(
        self,
        pending: PendingAddition,
        name: str,
        metadata: dict | None = None,
        operation_id: str | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> str:
        with self.metrics.timer("db_save_pending_ms"):
            self.store.save_pending_addition(pending)
        with self.metrics.timer("db_confirm_pending_ms"):
            person, _record = self.store.confirm_pending_addition(
                pending.pending_id,
                operation_id or str(uuid.uuid4()),
                name=name,
                metadata=metadata,
                notes=notes,
                mentioned_person_ids=mentioned_person_ids,
            )
        self._rebuild_index()
        return person.person_id

    def confirm_existing_person(
        self,
        pending: PendingAddition,
        person_id: str,
        operation_id: str | None = None,
    ) -> str:
        try:
            with self.metrics.timer("db_save_pending_ms"):
                self.store.save_pending_addition(pending)
            with self.metrics.timer("db_confirm_pending_ms"):
                _person, record = self.store.confirm_pending_addition(
                    pending.pending_id,
                    operation_id or str(uuid.uuid4()),
                    person_id=person_id,
                )
        except Exception:
            self.discard_prepared_addition(pending)
            raise
        self._rebuild_index()
        return record.embedding_id

    def confirm_existing_person_with_detail(
        self,
        pending: PendingAddition,
        person_id: str,
        recognition_detail: dict,
        operation_id: str | None = None,
    ) -> str:
        try:
            with self.metrics.timer("db_save_pending_ms"):
                self.store.save_pending_addition(pending)
            with self.metrics.timer("db_confirm_pending_ms"):
                _person, record = self.store.confirm_pending_addition(
                    pending.pending_id,
                    operation_id or str(uuid.uuid4()),
                    person_id=person_id,
                    recognition_detail=recognition_detail,
                )
        except Exception:
            self.discard_prepared_addition(pending)
            raise
        self._rebuild_index()
        return record.embedding_id

    def discard_prepared_addition(self, pending: PendingAddition) -> None:
        journal = self.cleanup.schedule(
            (pending.source_image, pending.face.crop_path),
            f"discard-prepared-{pending.pending_id}",
        )
        try:
            self.store.delete_pending_addition(pending.pending_id)
        finally:
            self.cleanup.run(journal, self.store.list_all_file_references)
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
        pending = self.store.get_pending_addition(pending_id)
        journal = self.cleanup.schedule(
            (pending.source_image, pending.face.crop_path) if pending else (),
            f"reject-pending-{pending_id}",
        )
        with self.metrics.timer("db_delete_pending_ms"):
            self.store.delete_pending_addition(pending_id)
        self.cleanup.run(journal, self.store.list_all_file_references)
    def create_init_session(
        self,
        source_path: Path,
        allow_bad_quality: bool = False,
    ) -> InitSession:
        return self._create_init_session(source_path, allow_bad_quality).session

    def create_queue_session(
        self,
        source_path: Path,
        allow_bad_quality: bool = False,
        progress_callback: Callable[[dict], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> "QueueSessionResult":
        return self._create_init_session(
            source_path,
            allow_bad_quality,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def _create_init_session(
        self,
        source_path: Path,
        allow_bad_quality: bool = False,
        progress_callback: Callable[[dict], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> "QueueSessionResult":
        def report(**payload) -> None:
            if progress_callback:
                progress_callback(payload)

        with self.metrics.timer("total_init_scan_ms"):
            with self.metrics.timer("db_create_init_session_ms"):
                session = self.store.create_init_session(str(source_path))

            def cancellation_checkpoint(phase: str) -> None:
                if cancel_check is not None and cancel_check():
                    report(
                        phase="cancelling",
                        status="cancelling",
                        session_id=session.session_id,
                        cancellation_phase=phase,
                    )
                    raise QueueCancellationError(session.session_id, phase)

            try:
                cancellation_checkpoint("discovering_images")
                image_paths = _iter_images(source_path, cancellation_checkpoint)
                self.metrics.increment("images_scanned", len(image_paths))
                report(
                    phase="detecting",
                    session_id=session.session_id,
                    total_images=len(image_paths),
                    images_scanned=0,
                    faces_detected=0,
                    embeddings_generated=0,
                    groups=0,
                )
                init_faces: list[InitFace] = []
                embeddings_generated = 0
                invalid_images: list[str] = []
                for image_index, image_path in enumerate(image_paths, start=1):
                    cancellation_checkpoint("before_image")
                    canonical_source = _canonical_source_path(image_path, self.config.data_dir)
                    try:
                        with self.metrics.timer("image_load_ms"):
                            image = load_bgr_image(image_path, self.config.storage_key)
                    except InputImageError:
                        invalid_images.append(str(image_path))
                        self.metrics.increment("images_rejected")
                        report(
                            phase="detecting",
                            session_id=session.session_id,
                            total_images=len(image_paths),
                            images_scanned=image_index,
                            invalid_images=len(invalid_images),
                            faces_detected=len(init_faces),
                            embeddings_generated=embeddings_generated,
                            groups=0,
                        )
                        continue
                    cancellation_checkpoint("before_detection")
                    with self.metrics.timer("detect_ms"):
                        faces = self.detector.detect(image_path)
                    cancellation_checkpoint("after_detection")
                    self.metrics.increment("faces_detected", len(faces))
                    for face in faces:
                        cancellation_checkpoint("before_face")
                        with self.metrics.timer("quality_ms"):
                            quality = self.quality.evaluate(image, face)
                        self.metrics.increment(f"quality_{quality.status.value}")
                        if quality.status == QualityStatus.BAD and not allow_bad_quality:
                            self.metrics.increment("faces_rejected")
                            continue
                        cancellation_checkpoint("before_embedding")
                        with self.metrics.timer("embed_ms"):
                            vector = self.embedder.encode(image_path, face)
                        cancellation_checkpoint("after_embedding")
                        embeddings_generated += 1
                        self.metrics.increment("faces_accepted")
                        init_face_id = str(uuid.uuid4())
                        with self.metrics.timer("crop_save_ms"):
                            crop_path = save_face_crop(
                                image,
                                face,
                                self.config.face_dir / "init" / session.session_id / f"{init_face_id}.jpg",
                                storage_key=self.config.storage_key,
                            )
                        init_faces.append(
                            InitFace(
                                init_face_id=init_face_id,
                                session_id=session.session_id,
                                group_id="unassigned",
                                source_image=canonical_source,
                                face=_with_crop_path(face, crop_path),
                                vector=vector,
                                quality=quality,
                            )
                        )
                        cancellation_checkpoint("after_face")
                    report(
                        phase="detecting" if image_index < len(image_paths) else "matching",
                        session_id=session.session_id,
                        total_images=len(image_paths),
                        images_scanned=image_index,
                        faces_detected=len(init_faces),
                        embeddings_generated=embeddings_generated,
                        groups=0,
                    )
                cancellation_checkpoint("before_matching")
                report(
                    phase="matching",
                    session_id=session.session_id,
                    total_images=len(image_paths),
                    images_scanned=len(image_paths),
                    faces_detected=len(init_faces),
                    embeddings_generated=embeddings_generated,
                    groups=0,
                )
                matches_by_face_id: dict[str, list[PersonMatch]] = {}
                with self.metrics.timer("search_ms"):
                    for face in init_faces:
                        cancellation_checkpoint("matching_face")
                        matches_by_face_id[face.init_face_id] = self._search_unique_people(face.vector)
                cancellation_checkpoint("before_clustering")
                report(
                    phase="clustering",
                    session_id=session.session_id,
                    total_images=len(image_paths),
                    images_scanned=len(image_paths),
                    faces_detected=len(init_faces),
                    embeddings_generated=embeddings_generated,
                    groups=0,
                )
                with self.metrics.timer("cluster_ms"):
                    grouped = _assign_groups(
                        init_faces,
                        threshold=self.config.high_confidence,
                        medium_threshold=self.config.medium_confidence,
                        matches_by_face_id=matches_by_face_id,
                    )
                cancellation_checkpoint("after_clustering")
                group_count = len({face.group_id for face in grouped})
                self.metrics.increment("init_groups", group_count)
                report(
                    phase="preparing",
                    session_id=session.session_id,
                    total_images=len(image_paths),
                    images_scanned=len(image_paths),
                    faces_detected=len(init_faces),
                    embeddings_generated=embeddings_generated,
                    groups=group_count,
                )
                cancellation_checkpoint("before_save")
                with self.metrics.timer("db_save_init_faces_ms"):
                    self.store.save_init_faces(grouped)
                cancellation_checkpoint("after_save")
                report(
                    phase="done",
                    session_id=session.session_id,
                    total_images=len(image_paths),
                    images_scanned=len(image_paths),
                    faces_detected=len(init_faces),
                    embeddings_generated=embeddings_generated,
                    groups=group_count,
                    invalid_images=len(invalid_images),
                )
                return QueueSessionResult(
                    session=session,
                    groups=_groups_from_faces(session.session_id, grouped),
                    matches_by_face_id=matches_by_face_id,
                    invalid_images=invalid_images,
                )
            except QueueCancellationError:
                try:
                    self.discard_init_session(session.session_id)
                finally:
                    raise
            except Exception:
                try:
                    self.discard_init_session(session.session_id)
                finally:
                    raise

    def list_init_groups(self, session_id: str) -> list[InitGroup]:
        with self.metrics.timer("db_get_init_session_ms"):
            session = self.store.get_init_session(session_id)
        if session is None:
            raise KeyError(f"Unknown init session: {session_id}")
        with self.metrics.timer("db_list_init_groups_ms"):
            return self.store.list_init_groups(session_id)

    def list_init_sessions(self) -> list[InitSession]:
        with self.metrics.timer("db_list_init_sessions_ms"):
            return self.store.list_init_sessions()

    def discard_init_session(self, session_id: str, *, delete_files: bool = True) -> None:
        session = self.store.get_init_session(session_id)
        if session is None:
            raise KeyError(f"Unknown init session: {session_id}")
        journal = self.cleanup.schedule(
            (session.source_path, self.config.face_dir / "init" / session_id),
            f"discard-init-session-{session_id}",
        ) if delete_files else None
        with self.metrics.timer("db_delete_init_session_ms"):
            self.store.delete_init_session(session_id)
        self.cleanup.run(journal, self.store.list_all_file_references)
    def _remove_managed_queue_path(self, path: Path, protected_paths: set[Path]) -> None:
        resolved = path.resolve()
        managed_roots = [
            (self.config.data_dir / "uploads").resolve(),
            (self.config.face_dir / "init").resolve(),
        ]
        if not any(resolved == root or root in resolved.parents for root in managed_roots):
            return
        if resolved.is_dir():
            for child in sorted(resolved.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if child.is_file() and child.resolve() not in protected_paths:
                    child.unlink()
                elif child.is_dir():
                    try:
                        child.rmdir()
                    except OSError:
                        pass
            try:
                resolved.rmdir()
            except OSError:
                pass
        elif resolved.exists() and resolved not in protected_paths:
            resolved.unlink()

    def get_init_group(self, session_id: str, group_id: str) -> InitGroup:
        return self._get_init_group(session_id, group_id)

    def refresh_init_groups(self, session_id: str) -> list[InitGroup]:
        self.list_init_groups(session_id)
        self._regroup_pending_init_session(session_id)
        return self.list_init_groups(session_id)

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

    def confirm_init_group_existing(self, session_id: str, group_id: str, person_id: str) -> int:
        group = self._get_init_group(session_id, group_id)
        if group.status != "pending":
            raise KeyError(f"Init group is not pending: {group_id}")
        if self.store.get_person(person_id) is None:
            raise KeyError(f"Unknown person: {person_id}")
        for face in group.faces:
            with self.metrics.timer("db_add_embedding_ms"):
                record = self.store.add_embedding(
                    person_id=person_id,
                    vector=face.vector,
                    quality_score=face.quality.score,
                    source_image=face.source_image,
                    crop_path=face.face.crop_path,
                )
            with self.metrics.timer("index_add_ms"):
                self.index.add(record)
        with self.metrics.timer("db_mark_init_group_ms"):
            self.store.mark_init_group_status(session_id, group_id, "confirmed")
        return len(group.faces)

    def confirm_init_faces(
        self,
        session_id: str,
        group_id: str,
        init_face_ids: list[str],
        name: str,
        operation_id: str | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> tuple[str, list[dict]]:
        operation_id = operation_id or str(uuid.uuid4())
        existing = self.store.get_person_operation(operation_id, "confirm-init-new")
        if existing:
            return str(existing["person_id"]), list(existing["accepted"])
        faces = self._selected_init_faces(session_id, group_id, init_face_ids)
        journal = self.cleanup.schedule(
            (path for face in faces for path in (face.source_image, face.face.crop_path)),
            f"confirm-init-{operation_id}",
        )
        result = self.store.confirm_init_faces_atomic(
            session_id,
            group_id,
            init_face_ids,
            operation_id,
            name=name,
            notes=notes,
            mentioned_person_ids=mentioned_person_ids,
        )
        self._rebuild_index()
        self.cleanup.run(journal, self.store.list_all_file_references)
        self._regroup_pending_init_session(session_id)
        return str(result["person_id"]), list(result["accepted"])

    def confirm_init_faces_existing(
        self,
        session_id: str,
        group_id: str,
        init_face_ids: list[str],
        person_id: str,
        operation_id: str | None = None,
    ) -> list[dict]:
        operation_id = operation_id or str(uuid.uuid4())
        existing = self.store.get_person_operation(operation_id, "confirm-init-existing")
        if existing:
            return list(existing["accepted"])
        faces = self._selected_init_faces(session_id, group_id, init_face_ids)
        journal = self.cleanup.schedule(
            (path for face in faces for path in (face.source_image, face.face.crop_path)),
            f"confirm-init-{operation_id}",
        )
        result = self.store.confirm_init_faces_atomic(
            session_id,
            group_id,
            init_face_ids,
            operation_id,
            person_id=person_id,
        )
        self._rebuild_index()
        self.cleanup.run(journal, self.store.list_all_file_references)
        self._regroup_pending_init_session(session_id)
        return list(result["accepted"])
    def discard_init_faces(self, session_id: str, group_id: str, init_face_ids: list[str]) -> None:
        self._selected_init_faces(session_id, group_id, init_face_ids)
        self._remove_reviewed_init_faces(session_id, group_id, init_face_ids, empty_status="rejected")

    def reject_init_group(self, session_id: str, group_id: str) -> None:
        self._get_init_group(session_id, group_id)
        with self.metrics.timer("db_mark_init_group_ms"):
            self.store.mark_init_group_status(session_id, group_id, "rejected")

    def skip_init_group(self, session_id: str, group_id: str) -> None:
        group = self._get_init_group(session_id, group_id)
        if group.status != "pending":
            raise KeyError(f"Queue group is not pending: {group_id}")
        with self.metrics.timer("db_mark_init_group_ms"):
            self.store.mark_init_group_status(session_id, group_id, "skipped")

    def resume_skipped_init_groups(self, session_id: str) -> int:
        skipped = [group for group in self.list_init_groups(session_id) if group.status == "skipped"]
        for group in skipped:
            with self.metrics.timer("db_mark_init_group_ms"):
                self.store.mark_init_group_status(session_id, group.group_id, "pending")
        return len(skipped)

    def reject_init_group_match(self, session_id: str, group_id: str, person_id: str) -> None:
        group = self._get_init_group(session_id, group_id)
        if group.status != "pending":
            raise KeyError(f"Queue group is not pending: {group_id}")
        face_ids = [face.init_face_id for face in group.faces]
        with self.metrics.timer("db_save_init_exclusions_ms"):
            self.store.add_init_face_person_exclusions(session_id, face_ids, person_id)
        self._regroup_pending_init_session(session_id)

    def reset_init_group(self, session_id: str, group_id: str) -> None:
        self._get_init_group(session_id, group_id)
        with self.metrics.timer("db_mark_init_group_ms"):
            self.store.mark_init_group_status(session_id, group_id, "pending")

    def _get_init_group(self, session_id: str, group_id: str) -> InitGroup:
        for group in self.list_init_groups(session_id):
            if group.group_id == group_id:
                return group
        raise KeyError(f"Unknown init group: {group_id}")

    def _selected_init_faces(self, session_id: str, group_id: str, init_face_ids: list[str]) -> list[InitFace]:
        if not init_face_ids:
            raise KeyError("Select at least one image")
        group = self._get_init_group(session_id, group_id)
        if group.status != "pending":
            raise KeyError(f"Queue group is not pending: {group_id}")
        selected = {face_id for face_id in init_face_ids if face_id}
        faces = [face for face in group.faces if face.init_face_id in selected]
        if len(faces) != len(selected):
            raise KeyError("One or more selected images are no longer in this group")
        return faces

    def _add_init_face_embeddings(self, person_id: str, faces: list[InitFace]) -> list[dict]:
        accepted: list[dict] = []
        for face in faces:
            duplicate = _duplicate_embedding(face.vector, self.store.list_embeddings_for_person(person_id))
            if duplicate:
                accepted.append(_accepted_init_face(face, duplicate.embedding_id, duplicate=True))
                continue
            with self.metrics.timer("db_add_embedding_ms"):
                record = self.store.add_embedding(
                    person_id=person_id,
                    vector=face.vector,
                    quality_score=face.quality.score,
                    source_image=face.source_image,
                    crop_path=face.face.crop_path,
                )
            with self.metrics.timer("index_add_ms"):
                self.index.add(record)
            accepted.append(_accepted_init_face(face, record.embedding_id, duplicate=False))
        return accepted

    def _remove_reviewed_init_faces(
        self,
        session_id: str,
        group_id: str,
        init_face_ids: list[str],
        empty_status: str = "confirmed",
        accepted_person_id: str | None = None,
    ) -> None:
        reviewed = {face_id for face_id in init_face_ids if face_id}
        group = self._get_init_group(session_id, group_id)
        remaining_faces = [face for face in group.faces if face.init_face_id not in reviewed]
        reviewed_faces = [face for face in group.faces if face.init_face_id in reviewed]
        journal = self.cleanup.schedule(
            (
                path
                for face in reviewed_faces
                for path in (face.source_image, face.face.crop_path)
            ),
            f"review-init-faces-{session_id}-{group_id}",
        )
        with self.metrics.timer("db_delete_init_faces_ms"):
            self.store.delete_init_faces(init_face_ids)
        if remaining_faces:
            if accepted_person_id:
                with self.metrics.timer("db_save_init_exclusions_ms"):
                    self.store.add_init_face_person_exclusions(
                        session_id,
                        [face.init_face_id for face in remaining_faces],
                        accepted_person_id,
                    )
            self._regroup_init_faces(session_id, group_id, remaining_faces)
        status = "pending" if remaining_faces else empty_status
        with self.metrics.timer("db_mark_init_group_ms"):
            self.store.mark_init_group_status(session_id, group_id, status)
        self.cleanup.run(journal, self.store.list_all_file_references)

    def _regroup_init_faces(self, session_id: str, original_group_id: str, faces: list[InitFace]) -> None:
        regrouped = _assign_groups(faces, threshold=self.config.high_confidence)
        local_group_ids = list(dict.fromkeys(face.group_id for face in regrouped))
        local_to_actual = {
            local_group_id: original_group_id if index == 0 else f"{original_group_id}_split_{index:02d}_{uuid.uuid4().hex[:8]}"
            for index, local_group_id in enumerate(local_group_ids)
        }
        assignments = {
            face.init_face_id: local_to_actual[face.group_id]
            for face in regrouped
        }
        with self.metrics.timer("db_update_init_face_groups_ms"):
            self.store.update_init_face_groups(assignments)
        for group_id in set(assignments.values()):
            with self.metrics.timer("db_mark_init_group_ms"):
                self.store.mark_init_group_status(session_id, group_id, "pending")

    def _regroup_pending_init_session(self, session_id: str) -> None:
        pending_faces = [
            face
            for group in self.list_init_groups(session_id)
            if group.status == "pending"
            for face in group.faces
        ]
        if len(pending_faces) <= 1:
            return
        matches_by_face_id = self._matches_for_init_faces(pending_faces)
        regrouped = _assign_groups(
            pending_faces,
            threshold=self.config.high_confidence,
            medium_threshold=self.config.medium_confidence,
            matches_by_face_id=matches_by_face_id,
        )
        assignments = {
            face.init_face_id: face.group_id
            for face in regrouped
        }
        with self.metrics.timer("db_update_init_face_groups_ms"):
            self.store.update_init_face_groups(assignments)
        for group_id in set(assignments.values()):
            with self.metrics.timer("db_mark_init_group_ms"):
                self.store.mark_init_group_status(session_id, group_id, "pending")

    def _matches_for_init_faces(self, faces: list[InitFace]) -> dict[str, list[PersonMatch]]:
        exclusions = self.excluded_person_ids_for_init_faces(
            faces[0].session_id,
            [face.init_face_id for face in faces],
        ) if faces else {}
        return {
            face.init_face_id: self.matches_for_vector(
                face.vector,
                excluded_person_ids=exclusions.get(face.init_face_id, set()),
            )
            for face in faces
        }

    def _rebuild_index(self) -> None:
        with self.metrics.timer("db_list_embeddings_ms"):
            embeddings = self.store.list_embeddings()
        try:
            with self.metrics.timer("index_rebuild_ms"):
                self.index.rebuild(embeddings)
            self.index_degraded_reason = None
        except Exception as exc:
            if self.index.backend_name == "linear":
                raise
            fallback = LinearFaceIndex()
            fallback.rebuild(embeddings)
            self.index.replace(fallback)
            self.index_degraded_reason = f"{type(exc).__name__}: {exc}"
            self.metrics.increment("index_fallbacks")

    @property
    def index_status(self) -> dict[str, str | None]:
        return {
            "requested": self.config.index_backend,
            "actual": self.index.backend_name,
            "degraded_reason": self.index_degraded_reason,
        }
    def matches_for_vector(self, vector, excluded_person_ids: set[str] | None = None) -> list[PersonMatch]:
        with self.metrics.timer("search_ms"):
            return self._search_unique_people(vector, excluded_person_ids=excluded_person_ids)

    def matches_for_init_group(self, group: InitGroup) -> list[PersonMatch]:
        representative = group_representative_embedding(group)
        if not representative:
            return []
        exclusions = self.excluded_person_ids_for_init_faces(
            group.session_id,
            [face.init_face_id for face in group.faces],
        )
        excluded_person_ids = set().union(*exclusions.values()) if exclusions else set()
        return self.matches_for_vector(representative, excluded_person_ids=excluded_person_ids)

    def ranked_people_for_init_group(self, group: InitGroup) -> list[RankedPersonCandidate]:
        """Rank every active person for an explicit human-review browse action.

        This deliberately uses two bulk reads (people and embeddings) and ranks
        in memory, avoiding one database query per person.
        """
        representative = group_representative_embedding(group)
        exclusions = self.excluded_person_ids_for_init_faces(
            group.session_id,
            [face.init_face_id for face in group.faces],
        )
        excluded_person_ids = set().union(*exclusions.values()) if exclusions else set()
        return self._rank_people_for_vector(representative, excluded_person_ids)

    def ranked_people_for_recognition_face(
        self,
        image_path: Path,
        face_index: int,
        expected_box: FaceBox | None = None,
    ) -> list[RankedPersonCandidate]:
        """Rank active people for one explicitly browsed recognition face."""
        with self.metrics.timer("detect_browse_face_ms"):
            faces = self.detector.detect(image_path)
        if face_index < 1 or face_index > len(faces):
            raise KeyError(f"Face {face_index} is no longer available in this image")
        selected_face = faces[face_index - 1]
        if expected_box is not None and _box_iou(selected_face.box, expected_box) < 0.5:
            selected_face = max(faces, key=lambda face: _box_iou(face.box, expected_box))
            if _box_iou(selected_face.box, expected_box) < 0.5:
                raise KeyError(f"Face {face_index} is no longer available in this image")
        with self.metrics.timer("embed_browse_face_ms"):
            vector = self.embedder.encode(image_path, selected_face)
        return self._rank_people_for_vector(vector)

    def _rank_people_for_vector(
        self,
        representative,
        excluded_person_ids: set[str] | None = None,
    ) -> list[RankedPersonCandidate]:
        excluded_person_ids = excluded_person_ids or set()
        with self.metrics.timer("db_list_people_candidates_ms"):
            people = self.store.list_persons()
            embeddings = self.store.list_embeddings()
        embeddings_by_person: dict[str, list] = {}
        for record in embeddings:
            if record.person_id not in excluded_person_ids:
                embeddings_by_person.setdefault(record.person_id, []).append(record)

        candidates: list[RankedPersonCandidate] = []
        with self.metrics.timer("rank_people_candidates_ms"):
            for summary in people:
                if summary.person.person_id in excluded_person_ids:
                    continue
                records = embeddings_by_person.get(summary.person.person_id, [])
                scored = sorted(
                    (
                        Match(
                            person_id=record.person_id,
                            score=_cosine(representative, record.vector),
                            embedding_id=record.embedding_id,
                        )
                        for record in records
                    ),
                    key=lambda item: item.score,
                    reverse=True,
                ) if representative else []
                match = PersonMatch(
                    person_id=summary.person.person_id,
                    score=scored[0].score,
                    embedding_ids=tuple(item.embedding_id for item in scored[: self.config.top_k]),
                    embeddings_matched=len(scored),
                ) if scored else None
                candidates.append(RankedPersonCandidate(summary, match, tuple(records)))
        candidates.sort(key=lambda item: (
            item.match is None,
            -(item.match.score if item.match else -2.0),
            item.summary.person.name.casefold(),
        ))
        return candidates

    def excluded_person_ids_for_init_faces(
        self,
        session_id: str,
        init_face_ids: list[str],
    ) -> dict[str, set[str]]:
        with self.metrics.timer("db_list_init_exclusions_ms"):
            return self.store.list_init_face_person_exclusions(session_id, init_face_ids)

    def changed_init_groups_for_person(self, session_id: str, person_id: str) -> list[InitGroup]:
        changed: list[InitGroup] = []
        for group in self.list_init_groups(session_id):
            if group.status != "pending":
                continue
            exclusions = self.excluded_person_ids_for_init_faces(
                session_id,
                [face.init_face_id for face in group.faces],
            )
            excluded_person_ids = set().union(*exclusions.values()) if exclusions else set()
            if person_id in excluded_person_ids:
                continue
            representative = group_representative_embedding(group)
            if not representative:
                continue
            match = self._match_group_to_person(representative, person_id)
            if match is not None and match.score >= self.config.medium_confidence:
                changed.append(group)
        return changed

    def _search_unique_people(self, vector, excluded_person_ids: set[str] | None = None) -> list[PersonMatch]:
        excluded_person_ids = excluded_person_ids or set()
        raw_matches = self.index.search(vector, max(self.config.top_k * 8, self.config.top_k))
        grouped: dict[str, list[Match]] = {}
        for match in raw_matches:
            if match.person_id in excluded_person_ids:
                continue
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

    def _match_group_to_person(self, vector, person_id: str) -> PersonMatch | None:
        matches = [
            Match(
                person_id=record.person_id,
                score=_cosine(vector, record.vector),
                embedding_id=record.embedding_id,
            )
            for record in self.store.list_embeddings_for_person(person_id)
        ]
        if not matches:
            return None
        matches.sort(key=lambda match: match.score, reverse=True)
        best = matches[0]
        if best.score <= 0:
            return None
        return PersonMatch(
            person_id=person_id,
            score=best.score,
            embedding_ids=tuple(match.embedding_id for match in matches[: self.config.top_k]),
            embeddings_matched=len(matches),
        )

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


class QueueSessionResult:
    def __init__(
        self,
        session: InitSession,
        groups: list[InitGroup],
        matches_by_face_id: dict[str, list[PersonMatch]],
        invalid_images: list[str] | None = None,
    ) -> None:
        self.session = session
        self.groups = groups
        self.matches_by_face_id = matches_by_face_id
        self.invalid_images = invalid_images or []


def _iter_images(
    source_path: Path,
    checkpoint: Callable[[str], None] | None = None,
) -> list[Path]:
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in IMAGE_EXTENSIONS else []
    if not source_path.exists():
        raise KeyError(f"Source path does not exist: {source_path}")
    images: list[Path] = []
    for path in source_path.rglob("*"):
        if checkpoint:
            checkpoint("discovering_images")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
            if len(images) > MAX_QUEUE_IMAGES:
                raise KeyError(
                    f"Queue folders may contain at most {MAX_QUEUE_IMAGES} images"
                )
    images.sort()
    return images


def _canonical_source_path(image_path: Path, data_dir: Path) -> str:
    """Map a queue hard link back to its content-addressed upload object."""
    batch_root = data_dir / "uploads" / "batches"
    try:
        image_path.relative_to(batch_root)
    except ValueError:
        return str(image_path)
    digest = image_path.stem.split("-", 1)[0]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        return str(image_path)
    candidate = data_dir / "uploads" / "objects" / f"{digest}{image_path.suffix.lower()}"
    try:
        if candidate.exists() and image_path.samefile(candidate):
            return str(candidate)
    except OSError:
        pass
    return str(image_path)

def _assign_groups(
    faces: list[InitFace],
    threshold: float,
    matches_by_face_id: dict[str, list[PersonMatch]] | None = None,
    medium_threshold: float | None = None,
    possible_threshold: float = QUEUE_POSSIBLE_MATCH_THRESHOLD,
) -> list[InitFace]:
    known_groups: dict[tuple[str, str], list[InitFace]] = {}
    unknown_faces: list[InitFace] = []
    for face in faces:
        bucket = _best_match_bucket(
            matches_by_face_id.get(face.init_face_id, []) if matches_by_face_id else [],
            threshold,
            medium_threshold,
            possible_threshold,
        )
        if bucket:
            person_id, strength = bucket
            known_groups.setdefault((person_id, strength), []).append(face)
        else:
            unknown_faces.append(face)

    unknown_groups: list[list[InitFace]] = []
    for face in unknown_faces:
        best_group_index = None
        best_score = -1.0
        for index, group in enumerate(unknown_groups):
            score = max(_cosine(face.vector, existing.vector) for existing in group)
            if score > best_score:
                best_group_index = index
                best_score = score
        if best_group_index is None or best_score < threshold:
            unknown_groups.append([face])
        else:
            unknown_groups[best_group_index].append(face)

    assigned: list[InitFace] = []
    groups = [*known_groups.values(), *unknown_groups]
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


def _best_match_bucket(
    matches: list[PersonMatch],
    high_threshold: float,
    medium_threshold: float | None,
    possible_threshold: float,
) -> tuple[str, str] | None:
    if not matches:
        return None
    best = matches[0]
    if best.score >= high_threshold:
        return best.person_id, "strong"
    if medium_threshold is not None and best.score >= medium_threshold:
        return best.person_id, "likely"
    if medium_threshold is not None and best.score >= possible_threshold:
        return best.person_id, "possible"
    return None


def _groups_from_faces(session_id: str, faces: list[InitFace]) -> list[InitGroup]:
    groups: dict[str, InitGroup] = {}
    for face in faces:
        if face.group_id not in groups:
            groups[face.group_id] = InitGroup(group_id=face.group_id, session_id=session_id, faces=[])
        groups[face.group_id].faces.append(face)
    return list(groups.values())


def group_representative_embedding(group: InitGroup):
    if not group.faces:
        return ()
    dimensions = len(group.faces[0].vector)
    centroid = [
        sum(face.vector[index] for face in group.faces) / len(group.faces)
        for index in range(dimensions)
    ]
    norm = sqrt(sum(value * value for value in centroid))
    if norm == 0:
        return tuple(centroid)
    return tuple(value / norm for value in centroid)


def _accepted_init_face(face: InitFace, embedding_id: str, duplicate: bool) -> dict:
    return {
        "face_id": face.init_face_id,
        "embedding_id": embedding_id,
        "image_id": Path(face.source_image).name,
        "image_path": face.source_image,
        "duplicate": duplicate,
    }


def _cosine(left, right) -> float:
    return sum(a * b for a, b in zip(left, right))


def _duplicate_embedding(vector, embeddings) -> object | None:
    for record in embeddings:
        if _cosine(vector, record.vector) >= DUPLICATE_MATCH_SCORE:
            return record
    return None


def _box_iou(left: FaceBox, right: FaceBox) -> float:
    intersection_width = max(0, min(left.x + left.width, right.x + right.width) - max(left.x, right.x))
    intersection_height = max(0, min(left.y + left.height, right.y + right.height) - max(left.y, right.y))
    intersection = intersection_width * intersection_height
    union = left.width * left.height + right.width * right.height - intersection
    return intersection / union if union > 0 else 0.0


def _with_crop_path(face, crop_path: str):
    return type(face)(
        box=face.box,
        quality_score=face.quality_score,
        landmarks=face.landmarks,
        crop_path=crop_path,
    )
