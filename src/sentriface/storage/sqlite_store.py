from __future__ import annotations

import json
import re
import sqlite3
import struct
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from sentriface.backup_service import BackupError, BackupService
from sentriface.models import (
    DetectedFace,
    Embedding,
    EmbeddingRecord,
    FaceBox,
    InitFace,
    InitGroup,
    InitSession,
    MatchDecision,
    PendingAddition,
    Person,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PersonSummary,
    QualityReport,
    QualityStatus,
    RecognitionDetail,
    utc_now,
)

from sentriface.secure_storage import connect_database, ensure_encrypted_database

SCHEMA_VERSION = 17
DELETED_FACE_RETENTION_DAYS = 30
OPERATION_STATUSES = frozenset({"STARTED", "COMMITTED", "FAILED", "ROLLED_BACK", "REVERTED"})
OPERATION_STATUS_TRANSITIONS = {
    "STARTED": frozenset({"COMMITTED", "FAILED", "ROLLED_BACK"}),
    "FAILED": frozenset({"ROLLED_BACK"}),
    "COMMITTED": frozenset({"REVERTED"}),
    "ROLLED_BACK": frozenset(),
    "REVERTED": frozenset(),
}


class SchemaMigrationError(RuntimeError):
    """Raised when the database cannot be migrated safely to the current schema."""


@dataclass(frozen=True)
class SchemaMigration:
    from_version: int
    to_version: int
    apply: Callable[[sqlite3.Connection], None]


class SQLiteIdentityStore:
    def __init__(
        self,
        db_path: Path,
        embedding_dim: int = 512,
        backup_dir: Path | None = None,
        backup_retention_limit: int = 10,
        database_key: bytes | None = None,
    ) -> None:
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.backup_dir = backup_dir or db_path.parent / "backups"
        self.backup_retention_limit = backup_retention_limit
        self.database_key = database_key

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_key is not None:
            ensure_encrypted_database(self.db_path, self.database_key)
        initial_version = self._schema_version()
        _require_supported_schema_version(initial_version)
        if 0 < initial_version < SCHEMA_VERSION:
            self._create_pre_migration_backup(initial_version)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            _require_supported_schema_version(current_version)
            if current_version != initial_version:
                raise SchemaMigrationError(
                    "Database schema version changed while migration was being prepared "
                    f"(v{initial_version} to v{current_version}); startup was stopped safely."
                )
            _apply_schema_migrations(conn, current_version)

    def _schema_version(self) -> int:
        if not self.db_path.exists():
            return 0
        with closing(connect_database(self.db_path, self.database_key)) as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def _create_pre_migration_backup(self, version: int) -> None:
        reason = f"before-schema-migration-v{version}-to-v{SCHEMA_VERSION}"
        operation_id = f"schema-migration-v{version}-to-v{SCHEMA_VERSION}"
        service = BackupService(
            self.db_path,
            self.backup_dir,
            retention_limit=self.backup_retention_limit,
            database_key=self.database_key,
        )
        existing = service.find_by_operation(operation_id)
        if existing is not None:
            if not service.verify_backup(existing.backup_id):
                raise BackupError(
                    f"Existing pre-migration backup failed verification: {existing.backup_id}"
                )
            return
        backup = service.create_backup(reason=reason, operation_id=operation_id)
        if not backup.verified or not service.verify_backup(backup.backup_id):
            raise BackupError(f"Pre-migration backup failed verification: {backup.backup_id}")

    def create_person(self, name: str, metadata: dict | None = None, notes: str = "") -> Person:
        person = Person(
            person_id=str(uuid.uuid4()),
            name=name,
            metadata=metadata or {},
            notes=notes.strip(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO persons(person_id, name, metadata, created_at, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    person.person_id,
                    person.name,
                    json.dumps(person.metadata, separators=(",", ":")),
                    person.created_at,
                    person.notes,
                ),
            )
            _create_note_associations(conn, person.person_id, person.notes, "SentriFace", [])
        return person

    def create_placeholder_person(
        self,
        name: str,
        metadata: dict | None,
        editor_name: str,
        operation_id: str,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> Person:
        normalized_name = name.strip()
        if not normalized_name:
            raise KeyError("Person name is required")
        if not editor_name.strip():
            raise KeyError("Created by is required")
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "create-placeholder")
            if existing:
                row = conn.execute(
                    """
                    SELECT person_id, name, metadata, created_at, deleted_at, enrollment_status, notes
                    FROM persons WHERE person_id = ?
                    """,
                    (existing["person_id"],),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Stored placeholder creation result is no longer available")
                return _person_from_row(row)
            person = _create_placeholder_record(
                conn,
                normalized_name,
                metadata,
                editor_name.strip(),
                notes,
            )
            automatic_associations = _create_note_associations(
                conn, person.person_id, person.notes, editor_name.strip(), mentioned_person_ids or [],
            )
            _record_person_operation(
                conn,
                operation_id,
                "create-placeholder",
                {
                    "person_id": person.person_id,
                    "person_ids": [person.person_id, *[item.target_person_id if item.source_person_id == person.person_id else item.source_person_id for item in automatic_associations]],
                    "enrollment_status": "placeholder",
                    "automatic_association_ids": [item.association_id for item in automatic_associations],
                },
            )
        return person

    def get_person(self, person_id: str, include_archived: bool = False) -> Person | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT person_id, name, metadata, created_at, deleted_at, enrollment_status, notes
                FROM persons
                WHERE person_id = ? {" " if include_archived else "AND deleted_at IS NULL"}
                """,
                (person_id,),
            ).fetchone()
        if row is None:
            return None
        return _person_from_row(row)

    def list_persons(self, archived: bool = False) -> list[PersonSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.person_id, p.name, p.metadata, p.created_at, p.deleted_at,
                       p.enrollment_status, p.notes,
                       (
                           SELECT COUNT(*)
                           FROM embeddings e
                           WHERE e.person_id = p.person_id AND e.deleted_at IS NULL
                       ) AS embedding_count,
                       (
                           SELECT COUNT(*)
                           FROM recognition_details d
                           JOIN embeddings e ON e.embedding_id = d.embedding_id
                           WHERE d.person_id = p.person_id AND e.deleted_at IS NULL
                       ) AS sighting_count,
                       (
                           SELECT MAX(
                               CASE
                                   WHEN TRIM(COALESCE(d.seen_date, '')) <> ''
                                   THEN d.seen_date || 'T' || COALESCE(NULLIF(d.seen_time, ''), '00:00:00')
                                   ELSE d.created_at
                               END
                           )
                           FROM recognition_details d
                           JOIN embeddings e ON e.embedding_id = d.embedding_id
                           WHERE d.person_id = p.person_id AND e.deleted_at IS NULL
                       ) AS last_seen_at
                FROM persons p
                WHERE p.deleted_at IS {"NOT NULL" if archived else "NULL"}
                ORDER BY p.name COLLATE NOCASE
                """
            ).fetchall()
        return [
            PersonSummary(
                person=Person(
                    person_id=row["person_id"],
                    name=row["name"],
                    metadata=json.loads(row["metadata"]),
                    created_at=row["created_at"],
                    deleted_at=row["deleted_at"],
                    enrollment_status=row["enrollment_status"],
                    notes=row["notes"],
                ),
                embedding_count=row["embedding_count"],
                sighting_count=row["sighting_count"],
                last_seen_at=row["last_seen_at"],
            )
            for row in rows
        ]

    def list_embeddings_for_person(
        self,
        person_id: str,
        include_archived: bool = False,
    ) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT e.embedding_id, e.person_id, e.vector, e.quality_score,
                       e.source_image, e.crop_path, e.created_at
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.person_id = ?
                  AND e.deleted_at IS NULL
                  {" " if include_archived else "AND p.deleted_at IS NULL"}
                ORDER BY e.created_at ASC
                """,
                (person_id,),
            ).fetchall()
        return [_embedding_from_row(row) for row in rows]

    def rename_person(self, person_id: str, name: str) -> None:
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    "UPDATE persons SET name = ? WHERE person_id = ? AND deleted_at IS NULL",
                    (name, person_id),
                )
            except sqlite3.IntegrityError as exc:
                raise _placeholder_name_conflict(exc) from exc
        if cursor.rowcount == 0:
            raise KeyError(f"Unknown person: {person_id}")

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
        with self._connect() as conn:
            if operation_id:
                existing = _begin_person_operation(conn, operation_id, "update-profile")
                if existing:
                    change_row = conn.execute(
                        """
                        SELECT change_id, person_id, previous_name, new_name,
                               previous_rank, new_rank, previous_country, new_country,
                               previous_importance, new_importance,
                               previous_status, new_status, previous_notes, new_notes,
                               editor_name, created_at
                        FROM person_change_history
                        WHERE change_id = ?
                        """,
                        (existing["change_id"],),
                    ).fetchone()
                    if change_row is None:
                        raise RuntimeError("Stored profile update result is no longer available")
                    return _person_change_from_row(change_row)
            row = conn.execute(
                """
                SELECT person_id, name, metadata, enrollment_status, notes
                FROM persons
                WHERE person_id = ? AND deleted_at IS NULL
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown person: {person_id}")
            previous_metadata = json.loads(row["metadata"])
            previous_name = row["name"]
            next_metadata = {
                **previous_metadata,
                "rank": rank or "",
                "country": country or "",
                "importance": importance or "",
                "tags": _normalize_tags(tags if tags is not None else previous_metadata.get("tags", [])),
            }
            change = PersonChange(
                change_id=str(uuid.uuid4()),
                person_id=person_id,
                previous_name=previous_name,
                new_name=name,
                previous_rank=previous_metadata.get("rank") or "",
                new_rank=rank or "",
                previous_country=previous_metadata.get("country") or "",
                new_country=country or "",
                previous_importance=previous_metadata.get("importance") or "",
                new_importance=importance or "",
                previous_status=row["enrollment_status"],
                new_status=row["enrollment_status"],
                previous_notes=row["notes"],
                new_notes=row["notes"],
                editor_name=editor_name,
                created_at=utc_now(),
            )
            try:
                conn.execute(
                    """
                    UPDATE persons
                    SET name = ?, metadata = ?
                    WHERE person_id = ? AND deleted_at IS NULL
                    """,
                    (
                        name,
                        json.dumps(next_metadata, separators=(",", ":")),
                        person_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise _placeholder_name_conflict(exc) from exc
            _insert_person_change(conn, change)
            if operation_id:
                _record_person_operation(
                    conn,
                    operation_id,
                    "update-profile",
                    {"change_id": change.change_id, "person_id": person_id},
                )
        return change

    def update_person_notes(
        self,
        person_id: str,
        notes: str,
        expected_previous_notes: str,
        editor_name: str,
        operation_id: str,
        mentioned_person_ids: list[str] | None = None,
    ) -> tuple[bool, Person, PersonChange | None]:
        next_notes = notes.strip()
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "update-person-notes")
            if existing:
                person_row = conn.execute(
                    "SELECT * FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError("This person no longer exists")
                change = None
                if existing.get("change_id"):
                    row = conn.execute(
                        "SELECT * FROM person_change_history WHERE change_id = ?",
                        (existing["change_id"],),
                    ).fetchone()
                    change = _person_change_from_row(row) if row else None
                return bool(existing.get("changed")), _person_from_row(person_row), change
            row = conn.execute(
                "SELECT * FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError("This person no longer exists")
            current_notes = row["notes"] or ""
            if current_notes != expected_previous_notes:
                raise KeyError("Notes were changed elsewhere. Reopen this profile and try again.")
            if current_notes == next_notes:
                automatic_associations = _create_note_associations(
                    conn, person_id, next_notes, editor_name.strip(), mentioned_person_ids or [],
                )
                if automatic_associations:
                    _record_person_operation(conn, operation_id, "update-person-notes", {
                        "person_id": person_id,
                        "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                        "changed": False,
                        "automatic_association_ids": [item.association_id for item in automatic_associations],
                    })
                    return True, _person_from_row(row), None
                return False, _person_from_row(row), None
            cursor = conn.execute(
                "UPDATE persons SET notes = ? WHERE person_id = ? AND deleted_at IS NULL AND notes = ?",
                (next_notes, person_id, current_notes),
            )
            if cursor.rowcount != 1:
                raise KeyError("Notes could not be saved because this profile changed. Reopen it and try again.")
            change = PersonChange(
                change_id=str(uuid.uuid4()),
                person_id=person_id,
                previous_name=row["name"],
                new_name=row["name"],
                previous_rank=(json.loads(row["metadata"]).get("rank") or ""),
                new_rank=(json.loads(row["metadata"]).get("rank") or ""),
                previous_country=(json.loads(row["metadata"]).get("country") or ""),
                new_country=(json.loads(row["metadata"]).get("country") or ""),
                previous_importance=(json.loads(row["metadata"]).get("importance") or ""),
                new_importance=(json.loads(row["metadata"]).get("importance") or ""),
                previous_status=row["enrollment_status"],
                new_status=row["enrollment_status"],
                previous_notes=current_notes,
                new_notes=next_notes,
                editor_name=editor_name.strip(),
                created_at=utc_now(),
            )
            _insert_person_change(conn, change)
            automatic_associations = _create_note_associations(
                conn, person_id, next_notes, editor_name.strip(), mentioned_person_ids or [],
            )
            _record_person_operation(conn, operation_id, "update-person-notes", {
                "person_id": person_id,
                "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                "change_id": change.change_id,
                "changed": True,
                "automatic_association_ids": [item.association_id for item in automatic_associations],
            })
            updated = conn.execute("SELECT * FROM persons WHERE person_id = ?", (person_id,)).fetchone()
        return True, _person_from_row(updated), change

    def list_person_changes(self, person_id: str) -> list[PersonChange]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT change_id, person_id, previous_name, new_name,
                       previous_rank, new_rank, previous_country, new_country,
                       previous_importance, new_importance,
                       previous_status, new_status, previous_notes, new_notes,
                       editor_name, created_at
                FROM person_change_history
                WHERE person_id = ?
                ORDER BY created_at DESC
                """,
                (person_id,),
            ).fetchall()
        return [_person_change_from_row(row) for row in rows]

    def list_person_operations(self, person_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT operation_id, operation_type, result, created_at
                FROM person_operations
                ORDER BY created_at DESC
                """
            ).fetchall()
        operations: list[dict] = []
        for row in rows:
            result = json.loads(row["result"])
            involved_ids = {
                result.get("person_id"),
                result.get("source_person_id"),
                result.get("target_person_id"),
            }
            involved_ids.update(result.get("person_ids") or [])
            if person_id not in involved_ids:
                continue
            operations.append(
                {
                    "operation_id": row["operation_id"],
                    "operation_type": row["operation_type"],
                    "created_at": row["created_at"],
                    "result": result,
                }
            )
        return operations

    def create_person_association(
        self,
        source_person_id: str,
        target_person_id: str,
        actor_name: str,
        operation_id: str,
    ) -> PersonAssociation:
        actor = actor_name.strip()
        if not actor:
            raise KeyError("Created by is required")
        person_a_id, person_b_id = _canonical_person_pair(
            source_person_id,
            target_person_id,
        )
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "create-person-association",
            )
            if existing:
                row = conn.execute(
                    "SELECT * FROM person_associations WHERE association_id = ?",
                    (existing["association_id"],),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Stored association result is no longer available")
                return _person_association_from_row(row)
            _require_active_people(conn, person_a_id, person_b_id)
            current = conn.execute(
                "SELECT * FROM person_associations WHERE source_person_id = ? AND target_person_id = ? AND relationship_type = 'ASSOCIATED_WITH'",
                (person_a_id, person_b_id),
            ).fetchone()
            if current is not None:
                if current["association_origin"] == "automatic_mention":
                    conn.execute(
                        "UPDATE person_associations SET association_origin = 'manual', updated_at = ?, created_by = ? WHERE association_id = ?",
                        (utc_now(), actor, current["association_id"]),
                    )
                    association = _person_association_from_row(conn.execute(
                        "SELECT * FROM person_associations WHERE association_id = ?", (current["association_id"],),
                    ).fetchone())
                    _record_person_operation(conn, operation_id, "create-person-association", {
                        "association_id": association.association_id,
                        "source_person_id": source_person_id,
                        "target_person_id": target_person_id,
                        "relationship_type": association.relationship_type,
                        "actor_name": actor,
                        "upgraded_from_automatic": True,
                    })
                    return association
                raise KeyError("These people are already associated")
            association = _new_person_association(person_a_id, person_b_id, actor)
            try:
                _insert_person_association(conn, association)
            except sqlite3.IntegrityError as exc:
                if "person_associations" in str(exc):
                    raise KeyError("These people are already associated") from exc
                raise
            _record_person_operation(
                conn,
                operation_id,
                "create-person-association",
                {
                    "association_id": association.association_id,
                    "source_person_id": source_person_id,
                    "target_person_id": target_person_id,
                    "relationship_type": association.relationship_type,
                    "actor_name": actor,
                },
            )
            return association

    def create_placeholder_association(
        self,
        source_person_id: str,
        name: str,
        metadata: dict | None,
        actor_name: str,
        operation_id: str,
    ) -> tuple[Person, PersonAssociation]:
        actor = actor_name.strip()
        normalized_name = name.strip().lstrip("@").strip()
        if not normalized_name:
            raise KeyError("Person name is required")
        if not actor:
            raise KeyError("Created by is required")
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "create-placeholder-association",
            )
            if existing:
                person_row = conn.execute(
                    """
                    SELECT person_id, name, metadata, created_at, deleted_at,
                           enrollment_status
                    FROM persons WHERE person_id = ?
                    """,
                    (existing["target_person_id"],),
                ).fetchone()
                association_row = conn.execute(
                    "SELECT * FROM person_associations WHERE association_id = ?",
                    (existing["association_id"],),
                ).fetchone()
                if person_row is None or association_row is None:
                    raise RuntimeError("Stored placeholder association is no longer available")
                return (
                    _person_from_row(person_row),
                    _person_association_from_row(association_row),
                )
            _require_active_people(conn, source_person_id)
            person = _create_placeholder_record(
                conn,
                normalized_name,
                metadata,
                actor,
            )
            person_a_id, person_b_id = _canonical_person_pair(
                source_person_id,
                person.person_id,
            )
            association = _new_person_association(person_a_id, person_b_id, actor)
            _insert_person_association(conn, association)
            _record_person_operation(
                conn,
                operation_id,
                "create-placeholder-association",
                {
                    "association_id": association.association_id,
                    "source_person_id": source_person_id,
                    "target_person_id": person.person_id,
                    "relationship_type": association.relationship_type,
                    "actor_name": actor,
                },
            )
            return person, association

    def list_person_associations(
        self,
        person_id: str,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[PersonAssociation]:
        with self._connect() as conn:
            person = conn.execute(
                f"""
                SELECT 1 FROM persons
                WHERE person_id = ? {" " if include_archived else "AND deleted_at IS NULL"}
                """,
                (person_id,),
            ).fetchone()
            if person is None:
                raise KeyError(f"Unknown person: {person_id}")
            limit_clause = " LIMIT ?" if limit is not None else ""
            params: tuple = (person_id, person_id, max(1, int(limit))) if limit is not None else (person_id, person_id)
            rows = conn.execute(
                f"""
                SELECT association_id, source_person_id, target_person_id,
                       relationship_type, created_at, updated_at, created_by, association_origin
                FROM person_associations
                WHERE source_person_id = ? OR target_person_id = ?
                ORDER BY updated_at DESC, association_id
                {limit_clause}
                """,
                params,
            ).fetchall()
        return [_person_association_from_row(row) for row in rows]

    def remove_person_association(
        self,
        association_id: str,
        actor_name: str,
        operation_id: str,
    ) -> dict:
        actor = actor_name.strip()
        if not actor:
            raise KeyError("Removed by is required")
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "remove-person-association",
            )
            if existing:
                return existing
            row = conn.execute(
                "SELECT * FROM person_associations WHERE association_id = ?",
                (association_id,),
            ).fetchone()
            if row is None:
                raise KeyError("This association no longer exists")
            association = _person_association_from_row(row)
            conn.execute(
                "DELETE FROM person_associations WHERE association_id = ?",
                (association_id,),
            )
            result = {
                "association_id": association_id,
                "source_person_id": association.source_person_id,
                "target_person_id": association.target_person_id,
                "relationship_type": association.relationship_type,
                "removed": True,
                "actor_name": actor,
            }
            _record_person_operation(
                conn,
                operation_id,
                "remove-person-association",
                result,
            )
            return result

    def get_person_operation(self, operation_id: str, operation_type: str) -> dict | None:
        with self._connect() as conn:
            return _existing_person_operation(conn, operation_id, operation_type)

    def begin_operation(
        self,
        operation_type: str,
        *,
        operation_id: str | None = None,
        actor: dict | None = None,
        source: str | None = None,
        context: dict | None = None,
        affected_entities: list[dict] | None = None,
        details: dict | None = None,
    ) -> dict:
        with self._connect() as conn:
            return _begin_journal_operation(
                conn,
                operation_type,
                operation_id=operation_id,
                actor=actor,
                source=source,
                context=context,
                affected_entities=affected_entities,
                details=details,
            )

    def mark_operation_committed(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "COMMITTED", details)

    def mark_operation_failed(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "FAILED", details)

    def mark_operation_rolled_back(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "ROLLED_BACK", details)

    def mark_operation_reverted(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "REVERTED", details)

    def _mark_operation_status(
        self,
        operation_id: str,
        status: str,
        details: dict | None,
    ) -> dict:
        with self._connect() as conn:
            return _transition_journal_operation(conn, operation_id, status, details)

    def get_operation(self, operation_id: str) -> dict | None:
        with self._connect() as conn:
            return _get_journal_operation(conn, operation_id)

    def list_recent_operations(self, limit: int = 50) -> list[dict]:
        if limit < 1 or limit > 500:
            raise ValueError("Operation list limit must be between 1 and 500")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT operation_id FROM operation_journal ORDER BY created_at DESC, operation_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_get_journal_operation(conn, row["operation_id"]) for row in rows]

    def get_embedding_lifecycle(self, embedding_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.deleted_at, e.purge_after,
                       p.name AS person_name, p.deleted_at AS person_deleted_at
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
        return dict(row) if row else None

    def archive_person(self, person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "archive-person")
            if existing:
                return existing
            row = conn.execute(
                "SELECT deleted_at FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown person: {person_id}")
            archived_at = row["deleted_at"] or utc_now()
            cursor = conn.execute(
                "UPDATE persons SET deleted_at = ? WHERE person_id = ? AND deleted_at IS NULL",
                (archived_at, person_id),
            )
            result = {
                "person_id": person_id,
                "archived": True,
                "archived_at": archived_at,
                "changed": bool(cursor.rowcount),
            }
            _record_person_operation(conn, operation_id, "archive-person", result)
            return result

    def restore_person(self, person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "restore-person")
            if existing:
                return existing
            row = conn.execute(
                "SELECT deleted_at, metadata FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown person: {person_id}")
            metadata = json.loads(row["metadata"])
            if metadata.get("merged_into"):
                raise KeyError(
                    f"Merged person records cannot be restored; merged into {metadata['merged_into']}"
                )
            try:
                cursor = conn.execute(
                    "UPDATE persons SET deleted_at = NULL WHERE person_id = ? AND deleted_at IS NOT NULL",
                    (person_id,),
                )
            except sqlite3.IntegrityError as exc:
                raise _placeholder_name_conflict(exc) from exc
            result = {"person_id": person_id, "restored": True, "changed": bool(cursor.rowcount)}
            _record_person_operation(conn, operation_id, "restore-person", result)
            return result

    def list_file_references_for_person(self, person_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_image AS path FROM embeddings
                WHERE person_id = ? AND source_image IS NOT NULL
                UNION
                SELECT crop_path AS path FROM embeddings
                WHERE person_id = ? AND crop_path IS NOT NULL
                UNION
                SELECT image_path AS path FROM recognition_details
                WHERE person_id = ? AND image_path IS NOT NULL
                """,
                (person_id, person_id, person_id),
            ).fetchall()
        return [str(row["path"]) for row in rows if row["path"]]

    def permanently_delete_person(self, person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "purge-person")
            if existing:
                return existing
            person = conn.execute(
                "SELECT name, deleted_at FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if person is None:
                raise KeyError(f"Unknown person: {person_id}")
            embedding_count = int(conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            sighting_count = int(conn.execute(
                "SELECT COUNT(*) FROM recognition_details WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            change_count = int(conn.execute(
                "SELECT COUNT(*) FROM person_change_history WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            exclusion_count = int(conn.execute(
                "SELECT COUNT(*) FROM init_face_person_exclusions WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            association_rows = conn.execute(
                """
                SELECT association_id FROM person_associations
                WHERE source_person_id = ? OR target_person_id = ?
                ORDER BY association_id
                """,
                (person_id, person_id),
            ).fetchall()
            conn.execute("DELETE FROM recognition_details WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM init_face_person_exclusions WHERE person_id = ?", (person_id,))
            conn.execute(
                "DELETE FROM person_associations WHERE source_person_id = ? OR target_person_id = ?",
                (person_id, person_id),
            )
            conn.execute("DELETE FROM person_change_history WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM embeddings WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM persons WHERE person_id = ?", (person_id,))
            result = {
                "person_id": person_id,
                "person_name": person["name"],
                "was_archived": person["deleted_at"] is not None,
                "deleted": True,
                "permanent": True,
                "deleted_embeddings": embedding_count,
                "deleted_sightings": sighting_count,
                "deleted_profile_changes": change_count,
                "deleted_queue_exclusions": exclusion_count,
                "deleted_associations": len(association_rows),
                "deleted_association_ids": [row["association_id"] for row in association_rows],
            }
            _record_person_operation(conn, operation_id, "purge-person", result)
            return result

    def delete_embedding(self, embedding_id: str, operation_id: str) -> dict:
        """Soft-delete a face for 30 days while retaining its linked sightings."""
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "soft-delete-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT e.person_id, e.source_image, e.crop_path, e.deleted_at,
                       e.purge_after, p.metadata
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown embedding: {embedding_id}")
            if row["deleted_at"]:
                raise KeyError("Face is already in Deleted Faces")
            detail_count = conn.execute(
                "SELECT COUNT(*) FROM recognition_details WHERE embedding_id = ?",
                (embedding_id,),
            ).fetchone()[0]
            deleted_at = utc_now()
            purge_after = (
                datetime.fromisoformat(deleted_at)
                + timedelta(days=DELETED_FACE_RETENTION_DAYS)
            ).isoformat()
            conn.execute(
                """
                UPDATE embeddings
                SET deleted_at = ?, purge_after = ?
                WHERE embedding_id = ? AND deleted_at IS NULL
                """,
                (deleted_at, purge_after, embedding_id),
            )
            metadata = json.loads(row["metadata"])
            if metadata.get("representative_embedding_id") == embedding_id:
                metadata.pop("representative_embedding_id", None)
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(metadata, separators=(",", ":")), row["person_id"]),
                )
            result = {
                "embedding_id": embedding_id,
                "person_id": row["person_id"],
                "deleted": True,
                "permanent": False,
                "retained_sightings": detail_count,
                "deleted_at": deleted_at,
                "purge_after": purge_after,
                "source_image": row["source_image"],
                "crop_path": row["crop_path"],
            }
            _record_person_operation(conn, operation_id, "soft-delete-embedding", result)
            return result

    def list_deleted_embeddings(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.quality_score,
                       e.source_image, e.crop_path, e.created_at,
                       e.deleted_at, e.purge_after,
                       p.name, p.deleted_at AS person_deleted_at,
                       COUNT(d.detail_id) AS sighting_count
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                LEFT JOIN recognition_details d ON d.embedding_id = e.embedding_id
                WHERE e.deleted_at IS NOT NULL
                GROUP BY e.embedding_id
                ORDER BY e.deleted_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def restore_deleted_embedding(self, embedding_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "restore-deleted-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT e.person_id, e.deleted_at, e.purge_after, p.deleted_at AS person_deleted_at,
                       p.metadata
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown deleted face: {embedding_id}")
            if row["deleted_at"] is None:
                raise KeyError("Face is not deleted")
            if row["person_deleted_at"] is not None:
                raise KeyError("Restore the archived person before restoring this face")
            conn.execute(
                """
                UPDATE embeddings
                SET deleted_at = NULL, purge_after = NULL
                WHERE embedding_id = ? AND deleted_at IS NOT NULL
                """,
                (embedding_id,),
            )
            metadata = json.loads(row["metadata"])
            if not metadata.get("representative_embedding_id"):
                metadata["representative_embedding_id"] = embedding_id
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(metadata, separators=(",", ":")), row["person_id"]),
                )
            result = {
                "embedding_id": embedding_id,
                "person_id": row["person_id"],
                "restored": True,
                "previously_deleted_at": row["deleted_at"],
            }
            _record_person_operation(conn, operation_id, "restore-deleted-embedding", result)
            return result

    def permanently_delete_embedding(self, embedding_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "purge-deleted-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT person_id, source_image, crop_path, deleted_at, purge_after
                FROM embeddings
                WHERE embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown deleted face: {embedding_id}")
            if row["deleted_at"] is None:
                raise KeyError("Move the face to Deleted Faces before deleting it permanently")
            detail_count = conn.execute(
                "SELECT COUNT(*) FROM recognition_details WHERE embedding_id = ?",
                (embedding_id,),
            ).fetchone()[0]
            conn.execute("DELETE FROM recognition_details WHERE embedding_id = ?", (embedding_id,))
            conn.execute("DELETE FROM embeddings WHERE embedding_id = ?", (embedding_id,))
            result = {
                "embedding_id": embedding_id,
                "person_id": row["person_id"],
                "deleted": True,
                "permanent": True,
                "deleted_sightings": detail_count,
                "source_image": row["source_image"],
                "crop_path": row["crop_path"],
                "previously_deleted_at": row["deleted_at"],
                "previous_purge_after": row["purge_after"],
            }
            _record_person_operation(conn, operation_id, "purge-deleted-embedding", result)
            return result

    def list_expired_deleted_embedding_ids(self, now: str | None = None) -> list[str]:
        cutoff = now or utc_now()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT embedding_id
                FROM embeddings
                WHERE deleted_at IS NOT NULL
                  AND purge_after IS NOT NULL
                  AND purge_after <= ?
                ORDER BY purge_after ASC
                """,
                (cutoff,),
            ).fetchall()
        return [row["embedding_id"] for row in rows]

    def purge_expired_deleted_embeddings(
        self,
        embedding_ids: list[str],
        operation_id: str,
        now: str | None = None,
    ) -> dict:
        unique_ids = list(dict.fromkeys(embedding_ids))
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "purge-expired-embeddings",
            )
            if existing:
                return existing
            if not unique_ids:
                result = {
                    "embedding_ids": [],
                    "person_ids": [],
                    "purged": 0,
                    "deleted_sightings": 0,
                }
                _record_person_operation(
                    conn,
                    operation_id,
                    "purge-expired-embeddings",
                    result,
                )
                return result
            placeholders = ", ".join("?" for _ in unique_ids)
            rows = conn.execute(
                f"""
                SELECT embedding_id, person_id, source_image, crop_path
                FROM embeddings
                WHERE embedding_id IN ({placeholders})
                  AND deleted_at IS NOT NULL
                  AND purge_after IS NOT NULL
                  AND purge_after <= ?
                ORDER BY embedding_id
                """,
                (*unique_ids, now or utc_now()),
            ).fetchall()
            eligible_ids = [row["embedding_id"] for row in rows]
            detail_count = 0
            if eligible_ids:
                eligible_placeholders = ", ".join("?" for _ in eligible_ids)
                detail_count = conn.execute(
                    f"""
                    SELECT COUNT(*) FROM recognition_details
                    WHERE embedding_id IN ({eligible_placeholders})
                    """,
                    eligible_ids,
                ).fetchone()[0]
                conn.execute(
                    f"DELETE FROM recognition_details WHERE embedding_id IN ({eligible_placeholders})",
                    eligible_ids,
                )
                conn.execute(
                    f"DELETE FROM embeddings WHERE embedding_id IN ({eligible_placeholders})",
                    eligible_ids,
                )
            result = {
                "embedding_ids": eligible_ids,
                "person_ids": sorted({row["person_id"] for row in rows}),
                "purged": len(eligible_ids),
                "deleted_sightings": detail_count,
                "paths": [
                    {
                        "source_image": row["source_image"],
                        "crop_path": row["crop_path"],
                    }
                    for row in rows
                ],
            }
            _record_person_operation(
                conn,
                operation_id,
                "purge-expired-embeddings",
                result,
            )
            return result

    def move_embedding(self, embedding_id: str, person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "move-embedding")
            if existing:
                return existing
            target = conn.execute(
                "SELECT name, metadata FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (person_id,),
            ).fetchone()
            if target is None:
                raise KeyError(f"Unknown person: {person_id}")
            embedding = conn.execute(
                """
                SELECT e.person_id, p.metadata
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ?
                  AND e.deleted_at IS NULL
                  AND p.deleted_at IS NULL
                """,
                (embedding_id,),
            ).fetchone()
            if embedding is None:
                raise KeyError(f"Unknown embedding: {embedding_id}")
            source_person_id = embedding["person_id"]
            if source_person_id == person_id:
                result = {
                    "embedding_id": embedding_id,
                    "source_person_id": source_person_id,
                    "target_person_id": person_id,
                    "moved": True,
                    "changed": False,
                    "moved_sightings": 0,
                }
                _record_person_operation(conn, operation_id, "move-embedding", result)
                return result
            conn.execute(
                "UPDATE embeddings SET person_id = ? WHERE embedding_id = ?",
                (person_id, embedding_id),
            )
            _mark_person_enrolled(conn, person_id)
            detail_cursor = conn.execute(
                """
                UPDATE recognition_details
                SET person_id = ?, name = ?
                WHERE embedding_id = ?
                """,
                (person_id, target["name"], embedding_id),
            )
            source_metadata = json.loads(embedding["metadata"])
            if source_metadata.get("representative_embedding_id") == embedding_id:
                source_metadata.pop("representative_embedding_id", None)
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(source_metadata, separators=(",", ":")), source_person_id),
                )
            target_metadata = json.loads(target["metadata"])
            if not target_metadata.get("representative_embedding_id"):
                target_metadata["representative_embedding_id"] = embedding_id
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(target_metadata, separators=(",", ":")), person_id),
                )
            result = {
                "embedding_id": embedding_id,
                "source_person_id": source_person_id,
                "target_person_id": person_id,
                "moved": True,
                "changed": True,
                "moved_sightings": detail_cursor.rowcount,
            }
            _record_person_operation(conn, operation_id, "move-embedding", result)
            return result

    def merge_persons(self, source_person_id: str, target_person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "merge-persons")
            if existing:
                return existing
            if source_person_id == target_person_id:
                raise KeyError("Source and target person must be different")
            source = conn.execute(
                "SELECT name, metadata, deleted_at, enrollment_status FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (source_person_id,),
            ).fetchone()
            target = conn.execute(
                "SELECT name, metadata, deleted_at, enrollment_status FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (target_person_id,),
            ).fetchone()
            if source is None:
                raise KeyError(f"Unknown source person: {source_person_id}")
            if target is None:
                raise KeyError(f"Unknown target person: {target_person_id}")
            embedding_rows = conn.execute(
                "SELECT embedding_id, deleted_at FROM embeddings WHERE person_id = ? ORDER BY embedding_id",
                (source_person_id,),
            ).fetchall()
            detail_rows = conn.execute(
                "SELECT detail_id, name FROM recognition_details WHERE person_id = ? ORDER BY detail_id",
                (source_person_id,),
            ).fetchall()
            source_exclusions = conn.execute(
                "SELECT session_id, init_face_id FROM init_face_person_exclusions WHERE person_id = ? ORDER BY session_id, init_face_id",
                (source_person_id,),
            ).fetchall()
            target_exclusions = conn.execute(
                "SELECT session_id, init_face_id FROM init_face_person_exclusions WHERE person_id = ? ORDER BY session_id, init_face_id",
                (target_person_id,),
            ).fetchall()
            moved_embeddings = sum(1 for row in embedding_rows if row["deleted_at"] is None)
            moved_deleted_faces = sum(1 for row in embedding_rows if row["deleted_at"] is not None)
            moved_sightings = len(detail_rows)
            original_source_metadata = json.loads(source["metadata"])
            original_target_metadata = json.loads(target["metadata"])
            conn.execute(
                "UPDATE embeddings SET person_id = ? WHERE person_id = ?",
                (target_person_id, source_person_id),
            )
            if embedding_rows:
                _mark_person_enrolled(conn, target_person_id)
            conn.execute(
                """
                UPDATE recognition_details
                SET person_id = ?, name = ?
                WHERE person_id = ?
                """,
                (target_person_id, target["name"], source_person_id),
            )
            source_metadata = dict(original_source_metadata)
            target_metadata = dict(original_target_metadata)
            merged_tags = _normalize_tags([
                *target_metadata.get("tags", []),
                *source_metadata.get("tags", []),
            ])
            if merged_tags:
                target_metadata["tags"] = merged_tags
            target_metadata["favorite"] = bool(
                target_metadata.get("favorite") or source_metadata.get("favorite")
            )
            if not target_metadata.get("representative_embedding_id"):
                source_representative = source_metadata.get("representative_embedding_id")
                if source_representative:
                    target_metadata["representative_embedding_id"] = source_representative
            conn.execute(
                "UPDATE persons SET metadata = ? WHERE person_id = ?",
                (json.dumps(target_metadata, separators=(",", ":")), target_person_id),
            )
            source_metadata["merged_into"] = target_person_id
            source_metadata["merged_at"] = utc_now()
            conn.execute(
                """
                UPDATE persons
                SET metadata = ?, deleted_at = ?
                WHERE person_id = ?
                """,
                (
                    json.dumps(source_metadata, separators=(",", ":")),
                    source_metadata["merged_at"],
                    source_person_id,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO init_face_person_exclusions(
                    session_id, init_face_id, person_id, created_at
                )
                SELECT session_id, init_face_id, ?, created_at
                FROM init_face_person_exclusions
                WHERE person_id = ?
                """,
                (target_person_id, source_person_id),
            )
            conn.execute(
                "DELETE FROM init_face_person_exclusions WHERE person_id = ?",
                (source_person_id,),
            )
            result = {
                "source_person_id": source_person_id,
                "target_person_id": target_person_id,
                "merged": True,
                "moved_embeddings": moved_embeddings,
                "moved_deleted_faces": moved_deleted_faces,
                "moved_sightings": moved_sightings,
                "undo_supported": True,
                "undo_snapshot": {
                    "source_name": source["name"],
                    "target_name": target["name"],
                    "source_metadata": original_source_metadata,
                    "target_metadata": original_target_metadata,
                    "source_status": source["enrollment_status"],
                    "target_status": target["enrollment_status"],
                    "merged_source_metadata": source_metadata,
                    "merged_target_metadata": target_metadata,
                    "embedding_ids": [row["embedding_id"] for row in embedding_rows],
                    "embedding_states": [
                        {
                            "embedding_id": row["embedding_id"],
                            "deleted_at": row["deleted_at"],
                        }
                        for row in embedding_rows
                    ],
                    "details": [
                        {"detail_id": row["detail_id"], "name": row["name"]}
                        for row in detail_rows
                    ],
                    "source_exclusions": [dict(row) for row in source_exclusions],
                    "target_exclusions": [dict(row) for row in target_exclusions],
                },
            }
            _record_person_operation(conn, operation_id, "merge-persons", result)
            return result

    def undo_merge_persons(self, merge_operation_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "undo-merge-persons")
            if existing:
                return existing
            merge = _existing_person_operation(conn, merge_operation_id, "merge-persons")
            if merge is None:
                raise KeyError("Unknown merge operation")
            snapshot = merge.get("undo_snapshot")
            if not snapshot:
                raise KeyError("This older merge cannot be undone safely from profile history")
            source_person_id = str(merge["source_person_id"])
            target_person_id = str(merge["target_person_id"])
            prior_undo = conn.execute(
                "SELECT 1 FROM person_operations WHERE operation_type = 'undo-merge-persons' AND json_extract(result, '$.merge_operation_id') = ?",
                (merge_operation_id,),
            ).fetchone()
            if prior_undo:
                raise KeyError("This merge has already been undone")
            source = conn.execute(
                "SELECT metadata, deleted_at FROM persons WHERE person_id = ?",
                (source_person_id,),
            ).fetchone()
            target = conn.execute(
                "SELECT metadata, deleted_at FROM persons WHERE person_id = ?",
                (target_person_id,),
            ).fetchone()
            if source is None or target is None:
                raise KeyError("One of the merged profiles no longer exists")
            if target["deleted_at"] is not None:
                raise KeyError("Restore the kept profile before undoing this merge")
            if json.loads(source["metadata"]) != snapshot["merged_source_metadata"]:
                raise KeyError("The merged record changed after the merge; undo was not applied")
            if json.loads(target["metadata"]) != snapshot["merged_target_metadata"]:
                raise KeyError("The kept profile changed after the merge; undo was not applied")
            embedding_ids = list(snapshot.get("embedding_ids") or [])
            if embedding_ids:
                placeholders = ", ".join("?" for _ in embedding_ids)
                rows = conn.execute(
                    f"SELECT embedding_id, person_id, deleted_at FROM embeddings WHERE embedding_id IN ({placeholders})",
                    embedding_ids,
                ).fetchall()
                expected_embedding_states = {
                    str(item["embedding_id"]): item.get("deleted_at")
                    for item in snapshot.get("embedding_states") or []
                }
                if len(rows) != len(embedding_ids) or any(
                    row["person_id"] != target_person_id
                    or (
                        expected_embedding_states
                        and row["deleted_at"] != expected_embedding_states.get(str(row["embedding_id"]))
                    )
                    for row in rows
                ):
                    raise KeyError("Merged photos changed after the merge; undo was not applied")
                detail_ids = {str(item["detail_id"]) for item in snapshot.get("details") or []}
                linked_details = conn.execute(
                    f"SELECT detail_id, person_id, name FROM recognition_details WHERE embedding_id IN ({placeholders})",
                    embedding_ids,
                ).fetchall()
                if any(
                    row["person_id"] != target_person_id
                    or row["detail_id"] not in detail_ids
                    or row["name"] != snapshot["target_name"]
                    for row in linked_details
                ):
                    raise KeyError("Merged sightings changed after the merge; undo was not applied")
                conn.execute(
                    f"UPDATE embeddings SET person_id = ? WHERE embedding_id IN ({placeholders})",
                    (source_person_id, *embedding_ids),
                )
            for detail in snapshot.get("details") or []:
                cursor = conn.execute(
                    "UPDATE recognition_details SET person_id = ?, name = ? WHERE detail_id = ? AND person_id = ?",
                    (source_person_id, detail["name"], detail["detail_id"], target_person_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError("A merged sighting changed after the merge; undo was not applied")
            conn.execute(
                "UPDATE persons SET metadata = ?, deleted_at = NULL, enrollment_status = ? WHERE person_id = ?",
                (
                    json.dumps(snapshot["source_metadata"], separators=(",", ":")),
                    snapshot.get("source_status", "enrolled"),
                    source_person_id,
                ),
            )
            conn.execute(
                "UPDATE persons SET metadata = ?, enrollment_status = ? WHERE person_id = ?",
                (
                    json.dumps(snapshot["target_metadata"], separators=(",", ":")),
                    snapshot.get("target_status", "enrolled"),
                    target_person_id,
                ),
            )
            source_exclusions = snapshot.get("source_exclusions") or []
            target_exclusions = snapshot.get("target_exclusions") or []
            affected = {
                (item["session_id"], item["init_face_id"])
                for item in [*source_exclusions, *target_exclusions]
            }
            expected_target_exclusions = affected
            if affected:
                current_exclusions = conn.execute(
                    "SELECT session_id, init_face_id, person_id FROM init_face_person_exclusions WHERE person_id IN (?, ?)",
                    (source_person_id, target_person_id),
                ).fetchall()
                current_source = {
                    (row["session_id"], row["init_face_id"])
                    for row in current_exclusions
                    if row["person_id"] == source_person_id
                }
                current_target = {
                    (row["session_id"], row["init_face_id"])
                    for row in current_exclusions
                    if row["person_id"] == target_person_id
                    and (row["session_id"], row["init_face_id"]) in affected
                }
                if current_source.intersection(affected) or current_target != expected_target_exclusions:
                    raise KeyError("Merge exclusions changed after the merge; undo was not applied")
            for session_id, init_face_id in affected:
                conn.execute(
                    "DELETE FROM init_face_person_exclusions WHERE session_id = ? AND init_face_id = ? AND person_id IN (?, ?)",
                    (session_id, init_face_id, source_person_id, target_person_id),
                )
            now = utc_now()
            conn.executemany(
                "INSERT OR IGNORE INTO init_face_person_exclusions(session_id, init_face_id, person_id, created_at) VALUES (?, ?, ?, ?)",
                [(item["session_id"], item["init_face_id"], source_person_id, now) for item in source_exclusions]
                + [(item["session_id"], item["init_face_id"], target_person_id, now) for item in target_exclusions],
            )
            result = {
                "source_person_id": source_person_id,
                "target_person_id": target_person_id,
                "merge_operation_id": merge_operation_id,
                "restored_embeddings": len(embedding_ids),
                "restored_sightings": len(snapshot.get("details") or []),
                "undone": True,
            }
            _record_person_operation(conn, operation_id, "undo-merge-persons", result)
            return result

    def update_person_preferences(
        self,
        person_id: str,
        operation_id: str,
        favorite: bool | None = None,
        representative_embedding_id: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "person-preferences")
            if existing:
                return existing
            person = conn.execute(
                "SELECT metadata FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (person_id,),
            ).fetchone()
            if person is None:
                raise KeyError(f"Unknown person: {person_id}")
            metadata = json.loads(person["metadata"])
            changed_preferences = []
            if favorite is not None:
                metadata["favorite"] = bool(favorite)
                changed_preferences.append("favorite")
            if representative_embedding_id is not None:
                owned = conn.execute(
                    """
                    SELECT 1 FROM embeddings
                    WHERE embedding_id = ? AND person_id = ? AND deleted_at IS NULL
                    """,
                    (representative_embedding_id, person_id),
                ).fetchone()
                if owned is None:
                    raise KeyError(
                        f"Embedding {representative_embedding_id} does not belong to person {person_id}"
                    )
                metadata["representative_embedding_id"] = representative_embedding_id
                changed_preferences.append("representative_photo")
            conn.execute(
                "UPDATE persons SET metadata = ? WHERE person_id = ?",
                (json.dumps(metadata, separators=(",", ":")), person_id),
            )
            result = {
                "person_id": person_id,
                "favorite": bool(metadata.get("favorite")),
                "representative_embedding_id": metadata.get("representative_embedding_id"),
                "changed_preferences": changed_preferences,
                "updated": True,
            }
            _record_person_operation(conn, operation_id, "person-preferences", result)
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
    ) -> RecognitionDetail:
        detail = RecognitionDetail(
            detail_id=str(uuid.uuid4()),
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
            notes=notes.strip(),
            created_at=utc_now(),
        )
        with self._connect() as conn:
            if operation_id:
                existing = _begin_person_operation(conn, operation_id, "recognition-followup")
                if existing:
                    row = conn.execute(
                        "SELECT * FROM recognition_details WHERE detail_id = ?",
                        (str(existing["detail_id"]),),
                    ).fetchone()
                    if row is None:
                        raise RuntimeError("Recognition follow-up operation is missing its detail")
                    return _recognition_detail_from_row(row)
            owned = conn.execute(
                """
                SELECT 1
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ? AND e.person_id = ?
                  AND e.deleted_at IS NULL AND p.deleted_at IS NULL
                """,
                (embedding_id, person_id),
            ).fetchone()
            if owned is None:
                raise KeyError("Recognition detail must reference an active face owned by the person")
            conn.execute(
                """
                INSERT INTO recognition_details(
                    detail_id, embedding_id, person_id, image_id, image_path,
                    name, decision, seen_date, seen_time, place_seen,
                    individual_count, event_occasion, rank, country,
                    importance, added_by, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    detail.detail_id,
                    detail.embedding_id,
                    detail.person_id,
                    detail.image_id,
                    detail.image_path,
                    detail.name,
                    detail.decision,
                    detail.seen_date,
                    detail.seen_time,
                    detail.place_seen,
                    detail.individual_count,
                    detail.event_occasion,
                    detail.rank,
                    detail.country,
                    detail.importance,
                    detail.added_by,
                    detail.notes,
                    detail.created_at,
                ),
            )
            profile_updates = {
                key: value
                for key, value in {
                    "rank": rank,
                    "country": country,
                    "importance": importance,
                }.items()
                if value
            }
            creator_name = added_by.strip() if decision == "new" and added_by and added_by.strip() else ""
            if profile_updates or creator_name:
                row = conn.execute(
                    "SELECT metadata FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if row is not None:
                    metadata = json.loads(row["metadata"])
                    metadata.update(profile_updates)
                    if creator_name:
                        metadata.setdefault("added_by", creator_name)
                    conn.execute(
                        "UPDATE persons SET metadata = ? WHERE person_id = ? AND deleted_at IS NULL",
                        (json.dumps(metadata, separators=(",", ":")), person_id),
                    )
            automatic_associations = _create_note_associations(
                conn, person_id, detail.notes, (added_by or "").strip(), mentioned_person_ids or [],
            )
            if operation_id:
                _record_person_operation(
                    conn,
                    operation_id,
                    "recognition-followup",
                    {
                        "detail_id": detail.detail_id,
                        "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                        "automatic_association_ids": [item.association_id for item in automatic_associations],
                    },
                )
        return detail

    def list_recognition_details_for_embedding(self, embedding_id: str) -> list[RecognitionDetail]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT detail_id, embedding_id, person_id, image_id, image_path,
                       name, decision, seen_date, seen_time, place_seen,
                       individual_count, event_occasion, rank, country,
                       importance, added_by, notes, created_at
                FROM recognition_details
                WHERE embedding_id = ?
                ORDER BY created_at ASC
                """,
                (embedding_id,),
            ).fetchall()
        return [_recognition_detail_from_row(row) for row in rows]

    def list_recognition_details_for_person(self, person_id: str) -> list[RecognitionDetail]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.detail_id, d.embedding_id, d.person_id, d.image_id, d.image_path,
                       d.name, d.decision, d.seen_date, d.seen_time, d.place_seen,
                       d.individual_count, d.event_occasion, d.rank, d.country,
                       d.importance, d.added_by, d.notes, d.created_at
                FROM recognition_details d
                JOIN embeddings e ON e.embedding_id = d.embedding_id
                WHERE d.person_id = ? AND e.deleted_at IS NULL
                ORDER BY d.seen_date DESC, d.seen_time DESC, d.created_at DESC
                """,
                (person_id,),
            ).fetchall()
        return [_recognition_detail_from_row(row) for row in rows]

    def backup_to(self, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source:
            with closing(connect_database(target_path, self.database_key)) as target:
                source.backup(target)

    def add_embedding(
        self,
        person_id: str,
        vector: Embedding,
        quality_score: float,
        source_image: str | None = None,
        crop_path: str | None = None,
    ) -> EmbeddingRecord:
        if len(vector) != self.embedding_dim:
            raise ValueError(f"Expected {self.embedding_dim} dimensions, got {len(vector)}")
        record = EmbeddingRecord(
            embedding_id=str(uuid.uuid4()),
            person_id=person_id,
            vector=tuple(vector),
            quality_score=quality_score,
            source_image=source_image,
            crop_path=crop_path,
            created_at=utc_now(),
        )
        with self._connect() as conn:
            person_exists = conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (person_id,),
            ).fetchone()
            if person_exists is None:
                raise KeyError(f"Unknown person: {person_id}")
            conn.execute(
                """
                INSERT INTO embeddings(
                    embedding_id, person_id, vector, quality_score,
                    source_image, crop_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.embedding_id,
                    record.person_id,
                    _pack_embedding(record.vector),
                    record.quality_score,
                    record.source_image,
                    record.crop_path,
                    record.created_at,
                ),
            )
            _mark_person_enrolled(conn, person_id)
        return record

    def list_embeddings(self) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.vector, e.quality_score,
                       e.source_image, e.crop_path, e.created_at
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE p.deleted_at IS NULL AND e.deleted_at IS NULL
                """
            ).fetchall()
        return [_embedding_from_row(row) for row in rows]

    def save_pending_addition(self, pending: PendingAddition) -> None:
        if len(pending.vector) != self.embedding_dim:
            raise ValueError(f"Expected {self.embedding_dim} dimensions, got {len(pending.vector)}")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_additions(
                    pending_id, source_image, box_x, box_y, box_width, box_height,
                    box_confidence, quality_score, landmarks, crop_path, vector,
                    matches, decision, quality_status, pending_quality_score,
                    quality_reasons, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending.pending_id,
                    pending.source_image,
                    pending.face.box.x,
                    pending.face.box.y,
                    pending.face.box.width,
                    pending.face.box.height,
                    pending.face.box.confidence,
                    pending.face.quality_score,
                    json.dumps(pending.face.landmarks),
                    pending.face.crop_path,
                    _pack_embedding(pending.vector),
                    json.dumps(
                        [
                            {
                                "person_id": match.person_id,
                                "score": match.score,
                                "embedding_ids": list(match.embedding_ids),
                                "embeddings_matched": match.embeddings_matched,
                            }
                            for match in pending.matches
                        ]
                    ),
                    pending.decision.value,
                    pending.quality.status.value,
                    pending.quality.score,
                    json.dumps(pending.quality.reasons),
                    pending.created_at,
                ),
            )

    def get_pending_addition(self, pending_id: str) -> PendingAddition | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pending_id, source_image, box_x, box_y, box_width, box_height,
                       box_confidence, quality_score, landmarks, crop_path, vector,
                       matches, decision, quality_status, pending_quality_score,
                       quality_reasons, created_at
                FROM pending_additions
                WHERE pending_id = ?
                """,
                (pending_id,),
            ).fetchone()
        return _pending_from_row(row) if row else None

    def list_pending_additions(self) -> list[PendingAddition]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT pending_id, source_image, box_x, box_y, box_width, box_height,
                       box_confidence, quality_score, landmarks, crop_path, vector,
                       matches, decision, quality_status, pending_quality_score,
                       quality_reasons, created_at
                FROM pending_additions
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [_pending_from_row(row) for row in rows]

    def list_all_file_references(self) -> list[str]:
        """Return paths from active, archived, deleted, pending, and queue state."""
        queries = (
            "SELECT source_image AS path FROM embeddings WHERE source_image IS NOT NULL",
            "SELECT crop_path AS path FROM embeddings WHERE crop_path IS NOT NULL",
            "SELECT image_path AS path FROM recognition_details WHERE image_path IS NOT NULL",
            "SELECT source_image AS path FROM pending_additions WHERE source_image IS NOT NULL",
            "SELECT crop_path AS path FROM pending_additions WHERE crop_path IS NOT NULL",
            "SELECT source_path AS path FROM init_sessions WHERE source_path IS NOT NULL",
            "SELECT source_image AS path FROM init_faces WHERE source_image IS NOT NULL",
            "SELECT crop_path AS path FROM init_faces WHERE crop_path IS NOT NULL",
        )
        with self._connect() as conn:
            return [
                str(row["path"])
                for query in queries
                for row in conn.execute(query).fetchall()
                if row["path"]
            ]

    def confirm_pending_addition(
        self,
        pending_id: str,
        operation_id: str,
        *,
        person_id: str | None = None,
        name: str | None = None,
        metadata: dict | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
        recognition_detail: dict | None = None,
    ) -> tuple[Person, EmbeddingRecord]:
        operation_type = "confirm-pending-existing" if person_id else "confirm-pending-new"
        creating_new_person = person_id is None
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, operation_type)
            if existing:
                # A lost-response retry may have re-prepared the same face.
                # The committed operation wins; discard the retry-only row.
                conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))
                return self._confirmed_records(
                    conn, str(existing["person_id"]), str(existing["embedding_id"])
                )
            pending_row = conn.execute(
                "SELECT * FROM pending_additions WHERE pending_id = ?", (pending_id,)
            ).fetchone()
            if pending_row is None:
                raise KeyError(f"Unknown pending addition: {pending_id}")
            if person_id:
                person_row = conn.execute(
                    "SELECT 1 FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError(f"Unknown person: {person_id}")
            else:
                if not name or not name.strip():
                    raise KeyError("Person name is required")
                person_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO persons(person_id, name, metadata, created_at, notes) VALUES (?, ?, ?, ?, ?)",
                    (
                        person_id,
                        name.strip(),
                        json.dumps(metadata or {}, separators=(",", ":")),
                        utc_now(),
                        notes.strip(),
                    ),
                )
                automatic_associations = _create_note_associations(
                    conn, person_id, notes.strip(), "SentriFace", mentioned_person_ids or [],
                )
            if not creating_new_person:
                automatic_associations = []
            embedding_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO embeddings(
                    embedding_id, person_id, vector, quality_score,
                    source_image, crop_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    embedding_id,
                    person_id,
                    pending_row["vector"],
                    pending_row["quality_score"],
                    pending_row["source_image"],
                    pending_row["crop_path"],
                    utc_now(),
                ),
            )
            _mark_person_enrolled(conn, person_id)
            detail_id = None
            if recognition_detail is not None:
                detail_id = str(uuid.uuid4())
                detail_notes = str(recognition_detail.get("notes") or "").strip()
                conn.execute(
                    """
                    INSERT INTO recognition_details(
                        detail_id, embedding_id, person_id, image_id, image_path,
                        name, decision, seen_date, seen_time, place_seen,
                        individual_count, event_occasion, rank, country,
                        importance, added_by, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail_id, embedding_id, person_id,
                        recognition_detail["image_id"], recognition_detail.get("image_path"),
                        recognition_detail["name"], recognition_detail.get("decision", "existing"),
                        recognition_detail["seen_date"], recognition_detail["seen_time"],
                        recognition_detail["place_seen"], int(recognition_detail["individual_count"]),
                        recognition_detail["event_occasion"], recognition_detail.get("rank"),
                        recognition_detail.get("country"), recognition_detail.get("importance"),
                        recognition_detail.get("added_by"), detail_notes, utc_now(),
                    ),
                )
                automatic_associations.extend(_create_note_associations(
                    conn, person_id, detail_notes,
                    str(recognition_detail.get("added_by") or "").strip(),
                    list(recognition_detail.get("mentioned_person_ids") or []),
                ))
            conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))
            _record_person_operation(
                conn,
                operation_id,
                operation_type,
                {
                    "person_id": person_id,
                    "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                    "embedding_id": embedding_id,
                    "detail_id": detail_id,
                    "automatic_association_ids": [item.association_id for item in automatic_associations],
                },
            )
            return self._confirmed_records(conn, person_id, embedding_id)

    @staticmethod
    def _confirmed_records(
        conn: sqlite3.Connection,
        person_id: str,
        embedding_id: str,
    ) -> tuple[Person, EmbeddingRecord]:
        person_row = conn.execute(
            "SELECT person_id, name, metadata, created_at, deleted_at, enrollment_status FROM persons WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        embedding_row = conn.execute(
            """
            SELECT embedding_id, person_id, vector, quality_score,
                   source_image, crop_path, created_at
            FROM embeddings WHERE embedding_id = ?
            """,
            (embedding_id,),
        ).fetchone()
        if person_row is None or embedding_row is None:
            raise RuntimeError("Confirmed identity operation is missing durable records")
        person = _person_from_row(person_row)
        return person, _embedding_from_row(embedding_row)
    def delete_pending_addition(self, pending_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))

    def create_init_session(self, source_path: str) -> InitSession:
        session = InitSession(
            session_id=str(uuid.uuid4()),
            source_path=source_path,
            status="pending",
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO init_sessions(session_id, source_path, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session.session_id, session.source_path, session.status, session.created_at),
            )
        return session

    def save_init_faces(self, faces: list[InitFace]) -> None:
        if not faces:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO init_faces(
                    init_face_id, session_id, group_id, source_image,
                    box_x, box_y, box_width, box_height, box_confidence,
                    face_quality_score, landmarks, crop_path, vector,
                    quality_status, quality_score, quality_reasons, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        face.init_face_id,
                        face.session_id,
                        face.group_id,
                        face.source_image,
                        face.face.box.x,
                        face.face.box.y,
                        face.face.box.width,
                        face.face.box.height,
                        face.face.box.confidence,
                        face.face.quality_score,
                        json.dumps(face.face.landmarks),
                        face.face.crop_path,
                        _pack_embedding(face.vector),
                        face.quality.status.value,
                        face.quality.score,
                        json.dumps(face.quality.reasons),
                        face.created_at,
                    )
                    for face in faces
                ],
            )

    def get_init_session(self, session_id: str) -> InitSession | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, source_path, status, created_at
                FROM init_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return InitSession(
            session_id=row["session_id"],
            source_path=row["source_path"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def list_init_sessions(self) -> list[InitSession]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, source_path, status, created_at
                FROM init_sessions
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            InitSession(
                session_id=row["session_id"],
                source_path=row["source_path"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_init_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM init_face_person_exclusions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_groups WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_faces WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_sessions WHERE session_id = ?", (session_id,))

    def list_init_groups(self, session_id: str) -> list[InitGroup]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.*, COALESCE(g.status, 'pending') AS group_status
                FROM init_faces f
                LEFT JOIN init_groups g
                  ON g.session_id = f.session_id AND g.group_id = f.group_id
                WHERE f.session_id = ?
                ORDER BY f.group_id, f.created_at
                """,
                (session_id,),
            ).fetchall()
        groups: dict[str, InitGroup] = {}
        for row in rows:
            group_id = row["group_id"]
            if group_id not in groups:
                groups[group_id] = InitGroup(
                    group_id=group_id,
                    session_id=session_id,
                    status=row["group_status"],
                    faces=[],
                )
            groups[group_id].faces.append(_init_face_from_row(row))
        return list(groups.values())

    def mark_init_group_status(self, session_id: str, group_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO init_groups(session_id, group_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, group_id)
                DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (session_id, group_id, status, utc_now()),
            )

    def confirm_init_faces_atomic(
        self,
        session_id: str,
        group_id: str,
        init_face_ids: list[str],
        operation_id: str,
        *,
        person_id: str | None = None,
        name: str | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> dict:
        operation_type = "confirm-init-existing" if person_id else "confirm-init-new"
        creating_new_person = person_id is None
        selected_ids = list(dict.fromkeys(item for item in init_face_ids if item))
        if not selected_ids:
            raise KeyError("Select at least one image")
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, operation_type)
            if existing:
                return existing
            placeholders = ", ".join("?" for _ in selected_ids)
            rows = conn.execute(
                f"""
                SELECT * FROM init_faces
                WHERE session_id = ? AND group_id = ?
                  AND init_face_id IN ({placeholders})
                ORDER BY created_at
                """,
                (session_id, group_id, *selected_ids),
            ).fetchall()
            if len(rows) != len(selected_ids):
                raise KeyError("One or more selected images are no longer in this group")
            status_row = conn.execute(
                "SELECT status FROM init_groups WHERE session_id = ? AND group_id = ?",
                (session_id, group_id),
            ).fetchone()
            if status_row is not None and status_row["status"] != "pending":
                raise KeyError(f"Queue group is not pending: {group_id}")
            if person_id:
                person_row = conn.execute(
                    "SELECT 1 FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError(f"Unknown person: {person_id}")
            else:
                if not name or not name.strip():
                    raise KeyError("Person name is required")
                person_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO persons(person_id, name, metadata, created_at, notes) VALUES (?, ?, '{}', ?, ?)",
                    (person_id, name.strip(), utc_now(), notes.strip()),
                )
                automatic_associations = _create_note_associations(
                    conn, person_id, notes.strip(), "SentriFace", mentioned_person_ids or [],
                )
            if not creating_new_person:
                automatic_associations = []
            existing_embeddings = conn.execute(
                """
                SELECT embedding_id, vector FROM embeddings
                WHERE person_id = ? AND deleted_at IS NULL
                ORDER BY created_at
                """,
                (person_id,),
            ).fetchall()
            known = [
                (row["embedding_id"], _unpack_embedding(row["vector"]))
                for row in existing_embeddings
            ]
            accepted: list[dict] = []
            for row in rows:
                vector = _unpack_embedding(row["vector"])
                duplicate_id = next(
                    (
                        embedding_id
                        for embedding_id, known_vector in known
                        if sum(a * b for a, b in zip(vector, known_vector)) >= 0.9999
                    ),
                    None,
                )
                if duplicate_id:
                    embedding_id = duplicate_id
                    duplicate = True
                else:
                    embedding_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO embeddings(
                            embedding_id, person_id, vector, quality_score,
                            source_image, crop_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id,
                            person_id,
                            row["vector"],
                            row["quality_score"],
                            row["source_image"],
                            row["crop_path"],
                            utc_now(),
                        ),
                    )
                    known.append((embedding_id, vector))
                    duplicate = False
                accepted.append(
                    {
                        "face_id": row["init_face_id"],
                        "embedding_id": embedding_id,
                        "image_id": Path(row["source_image"]).name,
                        "image_path": row["source_image"],
                        "duplicate": duplicate,
                    }
                )
            _mark_person_enrolled(conn, person_id)
            conn.execute(
                f"DELETE FROM init_faces WHERE init_face_id IN ({placeholders})",
                selected_ids,
            )
            remaining = conn.execute(
                "SELECT init_face_id FROM init_faces WHERE session_id = ? AND group_id = ?",
                (session_id, group_id),
            ).fetchall()
            if remaining:
                now = utc_now()
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO init_face_person_exclusions(
                        session_id, init_face_id, person_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [(session_id, row["init_face_id"], person_id, now) for row in remaining],
                )
            status = "pending" if remaining else "confirmed"
            conn.execute(
                """
                INSERT INTO init_groups(session_id, group_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, group_id)
                DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (session_id, group_id, status, utc_now()),
            )
            result = {
                "person_id": person_id,
                "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                "accepted": accepted,
                "automatic_association_ids": [item.association_id for item in automatic_associations],
            }
            _record_person_operation(conn, operation_id, operation_type, result)
            return result
    def delete_init_faces(self, init_face_ids: list[str]) -> None:
        if not init_face_ids:
            return
        with self._connect() as conn:
            conn.executemany("DELETE FROM init_faces WHERE init_face_id = ?", [(face_id,) for face_id in init_face_ids])

    def update_init_face_groups(self, assignments: dict[str, str]) -> None:
        if not assignments:
            return
        with self._connect() as conn:
            conn.executemany(
                "UPDATE init_faces SET group_id = ? WHERE init_face_id = ?",
                [(group_id, face_id) for face_id, group_id in assignments.items()],
            )

    def add_init_face_person_exclusions(
        self,
        session_id: str,
        init_face_ids: list[str],
        person_id: str,
    ) -> None:
        if not init_face_ids:
            return
        now = utc_now()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO init_face_person_exclusions(session_id, init_face_id, person_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [(session_id, face_id, person_id, now) for face_id in init_face_ids],
            )

    def list_init_face_person_exclusions(
        self,
        session_id: str,
        init_face_ids: list[str],
    ) -> dict[str, set[str]]:
        if not init_face_ids:
            return {}
        placeholders = ", ".join("?" for _ in init_face_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT init_face_id, person_id
                FROM init_face_person_exclusions
                WHERE session_id = ? AND init_face_id IN ({placeholders})
                """,
                (session_id, *init_face_ids),
            ).fetchall()
        exclusions: dict[str, set[str]] = {}
        for row in rows:
            exclusions.setdefault(row["init_face_id"], set()).add(row["person_id"])
        return exclusions

    @contextmanager
    def _connect(self):
        conn = connect_database(self.db_path, self.database_key, timeout=30, row_factory=True)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
def _pack_embedding(vector: Embedding) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack_embedding(payload: bytes) -> Embedding:
    count = len(payload) // 4
    return struct.unpack(f"{count}f", payload)


def _execute_migration_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without sqlite3.executescript's implicit commit."""
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if not sqlite3.complete_statement(statement):
            continue
        sql = statement.strip()
        if sql:
            conn.execute(sql)
        statement = ""
    if statement.strip():
        raise SchemaMigrationError("Migration contains an incomplete SQL statement")


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS persons (
            person_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            vector BLOB NOT NULL,
            quality_score REAL NOT NULL,
            source_image TEXT,
            crop_path TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_embeddings_person
        ON embeddings(person_id);

        CREATE TABLE IF NOT EXISTS pending_additions (
            pending_id TEXT PRIMARY KEY,
            source_image TEXT NOT NULL,
            box_x INTEGER NOT NULL,
            box_y INTEGER NOT NULL,
            box_width INTEGER NOT NULL,
            box_height INTEGER NOT NULL,
            box_confidence REAL NOT NULL,
            quality_score REAL NOT NULL,
            landmarks TEXT,
            crop_path TEXT,
            vector BLOB NOT NULL,
            matches TEXT NOT NULL,
            decision TEXT NOT NULL,
            quality_status TEXT NOT NULL DEFAULT 'warn',
            pending_quality_score REAL NOT NULL DEFAULT 0,
            quality_reasons TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        PRAGMA user_version = 1;
        """
    )


def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(pending_additions)").fetchall()
    }
    if "quality_status" not in columns:
        conn.execute("ALTER TABLE pending_additions ADD COLUMN quality_status TEXT NOT NULL DEFAULT 'warn'")
    if "pending_quality_score" not in columns:
        conn.execute(
            "ALTER TABLE pending_additions ADD COLUMN pending_quality_score REAL NOT NULL DEFAULT 0"
        )
    if "quality_reasons" not in columns:
        conn.execute("ALTER TABLE pending_additions ADD COLUMN quality_reasons TEXT NOT NULL DEFAULT '[]'")
    conn.execute("PRAGMA user_version = 2")


def _migrate_2_to_3(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS init_sessions (
            session_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS init_faces (
            init_face_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            source_image TEXT NOT NULL,
            box_x INTEGER NOT NULL,
            box_y INTEGER NOT NULL,
            box_width INTEGER NOT NULL,
            box_height INTEGER NOT NULL,
            box_confidence REAL NOT NULL,
            face_quality_score REAL NOT NULL,
            landmarks TEXT,
            crop_path TEXT,
            vector BLOB NOT NULL,
            quality_status TEXT NOT NULL,
            quality_score REAL NOT NULL,
            quality_reasons TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES init_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_init_faces_session_group
        ON init_faces(session_id, group_id);

        CREATE TABLE IF NOT EXISTS init_groups (
            session_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(session_id, group_id),
            FOREIGN KEY(session_id) REFERENCES init_sessions(session_id)
        );

        PRAGMA user_version = 3;
        """
    )


def _migrate_3_to_4(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(persons)").fetchall()
    }
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE persons ADD COLUMN deleted_at TEXT")
    conn.execute("PRAGMA user_version = 4")


def _migrate_4_to_5(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS recognition_details (
            detail_id TEXT PRIMARY KEY,
            embedding_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            image_id TEXT NOT NULL,
            image_path TEXT,
            name TEXT NOT NULL,
            decision TEXT NOT NULL,
            seen_date TEXT NOT NULL,
            seen_time TEXT NOT NULL,
            place_seen TEXT NOT NULL,
            individual_count INTEGER NOT NULL,
            event_occasion TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id),
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_recognition_details_embedding
        ON recognition_details(embedding_id);

        CREATE INDEX IF NOT EXISTS idx_recognition_details_person
        ON recognition_details(person_id);

        CREATE INDEX IF NOT EXISTS idx_recognition_details_image
        ON recognition_details(image_id);

        PRAGMA user_version = 5;
        """
    )


def _migrate_5_to_6(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(recognition_details)").fetchall()}
    additions = {
        "rank": "ALTER TABLE recognition_details ADD COLUMN rank TEXT",
        "country": "ALTER TABLE recognition_details ADD COLUMN country TEXT",
        "importance": "ALTER TABLE recognition_details ADD COLUMN importance TEXT",
        "added_by": "ALTER TABLE recognition_details ADD COLUMN added_by TEXT",
    }
    for column, statement in additions.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute("PRAGMA user_version = 6")


def _migrate_6_to_7(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS person_change_history (
            change_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            previous_name TEXT NOT NULL,
            new_name TEXT NOT NULL,
            previous_rank TEXT,
            new_rank TEXT,
            previous_country TEXT,
            new_country TEXT,
            previous_importance TEXT,
            new_importance TEXT,
            editor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_person_change_history_person
        ON person_change_history(person_id);

        PRAGMA user_version = 7;
        """
    )


def _migrate_7_to_8(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS init_face_person_exclusions (
            session_id TEXT NOT NULL,
            init_face_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(session_id, init_face_id, person_id),
            FOREIGN KEY(session_id) REFERENCES init_sessions(session_id),
            FOREIGN KEY(init_face_id) REFERENCES init_faces(init_face_id) ON DELETE CASCADE,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_init_face_person_exclusions_face
        ON init_face_person_exclusions(init_face_id);

        PRAGMA user_version = 8;
        """
    )


def _migrate_8_to_9(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS person_operations (
            operation_id TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_person_operations_created
        ON person_operations(created_at);

        PRAGMA user_version = 9;
        """
    )


def _migrate_9_to_10(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            vector BLOB NOT NULL,
            quality_score REAL NOT NULL,
            source_image TEXT,
            crop_path TEXT,
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            purge_after TEXT,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(embeddings)").fetchall()}
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE embeddings ADD COLUMN deleted_at TEXT")
    if "purge_after" not in columns:
        conn.execute("ALTER TABLE embeddings ADD COLUMN purge_after TEXT")
    _execute_migration_script(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_embeddings_deleted
        ON embeddings(deleted_at, purge_after);

        PRAGMA user_version = 10;
        """
    )


def _migrate_10_to_11(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS app_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            username_norm TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            roles TEXT NOT NULL,
            disabled INTEGER NOT NULL DEFAULT 0,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_app_users_enabled
        ON app_users(disabled, username_norm);

        CREATE TABLE IF NOT EXISTS auth_audit (
            audit_id TEXT PRIMARY KEY,
            actor_user_id TEXT,
            target_user_id TEXT,
            action TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_auth_audit_created
        ON auth_audit(created_at);

        PRAGMA user_version = 11;
        """
    )


def _migrate_11_to_12(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by_user_id TEXT,
            FOREIGN KEY(updated_by_user_id) REFERENCES app_users(user_id)
        );

        PRAGMA user_version = 12;
        """
    )


def _migrate_12_to_13(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS persons (
            person_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            enrollment_status TEXT NOT NULL DEFAULT 'enrolled'
        );

        CREATE TABLE IF NOT EXISTS person_change_history (
            change_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            previous_name TEXT NOT NULL,
            new_name TEXT NOT NULL,
            previous_rank TEXT,
            new_rank TEXT,
            previous_country TEXT,
            new_country TEXT,
            previous_importance TEXT,
            new_importance TEXT,
            previous_status TEXT,
            new_status TEXT,
            editor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );
        """
    )
    person_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(persons)").fetchall()
    }
    if "enrollment_status" not in person_columns:
        conn.execute(
            "ALTER TABLE persons ADD COLUMN enrollment_status TEXT NOT NULL DEFAULT 'enrolled'"
        )
    history_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(person_change_history)").fetchall()
    }
    if "previous_status" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN previous_status TEXT")
    if "new_status" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN new_status TEXT")
    _execute_migration_script(
        conn,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_placeholder_name
        ON persons(lower(trim(name)))
        WHERE enrollment_status = 'placeholder' AND deleted_at IS NULL;

        PRAGMA user_version = 13;
        """
    )


def _migrate_13_to_14(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS person_associations (
            association_id TEXT PRIMARY KEY,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT 'ASSOCIATED_WITH',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            CHECK(source_person_id < target_person_id),
            CHECK(relationship_type = 'ASSOCIATED_WITH'),
            UNIQUE(source_person_id, target_person_id, relationship_type),
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_person_associations_source
        ON person_associations(source_person_id, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_person_associations_target
        ON person_associations(target_person_id, updated_at DESC);

        PRAGMA user_version = 14;
        """
    )


def _migrate_14_to_15(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    person_columns = {row[1] for row in conn.execute("PRAGMA table_info(persons)")}
    detail_columns = {row[1] for row in conn.execute("PRAGMA table_info(recognition_details)")}
    history_columns = {row[1] for row in conn.execute("PRAGMA table_info(person_change_history)")}
    if "persons" in tables and "notes" not in person_columns:
        conn.execute("ALTER TABLE persons ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    if "recognition_details" in tables and "notes" not in detail_columns:
        conn.execute("ALTER TABLE recognition_details ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    if "person_change_history" in tables and "previous_notes" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN previous_notes TEXT")
    if "person_change_history" in tables and "new_notes" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN new_notes TEXT")
    conn.execute("PRAGMA user_version = 15")


def _migrate_15_to_16(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    columns = {row[1] for row in conn.execute("PRAGMA table_info(person_associations)")}
    person_columns = {row[1] for row in conn.execute("PRAGMA table_info(persons)")}
    detail_columns = {row[1] for row in conn.execute("PRAGMA table_info(recognition_details)")}
    if "person_associations" in tables and "association_origin" not in columns:
        conn.execute(
            "ALTER TABLE person_associations ADD COLUMN association_origin TEXT NOT NULL DEFAULT 'manual'"
        )
    if "notes" in person_columns and "person_associations" in tables:
        for row in conn.execute(
            "SELECT person_id, notes FROM persons WHERE deleted_at IS NULL AND notes LIKE '%@%'"
        ).fetchall():
            _create_note_associations(conn, row["person_id"], row["notes"] or "", "SentriFace migration", [])
    if "notes" in detail_columns and "person_associations" in tables:
        for row in conn.execute(
            "SELECT person_id, notes FROM recognition_details WHERE notes LIKE '%@%'"
        ).fetchall():
            _create_note_associations(conn, row["person_id"], row["notes"] or "", "SentriFace migration", [])
    conn.execute("PRAGMA user_version = 16")


def _migrate_16_to_17(conn: sqlite3.Connection) -> None:
    # `person_operations` remains the legacy idempotency/result store. Its rows
    # lack reliable actor and lifecycle data, so backfilling would invent audit
    # history. New journal-aware work uses these dedicated tables instead.
    _execute_migration_script(
        conn,
        """
        CREATE TABLE operation_journal (
            operation_id TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('STARTED', 'COMMITTED', 'FAILED', 'ROLLED_BACK', 'REVERTED')),
            actor_user_id TEXT,
            actor TEXT NOT NULL DEFAULT '{}',
            source TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            affected_entities TEXT NOT NULL DEFAULT '[]',
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE INDEX idx_operation_journal_created
        ON operation_journal(created_at DESC);

        CREATE INDEX idx_operation_journal_status
        ON operation_journal(status, created_at DESC);

        CREATE INDEX idx_operation_journal_actor
        ON operation_journal(actor_user_id, created_at DESC);

        CREATE TABLE operation_journal_status_history (
            transition_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL CHECK(to_status IN ('STARTED', 'COMMITTED', 'FAILED', 'ROLLED_BACK', 'REVERTED')),
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_operation_journal_history_operation
        ON operation_journal_status_history(operation_id, created_at, transition_id);

        CREATE TRIGGER operation_journal_no_delete
        BEFORE DELETE ON operation_journal
        BEGIN
            SELECT RAISE(ABORT, 'operation journal records cannot be deleted');
        END;

        CREATE TRIGGER operation_journal_identity_immutable
        BEFORE UPDATE OF operation_id, operation_type, actor_user_id, actor, source,
                         context, affected_entities, details, created_at
        ON operation_journal
        BEGIN
            SELECT RAISE(ABORT, 'operation journal identity and details are immutable');
        END;

        CREATE TRIGGER operation_journal_history_no_update
        BEFORE UPDATE ON operation_journal_status_history
        BEGIN
            SELECT RAISE(ABORT, 'operation journal history is append-only');
        END;

        CREATE TRIGGER operation_journal_history_no_delete
        BEFORE DELETE ON operation_journal_status_history
        BEGIN
            SELECT RAISE(ABORT, 'operation journal history cannot be deleted');
        END;

        PRAGMA user_version = 17;
        """,
    )


def _schema_migrations() -> tuple[SchemaMigration, ...]:
    """Return the ordered migration registry.

    Future schema work adds one `_migrate_N_to_N_plus_1` function and one entry
    here, then increments `SCHEMA_VERSION`. Resolving the functions on each call
    keeps migration failure tests and recovery tooling able to patch a step.
    """
    return (
        SchemaMigration(0, 1, _migrate_0_to_1),
        SchemaMigration(1, 2, _migrate_1_to_2),
        SchemaMigration(2, 3, _migrate_2_to_3),
        SchemaMigration(3, 4, _migrate_3_to_4),
        SchemaMigration(4, 5, _migrate_4_to_5),
        SchemaMigration(5, 6, _migrate_5_to_6),
        SchemaMigration(6, 7, _migrate_6_to_7),
        SchemaMigration(7, 8, _migrate_7_to_8),
        SchemaMigration(8, 9, _migrate_8_to_9),
        SchemaMigration(9, 10, _migrate_9_to_10),
        SchemaMigration(10, 11, _migrate_10_to_11),
        SchemaMigration(11, 12, _migrate_11_to_12),
        SchemaMigration(12, 13, _migrate_12_to_13),
        SchemaMigration(13, 14, _migrate_13_to_14),
        SchemaMigration(14, 15, _migrate_14_to_15),
        SchemaMigration(15, 16, _migrate_15_to_16),
        SchemaMigration(16, 17, _migrate_16_to_17),
    )


def _require_supported_schema_version(version: int) -> None:
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than this app supports "
            f"({SCHEMA_VERSION}). Please update SentriFace."
        )
    if version < 0:
        raise RuntimeError(f"Unsupported database schema version: {version}")


def _validated_migration_registry() -> tuple[SchemaMigration, ...]:
    migrations = _schema_migrations()
    expected_version = 0
    for migration in migrations:
        if migration.from_version != expected_version or migration.to_version != expected_version + 1:
            raise SchemaMigrationError(
                "Invalid schema migration registry: expected "
                f"v{expected_version} to v{expected_version + 1}, found "
                f"v{migration.from_version} to v{migration.to_version}."
            )
        expected_version = migration.to_version
    if expected_version != SCHEMA_VERSION:
        raise SchemaMigrationError(
            "Invalid schema migration registry: "
            f"ends at v{expected_version}, expected v{SCHEMA_VERSION}."
        )
    return migrations


def _apply_schema_migrations(conn: sqlite3.Connection, current_version: int) -> None:
    migrations = _validated_migration_registry()
    if current_version == SCHEMA_VERSION:
        return
    migrations_by_version = {migration.from_version: migration for migration in migrations}
    if current_version not in migrations_by_version:
        raise SchemaMigrationError(f"Unsupported database schema version: {current_version}")

    conn.execute("BEGIN IMMEDIATE")
    version = current_version
    try:
        while version < SCHEMA_VERSION:
            migration = migrations_by_version.get(version)
            if migration is None:
                raise SchemaMigrationError(
                    f"No migration is registered from database schema v{version}."
                )
            try:
                migration.apply(conn)
            except Exception as exc:
                raise SchemaMigrationError(
                    f"Database migration v{migration.from_version} to "
                    f"v{migration.to_version} failed: {exc}"
                ) from exc
            migrated_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if migrated_version != migration.to_version:
                raise SchemaMigrationError(
                    f"Database migration v{migration.from_version} to "
                    f"v{migration.to_version} reported schema v{migrated_version}."
                )
            version = migrated_version
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _create_placeholder_record(
    conn: sqlite3.Connection,
    name: str,
    metadata: dict | None,
    editor_name: str,
    notes: str = "",
) -> Person:
    duplicate = conn.execute(
        """
        SELECT 1 FROM persons
        WHERE enrollment_status = 'placeholder'
          AND lower(trim(name)) = lower(trim(?))
        LIMIT 1
        """,
        (name,),
    ).fetchone()
    if duplicate is not None:
        raise _placeholder_name_conflict(
            sqlite3.IntegrityError("duplicate placeholder name")
        )
    placeholder_metadata = dict(metadata or {})
    placeholder_metadata["tags"] = _normalize_tags(
        placeholder_metadata.get("tags", [])
    )
    person = Person(
        person_id=str(uuid.uuid4()),
        name=name,
        metadata=placeholder_metadata,
        enrollment_status="placeholder",
        notes=notes.strip(),
    )
    try:
        conn.execute(
            """
            INSERT INTO persons(
                person_id, name, metadata, created_at, enrollment_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                person.person_id,
                person.name,
                json.dumps(person.metadata, separators=(",", ":")),
                person.created_at,
                person.enrollment_status,
                person.notes,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "placeholder" in str(exc).lower() or "persons.name" in str(exc).lower():
            raise _placeholder_name_conflict(exc) from exc
        raise
    _insert_person_change(
        conn,
        PersonChange(
            change_id=str(uuid.uuid4()),
            person_id=person.person_id,
            previous_name="",
            new_name=person.name,
            previous_rank="",
            new_rank=str(person.metadata.get("rank") or ""),
            previous_country="",
            new_country=str(person.metadata.get("country") or ""),
            previous_importance="",
            new_importance=str(person.metadata.get("importance") or ""),
            previous_status=None,
            new_status="placeholder",
            previous_notes="",
            new_notes=person.notes,
            editor_name=editor_name,
            created_at=person.created_at,
        ),
    )
    return person


def _canonical_person_pair(source_person_id: str, target_person_id: str) -> tuple[str, str]:
    source = source_person_id.strip()
    target = target_person_id.strip()
    if not source or not target:
        raise KeyError("Choose two people to associate")
    if source == target:
        raise KeyError("A person cannot be associated with themselves")
    return tuple(sorted((source, target)))


def _require_active_people(conn: sqlite3.Connection, *person_ids: str) -> None:
    for person_id in person_ids:
        row = conn.execute(
            "SELECT 1 FROM persons WHERE person_id = ? AND deleted_at IS NULL",
            (person_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown active person: {person_id}")


def _new_person_association(
    person_a_id: str,
    person_b_id: str,
    actor_name: str,
    association_origin: str = "manual",
) -> PersonAssociation:
    created_at = utc_now()
    return PersonAssociation(
        association_id=str(uuid.uuid4()),
        source_person_id=person_a_id,
        target_person_id=person_b_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=actor_name,
        association_origin=association_origin,
    )


def _insert_person_association(
    conn: sqlite3.Connection,
    association: PersonAssociation,
) -> None:
    conn.execute(
        """
        INSERT INTO person_associations(
            association_id, source_person_id, target_person_id,
            relationship_type, created_at, updated_at, created_by, association_origin
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            association.association_id,
            association.source_person_id,
            association.target_person_id,
            association.relationship_type,
            association.created_at,
            association.updated_at,
            association.created_by,
            association.association_origin,
        ),
    )


def _person_association_from_row(row: sqlite3.Row) -> PersonAssociation:
    return PersonAssociation(
        association_id=row["association_id"],
        source_person_id=row["source_person_id"],
        target_person_id=row["target_person_id"],
        relationship_type=row["relationship_type"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row["created_by"],
        association_origin=row["association_origin"] if "association_origin" in row.keys() else "manual",
    )


def _create_note_associations(
    conn: sqlite3.Connection,
    owner_person_id: str,
    notes: str,
    actor_name: str,
    explicit_person_ids: list[str],
) -> list[PersonAssociation]:
    if "@" not in notes:
        return []
    active_rows = conn.execute(
        "SELECT person_id, name FROM persons WHERE deleted_at IS NULL AND person_id <> ?",
        (owner_person_id,),
    ).fetchall()
    rows_by_id = {row["person_id"]: row for row in active_rows}
    names: dict[str, list[sqlite3.Row]] = {}
    for row in active_rows:
        names.setdefault(row["name"].strip().casefold(), []).append(row)
    mentioned_ids: set[str] = set()
    for person_id in explicit_person_ids:
        row = rows_by_id.get(str(person_id))
        if row and re.search(rf"(?<!\w)@{re.escape(row['name'])}(?!\w)", notes, re.IGNORECASE):
            mentioned_ids.add(row["person_id"])
    for normalized_name, matching_rows in names.items():
        if len(matching_rows) != 1 or not normalized_name:
            continue
        row = matching_rows[0]
        if re.search(rf"(?<!\w)@{re.escape(row['name'])}(?!\w)", notes, re.IGNORECASE):
            mentioned_ids.add(row["person_id"])
    created: list[PersonAssociation] = []
    for mentioned_id in sorted(mentioned_ids):
        person_a_id, person_b_id = _canonical_person_pair(owner_person_id, mentioned_id)
        existing = conn.execute(
            "SELECT 1 FROM person_associations WHERE source_person_id = ? AND target_person_id = ? AND relationship_type = 'ASSOCIATED_WITH'",
            (person_a_id, person_b_id),
        ).fetchone()
        if existing is not None:
            continue
        association = _new_person_association(
            person_a_id, person_b_id, actor_name or "SentriFace", "automatic_mention",
        )
        _insert_person_association(conn, association)
        created.append(association)
    return created


def _person_from_row(row: sqlite3.Row) -> Person:
    return Person(
        person_id=row["person_id"],
        name=row["name"],
        metadata=json.loads(row["metadata"]),
        created_at=row["created_at"],
        deleted_at=row["deleted_at"],
        enrollment_status=row["enrollment_status"],
        notes=row["notes"] if "notes" in row.keys() else "",
    )


def _insert_person_change(conn: sqlite3.Connection, change: PersonChange) -> None:
    conn.execute(
        """
        INSERT INTO person_change_history(
            change_id, person_id, previous_name, new_name,
            previous_rank, new_rank, previous_country, new_country,
            previous_importance, new_importance, previous_status, new_status,
            previous_notes, new_notes, editor_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            change.change_id,
            change.person_id,
            change.previous_name,
            change.new_name,
            change.previous_rank,
            change.new_rank,
            change.previous_country,
            change.new_country,
            change.previous_importance,
            change.new_importance,
            change.previous_status,
            change.new_status,
            change.previous_notes,
            change.new_notes,
            change.editor_name,
            change.created_at,
        ),
    )


def _mark_person_enrolled(conn: sqlite3.Connection, person_id: str) -> None:
    row = conn.execute(
        """
        SELECT name, metadata, enrollment_status, notes
        FROM persons WHERE person_id = ? AND deleted_at IS NULL
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown person: {person_id}")
    if row["enrollment_status"] != "placeholder":
        return
    conn.execute(
        "UPDATE persons SET enrollment_status = 'enrolled' WHERE person_id = ?",
        (person_id,),
    )
    metadata = json.loads(row["metadata"])
    _insert_person_change(
        conn,
        PersonChange(
            change_id=str(uuid.uuid4()),
            person_id=person_id,
            previous_name=row["name"],
            new_name=row["name"],
            previous_rank=metadata.get("rank") or "",
            new_rank=metadata.get("rank") or "",
            previous_country=metadata.get("country") or "",
            new_country=metadata.get("country") or "",
            previous_importance=metadata.get("importance") or "",
            new_importance=metadata.get("importance") or "",
            previous_status="placeholder",
            new_status="enrolled",
            previous_notes=row["notes"],
            new_notes=row["notes"],
            editor_name="SentriFace",
        ),
    )


def _placeholder_name_conflict(exc: sqlite3.IntegrityError) -> KeyError:
    return KeyError(
        "A placeholder with this name already exists. Add a photograph to that profile or choose a different name."
    )


def _journal_json_object(value: dict | None, label: str) -> tuple[dict, str]:
    normalized = value or {}
    if not isinstance(normalized, dict):
        raise ValueError(f"Operation {label} must be an object")
    try:
        payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Operation {label} must contain JSON-compatible values") from exc
    return normalized, payload


def _journal_json_array(value: list[dict] | None, label: str) -> tuple[list[dict], str]:
    normalized = value or []
    if not isinstance(normalized, list) or any(not isinstance(item, dict) for item in normalized):
        raise ValueError(f"Operation {label} must be a list of objects")
    try:
        payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Operation {label} must contain JSON-compatible values") from exc
    return normalized, payload


def _operation_actor_snapshot(actor: dict | None) -> tuple[dict, str, str | None]:
    if actor is not None and not isinstance(actor, dict):
        raise ValueError("Operation actor must be an AuthUser-compatible object")
    source = actor or {}
    roles = source.get("roles") or []
    if not isinstance(roles, (list, tuple)):
        raise ValueError("Operation actor roles must be a list")
    snapshot = {
        key: str(source[key])
        for key in ("user_id", "username", "display_name")
        if source.get(key) is not None
    }
    snapshot["roles"] = [str(role) for role in roles]
    _, payload = _journal_json_object(snapshot, "actor")
    return snapshot, payload, snapshot.get("user_id")


def _begin_journal_operation(
    conn: sqlite3.Connection,
    operation_type: str,
    *,
    operation_id: str | None = None,
    actor: dict | None = None,
    source: str | None = None,
    context: dict | None = None,
    affected_entities: list[dict] | None = None,
    details: dict | None = None,
) -> dict:
    normalized_type = str(operation_type).strip()
    if not normalized_type:
        raise ValueError("Operation type is required")
    normalized_id = str(operation_id or uuid.uuid4()).strip()
    if not normalized_id:
        raise ValueError("Operation ID is required")
    _, actor_payload, actor_user_id = _operation_actor_snapshot(actor)
    _, context_payload = _journal_json_object(context, "context")
    _, entities_payload = _journal_json_array(affected_entities, "affected entities")
    _, details_payload = _journal_json_object(details, "details")
    normalized_source = str(source).strip() if source is not None else None
    normalized_source = normalized_source or None
    created_at = utc_now()
    try:
        conn.execute(
            """
            INSERT INTO operation_journal(
                operation_id, operation_type, status, actor_user_id, actor,
                source, context, affected_entities, details, created_at
            ) VALUES (?, ?, 'STARTED', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_id,
                normalized_type,
                actor_user_id,
                actor_payload,
                normalized_source,
                context_payload,
                entities_payload,
                details_payload,
                created_at,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if conn.execute(
            "SELECT 1 FROM operation_journal WHERE operation_id = ?",
            (normalized_id,),
        ).fetchone():
            raise KeyError(f"Operation ID already exists: {normalized_id}") from exc
        raise
    conn.execute(
        """
        INSERT INTO operation_journal_status_history(
            transition_id, operation_id, from_status, to_status, details, created_at
        ) VALUES (?, ?, NULL, 'STARTED', '{}', ?)
        """,
        (str(uuid.uuid4()), normalized_id, created_at),
    )
    return _get_journal_operation(conn, normalized_id)


def _transition_journal_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    target_status: str,
    details: dict | None = None,
) -> dict:
    normalized_id = str(operation_id).strip()
    if not normalized_id:
        raise ValueError("Operation ID is required")
    if target_status not in OPERATION_STATUSES or target_status == "STARTED":
        raise ValueError(f"Unsupported operation status: {target_status}")
    row = conn.execute(
        "SELECT status FROM operation_journal WHERE operation_id = ?",
        (normalized_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown operation: {normalized_id}")
    current_status = str(row["status"])
    if target_status not in OPERATION_STATUS_TRANSITIONS[current_status]:
        raise ValueError(
            f"Invalid operation status transition: {current_status} -> {target_status}"
        )
    _, details_payload = _journal_json_object(details, "transition details")
    transitioned_at = utc_now()
    cursor = conn.execute(
        """
        UPDATE operation_journal
        SET status = ?, completed_at = ?
        WHERE operation_id = ? AND status = ?
        """,
        (target_status, transitioned_at, normalized_id, current_status),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Operation status changed concurrently; transition was not applied")
    conn.execute(
        """
        INSERT INTO operation_journal_status_history(
            transition_id, operation_id, from_status, to_status, details, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            normalized_id,
            current_status,
            target_status,
            details_payload,
            transitioned_at,
        ),
    )
    return _get_journal_operation(conn, normalized_id)


def _get_journal_operation(conn: sqlite3.Connection, operation_id: str) -> dict | None:
    normalized_id = str(operation_id).strip()
    if not normalized_id:
        raise ValueError("Operation ID is required")
    row = conn.execute(
        "SELECT * FROM operation_journal WHERE operation_id = ?",
        (normalized_id,),
    ).fetchone()
    if row is None:
        return None
    history = conn.execute(
        """
        SELECT transition_id, from_status, to_status, details, created_at
        FROM operation_journal_status_history
        WHERE operation_id = ?
        ORDER BY created_at, rowid
        """,
        (normalized_id,),
    ).fetchall()
    return {
        "operation_id": row["operation_id"],
        "operation_type": row["operation_type"],
        "status": row["status"],
        "actor": json.loads(row["actor"]),
        "source": row["source"],
        "context": json.loads(row["context"]),
        "affected_entities": json.loads(row["affected_entities"]),
        "details": json.loads(row["details"]),
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "status_history": [
            {
                "transition_id": item["transition_id"],
                "from_status": item["from_status"],
                "to_status": item["to_status"],
                "details": json.loads(item["details"]),
                "created_at": item["created_at"],
            }
            for item in history
        ],
    }


def _existing_person_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
) -> dict | None:
    if not operation_id.strip():
        raise KeyError("operation_id is required")
    row = conn.execute(
        """
        SELECT operation_type, result
        FROM person_operations
        WHERE operation_id = ?
        """,
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    if row["operation_type"] != operation_type:
        raise KeyError("operation_id was already used for a different operation")
    return json.loads(row["result"])


def _begin_person_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
) -> dict | None:
    conn.execute("BEGIN IMMEDIATE")
    return _existing_person_operation(conn, operation_id, operation_type)


def _record_person_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
    result: dict,
) -> None:
    conn.execute(
        """
        INSERT INTO person_operations(operation_id, operation_type, result, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            operation_id,
            operation_type,
            json.dumps(result, separators=(",", ":")),
            utc_now(),
        ),
    )


def _normalize_tags(values: list | tuple | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        tag = str(value).strip()
        key = tag.casefold()
        if not tag or key in seen:
            continue
        normalized.append(tag[:48])
        seen.add(key)
        if len(normalized) == 20:
            break
    return normalized


def _pending_from_row(row: sqlite3.Row) -> PendingAddition:
    raw_landmarks = json.loads(row["landmarks"]) if row["landmarks"] else None
    landmarks = tuple(tuple(point) for point in raw_landmarks) if raw_landmarks else None
    matches = [_person_match_from_json(item) for item in json.loads(row["matches"])]
    return PendingAddition(
        pending_id=row["pending_id"],
        source_image=row["source_image"],
        face=DetectedFace(
            box=FaceBox(
                x=row["box_x"],
                y=row["box_y"],
                width=row["box_width"],
                height=row["box_height"],
                confidence=row["box_confidence"],
            ),
            quality_score=row["quality_score"],
            landmarks=landmarks,
            crop_path=row["crop_path"],
        ),
        vector=_unpack_embedding(row["vector"]),
        matches=matches,
        decision=MatchDecision(row["decision"]),
        quality=QualityReport(
            status=QualityStatus(row["quality_status"]),
            score=row["pending_quality_score"],
            reasons=tuple(json.loads(row["quality_reasons"])),
        ),
        created_at=row["created_at"],
    )


def _person_match_from_json(item: dict) -> PersonMatch:
    if "embedding_ids" in item:
        embedding_ids = tuple(item["embedding_ids"])
    else:
        embedding_ids = (item["embedding_id"],)
    return PersonMatch(
        person_id=item["person_id"],
        score=item["score"],
        embedding_ids=embedding_ids,
        embeddings_matched=item.get("embeddings_matched", len(embedding_ids)),
    )


def _embedding_from_row(row: sqlite3.Row) -> EmbeddingRecord:
    return EmbeddingRecord(
        embedding_id=row["embedding_id"],
        person_id=row["person_id"],
        vector=_unpack_embedding(row["vector"]),
        quality_score=row["quality_score"],
        source_image=row["source_image"],
        crop_path=row["crop_path"],
        created_at=row["created_at"],
    )


def _recognition_detail_from_row(row: sqlite3.Row) -> RecognitionDetail:
    return RecognitionDetail(
        detail_id=row["detail_id"],
        embedding_id=row["embedding_id"],
        person_id=row["person_id"],
        image_id=row["image_id"],
        image_path=row["image_path"],
        name=row["name"],
        decision=row["decision"],
        seen_date=row["seen_date"],
        seen_time=row["seen_time"],
        place_seen=row["place_seen"],
        individual_count=row["individual_count"],
        event_occasion=row["event_occasion"],
        rank=row["rank"],
        country=row["country"],
        importance=row["importance"],
        added_by=row["added_by"],
        notes=row["notes"] if "notes" in row.keys() else "",
        created_at=row["created_at"],
    )


def _person_change_from_row(row: sqlite3.Row) -> PersonChange:
    return PersonChange(
        change_id=row["change_id"],
        person_id=row["person_id"],
        previous_name=row["previous_name"],
        new_name=row["new_name"],
        previous_rank=row["previous_rank"],
        new_rank=row["new_rank"],
        previous_country=row["previous_country"],
        new_country=row["new_country"],
        previous_importance=row["previous_importance"],
        new_importance=row["new_importance"],
        previous_status=row["previous_status"],
        new_status=row["new_status"],
        previous_notes=row["previous_notes"] if "previous_notes" in row.keys() else None,
        new_notes=row["new_notes"] if "new_notes" in row.keys() else None,
        editor_name=row["editor_name"],
        created_at=row["created_at"],
    )


def _init_face_from_row(row: sqlite3.Row) -> InitFace:
    raw_landmarks = json.loads(row["landmarks"]) if row["landmarks"] else None
    landmarks = tuple(tuple(point) for point in raw_landmarks) if raw_landmarks else None
    return InitFace(
        init_face_id=row["init_face_id"],
        session_id=row["session_id"],
        group_id=row["group_id"],
        source_image=row["source_image"],
        face=DetectedFace(
            box=FaceBox(
                x=row["box_x"],
                y=row["box_y"],
                width=row["box_width"],
                height=row["box_height"],
                confidence=row["box_confidence"],
            ),
            quality_score=row["face_quality_score"],
            landmarks=landmarks,
            crop_path=row["crop_path"],
        ),
        vector=_unpack_embedding(row["vector"]),
        quality=QualityReport(
            status=QualityStatus(row["quality_status"]),
            score=row["quality_score"],
            reasons=tuple(json.loads(row["quality_reasons"])),
        ),
        created_at=row["created_at"],
    )
