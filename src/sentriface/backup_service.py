from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sqlite3
import threading
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from sentriface import __version__
from sentriface.backup_crypto import (
    BackupEncryptionError,
    ENCRYPTED_BACKUP_EXTENSION,
    decrypt_file,
    encrypt_file,
)
from sentriface.secure_storage import connect_database
from sentriface.secure_files import (
    ProtectedFileError,
    authenticate_protected_file,
    copy_into_protected_storage,
)
from sentriface.media_registry import (
    MEDIA_REGISTRY_BY_ID,
    identity_values,
    iter_media_references,
    stable_identity,
    update_media_reference,
)


BACKUP_ID_PATTERN = re.compile(
    r"^backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"
    r"(?:_[a-z0-9][a-z0-9-]{0,95})?(?:_\d{2})?$"
)
PORTABLE_BACKUP_FORMAT_VERSION = 3
LEGACY_PORTABLE_BACKUP_FORMAT_VERSION = 2
PORTABLE_BACKUP_EXTENSION = ".sfbackup"
MAX_ARCHIVE_ENTRIES = 100_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 50_000_000_000
MAX_MANIFEST_BYTES = 10_000_000
IMPORT_SAFETY_MARGIN_BYTES = 2_000_000_000
MAX_ARCHIVE_EXPANSION_RATIO = 100
PATH_REFERENCE_COLUMNS = (
    ("embeddings", "source_image"),
    ("embeddings", "crop_path"),
    ("pending_additions", "source_image"),
    ("pending_additions", "crop_path"),
    ("init_faces", "source_image"),
    ("init_faces", "crop_path"),
    ("recognition_details", "image_path"),
)


class BackupError(RuntimeError):
    """Raised when a managed backup operation cannot be completed safely."""


class BackupRestoreError(BackupError):
    def __init__(self, message: str, *, code: str, outcome: str, committed: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.outcome = outcome
        self.committed = committed


@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    created_at: str
    size_bytes: int
    people_count: int
    embedding_count: int
    verified: bool
    database_version: int
    app_version: str
    reason: str | None = None
    operation_id: str | None = None
    format_version: int = 1
    portable: bool = False
    complete: bool = False
    file_count: int = 0
    missing_file_count: int = 0
    reference_count: int = 0
    restorable: bool = False
    integrity_status: str = "UNKNOWN"


class BackupService:
    def __init__(
        self,
        db_path: Path,
        backup_dir: Path,
        retention_limit: int = 10,
        app_version: str = __version__,
        now: Callable[[], datetime] | None = None,
        logger: Callable[[str, object], None] | None = None,
        data_dir: Path | None = None,
        supported_database_version: int | None = None,
        database_key: bytes | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.data_dir = data_dir or db_path.parent
        self.retention_limit = retention_limit
        self.app_version = app_version
        self.supported_database_version = supported_database_version
        self.database_key = database_key
        self._failure_injector = failure_injector
        self._now = now or (lambda: datetime.now().astimezone())
        self._logger = logger
        self._create_lock = threading.RLock()

    def _checkpoint(self, name: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(name)

    def create_backup(
        self,
        reason: str | None = None,
        operation_id: str | None = None,
        protected_backup_ids: Iterable[str] = (),
    ) -> BackupRecord:
        with self._create_lock:
            if operation_id:
                existing = self.find_by_operation(operation_id)
                if existing:
                    return existing
            if not self.db_path.exists():
                raise BackupError(f"Database file not found: {self.db_path}")
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self._require_free_space(self._estimated_live_backup_bytes())
            created_at = self._now()
            backup_id = self._unique_backup_id(created_at, reason)
            target_dir = self._backup_path(backup_id)
            target_db = target_dir / self.db_path.name
            try:
                target_dir.mkdir(parents=False, exist_ok=False)
                self._backup_sqlite(target_db)
                asset_manifest = self._capture_referenced_files(target_db, target_dir)
                metadata = self._metadata(
                    backup_id,
                    created_at,
                    target_db,
                    asset_manifest=asset_manifest,
                    reason=reason,
                    operation_id=operation_id,
                )
                self._write_json_atomic(target_dir / "backup.json", metadata)
                if not self.verify_backup(backup_id):
                    raise BackupError("Portable backup verification failed")
                record = self._record_from_metadata(metadata)
            except Exception as exc:
                shutil.rmtree(target_dir, ignore_errors=True)
                self._log("backup-failed", backup_id=backup_id, error=str(exc))
                if isinstance(exc, BackupError):
                    raise
                raise BackupError(f"Database backup could not be created: {exc}") from exc

            self._log(
                "backup-created",
                backup_id=record.backup_id,
                size_bytes=record.size_bytes,
                file_count=record.file_count,
                missing_file_count=record.missing_file_count,
                complete=record.complete,
                reason=record.reason,
                operation_id=record.operation_id,
            )
            try:
                self.enforce_retention(
                    protected_ids={backup_id, *protected_backup_ids},
                )
            except Exception as exc:  # noqa: BLE001 - retention should not invalidate a verified backup.
                self._log("backup-retention-failed", error=str(exc))
            return record

    def find_by_operation(self, operation_id: str) -> BackupRecord | None:
        operation_id = operation_id.strip()
        if not operation_id:
            return None
        return next(
            (record for record in self.list_backups() if record.operation_id == operation_id),
            None,
        )

    def list_backups(self) -> list[BackupRecord]:
        if not self.backup_dir.exists():
            return []
        records = []
        for item in self.backup_dir.iterdir():
            if not item.is_dir() or not BACKUP_ID_PATTERN.fullmatch(item.name):
                continue
            metadata_path = item / "backup.json"
            if not metadata_path.exists():
                continue
            try:
                records.append(self._record_from_metadata(json.loads(metadata_path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                self._log("backup-metadata-invalid", backup_id=item.name)
        return sorted(records, key=lambda record: record.created_at, reverse=True)

    def verify_backup(self, backup_id: str) -> bool:
        target_dir = self._backup_path(backup_id)
        target_db = self._database_path(backup_id)
        if not target_db.exists():
            raise BackupError(f"Backup database not found: {backup_id}")
        metadata_path = target_dir / "backup.json"
        metadata = None
        if metadata_path.exists():
            try:
                if metadata_path.stat().st_size > MAX_MANIFEST_BYTES:
                    raise BackupError("Backup manifest exceeds the safe size limit")
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise BackupError(f"Backup manifest is invalid: {exc}") from exc
        if metadata and str(metadata.get("backup_id")) != backup_id:
            raise BackupError("Backup manifest identity does not match its directory")
        try:
            with _sqlite_connection(target_db, self.database_key) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        except Exception as exc:
            raise BackupError(f"Backup verification failed: {exc}") from exc
        verified = result == "ok" and not foreign_key_errors
        if verified and metadata and int(metadata.get("format_version", 1)) >= 2:
            verified = self._verify_portable_files(target_dir, target_db, metadata)
        if not verified:
            self._log("backup-verification-failed", backup_id=backup_id, result=result)
        return verified

    def delete_backup(self, backup_id: str) -> None:
        target_dir = self._backup_path(backup_id)
        if not target_dir.exists():
            raise BackupError(f"Backup not found: {backup_id}")
        shutil.rmtree(target_dir)
        self._log("backup-deleted", backup_id=backup_id)

    def enforce_retention(self, protected_ids: set[str] | None = None) -> list[str]:
        if self.retention_limit <= 0:
            return []
        protected_ids = set(protected_ids or set())
        backups = self.list_backups()
        last_verified = next(
            (record for record in backups if record.verified and record.complete),
            None,
        )
        if last_verified is not None:
            protected_ids.add(last_verified.backup_id)
        protected_ids.update(
            record.backup_id
            for record in backups
            if record.reason
            and (record.reason.startswith("before-") or "safety" in record.reason)
        )
        removed = []
        remaining = len(backups)
        for record in reversed(backups):
            if remaining <= self.retention_limit:
                break
            if record.backup_id in protected_ids:
                continue
            self.delete_backup(record.backup_id)
            removed.append(record.backup_id)
            remaining -= 1
            self._log("backup-retention-cleanup", backup_id=record.backup_id)
        return removed

    def export_backup(self, backup_id: str, destination: Path) -> Path:
        """Create one verified, portable archive without loading it into memory."""
        with self._create_lock:
            if not self.verify_backup(backup_id):
                raise BackupError(f"Backup failed verification: {backup_id}")
            backup_path = self._backup_path(backup_id)
            metadata = self._read_metadata(backup_path)
            if int(metadata.get("format_version", 1)) < LEGACY_PORTABLE_BACKUP_FORMAT_VERSION:
                raise BackupError("Legacy database-only backups are not portable")
            destination = destination.with_suffix(PORTABLE_BACKUP_EXTENSION)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                with zipfile.ZipFile(
                    temporary,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    allowZip64=True,
                ) as archive:
                    archive.write(backup_path / "backup.json", "backup.json")
                    archive.write(
                        self._database_path(backup_id),
                        f"database/{self.db_path.name}",
                    )
                    for asset in metadata.get("assets", []):
                        archive_path = self._safe_archive_path(str(asset["archive_path"]))
                        archive.write(backup_path / archive_path, archive_path.as_posix())
                os.replace(temporary, destination)
            except Exception as exc:
                temporary.unlink(missing_ok=True)
                if isinstance(exc, BackupError):
                    raise
                raise BackupError(f"Portable backup export failed: {exc}") from exc
            self._log(
                "backup-exported",
                backup_id=backup_id,
                size_bytes=destination.stat().st_size,
            )
            return destination

    def import_backup(self, archive_path: Path) -> BackupRecord:
        """Validate and install a portable archive as a managed backup."""
        with self._create_lock:
            if not archive_path.exists() or not archive_path.is_file():
                raise BackupError("Portable backup file was not found")
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            imported_root = self.backup_dir / f".import-{uuid.uuid4().hex}"
            imported_root.mkdir(parents=False, exist_ok=False)
            try:
                with zipfile.ZipFile(archive_path, "r", allowZip64=True) as archive:
                    infos = self._validate_archive_entries(archive)
                    expanded_bytes = sum(info.file_size for info in infos.values())
                    expansion_limit = min(
                        MAX_ARCHIVE_UNCOMPRESSED_BYTES,
                        archive_path.stat().st_size * MAX_ARCHIVE_EXPANSION_RATIO,
                    )
                    if expanded_bytes > expansion_limit:
                        raise BackupError("Portable backup compression ratio exceeds the safe limit")
                    self._require_free_space(expanded_bytes + IMPORT_SAFETY_MARGIN_BYTES)
                    manifest_info = infos.get("backup.json")
                    if manifest_info is None:
                        raise BackupError("Portable backup has no manifest")
                    if manifest_info.file_size > MAX_MANIFEST_BYTES:
                        raise BackupError("Portable backup manifest is too large")
                    with archive.open(manifest_info, "r") as source:
                        metadata = json.loads(source.read(MAX_MANIFEST_BYTES + 1).decode("utf-8"))
                    if int(metadata.get("format_version", 0)) not in {
                        LEGACY_PORTABLE_BACKUP_FORMAT_VERSION,
                        PORTABLE_BACKUP_FORMAT_VERSION,
                    }:
                        raise BackupError("Unsupported portable backup format")
                    source_backup_id = str(metadata.get("backup_id") or "unknown")
                    database_entry = f"database/{self.db_path.name}"
                    expected_entries = {"backup.json", database_entry}
                    expected_entries.update(
                        self._safe_archive_path(str(asset["archive_path"])).as_posix()
                        for asset in metadata.get("assets", [])
                    )
                    unexpected = set(infos) - expected_entries
                    missing = expected_entries - set(infos)
                    if unexpected:
                        raise BackupError("Portable backup contains unexpected files")
                    if missing:
                        raise BackupError("Portable backup is missing required files")
                    self._extract_verified_member(
                        archive,
                        infos[database_entry],
                        imported_root / self.db_path.name,
                        metadata["database"],
                    )
                    for asset in metadata.get("assets", []):
                        relative = self._safe_archive_path(str(asset["archive_path"]))
                        self._extract_verified_member(
                            archive,
                            infos[relative.as_posix()],
                            imported_root / relative,
                            asset,
                        )
                created_at = self._now()
                backup_id = self._unique_backup_id(created_at, f"imported-{source_backup_id}")
                metadata["backup_id"] = backup_id
                metadata["imported_from_backup_id"] = source_backup_id
                metadata["imported_at"] = created_at.isoformat(timespec="seconds")
                metadata["verified"] = True
                if int(metadata.get("format_version", 0)) == PORTABLE_BACKUP_FORMAT_VERSION:
                    metadata = _with_manifest_fingerprint(metadata)
                self._write_json_atomic(imported_root / "backup.json", metadata)
                if not self._verify_directory(imported_root, metadata):
                    raise BackupError("Imported portable backup failed verification")
                target = self._backup_path(backup_id)
                os.replace(imported_root, target)
                record = self._record_from_metadata(metadata)
                try:
                    self.enforce_retention(protected_ids={backup_id})
                except Exception as retention_exc:  # noqa: BLE001
                    self._log("backup-retention-failed", error=str(retention_exc))
                self._log(
                    "backup-imported",
                    backup_id=backup_id,
                    source_backup_id=source_backup_id,
                    complete=record.complete,
                )
                return record
            except Exception as exc:
                shutil.rmtree(imported_root, ignore_errors=True)
                self._log("backup-import-failed", error=str(exc))
                if isinstance(exc, BackupError):
                    raise
                if isinstance(exc, (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError)):
                    raise BackupError(f"Portable backup is invalid: {exc}") from exc
                raise BackupError(f"Portable backup import failed: {exc}") from exc

    def export_encrypted_backup(
        self,
        backup_id: str,
        destination: Path,
        passphrase: str,
    ) -> Path:
        """Export a portable backup protected by authenticated encryption."""
        with self._create_lock:
            if not destination.name.lower().endswith(ENCRYPTED_BACKUP_EXTENSION):
                destination = Path(f"{destination}{ENCRYPTED_BACKUP_EXTENSION}")
            plain = destination.parent / f".{uuid.uuid4().hex}.sfbackup"
            try:
                exported = self.export_backup(backup_id, plain)
                encrypt_file(exported, destination, passphrase)
            except Exception as exc:
                destination.unlink(missing_ok=True)
                if isinstance(exc, BackupError):
                    raise
                if isinstance(exc, BackupEncryptionError):
                    raise BackupError(str(exc)) from exc
                raise BackupError(f"Encrypted backup export failed: {exc}") from exc
            finally:
                plain.unlink(missing_ok=True)
            self._log(
                "backup-encrypted-exported",
                backup_id=backup_id,
                size_bytes=destination.stat().st_size,
            )
            return destination

    def import_encrypted_backup(
        self,
        archive_path: Path,
        passphrase: str,
    ) -> BackupRecord:
        """Authenticate, decrypt, validate, and install an encrypted export."""
        with self._create_lock:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            plain = self.backup_dir / f".decrypt-{uuid.uuid4().hex}.sfbackup"
            try:
                decrypt_file(archive_path, plain, passphrase)
                return self.import_backup(plain)
            except BackupEncryptionError as exc:
                raise BackupError(str(exc)) from exc
            finally:
                plain.unlink(missing_ok=True)

    def restore_backup(
        self,
        backup_id: str,
        operation_id: str,
        reload_callback: Callable[[], None] | None = None,
        *,
        actor: dict | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        """Prove a staged candidate, then install it or restore the old timeline."""
        with self._create_lock:
            operation_id = self._validate_operation_id(operation_id)
            receipt_path = self._restore_receipt_path(backup_id, operation_id)
            if receipt_path.exists():
                return json.loads(receipt_path.read_text(encoding="utf-8"))
            try:
                if not self.verify_backup(backup_id):
                    raise BackupError(f"Backup failed verification: {backup_id}")
            except BackupError as exc:
                raise BackupRestoreError(
                    str(exc), code="restore_refused", outcome="REFUSED",
                ) from exc
            record = next(
                (item for item in self.list_backups() if item.backup_id == backup_id),
                None,
            )
            if record is None:
                raise BackupRestoreError(
                    f"Backup metadata not found: {backup_id}",
                    code="restore_refused", outcome="REFUSED",
                )
            if self.supported_database_version is not None and (
                record.database_version > self.supported_database_version
            ):
                raise BackupRestoreError(
                    "Backup database is newer than this SentriFace version supports",
                    code="incompatible_schema", outcome="REFUSED",
                )
            if not record.complete or not record.restorable:
                raise BackupRestoreError(
                    "This backup is incomplete or failed restore-eligibility validation",
                    code="backup_not_restorable", outcome="REFUSED",
                )
            metadata = self._read_metadata(self._backup_path(backup_id))
            manifest_fingerprint = str(
                metadata.get("manifest_fingerprint")
                or _canonical_sha256(metadata)
            )

            from sentriface.storage.sqlite_store import SQLiteIdentityStore

            live_store = SQLiteIdentityStore(
                self.db_path,
                backup_dir=self.backup_dir,
                backup_retention_limit=self.retention_limit,
                database_key=self.database_key,
            )
            existing = live_store.get_operation(operation_id)
            if existing is not None:
                if (
                    existing.get("operation_type") == "backup.restore"
                    and existing.get("status") == "COMMITTED"
                    and existing.get("details", {}).get("backup_id") == backup_id
                ):
                    history = existing.get("status_history") or []
                    committed = history[-1].get("details", {}) if history else {}
                    return {"committed": True, "outcome": "COMMITTED", **committed}
                raise BackupRestoreError(
                    "Restore operation ID is stale or conflicts with an existing operation",
                    code="operation_conflict", outcome="REFUSED",
                )
            with _sqlite_connection(self._database_path(backup_id), self.database_key) as conn:
                operation_id_exists = (
                    _table_has_column(conn, "operation_journal", "operation_id")
                    and conn.execute(
                        "SELECT 1 FROM operation_journal WHERE operation_id = ?",
                        (operation_id,),
                    ).fetchone() is not None
                )
                if operation_id_exists:
                    raise BackupRestoreError(
                        "Restore operation ID conflicts with source backup history",
                        code="operation_conflict", outcome="REFUSED",
                    )

            self._require_free_space(
                self._estimated_live_backup_bytes()
                + max(record.size_bytes * 2, 64 * 1024 * 1024)
            )
            restore_token = uuid.uuid4().hex
            staging_root = self.data_dir / f".restore-{restore_token}"
            final_media_root = self.data_dir / "restored-media" / restore_token
            staging_media = staging_root / "media"
            staged_db = staging_root / self.db_path.name
            intent_path = self._restore_intent_path(operation_id)
            installed_media = False
            database_replaced = False
            live_started = False
            safety: BackupRecord | None = None
            try:
                live_store.begin_operation(
                    "backup.restore",
                    operation_id=operation_id,
                    actor=actor,
                    source="backup-restore-coordinator",
                    context={"manifest_version": int(metadata.get("format_version", 0))},
                    affected_entities=[
                        {"entity_type": "backup", "entity_id": backup_id},
                        {"entity_type": "database", "entity_id": self.db_path.name},
                    ],
                    details={
                        "backup_id": backup_id,
                        "manifest_fingerprint": manifest_fingerprint,
                        "source_schema": record.database_version,
                        "reason": _bounded_text(reason, 500),
                    },
                )
                live_started = True
                self._write_json_atomic(intent_path, {
                    "version": 1,
                    "operation_id": operation_id,
                    "backup_id": backup_id,
                    "manifest_fingerprint": manifest_fingerprint,
                    "state": "STARTED",
                    "restore_token": restore_token,
                    "final_media_root": str(final_media_root),
                })
                self._checkpoint("before_safety_backup")
                safety = self.create_backup(
                    reason=f"before-restore-{backup_id}",
                    operation_id=f"restore-safety-{operation_id}",
                    protected_backup_ids={backup_id},
                )
                self._checkpoint("after_safety_backup")
                if not safety.complete or not safety.restorable or not self.verify_backup(safety.backup_id):
                    raise BackupError("The current live state could not produce a complete safety backup")
                intent = json.loads(intent_path.read_text(encoding="utf-8"))
                self._write_json_atomic(intent_path, {
                    **intent,
                    "state": "SAFETY_BACKUP_READY",
                    "safety_backup_id": safety.backup_id,
                })

                self._checkpoint("before_staging")
                staging_media.mkdir(parents=True, exist_ok=False)
                shutil.copy2(self._database_path(backup_id), staged_db)
                self._checkpoint("after_database_staging")
                from sentriface.storage.sqlite_store import migrate_staged_database

                self._checkpoint("before_migration")
                source_schema, final_schema = migrate_staged_database(
                    staged_db, database_key=self.database_key,
                )
                self._checkpoint("after_migration")
                restored_paths = self._stage_restore_assets(
                    self._backup_path(backup_id),
                    metadata,
                    staging_media,
                    final_media_root,
                )
                self._checkpoint("after_media_staging")
                self._checkpoint("before_media_rewrite")
                self._rewrite_database_paths(staged_db, metadata, restored_paths)
                self._checkpoint("after_media_rewrite")
                self._verify_sqlite_file(staged_db)
                self._verify_rewritten_media_closure(
                    staged_db, metadata, restored_paths, staging_media,
                )

                staged_store = SQLiteIdentityStore(
                    staged_db,
                    backup_dir=staging_root / "migration-backups",
                    backup_retention_limit=1,
                    database_key=self.database_key,
                )
                from sentriface.graph_service import GlobalIdentityGraphService

                graph_operation_id = f"{operation_id}:graph-rebuild"
                self._checkpoint("before_graph_rebuild")
                graph_result = GlobalIdentityGraphService(staged_store).rebuild_projection(
                    graph_operation_id,
                    source="backup-restore-coordinator",
                    actor=actor,
                    reason="P12 staged restore projection rebuild",
                    context={"restore_operation_id": operation_id},
                )
                self._checkpoint("after_graph_rebuild")
                self._checkpoint("before_staged_integrity")
                staged_report = self._require_clean_integrity(staged_db)
                self._checkpoint("after_staged_integrity")
                self._verify_rewritten_media_closure(
                    staged_db, metadata, restored_paths, staging_media,
                )
                media_fingerprint = _canonical_sha256([
                    (asset.get("archive_path"), asset.get("sha256"), asset.get("size_bytes"))
                    for asset in metadata.get("assets", [])
                ])
                candidate_database_fingerprint = _sha256_file(staged_db)
                staged_store.begin_operation(
                    "backup.restore",
                    operation_id=operation_id,
                    actor=actor,
                    source="backup-restore-coordinator",
                    context={"manifest_version": int(metadata.get("format_version", 0))},
                    affected_entities=[
                        {"entity_type": "backup", "entity_id": backup_id},
                        {"entity_type": "database", "entity_id": self.db_path.name},
                        {"entity_type": "graph_projection", "entity_id": "graph_connections"},
                    ],
                    details={
                        "backup_id": backup_id,
                        "manifest_fingerprint": manifest_fingerprint,
                        "source_schema": source_schema,
                        "final_schema": final_schema,
                        "safety_backup_id": safety.backup_id,
                        "reason": _bounded_text(reason, 500),
                    },
                )
                journal_result: dict[str, object] = {
                    "restored": True,
                    "backup_id": backup_id,
                    "operation_id": operation_id,
                    "safety_backup_id": safety.backup_id,
                    "manifest_fingerprint": manifest_fingerprint,
                    "source_schema": source_schema,
                    "final_schema": final_schema,
                    "candidate_database_fingerprint": candidate_database_fingerprint,
                    "media_fingerprint": media_fingerprint,
                    "graph_changed": bool(graph_result.get("changed")),
                    "graph_revision": graph_result.get("revision_after"),
                    "staged_integrity_fingerprint": _integrity_report_fingerprint(staged_report),
                    "restored_files": len(metadata.get("assets", [])),
                    "missing_files": 0,
                    "complete": True,
                }
                staged_store.mark_operation_committed(operation_id, journal_result)
                self._require_clean_integrity(staged_db)
                self._checkpoint("before_media_install")
                final_media_root.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging_media, final_media_root)
                installed_media = True
                self._checkpoint("after_media_install")
                intent = json.loads(intent_path.read_text(encoding="utf-8"))
                self._write_json_atomic(intent_path, {**intent, "state": "READY_TO_SWAP"})
                self._checkpoint("before_database_swap")
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._replace_live_database(staged_db)
                database_replaced = True
                self._checkpoint("after_database_swap")
                self._checkpoint("before_reload")
                if reload_callback:
                    reload_callback()
                self._checkpoint("after_reload")
                self._checkpoint("before_final_integrity")
                final_report = self._require_clean_integrity(self.db_path)
                self._verify_live_media_closure(self.db_path)
                self._checkpoint("after_final_integrity")
                result: dict[str, object] = {
                    **journal_result,
                    "committed": True,
                    "outcome": "COMMITTED",
                    "final_integrity_fingerprint": _integrity_report_fingerprint(final_report),
                    "final_database_fingerprint": _sha256_file(self.db_path),
                    "restored_at": self._now().isoformat(timespec="seconds"),
                }
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.enforce_retention(protected_ids={backup_id, safety.backup_id})
                except Exception as retention_exc:  # noqa: BLE001
                    self._log("backup-retention-failed", error=str(retention_exc))
                self._checkpoint("before_receipt")
                self._write_json_atomic(receipt_path, result)
                intent_path.unlink(missing_ok=True)
                self._log("backup-restored", **result)
                return result
            except Exception as exc:
                rollback_error = None
                if database_replaced:
                    try:
                        rollback_temp = staging_root / f"rollback-{self.db_path.name}"
                        if safety is None:
                            raise BackupError("Restore safety backup is unavailable")
                        shutil.copy2(self._database_path(safety.backup_id), rollback_temp)
                        self._replace_live_database(rollback_temp)
                        if reload_callback:
                            reload_callback()
                    except Exception as rollback_exc:  # noqa: BLE001 - report both failures.
                        rollback_error = rollback_exc
                if installed_media:
                    shutil.rmtree(final_media_root, ignore_errors=True)
                if live_started and rollback_error is None:
                    try:
                        surviving_store = SQLiteIdentityStore(
                            self.db_path,
                            backup_dir=self.backup_dir,
                            backup_retention_limit=self.retention_limit,
                            database_key=self.database_key,
                        )
                        operation = surviving_store.get_operation(operation_id)
                        if operation is not None and operation.get("status") == "STARTED":
                            surviving_store.mark_operation_failed(operation_id, {
                                "backup_id": backup_id,
                                "manifest_fingerprint": manifest_fingerprint,
                                "safety_backup_id": safety.backup_id if safety else None,
                                "rolled_back": database_replaced,
                                "error_type": type(exc).__name__,
                                "error": _bounded_text(str(exc), 500),
                            })
                    except Exception as journal_exc:  # noqa: BLE001
                        rollback_error = journal_exc
                details = str(exc)
                if rollback_error is not None:
                    details = f"{details}; automatic rollback failed: {rollback_error}"
                self._log(
                    "backup-restore-failed",
                    backup_id=backup_id,
                    safety_backup_id=safety.backup_id if safety else None,
                    error=details,
                )
                if rollback_error is not None:
                    raise BackupRestoreError(
                        f"Backup restore entered an indeterminate state: {details}",
                        code="restore_indeterminate",
                        outcome="COMMITTED_POSTCHECK_FAILED" if database_replaced else "ROLLBACK_FAILED",
                        committed=database_replaced,
                    ) from exc
                intent_path.unlink(missing_ok=True)
                raise BackupRestoreError(
                    f"Backup restore was rolled back safely: {details}",
                    code="restore_rolled_back",
                    outcome="ROLLED_BACK",
                    committed=False,
                ) from exc
            finally:
                shutil.rmtree(staging_root, ignore_errors=True)

    def _require_clean_integrity(self, database_path: Path):
        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            database_path, database_key=self.database_key,
        ).run()
        if report.status != "PASS" or report.findings_truncated:
            invariant_ids = sorted({item.invariant_id for item in report.findings})
            raise BackupError(
                "Restore candidate failed P11-A integrity validation"
                + (f": {', '.join(invariant_ids[:20])}" if invariant_ids else "")
            )
        return report

    def _verify_rewritten_media_closure(
        self,
        database_path: Path,
        metadata: dict[str, object],
        restored_paths: dict[str, str],
        staging_media: Path,
    ) -> None:
        actual = self._database_media_references(database_path)
        allowed_paths = set(restored_paths.values())
        if int(metadata.get("format_version", 0)) == PORTABLE_BACKUP_FORMAT_VERSION:
            expected = {
                _binding_key(item.get("registry_id"), item.get("row_identity"))
                for item in metadata.get("path_references", [])
                if isinstance(item, dict)
            }
            actual_keys = {
                _binding_key(item["registry_id"], item["row_identity"])
                for item in actual
            }
            if expected != actual_keys:
                raise BackupError("Staged database media bindings changed during restore")
        for item in actual:
            rewritten = str(item["path"])
            if rewritten not in allowed_paths:
                raise BackupError("Staged database contains an unrewritten media path")
            staged_path = staging_media / Path(rewritten).name
            if not staged_path.is_file():
                raise BackupError("Staged database references unavailable media")
            try:
                authenticate_protected_file(staged_path, self.database_key)
            except ProtectedFileError as exc:
                raise BackupError(f"Staged media failed authentication: {exc}") from exc

    def _verify_live_media_closure(self, database_path: Path) -> None:
        for item in self._database_media_references(database_path):
            path = Path(str(item["path"]))
            if not path.is_file():
                raise BackupError("Installed database references unavailable media")
            try:
                authenticate_protected_file(path, self.database_key)
            except ProtectedFileError as exc:
                raise BackupError(f"Installed media failed authentication: {exc}") from exc

    def _restore_intent_path(self, operation_id: str) -> Path:
        return self.data_dir / ".restore-intents" / f"{operation_id}.json"

    def recover_interrupted_restores(self) -> list[dict[str, object]]:
        """Resolve crash sidecars by inspecting the surviving journal timeline."""
        intent_root = self.data_dir / ".restore-intents"
        if not intent_root.is_dir():
            return []
        from sentriface.storage.sqlite_store import SQLiteIdentityStore

        store = SQLiteIdentityStore(
            self.db_path,
            backup_dir=self.backup_dir,
            backup_retention_limit=self.retention_limit,
            database_key=self.database_key,
        )
        outcomes: list[dict[str, object]] = []
        for path in sorted(intent_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                operation_id = self._validate_operation_id(str(payload["operation_id"]))
                backup_id = str(payload["backup_id"])
                operation = store.get_operation(operation_id)
                final_media_root = Path(str(payload.get("final_media_root") or ""))
                if operation and operation.get("operation_type") == "backup.restore" and operation.get("status") == "COMMITTED":
                    self._require_clean_integrity(self.db_path)
                    self._verify_live_media_closure(self.db_path)
                    history = operation.get("status_history") or []
                    result = history[-1].get("details", {}) if history else {}
                    result = {"committed": True, "outcome": "COMMITTED", **result}
                    receipt = self._restore_receipt_path(backup_id, operation_id)
                    if not receipt.exists():
                        self._write_json_atomic(receipt, result)
                    outcomes.append({"operation_id": operation_id, "outcome": "COMMITTED"})
                else:
                    if operation and operation.get("status") == "STARTED":
                        store.mark_operation_failed(operation_id, {
                            "backup_id": backup_id,
                            "rolled_back": False,
                            "error": "Interrupted before database installation",
                        })
                    if final_media_root.is_dir():
                        shutil.rmtree(final_media_root, ignore_errors=True)
                    outcomes.append({"operation_id": operation_id, "outcome": "FAILED"})
                path.unlink(missing_ok=True)
            except Exception as exc:  # Keep the sidecar for explicit follow-up.
                self._log("backup-restore-recovery-failed", path=path.name, error=str(exc))
                outcomes.append({"intent": path.name, "outcome": "UNRESOLVED"})
        try:
            intent_root.rmdir()
        except OSError:
            pass
        return outcomes

    def _estimated_live_backup_bytes(self) -> int:
        estimate = self.db_path.stat().st_size
        try:
            references = {
                str(item["path"]) for item in self._database_media_references(self.db_path)
            }
        except (BackupError, sqlite3.Error):
            references = set()
        for raw_path in references:
            path = Path(raw_path)
            try:
                if path.is_file():
                    estimate += path.stat().st_size
            except OSError:
                continue
        return max(int(estimate * 1.15), estimate + 64 * 1024 * 1024)

    def require_import_upload_space(self, upload_bytes: int) -> None:
        """Reject before upload unless encrypted, decrypted, and expanded copies fit."""
        if upload_bytes <= 0:
            raise BackupError("Backup upload size must be positive")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        required = (
            upload_bytes * 2
            + min(MAX_ARCHIVE_UNCOMPRESSED_BYTES, upload_bytes * MAX_ARCHIVE_EXPANSION_RATIO)
            + IMPORT_SAFETY_MARGIN_BYTES
        )
        self._require_free_space(required)

    def _require_free_space(self, required_bytes: int) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        available = shutil.disk_usage(self.backup_dir).free
        if available < required_bytes:
            raise BackupError(
                f"Not enough free space for a safe backup operation: "
                f"need about {required_bytes} bytes, have {available} bytes"
            )
    def _backup_sqlite(self, target_db: Path) -> None:
        with _sqlite_connection(self.db_path, self.database_key) as source:
            with _sqlite_connection(target_db, self.database_key) as destination:
                source.backup(destination)

    def _capture_referenced_files(
        self,
        target_db: Path,
        target_dir: Path,
    ) -> dict[str, object]:
        references = self._database_media_references(target_db)
        assets_by_hash: dict[str, dict[str, object]] = {}
        path_references: list[dict[str, object]] = []
        missing_references: list[dict[str, object]] = []
        files_root = target_dir / "files"
        captured_paths: dict[str, dict[str, object] | None] = {}
        for reference in references:
            original_path = str(reference["path"])
            source = self._resolve_reference_path(original_path)
            if source is None:
                missing_references.append(
                    {
                        "registry_id": reference["registry_id"],
                        "row_identity": reference["row_identity"],
                        "media_class": reference["media_class"],
                        "rewrite_behavior": reference["rewrite_behavior"],
                        "protected_media": reference["protected_media"],
                        "path_fingerprint": _text_sha256(original_path),
                        "reason": "not_found_or_not_a_file",
                    }
                )
                continue
            existing = captured_paths.get(original_path)
            if original_path not in captured_paths:
                digest, size_bytes, temporary, protected, plaintext_size = self._copy_and_hash(
                    source, files_root,
                )
                existing = assets_by_hash.get(digest)
                if existing is None:
                    suffix = _safe_asset_suffix(source.suffix)
                    relative = PurePosixPath("files") / digest[:2] / f"{digest}{suffix}"
                    destination = target_dir / Path(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        temporary.unlink(missing_ok=True)
                    else:
                        os.replace(temporary, destination)
                    existing = {
                        "archive_path": relative.as_posix(),
                        "sha256": digest,
                        "size_bytes": size_bytes,
                        "protected": protected,
                        "plaintext_size": plaintext_size,
                    }
                    assets_by_hash[digest] = existing
                else:
                    temporary.unlink(missing_ok=True)
                captured_paths[original_path] = existing
            if existing is None:
                raise BackupError("Media capture state is incomplete")
            path_references.append(
                {
                    "registry_id": reference["registry_id"],
                    "row_identity": reference["row_identity"],
                    "media_class": reference["media_class"],
                    "rewrite_behavior": reference["rewrite_behavior"],
                    "protected_media": reference["protected_media"],
                    "path_fingerprint": _text_sha256(original_path),
                    "archive_path": existing["archive_path"],
                }
            )
        assets = sorted(
            assets_by_hash.values(),
            key=lambda asset: str(asset["archive_path"]),
        )
        return {
            "assets": assets,
            "path_references": sorted(
                path_references,
                key=lambda item: (
                    str(item["registry_id"]),
                    json.dumps(item["row_identity"], sort_keys=True),
                ),
            ),
            "missing_references": sorted(
                missing_references,
                key=lambda item: (
                    str(item["registry_id"]),
                    json.dumps(item["row_identity"], sort_keys=True),
                ),
            ),
            "reference_count": len(path_references) + len(missing_references),
            "asset_size_bytes": sum(int(asset["size_bytes"]) for asset in assets),
        }

    def _database_media_references(self, database_path: Path) -> list[dict[str, object]]:
        references: list[dict[str, object]] = []
        with _sqlite_connection(database_path, self.database_key) as conn:
            for spec, identity, path in iter_media_references(conn):
                references.append({
                    "registry_id": spec.registry_id,
                    "row_identity": stable_identity(spec, identity),
                    "media_class": spec.media_class,
                    "rewrite_behavior": spec.rewrite_behavior,
                    "protected_media": spec.protected_media,
                    "path": path,
                })
        return references

    def _database_path_references(
        self,
        database_path: Path,
    ) -> dict[str, list[dict[str, str]]]:
        references: dict[str, list[dict[str, str]]] = {}
        with _sqlite_connection(database_path, self.database_key) as conn:
            for table, column in PATH_REFERENCE_COLUMNS:
                if not _table_has_column(conn, table, column):
                    continue
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT "{column}"
                    FROM "{table}"
                    WHERE "{column}" IS NOT NULL AND TRIM("{column}") != ''
                    """
                ).fetchall()
                for row in rows:
                    value = str(row[0])
                    references.setdefault(value, []).append(
                        {"table": table, "column": column}
                    )
        return references

    def _resolve_reference_path(self, raw_path: str) -> Path | None:
        path = Path(raw_path).expanduser()
        candidates = [path] if path.is_absolute() else [
            path,
            self.data_dir / path,
            self.db_path.parent / path,
        ]
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if resolved.is_file():
                return resolved
        return None

    def _copy_and_hash(
        self,
        source: Path,
        files_root: Path,
    ) -> tuple[str, int, Path, bool, int]:
        files_root.mkdir(parents=True, exist_ok=True)
        source_before = source.stat()
        temporary = files_root / f".asset-{uuid.uuid4().hex}.tmp"
        try:
            copy_into_protected_storage(source, temporary, self.database_key)
            source_after = source.stat()
            if (
                source_before.st_dev != source_after.st_dev
                or source_before.st_ino != source_after.st_ino
                or source_before.st_size != source_after.st_size
                or source_before.st_mtime_ns != source_after.st_mtime_ns
            ):
                raise BackupError(f"Referenced file changed during backup: {source}")
            protected, plaintext_size = authenticate_protected_file(
                temporary, self.database_key,
            )
            return (
                _sha256_file(temporary),
                temporary.stat().st_size,
                temporary,
                protected,
                plaintext_size,
            )
        except ProtectedFileError as exc:
            temporary.unlink(missing_ok=True)
            raise BackupError(f"Referenced media failed authentication: {exc}") from exc
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    def _metadata(
        self,
        backup_id: str,
        created_at: datetime,
        target_db: Path,
        asset_manifest: dict[str, object] | None = None,
        reason: str | None = None,
        operation_id: str | None = None,
    ) -> dict[str, object]:
        asset_manifest = asset_manifest or {
            "assets": [],
            "path_references": [],
            "missing_references": [],
            "reference_count": 0,
            "asset_size_bytes": 0,
        }
        with _sqlite_connection(target_db, self.database_key) as conn:
            database_version = conn.execute("PRAGMA user_version").fetchone()[0]
            # Pre-migration snapshots can predate either table. Missing tables
            # represent zero records; they do not make an otherwise valid backup unsafe.
            people_count = _table_row_count(conn, "persons")
            embedding_count = _table_row_count(conn, "embeddings")
            journal = _journal_fingerprint(conn)
        database_size_bytes = target_db.stat().st_size
        database_sha256 = _sha256_file(target_db)
        assets = list(asset_manifest["assets"])
        missing_references = list(asset_manifest["missing_references"])
        size_bytes = database_size_bytes + int(asset_manifest["asset_size_bytes"])
        integrity = self._integrity_metadata(target_db, int(database_version))
        complete = not missing_references
        restorable = complete and integrity["restore_eligible"]
        metadata = {
            "backup_id": backup_id,
            "created_at": created_at.isoformat(timespec="seconds"),
            "format_version": PORTABLE_BACKUP_FORMAT_VERSION,
            "manifest_version": PORTABLE_BACKUP_FORMAT_VERSION,
            "portable": True,
            "app_version": self.app_version,
            "database_version": database_version,
            "minimum_supported_database_version": 0,
            "storage_key_id": _storage_key_id(self.database_key),
            "people_count": people_count,
            "embedding_count": embedding_count,
            "database_size_bytes": database_size_bytes,
            "database": {
                "archive_path": f"database/{self.db_path.name}",
                "local_name": self.db_path.name,
                "sha256": database_sha256,
                "size_bytes": database_size_bytes,
            },
            "assets": assets,
            "path_references": asset_manifest["path_references"],
            "missing_references": missing_references,
            "file_count": len(assets),
            "missing_file_count": len(missing_references),
            "reference_count": int(asset_manifest["reference_count"]),
            "complete": complete,
            "media_closure_status": "COMPLETE" if complete else "INCOMPLETE",
            "restorable": restorable,
            "integrity": integrity,
            "journal": journal,
            "size_bytes": size_bytes,
            "verified": True,
            "reason": reason,
            "operation_id": operation_id,
        }
        return _with_manifest_fingerprint(metadata)

    def _integrity_metadata(
        self,
        database_path: Path,
        database_version: int,
    ) -> dict[str, object]:
        supported = self.supported_database_version
        if supported is None:
            try:
                from sentriface.storage.sqlite_store import SCHEMA_VERSION

                supported = SCHEMA_VERSION
            except ImportError:
                supported = database_version
        if database_version != supported:
            payload = {
                "status": "PENDING_MIGRATION" if database_version < supported else "UNSUPPORTED_NEWER_SCHEMA",
                "schema_version": database_version,
                "graph_revision": None,
                "finding_count": 0,
                "blocking_invariant_ids": [],
                "findings_truncated": False,
                "restore_eligible": database_version < supported,
            }
            return {**payload, "fingerprint": _canonical_sha256(payload)}

        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            database_path, database_key=self.database_key,
        ).run()
        blocking = sorted({
            finding.invariant_id
            for finding in report.findings
            if finding.severity.value in {"ERROR", "CRITICAL"}
            and finding.invariant_id != "P11-GRAPH-001"
        })
        graph_drift = any(
            finding.invariant_id == "P11-GRAPH-001" for finding in report.findings
        )
        status = (
            "BLOCKED" if blocking or report.findings_truncated
            else "PROJECTION_DRIFT" if graph_drift
            else "PASS"
        )
        report_facts = {
            "status": report.status,
            "schema_version": report.schema_version,
            "graph_revision": report.graph_revision,
            "findings_truncated": report.findings_truncated,
            "findings": [
                {
                    "invariant_id": item.invariant_id,
                    "severity": item.severity.value,
                    "domain": item.domain,
                    "entity_ids": list(item.entity_ids),
                    "evidence": list(item.evidence),
                }
                for item in report.findings
            ],
        }
        payload = {
            "status": status,
            "schema_version": report.schema_version,
            "graph_revision": report.graph_revision,
            "finding_count": len(report.findings),
            "blocking_invariant_ids": blocking,
            "findings_truncated": report.findings_truncated,
            "restore_eligible": not blocking and not report.findings_truncated,
            "report_fingerprint": _canonical_sha256(report_facts),
        }
        return {**payload, "fingerprint": _canonical_sha256(payload)}

    def _record_from_metadata(self, metadata: dict[str, object]) -> BackupRecord:
        size_bytes = int(metadata.get("size_bytes") or metadata["database_size_bytes"])
        format_version = int(metadata.get("format_version", 1))
        return BackupRecord(
            backup_id=str(metadata["backup_id"]),
            created_at=str(metadata["created_at"]),
            size_bytes=size_bytes,
            people_count=int(metadata["people_count"]),
            embedding_count=int(metadata["embedding_count"]),
            verified=bool(metadata.get("verified", True)),
            database_version=int(metadata["database_version"]),
            app_version=str(metadata["app_version"]),
            reason=str(metadata["reason"]) if metadata.get("reason") else None,
            operation_id=str(metadata["operation_id"]) if metadata.get("operation_id") else None,
            format_version=format_version,
            portable=bool(metadata.get("portable", format_version >= 2)),
            complete=bool(metadata.get("complete", False)),
            file_count=int(metadata.get("file_count", 0)),
            missing_file_count=int(metadata.get("missing_file_count", 0)),
            reference_count=int(metadata.get("reference_count", 0)),
            restorable=bool(metadata.get("restorable", metadata.get("complete", False))),
            integrity_status=str(
                (metadata.get("integrity") or {}).get("status", "LEGACY")
                if isinstance(metadata.get("integrity"), dict)
                else "LEGACY"
            ),
        )

    def _read_metadata(self, backup_path: Path) -> dict[str, object]:
        metadata_path = backup_path / "backup.json"
        try:
            if metadata_path.stat().st_size > MAX_MANIFEST_BYTES:
                raise BackupError("Backup manifest exceeds the safe size limit")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, BackupError):
                raise
            raise BackupError(f"Backup manifest is invalid: {exc}") from exc
        if not isinstance(metadata, dict):
            raise BackupError("Backup manifest must be an object")
        return metadata

    def _verify_portable_files(
        self,
        target_dir: Path,
        target_db: Path,
        metadata: dict[str, object],
    ) -> bool:
        return self._verify_directory(target_dir, metadata, database_path=target_db)

    def _verify_directory(
        self,
        target_dir: Path,
        metadata: dict[str, object],
        database_path: Path | None = None,
    ) -> bool:
        format_version = int(metadata.get("format_version", 0))
        if format_version == PORTABLE_BACKUP_FORMAT_VERSION:
            return self._verify_directory_v3(
                target_dir, metadata, database_path=database_path,
            )
        if format_version == LEGACY_PORTABLE_BACKUP_FORMAT_VERSION:
            return self._verify_directory_v2(
                target_dir, metadata, database_path=database_path,
            )
        raise BackupError("Unsupported portable backup format")

    def _verify_directory_v2(
        self,
        target_dir: Path,
        metadata: dict[str, object],
        database_path: Path | None = None,
    ) -> bool:
        if int(metadata.get("format_version", 0)) != LEGACY_PORTABLE_BACKUP_FORMAT_VERSION:
            raise BackupError("Unsupported portable backup format")
        database = metadata.get("database")
        if not isinstance(database, dict):
            raise BackupError("Portable backup database manifest is missing")
        database_path = database_path or target_dir / self.db_path.name
        self._verify_file_entry(database_path, database)
        self._verify_sqlite_file(database_path)
        with _sqlite_connection(database_path, self.database_key) as conn:
            actual_database_version = int(
                conn.execute("PRAGMA user_version").fetchone()[0]
            )
            actual_people_count = _table_row_count(conn, "persons")
            actual_embedding_count = _table_row_count(conn, "embeddings")
        if int(metadata.get("database_version", -1)) != actual_database_version:
            raise BackupError("Portable backup database version manifest is invalid")
        if int(metadata.get("people_count", -1)) != actual_people_count:
            raise BackupError("Portable backup people count manifest is invalid")
        if int(metadata.get("embedding_count", -1)) != actual_embedding_count:
            raise BackupError("Portable backup embedding count manifest is invalid")
        assets = metadata.get("assets")
        references = metadata.get("path_references")
        missing_references = metadata.get("missing_references")
        if not isinstance(assets, list) or not isinstance(references, list):
            raise BackupError("Portable backup file manifest is invalid")
        if not isinstance(missing_references, list):
            raise BackupError("Portable backup missing-file manifest is invalid")
        declared_paths: set[str] = set()
        for asset in assets:
            if not isinstance(asset, dict):
                raise BackupError("Portable backup asset entry is invalid")
            relative = self._safe_archive_path(str(asset.get("archive_path", "")))
            if not relative.parts or relative.parts[0] != "files":
                raise BackupError("Portable backup asset is outside the files directory")
            normalized = relative.as_posix()
            if normalized in declared_paths:
                raise BackupError("Portable backup declares a duplicate asset path")
            declared_paths.add(normalized)
            self._verify_file_entry(target_dir / Path(*relative.parts), asset)
        for reference in references:
            if not isinstance(reference, dict):
                raise BackupError("Portable backup path reference is invalid")
            relative = self._safe_archive_path(str(reference.get("archive_path", "")))
            if relative.as_posix() not in declared_paths:
                raise BackupError("Portable backup path reference has no asset")
            locations = reference.get("locations")
            if not isinstance(locations, list) or not locations:
                raise BackupError("Portable backup path reference has no database location")
            for location in locations:
                if (
                    not isinstance(location, dict)
                    or (location.get("table"), location.get("column"))
                    not in PATH_REFERENCE_COLUMNS
                ):
                    raise BackupError("Portable backup path reference location is unsafe")
        actual_references = self._database_path_references(database_path)
        declared_reference_paths = {
            str(reference.get("original_path", ""))
            for reference in references
        }
        declared_missing_paths = {
            str(reference.get("original_path", ""))
            for reference in missing_references
            if isinstance(reference, dict)
        }
        if declared_reference_paths & declared_missing_paths:
            raise BackupError("Portable backup path is both stored and missing")
        if declared_reference_paths | declared_missing_paths != set(actual_references):
            raise BackupError("Portable backup path manifest does not match its database")
        for reference in references:
            original_path = str(reference["original_path"])
            declared_locations = {
                (str(location["table"]), str(location["column"]))
                for location in reference["locations"]
            }
            actual_locations = {
                (str(location["table"]), str(location["column"]))
                for location in actual_references[original_path]
            }
            if declared_locations != actual_locations:
                raise BackupError(
                    "Portable backup path locations do not match its database"
                )
        if int(metadata.get("reference_count", -1)) != len(actual_references):
            raise BackupError("Portable backup reference count is invalid")
        expected_size = int(database["size_bytes"]) + sum(
            int(asset["size_bytes"]) for asset in assets
        )
        if int(metadata.get("size_bytes", -1)) != expected_size:
            raise BackupError("Portable backup size manifest does not match its files")
        if int(metadata.get("file_count", -1)) != len(assets):
            raise BackupError("Portable backup file count is invalid")
        if int(metadata.get("missing_file_count", -1)) != len(missing_references):
            raise BackupError("Portable backup missing-file count is invalid")
        if bool(metadata.get("complete")) != (len(missing_references) == 0):
            raise BackupError("Portable backup completeness flag is invalid")
        self._verify_legacy_v2_media_closure(database_path, metadata)
        return True

    def _verify_directory_v3(
        self,
        target_dir: Path,
        metadata: dict[str, object],
        database_path: Path | None = None,
    ) -> bool:
        if int(metadata.get("manifest_version", 0)) != PORTABLE_BACKUP_FORMAT_VERSION:
            raise BackupError("Portable backup manifest version is unsupported")
        expected_fingerprint = str(metadata.get("manifest_fingerprint") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint):
            raise BackupError("Portable backup manifest fingerprint is invalid")
        unsigned = dict(metadata)
        unsigned.pop("manifest_fingerprint", None)
        if _canonical_sha256(unsigned) != expected_fingerprint:
            raise BackupError("Portable backup manifest fingerprint does not match")
        if str(metadata.get("storage_key_id") or "") != _storage_key_id(self.database_key):
            raise BackupError(
                "Backup requires the source installation recovery-kit storage key"
            )
        database = metadata.get("database")
        if not isinstance(database, dict):
            raise BackupError("Portable backup database manifest is missing")
        database_path = database_path or target_dir / self.db_path.name
        self._verify_file_entry(database_path, database)
        self._verify_sqlite_file(database_path)
        with _sqlite_connection(database_path, self.database_key) as conn:
            actual_database_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            actual_people_count = _table_row_count(conn, "persons")
            actual_embedding_count = _table_row_count(conn, "embeddings")
            journal = _journal_fingerprint(conn)
        if int(metadata.get("database_version", -1)) != actual_database_version:
            raise BackupError("Portable backup database version manifest is invalid")
        if int(metadata.get("people_count", -1)) != actual_people_count:
            raise BackupError("Portable backup people count manifest is invalid")
        if int(metadata.get("embedding_count", -1)) != actual_embedding_count:
            raise BackupError("Portable backup embedding count manifest is invalid")
        if metadata.get("journal") != journal:
            raise BackupError("Portable backup journal fingerprint is invalid")

        assets = metadata.get("assets")
        references = metadata.get("path_references")
        missing = metadata.get("missing_references")
        if not isinstance(assets, list) or not isinstance(references, list) or not isinstance(missing, list):
            raise BackupError("Portable backup media manifest is invalid")
        declared_assets: dict[str, dict[str, object]] = {}
        for asset in assets:
            if not isinstance(asset, dict):
                raise BackupError("Portable backup asset entry is invalid")
            relative = self._safe_archive_path(str(asset.get("archive_path", "")))
            normalized = relative.as_posix()
            if not relative.parts or relative.parts[0] != "files" or normalized in declared_assets:
                raise BackupError("Portable backup declares an unsafe or duplicate asset")
            declared_assets[normalized] = asset
            asset_path = target_dir / Path(*relative.parts)
            self._verify_file_entry(asset_path, asset)
            try:
                protected, plaintext_size = authenticate_protected_file(
                    asset_path, self.database_key,
                )
            except ProtectedFileError as exc:
                raise BackupError(f"Portable backup media failed authentication: {exc}") from exc
            if bool(asset.get("protected")) != protected:
                raise BackupError("Portable backup media protection manifest is invalid")
            if int(asset.get("plaintext_size", -1)) != plaintext_size:
                raise BackupError("Portable backup media plaintext size is invalid")

        actual = self._database_media_references(database_path)
        actual_by_binding = {
            _binding_key(item["registry_id"], item["row_identity"]): item
            for item in actual
        }
        if len(actual_by_binding) != len(actual):
            raise BackupError("Database contains ambiguous durable media bindings")
        declared_bindings: dict[str, tuple[str, dict[str, object]]] = {}
        for state, entries in (("stored", references), ("missing", missing)):
            for reference in entries:
                if not isinstance(reference, dict):
                    raise BackupError("Portable backup media binding is invalid")
                registry_id = str(reference.get("registry_id") or "")
                spec = MEDIA_REGISTRY_BY_ID.get(registry_id)
                if spec is None:
                    raise BackupError("Portable backup media binding is not registry-owned")
                try:
                    identity = identity_values(spec, reference.get("row_identity"))
                except ValueError as exc:
                    raise BackupError(str(exc)) from exc
                key = _binding_key(registry_id, stable_identity(spec, identity))
                if key in declared_bindings:
                    raise BackupError("Portable backup declares a duplicate media binding")
                actual_item = actual_by_binding.get(key)
                if actual_item is None:
                    raise BackupError("Portable backup media binding has no database row")
                if str(reference.get("path_fingerprint") or "") != _text_sha256(
                    str(actual_item["path"])
                ):
                    raise BackupError("Portable backup media binding path does not match its database")
                if state == "stored":
                    archive_path = self._safe_archive_path(
                        str(reference.get("archive_path") or "")
                    ).as_posix()
                    if archive_path not in declared_assets:
                        raise BackupError("Portable backup media binding has no asset")
                declared_bindings[key] = (state, reference)
        if set(declared_bindings) != set(actual_by_binding):
            raise BackupError("Portable backup media closure does not match its database")
        if int(metadata.get("reference_count", -1)) != len(actual):
            raise BackupError("Portable backup media reference count is invalid")
        if int(metadata.get("file_count", -1)) != len(assets):
            raise BackupError("Portable backup file count is invalid")
        if int(metadata.get("missing_file_count", -1)) != len(missing):
            raise BackupError("Portable backup missing-file count is invalid")
        complete = not missing
        if bool(metadata.get("complete")) != complete:
            raise BackupError("Portable backup completeness flag is invalid")
        if str(metadata.get("media_closure_status")) != ("COMPLETE" if complete else "INCOMPLETE"):
            raise BackupError("Portable backup media closure status is invalid")
        expected_size = int(database["size_bytes"]) + sum(int(asset["size_bytes"]) for asset in assets)
        if int(metadata.get("size_bytes", -1)) != expected_size:
            raise BackupError("Portable backup size manifest does not match its files")

        actual_integrity = self._integrity_metadata(database_path, actual_database_version)
        if metadata.get("integrity") != actual_integrity:
            raise BackupError("Portable backup integrity fingerprint is invalid")
        expected_restorable = complete and bool(actual_integrity["restore_eligible"])
        if bool(metadata.get("restorable")) != expected_restorable:
            raise BackupError("Portable backup restore eligibility is invalid")
        return True

    def _verify_legacy_v2_media_closure(
        self,
        database_path: Path,
        metadata: dict[str, object],
    ) -> None:
        """Accept v2 only when every current registry path was actually captured."""
        declared_stored = {
            str(item.get("original_path") or "")
            for item in metadata.get("path_references", [])
            if isinstance(item, dict)
        }
        declared_missing = {
            str(item.get("original_path") or "")
            for item in metadata.get("missing_references", [])
            if isinstance(item, dict)
        }
        actual_paths = {
            str(item["path"]) for item in self._database_media_references(database_path)
        }
        if actual_paths != declared_stored | declared_missing:
            raise BackupError(
                "Legacy v2 backup cannot prove complete durable media closure"
            )

    def _verify_file_entry(self, path: Path, entry: dict[str, object]) -> None:
        if not path.exists() or not path.is_file():
            raise BackupError(f"Portable backup file is missing: {path.name}")
        expected_size = int(entry.get("size_bytes", -1))
        if expected_size < 0 or path.stat().st_size != expected_size:
            raise BackupError(f"Portable backup file size mismatch: {path.name}")
        expected_digest = str(entry.get("sha256") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise BackupError("Portable backup checksum is invalid")
        if _sha256_file(path) != expected_digest:
            raise BackupError(f"Portable backup checksum mismatch: {path.name}")

    def _verify_sqlite_file(self, database_path: Path) -> None:
        try:
            with _sqlite_connection(database_path, self.database_key) as conn:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        except Exception as exc:
            raise BackupError(f"Backup database verification failed: {exc}") from exc
        if integrity != "ok" or foreign_key_errors:
            raise BackupError("Backup database failed integrity verification")

    def _validate_archive_entries(
        self,
        archive: zipfile.ZipFile,
    ) -> dict[str, zipfile.ZipInfo]:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise BackupError("Portable backup contains too many files")
        total_size = 0
        validated: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            relative = self._safe_archive_path(info.filename)
            normalized = relative.as_posix()
            if info.is_dir():
                continue
            if normalized in validated:
                raise BackupError("Portable backup contains duplicate file names")
            if info.flag_bits & 0x1:
                raise BackupError("Encrypted portable backups are not supported")
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise BackupError("Portable backup cannot contain symbolic links")
            total_size += int(info.file_size)
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise BackupError("Portable backup expands beyond the safe size limit")
            validated[normalized] = info
        return validated

    def _safe_archive_path(self, value: str) -> PurePosixPath:
        if (
            not value
            or len(value) > 2048
            or "\x00" in value
            or "\\" in value
            or value.startswith("/")
        ):
            raise BackupError("Portable backup contains an unsafe path")
        path = PurePosixPath(value)
        if (
            not path.parts
            or any(part in {"", ".", ".."} or len(part) > 255 for part in path.parts)
            or path.parts[0].endswith(":")
        ):
            raise BackupError("Portable backup contains an unsafe path")
        return path

    def _extract_verified_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        destination: Path,
        manifest_entry: dict[str, object],
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            declared_size = int(manifest_entry.get("size_bytes", -1))
            if declared_size < 0:
                raise BackupError("Portable backup file has an invalid declared size")
            self._require_free_space(declared_size + IMPORT_SAFETY_MARGIN_BYTES)
            with archive.open(info, "r") as source, temporary.open("xb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    if size_bytes > declared_size:
                        raise BackupError("Portable backup file exceeds its declared size")
                    self._require_free_space(
                        declared_size - size_bytes + IMPORT_SAFETY_MARGIN_BYTES
                    )
                output.flush()
                os.fsync(output.fileno())
            if size_bytes != declared_size:
                raise BackupError("Portable backup file size does not match its manifest")
            if digest.hexdigest() != str(manifest_entry.get("sha256", "")).lower():
                raise BackupError("Portable backup file checksum does not match its manifest")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _stage_restore_assets(
        self,
        backup_path: Path,
        metadata: dict[str, object],
        staging_media: Path,
        final_media_root: Path,
    ) -> dict[str, str]:
        restored_paths: dict[str, str] = {}
        for asset in metadata.get("assets", []):
            relative = self._safe_archive_path(str(asset["archive_path"]))
            source = backup_path / Path(*relative.parts)
            destination_name = Path(relative.name).name
            staged_destination = staging_media / destination_name
            if staged_destination.exists():
                if _sha256_file(staged_destination) != str(asset["sha256"]):
                    raise BackupError("Portable backup contains a conflicting asset name")
            else:
                shutil.copy2(source, staged_destination)
                self._verify_file_entry(staged_destination, asset)
            restored_paths[relative.as_posix()] = str(final_media_root / destination_name)
        return restored_paths

    def _rewrite_database_paths(
        self,
        database_path: Path,
        metadata: dict[str, object],
        restored_paths: dict[str, str],
    ) -> None:
        if database_path.resolve() == self.db_path.resolve():
            raise BackupError("Media relocation requires a disposable restore candidate")
        with _sqlite_connection(database_path, self.database_key) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            # Completed review decisions remain immutable. Only their physical
            # media location changes when restoring to a different authority.
            # Suspend this broad UPDATE guard on the disposable candidate, then
            # prove every non-location field unchanged and reinstall the exact
            # guard before committing. Failure rolls back paths and DDL together.
            guard = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'completed_photo_reviews_immutable'").fetchone()
            review_columns = [row[1] for row in conn.execute('PRAGMA table_info(photo_reviews)') if row[1] != 'media_path']
            review_select = 'SELECT ' + ', '.join(f'"{column}"' for column in review_columns) + ' FROM photo_reviews ORDER BY review_id' if review_columns else None
            review_authority = conn.execute(review_select).fetchall() if review_select else []
            if guard:
                conn.execute('DROP TRIGGER completed_photo_reviews_immutable')
            if int(metadata.get("format_version", 0)) == PORTABLE_BACKUP_FORMAT_VERSION:
                for reference in metadata.get("path_references", []):
                    registry_id = str(reference.get("registry_id") or "")
                    spec = MEDIA_REGISTRY_BY_ID.get(registry_id)
                    if spec is None:
                        raise BackupError("Restore media binding is not registry-owned")
                    try:
                        identity = identity_values(spec, reference.get("row_identity"))
                    except ValueError as exc:
                        raise BackupError(str(exc)) from exc
                    archive_path = self._safe_archive_path(
                        str(reference.get("archive_path") or "")
                    ).as_posix()
                    restored_path = restored_paths.get(archive_path)
                    if not restored_path:
                        raise BackupError("Restore manifest references an unavailable asset")
                    try:
                        update_media_reference(conn, spec, identity, restored_path)
                    except (KeyError, ValueError) as exc:
                        raise BackupError(str(exc)) from exc
            else:
                legacy_assets = {
                    str(reference.get("original_path") or ""): self._safe_archive_path(
                        str(reference.get("archive_path") or "")
                    ).as_posix()
                    for reference in metadata.get("path_references", [])
                    if isinstance(reference, dict)
                }
                for spec, identity, original_path in list(iter_media_references(conn)):
                    archive_path = legacy_assets.get(original_path)
                    restored_path = restored_paths.get(archive_path or "")
                    if not restored_path:
                        raise BackupError(
                            "Legacy v2 backup cannot rewrite a durable media reference"
                        )
                    update_media_reference(conn, spec, identity, restored_path)
            if (
                _table_has_column(conn, "init_sessions", "source_path")
                and _table_has_column(conn, "init_faces", "source_image")
            ):
                sessions = conn.execute(
                    """
                    SELECT s.session_id, MIN(f.source_image)
                    FROM init_sessions s
                    LEFT JOIN init_faces f ON f.session_id = s.session_id
                    GROUP BY s.session_id
                    """
                ).fetchall()
                for session_id, source_image in sessions:
                    if source_image:
                        conn.execute(
                            "UPDATE init_sessions SET source_path = ? WHERE session_id = ?",
                            (str(Path(source_image).parent), session_id),
                        )
            if review_select and conn.execute(review_select).fetchall() != review_authority:
                raise BackupError("Media relocation changed review authority")
            if guard:
                conn.execute(guard[0])
            conn.commit()

    def _replace_live_database(self, replacement: Path) -> None:
        if self.db_path.exists():
            try:
                with _sqlite_connection(self.db_path, self.database_key) as conn:
                    checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if checkpoint and int(checkpoint[0]) != 0:
                        raise BackupError("Current database is busy and cannot be restored safely")
            except Exception as exc:
                raise BackupError(
                    f"Current database could not be checkpointed safely: {exc}"
                ) from exc
        for suffix in ("-wal", "-shm"):
            Path(f"{self.db_path}{suffix}").unlink(missing_ok=True)
        os.replace(replacement, self.db_path)

    def _validate_operation_id(self, value: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise BackupError("Restore operation id must be a UUID") from exc

    def _restore_receipt_path(self, backup_id: str, operation_id: str) -> Path:
        return self._backup_path(backup_id) / "restores" / f"{operation_id}.json"

    def _write_json_atomic(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as output:
                json.dump(payload, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _unique_backup_id(self, created_at: datetime, reason: str | None = None) -> str:
        base = f"backup_{created_at.strftime('%Y-%m-%d_%H-%M-%S')}"
        if reason:
            slug = re.sub(r"[^a-z0-9]+", "-", reason.strip().lower()).strip("-")[:96]
            if slug:
                base = f"{base}_{slug}"
        candidate = base
        suffix = 1
        while (self.backup_dir / candidate).exists():
            candidate = f"{base}_{suffix:02d}"
            suffix += 1
        return candidate

    def _backup_path(self, backup_id: str) -> Path:
        if not BACKUP_ID_PATTERN.fullmatch(backup_id):
            raise BackupError(f"Invalid backup id: {backup_id}")
        resolved_root = self.backup_dir.resolve()
        resolved_path = (self.backup_dir / backup_id).resolve()
        if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
            raise BackupError(f"Invalid backup id: {backup_id}")
        return resolved_path

    def _database_path(self, backup_id: str) -> Path:
        return self._backup_path(backup_id) / self.db_path.name

    def _log(self, event: str, **details: object) -> None:
        if self._logger:
            try:
                self._logger(event, **details)
            except Exception:
                # Observability must never invalidate a verified data operation.
                pass


@contextmanager
def _sqlite_connection(path: Path, database_key: bytes | None = None):
    """Commit/roll back and always close SQLite handles before file operations."""
    conn = connect_database(path, database_key, timeout=30)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _table_row_count(conn: sqlite3.Connection, table: str) -> int:
    exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table,),
    ).fetchone()
    if exists is None:
        return 0
    # Table names are supplied only by this module, never by external input.
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    table_exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table,),
    ).fetchone()
    if table_exists is None:
        return False
    return column in {
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _with_manifest_fingerprint(metadata: dict[str, object]) -> dict[str, object]:
    normalized = dict(metadata)
    normalized.pop("manifest_fingerprint", None)
    normalized["manifest_fingerprint"] = _canonical_sha256(normalized)
    return normalized


def _storage_key_id(key: bytes | None) -> str:
    if key is None:
        return "plaintext-local-storage"
    if not isinstance(key, bytes) or len(key) != 32:
        raise BackupError("SentriFace storage key is invalid")
    return hashlib.sha256(b"sentriface-storage-key-v1\0" + key).hexdigest()


def _binding_key(registry_id: object, identity: object) -> str:
    return f"{registry_id}:{_canonical_sha256(identity)}"


def _bounded_text(value: object, limit: int) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized[:limit] or None


def _integrity_report_fingerprint(report: object) -> str:
    findings = getattr(report, "findings", ())
    payload = {
        "schema_version": getattr(report, "schema_version", None),
        "graph_revision": getattr(report, "graph_revision", None),
        "status": getattr(report, "status", None),
        "findings_truncated": bool(getattr(report, "findings_truncated", False)),
        "findings": [
            {
                "invariant_id": item.invariant_id,
                "severity": item.severity.value,
                "domain": item.domain,
                "entity_ids": list(item.entity_ids),
                "evidence": list(item.evidence),
            }
            for item in findings
        ],
    }
    return _canonical_sha256(payload)


def _journal_fingerprint(conn: sqlite3.Connection) -> dict[str, object]:
    if not _table_has_column(conn, "operation_journal", "operation_id"):
        payload = {"operation_count": 0, "transition_count": 0, "fingerprint": _canonical_sha256([])}
        return payload
    digest_rows: list[tuple[object, ...]] = []
    operations = conn.execute(
        """
        SELECT operation_id, operation_type, status, actor_user_id, source,
               created_at, completed_at
        FROM operation_journal ORDER BY created_at, operation_id
        """
    ).fetchall()
    for row in operations:
        digest_rows.append(("operation", *tuple(row)))
    transition_count = 0
    if _table_has_column(conn, "operation_journal_status_history", "transition_id"):
        transitions = conn.execute(
            """
            SELECT transition_id, operation_id, from_status, to_status, created_at
            FROM operation_journal_status_history
            ORDER BY created_at, rowid, transition_id
            """
        ).fetchall()
        transition_count = len(transitions)
        for row in transitions:
            digest_rows.append(("transition", *tuple(row)))
    return {
        "operation_count": len(operations),
        "transition_count": transition_count,
        "fingerprint": _canonical_sha256(digest_rows),
    }


def _safe_asset_suffix(suffix: str) -> str:
    normalized = suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,10}", normalized):
        return normalized
    return ".bin"
