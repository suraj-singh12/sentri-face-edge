from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from sentriface.backup_service import BackupError, BackupRecord, BackupService
from sentriface.cli import build_dev_engine, build_onnx_engine
from sentriface.config import RuntimeConfig, config_for_hardware
from sentriface.engine import IMAGE_EXTENSIONS, FaceEngine
from sentriface.errors import InputImageError, InputValidationError
from sentriface.hardware import assess_hardware
from sentriface.models import (
    EmbeddingRecord,
    FaceBox,
    InitGroup,
    InitSession,
    PendingAddition,
    Person,
    PersonChange,
    PersonMatch,
    PersonSummary,
    QualityReport,
    RecognitionDetail,
    RecognitionResult,
    RejectedFace,
)
from sentriface.storage.sqlite_store import SCHEMA_VERSION
# TODO: To be replaced with FastApi
# It is an adapter which connects react to python code.  


STATIC_DIR = Path(__file__).with_name("ui_static")
UPLOAD_RESIZE_LIMIT_BYTES = 1_000_000
UPLOAD_REQUEST_LIMIT_BYTES = 100_000_000
UPLOAD_MAX_EDGE = 1600
UPLOAD_MAX_PIXELS = 40_000_000
JSON_REQUEST_LIMIT_BYTES = 135_000_000
BACKUP_IMPORT_LIMIT_BYTES = 20_000_000_000
DUPLICATE_MATCH_SCORE = 0.9999


class OperationGate:
    """Allow concurrent normal work while giving restore exclusive access."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active_operations = 0
        self._exclusive_active = False
        self._exclusive_waiters = 0

    @contextmanager
    def shared(self):
        with self._condition:
            while self._exclusive_active or self._exclusive_waiters:
                self._condition.wait()
            self._active_operations += 1
        try:
            yield
        finally:
            with self._condition:
                self._active_operations -= 1
                self._condition.notify_all()

    @contextmanager
    def exclusive(self):
        with self._condition:
            self._exclusive_waiters += 1
            try:
                while self._exclusive_active or self._active_operations:
                    self._condition.wait()
                self._exclusive_active = True
            finally:
                self._exclusive_waiters -= 1
        try:
            yield
        finally:
            with self._condition:
                self._exclusive_active = False
                self._condition.notify_all()


class SentriFaceApiServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        engine: FaceEngine,
        config: RuntimeConfig,
        runtime: str,
        debug: bool = True,
    ) -> None:
        super().__init__(server_address, SentriFaceApiHandler)
        self.engine = engine
        self.config = config
        self.runtime = runtime
        self.debug = debug
        self.events: list[dict[str, Any]] = []
        self.queue_progress: dict[str, dict[str, Any]] = {}
        self.queue_progress_lock = threading.Lock()
        self.operation_gate = OperationGate()
        self.backups = BackupService(
            config.db_path,
            config.backup_dir,
            retention_limit=config.backup_retention_limit,
            logger=self.log_event,
            data_dir=config.data_dir,
            supported_database_version=SCHEMA_VERSION,
        )
        self.maintenance_stop = threading.Event()
        self.maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            name="sentriface-retention",
            daemon=True,
        )
        self.maintenance_thread.start()

    def log_event(self, event: str, **details: Any) -> None:
        safe_details = _sanitize_log_details(details)
        item = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **safe_details,
        }
        self.events.append(item)
        self.events = self.events[-200:]
        if self.debug:
            print(
                f"[sentriface-ui] {event} "
                f"{json.dumps(safe_details, separators=(',', ':'))}"
            )

    def update_queue_progress(self, job_id: str, **updates: Any) -> None:
        with self.queue_progress_lock:
            current = self.queue_progress.get(job_id, {"job_id": job_id, "started_at": time.time(), "status": "running"})
            current.update(updates)
            current["job_id"] = job_id
            self.queue_progress[job_id] = current

    def queue_progress_snapshot(self, job_id: str) -> dict[str, Any]:
        with self.queue_progress_lock:
            progress = dict(self.queue_progress.get(job_id, {"job_id": job_id, "status": "unknown"}))
        started_at = progress.get("started_at")
        ended_at = progress.get("finished_at") or time.time()
        progress["elapsed_seconds"] = max(0, int(ended_at - started_at)) if started_at else 0
        return progress

    def backed_up_people_deletion(
        self,
        operation_id: str,
        operation_type: str,
        reason: str,
        action: Callable[[], dict],
    ) -> dict:
        existing = self.engine.get_person_operation(operation_id, operation_type)
        if existing is not None:
            backup = self.backups.find_by_operation(operation_id)
            return {**existing, **({"backup": _backup(backup)} if backup else {})}
        backup = self.backups.create_backup(reason=reason, operation_id=operation_id)
        result = action()
        return {**result, "backup": _backup(backup)}

    def purge_expired_deleted_faces(self) -> int:
        embedding_ids = self.engine.list_expired_deleted_embedding_ids()
        if not embedding_ids:
            return 0
        ordered_ids = sorted(set(embedding_ids))
        digest = hashlib.sha256("\n".join(ordered_ids).encode("utf-8")).hexdigest()[:16]
        operation_id = f"retention-purge-batch-{digest}"
        reason = f"before-expired-face-purge-{len(ordered_ids)}-faces"
        result = self.backed_up_people_deletion(
            operation_id,
            "purge-expired-embeddings",
            reason,
            lambda: self.engine.purge_expired_deleted_embeddings(
                ordered_ids,
                operation_id,
            ),
        )
        purged = int(result.get("purged", 0))
        if purged:
            self.log_event("deleted-face-retention", purged=purged)
        return purged

    def _maintenance_loop(self) -> None:
        while not self.maintenance_stop.is_set():
            try:
                with self.operation_gate.shared():
                    self.purge_expired_deleted_faces()
            except Exception as exc:  # noqa: BLE001 - maintenance must not terminate the UI server.
                self.log_event("deleted-face-retention-failed", error=str(exc).strip("'"))
            if self.maintenance_stop.wait(3600):
                break

    def server_close(self) -> None:
        maintenance_stop = getattr(self, "maintenance_stop", None)
        maintenance_thread = getattr(self, "maintenance_thread", None)
        if maintenance_stop is not None:
            maintenance_stop.set()
        if maintenance_thread is not None and maintenance_thread.is_alive():
            maintenance_thread.join(timeout=2)
        super().server_close()


class SentriFaceApiHandler(SimpleHTTPRequestHandler):
    server: SentriFaceApiServer

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.path == "/":
            return str(STATIC_DIR / "index.html")
        return str(STATIC_DIR / parsed.path.lstrip("/"))

    def do_GET(self) -> None:
        with self.server.operation_gate.shared():
            self._do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        gate = (
            self.server.operation_gate.exclusive()
            if parsed.path == "/api/backups/restore"
            else self.server.operation_gate.shared()
        )
        with gate:
            self._do_POST()

    def do_DELETE(self) -> None:
        with self.server.operation_gate.shared():
            self._do_DELETE()

    def _do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/profile":
                self._json(self._profile())
                return
            if parsed.path == "/api/persons":
                self._json(
                    {
                        "persons": [
                            _person_summary(item, self.server.engine)
                            for item in self.server.engine.list_persons()
                        ],
                        "archived_persons": [
                            _person_summary(item, self.server.engine)
                            for item in self.server.engine.list_persons(archived=True)
                        ],
                    }
                )
                return
            if parsed.path == "/api/deleted-faces":
                self.server.purge_expired_deleted_faces()
                self._json(
                    {
                        "deleted_faces": [
                            _deleted_embedding(item)
                            for item in self.server.engine.list_deleted_embeddings()
                        ]
                    }
                )
                return
            if parsed.path == "/api/person":
                person_id = _query_value(parsed.query, "person_id")
                include_archived = _query_bool(parsed.query, "include_archived")
                person = self.server.engine.get_person(
                    person_id,
                    include_archived=include_archived,
                )
                if person is None:
                    raise KeyError(f"Unknown person: {person_id}")
                embeddings = self.server.engine.list_person_embeddings(
                    person_id,
                    include_archived=include_archived,
                )
                details = self.server.engine.list_recognition_details_for_person(
                    person_id,
                    include_archived=include_archived,
                )
                changes = self.server.engine.list_person_changes(
                    person_id,
                    include_archived=include_archived,
                )
                management_events = self.server.engine.list_person_operations(
                    person_id,
                    include_archived=include_archived,
                )
                self._json(
                    {
                        "person": {
                            **_person(person),
                            "favorite": bool(person.metadata.get("favorite")),
                            "tags": list(person.metadata.get("tags", [])),
                            "representative_image": _representative_image(
                                embeddings,
                                person.metadata.get("representative_embedding_id"),
                            ),
                        },
                        "embeddings": [_embedding(record) for record in embeddings],
                        "details": [_recognition_detail(detail) for detail in details],
                        "changes": [_person_change(change) for change in changes],
                        "management_events": management_events,
                    }
                )
                return
            if parsed.path == "/api/pending":
                self._json({"pending": [_pending(self.server.engine, item) for item in self.server.engine.list_pending_additions()]})
                return
            if parsed.path == "/api/events":
                self._json({"events": self.server.events[-80:]})
                return
            if parsed.path.startswith("/api/backups/") and parsed.path.endswith("/download"):
                backup_id = parsed.path.removeprefix("/api/backups/").removesuffix("/download").strip("/")
                export_dir = self.server.config.backup_dir / ".exports"
                export_path = export_dir / f"{backup_id}-{uuid.uuid4().hex}.sfbackup"
                try:
                    exported = self.server.backups.export_backup(backup_id, export_path)
                    self._download_file(
                        exported,
                        download_name=f"{backup_id}.sfbackup",
                        content_type="application/zip",
                    )
                finally:
                    export_path.unlink(missing_ok=True)
                    try:
                        export_dir.rmdir()
                    except OSError:
                        pass
                return
            if parsed.path == "/api/backups":
                self._json({"backups": [_backup(record) for record in self.server.backups.list_backups()]})
                return
            if parsed.path == "/api/queue-progress":
                job_id = _query_value(parsed.query, "job_id")
                self._json(self.server.queue_progress_snapshot(job_id))
                return
            if parsed.path == "/api/queue-sessions":
                sessions = []
                for session in self.server.engine.list_init_sessions():
                    groups = self.server.engine.list_init_groups(session.session_id)
                    if groups:
                        sessions.append(_init_session_summary(session, groups))
                self._json({"sessions": sessions})
                return
            if parsed.path == "/api/queue-groups":
                session_id = _query_value(parsed.query, "session_id")
                groups = self.server.engine.refresh_init_groups(session_id)
                self._json({"groups": [_init_group(self.server.engine, group) for group in groups]})
                return
            if parsed.path == "/media":
                self._media(_query_value(parsed.query, "path"))
                return
            super().do_GET()
        except Exception as exc:  # noqa: BLE001 - local UI should surface errors clearly.
            self._error(exc)

    def _do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/backups/import":
                filename = _query_value(parsed.query, "filename")
                if Path(filename).suffix.lower() != ".sfbackup":
                    raise InputValidationError(
                        "Choose a SentriFace .sfbackup file",
                        "unsupported_backup_type",
                    )
                import_dir = self.server.config.backup_dir / ".imports"
                import_path = import_dir / f"{uuid.uuid4().hex}.sfbackup"
                try:
                    self._stream_request_to_file(
                        import_path,
                        maximum_bytes=BACKUP_IMPORT_LIMIT_BYTES,
                    )
                    record = self.server.backups.import_backup(import_path)
                finally:
                    import_path.unlink(missing_ok=True)
                    try:
                        import_dir.rmdir()
                    except OSError:
                        pass
                self._json({"backup": _backup(record)})
                return
            if parsed.path == "/api/upload-chunk":
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise InputValidationError(
                        "Invalid upload length",
                        "invalid_content_length",
                    ) from exc
                if content_length <= 0:
                    raise InputValidationError("Upload is empty", "empty_file")
                if content_length > UPLOAD_REQUEST_LIMIT_BYTES:
                    raise InputValidationError(
                        "Upload exceeds the 100 MB per-file limit",
                        "file_too_large",
                    )
                saved_dir, saved_path = _save_upload_chunk(
                    self.server.config.data_dir,
                    _query_value(parsed.query, "upload_id"),
                    _query_value(parsed.query, "filename"),
                    _query_value(parsed.query, "relative_path"),
                    self.rfile.read(content_length),
                )
                self._json({
                    "path": str(saved_dir),
                    "stored_path": str(saved_path),
                    "stored_size": saved_path.stat().st_size,
                })
                return
            payload = self._read_json()
            if parsed.path == "/api/input-rejections":
                source = str(payload.get("source") or "unknown").strip().lower()[:40]
                rejected_count = _safe_count(payload.get("rejected_count"), "rejected_count")
                accepted_count = _safe_count(
                    payload.get("accepted_count", 0),
                    "accepted_count",
                    allow_zero=True,
                )
                reasons = _safe_rejection_reasons(payload.get("reasons"))
                self.server.log_event(
                    "input-rejected",
                    source=source,
                    rejected_count=rejected_count,
                    accepted_count=accepted_count,
                    reasons=reasons,
                    client_side=True,
                )
                self._json({"logged": True})
                return
            if parsed.path == "/api/backups":
                record = self.server.backups.create_backup()
                self._json({"backup": _backup(record)})
                return
            if parsed.path == "/api/backups/restore":
                backup_id = _required(payload, "backup_id")
                operation_id = _operation_id(payload)
                result = self.server.backups.restore_backup(
                    backup_id,
                    operation_id,
                    reload_callback=self.server.engine.initialize,
                    allow_incomplete=bool(payload.get("allow_incomplete", False)),
                )
                self.server.log_event("app-state-restored", **result)
                self._json({"restore": result})
                return
            if parsed.path == "/api/upload":
                saved_path = _save_upload(
                    self.server.config.data_dir,
                    _required(payload, "filename"),
                    _required(payload, "data"),
                )
                self.server.log_event(
                    "upload",
                    filename=payload.get("filename"),
                    path=str(saved_path),
                    stored_size=saved_path.stat().st_size,
                )
                self._json({"path": str(saved_path), "stored_size": saved_path.stat().st_size})
                return
            if parsed.path == "/api/upload-batch":
                saved_dir, count, rejected = _save_upload_batch(
                    self.server.config.data_dir,
                    payload.get("files", []),
                )
                self.server.log_event(
                    "upload-batch",
                    path=str(saved_dir),
                    files=count,
                    rejected_files=rejected,
                )
                self._json({
                    "path": str(saved_dir),
                    "files": count,
                    "rejected_files": rejected,
                })
                return
            if parsed.path == "/api/upload-batch-discard":
                removed = _discard_upload_batch(
                    self.server.config.data_dir,
                    _required(payload, "upload_id"),
                )
                self._json({"removed": removed})
                return
            if parsed.path == "/api/recognize":
                image_path = Path(_required(payload, "path"))
                self.server.engine.reset_metrics()
                results = self.server.engine.recognize(image_path)
                self.server.log_event("recognize", path=str(image_path), faces=len(results))
                self._json(
                    {
                        "faces": [_recognition(self.server.engine, result, index) for index, result in enumerate(results, 1)],
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/recognize-batch":
                source = Path(_required(payload, "path"))
                images = _image_paths(source)
                if not images:
                    raise KeyError(f"No supported images found: {source}")
                self.server.engine.reset_metrics()
                batch = [
                    {
                        "image": str(image_path),
                        "faces": [
                            _recognition(self.server.engine, result, index)
                            for index, result in enumerate(self.server.engine.recognize(image_path), 1)
                        ],
                    }
                    for image_path in images
                ]
                self.server.log_event("recognize-batch", path=str(source), images=len(images))
                self._json({"batch": batch, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/person-update":
                tags = payload.get("tags", [])
                if not isinstance(tags, list):
                    raise KeyError("tags must be a list")
                change = self.server.engine.update_person_profile(
                    person_id=_required(payload, "person_id"),
                    name=_required(payload, "name"),
                    rank=payload.get("rank"),
                    country=payload.get("country"),
                    importance=payload.get("importance"),
                    editor_name=_required(payload, "editor_name"),
                    tags=[str(tag) for tag in tags],
                    operation_id=_operation_id(payload),
                )
                self.server.log_event(
                    "person-update",
                    person_id=change.person_id,
                    editor_name=change.editor_name,
                )
                self._json({"updated": True, "change": _person_change(change)})
                return
            if parsed.path == "/api/person-preferences":
                favorite = payload.get("favorite")
                if favorite is not None and not isinstance(favorite, bool):
                    raise KeyError("favorite must be true or false")
                result = self.server.engine.update_person_preferences(
                    person_id=_required(payload, "person_id"),
                    operation_id=_operation_id(payload),
                    favorite=favorite,
                    representative_embedding_id=payload.get("representative_embedding_id"),
                )
                self.server.log_event("person-preferences", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-archive":
                person_id = _required(payload, "person_id")
                operation_id = _operation_id(payload)
                person = self.server.engine.get_person(person_id, include_archived=True)
                if person is None:
                    raise KeyError(f"Unknown person: {person_id}")
                if person.deleted_at:
                    result = self.server.engine.archive_person(person_id, operation_id)
                else:
                    result = self.server.backed_up_people_deletion(
                        operation_id,
                        "archive-person",
                        f"before-person-archive-{person.name}-{person_id[:8]}",
                        lambda: self.server.engine.archive_person(person_id, operation_id),
                    )
                self.server.log_event("person-archive", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-restore":
                result = self.server.engine.restore_person(
                    _required(payload, "person_id"),
                    _operation_id(payload),
                )
                self.server.log_event("person-restore", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-merge":
                source_id = _required(payload, "source_person_id")
                target_id = _required(payload, "target_person_id")
                operation_id = _operation_id(payload)
                source = self.server.engine.get_person(source_id)
                target = self.server.engine.get_person(target_id)
                if source is None:
                    raise KeyError(f"Unknown source person: {source_id}")
                if target is None:
                    raise KeyError(f"Unknown target person: {target_id}")
                result = self.server.backed_up_people_deletion(
                    operation_id,
                    "merge-persons",
                    f"before-person-merge-{source.name}-into-{target.name}-{source_id[:8]}",
                    lambda: self.server.engine.merge_persons(
                        source_id,
                        target_id,
                        operation_id,
                    ),
                )
                self.server.log_event("person-merge", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-photo-move":
                result = self.server.engine.move_embedding(
                    _required(payload, "embedding_id"),
                    _required(payload, "target_person_id"),
                    _operation_id(payload),
                )
                self.server.log_event("person-photo-move", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-photo-delete":
                embedding_id = _required(payload, "embedding_id")
                operation_id = _operation_id(payload)
                lifecycle = self.server.engine.get_embedding_lifecycle(embedding_id)
                if lifecycle is None:
                    raise KeyError(f"Unknown embedding: {embedding_id}")
                if lifecycle["deleted_at"]:
                    raise KeyError("Face is already in Deleted Faces")
                result = self.server.backed_up_people_deletion(
                    operation_id,
                    "soft-delete-embedding",
                    (
                        f"before-face-delete-{lifecycle['person_name']}-"
                        f"{embedding_id[:8]}"
                    ),
                    lambda: self.server.engine.delete_embedding(embedding_id, operation_id),
                )
                self.server.log_event("person-photo-delete", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-photo-restore":
                result = self.server.engine.restore_deleted_embedding(
                    _required(payload, "embedding_id"),
                    _operation_id(payload),
                )
                self.server.log_event("person-photo-restore", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-photo-purge":
                embedding_id = _required(payload, "embedding_id")
                operation_id = _operation_id(payload)
                lifecycle = self.server.engine.get_embedding_lifecycle(embedding_id)
                if lifecycle is None:
                    raise KeyError(f"Unknown deleted face: {embedding_id}")
                if not lifecycle["deleted_at"]:
                    raise KeyError("Move the face to Deleted Faces before deleting it permanently")
                result = self.server.backed_up_people_deletion(
                    operation_id,
                    "purge-deleted-embedding",
                    (
                        f"before-face-permanent-delete-{lifecycle['person_name']}-"
                        f"{embedding_id[:8]}"
                    ),
                    lambda: self.server.engine.permanently_delete_embedding(
                        embedding_id,
                        operation_id,
                    ),
                )
                self.server.log_event("person-photo-purge", **result)
                self._json(result)
                return
            if parsed.path == "/api/recognition-accept-existing":
                image_path = Path(_required(payload, "path"))
                person_id = _required(payload, "person_id")
                face_index = _face_index(payload)
                if self.server.engine.get_person(person_id) is None:
                    raise KeyError(f"Unknown person: {person_id}")
                self.server.engine.reset_metrics()
                addition = self.server.engine.prepare_face_addition(
                    image_path,
                    face_index,
                    allow_bad_quality=bool(payload.get("force_bad_quality", False)),
                    expected_box=_face_box(payload),
                )
                if addition is None:
                    raise KeyError(f"Face {face_index} does not meet the enrollment quality requirements")
                duplicate = _duplicate_embedding(addition.vector, self.server.engine.list_person_embeddings(person_id))
                if duplicate:
                    person = self.server.engine.get_person(person_id)
                    self.server.log_event("recognition-duplicate", path=str(image_path), person_id=person_id, face_index=face_index)
                    self._json(
                        {
                            "duplicate": True,
                            "embedding_id": duplicate.embedding_id,
                            "person_id": person_id,
                            "name": person.name if person else person_id,
                            "metrics": self.server.engine.metrics_snapshot(),
                        }
                    )
                    return
                embedding_id = self.server.engine.confirm_existing_person(addition, person_id)
                self.server.log_event("recognition-accept-existing", path=str(image_path), person_id=person_id, face_index=face_index)
                self._json({"embedding_id": embedding_id, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/recognition-new":
                image_path = Path(_required(payload, "path"))
                name = _required(payload, "name")
                face_index = _face_index(payload)
                self.server.engine.reset_metrics()
                addition = self.server.engine.prepare_face_addition(
                    image_path,
                    face_index,
                    allow_bad_quality=bool(payload.get("force_bad_quality", False)),
                    expected_box=_face_box(payload),
                )
                if addition is None:
                    raise KeyError(f"Face {face_index} does not meet the enrollment quality requirements")
                person_id = self.server.engine.confirm_new_person(addition, name)
                embedding = self.server.engine.list_person_embeddings(person_id)[-1]
                self.server.log_event("recognition-new", path=str(image_path), person_id=person_id, face_index=face_index)
                self._json(
                    {
                        "person_id": person_id,
                        "embedding_id": embedding.embedding_id,
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/recognition-followup":
                detail_id = self.server.engine.add_recognition_detail(
                    embedding_id=_required(payload, "embedding_id"),
                    person_id=_required(payload, "person_id"),
                    image_id=_required(payload, "image_id"),
                    image_path=payload.get("image_path"),
                    name=_required(payload, "name"),
                    decision=_required(payload, "decision"),
                    seen_date=_required(payload, "date"),
                    seen_time=_required(payload, "time"),
                    place_seen=_required(payload, "place_seen"),
                    individual_count=int(_required(payload, "individual_count")),
                    event_occasion=_required(payload, "event_occasion"),
                    rank=payload.get("rank"),
                    country=payload.get("country"),
                    importance=payload.get("importance"),
                    added_by=payload.get("added_by"),
                )
                self.server.log_event(
                    "recognition-followup",
                    detail_id=detail_id,
                    path=_required(payload, "path"),
                    image_id=_required(payload, "image_id"),
                    embedding_id=_required(payload, "embedding_id"),
                    name=_required(payload, "name"),
                    person_id=_required(payload, "person_id"),
                    decision=_required(payload, "decision"),
                    date=_required(payload, "date"),
                    time=_required(payload, "time"),
                    place_seen=_required(payload, "place_seen"),
                    individual_count=int(_required(payload, "individual_count")),
                    event_occasion=_required(payload, "event_occasion"),
                    rank=payload.get("rank"),
                    country=payload.get("country"),
                    importance=payload.get("importance"),
                    added_by=payload.get("added_by"),
                )
                self._json({"confirmed": True, "detail_id": detail_id})
                return
            if parsed.path == "/api/enroll":
                image_path = Path(_required(payload, "path"))
                name = _required(payload, "name")
                self.server.engine.reset_metrics()
                additions = self.server.engine.prepare_additions(image_path, bool(payload.get("force_bad_quality", False)))
                if not additions:
                    raise KeyError("No acceptable faces found")
                person_id = self.server.engine.confirm_new_person(additions[0], name)
                self.server.log_event("enroll", path=str(image_path), person_id=person_id)
                self._json({"person_id": person_id, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/queue-add":
                image_path = Path(_required(payload, "path"))
                self.server.engine.reset_metrics()
                prepared = self.server.engine.queue_additions(image_path, bool(payload.get("force_bad_quality", False)))
                self.server.log_event(
                    "queue-add",
                    path=str(image_path),
                    accepted=len(prepared.accepted),
                    rejected=len(prepared.rejected),
                )
                self._json(
                    {
                        "pending": [_pending(self.server.engine, item) for item in prepared.accepted],
                        "rejected": [_rejected(item, index) for index, item in enumerate(prepared.rejected, 1)],
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/queue-scan":
                source = Path(_required(payload, "path"))
                job_id = str(payload.get("job_id") or uuid.uuid4())
                total_files = _safe_count(
                    payload.get("total_files", 0),
                    "total_files",
                    allow_zero=True,
                )
                uploaded_files = _safe_count(
                    payload.get("uploaded_files", total_files),
                    "uploaded_files",
                    allow_zero=True,
                )
                self.server.update_queue_progress(
                    job_id,
                    phase="scanning",
                    status="running",
                    total_files=total_files,
                    uploaded_files=uploaded_files,
                    total_images=0,
                    images_scanned=0,
                    faces_detected=0,
                    embeddings_generated=0,
                    groups=0,
                    started_at=time.time(),
                )
                self.server.engine.reset_metrics()
                queue_result = self.server.engine.create_queue_session(
                    source,
                    bool(payload.get("force_bad_quality", False)),
                    progress_callback=lambda update: self.server.update_queue_progress(job_id, **update),
                )
                self.server.update_queue_progress(
                    job_id,
                    phase="done",
                    status="done",
                    session_id=queue_result.session.session_id,
                    groups=len(queue_result.groups),
                    finished_at=time.time(),
                )
                self.server.log_event(
                    "queue-scan",
                    path=str(source),
                    job_id=job_id,
                    session_id=queue_result.session.session_id,
                    groups=len(queue_result.groups),
                    rejected_files=len(queue_result.invalid_images),
                )
                if queue_result.invalid_images:
                    self.server.log_event(
                        "input-rejected",
                        source="queue-scan",
                        rejected_count=len(queue_result.invalid_images),
                        accepted_count=max(
                            0,
                            uploaded_files - len(queue_result.invalid_images),
                        ),
                        reasons={"unreadable_image": len(queue_result.invalid_images)},
                        client_side=False,
                    )
                session_id = queue_result.session.session_id
                if not queue_result.groups:
                    self.server.engine.discard_init_session(session_id)
                    session_id = ""
                self._json(
                    {
                        "session_id": session_id,
                        "job_id": job_id,
                        "rejected_files": len(queue_result.invalid_images),
                        "groups": [
                            _init_group(self.server.engine, group, queue_result.matches_by_face_id)
                            for group in queue_result.groups
                        ],
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/queue-confirm-new":
                session_id = _required(payload, "session_id")
                person_id, accepted = self.server.engine.confirm_init_faces(
                    session_id,
                    _required(payload, "group_id"),
                    _queue_face_ids(self.server.engine, payload),
                    _required(payload, "name"),
                )
                changed = self.server.engine.changed_init_groups_for_person(session_id, person_id)
                groups = self.server.engine.list_init_groups(session_id)
                session_closed = not groups
                if session_closed:
                    self.server.engine.discard_init_session(session_id)
                self.server.log_event("queue-confirm-new", person_id=person_id, embeddings=len(accepted))
                self._json(
                    {
                        "person_id": person_id,
                        "accepted": accepted,
                        "embedding_ids": [item["embedding_id"] for item in accepted],
                        "changed_groups": [_init_group(self.server.engine, group) for group in changed],
                        "groups": [_init_group(self.server.engine, group) for group in groups],
                        "session_closed": session_closed,
                    }
                )
                return
            if parsed.path == "/api/queue-confirm-existing":
                session_id = _required(payload, "session_id")
                person_id = _required(payload, "person_id")
                accepted = self.server.engine.confirm_init_faces_existing(
                    session_id,
                    _required(payload, "group_id"),
                    _queue_face_ids(self.server.engine, payload),
                    person_id,
                )
                changed = self.server.engine.changed_init_groups_for_person(session_id, person_id)
                groups = self.server.engine.list_init_groups(session_id)
                session_closed = not groups
                if session_closed:
                    self.server.engine.discard_init_session(session_id)
                self.server.log_event("queue-confirm-existing", person_id=payload.get("person_id"), embeddings=len(accepted))
                self._json(
                    {
                        "accepted": accepted,
                        "embedding_ids": [item["embedding_id"] for item in accepted],
                        "changed_groups": [_init_group(self.server.engine, group) for group in changed],
                        "groups": [_init_group(self.server.engine, group) for group in groups],
                        "session_closed": session_closed,
                    }
                )
                return
            if parsed.path == "/api/queue-refresh-suggestions":
                session_id = _required(payload, "session_id")
                groups = self.server.engine.list_init_groups(session_id)
                self.server.log_event("queue-refresh-suggestions", session_id=session_id, groups=len(groups))
                self._json({"groups": [_init_group(self.server.engine, group) for group in groups]})
                return
            if parsed.path == "/api/queue-discard":
                session_id = _required(payload, "session_id")
                self.server.engine.discard_init_faces(
                    session_id,
                    _required(payload, "group_id"),
                    list(payload.get("face_ids", [])),
                )
                groups = self.server.engine.list_init_groups(session_id)
                session_closed = not groups
                if session_closed:
                    self.server.engine.discard_init_session(session_id)
                self.server.log_event("queue-discard", group_id=payload.get("group_id"), faces=len(payload.get("face_ids", [])))
                self._json({
                    "discarded": len(payload.get("face_ids", [])),
                    "groups": [_init_group(self.server.engine, group) for group in groups],
                    "session_closed": session_closed,
                })
                return
            if parsed.path == "/api/queue-skip":
                session_id = _required(payload, "session_id")
                group_id = _required(payload, "group_id")
                self.server.engine.skip_init_group(session_id, group_id)
                groups = self.server.engine.list_init_groups(session_id)
                self.server.log_event("queue-skip", session_id=session_id, group_id=group_id)
                self._json({"skipped": True, "groups": [_init_group(self.server.engine, group) for group in groups]})
                return
            if parsed.path == "/api/queue-resume-skipped":
                session_id = _required(payload, "session_id")
                resumed = self.server.engine.resume_skipped_init_groups(session_id)
                groups = self.server.engine.list_init_groups(session_id)
                self.server.log_event("queue-resume-skipped", session_id=session_id, groups=resumed)
                self._json({"resumed": resumed, "groups": [_init_group(self.server.engine, group) for group in groups]})
                return
            if parsed.path == "/api/queue-reject-match":
                session_id = _required(payload, "session_id")
                group_id = _required(payload, "group_id")
                person_id = _required(payload, "person_id")
                self.server.engine.reject_init_group_match(session_id, group_id, person_id)
                groups = self.server.engine.list_init_groups(session_id)
                self.server.log_event("queue-reject-match", session_id=session_id, group_id=group_id, person_id=person_id)
                self._json({"rejected": True, "groups": [_init_group(self.server.engine, group) for group in groups]})
                return
            if parsed.path == "/api/confirm-new":
                pending_id = _required(payload, "pending_id")
                name = _required(payload, "name")
                person_id = self.server.engine.confirm_pending_as_new_person(pending_id, name)
                self.server.log_event("confirm-new", pending_id=pending_id, person_id=person_id)
                self._json({"person_id": person_id})
                return
            if parsed.path == "/api/confirm-existing":
                pending_id = _required(payload, "pending_id")
                person_id = _required(payload, "person_id")
                embedding_id = self.server.engine.confirm_pending_as_existing_person(pending_id, person_id)
                self.server.log_event("confirm-existing", pending_id=pending_id, person_id=person_id)
                self._json({"embedding_id": embedding_id})
                return
            if parsed.path == "/api/reject-pending":
                pending_id = _required(payload, "pending_id")
                self.server.engine.reject_pending_addition(pending_id)
                self.server.log_event("reject-pending", pending_id=pending_id)
                self._json({"rejected": 1})
                return
            if parsed.path == "/api/backup-db":
                record = self.server.backups.create_backup()
                self._json({"backup": _backup(record)})
                return
            self._json({"error": "Unknown endpoint"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - local UI should surface errors clearly.
            self._error(exc)

    def _do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/backups/"):
                backup_id = parsed.path.removeprefix("/api/backups/")
                self.server.backups.delete_backup(backup_id)
                self._json({"deleted": True, "backup_id": backup_id})
                return
            if parsed.path == "/api/queue-session":
                session_id = _query_value(parsed.query, "session_id")
                self.server.engine.discard_init_session(session_id)
                self.server.log_event("queue-session-discard", session_id=session_id)
                self._json({"deleted": True, "session_id": session_id})
                return
            self._json({"error": "Unknown endpoint"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - local UI should surface errors clearly.
            self._error(exc)

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.debug:
            print(f"[sentriface-ui:http] {self.address_string()} {format % args}")

    def _profile(self) -> dict[str, Any]:
        config = self.server.config
        return {
            "runtime": self.server.runtime,
            "hardware_tier": config.hardware_tier,
            "data_dir": str(config.data_dir),
            "db_path": str(config.db_path),
            "max_workers": config.max_workers,
            "onnx_intra_threads": config.onnx_intra_threads,
            "max_image_edge": config.max_image_edge,
            "high_confidence": config.high_confidence,
            "medium_confidence": config.medium_confidence,
            "min_quality_score": config.min_quality_score,
        }

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise InputValidationError(
                "Invalid request length",
                "invalid_content_length",
            ) from exc
        if length < 0:
            raise InputValidationError("Invalid request length", "invalid_content_length")
        if length > JSON_REQUEST_LIMIT_BYTES:
            raise InputValidationError("Request is too large", "request_too_large")
        if length == 0:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InputValidationError("Request contains invalid JSON", "invalid_json") from exc
        if not isinstance(payload, dict):
            raise InputValidationError("JSON request must be an object", "invalid_json_shape")
        return payload

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_request_to_file(self, destination: Path, maximum_bytes: int) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise InputValidationError(
                "Invalid backup upload length",
                "invalid_content_length",
            ) from exc
        if content_length <= 0:
            raise InputValidationError("Backup upload is empty", "empty_file")
        if content_length > maximum_bytes:
            raise InputValidationError(
                "Portable backup exceeds the 20 GB import limit",
                "file_too_large",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        remaining = content_length
        try:
            with temporary.open("xb") as output:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise InputValidationError(
                            "Portable backup upload ended unexpectedly",
                            "incomplete_upload",
                        )
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _download_file(
        self,
        path: Path,
        download_name: str,
        content_type: str,
    ) -> None:
        size = path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{download_name}"',
        )
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with path.open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _error(self, exc: Exception) -> None:
        message = str(exc).strip("'")
        validation_error = isinstance(
            exc,
            (InputValidationError, InputImageError, KeyError, ValueError, TypeError),
        )
        if validation_error:
            reason = getattr(exc, "reason", "invalid_request")
            self.server.log_event(
                "input-rejected",
                endpoint=urlparse(self.path).path,
                rejected_count=1,
                accepted_count=0,
                reasons={reason: 1},
                message=message,
                client_side=False,
            )
        else:
            self.server.log_event("error", message=message)
        status = HTTPStatus.BAD_REQUEST
        if isinstance(exc, BackupError) and "not found" in str(exc).lower():
            status = HTTPStatus.NOT_FOUND
        if isinstance(exc, InputValidationError):
            status = HTTPStatus.UNPROCESSABLE_ENTITY
        payload = {"error": message}
        if validation_error:
            payload["code"] = "invalid_input"
            payload["reason"] = getattr(exc, "reason", "invalid_request")
        self._json(payload, status=status)

    def _media(self, raw_path: str) -> None:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise KeyError(f"Unsupported media file: {path}")
        data = path.read_bytes()
        content_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: Path = Path("data"),
    runtime: str = "dev",
    debug: bool = True,
) -> SentriFaceApiServer:
    profile = assess_hardware()
    config = config_for_hardware(profile, data_dir=data_dir)
    engine = build_dev_engine(data_dir, config) if runtime == "dev" else build_onnx_engine(config)
    engine.initialize()
    server = SentriFaceApiServer((host, port), engine=engine, config=config, runtime=runtime, debug=debug)
    server.log_event("startup", runtime=runtime, data_dir=str(data_dir), address=f"http://{host}:{server.server_port}")
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="SentriFace Edge local UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--runtime", choices=("dev", "onnx"), default="dev")
    parser.add_argument("--quiet-debug", action="store_true", help="Disable verbose UI debug logs")
    args = parser.parse_args()

    from sentriface.logging_config import setup_logging

    setup_logging(debug=not args.quiet_debug)
    server = create_server(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        runtime=args.runtime,
        debug=not args.quiet_debug,
    )
    print(f"SentriFace UI running at http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("SentriFace UI stopped")
    finally:
        server.server_close()
    return 0


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        raise KeyError(f"Missing required field: {key}")
    return str(value)


def _safe_count(value: Any, field: str, allow_zero: bool = False) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise InputValidationError(f"{field} must be an integer", "invalid_count") from exc
    minimum = 0 if allow_zero else 1
    if count < minimum or count > 100_000:
        raise InputValidationError(
            f"{field} must be between {minimum} and 100000",
            "invalid_count",
        )
    return count


def _safe_rejection_reasons(value: Any) -> dict[str, int]:
    if value is None:
        return {"invalid_input": 1}
    if not isinstance(value, dict) or len(value) > 20:
        raise InputValidationError("reasons must be a small object", "invalid_reasons")
    reasons: dict[str, int] = {}
    for raw_reason, raw_count in value.items():
        reason = str(raw_reason).strip().lower()
        if not reason or len(reason) > 50 or not reason.replace("_", "").isalnum():
            reason = "invalid_input"
        reasons[reason] = reasons.get(reason, 0) + _safe_count(raw_count, "reason count")
    return reasons or {"invalid_input": 1}


def _operation_id(payload: dict[str, Any]) -> str:
    value = _required(payload, "operation_id")
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise KeyError("operation_id must be a UUID") from exc


def _face_index(payload: dict[str, Any]) -> int:
    try:
        face_index = int(payload.get("face_index", 1))
    except (TypeError, ValueError) as exc:
        raise KeyError("face_index must be a positive integer") from exc
    if face_index < 1:
        raise KeyError("face_index must be a positive integer")
    return face_index


def _face_box(payload: dict[str, Any]) -> FaceBox | None:
    value = payload.get("face_box")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise KeyError("face_box must be an object")
    try:
        box = FaceBox(
            x=int(value["x"]),
            y=int(value["y"]),
            width=int(value["width"]),
            height=int(value["height"]),
            confidence=float(value.get("confidence", 1.0)),
        )
        if box.width <= 0 or box.height <= 0:
            raise ValueError("face box dimensions must be positive")
        return box
    except (KeyError, TypeError, ValueError) as exc:
        raise KeyError("face_box must contain numeric x, y, width, and height") from exc


def _query_value(query: str, key: str) -> str:
    values = parse_qs(query).get(key)
    if not values:
        raise KeyError(f"Missing required query: {key}")
    return values[0]


def _query_bool(query: str, key: str) -> bool:
    values = parse_qs(query).get(key)
    if not values:
        return False
    return values[0].strip().lower() in {"1", "true", "yes"}


def _image_paths(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() in IMAGE_EXTENSIONS else []
    if not source.exists():
        raise KeyError(f"Source path does not exist: {source}")
    return sorted(path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _save_upload(data_dir: Path, filename: str, data_url: str, upload_subdir: Path = Path("uploads")) -> Path:
    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise InputValidationError(
            f"Unsupported upload type: {suffix or filename}",
            "unsupported_extension",
        )
    if "," in data_url:
        _, encoded = data_url.split(",", 1)
    else:
        encoded = data_url
    try:
        data = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise InputValidationError("Invalid upload data", "invalid_base64") from exc
    return _save_upload_bytes(data_dir, filename, data, upload_subdir)


def _save_upload_bytes(data_dir: Path, filename: str, data: bytes, upload_subdir: Path = Path("uploads")) -> Path:
    declared_suffix = _normalize_image_suffix(Path(filename).suffix.lower())
    if declared_suffix not in {".jpg", ".png", ".bmp", ".webp"}:
        raise InputValidationError(
            f"Unsupported upload type: {Path(filename).suffix.lower() or filename}",
            "unsupported_extension",
        )
    if not data:
        raise InputValidationError("Upload is empty", "empty_file")
    if len(data) > UPLOAD_REQUEST_LIMIT_BYTES:
        raise InputValidationError(
            "Upload exceeds the 100 MB per-file limit",
            "file_too_large",
        )
    detected_suffix = _detect_image_suffix(data)
    if detected_suffix is None:
        raise InputValidationError(
            "File contents are not a supported image",
            "invalid_image_content",
        )
    if detected_suffix != declared_suffix:
        raise InputValidationError(
            "File contents do not match the file extension",
            "content_type_mismatch",
        )
    image = _decode_upload_image(data)
    height, width = image.shape[:2]
    if height <= 0 or width <= 0 or height * width > UPLOAD_MAX_PIXELS:
        raise InputValidationError(
            "Image dimensions exceed the safe processing limit",
            "unsafe_image_dimensions",
        )
    suffix = detected_suffix
    if len(data) > UPLOAD_RESIZE_LIMIT_BYTES:
        data, suffix = _reduce_upload_image(data, image=image)
    upload_dir = data_dir / upload_subdir
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)
    return target


def _upload_batch_subdir(upload_id: str) -> Path:
    try:
        normalized_id = uuid.UUID(str(upload_id)).hex
    except (ValueError, AttributeError) as exc:
        raise KeyError("Invalid upload id") from exc
    return Path("uploads") / "batches" / normalized_id


def _save_upload_chunk(
    data_dir: Path,
    upload_id: str,
    filename: str,
    relative_path: str,
    data: bytes,
) -> tuple[Path, Path]:
    batch_subdir = _upload_batch_subdir(upload_id)
    safe_path = _safe_relative_upload_path(relative_path or filename)
    saved = _save_upload_bytes(data_dir, filename, data, batch_subdir / safe_path.parent)
    return data_dir / batch_subdir, saved


def _discard_upload_batch(data_dir: Path, upload_id: str) -> bool:
    batch_dir = data_dir / _upload_batch_subdir(upload_id)
    if not batch_dir.exists():
        return False
    shutil.rmtree(batch_dir)
    return True


def _save_upload_batch(data_dir: Path, files: list[dict[str, Any]]) -> tuple[Path, int, int]:
    if not isinstance(files, list) or not files:
        raise InputValidationError("No files selected", "empty_selection")
    batch_subdir = Path("uploads") / "batches" / uuid.uuid4().hex
    batch_dir = data_dir / batch_subdir
    count = 0
    rejected = 0
    for item in files:
        if not isinstance(item, dict):
            rejected += 1
            continue
        try:
            filename = _required(item, "filename")
            relative_path = str(item.get("relative_path") or filename)
            data_url = _required(item, "data")
            safe_path = _safe_relative_upload_path(relative_path)
            saved = _save_upload(
                data_dir,
                safe_path.name,
                data_url,
                batch_subdir / safe_path.parent,
            )
            count += int(saved.exists())
        except (InputValidationError, KeyError, TypeError, ValueError):
            rejected += 1
    if count == 0:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise InputValidationError(
            "No valid image files selected",
            "no_valid_images",
        )
    return batch_dir, count, rejected


def _safe_relative_upload_path(relative_path: str) -> Path:
    if not isinstance(relative_path, str):
        raise InputValidationError("Invalid upload path", "invalid_path")
    normalized = relative_path.replace("\\", "/").strip()
    if (
        not normalized
        or len(normalized) > 1024
        or "\x00" in normalized
        or normalized.startswith("/")
    ):
        raise InputValidationError("Invalid upload path", "invalid_path")
    parts = Path(normalized).parts
    if (
        not parts
        or any(part in {"", ".", ".."} for part in parts)
        or any(len(part) > 255 or any(ord(char) < 32 for char in part) for part in parts)
        or parts[0].endswith(":")
    ):
        raise InputValidationError("Invalid upload path", "invalid_path")
    return Path(*parts)


def _detect_image_suffix(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"BM"):
        return ".bmp"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _normalize_image_suffix(suffix: str) -> str:
    return ".jpg" if suffix == ".jpeg" else suffix


def _decode_upload_image(data: bytes) -> Any:
    cv2 = _cv2()
    np = _numpy()
    encoded = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise InputValidationError(
            "Could not decode uploaded image",
            "invalid_image_content",
        )
    return image


def _reduce_upload_image(data: bytes, image: Any | None = None) -> tuple[bytes, str]:
    cv2 = _cv2()
    image = image if image is not None else _decode_upload_image(data)

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > UPLOAD_MAX_EDGE:
        scale = UPLOAD_MAX_EDGE / float(longest)
        image = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    for quality in (92, 88, 84, 80, 76, 72, 68):
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise KeyError("Could not encode uploaded image")
        reduced = buffer.tobytes()
        if len(reduced) <= UPLOAD_RESIZE_LIMIT_BYTES:
            return reduced, ".jpg"

    while len(reduced) > UPLOAD_RESIZE_LIMIT_BYTES:
        height, width = image.shape[:2]
        if max(height, width) <= 640:
            return reduced, ".jpg"
        image = cv2.resize(
            image,
            (max(1, int(width * 0.85)), max(1, int(height * 0.85))),
            interpolation=cv2.INTER_AREA,
        )
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 76])
        if not ok:
            raise KeyError("Could not encode uploaded image")
        reduced = buffer.tobytes()
    return reduced, ".jpg"


def _cv2() -> Any:
    try:
        import cv2

        return cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for upload size reduction") from exc


def _numpy() -> Any:
    try:
        import numpy

        return numpy
    except ImportError as exc:
        raise RuntimeError("NumPy is required for upload size reduction") from exc


def _recognition(engine: FaceEngine, result: RecognitionResult, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "decision": result.decision.value,
        "box": _box(result.face),
        "quality": _quality(result.quality),
        "matches": [_match(engine, match, rank) for rank, match in enumerate(result.matches, 1)],
    }


def _pending(engine: FaceEngine, pending: PendingAddition) -> dict[str, Any]:
    return {
        "pending_id": pending.pending_id,
        "source_image": pending.source_image,
        "crop_path": pending.face.crop_path,
        "decision": pending.decision.value,
        "box": _box(pending.face),
        "quality": _quality(pending.quality),
        "matches": [_match(engine, match, rank) for rank, match in enumerate(pending.matches, 1)],
        "created_at": pending.created_at,
    }


def _rejected(rejected: RejectedFace, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "source_image": rejected.source_image,
        "box": _box(rejected.face),
        "quality": _quality(rejected.quality),
    }


def _person(person: Person) -> dict[str, Any]:
    return {
        "person_id": person.person_id,
        "name": person.name,
        "metadata": person.metadata,
        "created_at": person.created_at,
        "deleted_at": person.deleted_at,
        "archived": person.deleted_at is not None,
    }


def _person_summary(summary: PersonSummary, engine: FaceEngine | None = None) -> dict[str, Any]:
    embeddings = (
        engine.list_person_embeddings(
            summary.person.person_id,
            include_archived=summary.person.deleted_at is not None,
        )
        if engine
        else []
    )
    return {
        **_person(summary.person),
        "embedding_count": summary.embedding_count,
        "favorite": bool(summary.person.metadata.get("favorite")),
        "tags": list(summary.person.metadata.get("tags", [])),
        "representative_image": _representative_image(
            embeddings,
            summary.person.metadata.get("representative_embedding_id"),
        ),
    }


def _embedding(record: EmbeddingRecord) -> dict[str, Any]:
    return {
        "embedding_id": record.embedding_id,
        "person_id": record.person_id,
        "quality_score": record.quality_score,
        "source_image": record.source_image,
        "crop_path": record.crop_path,
        "created_at": record.created_at,
    }


def _deleted_embedding(record: dict[str, Any]) -> dict[str, Any]:
    purge_after = str(record.get("purge_after") or "")
    try:
        deadline = datetime.fromisoformat(purge_after)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        seconds_remaining = max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
        days_remaining = max(0, int((seconds_remaining + 86_399) // 86_400))
    except ValueError:
        days_remaining = 0
    return {
        "embedding_id": record["embedding_id"],
        "person_id": record["person_id"],
        "person_name": record["name"],
        "person_archived": record["person_deleted_at"] is not None,
        "quality_score": record["quality_score"],
        "source_image": record["source_image"],
        "crop_path": record["crop_path"],
        "created_at": record["created_at"],
        "deleted_at": record["deleted_at"],
        "purge_after": purge_after,
        "days_remaining": days_remaining,
        "sighting_count": record["sighting_count"],
    }


def _recognition_detail(detail: RecognitionDetail) -> dict[str, Any]:
    return {
        "detail_id": detail.detail_id,
        "embedding_id": detail.embedding_id,
        "person_id": detail.person_id,
        "image_id": detail.image_id,
        "image_path": detail.image_path,
        "name": detail.name,
        "decision": detail.decision,
        "date": detail.seen_date,
        "time": detail.seen_time,
        "place_seen": detail.place_seen,
        "individual_count": detail.individual_count,
        "event_occasion": detail.event_occasion,
        "rank": detail.rank,
        "country": detail.country,
        "importance": detail.importance,
        "added_by": detail.added_by,
        "created_at": detail.created_at,
    }


def _person_change(change: PersonChange) -> dict[str, Any]:
    return {
        "change_id": change.change_id,
        "person_id": change.person_id,
        "previous_name": change.previous_name,
        "new_name": change.new_name,
        "previous_rank": change.previous_rank,
        "new_rank": change.new_rank,
        "previous_country": change.previous_country,
        "new_country": change.new_country,
        "previous_importance": change.previous_importance,
        "new_importance": change.new_importance,
        "editor_name": change.editor_name,
        "created_at": change.created_at,
    }


def _init_group(
    engine: FaceEngine,
    group: InitGroup,
    matches_by_face_id: dict[str, list[PersonMatch]] | None = None,
) -> dict[str, Any]:
    exclusions_by_face_id = engine.excluded_person_ids_for_init_faces(
        group.session_id,
        [face.init_face_id for face in group.faces],
    )
    face_matches = [
        _filtered_matches(
            matches_by_face_id.get(face.init_face_id, []),
            exclusions_by_face_id.get(face.init_face_id, set()),
        ) if matches_by_face_id is not None else engine.matches_for_vector(
            face.vector,
            excluded_person_ids=exclusions_by_face_id.get(face.init_face_id, set()),
        )
        for face in group.faces
    ]
    group_matches = _group_matches_from_face_matches(face_matches, engine.config.top_k)
    representative = _representative_init_face(group)
    return {
        "group_id": group.group_id,
        "session_id": group.session_id,
        "status": group.status,
        "representative_face_id": representative.init_face_id if representative else None,
        "representative_image": (representative.face.crop_path or representative.source_image) if representative else None,
        "matches": [_match(engine, match, rank) for rank, match in enumerate(group_matches, 1)],
        "faces": [
            {
                "init_face_id": face.init_face_id,
                "source_image": face.source_image,
                "crop_path": face.face.crop_path,
                "box": _box(face.face),
                "quality": _quality(face.quality),
                "matches": [_match(engine, match, rank) for rank, match in enumerate(face_matches[index], 1)],
            }
            for index, face in enumerate(group.faces)
        ],
    }


def _representative_init_face(group: InitGroup):
    if not group.faces:
        return None
    return max(group.faces, key=lambda face: face.quality.score)


def _init_session_summary(session: InitSession, groups: list[InitGroup]) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "source_path": session.source_path,
        "status": session.status,
        "created_at": session.created_at,
        "group_count": len(groups),
        "face_count": sum(len(group.faces) for group in groups),
        "pending_count": sum(1 for group in groups if group.status == "pending" and group.faces),
        "skipped_count": sum(1 for group in groups if group.status == "skipped" and group.faces),
    }


def _filtered_matches(matches: list[PersonMatch], excluded_person_ids: set[str]) -> list[PersonMatch]:
    if not excluded_person_ids:
        return matches
    return [match for match in matches if match.person_id not in excluded_person_ids]


def _group_matches_from_face_matches(
    face_matches: list[list[PersonMatch]],
    top_k: int,
) -> list[PersonMatch]:
    best_by_person: dict[str, PersonMatch] = {}
    for matches in face_matches:
        for match in matches:
            current = best_by_person.get(match.person_id)
            if current is None or match.score > current.score:
                best_by_person[match.person_id] = match
    group_matches = sorted(best_by_person.values(), key=lambda match: match.score, reverse=True)
    return group_matches[:top_k]


def _queue_face_ids(engine: FaceEngine, payload: dict[str, Any]) -> list[str]:
    face_ids = list(payload.get("face_ids") or [])
    if face_ids:
        return face_ids
    group = engine.get_init_group(_required(payload, "session_id"), _required(payload, "group_id"))
    return [face.init_face_id for face in group.faces]


def _match(engine: FaceEngine, match: PersonMatch, rank: int) -> dict[str, Any]:
    person = engine.get_person(match.person_id)
    embeddings = engine.list_person_embeddings(match.person_id) if person else []
    representative = _representative_image(embeddings)
    return {
        "rank": rank,
        "person_id": match.person_id,
        "name": person.name if person else "unknown",
        "score": match.score,
        "embedding_ids": list(match.embedding_ids),
        "embeddings_matched": match.embeddings_matched,
        "representative_image": representative,
    }


def _representative_image(
    embeddings: list[EmbeddingRecord],
    representative_embedding_id: str | None = None,
) -> str | None:
    if representative_embedding_id:
        for record in embeddings:
            if record.embedding_id == representative_embedding_id:
                return record.crop_path or record.source_image
    for record in embeddings:
        if record.source_image:
            return record.source_image
    for record in embeddings:
        if record.crop_path:
            return record.crop_path
    return None


def _has_duplicate_embedding(vector: tuple[float, ...], embeddings: list[EmbeddingRecord]) -> bool:
    return _duplicate_embedding(vector, embeddings) is not None


def _duplicate_embedding(vector: tuple[float, ...], embeddings: list[EmbeddingRecord]) -> EmbeddingRecord | None:
    for record in embeddings:
        if _cosine(vector, record.vector) >= DUPLICATE_MATCH_SCORE:
            return record
    return None


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _box(face) -> dict[str, Any]:
    return {
        "x": face.box.x,
        "y": face.box.y,
        "width": face.box.width,
        "height": face.box.height,
        "confidence": face.box.confidence,
        "quality_score": face.quality_score,
        "crop_path": face.crop_path,
    }


def _quality(report: QualityReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {"status": report.status.value, "score": report.score, "reasons": list(report.reasons)}


def _sanitize_log_details(details: dict[str, Any]) -> dict[str, Any]:
    """Keep production events useful without retaining image/vector payloads."""
    return {str(key): _sanitize_log_value(value) for key, value in details.items()}


def _sanitize_log_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_log_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary omitted; {len(value)} bytes>"
    if isinstance(value, (list, tuple, set, frozenset)):
        return f"<sequence omitted; {len(value)} items>"
    if hasattr(value, "shape"):
        return "<array omitted>"
    return f"<{type(value).__name__}>"


def _backup(record: BackupRecord) -> dict[str, Any]:
    return {
        "backup_id": record.backup_id,
        "created_at": record.created_at,
        "size_bytes": record.size_bytes,
        "people_count": record.people_count,
        "embedding_count": record.embedding_count,
        "verified": record.verified,
        "reason": record.reason,
        "operation_id": record.operation_id,
        "format_version": record.format_version,
        "portable": record.portable,
        "complete": record.complete,
        "file_count": record.file_count,
        "missing_file_count": record.missing_file_count,
        "reference_count": record.reference_count,
    }


if __name__ == "__main__":
    raise SystemExit(main())
