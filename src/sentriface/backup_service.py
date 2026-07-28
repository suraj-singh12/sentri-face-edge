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


BACKUP_ID_PATTERN = re.compile(
    r"^backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"
    r"(?:_[a-z0-9][a-z0-9-]{0,95})?(?:_\d{2})?$"
)
PORTABLE_BACKUP_FORMAT_VERSION = 2
PORTABLE_BACKUP_EXTENSION = ".sfbackup"
MAX_ARCHIVE_ENTRIES = 100_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 50_000_000_000
MAX_MANIFEST_BYTES = 10_000_000
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
    ) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.data_dir = data_dir or db_path.parent
        self.retention_limit = retention_limit
        self.app_version = app_version
        self.supported_database_version = supported_database_version
        self._now = now or (lambda: datetime.now().astimezone())
        self._logger = logger
        self._create_lock = threading.RLock()

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
            with _sqlite_connection(target_db) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        except sqlite3.Error as exc:
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
        protected_ids = protected_ids or set()
        backups = self.list_backups()
        removed = []
        kept = 0
        for record in backups:
            if record.backup_id in protected_ids:
                kept += 1
                continue
            if kept < self.retention_limit:
                kept += 1
                continue
            self.delete_backup(record.backup_id)
            removed.append(record.backup_id)
            self._log("backup-retention-cleanup", backup_id=record.backup_id)
        return removed

    def export_backup(self, backup_id: str, destination: Path) -> Path:
        """Create one verified, portable archive without loading it into memory."""
        with self._create_lock:
            if not self.verify_backup(backup_id):
                raise BackupError(f"Backup failed verification: {backup_id}")
            backup_path = self._backup_path(backup_id)
            metadata = self._read_metadata(backup_path)
            if int(metadata.get("format_version", 1)) < PORTABLE_BACKUP_FORMAT_VERSION:
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
                    manifest_info = infos.get("backup.json")
                    if manifest_info is None:
                        raise BackupError("Portable backup has no manifest")
                    if manifest_info.file_size > MAX_MANIFEST_BYTES:
                        raise BackupError("Portable backup manifest is too large")
                    with archive.open(manifest_info, "r") as source:
                        metadata = json.loads(source.read(MAX_MANIFEST_BYTES + 1).decode("utf-8"))
                    if int(metadata.get("format_version", 0)) != PORTABLE_BACKUP_FORMAT_VERSION:
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

    def restore_backup(
        self,
        backup_id: str,
        operation_id: str,
        reload_callback: Callable[[], None] | None = None,
        allow_incomplete: bool = False,
    ) -> dict[str, object]:
        """Atomically restore a verified backup and roll back on any failure."""
        with self._create_lock:
            operation_id = self._validate_operation_id(operation_id)
            receipt_path = self._restore_receipt_path(backup_id, operation_id)
            if receipt_path.exists():
                return json.loads(receipt_path.read_text(encoding="utf-8"))
            if not self.verify_backup(backup_id):
                raise BackupError(f"Backup failed verification: {backup_id}")
            record = next(
                (item for item in self.list_backups() if item.backup_id == backup_id),
                None,
            )
            if record is None:
                raise BackupError(f"Backup metadata not found: {backup_id}")
            if self.supported_database_version is not None and (
                record.database_version > self.supported_database_version
            ):
                raise BackupError(
                    "Backup database is newer than this SentriFace version supports"
                )
            if not record.complete and not allow_incomplete:
                raise BackupError(
                    "This backup is incomplete because referenced files were missing"
                )
            self._require_free_space(max(record.size_bytes * 2, 64 * 1024 * 1024))
            safety = self.create_backup(
                reason=f"before-restore-{backup_id}",
                operation_id=f"restore-safety-{operation_id}",
                protected_backup_ids={backup_id},
            )
            restore_token = uuid.uuid4().hex
            staging_root = self.data_dir / f".restore-{restore_token}"
            final_media_root = self.data_dir / "restored-media" / restore_token
            staging_media = staging_root / "media"
            staged_db = staging_root / self.db_path.name
            installed_media = False
            database_replaced = False
            try:
                staging_media.mkdir(parents=True, exist_ok=False)
                metadata = self._read_metadata(self._backup_path(backup_id))
                shutil.copy2(self._database_path(backup_id), staged_db)
                restored_paths = self._stage_restore_assets(
                    self._backup_path(backup_id),
                    metadata,
                    staging_media,
                    final_media_root,
                )
                self._rewrite_database_paths(staged_db, metadata, restored_paths)
                self._verify_sqlite_file(staged_db)
                final_media_root.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging_media, final_media_root)
                installed_media = True
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._replace_live_database(staged_db)
                database_replaced = True
                if reload_callback:
                    reload_callback()
                result: dict[str, object] = {
                    "restored": True,
                    "backup_id": backup_id,
                    "operation_id": operation_id,
                    "safety_backup_id": safety.backup_id,
                    "restored_files": len(metadata.get("assets", [])),
                    "missing_files": len(metadata.get("missing_references", [])),
                    "complete": record.complete,
                    "restored_at": self._now().isoformat(timespec="seconds"),
                }
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.enforce_retention(protected_ids={backup_id, safety.backup_id})
                except Exception as retention_exc:  # noqa: BLE001
                    self._log("backup-retention-failed", error=str(retention_exc))
                # The receipt is the restore commit marker. Write it only after
                # every step that is allowed to trigger rollback has succeeded.
                self._write_json_atomic(receipt_path, result)
                self._log("backup-restored", **result)
                return result
            except Exception as exc:
                rollback_error = None
                if database_replaced:
                    try:
                        rollback_temp = staging_root / f"rollback-{self.db_path.name}"
                        shutil.copy2(self._database_path(safety.backup_id), rollback_temp)
                        self._replace_live_database(rollback_temp)
                        if reload_callback:
                            reload_callback()
                    except Exception as rollback_exc:  # noqa: BLE001 - report both failures.
                        rollback_error = rollback_exc
                if installed_media:
                    shutil.rmtree(final_media_root, ignore_errors=True)
                details = str(exc)
                if rollback_error is not None:
                    details = f"{details}; automatic rollback failed: {rollback_error}"
                self._log(
                    "backup-restore-failed",
                    backup_id=backup_id,
                    safety_backup_id=safety.backup_id,
                    error=details,
                )
                if isinstance(exc, BackupError) and rollback_error is None:
                    raise
                raise BackupError(f"Backup restore failed: {details}") from exc
            finally:
                shutil.rmtree(staging_root, ignore_errors=True)

    def _estimated_live_backup_bytes(self) -> int:
        estimate = self.db_path.stat().st_size
        try:
            references = self._database_path_references(self.db_path)
        except (BackupError, sqlite3.Error):
            references = {}
        for raw_path in references:
            path = Path(raw_path)
            try:
                if path.is_file():
                    estimate += path.stat().st_size
            except OSError:
                continue
        return max(int(estimate * 1.15), estimate + 64 * 1024 * 1024)

    def _require_free_space(self, required_bytes: int) -> None:
        available = shutil.disk_usage(self.backup_dir).free
        if available < required_bytes:
            raise BackupError(
                f"Not enough free space for a safe backup operation: "
                f"need about {required_bytes} bytes, have {available} bytes"
            )
    def _backup_sqlite(self, target_db: Path) -> None:
        with _sqlite_connection(self.db_path) as source:
            with _sqlite_connection(target_db) as destination:
                source.backup(destination)

    def _capture_referenced_files(
        self,
        target_db: Path,
        target_dir: Path,
    ) -> dict[str, object]:
        references = self._database_path_references(target_db)
        assets_by_hash: dict[str, dict[str, object]] = {}
        path_references: list[dict[str, object]] = []
        missing_references: list[dict[str, str]] = []
        files_root = target_dir / "files"
        for original_path, locations in references.items():
            source = self._resolve_reference_path(original_path)
            if source is None:
                missing_references.append(
                    {
                        "original_path": original_path,
                        "reason": "not_found_or_not_a_file",
                    }
                )
                continue
            digest, size_bytes, temporary = self._copy_and_hash(source, files_root)
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
                    "original_paths": [],
                }
                assets_by_hash[digest] = existing
            else:
                temporary.unlink(missing_ok=True)
            original_paths = existing["original_paths"]
            if original_path not in original_paths:
                original_paths.append(original_path)
            path_references.append(
                {
                    "original_path": original_path,
                    "archive_path": existing["archive_path"],
                    "locations": locations,
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
                key=lambda item: str(item["original_path"]),
            ),
            "missing_references": sorted(
                missing_references,
                key=lambda item: item["original_path"],
            ),
            "reference_count": len(references),
            "asset_size_bytes": sum(int(asset["size_bytes"]) for asset in assets),
        }

    def _database_path_references(
        self,
        database_path: Path,
    ) -> dict[str, list[dict[str, str]]]:
        references: dict[str, list[dict[str, str]]] = {}
        with _sqlite_connection(database_path) as conn:
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
    ) -> tuple[str, int, Path]:
        files_root.mkdir(parents=True, exist_ok=True)
        source_before = source.stat()
        temporary = files_root / f".asset-{uuid.uuid4().hex}.tmp"
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with source.open("rb") as input_file, temporary.open("xb") as output_file:
                while True:
                    chunk = input_file.read(1024 * 1024)
                    if not chunk:
                        break
                    output_file.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())
            source_after = source.stat()
            if (
                source_before.st_size != source_after.st_size
                or source_before.st_mtime_ns != source_after.st_mtime_ns
                or size_bytes != source_after.st_size
            ):
                raise BackupError(f"Referenced file changed during backup: {source}")
            return digest.hexdigest(), size_bytes, temporary
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
        with _sqlite_connection(target_db) as conn:
            database_version = conn.execute("PRAGMA user_version").fetchone()[0]
            # Pre-migration snapshots can predate either table. Missing tables
            # represent zero records; they do not make an otherwise valid backup unsafe.
            people_count = _table_row_count(conn, "persons")
            embedding_count = _table_row_count(conn, "embeddings")
        database_size_bytes = target_db.stat().st_size
        database_sha256 = _sha256_file(target_db)
        assets = list(asset_manifest["assets"])
        missing_references = list(asset_manifest["missing_references"])
        size_bytes = database_size_bytes + int(asset_manifest["asset_size_bytes"])
        return {
            "backup_id": backup_id,
            "created_at": created_at.isoformat(timespec="seconds"),
            "format_version": PORTABLE_BACKUP_FORMAT_VERSION,
            "portable": True,
            "app_version": self.app_version,
            "database_version": database_version,
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
            "complete": not missing_references,
            "size_bytes": size_bytes,
            "verified": True,
            "reason": reason,
            "operation_id": operation_id,
        }

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
        if int(metadata.get("format_version", 0)) != PORTABLE_BACKUP_FORMAT_VERSION:
            raise BackupError("Unsupported portable backup format")
        database = metadata.get("database")
        if not isinstance(database, dict):
            raise BackupError("Portable backup database manifest is missing")
        database_path = database_path or target_dir / self.db_path.name
        self._verify_file_entry(database_path, database)
        self._verify_sqlite_file(database_path)
        with _sqlite_connection(database_path) as conn:
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
        return True

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
            with _sqlite_connection(database_path) as conn:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        except sqlite3.Error as exc:
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
            with archive.open(info, "r") as source, temporary.open("xb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    if size_bytes > int(manifest_entry.get("size_bytes", -1)):
                        raise BackupError("Portable backup file exceeds its declared size")
                output.flush()
                os.fsync(output.fileno())
            if size_bytes != int(manifest_entry.get("size_bytes", -1)):
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
        with _sqlite_connection(database_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for reference in metadata.get("path_references", []):
                original_path = str(reference["original_path"])
                archive_path = self._safe_archive_path(
                    str(reference["archive_path"])
                ).as_posix()
                restored_path = restored_paths.get(archive_path)
                if not restored_path:
                    raise BackupError("Restore manifest references an unavailable asset")
                for location in reference["locations"]:
                    table = str(location["table"])
                    column = str(location["column"])
                    if (table, column) not in PATH_REFERENCE_COLUMNS:
                        raise BackupError("Restore manifest contains an unsafe database location")
                    if not _table_has_column(conn, table, column):
                        continue
                    conn.execute(
                        f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" = ?',
                        (restored_path, original_path),
                    )
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
            conn.commit()

    def _replace_live_database(self, replacement: Path) -> None:
        if self.db_path.exists():
            try:
                with _sqlite_connection(self.db_path) as conn:
                    checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if checkpoint and int(checkpoint[0]) != 0:
                        raise BackupError("Current database is busy and cannot be restored safely")
            except sqlite3.Error as exc:
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
def _sqlite_connection(path: Path):
    """Commit/roll back and always close SQLite handles before file operations."""
    conn = sqlite3.connect(path, timeout=30)
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


def _safe_asset_suffix(suffix: str) -> str:
    normalized = suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,10}", normalized):
        return normalized
    return ".bin"
