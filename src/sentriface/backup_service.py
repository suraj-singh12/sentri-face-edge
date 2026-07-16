from __future__ import annotations

import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from sentriface import __version__


BACKUP_ID_PATTERN = re.compile(r"^backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_\d{2})?$")


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


class BackupService:
    def __init__(
        self,
        db_path: Path,
        backup_dir: Path,
        retention_limit: int = 10,
        app_version: str = __version__,
        now: Callable[[], datetime] | None = None,
        logger: Callable[[str, object], None] | None = None,
    ) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.retention_limit = retention_limit
        self.app_version = app_version
        self._now = now or (lambda: datetime.now().astimezone())
        self._logger = logger

    def create_backup(self) -> BackupRecord:
        if not self.db_path.exists():
            raise BackupError(f"Database file not found: {self.db_path}")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        created_at = self._now()
        backup_id = self._unique_backup_id(created_at)
        target_dir = self._backup_path(backup_id)
        target_db = target_dir / self.db_path.name
        try:
            target_dir.mkdir(parents=False, exist_ok=False)
            self._backup_sqlite(target_db)
            if not self.verify_backup(backup_id):
                raise BackupError("SQLite integrity check failed")
            metadata = self._metadata(backup_id, created_at, target_db)
            (target_dir / "backup.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            record = self._record_from_metadata(metadata)
        except Exception as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            self._log("backup-failed", backup_id=backup_id, error=str(exc))
            if isinstance(exc, BackupError):
                raise
            raise BackupError(f"Database backup could not be created: {exc}") from exc

        self._log("backup-created", backup_id=record.backup_id, size_bytes=record.size_bytes)
        try:
            self.enforce_retention()
        except Exception as exc:  # noqa: BLE001 - retention should not invalidate a verified backup.
            self._log("backup-retention-failed", error=str(exc))
        return record

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
        target_db = self._database_path(backup_id)
        if not target_db.exists():
            raise BackupError(f"Backup database not found: {backup_id}")
        try:
            with sqlite3.connect(target_db) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.Error as exc:
            raise BackupError(f"Backup verification failed: {exc}") from exc
        verified = result == "ok"
        if not verified:
            self._log("backup-verification-failed", backup_id=backup_id, result=result)
        return verified

    def delete_backup(self, backup_id: str) -> None:
        target_dir = self._backup_path(backup_id)
        if not target_dir.exists():
            raise BackupError(f"Backup not found: {backup_id}")
        shutil.rmtree(target_dir)
        self._log("backup-deleted", backup_id=backup_id)

    def enforce_retention(self) -> list[str]:
        if self.retention_limit <= 0:
            return []
        backups = self.list_backups()
        removed = []
        for record in backups[self.retention_limit:]:
            self.delete_backup(record.backup_id)
            removed.append(record.backup_id)
            self._log("backup-retention-cleanup", backup_id=record.backup_id)
        return removed

    def _backup_sqlite(self, target_db: Path) -> None:
        with sqlite3.connect(self.db_path) as source:
            with sqlite3.connect(target_db) as destination:
                source.backup(destination)

    def _metadata(self, backup_id: str, created_at: datetime, target_db: Path) -> dict[str, object]:
        with sqlite3.connect(target_db) as conn:
            database_version = conn.execute("PRAGMA user_version").fetchone()[0]
            people_count = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
            embedding_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        size_bytes = target_db.stat().st_size
        return {
            "backup_id": backup_id,
            "created_at": created_at.isoformat(timespec="seconds"),
            "app_version": self.app_version,
            "database_version": database_version,
            "people_count": people_count,
            "embedding_count": embedding_count,
            "database_size_bytes": size_bytes,
            "size_bytes": size_bytes,
            "verified": True,
        }

    def _record_from_metadata(self, metadata: dict[str, object]) -> BackupRecord:
        size_bytes = int(metadata.get("size_bytes") or metadata["database_size_bytes"])
        return BackupRecord(
            backup_id=str(metadata["backup_id"]),
            created_at=str(metadata["created_at"]),
            size_bytes=size_bytes,
            people_count=int(metadata["people_count"]),
            embedding_count=int(metadata["embedding_count"]),
            verified=bool(metadata.get("verified", True)),
            database_version=int(metadata["database_version"]),
            app_version=str(metadata["app_version"]),
        )

    def _unique_backup_id(self, created_at: datetime) -> str:
        base = f"backup_{created_at.strftime('%Y-%m-%d_%H-%M-%S')}"
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
            self._logger(event, **details)
