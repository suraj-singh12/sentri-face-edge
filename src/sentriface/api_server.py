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
import signal
import sys
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from loguru import logger

from sentriface import __version__
from sentriface.api_serializers import embedding_record_payload
from sentriface.auth import (
    AUTH_COOKIE_NAME,
    RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION,
    AuthError,
    AuthService,
    AuthUser,
    auth_status_payload,
)
from sentriface.backup_service import (
    BackupError,
    BackupRecord,
    BackupRestoreError,
    BackupService,
)
from sentriface.cli import (
    build_dev_engine,
    build_onnx_engine,
    build_onnx_recognition_runtime,
)
from sentriface.config import HardwareProfile, RuntimeConfig, config_for_hardware
from sentriface.engine import DomainWorkflowUnavailableError, IMAGE_EXTENSIONS, FaceEngine
from sentriface.errors import (
    EncounterRelationConflict,
    GraphProjectionPostcheckError,
    GraphProjectionRebuildRefused,
    InputImageError,
    InputValidationError,
    ModelSetupError,
    OperationRevertPostcheckError,
    OperationRevertRefused,
    QueueCancellationError,
    SentriFaceError,
    StructuredRepairPostcheckError,
    StructuredRepairRefused,
)
from sentriface.hardware import assess_hardware
from sentriface.integrity_recovery_service import (
    IntegrityRecoveryApplication,
    RecoveryPreparationRefused,
    RecoveryTokenError,
)
from sentriface.logging_config import redact_log_text, sanitize_log_details
from sentriface.licensing import LicenseAuthority
from sentriface.licensing.authority import packaged_windows_license_enforced
from sentriface.paths import default_data_dir, default_log_dir
from sentriface.recovery import RecoveryError, RecoveryService, available_recovery_destinations, recover_master_key
from sentriface.secure_storage import StorageSecurityError, database_is_encrypted, load_or_create_master_key, protect_existing_managed_data, store_master_key, validate_recovered_master_key
from sentriface.secure_storage import load_linux_source_master_key
from sentriface.secure_files import read_protected_bytes, write_protected_bytes
from sentriface.offline_guard import install_offline_guard, offline_guard_installed, require_local_path
from sentriface.os_network_policy import (
    OsNetworkPolicyError,
    OsNetworkPolicyStatus,
    inspect_os_network_policy,
    require_os_network_policy,
)
from sentriface.model_activation import (
    ModelActivationRefused,
    ModelActivationService,
    resolve_startup_model_bundle,
)
from sentriface.model_bundle import ModelBundleAuthority, _limit_for_kind
from sentriface.runtime_hardening import (
    InstanceLock,
    RuntimeReadinessError,
    WindowsShutdownSignal,
    cleanup_managed_temporaries,
    validate_managed_storage,
)
from sentriface.model_setup import MODEL_COMBINATIONS
from sentriface.models import (
    EmbeddingRecord,
    FaceBox,
    GraphConnection,
    GraphReadEdge,
    GraphReadFilter,
    GraphReadNode,
    InitGroup,
    InitSession,
    MatchDecision,
    Note,
    Observation,
    PendingAddition,
    PhotoReview,
    Person,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PersonIntelligence,
    PersonGraphReadModel,
    PersonSummary,
    QualityReport,
    RecognitionDetail,
    RecognitionResult,
    RejectedFace,
    Sighting,
    WorldGraphReadModel,
    WorldDetailLevel,
    WorldCollection,
    WorldGraphRequest,
    WorldGraphV2ReadModel,
    WorldReadFilter,
    WorldReadLimits,
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
    "/api/reference-prepare",
    "/api/recognize",
    "/api/recognize-batch",
    "/api/recognition-person-candidates",
    "/api/recognition-accept-existing",
    "/api/placeholder-enroll",
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
    "/api/models/activation/prepare",
    "/api/models/activation/execute",
    "/api/models/rollback/prepare",
    "/api/models/rollback/execute",
    "/api/support-package",
}
MODEL_OPERATION_REQUEST_FIELDS = {
    "/api/models/activation/prepare": frozenset({"bundle_id"}),
    "/api/models/activation/execute": frozenset({"token", "operation_id", "reason"}),
    "/api/models/rollback/prepare": frozenset(),
    "/api/models/rollback/execute": frozenset({"token", "operation_id", "reason"}),
}
MODEL_INSTALL_REQUEST_FIELDS = frozenset({
    "combination_id",
    "detector_upload_id",
    "recognizer_upload_id",
    "calibration_upload_id",
    "organization",
    "licensor",
    "license_reference",
    "license_name",
    "accept_responsibility",
})
INTEGRITY_RECOVERY_ENDPOINTS = {
    "/api/integrity/check",
    "/api/integrity/graph-rebuild/prepare",
    "/api/integrity/graph-rebuild/execute",
    "/api/integrity/repairs/r01/prepare",
    "/api/integrity/repairs/r01/execute",
    "/api/integrity/repairs/r02/prepare",
    "/api/integrity/repairs/r02/execute",
    "/api/integrity/revert-operations",
    "/api/integrity/reverts/prepare",
    "/api/integrity/reverts/execute",
}
INTEGRITY_RECOVERY_REQUEST_FIELDS = {
    "/api/integrity/check": frozenset(),
    "/api/integrity/graph-rebuild/prepare": frozenset({"report_token", "action_id"}),
    "/api/integrity/graph-rebuild/execute": frozenset({"token", "operation_id", "reason"}),
    "/api/integrity/repairs/r01/prepare": frozenset({"report_token", "action_id"}),
    "/api/integrity/repairs/r01/execute": frozenset({"token", "operation_id", "reason"}),
    "/api/integrity/repairs/r02/prepare": frozenset({"report_token", "action_id"}),
    "/api/integrity/repairs/r02/execute": frozenset({"token", "operation_id", "reason"}),
    "/api/integrity/reverts/prepare": frozenset({"operation_id"}),
    "/api/integrity/reverts/execute": frozenset({"token", "operation_id", "reason"}),
}


PUBLIC_AUTH_ENDPOINTS = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/login"),
}

LICENSE_ENDPOINTS = {
    "/api/license/status",
    "/api/license/activate",
}


def _license_exempt_endpoint(method: str, path: str) -> bool:
    """The explicit recovery shell that remains available without a license."""
    if (method, path) in PUBLIC_AUTH_ENDPOINTS or path.startswith("/api/auth/"):
        return True
    if path in LICENSE_ENDPOINTS or path == "/api/health":
        return True
    if path.startswith("/api/models/"):
        return True
    if path in INTEGRITY_RECOVERY_ENDPOINTS or path.startswith("/api/integrity/"):
        return True
    if path.startswith("/api/backups") or path == "/api/backup-db":
        return True
    if path.startswith("/api/recovery"):
        return True
    if path in {"/api/profile", "/api/events", "/api/support-package"}:
        return True
    return False


def _required_capability(method: str, path: str) -> str | None:
    if (method, path) in PUBLIC_AUTH_ENDPOINTS:
        return None
    if path in {"/api/auth/logout", "/api/auth/change-password"}:
        return "view"
    if path == "/api/license/status":
        return "view"
    if path == "/api/license/activate":
        return "license_administer"
    if path.startswith("/api/users"):
        return "administer"
    if method == "POST" and path.startswith("/api/models/"):
        return "administer"
    if path in INTEGRITY_RECOVERY_ENDPOINTS:
        return "recovery"
    if method == "GET":
        if path == "/api/events":
            return "technical"
        if path in {"/api/recovery", "/api/recovery/destinations"}:
            return "recovery"
        if path == "/api/backups":
            return "backups"
        if path in {"/api/deleted-faces"}:
            return "destroy"
        if path in {"/api/photo-review", "/api/pending", "/api/queue-progress", "/api/queue-sessions", "/api/queue-groups", "/api/queue-person-candidates", "/api/queue-encounters"}:
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
        "/api/person-archive", "/api/person-restore", "/api/person-merge-preview", "/api/person-merge", "/api/person-merge-undo", "/api/person-purge",
        "/api/person-photo-move", "/api/observation-correct", "/api/encounter-correct", "/api/person-photo-delete",
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
        "/api/person-create", "/api/person-update", "/api/person-notes", "/api/person-preferences",
        "/api/person-association", "/api/person-association-placeholder",
        "/api/person-association-remove", "/api/encounter-attach-media",
        "/api/recognition-person-candidates",
        "/api/proof-only-duplicate-check",
        "/api/recognition-accept-existing", "/api/recognition-new",
        "/api/placeholder-enroll",
        "/api/recognition-followup", "/api/queue-add", "/api/queue-cancel",
        "/api/photo-review", "/api/photo-review-decision",
        "/api/photo-review-complete", "/api/photo-review-cancel",
        "/api/reference-prepare", "/api/reference-confirm", "/api/reference-lifecycle", "/api/reference-cancel",
        "/api/queue-scan", "/api/queue-confirm-new", "/api/queue-confirm-existing",
        "/api/queue-encounters-plan", "/api/queue-encounter-event",
        "/api/queue-encounter-decision", "/api/queue-encounter-identities-complete",
        "/api/queue-encounter-relation", "/api/queue-encounter-complete",
        "/api/queue-encounter-discard",
        "/api/queue-media-selection", "/api/queue-quality-policy",
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
        self._shutting_down = False

    @contextmanager
    def shared(self):
        with self._condition:
            if self._shutting_down:
                raise EngineBusyError("SentriFace is shutting down")
            while self._exclusive_active or self._exclusive_waiters:
                self._condition.wait()
                if self._shutting_down:
                    raise EngineBusyError("SentriFace is shutting down")
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
            if self._shutting_down:
                raise EngineBusyError("SentriFace is shutting down")
            self._exclusive_waiters += 1
            try:
                while self._exclusive_active or self._active_operations:
                    self._condition.wait()
                    if self._shutting_down:
                        raise EngineBusyError("SentriFace is shutting down")
                self._exclusive_active = True
            finally:
                self._exclusive_waiters -= 1
        try:
            yield
        finally:
            with self._condition:
                self._exclusive_active = False
                self._condition.notify_all()

    def begin_shutdown(self) -> None:
        with self._condition:
            self._shutting_down = True
            self._condition.notify_all()

    def wait_for_idle(self, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            while self._active_operations or self._exclusive_active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True


class SentriFaceApiServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        engine: FaceEngine,
        config: RuntimeConfig,
        hardware_profile: HardwareProfile,
        runtime: str,
        debug: bool = False,
        model_ready: bool = True,
        model_error: str = "",
        os_network_policy: OsNetworkPolicyStatus | None = None,
        model_bundles: ModelBundleAuthority | None = None,
        instance_lock: InstanceLock | None = None,
        license_authority: LicenseAuthority | None = None,
        linux_source_onnx: bool = False,
    ) -> None:
        super().__init__(server_address, SentriFaceApiHandler)
        self.engine = engine
        self.config = config
        self.key_protection = "operating-system-vault" if config.storage_key else "none"
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
        self.shutting_down = threading.Event()
        self._closed = False
        self.instance_lock = instance_lock
        self.license = license_authority or LicenseAuthority(
            enforced=packaged_windows_license_enforced(),
        )
        self.model_bundles = model_bundles or ModelBundleAuthority(
            config.detector_model.parent
        )
        self.model_activation = ModelActivationService(
            self.model_bundles,
            engine,
            build_onnx_recognition_runtime,
            token_secret=secrets.token_urlsafe(32),
        )
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
        recovered_restores = self.backups.recover_interrupted_restores()
        for recovery_result in recovered_restores:
            self.log_event("backup-restore-interrupted-recovered", **recovery_result)
        self.recovery = RecoveryService(config.data_dir, config.storage_key, self.backups, linux_source_onnx=linux_source_onnx)
        self.auth = AuthService(config.db_path, config.storage_key)
        self.integrity_recovery = IntegrityRecoveryApplication(
            engine, token_secret=secrets.token_urlsafe(32),
        )
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
                try:
                    stat = path.stat()
                except OSError as exc:
                    raise OSError(
                        f"Model setup file is missing or unreadable: {path.name}"
                    ) from exc
                if self.model_fingerprints.get(str(path.resolve())) != (stat.st_size, stat.st_mtime_ns):
                    raise OSError(f"Model setup file changed or was replaced: {path.name}")
        except OSError as exc:
            self.model_ready = False
            self.model_error = redact_log_text(str(exc))
            self.log_event("model-setup-required", error=self.model_error)
            return False
        return True

    def model_status(self, user: AuthUser | None) -> dict[str, Any]:
        ready = self.models_available()
        active = self.model_activation.active_state()
        can_configure = bool(user and user.has("administer"))
        candidates = []
        if can_configure and not ready:
            active_id = active.active_bundle_id if active else None
            candidates = [
                bundle.dto()
                for bundle in self.model_bundles.list_bundles(limit=1)
                if bundle.bundle_id != active_id
            ]
        return {
            "ready": ready,
            "runtime": self.runtime,
            "error": "" if ready else self.model_error or "Recognition models are required",
            "can_configure": can_configure,
            "combinations": MODEL_COMBINATIONS,
            "requirements": {
                "detector": "SCRFD-compatible ONNX detector",
                "recognizer": "ArcFace-compatible ONNX recognizer with 512-dimensional embeddings",
                "calibration": "Optional hash-bound threshold file; built-in thresholds are used when omitted",
                "checksums": "SHA-256 is required for every supplied file",
            },
            "usage": self.model_usage if ready else None,
            "active_bundle": active.dto() if active else None,
            "rollback_available": bool(active and active.previous_bundle_id),
            "candidate_bundles": candidates,
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
    def sync_model_runtime_state(self) -> None:
        self.config = self.engine.config
        declaration = getattr(self.engine, "model_usage", None)
        self.model_usage = declaration if isinstance(declaration, dict) else {}
        self.model_error = ""
        self.model_ready = True
        self._capture_model_fingerprints()
        self.log_event(
            "models-activated",
            usage_basis=self.model_usage.get("usage_basis", "unknown"),
        )
    def process_request(self, request: Any, client_address: Any) -> None:
        if self.network_policy_violation or self.shutting_down.is_set():
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
        logger.info(json.dumps(item, separators=(",", ":"), sort_keys=True))

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

    def finish_queue_job(self, job_id: str, **terminal_progress: Any) -> None:
        with self.queue_progress_lock:
            self.queue_cancellations.pop(job_id, None)
            self.queue_cancellation_created.pop(job_id, None)
            self.active_queue_jobs.discard(job_id)
            if terminal_progress:
                current = dict(self.queue_progress.get(job_id, {"job_id": job_id}))
                current.update(terminal_progress)
                self.queue_progress[job_id] = current
                self._prune_queue_progress_locked()

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
        *, person_id: str | None = None,
    ) -> dict:
        existing = self.engine.get_person_operation(operation_id, operation_type)
        if existing is not None:
            backup = self.backups.find_by_operation(operation_id)
            return {**existing, **({"backup": _backup(backup)} if backup else {})}
        if operation_type in {"archive-person", "purge-person"}:
            # API exclusive gate covers backup and mutation; store still rechecks.
            self.engine.store.validate_person_lifecycle_operation(person_id, operation_id, operation_type)
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
                with self.operation_gate.exclusive():
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
        if getattr(self, "_closed", False):
            return
        self._closed = True
        shutting_down = getattr(self, "shutting_down", None)
        operation_gate = getattr(self, "operation_gate", None)
        if shutting_down is not None:
            shutting_down.set()
        if operation_gate is not None:
            operation_gate.begin_shutdown()
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
        if operation_gate is not None:
            operation_gate.wait_for_idle(10)
        engine = getattr(self, "engine", None)
        try:
            if engine is not None:
                engine.close()
        finally:
            try:
                super().server_close()
            finally:
                instance_lock = getattr(self, "instance_lock", None)
                if instance_lock is not None:
                    instance_lock.release()

    def graceful_shutdown(self, *, drain_timeout: float = 10) -> bool:
        """Stop admission, cancel maintenance work, drain active operations, then stop HTTP."""
        if self.shutting_down.is_set():
            return self.operation_gate.wait_for_idle(drain_timeout)
        self.shutting_down.set()
        self.operation_gate.begin_shutdown()
        with self.queue_progress_lock:
            for cancellation in self.queue_cancellations.values():
                cancellation.set()
        self.maintenance_stop.set()
        self.network_policy_stop.set()
        drained = self.operation_gate.wait_for_idle(drain_timeout)
        self.shutdown()
        return drained


class SentriFaceApiHandler(SimpleHTTPRequestHandler):
    server: SentriFaceApiServer
    auth_user: AuthUser | None = None
    pending_auth_cookie: str | None = None

    def log_message(self, format: str, *args: object) -> None:
        """Never put session-bearing query strings into operational logs."""
        if self.server.debug:
            logger.debug("http_request method={} endpoint={}", self.command, urlparse(self.path).path)
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

    def _operation_actor(self) -> dict | None:
        if self.auth_user is None:
            return None
        return {
            "user_id": self.auth_user.user_id,
            "username": self.auth_user.username,
            "display_name": self.auth_user.display_name,
            "roles": list(self.auth_user.roles),
        }

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
            or path in LICENSE_ENDPOINTS
            or path in INTEGRITY_RECOVERY_ENDPOINTS
            or path == "/api/backup-db"
            or path.startswith("/api/backups")
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

    def _reject_license_policy(self, method: str, path: str) -> bool:
        if _license_exempt_endpoint(method, path):
            return False
        result = self.server.license.status()
        if not self.server.license.enforced or result.licensed:
            return False
        self._json(
            {
                "error": "Activate SentriFace Edge to use this product operation",
                "code": "license_required",
                "license_status": result.status.value,
            },
            status=HTTPStatus.PAYMENT_REQUIRED,
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
                or self._reject_license_policy("GET", parsed.path)
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
        if self._reject_license_policy("POST", parsed.path):
            return
        if self._reject_model_readiness(parsed.path):
            return
        if parsed.path == "/api/queue-cancel":
            self._do_POST()
            return
        exclusive_backup_paths = {
            "/api/backups",
            "/api/backup-db",
            "/api/backups/restore",
            "/api/person-archive",
            "/api/person-purge",
            "/api/person-photo-delete",
            "/api/person-photo-purge",
        }
        gate = (
            self.server.operation_gate.exclusive()
            if parsed.path in {
                *exclusive_backup_paths,
                "/api/models/install",
                "/api/models/activation/prepare",
                "/api/models/activation/execute",
                "/api/models/rollback/prepare",
                "/api/models/rollback/execute",
            }
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
        if self._reject_license_policy("DELETE", parsed.path):
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
            if parsed.path == "/api/license/status":
                self._json(self.server.license.status().as_dict(enforced=self.server.license.enforced))
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
            if parsed.path == "/api/integrity/revert-operations":
                self._json(self.server.integrity_recovery.list_revert_operations())
                return
            if parsed.path == "/api/photo-review":
                review = self.server.engine.store.get_photo_review(_query_value(parsed.query, "review_id"))
                if review is None:
                    raise KeyError("Unknown photo review")
                self._json(_photo_review(review))
                return
            if parsed.path == "/api/persons":
                self._json(_people_collection_payload(self.server.engine))
                return
            if parsed.path == "/api/encounters":
                query = parse_qs(parsed.query)
                allowed = {
                    "limit", "cursor", "search", "date_from", "date_to", "location",
                    "context", "participant_id", "mentioned_person_id", "person_id", "person_status",
                }
                if set(query) - allowed:
                    raise ValueError("Unknown Encounter filter")
                self._json(self.server.engine.query_encounters(**{
                    key: values[0] for key, values in query.items() if values
                }))
                return
            if parsed.path == "/api/encounter":
                self._json(self.server.engine.get_encounter_read(
                    _query_value(parsed.query, "observation_id")
                ))
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
                # The normal profile is the effective canonical identity. Raw is
                # an explicit history/archived inspection mode.
                view = parse_qs(parsed.query).get("view", ["effective"])[0]
                if view not in {"effective", "raw"}:
                    raise KeyError(f"Unknown person view: {view}")
                raw_view = include_archived or view == "raw"
                person = (
                    self.server.engine.get_person(person_id, include_archived=True)
                    if raw_view else self.server.engine.get_effective_person(person_id)
                )
                if person is None:
                    raise KeyError(f"Unknown person: {person_id}")
                embeddings = self.server.engine.list_person_embeddings(
                    person_id,
                    include_archived=include_archived,
                    raw=raw_view,
                )
                face_origins = self.server.engine.face_origins_for_embeddings(
                    [record.embedding_id for record in embeddings],
                    person_id=None if raw_view else person.person_id,
                )
                details = self.server.engine.list_recognition_details_for_person(
                    person_id,
                    include_archived=include_archived,
                    raw=raw_view,
                )
                changes = self.server.engine.list_person_changes(
                    person_id,
                    include_archived=include_archived,
                    raw=raw_view,
                )
                management_events = self.server.engine.list_person_operations(
                    person_id,
                    include_archived=include_archived,
                    raw=raw_view,
                )
                notes = self.server.engine.list_person_notes(person_id, raw=raw_view)
                profile_note = self.server.engine.get_person_note(person.person_id)
                observations = (
                    self.server.engine.list_raw_observations_for_person(person_id)
                    if raw_view else self.server.engine.list_observations_for_person(person_id)
                )
                associations = (
                    self.server.engine.list_person_associations(
                        person_id,
                        include_archived=True,
                    )
                    if raw_view
                    else self.server.engine.get_person_graph_neighbors(person.person_id)
                )
                intelligence = self.server.engine.get_person_intelligence(person_id)
                sightings = self.server.engine.list_person_sightings(person_id)
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
                            "notes": profile_note.content if profile_note is not None else "",
                            "favorite": bool(person.metadata.get("favorite")),
                            "tags": list(person.metadata.get("tags", [])),
                            "representative_image": _representative_image(
                                embeddings,
                                person.metadata.get("representative_embedding_id"),
                            ),
                        },
                        "requested_person_id": person_id,
                        "view": "raw" if raw_view else "effective",
                        "encounter_media": self.server.engine.list_person_encounter_media(person_id),
                        "recognition_references": self.server.engine.store.list_recognition_references(person_id),
                        "embeddings": [
                            {**_embedding(record), "face_origins": face_origins[record.embedding_id]}
                            for record in embeddings
                        ],
                        "details": [
                            _recognition_detail(
                                detail,
                                self.server.engine.resolve_canonical_person_id(
                                    detail.person_id,
                                ),
                            )
                            for detail in details
                        ],
                        "notes_records": [_note_record(note) for note in notes],
                        "profile_note": _profile_note_record(
                            profile_note, person_summaries, self.server.engine,
                        ),
                        "observations": [_observation_record(item) for item in observations],
                        "sightings": [_sighting_record(item) for item in sightings],
                        "intelligence": _person_intelligence(intelligence),
                        "relationships": _person_relationships(
                            intelligence, person_summaries, self.server.engine,
                        ),
                        "relationship_count": len({item.person_id for item in intelligence.relationships}),
                        "activity": list(intelligence.activity),
                        "changes": [_person_change(change) for change in changes],
                        "management_events": management_events,
                        "associations": [
                            (
                                _person_association(
                                    association, person_id, person_summaries, self.server.engine,
                                )
                                if raw_view
                                else _graph_connection_association(
                                    association, person.person_id, person_summaries, self.server.engine,
                                )
                            )
                            for association in associations
                        ],
                    }
                )
                return
            if parsed.path == "/api/person-intelligence":
                person_id = _query_value(parsed.query, "person_id")
                self._json({
                    "intelligence": _person_intelligence(
                        self.server.engine.get_person_intelligence(person_id)
                    )
                })
                return
            if parsed.path == "/api/person-relationship-graph":
                person_id = _query_value(parsed.query, "person_id")
                requested_limit = _safe_count(
                    _query_value(parsed.query, "limit") or "60", "graph limit",
                )
                self._json(_person_relationship_graph(
                    self.server.engine,
                    person_id,
                    limit=max(1, min(requested_limit, 100)),
                ))
                return
            if parsed.path == "/api/graph-revision":
                revision = self.server.engine.get_graph_revision()
                current_revision = parse_qs(parsed.query).get("current_revision", [None])[0]
                self._json({
                    "contract": "sentriface.graph-revision",
                    "contract_version": 1,
                    "graph_revision": revision,
                    "current_revision": current_revision,
                    "stale": current_revision is not None and current_revision != revision,
                })
                return
            if parsed.path == "/api/person-graph":
                person_id = _query_value(parsed.query, "person_id")
                self._json(_person_graph_read_payload(
                    self.server.engine.get_person_graph_read(
                        person_id, _graph_filters_from_query(parsed.query),
                    )
                ))
                return
            if parsed.path == "/api/world-graph":
                version = parse_qs(parsed.query).get("version", ["1"])[0]
                if version == "2":
                    self._json(_world_graph_v2_payload(
                        self.server.engine.get_world_graph_v2_read(
                            _world_graph_v2_request_from_query(parsed.query),
                        )
                    ))
                    return
                if version != "1":
                    raise ValueError("Unsupported World Graph API version")
                self._json(_world_graph_read_payload(
                    self.server.engine.get_world_graph_read(
                        _graph_filters_from_query(parsed.query),
                    )
                ))
                return
            if parsed.path == "/api/person-sightings":
                person_id = _query_value(parsed.query, "person_id")
                self._json({
                    "sightings": [
                        _sighting_record(item)
                        for item in self.server.engine.list_person_sightings(person_id)
                    ]
                })
                return
            if parsed.path == "/api/person-association-neighbors":
                person_id = _query_value(parsed.query, "person_id")
                include_archived = _query_bool(parsed.query, "include_archived")
                requested_limit = _safe_count(_query_value(parsed.query, "limit") or "30", "graph limit")
                limit = max(1, min(requested_limit, 50))
                person = self.server.engine.get_effective_person(person_id)
                if person is None:
                    raise KeyError("This person no longer exists")
                associations = self.server.engine.get_person_graph_neighbors(person.person_id)
                person_summaries = {
                    item.person.person_id: item
                    for item in [
                        *self.server.engine.list_persons(),
                        *self.server.engine.list_persons(archived=True),
                    ]
                }
                self._json({
                    "person": {
                        **_person(person),
                        "favorite": bool(person.metadata.get("favorite")),
                        "tags": list(person.metadata.get("tags", [])),
                        "representative_image": _representative_image(
                            self.server.engine.list_person_embeddings(
                                person_id, include_archived=include_archived,
                            ),
                            person.metadata.get("representative_embedding_id"),
                        ),
                    },
                    "associations": [
                        _graph_connection_association(
                            item, person.person_id, person_summaries, self.server.engine,
                        )
                        for item in associations[:limit]
                    ],
                    "truncated": len(associations) > limit,
                    "limit": limit,
                })
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
                    media = self.server.engine.list_init_session_media(session.session_id)
                    reviews = self.server.engine.list_init_session_encounter_reviews(session.session_id)
                    if groups or media or reviews or session.target_observation_id:
                        sessions.append(_init_session_summary(session, groups))
                self._json({"sessions": sessions})
                return
            if parsed.path == "/api/queue-encounters":
                session_id = _query_value(parsed.query, "session_id")
                session = self.server.engine.store.get_init_session(session_id)
                self._json({
                    "media": self.server.engine.list_init_session_media(session_id),
                    "reviews": self.server.engine.list_init_session_encounter_reviews(session_id),
                    "attachment": {"observation_id": session.target_observation_id,
                                   "expected_revision": session.expected_encounter_revision,
                                   "processing_failed": session.status == "processing_failed",
                                   "source_path": session.source_path}
                                  if session and session.target_observation_id else None,
                })
                return
            if parsed.path == "/api/queue-groups":
                session_id = _query_value(parsed.query, "session_id")
                groups = self.server.engine.refresh_init_groups(session_id)
                reviews = self.server.engine.list_init_session_encounter_reviews(session_id)
                active_review = next((item for item in reviews if item["status"] == "IN_PROGRESS" and item["phase"] != "WAITING"), None)
                if active_review is not None:
                    active_ids = {face["face_id"] for face in active_review["faces"] if face["decision"] in (None, "SKIP")}
                    groups = [InitGroup(
                        group_id=group.group_id, session_id=group.session_id, status=group.status,
                        faces=[face for face in group.faces if face.init_face_id in active_ids],
                    ) for group in groups]
                    groups = [group for group in groups if group.faces]
                session = self.server.engine.store.get_init_session(session_id)
                self._json({"quality_only": session.quality_only if session else True, "groups": [
                    _init_group(self.server.engine, group, encounter_review_id=active_review["review_id"] if active_review else None)
                    for group in groups
                ]})
                return
            if parsed.path == "/api/queue-person-candidates":
                session_id = _query_value(parsed.query, "session_id")
                group_id = _query_value(parsed.query, "group_id")
                group = self.server.engine.get_init_group(session_id, group_id)
                reviews = self.server.engine.list_init_session_encounter_reviews(session_id)
                active_review = next((item for item in reviews if item["status"] == "IN_PROGRESS" and item["phase"] != "WAITING"), None)
                if active_review is not None:
                    active_ids = {face["face_id"] for face in active_review["faces"] if face["decision"] in (None, "SKIP")}
                    group = InitGroup(
                        group_id=group.group_id, session_id=group.session_id, status=group.status,
                        faces=[face for face in group.faces if face.init_face_id in active_ids],
                    )
                    if not group.faces:
                        raise KeyError("This identity group does not belong to the active Encounter")
                candidates = self.server.engine.ranked_people_for_init_group(group)
                if active_review:
                    combined = self.server.engine.encounter_matches_for_init_group(group, active_review["review_id"], limit=False)
                    by_id = {item["person_id"]: item for item in combined}
                    people = [{**_person_summary_from_embeddings(candidate.summary, candidate.embeddings),
                               "match": {**_match_policy(self.server.engine, by_id[candidate.summary.person.person_id]["score"]), "score": by_id[candidate.summary.person.person_id]["score"]} if candidate.summary.person.person_id in by_id else None}
                              for candidate in candidates]
                    for item in combined:
                        if item["draft_created"]:
                            people.append({**item, "biometric_status": "ENROLLED", "embedding_count": 1,
                                           "match": {**_match_policy(self.server.engine, item["score"]), "score": item["score"]}})
                        else:
                            existing = next((person for person in people if person["person_id"] == item["person_id"]), None)
                            if existing is not None:
                                existing["representative_image"] = item["representative_image"]
                    people.sort(key=lambda item: (-(item["match"]["score"] if item["match"] else -1), item["person_id"]))
                    for rank, item in enumerate(people, 1):
                        if item["match"]:
                            item["match"]["rank"] = rank
                    self._json({"candidates": people})
                    return
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
                _validate_model_upload_query(parsed.query)
                kind = _query_value(parsed.query, "kind").strip().casefold()
                if kind not in {"detector", "recognizer", "calibration"}:
                    raise InputValidationError(
                        "Model upload kind must be detector, recognizer, or calibration",
                        "invalid_model_kind",
                    )
                target = self.server.model_bundles.begin_upload(
                    kind, _query_value(parsed.query, "filename")
                )
                try:
                    digest, size = self._stream_model_upload(
                        target.path, maximum_bytes=_limit_for_kind(kind)
                    )
                    reference = self.server.model_bundles.complete_upload(
                        target, sha256=digest, size=size
                    )
                except Exception:
                    self.server.model_bundles.abort_upload(target)
                    raise
                self.server.log_event(
                    "model-file-selected",
                    actor=self.auth_user.username,
                    kind=kind,
                    filename=reference.filename,
                    size=size,
                    sha256=digest,
                )
                self._json(reference.dto(), status=HTTPStatus.CREATED)
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
            if parsed.path == "/api/license/activate":
                if set(payload) != {"token"}:
                    raise InputValidationError(
                        "License activation accepts only the signed token",
                        "invalid_license_activation_payload",
                    )
                token = payload.get("token")
                if not isinstance(token, str):
                    raise InputValidationError("License token must be text", "invalid_license_token")
                result = self.server.license.activate(token)
                response = result.as_dict(enforced=self.server.license.enforced)
                if result.licensed:
                    self.server.log_event(
                        "license-activated",
                        username=self.auth_user.username if self.auth_user else "unknown",
                        license_id=result.license_id,
                        edition=result.edition,
                    )
                    self._json(response)
                else:
                    self.server.log_event(
                        "license-activation-refused",
                        username=self.auth_user.username if self.auth_user else "unknown",
                        code=result.code,
                    )
                    self._json({**response, "error": result.message}, status=HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            if parsed.path in MODEL_OPERATION_REQUEST_FIELDS:
                _validate_model_operation_payload(parsed.path, payload)
            if parsed.path in INTEGRITY_RECOVERY_REQUEST_FIELDS:
                _validate_integrity_recovery_payload(parsed.path, payload)
            if parsed.path == "/api/integrity/check":
                self._json(self.server.integrity_recovery.check())
                return
            if parsed.path == "/api/integrity/graph-rebuild/prepare":
                self._json(self.server.integrity_recovery.prepare_graph_rebuild(
                    _required(payload, "report_token"),
                    _required(payload, "action_id"),
                ))
                return
            if parsed.path == "/api/integrity/graph-rebuild/execute":
                try:
                    result = self.server.integrity_recovery.execute_graph_rebuild(
                        _required(payload, "token"),
                        _operation_id(payload),
                        actor=self._operation_actor(),
                        reason=_integrity_reason(payload),
                        source=parsed.path,
                    )
                except GraphProjectionPostcheckError as exc:
                    self._json(
                        self.server.integrity_recovery.postcheck_failure_payload(
                            "GRAPH_REBUILD", exc.result, exc.report,
                        ),
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._json(result)
                return
            if parsed.path == "/api/integrity/repairs/r01/prepare":
                self._json(self.server.integrity_recovery.prepare_r01(
                    _required(payload, "report_token"),
                    _required(payload, "action_id"),
                ))
                return
            if parsed.path == "/api/integrity/repairs/r01/execute":
                try:
                    result = self.server.integrity_recovery.execute_r01(
                        _required(payload, "token"),
                        _operation_id(payload),
                        actor=self._operation_actor(),
                        reason=_integrity_reason(payload),
                        source=parsed.path,
                    )
                except StructuredRepairPostcheckError as exc:
                    self._json(
                        self.server.integrity_recovery.postcheck_failure_payload(
                            "R01", exc.result, exc.report,
                        ),
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._json(result)
                return
            if parsed.path == "/api/integrity/repairs/r02/prepare":
                self._json(self.server.integrity_recovery.prepare_r02(
                    _required(payload, "report_token"),
                    _required(payload, "action_id"),
                ))
                return
            if parsed.path == "/api/integrity/repairs/r02/execute":
                try:
                    result = self.server.integrity_recovery.execute_r02(
                        _required(payload, "token"),
                        _operation_id(payload),
                        actor=self._operation_actor(),
                        reason=_integrity_reason(payload),
                        source=parsed.path,
                    )
                except StructuredRepairPostcheckError as exc:
                    self._json(
                        self.server.integrity_recovery.postcheck_failure_payload(
                            "R02", exc.result, exc.report,
                        ),
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._json(result)
                return
            if parsed.path == "/api/integrity/reverts/prepare":
                self._json(self.server.integrity_recovery.prepare_revert(
                    _required(payload, "operation_id"),
                ))
                return
            if parsed.path == "/api/integrity/reverts/execute":
                try:
                    result = self.server.integrity_recovery.execute_revert(
                        _required(payload, "token"),
                        _operation_id(payload),
                        actor=self._operation_actor(),
                        reason=_integrity_reason(payload),
                        source=parsed.path,
                    )
                except OperationRevertPostcheckError as exc:
                    self._json(
                        self.server.integrity_recovery.postcheck_failure_payload(
                            "REVERT", exc.result, exc.report,
                        ),
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._json(result)
                return
            if parsed.path == "/api/backups/restore":
                _validate_backup_restore_payload(payload)
                result = self.server.backups.restore_backup(
                    _required(payload, "backup_id"),
                    _required(payload, "operation_id"),
                    actor=self._operation_actor(),
                    reason=payload.get("reason"),
                    reload_callback=self.server.engine.reload_after_restore,
                )
                self._json({"restore": result})
                return
            if parsed.path == "/api/photo-review":
                if payload.get("source") == "reference-only":
                    raise ValueError("Reference Only requires the single-face admission endpoint")
                faces = payload.get("faces")
                if not isinstance(faces, list):
                    raise KeyError("faces must be a list")
                review = self.server.engine.create_photo_review(
                    _required(payload, "review_id"),
                    _required(payload, "media_id"),
                    faces,
                    media_path=payload.get("media_path"),
                    source=str(payload.get("source") or "check-photo"),
                )
                self._json(_photo_review(review), status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/photo-review-decision":
                review = self.server.engine.set_photo_review_face_decision(
                    _required(payload, "review_id"),
                    _required(payload, "face_id"),
                    _required(payload, "decision"),
                    person_id=payload.get("person_id"),
                    new_person_key=payload.get("new_person_key"),
                    new_person_name=payload.get("new_person_name"),
                    new_person_metadata=payload.get("new_person_metadata"),
                    notes=str(payload.get("notes") or ""),
                    mentioned_person_ids=list(payload.get("mentioned_person_ids") or []),
                    recognition_detail=payload.get("recognition_detail"),
                )
                self._json(_photo_review(review))
                return
            if parsed.path == "/api/photo-review-complete":
                target_person_id = str(payload.get("target_person_id") or "").strip()
                if target_person_id:
                    result = self.server.engine.add_face_to_person(
                        _required(payload, "review_id"),
                        target_person_id,
                        _operation_id(payload),
                        actor=self._operation_actor(),
                        source=str(payload.get("source") or "add-face-review"),
                        no_context_acknowledged=payload.get("no_context_acknowledged") is True,
                    )
                else:
                    result = self.server.engine.complete_photo_review(
                        _required(payload, "review_id"),
                        _operation_id(payload),
                        actor=self._operation_actor(),
                        source=str(payload.get("source") or "review-finalisation"),
                    )
                self.server.log_event("photo-review-completed", **result)
                self._json(result)
                return
            if parsed.path == "/api/photo-review-cancel":
                review = self.server.engine.cancel_photo_review(_required(payload, "review_id"))
                self._json(_photo_review(review))
                return
            if parsed.path == "/api/reference-prepare":
                self._json(self.server.engine.prepare_reference_review(
                    require_local_path(Path(_required(payload, "path"))), _required(payload, "person_id")))
                return
            if parsed.path == "/api/reference-confirm":
                self._json(self.server.engine.confirm_reference(_required(payload, "review_id"),
                    _required(payload, "person_id"), _operation_id(payload),
                    no_context_acknowledged=payload.get("no_context_acknowledged") is True,
                    recognition_state=_required(payload, "recognition_state"), actor=self._operation_actor()))
                return
            if parsed.path == "/api/reference-lifecycle":
                if not isinstance(payload.get("active"), bool):
                    raise ValueError("Reference active must be a boolean")
                self._json(self.server.engine.set_reference_active(_required(payload, "reference_id"),
                    _required(payload, "person_id"), payload["active"], _operation_id(payload), actor=self._operation_actor()))
                return
            if parsed.path == "/api/reference-cancel":
                self.server.engine.cancel_reference_review(_required(payload, "review_id"))
                self._json({"cancelled": True})
                return
            if parsed.path in {
                "/api/recognition-accept-existing", "/api/recognition-new",
                "/api/placeholder-enroll", "/api/recognition-followup",
                "/api/confirm-new", "/api/confirm-existing",
                "/api/enroll",
            }:
                raise DomainWorkflowUnavailableError(
                    "Per-face confirmation is unavailable; complete the whole review atomically"
                )
            if parsed.path == "/api/person-photo-move":
                result = self.server.engine.move_embedding(
                    _required(payload, "embedding_id"),
                    _required(payload, "target_person_id"),
                    _operation_id(payload),
                    actor=self._operation_actor(),
                    source=parsed.path,
                )
                self.server.log_event("person-photo-move", **result)
                self._json(result)
                return
            if parsed.path == "/api/observation-correct":
                result = self.server.engine.correct_observation_identity(
                    _required(payload, "observation_id"),
                    _required(payload, "from_person_id"),
                    _required(payload, "to_person_id"),
                    _operation_id(payload),
                    actor=self._operation_actor(),
                    source=parsed.path,
                )
                self.server.log_event("observation-identity-corrected", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-merge-preview":
                result = self.server.engine.preview_merge_persons(
                    _required(payload, "source_person_id"),
                    _required(payload, "target_person_id"),
                )
                self._json(result)
                return
            if parsed.path == "/api/person-merge":
                resolutions = payload.get("conflict_resolutions")
                if resolutions is not None and not isinstance(resolutions, (list, dict)):
                    raise KeyError("conflict_resolutions must be a list or object")
                result = self.server.engine.merge_persons(
                    _required(payload, "source_person_id"),
                    _required(payload, "target_person_id"),
                    _operation_id(payload),
                    conflict_resolutions=resolutions,
                    actor=self._operation_actor(),
                    source=parsed.path,
                    reason=str(payload.get("reason") or "").strip() or None,
                    context=(
                        payload.get("context")
                        if isinstance(payload.get("context"), dict) else None
                    ),
                )
                self.server.log_event("person-merged", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-merge-undo":
                raise DomainWorkflowUnavailableError(
                    "Identity Merge undo is not exposed in P8-B"
                )
            if parsed.path == "/api/encounter-correct":
                allowed = {"observation_id", "operation_id", "expected_revision", "event_details", "participant_correction", "relations"}
                if set(payload) - allowed:
                    raise ValueError("Unknown Encounter correction field")
                result = self.server.engine.correct_encounter(
                    _required(payload, "observation_id"), _operation_id(payload),
                    expected_revision=_required(payload, "expected_revision"),
                    event_details=payload.get("event_details"), participant_correction=payload.get("participant_correction"),
                    relations=payload.get("relations"), actor=self._operation_actor(), source=parsed.path,
                )
                self._json(result)
                return
            if parsed.path == "/api/encounter-attach-media":
                if set(payload) - {"observation_id", "session_id", "expected_revision", "media_ids"}:
                    raise ValueError("Unknown attachment draft field")
                media_ids = payload.get("media_ids")
                if not isinstance(media_ids, list) or not media_ids or any(not isinstance(item, str) for item in media_ids):
                    raise ValueError("Select scanned media to attach")
                self._json({"reviews": self.server.engine.plan_init_session_encounters(
                    _required(payload, "session_id"), [media_ids],
                    target_observation_id=_required(payload, "observation_id"), expected_revision=_required(payload, "expected_revision"),
                )})
                return
            if parsed.path == "/api/person-association":
                if set(payload) - {"first_person_id", "second_person_id", "operation_id"}:
                    raise ValueError("Unknown Manual Association field")
                self._json(self.server.engine.create_manual_association(
                    _required(payload, "first_person_id"), _required(payload, "second_person_id"), _operation_id(payload),
                    actor=self._operation_actor(), source=parsed.path,
                ))
                return
            if parsed.path == "/api/person-association-remove":
                if set(payload) - {"evidence_id", "operation_id"}:
                    raise ValueError("Unknown Manual Association retirement field")
                self._json(self.server.engine.retire_manual_association(
                    _required(payload, "evidence_id"), _operation_id(payload), actor=self._operation_actor(), source=parsed.path,
                ))
                return
            if parsed.path == "/api/person-association-placeholder":
                raise DomainWorkflowUnavailableError("Create a Person first, then add a Manual Association")
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
                _validate_model_install_payload(payload)
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
                bundle = self.server.model_bundles.create_bundle(
                    detector_upload_id=_required(payload, "detector_upload_id"),
                    recognizer_upload_id=_required(payload, "recognizer_upload_id"),
                    calibration_upload_id=str(payload.get("calibration_upload_id") or "").strip() or None,
                    calibration_profile=choice_id,
                    usage_basis=choice["usage_basis"],
                    authorized_by=self.auth_user.display_name or self.auth_user.username,
                    organization=str(payload.get("organization") or ""),
                    licensor=str(payload.get("licensor") or ""),
                    license_reference=str(payload.get("license_reference") or ""),
                    license_name=str(payload.get("license_name") or ""),
                )
                preparation = self.server.model_activation.prepare_model_activation(
                    bundle.bundle_id
                )
                self.server.log_event(
                    "model-bundle-prepared",
                    actor=self.auth_user.username,
                    bundle_id=bundle.bundle_id,
                    combination_id=choice_id,
                    usage_basis=choice["usage_basis"],
                )
                self._json(
                    {
                        **self.server.model_status(self.auth_user),
                        "bundle": bundle.dto(),
                        "preparation": preparation,
                    },
                    status=HTTPStatus.CREATED,
                )
                return
            if parsed.path == "/api/models/activation/prepare":
                preparation = self.server.model_activation.prepare_model_activation(
                    _required(payload, "bundle_id")
                )
                self._json({"preparation": preparation})
                return
            if parsed.path == "/api/models/rollback/prepare":
                self._json({"preparation": self.server.model_activation.prepare_rollback()})
                return
            if parsed.path in {
                "/api/models/activation/execute",
                "/api/models/rollback/execute",
            }:
                result = self.server.model_activation.execute(
                    _required(payload, "token"),
                    _required(payload, "operation_id"),
                    actor=self._operation_actor(),
                    reason=str(payload.get("reason") or ""),
                )
                if result.get("committed"):
                    self.server.sync_model_runtime_state()
                self.server.log_event(
                    "model-runtime-operation",
                    actor=self.auth_user.username,
                    operation_id=result["operation_id"],
                    action=result["action"],
                    status=result["status"],
                    bundle_id=result["bundle_id"],
                )
                self._json({**self.server.model_status(self.auth_user), "result": result})
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
                quality_only = _recognition_quality_only(payload)
                self.server.engine.reset_metrics()
                review, pending_faces = self.server.engine.prepare_photo_review(
                    image_path, quality_only=quality_only,
                )
                self.server.log_event("recognize", path=str(image_path), faces=len(pending_faces))
                self._json(
                    {
                        "review_id": review.review_id if review else None,
                        "faces": [
                            {
                                **_pending_recognition(self.server.engine, pending, index),
                                "staged_face_id": pending.pending_id,
                            }
                            for index, pending in enumerate(pending_faces, 1)
                        ],
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/recognize-batch":
                source = require_local_path(Path(_required(payload, "path")))
                quality_only = _recognition_quality_only(payload)
                images = _image_paths(source)
                if not images:
                    raise KeyError(f"No supported images found: {source}")
                self.server.engine.reset_metrics()
                batch = [
                    {
                        "image": str(image_path),
                        "faces": [
                            _recognition(self.server.engine, result, index)
                            for index, result in enumerate(
                                self.server.engine.recognize(image_path, quality_only=quality_only), 1
                            )
                        ],
                    }
                    for image_path in images
                ]
                self.server.log_event("recognize-batch", path=str(source), images=len(images))
                self._json({"batch": batch, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/recognition-person-candidates":
                image_path = require_local_path(Path(_required(payload, "path")))
                quality_only = _recognition_quality_only(payload)
                candidates = self.server.engine.ranked_people_for_recognition_face(
                    image_path,
                    int(_required(payload, "face_index")),
                    expected_box=_face_box(payload),
                    quality_only=quality_only,
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
            if parsed.path == "/api/proof-only-duplicate-check":
                if payload.get("review_id") and not payload.get("session_id"):
                    candidates = self.server.engine.proof_only_duplicate_candidates_for_review_face(
                        _required(payload, "review_id"), _required(payload, "face_id"),
                    )
                else:
                    candidates = self.server.engine.proof_only_duplicate_candidates_for_init_faces(
                        _required(payload, "session_id"), _required(payload, "group_id"),
                        payload.get("face_ids") if payload.get("review_id") else _queue_face_ids(self.server.engine, payload),
                        review_id=payload.get("review_id"),
                    )
                self._json({"candidates": candidates, "basis": "PROOF_ONLY_DUPLICATE_CHECK"})
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
                    actor=self._operation_actor(),
                    source=parsed.path,
                )
                self.server.log_event(
                    "person-update",
                    person_id=change.person_id,
                    editor_name=change.editor_name,
                )
                self._json({"updated": True, "change": _person_change(change)})
                return
            if parsed.path == "/api/person-notes":
                mentioned_person_ids = payload.get("mentioned_person_ids", [])
                if not isinstance(mentioned_person_ids, list):
                    raise KeyError("mentioned_person_ids must be a list")
                changed, person, change = self.server.engine.update_person_notes(
                    person_id=_required(payload, "person_id"),
                    notes=str(payload.get("notes") or ""),
                    expected_previous_notes=str(payload.get("expected_previous_notes") or ""),
                    editor_name=self.auth_user.display_name or self.auth_user.username,
                    operation_id=_operation_id(payload),
                    mentioned_person_ids=[str(item) for item in mentioned_person_ids],
                    actor=self._operation_actor(),
                    source=parsed.path,
                )
                associations = self.server.engine.get_person_graph_neighbors(person.person_id)
                person_summaries = {item.person.person_id: item for item in self.server.engine.list_persons()}
                self.server.log_event("person-notes-update", person_id=person.person_id, changed=changed)
                self._json({
                    "updated": changed,
                    "notes": person.notes,
                    "change": _person_change(change) if change else None,
                    "associations": [
                        _graph_connection_association(
                            item, person.person_id, person_summaries, self.server.engine,
                        )
                        for item in associations
                    ],
                })
                return
            if parsed.path == "/api/person-create":
                tags = payload.get("tags", [])
                if not isinstance(tags, list):
                    raise KeyError("tags must be a list")
                person = self.server.engine.create_identified_person(
                    name=_required(payload, "name"),
                    metadata={
                        "rank": _required(payload, "rank").strip(),
                        "country": _required(payload, "country").strip(),
                        "importance": _required(payload, "importance").strip(),
                        "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
                        "added_by": _required(payload, "added_by"),
                        "initial_observation": {
                            "seen_date": _required(payload, "seen_date"),
                            "seen_time": _required(payload, "seen_time"),
                            "place_seen": _required(payload, "place_seen"),
                            "individual_count": _safe_count(payload.get("individual_count"), "individual_count", allow_zero=True),
                            "event_occasion": _required(payload, "event_occasion"),
                        },
                    },
                    operation_id=_operation_id(payload),
                    actor=self._operation_actor(),
                    source=parsed.path,
                )
                summary = next(
                    item for item in self.server.engine.list_persons()
                    if item.person.person_id == person.person_id
                )
                result = _person_summary(summary, self.server.engine)
                self.server.log_event("person-created", person_id=person.person_id)
                self._json({"person": result})
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
                    actor=self._operation_actor(),
                    source=parsed.path,
                )
                self.server.log_event("person-preferences", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-archive":
                person_id = _required(payload, "person_id")
                operation_id = _operation_id(payload)
                actor = self._operation_actor()
                person = self.server.engine.get_person(person_id, include_archived=True)
                if person is None:
                    raise KeyError(f"Unknown person: {person_id}")
                if person.deleted_at:
                    result = self.server.engine.archive_person(
                        person_id, operation_id, actor, parsed.path,
                    )
                else:
                    result = self.server.backed_up_people_deletion(
                        operation_id,
                        "archive-person",
                        f"before-person-archive-{person.name}-{person_id[:8]}",
                        lambda: self.server.engine.archive_person(
                            person_id, operation_id, actor, parsed.path,
                        ),
                        person_id=person_id,
                    )
                self.server.log_event("person-archive", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-restore":
                result = self.server.engine.restore_person(
                    _required(payload, "person_id"),
                    _operation_id(payload),
                    self._operation_actor(),
                    parsed.path,
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
                        self._operation_actor(),
                        parsed.path,
                    ),
                    person_id=person_id,
                )
                self.server.log_event("person-purge", **result)
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
                    lambda: self.server.engine.delete_embedding(
                        embedding_id, operation_id,
                        actor=self._operation_actor(), source=parsed.path,
                    ),
                )
                self.server.log_event("person-photo-delete", **result)
                self._json(result)
                return
            if parsed.path == "/api/person-photo-restore":
                result = self.server.engine.restore_deleted_embedding(
                    _required(payload, "embedding_id"),
                    _operation_id(payload),
                    actor=self._operation_actor(),
                    source=parsed.path,
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
                        actor=self._operation_actor(),
                        source=parsed.path,
                    ),
                )
                self.server.log_event("person-photo-purge", **result)
                self._json(result)
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
                quality_only = _recognition_quality_only(payload)
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
                job_finished = False
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
                            quality_only=quality_only,
                            target_observation_id=payload.get("target_observation_id"),
                            expected_revision=payload.get("expected_revision"),
                            session_id=payload.get("session_id"),
                        )
                    except QueueCancellationError as exc:
                        self.server.finish_queue_job(
                            job_id,
                            phase="cancelled",
                            status="cancelled",
                            session_id="",
                            cancellation_phase=exc.phase,
                            finished_at=time.time(),
                        )
                        job_finished = True
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
                    if not queue_result.media_paths:
                        self.server.engine.discard_init_session(session_id)
                        session_id = ""
                    self.server.finish_queue_job(
                        job_id, phase="done", status="done", session_id=session_id,
                        groups=len(queue_result.groups), finished_at=time.time(),
                    )
                    job_finished = True
                    self._json(
                        {
                            "session_id": session_id,
                            "job_id": job_id,
                            "rejected_files": len(queue_result.invalid_images),
                            "groups": [
                                _init_group(self.server.engine, group, queue_result.matches_by_face_id)
                                for group in queue_result.groups
                            ],
                            "media": self.server.engine.store.list_init_session_media(session_id) if session_id else [],
                            "metrics": self.server.engine.metrics_snapshot(),
                        }
                    )
                    return
                except Exception:
                    if not job_finished:
                        self.server.finish_queue_job(
                            job_id, phase="failed", status="failed", finished_at=time.time(),
                        )
                        job_finished = True
                    raise
                finally:
                    if not job_finished:
                        self.server.finish_queue_job(job_id)
            if parsed.path == "/api/queue-media-selection":
                if not isinstance(payload.get("excluded"), bool):
                    raise ValueError("excluded must be a boolean")
                self.server.engine.set_init_media_excluded(_required(payload, "session_id"), _required(payload, "media_id"), payload["excluded"])
                self._json({"media": self.server.engine.list_init_session_media(payload["session_id"])})
                return
            if parsed.path == "/api/queue-quality-policy":
                if not isinstance(payload.get("quality_only"), bool):
                    raise ValueError("quality_only must be a boolean")
                self.server.engine.set_init_session_quality_policy(_required(payload, "session_id"), payload["quality_only"])
                self._json({"quality_only": payload["quality_only"]})
                return
            if parsed.path == "/api/queue-encounters-plan":
                groups = payload.get("media_groups")
                if not isinstance(groups, list) or any(not isinstance(group, list) for group in groups):
                    raise ValueError("media_groups must be a list of media ID lists")
                self._json({"reviews": self.server.engine.plan_init_session_encounters(
                    _required(payload, "session_id"), groups,
                )})
                return
            if parsed.path == "/api/queue-encounter-event":
                self._json({"review": self.server.engine.save_encounter_review_event(
                    _required(payload, "review_id"), payload.get("event_details"),
                )})
                return
            if parsed.path == "/api/queue-encounter-decision":
                review_id = _required(payload, "review_id")
                face_ids = payload.get("face_ids")
                if not isinstance(face_ids, list) or not face_ids:
                    raise ValueError("Select at least one face")
                choices = payload.get("quality_choices") or {}
                if not isinstance(choices, dict):
                    raise ValueError("quality_choices must be an object")
                decisions = []
                for face_id in face_ids:
                    detail = dict(payload.get("recognition_detail") or {})
                    if str(face_id) in choices:
                        detail["embedding_state"] = choices[str(face_id)]
                    decisions.append({"face_id": str(face_id), "recognition_detail": detail})
                self.server.engine.set_photo_review_face_decisions(
                        review_id, decisions, decision=_required(payload, "decision"),
                        person_id=payload.get("person_id"),
                        new_person_key=payload.get("new_person_key"),
                        new_person_name=payload.get("new_person_name"),
                        new_person_metadata=payload.get("new_person_metadata"),
                        notes=str(payload.get("notes") or ""),
                        mentioned_person_ids=list(payload.get("mentioned_person_ids") or []),
                    )
                self.server.engine.resume_deferred_encounter_groups(review_id)
                self._json({"review": self.server.engine.get_encounter_review(review_id)})
                return
            if parsed.path == "/api/queue-encounter-identities-complete":
                self._json({"review": self.server.engine.complete_encounter_identity_review(
                    _required(payload, "review_id"),
                )})
                return
            if parsed.path == "/api/queue-encounter-relation":
                self._json({"review": self.server.engine.set_encounter_relation_decision(
                    _required(payload, "review_id"), _required(payload, "first_ref"),
                    _required(payload, "second_ref"), _required(payload, "disposition"),
                )})
                return
            if parsed.path == "/api/queue-encounter-complete":
                review_id = _required(payload, "review_id")
                result = self.server.engine.complete_encounter_review(
                    review_id, _operation_id(payload), actor=self._operation_actor(),
                    source="queue-encounter-review",
                )
                self.server.log_event("queue-encounter-completed", **result)
                self._json({"result": result, "review": self.server.engine.get_encounter_review(review_id)})
                return
            if parsed.path == "/api/queue-encounter-discard":
                review_id = _required(payload, "review_id")
                self.server.engine.cancel_photo_review(review_id)
                self._json({"review": self.server.engine.get_encounter_review(review_id)})
                return
            if parsed.path == "/api/queue-confirm-new":
                session_id = _required(payload, "session_id")
                if self.server.engine.list_init_session_encounter_reviews(session_id):
                    raise ValueError("This Queue session uses Encounter review; complete the Encounter draft")
                mentioned_person_ids = payload.get("mentioned_person_ids", [])
                if not isinstance(mentioned_person_ids, list):
                    raise KeyError("mentioned_person_ids must be a list")
                person_id, accepted = self.server.engine.confirm_init_faces(
                    session_id,
                    _required(payload, "group_id"),
                    _queue_face_ids(self.server.engine, payload),
                    _required(payload, "name"),
                    _operation_id(payload),
                    notes=str(payload.get("notes") or ""),
                    mentioned_person_ids=[str(item) for item in mentioned_person_ids],
                    recognition_detail=_review_detail_payload(payload),
                    quality_choices=_queue_quality_choices(payload),
                    actor=self._operation_actor(),
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
                if self.server.engine.list_init_session_encounter_reviews(session_id):
                    raise ValueError("This Queue session uses Encounter review; complete the Encounter draft")
                person_id = _required(payload, "person_id")
                accepted = self.server.engine.confirm_init_faces_existing(
                    session_id,
                    _required(payload, "group_id"),
                    _queue_face_ids(self.server.engine, payload),
                    person_id,
                    _operation_id(payload),
                    notes=str(payload.get("notes") or ""),
                    mentioned_person_ids=[str(item) for item in payload.get("mentioned_person_ids", [])],
                    recognition_detail=_review_detail_payload(payload),
                    quality_choices=_queue_quality_choices(payload),
                    actor=self._operation_actor(),
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
                if self.server.engine.list_init_session_encounter_reviews(session_id):
                    raise ValueError("Use the Encounter draft decision to exclude faces")
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
                reviews = self.server.engine.list_init_session_encounter_reviews(session_id)
                if reviews:
                    active = next((item for item in reviews if item["status"] == "IN_PROGRESS" and item["phase"] == "IDENTITIES"), None)
                    if active is None:
                        raise ValueError("Only an active Encounter identity group can be deferred")
                    resumed = self.server.engine.skip_encounter_identity_group(active["review_id"], group_id)
                    self.server.log_event("queue-skip", session_id=session_id, group_id=group_id)
                    self._json({"skipped": True, "resumed": resumed, "review": self.server.engine.get_encounter_review(active["review_id"])})
                    return
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
                "detector": config.detector_model.name,
                "recognizer": config.recognizer_model.name,
            },
            "offline_enforcement": {
                "loopback_only": True,
                "source_runtime_admitted": bool(getattr(self.server, "source_runtime_admitted", False)),
                "real_model_running": self.server.runtime == "onnx" and self.server.models_available(),
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
                "key_protection": self.server.key_protection,
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

    def _stream_model_upload(
        self,
        destination: Path,
        *,
        maximum_bytes: int = MODEL_UPLOAD_LIMIT_BYTES,
    ) -> tuple[str, int]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise InputValidationError(
                "Invalid model upload length",
                "invalid_content_length",
            ) from exc
        if content_length <= 0:
            raise InputValidationError("Model upload is empty", "empty_file")
        if content_length > maximum_bytes:
            raise InputValidationError(
                "Model file exceeds the server-owned component limit",
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
        recovery_refusal = isinstance(exc, (
            GraphProjectionRebuildRefused,
            OperationRevertRefused,
            RecoveryPreparationRefused,
            RecoveryTokenError,
            StructuredRepairRefused,
            BackupRestoreError,
            ModelActivationRefused,
        ))
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
        if isinstance(exc, ModelActivationRefused):
            status = HTTPStatus.CONFLICT
        if isinstance(exc, EngineBusyError):
            status = HTTPStatus.SERVICE_UNAVAILABLE
        if isinstance(exc, AuthError):
            status = exc.status
        if recovery_refusal:
            status = HTTPStatus.CONFLICT
        payload = {"error": message}
        if isinstance(exc, EngineBusyError):
            payload["code"] = "engine_busy"
        if isinstance(exc, AuthError):
            payload["code"] = exc.code
        if isinstance(exc, ModelSetupError):
            payload["code"] = "model_setup_failed"
        if isinstance(exc, ModelActivationRefused):
            payload["code"] = "model_activation_refused"
        if validation_error:
            payload["code"] = "invalid_input"
            payload["reason"] = getattr(exc, "reason", "invalid_request")
        if isinstance(exc, EncounterRelationConflict):
            status = HTTPStatus.CONFLICT
            payload["code"] = "encounter_relation_conflict"
            payload["observation_id"] = exc.observation_id
        if recovery_refusal:
            stale_terms = ("stale", "fingerprint", "changed", "token")
            payload["code"] = (
                "stale_precondition"
                if isinstance(exc, RecoveryTokenError)
                or any(term in message.casefold() for term in stale_terms)
                else "operation_refused"
            )
            payload["committed"] = False
        if isinstance(exc, BackupRestoreError):
            payload["code"] = exc.code
            payload["outcome"] = exc.outcome
            payload["committed"] = exc.committed
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
    debug: bool = False,
    os_network_policy: OsNetworkPolicyStatus | None = None,
    instance_lock: InstanceLock | None = None,
    linux_source_onnx: bool = False,
    source_runtime_admitted: bool = False,
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
    if linux_source_onnx and runtime != "onnx":
        raise ValueError("Linux source custody requires ONNX source runtime")
    if linux_source_onnx or source_runtime_admitted:
        _startup_network_policy(runtime, allow_unpacked_source=True)
    data_dir = require_local_path(data_dir or default_data_dir()).expanduser().absolute()
    owned_lock = instance_lock is None
    runtime_lock = instance_lock or InstanceLock(data_dir).acquire()
    try:
        profile = assess_hardware()
        config = config_for_hardware(profile, data_dir=data_dir)
        config = replace(
            config,
            detector_model=data_dir / "models" / "detector.onnx",
            recognizer_model=data_dir / "models" / "recognizer.onnx",
        )
        require_local_path(config.detector_model)
        require_local_path(config.recognizer_model)
        validate_managed_storage(
            data_dir,
            (
                config.face_dir,
                config.index_dir,
                config.backup_dir,
                default_log_dir(data_dir),
                data_dir / "models",
            ),
        )
        cleanup_managed_temporaries((data_dir, config.backup_dir, data_dir / "models"))
        config = replace(config, storage_key=(
            load_linux_source_master_key(data_dir, explicit_source_onnx=True)
            if linux_source_onnx and runtime == "onnx"
            else load_or_create_master_key(data_dir)
        ))
        protect_existing_managed_data(data_dir, config.storage_key)
        authority = ModelBundleAuthority(data_dir / "models")
        authority.cleanup_stale_uploads()
        startup_bundle = resolve_startup_model_bundle(authority) if runtime == "onnx" else None
        if startup_bundle is not None:
            config = replace(
                config,
                detector_model=startup_bundle.directory / "detector.onnx",
                recognizer_model=startup_bundle.directory / "recognizer.onnx",
            )
        model_ready = True
        model_error = ""
        if runtime == "dev":
            engine = build_dev_engine(data_dir, config)
        else:
            try:
                engine = build_onnx_engine(config)
            except Exception as exc:
                model_ready = False
                model_error = redact_log_text(str(exc).strip("'")) or "Recognition models are missing or invalid"
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
            model_bundles=authority,
            instance_lock=runtime_lock,
            linux_source_onnx=linux_source_onnx,
        )
        server.source_runtime_admitted = runtime == "onnx" and (source_runtime_admitted or linux_source_onnx) and not getattr(sys, "frozen", False)
        if linux_source_onnx:
            server.key_protection = "linux-source-development-file"
        server.log_event("startup", runtime=runtime, port=server.server_port)
        if not model_ready:
            server.log_event("model-setup-required", error=model_error)
        return server
    except Exception:
        if owned_lock:
            runtime_lock.release()
        raise


def _install_shutdown_signal_handlers(
    server: SentriFaceApiServer,
) -> dict[int, Any]:
    shutdown_started = threading.Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        if shutdown_started.is_set():
            return
        shutdown_started.set()
        server.log_event("shutdown-requested", signal=signal.Signals(signum).name)
        threading.Thread(
            target=server.graceful_shutdown,
            name="sentriface-shutdown",
            daemon=True,
        ).start()

    previous_handlers: dict[int, Any] = {}
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[handled_signal] = signal.getsignal(handled_signal)
        signal.signal(handled_signal, request_shutdown)
    return previous_handlers


def _show_packaged_startup_error(message: str) -> None:
    """Make fail-closed startup errors visible for a windowed Windows build."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            "SentriFace Edge could not start",
            0x10,
        )
    except Exception:
        # The console error remains the fallback for diagnostic launches.
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="SentriFace Edge local UI")
    parser.add_argument("--version", action="version", version=f"SentriFace Edge {__version__}")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--runtime", choices=("dev", "onnx"), default="onnx")
    parser.add_argument(
        "--allow-unpackaged-source-onnx",
        action="store_true",
        help=(
            "Allow real ONNX inference from a Windows, macOS, or Linux Git checkout "
            "with the application socket guard but without the packaged OS-policy "
            "boundary; unavailable in packaged builds"
        ),
    )
    parser.add_argument("--quiet-debug", action="store_true", help="Disable verbose UI debug logs")
    parser.add_argument("--debug", action="store_true", help="Enable local diagnostic logging")
    parser.add_argument("--recover-kit", type=Path, help="Install a disaster-recovery key before startup")
    parser.add_argument(
        "--request-shutdown",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--release-self-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--self-test-report",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--self-test-detector",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--self-test-recognizer",
        type=Path,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.request_shutdown:
        return 0 if WindowsShutdownSignal.request(args.data_dir) else 3
    if args.release_self_test:
        if args.self_test_report is None:
            parser.error("--self-test-report is required with --release-self-test")
        from sentriface.release_self_test import run_release_self_test

        try:
            run_release_self_test(
                args.data_dir,
                args.self_test_report,
                detector_model=args.self_test_detector,
                recognizer_model=args.self_test_recognizer,
            )
        except Exception as exc:
            print(f"SentriFace packaged runtime self-test failed: {exc}")
            return 4
        print("SentriFace packaged runtime self-test passed")
        return 0

    from sentriface.logging_config import setup_logging

    runtime_lock: InstanceLock | None = None
    server: SentriFaceApiServer | None = None
    debug_enabled = bool(args.debug and not args.quiet_debug)
    try:
        os_network_policy = _startup_network_policy(
            args.runtime,
            allow_unpacked_source=args.allow_unpackaged_source_onnx,
        )
        if args.allow_unpackaged_source_onnx and os_network_policy is None:
            print(
                "WARNING: source ONNX mode uses the loopback listener and "
                "application socket guard, but not the packaged OS-policy boundary."
            )
        require_local_path(args.data_dir)
        startup_data_dir = args.data_dir.expanduser().absolute()
        runtime_lock = InstanceLock(startup_data_dir).acquire()
        validate_managed_storage(
            startup_data_dir,
            (
                startup_data_dir / "faces",
                startup_data_dir / "index",
                startup_data_dir / "backups",
                startup_data_dir / "logs",
                startup_data_dir / "models",
            ),
        )
        linux_source_onnx = sys.platform == "linux" and args.allow_unpackaged_source_onnx
        if args.recover_kit:
            require_local_path(args.recover_kit)
            from getpass import getpass
            recovered_key = recover_master_key(args.recover_kit, getpass("SentriFace recovery code: "))
            validate_recovered_master_key(args.data_dir, recovered_key)
            if linux_source_onnx:
                load_linux_source_master_key(args.data_dir, explicit_source_onnx=True, recovered_key=recovered_key)
            else:
                store_master_key(args.data_dir, recovered_key)
        storage_key = (
            load_linux_source_master_key(args.data_dir, explicit_source_onnx=True)
            if linux_source_onnx else load_or_create_master_key(args.data_dir)
        )
        setup_logging(
            debug=debug_enabled,
            log_dir=default_log_dir(args.data_dir),
            storage_key=storage_key,
            require_persistent=True,
        )
        server = create_server(
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
            runtime=args.runtime,
            debug=debug_enabled,
            os_network_policy=os_network_policy,
            instance_lock=runtime_lock,
            linux_source_onnx=linux_source_onnx,
            source_runtime_admitted=args.allow_unpackaged_source_onnx,
        )
    except ModelSetupError as exc:
        if runtime_lock is not None and server is None:
            runtime_lock.release()
        message = f"SentriFace could not start: {exc}"
        print(message)
        _show_packaged_startup_error(message)
        print("Install verified models with: sentriface-models")
        return 2
    except (
        SentriFaceError,
        StorageSecurityError,
        RuntimeReadinessError,
        RecoveryError,
        OsNetworkPolicyError,
        OSError,
        ValueError,
    ) as exc:
        if runtime_lock is not None and server is None:
            runtime_lock.release()
        message = f"SentriFace could not start safely: {exc}"
        print(message)
        _show_packaged_startup_error(message)
        return 2
    print(f"SentriFace UI running at http://{args.host}:{server.server_port}")
    previous_handlers = _install_shutdown_signal_handlers(server)
    installer_signal = WindowsShutdownSignal(args.data_dir).create()
    installer_waiter = None
    if os.name == "nt":
        installer_waiter = threading.Thread(
            target=lambda: installer_signal.wait() and server.graceful_shutdown(),
            name="sentriface-installer-shutdown",
            daemon=True,
        )
        installer_waiter.start()
    try:
        server.serve_forever()
    finally:
        installer_signal.close()
        for handled_signal, previous in previous_handlers.items():
            signal.signal(handled_signal, previous)
        server.server_close()
    return 0



def _startup_network_policy(
    runtime: str,
    *,
    allow_unpacked_source: bool = False,
    source_root: Path | None = None,
) -> OsNetworkPolicyStatus | None:
    if runtime != "onnx":
        if allow_unpacked_source:
            raise ValueError(
                "--allow-unpackaged-source-onnx requires --runtime onnx"
            )
        return None
    if not allow_unpacked_source:
        return require_os_network_policy()
    if sys.platform not in {"darwin", "win32", "linux"}:
        raise ValueError(
            "--allow-unpackaged-source-onnx is available only on Windows, macOS, and Linux"
        )
    if sys.platform == "linux" and "__compiled__" in globals():
        raise ValueError(
            "--allow-unpackaged-source-onnx requires an unpackaged Git checkout"
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

def _recognition_quality_only(payload: dict[str, Any]) -> bool:
    value = payload.get("quality_only", True)
    if not isinstance(value, bool):
        raise InputValidationError("quality_only must be a boolean", "invalid_quality_policy")
    return value


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        raise KeyError(f"Missing required field: {key}")
    return str(value)


def _review_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload.get(key)
        for key in (
            "name", "decision", "date", "time", "rank", "country",
            "importance", "place_seen", "individual_count",
            "event_occasion", "event_context", "event_notes", "event_mentioned_person_ids", "end_time", "time_precision", "added_by", "proof_only_duplicate_override",
        )
        if payload.get(key) is not None
    }


def _queue_quality_choices(payload: dict[str, Any]) -> dict[str, str]:
    choices = payload.get("quality_choices") or {}
    if not isinstance(choices, dict) or len(choices) > 1000:
        raise InputValidationError("quality_choices must be a face map", "invalid_quality_choices")
    result = {str(key): str(value) for key, value in choices.items()}
    if any(value not in {"POOR_ACCEPTED", "PROOF_ONLY"} for value in result.values()):
        raise InputValidationError("Invalid poor-face choice", "invalid_quality_choices")
    return result


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


def _integrity_reason(payload: dict[str, Any]) -> str:
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise InputValidationError(
            "A recovery reason is required",
            "recovery_reason_required",
        )
    if len(reason) > 500:
        raise InputValidationError(
            "Recovery reason must be 500 characters or fewer",
            "recovery_reason_too_long",
        )
    return reason


def _validate_integrity_recovery_payload(path: str, payload: dict[str, Any]) -> None:
    allowed = INTEGRITY_RECOVERY_REQUEST_FIELDS[path]
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise InputValidationError(
            "Integrity recovery requests contain only server-defined fields",
            "unsupported_recovery_fields",
        )


def _validate_model_install_payload(payload: dict[str, Any]) -> None:
    unknown = sorted(set(payload) - MODEL_INSTALL_REQUEST_FIELDS)
    if unknown:
        raise InputValidationError(
            "Model installation accepts only server-defined bundle fields",
            "unsupported_model_install_fields",
        )
    for field in ("detector_upload_id", "recognizer_upload_id"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise InputValidationError(
                "Model installation requires opaque detector and recognizer upload IDs",
                "invalid_model_upload_reference",
            )
    optional_reference = payload.get("calibration_upload_id")
    if optional_reference is not None and (
        not isinstance(optional_reference, str) or len(optional_reference.strip()) > 64
    ):
        raise InputValidationError(
            "Calibration upload reference is invalid",
            "invalid_model_upload_reference",
        )
    for field in ("organization", "licensor", "license_reference", "license_name"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or len(value.strip()) > 500):
            raise InputValidationError(
                "Model declaration fields must be bounded text",
                "invalid_model_declaration",
            )


def _validate_model_operation_payload(path: str, payload: dict[str, Any]) -> None:
    allowed = MODEL_OPERATION_REQUEST_FIELDS[path]
    if set(payload) - allowed:
        raise InputValidationError(
            "Model runtime operations accept only server-defined fields",
            "unsupported_model_operation_fields",
        )
    if path.endswith("/prepare") and "bundle_id" in allowed:
        value = payload.get("bundle_id")
        if not isinstance(value, str) or len(value.strip()) != 32:
            raise InputValidationError(
                "Model preparation requires one opaque bundle ID",
                "invalid_model_bundle_reference",
            )
    if path.endswith("/execute"):
        token = payload.get("token")
        operation_id = payload.get("operation_id")
        reason = payload.get("reason", "")
        if not isinstance(token, str) or not token or len(token) > 16_000:
            raise InputValidationError(
                "Model execution requires the exact bounded preparation token",
                "invalid_model_preparation_token",
            )
        try:
            uuid.UUID(str(operation_id), version=4)
        except (ValueError, TypeError, AttributeError) as exc:
            raise InputValidationError(
                "Model execution operation ID must be a UUID",
                "invalid_model_operation_id",
            ) from exc
        if not isinstance(reason, str) or len(reason.strip()) > 500:
            raise InputValidationError(
                "Model execution reason must be bounded text",
                "invalid_model_operation_reason",
            )


def _validate_model_upload_query(query: str) -> None:
    fields = parse_qs(query, keep_blank_values=True)
    if set(fields) != {"kind", "filename"} or any(len(values) != 1 for values in fields.values()):
        raise InputValidationError(
            "Model upload accepts only one kind and one metadata filename",
            "unsupported_model_upload_fields",
        )


def _validate_backup_restore_payload(payload: dict[str, Any]) -> None:
    allowed = {"backup_id", "operation_id", "reason"}
    unexpected = set(payload) - allowed
    if unexpected:
        raise InputValidationError(
            "Backup restore accepts only backup ID, operation ID, and reason",
            "unsupported_restore_fields",
        )
    for field in ("backup_id", "operation_id"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise InputValidationError(
                "Backup restore requires a bounded backup ID and operation ID",
                "invalid_restore_identity",
            )
    reason = payload.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason.strip()) > 500):
        raise InputValidationError(
            "Backup restore reason must be at most 500 characters",
            "invalid_restore_reason",
        )


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


def _pending_recognition(
    engine: FaceEngine, pending: PendingAddition, index: int,
) -> dict[str, Any]:
    return {
        "index": index,
        "decision": pending.decision.value,
        "box": _box(pending.face),
        "quality": _quality(pending.quality),
        "matches": [
            _match(engine, match, rank)
            for rank, match in enumerate(pending.matches, 1)
        ],
    }


def _photo_review(review: PhotoReview) -> dict[str, Any]:
    return {
        "review_id": review.review_id,
        "media_id": review.media_id,
        "media_path": review.media_path,
        "source": review.source,
        "status": review.status,
        "observation_id": review.observation_id,
        "completed_operation_id": review.completed_operation_id,
        "created_at": review.created_at,
        "completed_at": review.completed_at,
        "faces": [
            {
                "face_id": face.face_id,
                "staged_face_type": face.staged_face_type,
                "staged_face_id": face.staged_face_id,
                "decision": face.decision,
                "person_id": face.person_id,
                "new_person_key": face.new_person_key,
                "new_person_name": face.new_person_name,
                "new_person_metadata": face.new_person_metadata,
                "notes": face.notes,
                "mentioned_person_ids": list(face.mentioned_person_ids),
                "recognition_detail": face.recognition_detail,
            }
            for face in review.faces
        ],
    }


def _rejected(rejected: RejectedFace, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "source_image": rejected.source_image,
        "box": _box(rejected.face),
        "quality": _quality(rejected.quality),
    }


def _person(person: Person) -> dict[str, Any]:
    lifecycle_status = person.lifecycle_status
    effective_person_id = person.canonical_person_id or person.person_id
    return {
        "person_id": person.person_id,
        "name": person.name,
        "metadata": person.metadata,
        "created_at": person.created_at,
        "deleted_at": person.deleted_at,
        "lifecycle_status": lifecycle_status,
        "canonical_person_id": person.canonical_person_id,
        "effective_person_id": effective_person_id,
        "identity_status": person.identity_status,
        "biometric_status": person.biometric_status,
        "archived": lifecycle_status == "ARCHIVED",
        "deleted": lifecycle_status == "DELETED",
        "merged": lifecycle_status == "MERGED",
        "active": lifecycle_status == "ACTIVE" and person.deleted_at is None,
        "enrollment_status": person.enrollment_status,
        "is_placeholder": person.enrollment_status == "placeholder",
        "notes": person.notes,
        "allowed_actions": _allowed_person_actions(lifecycle_status),
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
    payload = {
        **_person(summary.person),
        "embedding_count": summary.embedding_count,
        "sighting_count": summary.sighting_count,
        "last_seen_at": summary.last_seen_at,
        "first_seen_at": summary.first_seen_at,
        "frequency_per_30_days": summary.frequency_per_30_days,
        "frequency_label": summary.frequency_label,
        "favorite": bool(summary.person.metadata.get("favorite")),
        "tags": list(summary.person.metadata.get("tags", [])),
        "representative_image": _representative_image(
            embeddings,
            summary.person.metadata.get("representative_embedding_id"),
        ),
    }
    payload["presentation"] = {
        "priority_rank": _priority_rank(summary.person.metadata.get("importance")),
        "priority_label": _priority_label(summary.person.metadata.get("importance")),
        "group_labels": {
            "country": str(summary.person.metadata.get("country") or "Unknown Country"),
            "rank": str(summary.person.metadata.get("rank") or "Unspecified Rank"),
            "priority": f"{_priority_label(summary.person.metadata.get('importance'), long=True)} Priority",
            "frequency": summary.frequency_label,
            "frequent": (
                "Not Seen Yet" if summary.sighting_count == 0
                else "Frequently Seen" if summary.frequency_label in {"Very Frequent", "Frequent"}
                else "Seen Occasionally"
            ),
        },
    }
    return payload


def _allowed_person_actions(lifecycle_status: str) -> list[str]:
    return {
        "ACTIVE": [
            "OPEN", "EDIT", "EDIT_NOTES", "FAVORITE", "MANAGE_FACES",
            "ARCHIVE", "DELETE", "MERGE",
        ],
        "ARCHIVED": ["VIEW_HISTORY", "RESTORE", "DELETE"],
        "DELETED": ["VIEW_HISTORY"],
        "MERGED": ["VIEW_HISTORY", "OPEN_CANONICAL"],
    }.get(lifecycle_status, [])


def _priority_rank(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized in {"important", "high"}:
        return 3
    if normalized in {"suspicious", "watch"}:
        return 2
    if normalized in {"regular", "medium"}:
        return 1
    return 0


def _priority_label(value: Any, *, long: bool = False) -> str:
    rank = _priority_rank(value)
    labels = {
        3: ("HIGH", "High"),
        2: ("WATCH", "Watch"),
        1: ("REGULAR", "Regular"),
        0: ("UNSPECIFIED", "Unspecified"),
    }
    return labels[rank][1 if long else 0]


def _people_collection_payload(engine: FaceEngine) -> dict[str, Any]:
    active_summaries = engine.list_persons()
    historical_summaries = engine.list_persons(archived=True)
    active = [_person_summary(item, engine) for item in active_summaries]
    historical = [_person_summary(item, engine) for item in historical_summaries]
    return {
        "contract_version": 1,
        "persons": active,
        "archived_persons": historical,
        "statistics": {
            "active": _people_statistics(active),
            "historical": _people_statistics(historical),
        },
        "sort_orders": {
            "active": _people_sort_orders(active),
            "historical": _people_sort_orders(historical),
        },
    }


def _people_statistics(people: list[dict[str, Any]]) -> dict[str, int]:
    now = datetime.now(timezone.utc)

    def parsed(value: Any) -> datetime | None:
        try:
            result = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            return result.replace(tzinfo=result.tzinfo or timezone.utc)
        except ValueError:
            return None

    def today(value: Any) -> bool:
        result = parsed(value)
        return bool(result and result.astimezone(timezone.utc).date() == now.date())

    def recent(value: Any) -> bool:
        result = parsed(value)
        return bool(result and 0 <= (now - result.astimezone(timezone.utc)).total_seconds() <= 7 * 86_400)

    return {
        "people_count": len(people),
        "embedding_count": sum(int(item.get("embedding_count") or 0) for item in people),
        "favorite_count": sum(bool(item.get("favorite")) for item in people),
        "with_photos_count": sum(int(item.get("embedding_count") or 0) > 0 for item in people),
        "without_photos_count": sum(int(item.get("embedding_count") or 0) == 0 for item in people),
        "seen_last_7_days_count": sum(recent(item.get("last_seen_at")) for item in people),
        "added_today_count": sum(today(item.get("created_at")) for item in people),
        "archived_today_count": sum(today(item.get("deleted_at")) for item in people),
        "merged_count": sum(item.get("lifecycle_status") == "MERGED" for item in people),
    }


def _people_sort_orders(people: list[dict[str, Any]]) -> dict[str, list[str]]:
    def text(item: dict[str, Any], key: str) -> str:
        return str(item.get("metadata", {}).get(key) or "").casefold()

    def timestamp(value: Any) -> float:
        try:
            return datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    def ordered(key: Callable[[dict[str, Any]], Any]) -> list[str]:
        return [item["person_id"] for item in sorted(people, key=key)]

    name_key = lambda item: str(item.get("name") or "").casefold()
    return {
        "name": ordered(name_key),
        "country": ordered(lambda item: (text(item, "country"), name_key(item))),
        "rank": ordered(lambda item: (text(item, "rank"), name_key(item))),
        "priority": ordered(lambda item: (-item["presentation"]["priority_rank"], name_key(item))),
        "sightings": ordered(lambda item: (-int(item.get("sighting_count") or 0), name_key(item))),
        "frequency": ordered(lambda item: (-float(item.get("frequency_per_30_days") or 0), name_key(item))),
        "seen": ordered(lambda item: (-timestamp(item.get("last_seen_at")), name_key(item))),
        "frequent": ordered(lambda item: (-float(item.get("frequency_per_30_days") or 0), name_key(item))),
        "newest": ordered(lambda item: (-timestamp(item.get("created_at")), name_key(item))),
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
        "association_origin": association.association_origin,
        "person": _person_summary(summary, engine),
    }


def _graph_connection_association(
    connection: GraphConnection,
    current_person_id: str,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> dict[str, Any]:
    associated_person_id = (
        connection.target_person_id
        if connection.source_person_id == current_person_id
        else connection.source_person_id
    )
    summary = person_summaries.get(associated_person_id)
    if summary is None:
        raise RuntimeError("A graph person record is unavailable")
    return {
        "association_id": (
            f"graph:{connection.source_person_id}:{connection.target_person_id}:"
            f"{connection.relationship_type}:{connection.directionality}"
        ),
        "source_person_id": connection.source_person_id,
        "target_person_id": connection.target_person_id,
        "relationship_type": connection.relationship_type,
        "created_at": connection.last_evidence_at,
        "updated_at": connection.last_evidence_at,
        "created_by": "Normalized evidence",
        "association_origin": "+".join(connection.evidence_types),
        "evidence_count": connection.evidence_count,
        "person": _person_summary(summary, engine),
    }


def _embedding(record: EmbeddingRecord) -> dict[str, Any]:
    return embedding_record_payload(record)


def _note_record(note: Note) -> dict[str, Any]:
    return {
        "note_id": note.note_id,
        "raw_owner_person_id": note.owner_person_id,
        "canonical_owner_person_id": note.canonical_owner_person_id or note.owner_person_id,
        "content": note.content,
        "revision_number": note.revision_number,
        "raw_mentioned_person_ids": list(note.mentioned_person_ids),
        "effective_mentioned_person_ids": list(note.effective_mentioned_person_ids),
        "status": note.status,
    }


def _profile_note_record(
    note: Note | None,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> dict[str, Any]:
    if note is None:
        return {
            "note_id": None,
            "content": "",
            "revision_number": 0,
            "mentioned_person_ids": [],
            "mentions": [],
        }
    mentions = []
    for raw_person_id in note.mentioned_person_ids:
        effective_person_id = engine.resolve_canonical_person_id(raw_person_id)
        summary = person_summaries.get(effective_person_id) or person_summaries.get(raw_person_id)
        person_payload = _person_summary(summary, engine) if summary is not None else None
        mentions.append({
            "occurrence_id": f"{note.note_id}:{raw_person_id}",
            "raw_person_id": raw_person_id,
            "effective_person_id": effective_person_id,
            "display_name": person_payload["name"] if person_payload else raw_person_id,
            "person": person_payload,
        })
    return {
        "note_id": note.note_id,
        "content": note.content,
        "revision_number": note.revision_number,
        "mentioned_person_ids": list(note.mentioned_person_ids),
        "effective_mentioned_person_ids": list(note.effective_mentioned_person_ids),
        "mentions": mentions,
    }


def _person_relationships(
    intelligence: PersonIntelligence,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> list[dict[str, Any]]:
    relationships = []
    for item in intelligence.relationships:
        summary = person_summaries.get(item.person_id)
        if summary is None:
            raise RuntimeError("A related person record is unavailable")
        relationships.append({
            "relationship_id": (
                f"relationship:{item.source_person_id}:{item.target_person_id}:"
                f"{item.relationship_type}:{item.directionality}"
            ),
            "person_id": item.person_id,
            "source_person_id": item.source_person_id,
            "target_person_id": item.target_person_id,
            "relationship_type": item.relationship_type,
            "directionality": item.directionality,
            "evidence_count": item.evidence_count,
            "evidence_type_counts": item.evidence_type_counts,
            "co_observation_count": item.co_observation_count,
            "first_evidence_at": item.first_evidence_at,
            "last_evidence_at": item.last_evidence_at,
            "presentation_label": _relationship_label(item.evidence_type_counts),
            "person": _person_summary(summary, engine),
            "manual_evidence": [{"evidence_id": evidence.evidence_id, "created_at": evidence.created_at}
                                for evidence in item.evidence if evidence.evidence_type == "MANUAL_ASSOCIATION"],
        })
    return relationships


def _relationship_label(evidence_counts: dict[str, int] | set[str] | tuple[str, ...]) -> str:
    types = set(evidence_counts)
    if len(types) > 1:
        return "Multiple evidence types"
    if "NOTE_REFERENCE" in types:
        return "Mention-linked"
    if "CO_OBSERVED" in types:
        return "Co-observed"
    if "MANUAL_ASSOCIATION" in types:
        return "Manually linked"
    return "Related"


def _graph_filters_from_query(query: str) -> GraphReadFilter:
    values = parse_qs(query)

    def one(key: str) -> str | None:
        value = values.get(key, [None])[0]
        return str(value).strip() if value is not None and str(value).strip() else None

    def many(key: str) -> tuple[str, ...]:
        result: list[str] = []
        for value in values.get(key, []):
            result.extend(item.strip() for item in str(value).split(",") if item.strip())
        return tuple(result)

    def number(key: str, caster):
        value = one(key)
        if value is None:
            return None
        try:
            return caster(value)
        except ValueError as exc:
            raise ValueError(f"Invalid graph filter: {key}") from exc

    return GraphReadFilter(
        date_from=one("date_from"),
        date_to=one("date_to"),
        location=one("location"),
        lifecycle=many("lifecycle"),
        country=many("country"),
        rank=many("rank"),
        priority=many("priority"),
        min_frequency=number("min_frequency", float),
        min_relationship_strength=number("min_relationship_strength", int),
    )


def _graph_filter_payload(filters: GraphReadFilter) -> dict[str, Any]:
    return {
        "date_from": filters.date_from,
        "date_to": filters.date_to,
        "location": filters.location,
        "lifecycle": list(filters.lifecycle),
        "country": list(filters.country),
        "rank": list(filters.rank),
        "priority": list(filters.priority),
        "min_frequency": filters.min_frequency,
        "min_relationship_strength": filters.min_relationship_strength,
    }


def _graph_read_node_payload(node: GraphReadNode) -> dict[str, Any]:
    return {
        "person_id": node.person_id,
        "canonical_person_id": node.canonical_person_id,
        "effective_person_id": node.canonical_person_id,
        "display_name": node.display_name,
        "lifecycle_status": node.lifecycle_status,
        "biometric_status": node.biometric_status,
        "representative_media_reference": node.representative_media_reference,
        "allowed_actions": list(node.allowed_actions),
        "state_indicator": node.state_indicator,
        "historical_person_ids": list(node.historical_person_ids),
        "summary_intelligence": node.summary_intelligence,
    }


def _graph_read_edge_payload(edge: GraphReadEdge) -> dict[str, Any]:
    return {
        "edge_id": f"graph:{edge.source_person_id}:{edge.target_person_id}",
        "source": edge.source_person_id,
        "target": edge.target_person_id,
        "source_person_id": edge.source_person_id,
        "target_person_id": edge.target_person_id,
        "connected_person_id": edge.connected_person_id,
        "canonical_endpoints": {
            "source_person_id": edge.canonical_source_person_id,
            "target_person_id": edge.canonical_target_person_id,
        },
        "relationship_strength": edge.relationship_strength,
        "evidence_count": edge.evidence_count,
        "evidence_types": list(edge.evidence_types),
        "first_occurrence": edge.first_occurrence_at,
        "last_occurrence": edge.last_occurrence_at,
        "directionality": edge.directionality,
        "relationship_types": list(edge.relationship_types),
        "relationship_type_summary": edge.relationship_type_summary,
        "strength_basis": edge.strength_basis,
        "provenance_summary": edge.provenance_summary,
    }


def _person_graph_read_payload(model: PersonGraphReadModel) -> dict[str, Any]:
    return {
        "contract": "sentriface.person-graph",
        "contract_version": 1,
        "graph_revision": model.graph_revision,
        "generated_at": model.generated_at,
        "requested_person_id": model.requested_person_id,
        "root_person_id": model.root_person_id,
        "root_requested_state": model.root_requested_state,
        "filters": _graph_filter_payload(model.filters),
        "nodes": [_graph_read_node_payload(item) for item in model.nodes],
        "edges": [_graph_read_edge_payload(item) for item in model.edges],
        "node_count": len(model.nodes),
        "edge_count": len(model.edges),
    }


def _world_graph_read_payload(model: WorldGraphReadModel) -> dict[str, Any]:
    return {
        "contract": "sentriface.world-graph",
        "contract_version": 1,
        "graph_revision": model.graph_revision,
        "generated_at": model.generated_at,
        "filters": _graph_filter_payload(model.filters),
        "nodes": [_graph_read_node_payload(item) for item in model.nodes],
        "edges": [_graph_read_edge_payload(item) for item in model.edges],
        "node_count": len(model.nodes),
        "edge_count": len(model.edges),
    }


def _world_graph_v2_request_from_query(query: str) -> WorldGraphRequest:
    values = parse_qs(query)

    def one(key: str) -> str | None:
        value = values.get(key, [None])[0]
        return str(value).strip() if value is not None and str(value).strip() else None

    def many(key: str) -> tuple[str, ...]:
        result: list[str] = []
        for value in values.get(key, []):
            result.extend(item.strip() for item in str(value).split(",") if item.strip())
        return tuple(result)

    def integer(key: str, default: int) -> int:
        value = one(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Invalid World limit: {key}") from exc

    level_text = (one("level") or "WORLD_SCOPE").upper()
    below = one("include_below_threshold") or "false"
    if below.lower() not in {"true", "false"}:
        raise ValueError("include_below_threshold must be true or false")
    try:
        level = WorldDetailLevel(level_text)
    except ValueError as exc:
        raise ValueError(f"Unsupported World detail level: {level_text}") from exc
    return WorldGraphRequest(
        detail_level=level,
        collection=(WorldCollection(one("collection").upper()) if one("collection") else None),
        focus_type=one("focus_type"), focus_id=one("focus_id"),
        filters=WorldReadFilter(
            date_from=one("date_from"), date_to=one("date_to"),
            recent_activity=one("recent_activity"), locations=many("location"),
            missing_location=one("missing_location") or "INCLUDE",
            lifecycle=many("lifecycle"), identity_state=many("identity_state"),
            biometric_state=many("biometric_state"), country=many("country"),
            rank=many("rank"), priority=many("priority"),
            evidence_type=many("evidence_type"), relationship_type=many("relationship_type"),
            min_relationship_strength=(integer("min_relationship_strength", 1) if one("min_relationship_strength") else None),
            activity=many("activity"), pattern_type=many("pattern_type"),
        ),
        ranking=one("ranking") or "SALIENCE",
        limits=WorldReadLimits(
            people=integer("people_limit", 25), clusters=integer("cluster_limit", 10),
            events=integer("event_limit", 25), evidence=integer("evidence_limit", 25),
            media=integer("media_limit", 25),
            relationships=integer("relationship_limit", 50), patterns=integer("pattern_limit", 10),
            provenance=integer("provenance_limit", 100),
            facets=integer("facet_limit", 100),
        ),
        cursor=one("cursor"), revision=one("revision"), as_of=one("as_of"),
        view=one("view") or "CURRENT",
        include_below_threshold=below.lower() == "true",
        discovery_period_days=integer("discovery_period_days", 30),
        location_query=one("location_query"),
    )


def _world_graph_v2_payload(model: WorldGraphV2ReadModel) -> dict[str, Any]:
    # Normalize tuple-backed immutable models into their JSON array representation.
    payload = json.loads(json.dumps(asdict(model)))
    def remove_dormant_tokens(value: Any) -> None:
        if isinstance(value, dict):
            for key in (
                "expansion_tokens", "expansion_token", "evidence_expansion_token",
            ):
                value.pop(key, None)
            for child in value.values():
                remove_dormant_tokens(child)
        elif isinstance(value, list):
            for child in value:
                remove_dormant_tokens(child)

    remove_dormant_tokens(payload)
    payload.update({
        "contract": "sentriface.world-graph",
        "contract_version": 2,
        "filter_semantics_version": "world-filters-v1",
        "ranking_version": "descriptive-salience-v1",
        "clustering_version": "connected-evidence-components-v1",
        "calculation_version": "world-descriptive-v1",
    })
    return payload


def _person_relationship_graph(
    engine: FaceEngine,
    requested_person_id: str,
    *,
    limit: int,
) -> dict[str, Any]:
    root = engine.get_effective_person(requested_person_id)
    if root is None:
        raise KeyError("This person no longer exists")
    projection = engine.get_global_graph_projection()
    nodes_by_id = {node.person_id: node for node in projection.nodes}
    root_id = root.person_id
    if root_id not in nodes_by_id:
        raise RuntimeError("The requested person is missing from the graph projection")

    adjacency: dict[str, set[str]] = {person_id: set() for person_id in nodes_by_id}
    for connection in projection.connections:
        adjacency.setdefault(connection.source_person_id, set()).add(connection.target_person_id)
        adjacency.setdefault(connection.target_person_id, set()).add(connection.source_person_id)

    selected_ids: list[str] = []
    depths = {root_id: 0}
    queue = [root_id]
    while queue and len(selected_ids) < limit:
        person_id = queue.pop(0)
        selected_ids.append(person_id)
        for neighbor_id in sorted(adjacency.get(person_id, set())):
            if neighbor_id in depths:
                continue
            depths[neighbor_id] = depths[person_id] + 1
            queue.append(neighbor_id)

    selected = set(selected_ids)
    summaries = {
        item.person.person_id: item
        for item in [*engine.list_persons(), *engine.list_persons(archived=True)]
    }
    nodes = []
    for person_id in selected_ids:
        graph_node = nodes_by_id[person_id]
        summary = summaries.get(person_id)
        person_payload = _person_summary(summary, engine) if summary is not None else {
            "person_id": person_id,
            "name": graph_node.name,
            "lifecycle_status": graph_node.lifecycle_status,
            "canonical_person_id": graph_node.canonical_person_id,
            "effective_person_id": graph_node.canonical_person_id or person_id,
            "allowed_actions": _allowed_person_actions(graph_node.lifecycle_status),
            "representative_image": "",
            "metadata": {},
            "is_placeholder": True,
        }
        nodes.append({
            **person_payload,
            "layout": {"depth": depths[person_id]},
        })

    edges = [
        {
            "edge_id": (
                f"graph:{item.source_person_id}:{item.target_person_id}:"
                f"{item.relationship_type}:{item.directionality}"
            ),
            "source_person_id": item.source_person_id,
            "target_person_id": item.target_person_id,
            "relationship_type": item.relationship_type,
            "directionality": item.directionality,
            "evidence_count": item.evidence_count,
            "evidence_types": list(item.evidence_types),
            "last_evidence_at": item.last_evidence_at,
            "presentation_label": _relationship_label(item.evidence_types),
        }
        for item in projection.connections
        if item.source_person_id in selected and item.target_person_id in selected
    ]
    revision_payload = {
        "nodes": [
            [item["person_id"], item["canonical_person_id"], item["lifecycle_status"]]
            for item in nodes
        ],
        "edges": [
            [item["edge_id"], item["evidence_count"], item["last_evidence_at"]]
            for item in edges
        ],
    }
    graph_revision = hashlib.sha256(
        json.dumps(revision_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "contract": "sentriface.relationship-subgraph",
        "contract_version": 1,
        "graph_revision": graph_revision,
        "requested_person_id": requested_person_id,
        "root_person_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "truncated": len(selected_ids) < len(nodes_by_id) and bool(queue),
        "limit": limit,
    }


def _observation_record(observation: Observation) -> dict[str, Any]:
    return {
        "observation_id": observation.observation_id,
        "status": observation.status,
        "observed_at": observation.observed_at,
        "location": observation.location,
        "context": observation.context,
        "source": observation.source,
    }


def _sighting_record(sighting: Sighting) -> dict[str, Any]:
    observed_at = sighting.observed_at
    date, separator, time = observed_at.partition("T")
    media = [
        {
            "media_id": item.media_id,
            "media_path": item.media_path,
            "source": item.source,
        }
        for item in sighting.media
    ]
    return {
        "sighting_id": sighting.sighting_id,
        "detail_id": sighting.sighting_id,
        "observation_id": sighting.observation_id,
        "canonical_person_id": sighting.canonical_person_id,
        "observed_at": observed_at,
        "date": date,
        "time": time if separator else "",
        "location": sighting.location,
        "place_seen": sighting.location or "",
        "context": sighting.context,
        "event_occasion": str(sighting.context.get("occasion") or ""),
        "source": sighting.source,
        "added_by": str(sighting.context.get("added_by") or ""),
        "finalized_at": sighting.finalized_at,
        "media": media,
        "image_path": next((item["media_path"] for item in media if item["media_path"]), None),
        "raw_participant_person_ids": list(sighting.raw_participant_person_ids),
        "effective_participant_person_ids": list(sighting.effective_participant_person_ids),
        "correction_operation_ids": list(sighting.correction_operation_ids),
        "provenance": {
            "basis": "finalized observation accepted participation",
            "raw_participants_preserved": True,
            "canonical_resolution_applied": True,
        },
    }


def _person_intelligence(intelligence: PersonIntelligence) -> dict[str, Any]:
    presence = intelligence.presence
    return {
        "requested_person_id": intelligence.requested_person_id,
        "canonical_person_id": intelligence.canonical_person_id,
        "lifecycle_status": intelligence.lifecycle_status,
        "canonical_lifecycle_status": intelligence.canonical_lifecycle_status,
        "biometric_status": intelligence.biometric_status,
        "embedding_count": intelligence.embedding_count,
        "confidence_summary": intelligence.confidence_summary,
        "relationship_count": len({item.person_id for item in intelligence.relationships}),
        "presence": {
            "observation_count": presence.observation_count,
            "first_seen_at": presence.first_seen_at,
            "last_seen_at": presence.last_seen_at,
            "frequency_per_30_days": presence.frequency_per_30_days,
            "frequency_label": presence.frequency_label,
            "timeline": [
                {"period": item.period, "count": item.count}
                for item in presence.timeline
            ],
            "locations": [
                {
                    "location": item.location,
                    "count": item.count,
                    "last_observed_at": item.last_observed_at,
                }
                for item in presence.locations
            ],
            "provenance": list(presence.provenance),
        },
        "relationships": [
            {
                "person_id": item.person_id,
                "source_person_id": item.source_person_id,
                "target_person_id": item.target_person_id,
                "relationship_type": item.relationship_type,
                "directionality": item.directionality,
                "evidence_count": item.evidence_count,
                "evidence_type_counts": item.evidence_type_counts,
                "first_evidence_at": item.first_evidence_at,
                "last_evidence_at": item.last_evidence_at,
                "co_observation_count": item.co_observation_count,
                "strength": {
                    "basis": "active normalized evidence count",
                    "count": item.evidence_count,
                    "probability": None,
                },
                "evidence": [
                    {
                        "evidence_id": evidence.evidence_id,
                        "evidence_type": evidence.evidence_type,
                        "source_entity_type": evidence.source_entity_type,
                        "source_entity_id": evidence.source_entity_id,
                        "raw_source_person_id": evidence.source_person_id,
                        "raw_target_person_id": evidence.target_person_id,
                        "created_at": evidence.created_at,
                        "source": evidence.source,
                    }
                    for evidence in item.evidence
                ],
            }
            for item in intelligence.relationships
        ],
        "activity": list(intelligence.activity),
        "provenance": list(intelligence.provenance),
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
        "person_lifecycle_status": record["person_lifecycle_status"],
        "canonical_person_id": record["canonical_person_id"],
        "person_archived": record["person_lifecycle_status"] == "ARCHIVED",
        "person_deleted": record["person_lifecycle_status"] == "DELETED",
        "person_merged": record["person_lifecycle_status"] == "MERGED",
        "quality_score": record["quality_score"],
        "source_image": record["source_image"],
        "crop_path": record["crop_path"],
        "created_at": record["created_at"],
        "deleted_at": record["deleted_at"],
        "purge_after": purge_after,
        "days_remaining": days_remaining,
        "sighting_count": record["sighting_count"],
    }


def _recognition_detail(
    detail: RecognitionDetail,
    canonical_person_id: str | None = None,
) -> dict[str, Any]:
    return {
        "detail_id": detail.detail_id,
        "embedding_id": detail.embedding_id,
        "person_id": detail.person_id,
        "raw_person_id": detail.person_id,
        "canonical_person_id": canonical_person_id or detail.person_id,
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
        "notes": detail.notes,
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
        "previous_notes": change.previous_notes,
        "new_notes": change.new_notes,
        "editor_name": change.editor_name,
        "created_at": change.created_at,
    }


def _init_group(
    engine: FaceEngine,
    group: InitGroup,
    matches_by_face_id: dict[str, list[PersonMatch]] | None = None,
    encounter_review_id: str | None = None,
) -> dict[str, Any]:
    session = engine.store.get_init_session(group.session_id)
    quality_only = session.quality_only if session else True
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
            quality_only=quality_only,
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
        "matches": [{**match, "rank": rank, **_match_policy(engine, match["score"])} for rank, match in enumerate(engine.encounter_matches_for_init_group(group, encounter_review_id), 1)] if encounter_review_id else [_match(engine, match, rank) for rank, match in enumerate(group_matches, 1)],
        "draft_matches": [],
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
        "target_observation_id": session.target_observation_id,
        "expected_encounter_revision": session.expected_encounter_revision,
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
    sanitized = sanitize_log_details(details)
    return sanitized if isinstance(sanitized, dict) else {}


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
        "key_protection": getattr(server, "key_protection", "operating-system-vault" if config.storage_key else "none"),
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
        "restorable": record.restorable,
        "integrity_status": record.integrity_status,
    }


if __name__ == "__main__":
    raise SystemExit(main())
