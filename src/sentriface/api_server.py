from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import ipaddress
import json
import os
import platform
import secrets
import shutil
import sys
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from sentriface import __version__
from sentriface.auth import (
    AUTH_COOKIE_NAME,
    RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION,
    AuthError,
    AuthService,
    AuthUser,
    auth_status_payload,
)
from sentriface.backup_service import BackupError, BackupRecord, BackupService
from sentriface.cli import build_dev_engine, build_onnx_engine
from sentriface.config import HardwareProfile, RuntimeConfig, config_for_hardware
from sentriface.engine import IMAGE_EXTENSIONS, FaceEngine
from sentriface.errors import InputImageError, InputValidationError, ModelSetupError, QueueCancellationError, SentriFaceError
from sentriface.hardware import assess_hardware
from sentriface.paths import default_data_dir, default_log_dir
from sentriface.recovery import RecoveryError, RecoveryService, available_recovery_destinations, recover_master_key
from sentriface.secure_storage import StorageSecurityError, database_is_encrypted, load_or_create_master_key, protect_existing_managed_data, store_master_key
from sentriface.secure_files import read_protected_bytes, write_protected_bytes
from sentriface.offline_guard import install_offline_guard, offline_guard_installed, require_local_path
from sentriface.os_network_policy import (
    OsNetworkPolicyError,
    OsNetworkPolicyStatus,
    inspect_os_network_policy,
    require_os_network_policy,
)
from sentriface.model_setup import MODEL_COMBINATIONS, install_local_model_bundle
from sentriface.models import (
    EmbeddingRecord,
    FaceBox,
    InitGroup,
    InitSession,
    PendingAddition,
    Person,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PersonSummary,
    QualityReport,
    RecognitionDetail,
    RecognitionResult,
    RejectedFace,
)
from sentriface.storage.sqlite_store import SCHEMA_VERSION
STATIC_DIR = Path(__file__).with_name("ui_static")
UPLOAD_RESIZE_LIMIT_BYTES = 1_000_000
UPLOAD_REQUEST_LIMIT_BYTES = 25_000_000
UPLOAD_MAX_EDGE = 1600
UPLOAD_MAX_PIXELS = 40_000_000
JSON_REQUEST_LIMIT_BYTES = 10_000_000
BACKUP_IMPORT_LIMIT_BYTES = 20_000_000_000
MODEL_UPLOAD_LIMIT_BYTES = 2_000_000_000
DUPLICATE_MATCH_SCORE = 0.9999
INFERENCE_ENDPOINTS = {
    "/api/recognize",
    "/api/recognize-batch",
    "/api/recognition-person-candidates",
    "/api/recognition-accept-existing",
    "/api/recognition-new",
    "/api/enroll",
    "/api/queue-add",
    "/api/queue-scan",
}
TERMINAL_QUEUE_STATES = {"done", "failed", "cancelled"}
QUEUE_PROGRESS_RETENTION_SECONDS = 3600
QUEUE_PROGRESS_LIMIT = 200
MAX_HTTP_HANDLERS = 8
_UPLOAD_OBJECT_LOCK = threading.Lock()


MODEL_SETUP_ALLOWED_ENDPOINTS = {
    "/api/health",
    "/api/models/status",
    "/api/models/upload",
    "/api/models/install",
    "/api/support-package",
}


PUBLIC_AUTH_ENDPOINTS = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/login"),
}


def _required_capability(method: str, path: str) -> str | None:
    if (method, path) in PUBLIC_AUTH_ENDPOINTS:
        return None
    if path in {"/api/auth/logout", "/api/auth/change-password"}:
        return "view"
    if path.startswith("/api/users"):
        return "administer"
    if path in {"/api/models/install", "/api/models/upload"}:
        return "administer"
    if method == "GET":
        if path == "/api/events":
            return "technical"
        if path in {"/api/recovery", "/api/recovery/destinations"}:
            return "recovery"
        if path == "/api/backups":
            return "backups"
        if path in {"/api/deleted-faces"}:
            return "destroy"
        if path in {"/api/pending", "/api/queue-progress", "/api/queue-sessions", "/api/queue-groups", "/api/queue-person-candidates"}:
            return "add"
        return "view"
    if method == "DELETE":
        return "backup_delete" if path.startswith("/api/backups/") else "add"
    if path in {"/api/backups/restore", "/api/backups/import"}:
        return "database_restore"
    if path in {"/api/recovery/configure", "/api/recovery/acknowledge"}:
        return "recovery"
    if path.startswith("/api/backups/") and path.endswith("/encrypted-download"):
        return "backups"
    if path in {"/api/backups", "/api/backup-db"}:
        return "backups"
    if path == "/api/support-package":
        return "technical"
    if path in {
        "/api/person-archive", "/api/person-restore", "/api/person-merge", "/api/person-merge-undo", "/api/person-purge",
        "/api/person-photo-move", "/api/person-photo-delete",
        "/api/person-photo-restore", "/api/person-photo-purge",
    }:
        return "destroy"
    if path in {
        "/api/upload", "/api/upload-batch", "/api/upload-chunk",
        "/api/upload-file-discard", "/api/upload-batch-discard",
        "/api/recognize", "/api/recognize-batch", "/api/input-rejections",
    }:
        return "recognize"
    if path in {
        "/api/enroll", "/api/person-placeholder", "/api/person-update", "/api/person-preferences",
        "/api/person-association", "/api/person-association-placeholder",
        "/api/person-association-remove",
        "/api/recognition-person-candidates",
        "/api/recognition-accept-existing", "/api/recognition-new",
        "/api/recognition-followup", "/api/queue-add", "/api/queue-cancel",
        "/api/queue-scan", "/api/queue-confirm-new", "/api/queue-confirm-existing",
        "/api/queue-refresh-suggestions", "/api/queue-discard", "/api/queue-skip",
        "/api/queue-resume-skipped", "/api/queue-reject-match",
        "/api/confirm-new", "/api/confirm-existing", "/api/reject-pending",
    }:
        return "add"
    return "view"


class EngineBusyError(RuntimeError):
    pass


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
        hardware_profile: HardwareProfile,
        runtime: str,
        debug: bool = True,
        model_ready: bool = True,
        model_error: str = "",
        os_network_policy: OsNetworkPolicyStatus | None = None,
    ) -> None:
        super().__init__(server_address, SentriFaceApiHandler)
        self.engine = engine
        self.config = config
        self.hardware_profile = hardware_profile
        self.runtime = runtime
        self.model_ready = model_ready
        self.model_error = model_error
        self.os_network_policy = os_network_policy
        self.model_fingerprints: dict[str, tuple[int, int]] = {}
        declaration = getattr(engine, "model_usage", None)
        self.model_usage = declaration if isinstance(declaration, dict) else {
            "usage_basis": "development",
            "terms_version": "development",
            "accepted_at": "",
        }
        if self.model_ready and self.runtime != "dev":
            self._capture_model_fingerprints()
        self.debug = debug
        self.session_token = secrets.token_urlsafe(32)
        self.events: list[dict[str, Any]] = []
        self.events_lock = threading.Lock()
        self.upload_object_index: dict[str, Path] | None = None
        self.upload_object_index_lock = threading.Lock()
        self.queue_progress: dict[str, dict[str, Any]] = {}
        self.queue_progress_lock = threading.Lock()
        self.queue_cancellations: dict[str, threading.Event] = {}
        self.queue_cancellation_created: dict[str, float] = {}
        self.active_queue_jobs: set[str] = set()
        self.operation_gate = OperationGate()
        self.inference_semaphore = threading.BoundedSemaphore(max(1, config.max_workers))
        self.request_semaphore = threading.BoundedSemaphore(MAX_HTTP_HANDLERS)
        self.backups = BackupService(
            config.db_path,
            config.backup_dir,
            retention_limit=config.backup_retention_limit,
            logger=self.log_event,
            data_dir=config.data_dir,
            supported_database_version=SCHEMA_VERSION,
            database_key=config.storage_key,
        )
        self.recovery = RecoveryService(config.data_dir, config.storage_key, self.backups)
        self.auth = AuthService(config.db_path, config.storage_key)
        self._scavenge_stale_files()
        self.maintenance_stop = threading.Event()
        self.maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            name="sentriface-retention",
            daemon=True,
        )
        self.maintenance_thread.start()
        self.network_policy_violation = False
        self.network_policy_stop = threading.Event()
        self.network_policy_thread = None
        if self.os_network_policy is not None:
            self.network_policy_thread = threading.Thread(
                target=self._network_policy_loop,
                name="sentriface-os-network-policy",
                daemon=True,
            )
            self.network_policy_thread.start()

    def indexed_upload_objects(self) -> dict[str, Path]:
        """Build the legacy upload hash index once, then reuse it in memory."""
        with self.upload_object_index_lock:
            if self.upload_object_index is not None:
                return self.upload_object_index
            upload_root = (self.config.data_dir / "uploads").resolve()
            indexed: dict[str, Path] = {}
            for raw_path in set(self.engine.store.list_all_file_references()):
                path = Path(raw_path)
                try:
                    resolved = path.resolve()
                    resolved.relative_to(upload_root)
                    if not resolved.is_file():
                        continue
                    digest = hashlib.sha256(
                        read_protected_bytes(resolved, self.config.storage_key)
                    ).hexdigest()
                except (OSError, ValueError, StorageSecurityError):
                    continue
                indexed.setdefault(digest, resolved)
            self.upload_object_index = indexed
            return indexed

    def _model_files(self) -> tuple[Path, ...]:
        model_dir = self.config.detector_model.parent
        return (
            self.config.detector_model,
            self.config.recognizer_model,
            model_dir / "calibration.json",
            model_dir / "model-usage.json",
        )

    def _capture_model_fingerprints(self) -> None:
        fingerprints: dict[str, tuple[int, int]] = {}
        for path in self._model_files():
            stat = path.stat()
            fingerprints[str(path.resolve())] = (stat.st_size, stat.st_mtime_ns)
        self.model_fingerprints = fingerprints

    def models_available(self) -> bool:
        if self.runtime == "dev":
            return True
        if not self.model_ready:
            return False
        try:
            for path in self._model_files():
                stat = path.stat()
                if self.model_fingerprints.get(str(path.resolve())) != (stat.st_size, stat.st_mtime_ns):
                    raise OSError(f"Model setup file changed or was replaced: {path.name}")
        except OSError as exc:
            self.model_ready = False
            self.model_error = str(exc)
            self.log_event("model-setup-required", error=self.model_error)
            return False
        return True

    def model_status(self, user: AuthUser | None) -> dict[str, Any]:
        ready = self.models_available()
        model_dir = self.config.detector_model.parent
        return {
            "ready": ready,
            "runtime": self.runtime,
            "error": "" if ready else self.model_error or "Recognition models are required",
            "can_configure": bool(user and user.has("administer")),
            "models_dir": str(model_dir) if user and user.has("administer") else None,
            "detector_target": str(model_dir / "detector.onnx") if user and user.has("administer") else None,
            "recognizer_target": str(model_dir / "recognizer.onnx") if user and user.has("administer") else None,
            "combinations": MODEL_COMBINATIONS,
            "requirements": {
                "detector": "SCRFD-compatible ONNX detector",
                "recognizer": "ArcFace-compatible ONNX recognizer with 512-dimensional embeddings",
                "calibration": "Optional hash-bound threshold file; built-in thresholds are used when omitted",
                "checksums": "SHA-256 is required for every supplied file",
            },
            "usage": self.model_usage if ready else None,
        }

    def recovery_readiness(self) -> dict[str, Any]:
        status = self.recovery.status()
        acknowledgement = self.auth.recovery_risk_acknowledgement() or {}
        ready = bool(
            status.get("configured")
            and status.get("destination_available")
            and status.get("recovery_kit_present")
            and int(status.get("external_backup_count") or 0) > 0
        )
        acknowledged = acknowledgement.get("version") == RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION
        return {
            "ready": ready,
            "configured": bool(status.get("configured")),
            "destination_available": bool(status.get("destination_available")),
            "recovery_kit_present": bool(status.get("recovery_kit_present")),
            "external_backup_present": int(status.get("external_backup_count") or 0) > 0,
            "acknowledged": acknowledged,
            "acknowledged_at": acknowledgement.get("acknowledged_at", ""),
            "acknowledged_by": acknowledgement.get("acknowledged_by", ""),
            "acknowledgement_version": RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION,
        }
    def activate_installed_models(self, model_dir: Path) -> None:
        config = replace(
            self.config,
            detector_model=model_dir / "detector.onnx",
            recognizer_model=model_dir / "recognizer.onnx",
        )
        candidate = build_onnx_engine(config)
        candidate.initialize()
        self.engine = candidate
        self.config = candidate.config
        declaration = getattr(candidate, "model_usage", None)
        self.model_usage = declaration if isinstance(declaration, dict) else {}
        self.model_error = ""
        self.model_ready = True
        self._capture_model_fingerprints()
        self.log_event(
            "models-activated",
            usage_basis=self.model_usage.get("usage_basis", "unknown"),
            detector=str(self.config.detector_model),
            recognizer=str(self.config.recognizer_model),
        )
    def process_request(self, request: Any, client_address: Any) -> None:
        if self.network_policy_violation:
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            finally:
                self.shutdown_request(request)
            return
        if not self.request_semaphore.acquire(timeout=0.25):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.request_semaphore.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_semaphore.release()
    def _scavenge_stale_files(self) -> None:
        """Retry journals and conservatively remove abandoned staging data."""
        cutoff = time.time() - 24 * 60 * 60
        try:
            self.engine.cleanup.retry_all(self.engine.store.list_all_file_references)
            stale_managed: list[Path] = []
            for root in (
                self.config.data_dir / "uploads",
                self.config.face_dir / "pending",
                self.config.face_dir / "init",
                self.config.data_dir / "restored-media",
            ):
                if not root.exists():
                    continue
                stale_managed.extend(
                    item for item in root.iterdir() if item.stat().st_mtime < cutoff
                )
            journal = self.engine.cleanup.schedule(stale_managed, "startup-orphan-scavenge")
            self.engine.cleanup.run(journal, self.engine.store.list_all_file_references)
            for root, pattern in (
                (self.config.data_dir, ".restore-*"),
                (self.config.backup_dir, ".import-*"),
            ):
                if not root.exists():
                    continue
                for item in root.glob(pattern):
                    if item.stat().st_mtime >= cutoff:
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        except OSError as exc:
            self.log_event("startup-scavenge-failed", error=str(exc))
    def log_event(self, event: str, **details: Any) -> None:
        safe_details = _sanitize_log_details(details)
        item = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **safe_details,
        }
        with getattr(self, "events_lock", threading.Lock()):
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
            self._prune_queue_progress_locked()

    def queue_progress_snapshot(self, job_id: str) -> dict[str, Any]:
        with self.queue_progress_lock:
            progress = dict(self.queue_progress.get(job_id, {"job_id": job_id, "status": "unknown"}))
        started_at = progress.get("started_at")
        ended_at = progress.get("finished_at") or time.time()
        progress["elapsed_seconds"] = max(0, int(ended_at - started_at)) if started_at else 0
        return progress

    def _prune_queue_progress_locked(self) -> None:
        now = time.time()
        stale = [
            job_id
            for job_id, item in self.queue_progress.items()
            if item.get("status") in TERMINAL_QUEUE_STATES
            and float(item.get("finished_at") or now) < now - QUEUE_PROGRESS_RETENTION_SECONDS
        ]
        for job_id in stale:
            self.queue_progress.pop(job_id, None)
        overflow = len(self.queue_progress) - QUEUE_PROGRESS_LIMIT
        if overflow > 0:
            oldest = sorted(
                self.queue_progress,
                key=lambda job_id: float(self.queue_progress[job_id].get("started_at") or 0),
            )
            removed = 0
            for job_id in oldest:
                if job_id in self.active_queue_jobs:
                    continue
                self.queue_progress.pop(job_id, None)
                removed += 1
                if removed >= overflow:
                    break
    def register_queue_job(self, job_id: str) -> threading.Event:
        with self.queue_progress_lock:
            self._prune_queue_cancellations_locked()
            if job_id in self.active_queue_jobs:
                raise ValueError(f"Queue job is already running: {job_id}")
            existing = self.queue_cancellations.get(job_id)
            if existing is not None:
                self.active_queue_jobs.add(job_id)
                return existing
            cancellation = threading.Event()
            self.queue_cancellations[job_id] = cancellation
            self.queue_cancellation_created[job_id] = time.time()
            self.active_queue_jobs.add(job_id)
            return cancellation

    def request_queue_cancellation(self, job_id: str) -> bool:
        with self.queue_progress_lock:
            self._prune_queue_cancellations_locked()
            progress = self.queue_progress.get(job_id)
            if progress and progress.get("status") in {"done", "failed", "cancelled"}:
                return False
            cancellation = self.queue_cancellations.get(job_id)
            if cancellation is None:
                # Preserve cancellation if this request wins the race with queue-scan registration.
                cancellation = threading.Event()
                self.queue_cancellations[job_id] = cancellation
                self.queue_cancellation_created[job_id] = time.time()
            cancellation.set()
            current = dict(progress or {"job_id": job_id, "started_at": time.time()})
            current.update(status="cancelling", phase="cancelling", cancellation_requested_at=time.time())
            self.queue_progress[job_id] = current
            return True

    def finish_queue_job(self, job_id: str) -> None:
        with self.queue_progress_lock:
            self.queue_cancellations.pop(job_id, None)
            self.queue_cancellation_created.pop(job_id, None)
            self.active_queue_jobs.discard(job_id)

    def _prune_queue_cancellations_locked(self) -> None:
        cutoff = time.time() - 60
        stale = [
            job_id
            for job_id, created_at in self.queue_cancellation_created.items()
            if created_at < cutoff and job_id not in self.active_queue_jobs
        ]
        for job_id in stale:
            self.queue_cancellations.pop(job_id, None)
            self.queue_cancellation_created.pop(job_id, None)

    @contextmanager
    def inference_slot(self):
        if not self.inference_semaphore.acquire(timeout=0.25):
            raise EngineBusyError("Face engine is busy; please retry in a moment")
        try:
            yield
        finally:
            self.inference_semaphore.release()
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
                    automatic = self.recovery.automatic_backup_if_due(self.config.automatic_backup_interval_hours)
                    if automatic is not None:
                        self.log_event("automatic-recovery-backup", backup_id=automatic.backup_id)
            except Exception as exc:  # noqa: BLE001 - maintenance must not terminate the UI server.
                self.log_event("deleted-face-retention-failed", error=str(exc).strip("'"))
            if self.maintenance_stop.wait(3600):
                break

    def _network_policy_loop(self) -> None:
        while not self.network_policy_stop.wait(30):
            try:
                status = inspect_os_network_policy()
            except Exception as exc:  # Fail closed if OS inspection itself breaks.
                status = OsNetworkPolicyStatus(
                    False,
                    "inspection-failed",
                    str(exc).strip("'") or "OS network policy inspection failed",
                )
            self.os_network_policy = status
            if status.enforced:
                continue
            self.network_policy_violation = True
            self.log_event(
                "os-network-policy-lost",
                mechanism=status.mechanism,
                error=status.detail,
            )
            self.shutdown()
            break

    def server_close(self) -> None:
        queue_progress_lock = getattr(self, "queue_progress_lock", None)
        queue_cancellations = getattr(self, "queue_cancellations", None)
        if queue_progress_lock is not None and queue_cancellations is not None:
            with queue_progress_lock:
                for cancellation in queue_cancellations.values():
                    cancellation.set()
        maintenance_stop = getattr(self, "maintenance_stop", None)
        maintenance_thread = getattr(self, "maintenance_thread", None)
        if maintenance_stop is not None:
            maintenance_stop.set()
        if maintenance_thread is not None and maintenance_thread.is_alive():
            maintenance_thread.join(timeout=2)
        network_policy_stop = getattr(self, "network_policy_stop", None)
        network_policy_thread = getattr(self, "network_policy_thread", None)
        if network_policy_stop is not None:
            network_policy_stop.set()
        if network_policy_thread is not None and network_policy_thread.is_alive():
            network_policy_thread.join(timeout=2)
        super().server_close()


class SentriFaceApiHandler(SimpleHTTPRequestHandler):
    server: SentriFaceApiServer
    auth_user: AuthUser | None = None
    pending_auth_cookie: str | None = None

    def log_message(self, format: str, *args: object) -> None:
        """Never put session-bearing query strings into operational logs."""
        if self.server.debug:
            print(f"[sentriface-http] {self.command} {urlparse(self.path).path}")
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.path == "/":
            return str(STATIC_DIR / "index.html")
        root = STATIC_DIR.resolve()
        candidate = (root / parsed.path.lstrip("/")).resolve()
        if candidate != root and root not in candidate.parents:
            return str(root / "__invalid_path__")
        return str(candidate)

    def _valid_host(self) -> bool:
        raw = self.headers.get("Host", "")
        if not raw:
            return False
        hostname = raw
        if raw.startswith("["):
            hostname = raw[1:].split("]", 1)[0]
        elif ":" in raw:
            hostname = raw.rsplit(":", 1)[0]
        if hostname.casefold() == "localhost":
            return True
        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False

    def _reject_invalid_host(self) -> bool:
        if self._valid_host():
            return False
        self._json({"error": "SentriFace accepts localhost requests only"}, status=HTTPStatus.FORBIDDEN)
        return True

    def _valid_origin(self) -> bool:
        raw = self.headers.get("Origin")
        if not raw:
            return True
        parsed = urlparse(raw)
        return (
            parsed.scheme == "http"
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
            and parsed.netloc.casefold() == self.headers.get("Host", "").casefold()
        )

    def _reject_invalid_origin(self) -> bool:
        if self._valid_origin():
            return False
        self._json(
            {"error": "SentriFace accepts browser requests only from its own origin"},
            status=HTTPStatus.FORBIDDEN,
        )
        return True

    def _valid_session(self) -> bool:
        supplied = self.headers.get("X-SentriFace-Session", "")
        if not supplied and urlparse(self.path).path == "/media":
            supplied = parse_qs(urlparse(self.path).query).get("session", [""])[0]
        return bool(supplied) and secrets.compare_digest(supplied, self.server.session_token)

    def _reject_invalid_session(self) -> bool:
        if self._valid_session():
            return False
        self._json(
            {"error": "SentriFace session authorization is required"},
            status=HTTPStatus.UNAUTHORIZED,
        )
        return True

    def _auth_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        cookies = SimpleCookie()
        try:
            cookies.load(raw)
        except Exception:
            return ""
        morsel = cookies.get(AUTH_COOKIE_NAME)
        return morsel.value if morsel else ""

    def _reject_user_authorization(self, method: str, path: str) -> bool:
        required = _required_capability(method, path)
        user = self.server.auth.authenticate(self._auth_token())
        self.auth_user = user
        if required is None:
            return False
        if self.server.auth.setup_required():
            self._json(
                {"error": "Create the first administrator account before using SentriFace", "code": "setup_required"},
                status=HTTPStatus.PRECONDITION_REQUIRED,
            )
            return True
        if user is None:
            self._json({"error": "Sign in to continue", "code": "authentication_required"}, status=HTTPStatus.UNAUTHORIZED)
            return True
        if not user.has(required):
            self.server.log_event("authorization-denied", username=user.username, capability=required, endpoint=path)
            self._json(
                {"error": "Your account is not allowed to perform this operation", "code": "permission_denied", "required_capability": required},
                status=HTTPStatus.FORBIDDEN,
            )
            return True
        return False

    def _reject_model_readiness(self, path: str) -> bool:
        if (
            self.server.runtime == "dev"
            or path in MODEL_SETUP_ALLOWED_ENDPOINTS
            or path.startswith("/api/auth/")
        ):
            return False
        if self.server.models_available():
            return False
        self._json(
            {
                "error": self.server.model_error or "Recognition models must be configured before SentriFace can continue",
                "code": "models_required",
            },
            status=HTTPStatus.PRECONDITION_REQUIRED,
        )
        return True
    def _set_auth_cookie(self, token: str) -> None:
        self.pending_auth_cookie = f"{AUTH_COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={8 * 60 * 60}"

    def _clear_auth_cookie(self) -> None:
        self.pending_auth_cookie = f"{AUTH_COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"

    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
        )
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()
    def do_GET(self) -> None:
        if self._reject_invalid_host():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") or parsed.path == "/media":
            if (
                self._reject_invalid_origin()
                or self._reject_invalid_session()
                or self._reject_user_authorization("GET", parsed.path)
                or self._reject_model_readiness(parsed.path)
            ):
                return
        if parsed.path in {"/api/health", "/api/profile", "/api/queue-progress"}:
            self._do_GET()
            return
        with self.server.operation_gate.shared():
            self._do_GET()

    def do_POST(self) -> None:
        if (
            self._reject_invalid_host()
            or self._reject_invalid_origin()
            or self._reject_invalid_session()
        ):
            return
        parsed = urlparse(self.path)
        if self._reject_user_authorization("POST", parsed.path):
            return
        if self._reject_model_readiness(parsed.path):
            return
        if parsed.path == "/api/queue-cancel":
            self._do_POST()
            return
        gate = (
            self.server.operation_gate.exclusive()
            if parsed.path in {"/api/backups/restore", "/api/models/install"}
            else self.server.operation_gate.shared()
        )
        with gate:
            if parsed.path in INFERENCE_ENDPOINTS:
                try:
                    with self.server.inference_slot():
                        self._do_POST()
                except EngineBusyError as exc:
                    self._error(exc)
            else:
                self._do_POST()

    def do_DELETE(self) -> None:
        if (
            self._reject_invalid_host()
            or self._reject_invalid_origin()
            or self._reject_invalid_session()
        ):
            return
        parsed = urlparse(self.path)
        if self._reject_user_authorization("DELETE", parsed.path):
            return
        if self._reject_model_readiness(parsed.path):
            return
        with self.server.operation_gate.shared():
            self._do_DELETE()
    def _do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._serve_index()
                return
            if parsed.path == "/api/health":
                self._json({"status": "ok", "runtime": self.server.runtime})
                return
            if parsed.path == "/api/auth/status":
                self._json(auth_status_payload(self.server.auth, self.auth_user))
                return
            if parsed.path == "/api/models/status":
                self._json(self.server.model_status(self.auth_user))
                return
            if parsed.path == "/api/users":
                self._json({"users": self.server.auth.list_users(), "roles": self.server.auth.role_catalog()})
                return
            if parsed.path == "/api/profile":
                self._json(self._profile())
                return
            if parsed.path == "/api/recovery/readiness":
                self._json(self.server.recovery_readiness())
                return
            if parsed.path == "/api/recovery/destinations":
                self._json({"destinations": available_recovery_destinations()})
                return
            if parsed.path == "/api/recovery":
                self._json(self.server.recovery.status())
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
                associations = self.server.engine.list_person_associations(
                    person_id,
                    include_archived=include_archived,
                )
                person_summaries = {
                    item.person.person_id: item
                    for item in [
                        *self.server.engine.list_persons(),
                        *self.server.engine.list_persons(archived=True),
                    ]
                }
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
                        "associations": [
                            _person_association(
                                association,
                                person_id,
                                person_summaries,
                                self.server.engine,
                            )
                            for association in associations
                        ],
                    }
                )
                return
            if parsed.path == "/api/pending":
                self._json({"pending": [_pending(self.server.engine, item) for item in self.server.engine.list_pending_additions()]})
                return
            if parsed.path == "/api/events":
                with self.server.events_lock:
                    events = list(self.server.events[-80:])
                self._json({"events": events})
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
            if parsed.path == "/api/queue-person-candidates":
                session_id = _query_value(parsed.query, "session_id")
                group_id = _query_value(parsed.query, "group_id")
                group = self.server.engine.get_init_group(session_id, group_id)
                candidates = self.server.engine.ranked_people_for_init_group(group)
                self._json({
                    "candidates": [
                        {
                            **_person_summary_from_embeddings(candidate.summary, candidate.embeddings),
                            "match": {
                                "rank": rank,
                                **_match_policy(self.server.engine, candidate.match.score),
                            } if candidate.match else None,
                        }
                        for rank, candidate in enumerate(candidates, 1)
                    ]
                })
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
            if parsed.path == "/api/support-package":
                package = _support_package_bytes(self.server)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                self.server.log_event(
                    "support-package-exported",
                    actor=self.auth_user.username,
                )
                self._download_bytes(
                    package,
                    f"sentriface-support-{timestamp}.zip",
                    "application/zip",
                )
                return
            if parsed.path == "/api/models/upload":
                kind = _query_value(parsed.query, "kind").strip().casefold()
                if kind not in {"detector", "recognizer"}:
                    raise InputValidationError(
                        "Model upload kind must be detector or recognizer",
                        "invalid_model_kind",
                    )
                filename = Path(_query_value(parsed.query, "filename")).name
                if not filename.casefold().endswith(".onnx"):
                    raise InputValidationError(
                        "Choose an ONNX model file",
                        "unsupported_model_file",
                    )
                model_dir = require_local_path(
                    self.server.config.detector_model.parent
                )
                upload_dir = model_dir / ".uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                for previous in upload_dir.glob(f"{kind}-*.onnx"):
                    previous.unlink(missing_ok=True)
                staged_path = (
                    upload_dir / f"{kind}-{uuid.uuid4().hex}.onnx"
                )
                digest, size = self._stream_model_upload(staged_path)
                self.server.log_event(
                    "model-file-selected",
                    actor=self.auth_user.username,
                    kind=kind,
                    filename=filename,
                    size=size,
                    sha256=digest,
                )
                self._json(
                    {
                        "kind": kind,
                        "filename": filename,
                        "path": str(staged_path),
                        "size": size,
                        "sha256": digest,
                    },
                    status=HTTPStatus.CREATED,
                )
                return
            if parsed.path == "/api/backups/import":
                filename = _query_value(parsed.query, "filename")
                encrypted = filename.lower().endswith(".sfbackup.enc")
                if not encrypted:
                    raise InputValidationError(
                        "Choose a password-encrypted SentriFace .sfbackup.enc file",
                        "unsupported_backup_type",
                    )
                passphrase = _decode_backup_passphrase(
                    self.headers.get("X-SentriFace-Backup-Passphrase", "")
                )
                import_dir = self.server.config.backup_dir / ".imports"
                suffix = ".sfbackup.enc"
                import_path = import_dir / f"{uuid.uuid4().hex}{suffix}"
                try:
                    self._stream_request_to_file(
                        import_path,
                        maximum_bytes=BACKUP_IMPORT_LIMIT_BYTES,
                    )
                    record = self.server.backups.import_encrypted_backup(
                        import_path, passphrase
                    )
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
                        "Upload exceeds the 25 MB per-file limit",
                        "file_too_large",
                    )
                saved_dir, saved_path = _save_upload_chunk(
                    self.server.config.data_dir,
                    _query_value(parsed.query, "upload_id"),
                    _query_value(parsed.query, "filename"),
                    _query_value(parsed.query, "relative_path"),
                    self.rfile.read(content_length),
                    self.server.config.storage_key,
                    self.server.indexed_upload_objects(),
                )
                self._json({
                    "path": str(saved_dir),
                    "stored_path": str(saved_path),
                    "stored_size": saved_path.stat().st_size,
                })
                return
            payload = self._read_json()
            if parsed.path == "/api/auth/signup":
                user, token = self.server.auth.signup_initial(_required(payload, "username"), str(payload.get("display_name") or ""), _required(payload, "password"))
                self._set_auth_cookie(token)
                self.server.log_event("initial-admin-created", username=user.username)
                self._json(auth_status_payload(self.server.auth, user), status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/auth/login":
                user, token = self.server.auth.login(_required(payload, "username"), _required(payload, "password"))
                self._set_auth_cookie(token)
                self.server.log_event("login", username=user.username)
                self._json(auth_status_payload(self.server.auth, user))
                return
            if parsed.path == "/api/auth/logout":
                username = self.auth_user.username if self.auth_user else "unknown"
                self.server.auth.logout(self._auth_token())
                self._clear_auth_cookie()
                self.server.log_event("logout", username=username)
                self._json({"logged_out": True})
                return
            if parsed.path == "/api/auth/change-password":
                self.server.auth.change_password(self.auth_user, _required(payload, "current_password"), _required(payload, "new_password"))
                self._clear_auth_cookie()
                self.server.log_event("password-changed", username=self.auth_user.username)
                self._json({"password_changed": True, "reauthentication_required": True})
                return
            if parsed.path == "/api/users":
                user = self.server.auth.create_user(self.auth_user, _required(payload, "username"), str(payload.get("display_name") or ""), _required(payload, "password"), list(payload.get("roles") or []))
                self.server.log_event("account-created", actor=self.auth_user.username, username=user["username"])
                self._json({"user": user}, status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/users/update":
                user = self.server.auth.update_user(self.auth_user, _required(payload, "user_id"), str(payload.get("display_name") or ""), list(payload.get("roles") or []), bool(payload.get("disabled")))
                self.server.log_event("account-updated", actor=self.auth_user.username, username=user["username"])
                self._json({"user": user})
                return
            if parsed.path == "/api/users/reset-password":
                target_id = _required(payload, "user_id")
                self.server.auth.reset_password(self.auth_user, target_id, _required(payload, "password"))
                self.server.log_event("account-password-reset", actor=self.auth_user.username, target_user_id=target_id)
                self._json({"password_reset": True})
                return
            if parsed.path == "/api/models/install":
                if payload.get("accept_responsibility") is not True:
                    raise InputValidationError(
                        "Accept responsibility for model licensing and biometric use before continuing",
                        "model_responsibility_required",
                    )
                choice_id = _required(payload, "combination_id")
                choices = [
                    item
                    for group in MODEL_COMBINATIONS.values()
                    for item in group
                ]
                choice = next((item for item in choices if item["id"] == choice_id), None)
                if choice is None:
                    raise InputValidationError("Choose a supported model combination", "unsupported_model_combination")
                detector_source = require_local_path(Path(_required(payload, "detector_path")))
                recognizer_source = require_local_path(Path(_required(payload, "recognizer_path")))
                calibration_path = str(payload.get("calibration_path") or "").strip()
                calibration_sha256 = str(payload.get("calibration_sha256") or "").strip()
                if bool(calibration_path) != bool(calibration_sha256):
                    raise InputValidationError(
                        "Provide both the calibration threshold file path and its SHA-256, or leave both empty",
                        "incomplete_calibration",
                    )
                calibration_source = (
                    require_local_path(Path(calibration_path)) if calibration_path else None
                )
                model_dir = require_local_path(self.server.config.detector_model.parent)
                declaration = install_local_model_bundle(
                    model_dir,
                    detector_source=detector_source,
                    detector_sha256=_required(payload, "detector_sha256"),
                    recognizer_source=recognizer_source,
                    recognizer_sha256=_required(payload, "recognizer_sha256"),
                    calibration_source=calibration_source,
                    calibration_sha256=calibration_sha256 or None,
                    calibration_profile=choice_id,
                    usage_basis=choice["usage_basis"],
                    authorized_by=self.auth_user.display_name or self.auth_user.username,
                    organization=str(payload.get("organization") or ""),
                    licensor=str(payload.get("licensor") or ""),
                    license_reference=str(payload.get("license_reference") or ""),
                    license_name=str(payload.get("license_name") or ""),
                )
                for source in (detector_source, recognizer_source):
                    upload_dir = model_dir / ".uploads"
                    if upload_dir in source.parents:
                        source.unlink(missing_ok=True)
                try:
                    (model_dir / ".uploads").rmdir()
                except OSError:
                    pass
                try:
                    self.server.activate_installed_models(model_dir)
                except Exception as exc:
                    self.server.model_ready = False
                    self.server.model_error = f"The supplied model bundle could not be activated: {exc}"
                    raise ModelSetupError(self.server.model_error) from exc
                self.server.log_event(
                    "model-bundle-installed",
                    actor=self.auth_user.username,
                    combination_id=choice_id,
                    usage_basis=declaration["usage_basis"],
                )
                self._json(self.server.model_status(self.auth_user), status=HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/api/backups/") and parsed.path.endswith("/encrypted-download"):
                backup_id = parsed.path.removeprefix("/api/backups/").removesuffix("/encrypted-download").strip("/")
                passphrase = _required(payload, "passphrase")
                export_dir = self.server.config.backup_dir / ".exports"
                export_path = export_dir / f"{backup_id}-{uuid.uuid4().hex}"
                exported = None
                try:
                    exported = self.server.backups.export_encrypted_backup(backup_id, export_path, passphrase)
                    self._download_file(
                        exported,
                        download_name=f"{backup_id}.sfbackup.enc",
                        content_type="application/octet-stream",
                    )
                finally:
                    if exported is not None:
                        exported.unlink(missing_ok=True)
                    try:
                        export_dir.rmdir()
                    except OSError:
                        pass
                return
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
            if parsed.path == "/api/recovery/configure":
                result = self.server.recovery.configure(Path(_required(payload, "destination")))
                try:
                    initial_backup = self.server.recovery.automatic_backup_if_due(self.server.config.automatic_backup_interval_hours)
                    if initial_backup is not None:
                        result["initial_backup_id"] = initial_backup.backup_id
                        result.update(self.server.recovery.status())
                except Exception as exc:  # Keep the one-time recovery code visible even if the first export fails.
                    result["initial_backup_error"] = str(exc)
                    self.server.log_event("automatic-recovery-backup-failed", error=str(exc))
                result["readiness"] = self.server.recovery_readiness()
                self.server.log_event("disaster-recovery-configured", destination=result["destination"])
                self._json(result)
                return
            if parsed.path == "/api/recovery/acknowledge":
                if payload.get("acknowledge_risk") is not True:
                    raise InputValidationError(
                        "Explicit disaster-recovery risk acknowledgement is required",
                        "acknowledgement_required",
                    )
                self.server.auth.acknowledge_recovery_risk(
                    self.auth_user,
                    str(payload.get("acknowledgement_version") or ""),
                )
                self.server.log_event(
                    "disaster-recovery-risk-acknowledged",
                    actor=self.auth_user.username,
                )
                self._json({"readiness": self.server.recovery_readiness()})
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
                with self.server.upload_object_index_lock:
                    self.server.upload_object_index = None
                self.server.log_event("app-state-restored", **result)
                self._json({"restore": result})
                return
            if parsed.path == "/api/upload":
                saved_path = _save_upload(
                    self.server.config.data_dir,
                    _required(payload, "filename"),
                    _required(payload, "data"),
                    storage_key=self.server.config.storage_key,
                    known_objects=self.server.indexed_upload_objects(),
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
                    self.server.config.storage_key,
                    self.server.indexed_upload_objects(),
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
            if parsed.path == "/api/upload-file-discard":
                path = require_local_path(Path(_required(payload, "path")))
                journal = self.server.engine.cleanup.schedule(
                    (path,),
                    f"ui-discard-upload-{uuid.uuid4()}",
                )
                removed = self.server.engine.cleanup.run(
                    journal,
                    self.server.engine.store.list_all_file_references,
                )
                self._json({"removed": removed and not path.exists()})
                return
            if parsed.path == "/api/upload-batch-discard":
                removed = _discard_upload_batch(
                    self.server.config.data_dir,
                    _required(payload, "upload_id"),
                )
                self._json({"removed": removed})
                return
            if parsed.path == "/api/recognize":
                image_path = require_local_path(Path(_required(payload, "path")))
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
                source = require_local_path(Path(_required(payload, "path")))
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
            if parsed.path == "/api/recognition-person-candidates":
                image_path = require_local_path(Path(_required(payload, "path")))
                candidates = self.server.engine.ranked_people_for_recognition_face(
                    image_path,
                    int(_required(payload, "face_index")),
                    expected_box=_face_box(payload),
                )
                self._json({
                    "candidates": [
                        {
                            **_person_summary_from_embeddings(candidate.summary, candidate.embeddings),
                            "match": {
                                "rank": rank,
                                **_match_policy(self.server.engine, candidate.match.score),
                            } if candidate.match else None,
                        }
                        for rank, candidate in enumerate(candidates, 1)
                    ]
                })
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
            if parsed.path == "/api/person-placeholder":
                tags = payload.get("tags", [])
                if not isinstance(tags, list):
                    raise KeyError("tags must be a list")
                person = self.server.engine.create_placeholder_person(
                    name=_required(payload, "name"),
                    metadata={
                        "rank": str(payload.get("rank") or "").strip(),
                        "country": str(payload.get("country") or "").strip(),
                        "importance": str(payload.get("importance") or "").strip(),
                        "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
                    },
                    editor_name=self.auth_user.display_name or self.auth_user.username,
                    operation_id=_operation_id(payload),
                )
                summary = next(
                    item for item in self.server.engine.list_persons()
                    if item.person.person_id == person.person_id
                )
                result = _person_summary(summary, self.server.engine)
                self.server.log_event("person-placeholder-created", person_id=person.person_id)
                self._json({"person": result})
                return
            if parsed.path == "/api/person-association":
                source_person_id = _required(payload, "source_person_id")
                association = self.server.engine.create_person_association(
                    source_person_id=source_person_id,
                    target_person_id=_required(payload, "target_person_id"),
                    actor_name=self.auth_user.display_name or self.auth_user.username,
                    operation_id=_operation_id(payload),
                )
                person_summaries = {
                    item.person.person_id: item
                    for item in self.server.engine.list_persons()
                }
                result = _person_association(
                    association,
                    source_person_id,
                    person_summaries,
                    self.server.engine,
                )
                self.server.log_event(
                    "person-association-created",
                    association_id=association.association_id,
                    source_person_id=source_person_id,
                    target_person_id=_required(payload, "target_person_id"),
                )
                self._json({"association": result})
                return
            if parsed.path == "/api/person-association-placeholder":
                source_person_id = _required(payload, "source_person_id")
                person, association = self.server.engine.create_placeholder_association(
                    source_person_id=source_person_id,
                    name=_required(payload, "name"),
                    metadata={},
                    actor_name=self.auth_user.display_name or self.auth_user.username,
                    operation_id=_operation_id(payload),
                )
                summary = next(
                    item for item in self.server.engine.list_persons()
                    if item.person.person_id == person.person_id
                )
                result = _person_association(
                    association,
                    source_person_id,
                    {person.person_id: summary},
                    self.server.engine,
                )
                self.server.log_event(
                    "person-association-placeholder-created",
                    association_id=association.association_id,
                    source_person_id=source_person_id,
                    target_person_id=person.person_id,
                )
                self._json({"association": result, "person": _person_summary(summary, self.server.engine)})
                return
            if parsed.path == "/api/person-association-remove":
                result = self.server.engine.remove_person_association(
                    association_id=_required(payload, "association_id"),
                    actor_name=self.auth_user.display_name or self.auth_user.username,
                    operation_id=_operation_id(payload),
                )
                self.server.log_event("person-association-removed", **result)
                self._json(result)
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
            if parsed.path == "/api/person-purge":
                person_id = _required(payload, "person_id")
                operation_id = _operation_id(payload)
                person = self.server.engine.get_person(person_id, include_archived=True)
                existing = self.server.engine.get_person_operation(operation_id, "purge-person")
                if person is None and existing is None:
                    raise KeyError(f"Unknown person: {person_id}")
                result = self.server.backed_up_people_deletion(
                    operation_id,
                    "purge-person",
                    f"before-person-permanent-delete-{person.name if person else 'deleted'}-{person_id[:8]}",
                    lambda: self.server.engine.permanently_delete_person(
                        person_id,
                        operation_id,
                    ),
                )
                self.server.log_event("person-purge", **result)
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
            if parsed.path == "/api/person-merge-undo":
                merge_operation_id = _required(payload, "merge_operation_id")
                operation_id = _operation_id(payload)
                merge = self.server.engine.get_person_operation(merge_operation_id, "merge-persons")
                if merge is None:
                    raise KeyError("Unknown merge operation")
                source_id = str(merge["source_person_id"])
                target_id = str(merge["target_person_id"])
                result = self.server.backed_up_people_deletion(
                    operation_id,
                    "undo-merge-persons",
                    f"before-person-merge-undo-{source_id[:8]}-from-{target_id[:8]}",
                    lambda: self.server.engine.undo_merge_persons(
                        merge_operation_id,
                        operation_id,
                    ),
                )
                source = next(
                    item for item in self.server.engine.list_persons() if item.person.person_id == source_id
                )
                target = next(
                    item for item in self.server.engine.list_persons() if item.person.person_id == target_id
                )
                response = {
                    **result,
                    "source_person": _person_summary(source, self.server.engine),
                    "target_person": _person_summary(target, self.server.engine),
                }
                self.server.log_event("person-merge-undo", **result)
                self._json(response)
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
                    raise KeyError("Move the face to Deleted Faces before erasing it from the live library")
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
                image_path = require_local_path(Path(_required(payload, "path")))
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
                    journal = self.server.engine.cleanup.schedule(
                        (addition.face.crop_path,),
                        f"duplicate-prepared-crop-{addition.pending_id}",
                    )
                    self.server.engine.cleanup.run(
                        journal, self.server.engine.store.list_all_file_references
                    )
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
                embedding_id = self.server.engine.confirm_existing_person(addition, person_id, operation_id=_optional_operation_id(payload))
                self.server.log_event("recognition-accept-existing", path=str(image_path), person_id=person_id, face_index=face_index)
                self._json({"embedding_id": embedding_id, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/recognition-new":
                image_path = require_local_path(Path(_required(payload, "path")))
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
                person_id = self.server.engine.confirm_new_person(addition, name, operation_id=_optional_operation_id(payload))
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
                    operation_id=_optional_operation_id(payload),
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
                image_path = require_local_path(Path(_required(payload, "path")))
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
                image_path = require_local_path(Path(_required(payload, "path")))
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
            if parsed.path == "/api/queue-cancel":
                job_id = str(_required(payload, "job_id"))
                cancel_requested = self.server.request_queue_cancellation(job_id)
                self.server.log_event(
                    "queue-cancel-requested",
                    job_id=job_id,
                    cancel_requested=cancel_requested,
                )
                self._json(
                    {
                        "job_id": job_id,
                        "cancel_requested": cancel_requested,
                        "status": self.server.queue_progress_snapshot(job_id).get("status"),
                    }
                )
                return
            if parsed.path == "/api/queue-scan":
                source = require_local_path(Path(_required(payload, "path")))
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
                cancellation = self.server.register_queue_job(job_id)
                try:
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
                    try:
                        queue_result = self.server.engine.create_queue_session(
                            source,
                            bool(payload.get("force_bad_quality", False)),
                            progress_callback=lambda update: self.server.update_queue_progress(job_id, **update),
                            cancel_check=cancellation.is_set,
                        )
                    except QueueCancellationError as exc:
                        self.server.update_queue_progress(
                            job_id,
                            phase="cancelled",
                            status="cancelled",
                            session_id="",
                            cancellation_phase=exc.phase,
                            finished_at=time.time(),
                        )
                        self.server.log_event(
                            "queue-cancelled",
                            path=str(source),
                            job_id=job_id,
                            cancellation_phase=exc.phase,
                        )
                        self._json(
                            {
                                "cancelled": True,
                                "job_id": job_id,
                                "session_id": "",
                                "groups": [],
                                "metrics": self.server.engine.metrics_snapshot(),
                            }
                        )
                        return
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
                except Exception:
                    self.server.update_queue_progress(
                        job_id,
                        phase="failed",
                        status="failed",
                        finished_at=time.time(),
                    )
                    raise
                finally:
                    self.server.finish_queue_job(job_id)
            if parsed.path == "/api/queue-confirm-new":
                session_id = _required(payload, "session_id")
                person_id, accepted = self.server.engine.confirm_init_faces(
                    session_id,
                    _required(payload, "group_id"),
                    _queue_face_ids(self.server.engine, payload),
                    _required(payload, "name"),
                    _optional_operation_id(payload),
                )
                try:
                    changed = self.server.engine.changed_init_groups_for_person(session_id, person_id)
                    groups = self.server.engine.list_init_groups(session_id)
                except KeyError:
                    # A retry can arrive after the successful request already
                    # discarded its now-empty queue session.
                    changed = []
                    groups = []
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
                    _optional_operation_id(payload),
                )
                try:
                    changed = self.server.engine.changed_init_groups_for_person(session_id, person_id)
                    groups = self.server.engine.list_init_groups(session_id)
                except KeyError:
                    # A retry can arrive after the successful request already
                    # discarded its now-empty queue session.
                    changed = []
                    groups = []
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
                if _query_value(parsed.query, "confirm") != backup_id:
                    raise InputValidationError(
                        "Type the exact backup ID to confirm deletion",
                        "backup_confirmation_mismatch",
                    )
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
        profile = {
            "application": {
                "name": "SentriFace Edge",
                "version": __version__,
                "database_schema_version": SCHEMA_VERSION,
            },
            "runtime": self.server.runtime,
            "hardware_tier": config.hardware_tier,
            "hardware": {
                "cpu_count": self.server.hardware_profile.cpu_count,
                "memory_gb": self.server.hardware_profile.memory_gb,
                "reason": self.server.hardware_profile.reason,
                "operating_system": platform.system(),
                "architecture": platform.machine(),
            },
            "data_dir": str(config.data_dir),
            "db_path": str(config.db_path),
            "max_workers": config.max_workers,
            "onnx_intra_threads": config.onnx_intra_threads,
            "max_image_edge": config.max_image_edge,
            "detector_input_size": config.detector_input_size,
            "batch_size": config.batch_size,
            "prefer_small_models": config.prefer_small_models,
            "models": {
                "detector": str(config.detector_model),
                "recognizer": str(config.recognizer_model),
            },
            "offline_enforcement": {
                "loopback_only": True,
                "outbound_socket_guard": offline_guard_installed(),
                "os_network_enforced": bool(
                    self.server.os_network_policy
                    and self.server.os_network_policy.enforced
                ),
                "os_network_mechanism": (
                    self.server.os_network_policy.mechanism
                    if self.server.os_network_policy
                    else "not-verified"
                ),
            },
            "storage_security": {
                "database_encrypted": database_is_encrypted(config.db_path),
                "managed_files_encrypted": bool(config.storage_key),
                "managed_backups_encrypted": bool(config.storage_key),
                "persistent_logs_encrypted": bool(config.storage_key),
                "key_protection": "operating-system-vault" if config.storage_key else "none",
            },
            "recovery": self.server.recovery.status(),
            "recovery_readiness": self.server.recovery_readiness(),
            "index": self.server.engine.index_status,
            "high_confidence": config.high_confidence,
            "medium_confidence": config.medium_confidence,
            "possible_confidence": config.possible_confidence,
            "min_quality_score": config.min_quality_score,
            "model_usage": {
                "usage_basis": self.server.model_usage.get("usage_basis", "unknown"),
                "terms_version": self.server.model_usage.get("terms_version", ""),
                "accepted_at": self.server.model_usage.get("accepted_at", ""),
                "licensor": self.server.model_usage.get("licensor", ""),
                "license_name": self.server.model_usage.get("license_name", ""),
                "research_only": self.server.model_usage.get("usage_basis") == "noncommercial-research",
            },
        }
        if not self.auth_user or not self.auth_user.has("technical"):
            for sensitive in ("data_dir", "db_path", "models", "storage_security", "recovery"):
                profile.pop(sensitive, None)
        return profile

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

    def _serve_index(self) -> None:
        template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        marker = "__SENTRIFACE_SESSION_TOKEN__"
        if marker not in template:
            raise RuntimeError("UI index is missing the session-token injection point")
        body = template.replace(marker, self.server.session_token).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        self.send_response(status)
        if self.pending_auth_cookie:
            self.send_header("Set-Cookie", self.pending_auth_cookie)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The operation lifecycle is independent of a disconnected browser.
            pass

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
        self.server.backups.require_import_upload_space(content_length)
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

    def _stream_model_upload(self, destination: Path) -> tuple[str, int]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise InputValidationError(
                "Invalid model upload length",
                "invalid_content_length",
            ) from exc
        if content_length <= 0:
            raise InputValidationError("Model upload is empty", "empty_file")
        if content_length > MODEL_UPLOAD_LIMIT_BYTES:
            raise InputValidationError(
                "Model file exceeds the 2 GB limit",
                "file_too_large",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        available = shutil.disk_usage(destination.parent).free
        if available < (content_length * 2) + 512 * 1024 * 1024:
            raise InputValidationError(
                "Not enough free disk space to stage and install this model",
                "insufficient_disk_space",
            )
        temporary = destination.with_name(
            f".{destination.name}.{uuid.uuid4().hex}.tmp"
        )
        digest = hashlib.sha256()
        remaining = content_length
        try:
            with temporary.open("xb") as output:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise InputValidationError(
                            "Model upload ended unexpectedly",
                            "incomplete_upload",
                        )
                    output.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
            return digest.hexdigest(), content_length
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

    def _download_bytes(
        self,
        content: bytes,
        download_name: str,
        content_type: str,
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{download_name}"',
        )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

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
        if isinstance(exc, ModelSetupError):
            status = HTTPStatus.UNPROCESSABLE_ENTITY
        if isinstance(exc, EngineBusyError):
            status = HTTPStatus.SERVICE_UNAVAILABLE
        if isinstance(exc, AuthError):
            status = exc.status
        payload = {"error": message}
        if isinstance(exc, EngineBusyError):
            payload["code"] = "engine_busy"
        if isinstance(exc, AuthError):
            payload["code"] = exc.code
        if isinstance(exc, ModelSetupError):
            payload["code"] = "model_setup_failed"
        if validation_error:
            payload["code"] = "invalid_input"
            payload["reason"] = getattr(exc, "reason", "invalid_request")
        self._json(payload, status=status)

    def _media(self, raw_path: str) -> None:
        path = Path(raw_path).resolve()
        data_root = self.server.config.data_dir.resolve()
        referenced = {
            Path(item).resolve()
            for item in self.server.engine.store.list_all_file_references()
            if item
        }
        managed = path == data_root or data_root in path.parents
        if not managed and path not in referenced:
            self.send_response(HTTPStatus.FORBIDDEN)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not path.exists() or not path.is_file():
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise KeyError(f"Unsupported media file: {path}")
        content_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "application/octet-stream")
        data = read_protected_bytes(path, self.server.config.storage_key)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: Path | None = None,
    runtime: str = "onnx",
    detector_model: Path | None = None,
    recognizer_model: Path | None = None,
    debug: bool = True,
    os_network_policy: OsNetworkPolicyStatus | None = None,
) -> SentriFaceApiServer:
    install_offline_guard()
    normalized_host = host.strip().casefold()
    if normalized_host == "localhost":
        host = "127.0.0.1"
    else:
        try:
            address = ipaddress.ip_address(normalized_host)
        except ValueError as exc:
            raise ValueError("Server host must be localhost or a loopback IP address") from exc
        if not address.is_loopback or address.version != 4:
            raise ValueError("Server may bind only to an IPv4 loopback address")
    if runtime not in {"dev", "onnx"}:
        raise ValueError("Runtime must be dev or onnx")
    data_dir = require_local_path(data_dir or default_data_dir())
    profile = assess_hardware()
    config = config_for_hardware(profile, data_dir=data_dir)
    config = replace(config, storage_key=load_or_create_master_key(data_dir))
    protect_existing_managed_data(data_dir, config.storage_key)
    if detector_model is not None or recognizer_model is not None:
        config = replace(
            config,
            detector_model=detector_model or config.detector_model,
            recognizer_model=recognizer_model or config.recognizer_model,
        )
    require_local_path(config.detector_model)
    require_local_path(config.recognizer_model)
    model_ready = True
    model_error = ""
    if runtime == "dev":
        engine = build_dev_engine(data_dir, config)
    else:
        try:
            engine = build_onnx_engine(config)
        except Exception as exc:
            model_ready = False
            model_error = str(exc).strip("'") or "Recognition models are missing or invalid"
            engine = build_dev_engine(data_dir, config)
    config = engine.config
    engine.initialize()
    server = SentriFaceApiServer(
        (host, port),
        engine=engine,
        config=config,
        hardware_profile=profile,
        runtime=runtime,
        debug=debug,
        model_ready=model_ready,
        model_error=model_error,
        os_network_policy=os_network_policy,
    )
    server.log_event("startup", runtime=runtime, data_dir=str(data_dir), address=f"http://{host}:{server.server_port}")
    if not model_ready:
        server.log_event("model-setup-required", error=model_error)
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="SentriFace Edge local UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--detector-model", type=Path)
    parser.add_argument("--recognizer-model", type=Path)
    parser.add_argument("--runtime", choices=("dev", "onnx"), default="onnx")
    parser.add_argument(
        "--allow-unpackaged-source-onnx",
        action="store_true",
        help=(
            "Allow real ONNX inference from a macOS Git checkout without the "
            "packaged App Sandbox boundary; unavailable in packaged builds"
        ),
    )
    parser.add_argument("--quiet-debug", action="store_true", help="Disable verbose UI debug logs")
    parser.add_argument("--recover-kit", type=Path, help="Install a disaster-recovery key before startup")
    args = parser.parse_args()

    from sentriface.logging_config import setup_logging

    try:
        os_network_policy = _startup_network_policy(
            args.runtime,
            allow_unpacked_macos_source=args.allow_unpackaged_source_onnx,
        )
        if args.allow_unpackaged_source_onnx and os_network_policy is None:
            print(
                "WARNING: macOS source ONNX mode uses the loopback listener and "
                "application socket guard, but not the packaged App Sandbox boundary."
            )
        require_local_path(args.data_dir)
        if args.recover_kit:
            require_local_path(args.recover_kit)
            from getpass import getpass
            recovered_key = recover_master_key(args.recover_kit, getpass("SentriFace recovery code: "))
            store_master_key(args.data_dir, recovered_key)
        storage_key = load_or_create_master_key(args.data_dir)
        setup_logging(
            debug=not args.quiet_debug,
            log_dir=default_log_dir(args.data_dir),
            storage_key=storage_key,
        )
        server = create_server(
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
            runtime=args.runtime,
            detector_model=args.detector_model,
            recognizer_model=args.recognizer_model,
            debug=not args.quiet_debug,
            os_network_policy=os_network_policy,
        )
    except ModelSetupError as exc:
        print(f"SentriFace could not start: {exc}")
        print("Install verified models with: sentriface-models")
        return 2
    except (
        SentriFaceError,
        StorageSecurityError,
        RecoveryError,
        OsNetworkPolicyError,
        OSError,
        ValueError,
    ) as exc:
        print(f"SentriFace could not start safely: {exc}")
        return 2
    print(f"SentriFace UI running at http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("SentriFace UI stopped")
    finally:
        server.server_close()
    return 0



def _startup_network_policy(
    runtime: str,
    *,
    allow_unpacked_macos_source: bool = False,
    source_root: Path | None = None,
) -> OsNetworkPolicyStatus | None:
    if runtime != "onnx":
        if allow_unpacked_macos_source:
            raise ValueError(
                "--allow-unpackaged-source-onnx requires --runtime onnx"
            )
        return None
    if not allow_unpacked_macos_source:
        return require_os_network_policy()
    if sys.platform != "darwin":
        raise ValueError(
            "--allow-unpackaged-source-onnx is available only on macOS"
        )
    checkout = source_root or Path(__file__).resolve().parents[2]
    if getattr(sys, "frozen", False) or not (checkout / ".git").exists():
        raise ValueError(
            "--allow-unpackaged-source-onnx requires an unpackaged Git checkout"
        )
    status = inspect_os_network_policy()
    return status if status.enforced else None


def _decode_backup_passphrase(value: str) -> str:
    if not value:
        raise InputValidationError(
            "Encrypted backup passphrase is required",
            "backup_passphrase_required",
        )
    try:
        raw = base64.b64decode(
            value + ("=" * (-len(value) % 4)),
            altchars=b"-_",
            validate=True,
        )
        return raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise InputValidationError(
            "Encrypted backup passphrase header is invalid",
            "invalid_backup_passphrase",
        ) from exc

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


def _optional_operation_id(payload: dict[str, Any]) -> str:
    if not str(payload.get("operation_id") or "").strip():
        return str(uuid.uuid4())
    return _operation_id(payload)

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


def _save_upload(data_dir: Path, filename: str, data_url: str, upload_subdir: Path = Path("uploads"), storage_key: bytes | None = None, known_objects: dict[str, Path] | None = None) -> Path:
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
    return _save_upload_bytes(data_dir, filename, data, upload_subdir, storage_key, known_objects)


def _save_upload_bytes(data_dir: Path, filename: str, data: bytes, upload_subdir: Path = Path("uploads"), storage_key: bytes | None = None, known_objects: dict[str, Path] | None = None) -> Path:
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
            "Upload exceeds the 25 MB per-file limit",
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
    stored = _store_upload_object(data_dir, data, suffix, storage_key, known_objects)
    if upload_subdir == Path("uploads"):
        return stored
    return _stage_upload_object(data_dir / upload_subdir, stored, suffix)


def _store_upload_object(
    data_dir: Path,
    data: bytes,
    suffix: str,
    storage_key: bytes | None,
    known_objects: dict[str, Path] | None = None,
) -> Path:
    """Store one physical copy of identical uploaded image bytes."""
    digest = hashlib.sha256(data).hexdigest()
    target = data_dir / "uploads" / "objects" / f"{digest}{suffix}"
    with _UPLOAD_OBJECT_LOCK:
        if target.exists():
            existing_digest = hashlib.sha256(
                read_protected_bytes(target, storage_key)
            ).hexdigest()
            if existing_digest != digest:
                raise StorageSecurityError(
                    f"Stored upload object failed its content check: {target.name}"
                )
            return target
        legacy = known_objects.get(digest) if known_objects is not None else None
        if legacy is not None and legacy.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(legacy, target)
            except OSError:
                write_protected_bytes(target, data, storage_key)
        else:
            write_protected_bytes(target, data, storage_key)
        if known_objects is not None:
            known_objects[digest] = target
    return target


def _stage_upload_object(stage_dir: Path, stored: Path, suffix: str) -> Path:
    """Expose a canonical object inside a queue batch without copying bytes."""
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged = stage_dir / f"{stored.stem}-{uuid.uuid4().hex}{suffix}"
    os.link(stored, staged)
    return staged


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
    storage_key: bytes | None = None,
    known_objects: dict[str, Path] | None = None,
) -> tuple[Path, Path]:
    batch_subdir = _upload_batch_subdir(upload_id)
    safe_path = _safe_relative_upload_path(relative_path or filename)
    saved = _save_upload_bytes(data_dir, filename, data, batch_subdir / safe_path.parent, storage_key, known_objects)
    return data_dir / batch_subdir, saved


def _discard_upload_batch(data_dir: Path, upload_id: str) -> bool:
    batch_dir = data_dir / _upload_batch_subdir(upload_id)
    if not batch_dir.exists():
        return False
    shutil.rmtree(batch_dir)
    return True


def _save_upload_batch(data_dir: Path, files: list[dict[str, Any]], storage_key: bytes | None = None, known_objects: dict[str, Path] | None = None) -> tuple[Path, int, int]:
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
                storage_key,
                known_objects,
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
        "enrollment_status": person.enrollment_status,
        "is_placeholder": person.enrollment_status == "placeholder",
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
    return _person_summary_from_embeddings(summary, embeddings)


def _person_summary_from_embeddings(
    summary: PersonSummary,
    embeddings: list[EmbeddingRecord] | tuple[EmbeddingRecord, ...],
) -> dict[str, Any]:
    return {
        **_person(summary.person),
        "embedding_count": summary.embedding_count,
        "sighting_count": summary.sighting_count,
        "last_seen_at": summary.last_seen_at,
        "favorite": bool(summary.person.metadata.get("favorite")),
        "tags": list(summary.person.metadata.get("tags", [])),
        "representative_image": _representative_image(
            embeddings,
            summary.person.metadata.get("representative_embedding_id"),
        ),
    }


def _person_association(
    association: PersonAssociation,
    current_person_id: str,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> dict[str, Any]:
    associated_person_id = (
        association.target_person_id
        if association.source_person_id == current_person_id
        else association.source_person_id
    )
    summary = person_summaries.get(associated_person_id)
    if summary is None:
        raise RuntimeError("An associated person record is unavailable")
    return {
        "association_id": association.association_id,
        "source_person_id": association.source_person_id,
        "target_person_id": association.target_person_id,
        "relationship_type": association.relationship_type,
        "created_at": association.created_at,
        "updated_at": association.updated_at,
        "created_by": association.created_by,
        "person": _person_summary(summary, engine),
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
        "previous_status": change.previous_status,
        "new_status": change.new_status,
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
        "representative_image": _available_image_path(
            representative.face.crop_path,
            representative.source_image,
        ) if representative else None,
        "matches": [_match(engine, match, rank) for rank, match in enumerate(group_matches, 1)],
        "faces": [
            {
                "init_face_id": face.init_face_id,
                "source_image": face.source_image,
                "crop_path": face.face.crop_path,
                "image_path": _available_image_path(
                    face.face.crop_path,
                    face.source_image,
                ),
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
        **_match_policy(engine, match.score),
    }


def _match_policy(engine: FaceEngine, score: float) -> dict[str, Any]:
    config = engine.config
    if score >= DUPLICATE_MATCH_SCORE:
        classification = "duplicate"
    elif score >= config.high_confidence:
        classification = "strong"
    elif score >= config.medium_confidence:
        classification = "likely"
    elif score >= config.possible_confidence:
        classification = "possible"
    else:
        classification = "unknown"
    return {
        "classification": classification,
        "is_known": classification != "unknown",
        "is_duplicate": classification == "duplicate",
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
        if record.crop_path:
            return record.crop_path
    for record in embeddings:
        if record.source_image:
            return record.source_image
    return None


def _available_image_path(*candidates: str | None) -> str | None:
    """Prefer the first image that is still available, then a stable fallback.

    Queue crops should normally exist, but an interrupted cleanup or manually
    moved data must not make a whole group look empty when its source upload is
    still readable.
    """
    paths = [candidate for candidate in candidates if candidate]
    for candidate in paths:
        if Path(candidate).is_file():
            return candidate
    return paths[0] if paths else None


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


def _support_diagnostic_report(server: SentriFaceApiServer) -> dict[str, Any]:
    """Return troubleshooting facts without identity data or local paths."""
    config = server.config
    with server.events_lock:
        events = list(server.events)
    event_counts: dict[str, int] = {}
    event_history: list[dict[str, str]] = []
    for item in events:
        event_name = str(item.get("event") or "unknown")
        event_counts[event_name] = event_counts.get(event_name, 0) + 1
        event_history.append({
            "timestamp": str(item.get("timestamp") or ""),
            "event": event_name,
        })
    security = {
        "database_encrypted": database_is_encrypted(config.db_path),
        "managed_files_encrypted": bool(config.storage_key),
        "managed_backups_encrypted": bool(config.storage_key),
        "persistent_logs_encrypted": bool(config.storage_key),
        "key_protection": "operating-system-vault" if config.storage_key else "none",
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "application": {
            "name": "SentriFace Edge",
            "version": __version__,
            "database_schema_version": SCHEMA_VERSION,
        },
        "runtime": server.runtime,
        "hardware": {
            "tier": config.hardware_tier,
            "cpu_count": server.hardware_profile.cpu_count,
            "memory_gb": server.hardware_profile.memory_gb,
            "operating_system": platform.system(),
            "architecture": platform.machine(),
        },
        "processing": {
            "max_workers": config.max_workers,
            "onnx_intra_threads": config.onnx_intra_threads,
            "max_image_edge": config.max_image_edge,
            "detector_input_size": config.detector_input_size,
            "batch_size": config.batch_size,
            "prefer_small_models": config.prefer_small_models,
        },
        "models": {
            "ready": server.models_available(),
            "detector": config.detector_model.name,
            "recognizer": config.recognizer_model.name,
            "usage": {
                "usage_basis": server.model_usage.get("usage_basis", "unknown"),
                "terms_version": server.model_usage.get("terms_version", ""),
                "licensor": server.model_usage.get("licensor", ""),
                "license_name": server.model_usage.get("license_name", ""),
            },
        },
        "offline_enforcement": {
            "loopback_only": True,
            "outbound_socket_guard": offline_guard_installed(),
            "os_network_enforced": bool(server.os_network_policy and server.os_network_policy.enforced),
            "os_network_mechanism": server.os_network_policy.mechanism if server.os_network_policy else "not-verified",
        },
        "storage_security": security,
        "recovery_readiness": {
            key: value
            for key, value in server.recovery_readiness().items()
            if key in {
                "ready", "configured", "destination_available",
                "recovery_kit_present", "external_backup_present", "acknowledged",
            }
        },
        "index": {
            "requested": server.engine.index_status.get("requested"),
            "actual": server.engine.index_status.get("actual"),
            "degraded": bool(server.engine.index_status.get("degraded_reason")),
        },
        "events": {
            "total": len(event_history),
            "counts": event_counts,
            "history": event_history,
        },
    }


def _support_package_bytes(server: SentriFaceApiServer) -> bytes:
    report = _support_diagnostic_report(server)
    readme = (
        "SentriFace Edge support package\n\n"
        "This package contains application, system, runtime, configuration, model filename, "
        "database schema, protection, recovery-readiness, and event-type/timestamp information.\n\n"
        "It does not contain face images, source images, embeddings, names, identity records, "
        "database contents, arbitrary event details, secrets, or local file paths.\n"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostic-report.json", json.dumps(report, indent=2, sort_keys=True))
        archive.writestr("README.txt", readme)
    return output.getvalue()


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
