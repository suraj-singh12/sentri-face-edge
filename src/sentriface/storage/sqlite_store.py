from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import struct
import uuid
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sentriface.backup_service import BackupError, BackupService
from sentriface.errors import (
    GraphProjectionPostcheckError,
    GraphProjectionRebuildRefused,
    StructuredRepairRefused,
    OperationRevertRefused,
)
from sentriface.models import (
    ArchivedCanonicalSurvivorRepairPrecondition,
    NoteReferenceReconciliationPrecondition,
    NoteReferenceRepairPlan,
    OperationRevertPrecondition,
    DetectedFace,
    Embedding,
    EmbeddingRecord,
    FaceBox,
    GlobalGraphProjection,
    GraphConnection,
    GraphNode,
    GraphReadEdge,
    GraphReadFilter,
    GraphReadNode,
    InitFace,
    InitGroup,
    InitSession,
    IdentityCorrection,
    MatchDecision,
    MergeAffectedAction,
    MergeAffectedItem,
    MergeConflictResolution,
    MergeConflictStrategy,
    MergeOperation,
    Note,
    NoteRevision,
    Observation,
    ObservationMedia,
    ObservationParticipant,
    PendingAddition,
    Person,
    PersonIntelligence,
    PersonGraphReadModel,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PersonSummary,
    PresenceAnalytics,
    QualityReport,
    QualityStatus,
    PhotoReview,
    ReviewFaceDecision,
    RecognitionDetail,
    RelationshipEvidence,
    RelationshipAnalytics,
    Sighting,
    TemporalCount,
    LocationCount,
    WorldGraphReadModel,
    WorldCluster,
    WorldCollection,
    WorldDetailLevel,
    WorldEvent,
    WorldEvidence,
    WorldExplanation,
    WorldGraphRequest,
    WorldGraphV2ReadModel,
    WorldMediaReference,
    WorldPageState,
    WorldPattern,
    WorldPerson,
    WorldReadFilter,
    WorldReadLimits,
    WorldRelationship,
    utc_now,
)

from sentriface.secure_storage import connect_database, ensure_encrypted_database

SCHEMA_VERSION = 28
DELETED_FACE_RETENTION_DAYS = 30
PERSON_LIFECYCLE_STATUSES = frozenset({"ACTIVE", "ARCHIVED", "DELETED", "MERGED"})
PERSON_IDENTITY_STATUSES = frozenset({"IDENTIFIED", "UNIDENTIFIED"})
PERSON_BIOMETRIC_STATUSES = frozenset({"NO_FACE", "ENROLLED"})
RELATIONSHIP_EVIDENCE_TYPES = frozenset({
    "CO_OBSERVED", "NOTE_REFERENCE", "MANUAL_ASSOCIATION",
})
OPERATION_STATUSES = frozenset({"STARTED", "COMMITTED", "FAILED", "ROLLED_BACK", "REVERTED"})
OPERATION_STATUS_TRANSITIONS = {
    "STARTED": frozenset({"COMMITTED", "FAILED", "ROLLED_BACK"}),
    "FAILED": frozenset({"ROLLED_BACK"}),
    "COMMITTED": frozenset({"REVERTED"}),
    "ROLLED_BACK": frozenset(),
    "REVERTED": frozenset(),
}
REVIEW_DECISIONS = frozenset({
    "ACCEPT_EXISTING_PERSON", "ACCEPT_NEW_PERSON", "EXCLUDE", "SKIP",
})
MERGE_COLLECTION_ITEM_TYPES = frozenset({
    "EMBEDDING", "PHOTO", "OBSERVATION", "OBSERVATION_PARTICIPANT",
    "NOTE", "NOTE_MENTION", "HISTORY", "GRAPH_EVIDENCE",
})


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
            conn.execute("PRAGMA synchronous=FULL")
            current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            _require_supported_schema_version(current_version)
            if current_version != initial_version:
                raise SchemaMigrationError(
                    "Database schema version changed while migration was being prepared "
                    f"(v{initial_version} to v{current_version}); startup was stopped safely."
                )
            _apply_schema_migrations(conn, current_version)
            if current_version == SCHEMA_VERSION:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    _validate_current_domain_state(conn)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

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

    def create_person(
        self,
        name: str,
        metadata: dict | None = None,
        notes: str = "",
        identity_status: str = "IDENTIFIED",
    ) -> Person:
        """Internal fixture/compatibility primitive; production uses IdentityService."""
        normalized_name = name.strip()
        normalized_metadata = metadata or {}
        normalized_notes = notes.strip()
        normalized_identity_status = identity_status.strip().upper()
        if normalized_identity_status not in PERSON_IDENTITY_STATUSES:
            raise ValueError(f"Unsupported identity status: {identity_status}")
        if not _has_meaningful_identity_context(
            normalized_name, normalized_metadata, normalized_notes,
        ):
            raise ValueError("A person without a face requires meaningful identity or context")
        person = Person(
            person_id=str(uuid.uuid4()),
            name=normalized_name,
            metadata=normalized_metadata,
            notes=normalized_notes,
            identity_status=normalized_identity_status,
            biometric_status="NO_FACE",
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO persons(
                    person_id, name, metadata, created_at, notes,
                    identity_status, biometric_status, lifecycle_changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'NO_FACE', ?)
                """,
                (
                    person.person_id,
                    person.name,
                    json.dumps(person.metadata, separators=(",", ":")),
                    person.created_at,
                    person.notes,
                    person.identity_status,
                    person.created_at,
                ),
            )
            _insert_unjournaled_profile_note(
                conn, person.person_id, person.notes, person.created_at,
            )
        return person

    def create_identified_person(
        self,
        name: str,
        metadata: dict,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str = "identity-service",
    ) -> Person:
        normalized_name = str(name).strip()
        normalized_metadata = dict(metadata or {})
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.create",
            )
            if existing is not None:
                row = conn.execute(
                    "SELECT * FROM persons WHERE person_id = ?",
                    (existing.get("person_id"),),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed identity creation is missing its person")
                return _person_from_row(row)
            person_id = str(uuid.uuid4())
            _begin_journal_operation(
                conn,
                "identity.create",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-service",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"identity_status": "IDENTIFIED", "biometric_status": "NO_FACE"},
            )
            try:
                person = _insert_identified_person_record(
                    conn,
                    person_id=person_id,
                    name=normalized_name,
                    metadata=normalized_metadata,
                    enrollment_status="placeholder",
                )
            except sqlite3.IntegrityError as exc:
                raise _placeholder_name_conflict(exc) from exc
            result = {
                "person_id": person.person_id,
                "lifecycle_status": "ACTIVE",
                "identity_status": "IDENTIFIED",
                "biometric_status": "NO_FACE",
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return person

    def _legacy_create_placeholder_person(
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
                    SELECT * FROM persons WHERE person_id = ?
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
            automatic_associations = _legacy_create_note_associations(
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
                SELECT *
                FROM persons
                WHERE person_id = ? {" " if include_archived else "AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL"}
                """,
                (person_id,),
            ).fetchone()
        if row is None:
            return None
        return _person_from_row(row)

    def get_effective_person(self, person_id: str) -> Person | None:
        with self._connect() as conn:
            try:
                canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            except KeyError:
                return None
            row = conn.execute(
                """
                SELECT * FROM persons
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
                """,
                (canonical_person_id,),
            ).fetchone()
        return _person_from_row(row) if row is not None else None

    def list_persons(self, archived: bool = False) -> list[PersonSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.*
                FROM persons p
                WHERE {"p.lifecycle_status <> 'ACTIVE' OR p.deleted_at IS NOT NULL" if archived else "p.lifecycle_status = 'ACTIVE' AND p.deleted_at IS NULL"}
                ORDER BY p.name COLLATE NOCASE
                """
            ).fetchall()
            effective_embedding_counts: dict[str, int] = {}
            for embedding_row in conn.execute(
                "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
            ).fetchall():
                canonical_id = _effective_embedding_owner_person_id(conn, embedding_row)
                effective_embedding_counts[canonical_id] = (
                    effective_embedding_counts.get(canonical_id, 0) + 1
                )
            analytics_by_canonical: dict[str, PresenceAnalytics] = {}
            row_canonical_ids: dict[str, str] = {}
            for row in rows:
                canonical_id = _resolve_canonical_person_id(conn, str(row["person_id"]))
                row_canonical_ids[str(row["person_id"])] = canonical_id
                if canonical_id not in analytics_by_canonical:
                    analytics_by_canonical[canonical_id] = _presence_analytics(
                        _list_person_sightings(conn, canonical_id)
                    )
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
                    lifecycle_status=row["lifecycle_status"],
                    canonical_person_id=row["canonical_person_id"],
                    identity_status=row["identity_status"],
                    biometric_status=row["biometric_status"],
                ),
                embedding_count=effective_embedding_counts.get(
                    row_canonical_ids[str(row["person_id"])], 0,
                ),
                sighting_count=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].observation_count,
                last_seen_at=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].last_seen_at,
                first_seen_at=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].first_seen_at,
                frequency_per_30_days=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].frequency_per_30_days,
                frequency_label=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].frequency_label,
            )
            for row in rows
        ]

    def list_embeddings_for_person(
        self,
        person_id: str,
        include_archived: bool = False,
    ) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            requested_canonical_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.vector, e.quality_score,
                       e.source_image, e.crop_path, e.created_at
                FROM embeddings e
                WHERE e.deleted_at IS NULL
                ORDER BY e.created_at ASC
                """
            ).fetchall()
            result = [
                _embedding_from_row(
                    row,
                    raw_person_id=_raw_embedding_owner_person_id(conn, row),
                    canonical_person_id=_effective_embedding_owner_person_id(conn, row),
                )
                for row in rows
                if _effective_embedding_owner_person_id(conn, row)
                == requested_canonical_id
            ]
            if not include_archived:
                canonical = conn.execute(
                    "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                    (requested_canonical_id,),
                ).fetchone()
                if canonical is None or canonical["lifecycle_status"] != "ACTIVE" or canonical["deleted_at"]:
                    return []
            return result

    def list_raw_embeddings_for_person(
        self, person_id: str, include_deleted: bool = False,
    ) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {person_id}")
            rows = conn.execute(
                f"""
                SELECT embedding_id, person_id, vector, quality_score,
                       source_image, crop_path, created_at
                FROM embeddings
                {"" if include_deleted else "WHERE deleted_at IS NULL"}
                ORDER BY created_at ASC
                """
            ).fetchall()
            return [
                _embedding_from_row(
                    row,
                    raw_person_id=_raw_embedding_owner_person_id(conn, row),
                    canonical_person_id=_effective_embedding_owner_person_id(conn, row),
                )
                for row in rows
                if _raw_embedding_owner_person_id(conn, row) == person_id
            ]

    def _legacy_rename_person(self, person_id: str, name: str) -> None:
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
        *,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> PersonChange:
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.profile.update",
            )
            if existing is None:
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
            _begin_journal_operation(
                conn,
                "identity.profile.update",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-service",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
            )
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
            result = {"change_id": change.change_id, "person_id": person_id}
            _record_person_operation(
                conn, operation_id, "update-profile", result,
            )
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
        return change

    def create_note(
        self,
        owner_person_id: str,
        content: str,
        operation_id: str,
        *,
        mentioned_person_ids: list[str] | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        normalized_content = content.strip()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.create",
            )
            if existing_result is not None:
                if existing_result.get("owner_person_id") != owner_person_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _note_row(conn, str(existing_result["note_id"]))
                if row is None:
                    raise RuntimeError("Committed note creation is missing its note")
                return _note_from_row(conn, row)
            owner = conn.execute(
                """
                SELECT person_id FROM persons
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
                """,
                (owner_person_id,),
            ).fetchone()
            if owner is None:
                raise KeyError(f"Unknown active person: {owner_person_id}")
            mentions = _normalize_note_mentions(
                conn, owner_person_id, mentioned_person_ids,
            )
            note_id = str(uuid.uuid4())
            created_at = utc_now()
            _begin_journal_operation(
                conn,
                "note.create",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "notes-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": owner_person_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id, _ in mentions
                    ],
                ],
            )
            conn.execute(
                """
                INSERT INTO notes(
                    note_id, owner_person_id, subject_type, subject_id,
                    is_profile_note, status, created_operation_id, created_at, updated_at
                ) VALUES (?, ?, 'PERSON', ?, 0, 'ACTIVE', ?, ?, ?)
                """,
                (
                    note_id,
                    owner_person_id,
                    owner_person_id,
                    operation_id,
                    created_at,
                    created_at,
                ),
            )
            revision_id = _insert_note_revision(
                conn,
                note_id=note_id,
                revision_number=1,
                content=normalized_content,
                mentions=mentions,
                actor=actor,
                author_name="",
                operation_id=operation_id,
                created_at=created_at,
            )
            _sync_note_reference_evidence(
                conn,
                note_id=note_id,
                owner_person_id=owner_person_id,
                revision_id=revision_id,
                mentions=mentions,
                operation_id=operation_id,
                source=_optional_text(source),
                created_at=created_at,
            )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            _transition_journal_operation(conn, operation_id, "COMMITTED", {
                "note_id": note_id,
                "owner_person_id": owner_person_id,
                "revision_number": 1,
                "mentioned_person_ids": [person_id for person_id, _ in mentions],
            })
            return _note_from_row(conn, _note_row(conn, note_id))

    def update_note(
        self,
        note_id: str,
        content: str,
        operation_id: str,
        *,
        mentioned_person_ids: list[str] | None = None,
        expected_revision_number: int | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        normalized_content = content.strip()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.update",
            )
            if existing_result is not None:
                if existing_result.get("note_id") != note_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _note_row(conn, note_id)
                if row is None:
                    raise RuntimeError("Committed note update is missing its note")
                return _note_from_row(conn, row)
            row = _note_row(conn, note_id)
            if row is None or row["status"] != "ACTIVE":
                raise KeyError(f"Unknown active note: {note_id}")
            current = _note_from_row(conn, row)
            if (
                expected_revision_number is not None
                and current.revision_number != expected_revision_number
            ):
                raise KeyError("The note was changed elsewhere. Reload it and try again.")
            mentions = _normalize_note_mentions(
                conn,
                current.owner_person_id,
                mentioned_person_ids,
                historical_person_ids=set(current.mentioned_person_ids),
            )
            desired_mention_ids = tuple(person_id for person_id, _ in mentions)
            changed = (
                current.content != normalized_content
                or current.mentioned_person_ids != desired_mention_ids
            )
            _begin_journal_operation(
                conn,
                "note.update",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "notes-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": current.owner_person_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id, _ in mentions
                    ],
                ],
                details={"previous_revision_number": current.revision_number},
            )
            revision_number = current.revision_number
            if changed:
                revision_number += 1
                created_at = utc_now()
                revision_id = _insert_note_revision(
                    conn,
                    note_id=note_id,
                    revision_number=revision_number,
                    content=normalized_content,
                    mentions=mentions,
                    actor=actor,
                    author_name="",
                    operation_id=operation_id,
                    created_at=created_at,
                )
                _sync_note_reference_evidence(
                    conn,
                    note_id=note_id,
                    owner_person_id=current.owner_person_id,
                    revision_id=revision_id,
                    mentions=mentions,
                    operation_id=operation_id,
                    source=_optional_text(source),
                    created_at=created_at,
                )
                conn.execute(
                    "UPDATE notes SET updated_at = ? WHERE note_id = ?",
                    (created_at, note_id),
                )
                if row["is_profile_note"]:
                    conn.execute(
                        "UPDATE persons SET notes = ? WHERE person_id = ?",
                        (normalized_content, current.owner_person_id),
                    )
                _replace_graph_projection(conn)
                validation = _validate_graph_projection(conn)
                if not validation["valid"]:
                    raise RuntimeError(
                        "Graph projection validation failed: "
                        + "; ".join(validation["errors"])
                    )
            _transition_journal_operation(conn, operation_id, "COMMITTED", {
                "note_id": note_id,
                "owner_person_id": current.owner_person_id,
                "revision_number": revision_number,
                "changed": changed,
                "mentioned_person_ids": list(desired_mention_ids),
            })
            return _note_from_row(conn, _note_row(conn, note_id))

    def get_note(self, note_id: str, include_retired: bool = False) -> Note | None:
        with self._connect() as conn:
            row = _note_row(conn, note_id)
            if row is None or (row["status"] == "RETIRED" and not include_retired):
                return None
            return _note_from_row(conn, row)

    def get_person_note(
        self, person_id: str, include_retired: bool = False,
    ) -> Note | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT note_id FROM notes
                WHERE owner_person_id = ? AND is_profile_note = 1
                {' ' if include_retired else "AND status = 'ACTIVE'"}
                ORDER BY CASE status WHEN 'ACTIVE' THEN 0 ELSE 1 END,
                         updated_at DESC, note_id
                LIMIT 1
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                return None
            note_row = _note_row(conn, str(row["note_id"]))
            return _note_from_row(conn, note_row)

    def list_person_notes(
        self,
        person_id: str,
        *,
        raw: bool = False,
        include_retired: bool = False,
    ) -> list[Note]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                f"""
                SELECT note_id, owner_person_id FROM notes
                {' ' if include_retired else "WHERE status = 'ACTIVE'"}
                ORDER BY updated_at DESC, note_id
                """
            ).fetchall()
            notes: list[Note] = []
            for item in rows:
                owner_id = str(item["owner_person_id"])
                matches = (
                    owner_id == str(person_id)
                    if raw
                    else _resolve_canonical_person_id(conn, owner_id) == canonical_person_id
                )
                if matches:
                    notes.append(_note_from_row(
                        conn, _note_row(conn, str(item["note_id"])),
                    ))
            return notes

    def list_note_revisions(self, note_id: str) -> list[NoteRevision]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM notes WHERE note_id = ?", (note_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown note: {note_id}")
            rows = conn.execute(
                """
                SELECT * FROM note_revisions
                WHERE note_id = ? ORDER BY revision_number
                """,
                (note_id,),
            ).fetchall()
            revisions: list[NoteRevision] = []
            for row in rows:
                mention_rows = conn.execute(
                    """
                    SELECT referenced_person_id FROM note_revision_mentions
                    WHERE revision_id = ? ORDER BY referenced_person_id
                    """,
                    (row["revision_id"],),
                ).fetchall()
                revisions.append(NoteRevision(
                    revision_id=str(row["revision_id"]),
                    note_id=str(row["note_id"]),
                    revision_number=int(row["revision_number"]),
                    content=str(row["content"]),
                    mentioned_person_ids=tuple(str(item[0]) for item in mention_rows),
                    actor=json.loads(row["actor"]),
                    author_name=str(row["author_name"]),
                    operation_id=row["operation_id"],
                    created_at=str(row["created_at"]),
                    effective_mentioned_person_ids=tuple(sorted({
                        _resolve_canonical_person_id(conn, str(item[0]))
                        for item in mention_rows
                    })),
                ))
            return revisions

    def retire_note(
        self,
        note_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.retire",
            )
            if existing_result is not None:
                if existing_result.get("note_id") != note_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _note_row(conn, note_id)
                if row is None:
                    raise RuntimeError("Committed note retirement is missing its note")
                return _note_from_row(conn, row)
            row = _note_row(conn, note_id)
            if row is None or row["status"] != "ACTIVE":
                raise KeyError(f"Unknown active note: {note_id}")
            _begin_journal_operation(
                conn,
                "note.retire",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "notes-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": row["owner_person_id"]},
                ],
            )
            retired_at = utc_now()
            active_mentions = conn.execute(
                """
                SELECT mention_id FROM note_mentions
                WHERE note_id = ? AND active = 1 ORDER BY mention_id
                """,
                (note_id,),
            ).fetchall()
            for mention in active_mentions:
                mention_id = str(mention["mention_id"])
                conn.execute(
                    """
                    UPDATE note_mentions
                    SET active = 0, retired_revision_id = ?, retired_operation_id = ?,
                        retired_at = ?
                    WHERE mention_id = ? AND active = 1
                    """,
                    (row["revision_id"], operation_id, retired_at, mention_id),
                )
                conn.execute(
                    """
                    UPDATE relationship_evidence
                    SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
                    WHERE evidence_type = 'NOTE_REFERENCE'
                      AND source_entity_type = 'NOTE'
                      AND source_entity_id = ? AND active = 1
                    """,
                    (operation_id, retired_at, mention_id),
                )
            conn.execute(
                """
                UPDATE notes
                SET status = 'RETIRED', retired_operation_id = ?, retired_at = ?,
                    updated_at = ?
                WHERE note_id = ? AND status = 'ACTIVE'
                """,
                (operation_id, retired_at, retired_at, note_id),
            )
            if row["is_profile_note"]:
                conn.execute(
                    "UPDATE persons SET notes = '' WHERE person_id = ?",
                    (row["owner_person_id"],),
                )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            _transition_journal_operation(conn, operation_id, "COMMITTED", {
                "note_id": note_id,
                "owner_person_id": row["owner_person_id"],
                "retired": True,
                "deactivated_mentions": len(active_mentions),
            })
            return _note_from_row(conn, _note_row(conn, note_id))

    def update_person_notes(
        self,
        person_id: str,
        notes: str,
        expected_previous_notes: str,
        editor_name: str,
        operation_id: str,
        mentioned_person_ids: list[str] | None = None,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> tuple[bool, Person, PersonChange | None]:
        next_notes = notes.strip()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.profile-save",
            )
            if existing_result is not None:
                if existing_result.get("person_id") != person_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                person_row = conn.execute(
                    "SELECT * FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError("This person no longer exists")
                change = None
                if existing_result.get("change_id"):
                    change_row = conn.execute(
                        "SELECT * FROM person_change_history WHERE change_id = ?",
                        (existing_result["change_id"],),
                    ).fetchone()
                    change = _person_change_from_row(change_row) if change_row else None
                return (
                    bool(existing_result.get("changed")),
                    _person_from_row(person_row),
                    change,
                )
            legacy_result = _existing_person_operation(
                conn, operation_id, "update-person-notes",
            )
            if legacy_result is not None:
                person_row = conn.execute(
                    "SELECT * FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError("This person no longer exists")
                change_row = None
                if legacy_result.get("change_id"):
                    change_row = conn.execute(
                        "SELECT * FROM person_change_history WHERE change_id = ?",
                        (legacy_result["change_id"],),
                    ).fetchone()
                return (
                    bool(legacy_result.get("changed")),
                    _person_from_row(person_row),
                    _person_change_from_row(change_row) if change_row else None,
                )
            row = conn.execute(
                """
                SELECT * FROM persons
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError("This person no longer exists")
            active_note_row = conn.execute(
                """
                SELECT note_id FROM notes
                WHERE owner_person_id = ? AND is_profile_note = 1 AND status = 'ACTIVE'
                ORDER BY updated_at DESC, note_id LIMIT 1
                """,
                (person_id,),
            ).fetchone()
            note_row = (
                _note_row(conn, str(active_note_row["note_id"]))
                if active_note_row is not None else None
            )
            current_note = _note_from_row(conn, note_row) if note_row is not None else None
            current_notes = current_note.content if current_note is not None else ""
            if current_notes != expected_previous_notes:
                raise KeyError("Notes were changed elsewhere. Reopen this profile and try again.")
            mentions = _normalize_note_mentions(
                conn,
                person_id,
                mentioned_person_ids,
                historical_person_ids=(
                    set(current_note.mentioned_person_ids) if current_note is not None else set()
                ),
            )
            desired_ids = tuple(person_id for person_id, _ in mentions)
            mentions_changed = (
                current_note is None or current_note.mentioned_person_ids != desired_ids
            )
            content_changed = current_notes != next_notes
            changed = content_changed or mentions_changed
            note_id = current_note.note_id if current_note is not None else str(uuid.uuid4())
            operation_actor = actor or {
                "display_name": editor_name.strip(),
                "roles": [],
            }
            _begin_journal_operation(
                conn,
                "note.profile-save",
                operation_id=operation_id,
                actor=operation_actor,
                source=_optional_text(source) or "person-notes",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": person_id},
                    *[
                        {"entity_type": "person", "entity_id": mentioned_id}
                        for mentioned_id, _ in mentions
                    ],
                ],
            )
            change = None
            revision_number = current_note.revision_number if current_note else 0
            if changed:
                created_at = utc_now()
                if current_note is None:
                    conn.execute(
                        """
                        INSERT INTO notes(
                            note_id, owner_person_id, subject_type, subject_id,
                            is_profile_note, status, created_operation_id, created_at, updated_at
                        ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?, ?)
                        """,
                        (
                            note_id,
                            person_id,
                            person_id,
                            operation_id,
                            created_at,
                            created_at,
                        ),
                    )
                revision_number += 1
                revision_id = _insert_note_revision(
                    conn,
                    note_id=note_id,
                    revision_number=revision_number,
                    content=next_notes,
                    mentions=mentions,
                    actor=operation_actor,
                    author_name=editor_name,
                    operation_id=operation_id,
                    created_at=created_at,
                )
                _sync_note_reference_evidence(
                    conn,
                    note_id=note_id,
                    owner_person_id=person_id,
                    revision_id=revision_id,
                    mentions=mentions,
                    operation_id=operation_id,
                    source=_optional_text(source),
                    created_at=created_at,
                )
                conn.execute(
                    "UPDATE notes SET updated_at = ? WHERE note_id = ?",
                    (created_at, note_id),
                )
                conn.execute(
                    "UPDATE persons SET notes = ? WHERE person_id = ?",
                    (next_notes, person_id),
                )
                if content_changed:
                    metadata = json.loads(row["metadata"])
                    change = PersonChange(
                        change_id=str(uuid.uuid4()),
                        person_id=person_id,
                        previous_name=row["name"],
                        new_name=row["name"],
                        previous_rank=(metadata.get("rank") or ""),
                        new_rank=(metadata.get("rank") or ""),
                        previous_country=(metadata.get("country") or ""),
                        new_country=(metadata.get("country") or ""),
                        previous_importance=(metadata.get("importance") or ""),
                        new_importance=(metadata.get("importance") or ""),
                        previous_status=row["enrollment_status"],
                        new_status=row["enrollment_status"],
                        previous_notes=current_notes,
                        new_notes=next_notes,
                        editor_name=editor_name.strip(),
                        created_at=created_at,
                    )
                    _insert_person_change(conn, change)
                _replace_graph_projection(conn)
                validation = _validate_graph_projection(conn)
                if not validation["valid"]:
                    raise RuntimeError(
                        "Graph projection validation failed: "
                        + "; ".join(validation["errors"])
                    )
            result = {
                "person_id": person_id,
                "person_ids": [person_id, *list(desired_ids)],
                "note_id": note_id,
                "change_id": change.change_id if change else None,
                "changed": changed,
                "revision_number": revision_number,
                "mentioned_person_ids": list(desired_ids),
            }
            _record_person_operation(
                conn, operation_id, "update-person-notes", result,
            )
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            updated = conn.execute("SELECT * FROM persons WHERE person_id = ?", (person_id,)).fetchone()
        return changed, _person_from_row(updated), change

    def list_person_changes(self, person_id: str) -> list[PersonChange]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT change_id, person_id, previous_name, new_name,
                       previous_rank, new_rank, previous_country, new_country,
                       previous_importance, new_importance,
                       previous_status, new_status, previous_notes, new_notes,
                       editor_name, created_at
                FROM person_change_history
                ORDER BY created_at DESC
                """
            ).fetchall()
            return [
                _person_change_from_row(row) for row in rows
                if _resolve_canonical_person_id(conn, str(row["person_id"]))
                == canonical_person_id
            ]

    def list_raw_person_changes(self, person_id: str) -> list[PersonChange]:
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
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            return self._list_person_operations(
                conn, person_id, canonical_person_id=canonical_person_id,
            )

    def list_raw_person_operations(self, person_id: str) -> list[dict]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {person_id}")
            return self._list_person_operations(conn, person_id, canonical_person_id=None)

    def _list_person_operations(
        self,
        conn: sqlite3.Connection,
        person_id: str,
        *,
        canonical_person_id: str | None,
    ) -> list[dict]:
        rows = conn.execute(
            """
            SELECT operation_id FROM operation_journal
            WHERE status IN ('COMMITTED', 'REVERTED')
            ORDER BY created_at DESC, operation_id DESC
            """
        ).fetchall()
        operations: list[dict] = []
        for row in rows:
            operation = _get_journal_operation(conn, str(row["operation_id"]))
            if operation is None:
                continue
            involved_ids = {
                str(item.get("entity_id"))
                for item in operation["affected_entities"]
                if isinstance(item, dict)
                and item.get("entity_type") == "person"
                and item.get("entity_id")
            }
            if canonical_person_id is None:
                matches = person_id in involved_ids
            else:
                matches = any(
                    _resolve_canonical_person_id(conn, str(involved_id))
                    == canonical_person_id
                    for involved_id in involved_ids
                    if conn.execute(
                        "SELECT 1 FROM persons WHERE person_id = ?", (involved_id,),
                    ).fetchone() is not None
                )
            if not matches:
                continue
            history = operation.get("status_history") or []
            result = dict(history[-1].get("details") or {}) if history else {}
            operations.append(
                {
                    "operation_id": operation["operation_id"],
                    "operation_type": operation["operation_type"],
                    "status": operation["status"],
                    "actor": operation["actor"],
                    "source": operation["source"],
                    "created_at": operation["created_at"],
                    "completed_at": operation["completed_at"],
                    "result": result,
                }
            )
        return operations

    def _legacy_create_person_association(
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

    def _legacy_create_placeholder_association(
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
                    SELECT * FROM persons WHERE person_id = ?
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

    def _legacy_remove_person_association(
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

    def record_merge_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
        context: dict | None = None,
        affected_entities: list[dict] | None = None,
        details: dict | None = None,
    ) -> dict:
        """Record failure only after the merge transaction has rolled back."""
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM merge_operations WHERE operation_journal_id = ?",
                (operation_id,),
            ).fetchone() is not None:
                raise RuntimeError("Cannot mark a merge failed while partial manifest state exists")
            existing = _get_journal_operation(conn, operation_id)
            if existing is not None:
                if existing["operation_type"] != "identity.merge":
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                if existing["status"] in {"FAILED", "ROLLED_BACK"}:
                    return existing
                if existing["status"] != "STARTED":
                    raise ValueError("Only a started merge attempt can fail")
            else:
                _begin_journal_operation(
                    conn,
                    "identity.merge",
                    operation_id=operation_id,
                    actor=actor,
                    source=_optional_text(source) or "identity-merge",
                    context=context,
                    affected_entities=affected_entities,
                    details={"transaction_rolled_back": True},
                )
            return _transition_journal_operation(
                conn,
                operation_id,
                "FAILED",
                {"transaction_rolled_back": True, **(details or {})},
            )

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

    def create_observation(
        self,
        operation_id: str,
        *,
        observed_at: str | None = None,
        location: str | None = None,
        context: dict | None = None,
        source: str | None = None,
        actor: dict | None = None,
        participant_ids: list[str] | None = None,
        media: list[dict] | None = None,
    ) -> Observation:
        observation_id = str(uuid.uuid4())
        _, context_payload = _journal_json_object(context, "observation context")
        normalized_source = _optional_text(source)
        participants = [str(item).strip() for item in (participant_ids or [])]
        if any(not item for item in participants):
            raise ValueError("Observation participant IDs cannot be empty")
        media_items = media or []
        if not isinstance(media_items, list) or any(
            not isinstance(item, dict) for item in media_items
        ):
            raise ValueError("Observation media must be a list of objects")
        created_at = utc_now()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.create",
            )
            if existing_result is not None:
                row = conn.execute(
                    "SELECT * FROM observations WHERE observation_id = ?",
                    (existing_result.get("observation_id"),),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed observation creation is missing its observation")
                return _observation_from_row(row)
            _begin_journal_operation(
                conn,
                "observation.create",
                operation_id=operation_id,
                actor=actor,
                source=normalized_source or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id in participants
                    ],
                    *[
                        {"entity_type": "media", "entity_id": str(item.get("media_id") or "")}
                        for item in media_items
                    ],
                ],
                details={"initial_status": "DRAFT"},
            )
            conn.execute(
                """
                INSERT INTO observations(
                    observation_id, status, observed_at, location, context, source,
                    created_operation_id, created_at, updated_at
                ) VALUES (?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    _optional_text(observed_at),
                    _optional_text(location),
                    context_payload,
                    normalized_source,
                    operation_id,
                    created_at,
                    created_at,
                ),
            )
            for item in media_items:
                _attach_observation_media(
                    conn,
                    observation_id,
                    str(item.get("media_id") or ""),
                    item.get("media_path"),
                    _optional_text(item.get("source")) or normalized_source,
                    operation_id,
                )
            for person_id in participants:
                _add_observation_participant(
                    conn, observation_id, person_id, normalized_source, operation_id,
                )
            result = {
                "observation_id": observation_id,
                "status": "DRAFT",
                "participant_count": len(_list_observation_participants(conn, observation_id)),
                "media_count": len(_list_observation_media(conn, observation_id)),
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            row = conn.execute(
                "SELECT * FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            return _observation_from_row(row)

    def create_photo_review(
        self,
        review_id: str,
        media_id: str,
        faces: list[dict],
        *,
        media_path: str | None = None,
        source: str = "check-photo",
    ) -> PhotoReview:
        normalized_review_id = str(review_id).strip()
        normalized_media_id = str(media_id).strip()
        if not normalized_review_id or not normalized_media_id:
            raise ValueError("Review ID and media ID are required")
        if not faces:
            raise ValueError("A review requires at least one detected face")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM photo_reviews WHERE review_id = ?", (normalized_review_id,),
            ).fetchone()
            if existing is not None:
                return _photo_review_from_conn(conn, normalized_review_id)
            _require_existing_media(conn, normalized_media_id, media_path)
            created_at = utc_now()
            conn.execute(
                """
                INSERT INTO photo_reviews(
                    review_id, media_id, media_path, source, status, created_at
                ) VALUES (?, ?, ?, ?, 'IN_PROGRESS', ?)
                """,
                (
                    normalized_review_id, normalized_media_id, _optional_text(media_path),
                    str(source).strip() or "check-photo", created_at,
                ),
            )
            seen_face_ids: set[str] = set()
            for face in faces:
                face_id = str(face.get("face_id") or "").strip()
                staged_type = str(face.get("staged_face_type") or "").strip().upper()
                staged_id = str(face.get("staged_face_id") or "").strip()
                if not face_id or face_id in seen_face_ids:
                    raise ValueError("Review face IDs must be non-empty and unique")
                _require_staged_review_face(conn, staged_type, staged_id)
                seen_face_ids.add(face_id)
                conn.execute(
                    """
                    INSERT INTO photo_review_faces(
                        review_id, face_id, staged_face_type, staged_face_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (normalized_review_id, face_id, staged_type, staged_id, created_at, created_at),
                )
            return _photo_review_from_conn(conn, normalized_review_id)

    def set_photo_review_face_decision(
        self,
        review_id: str,
        face_id: str,
        decision: str,
        *,
        person_id: str | None = None,
        new_person_key: str | None = None,
        new_person_name: str | None = None,
        new_person_metadata: dict | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
        recognition_detail: dict | None = None,
    ) -> PhotoReview:
        normalized_decision = str(decision).strip().upper()
        if normalized_decision not in REVIEW_DECISIONS:
            raise ValueError(f"Unsupported review decision: {decision}")
        metadata, metadata_payload = _journal_json_object(
            new_person_metadata, "new person metadata",
        )
        del metadata
        _, recognition_detail_payload = _journal_json_object(
            recognition_detail, "recognition detail",
        )
        mention_ids = sorted({str(item).strip() for item in (mentioned_person_ids or []) if str(item).strip()})
        with self._connect() as conn:
            review = conn.execute(
                "SELECT status FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if review is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if review["status"] != "IN_PROGRESS":
                raise ValueError("Only an in-progress review can be changed")
            if normalized_decision == "ACCEPT_EXISTING_PERSON":
                _require_active_review_person(conn, person_id)
                new_person_key = new_person_name = None
            elif normalized_decision == "ACCEPT_NEW_PERSON":
                if not str(new_person_name or "").strip():
                    raise ValueError("A name is required for a new person decision")
                person_id = None
                new_person_key = str(new_person_key or face_id).strip()
            else:
                person_id = new_person_key = new_person_name = None
                metadata_payload = "{}"
                notes = ""
                mention_ids = []
                recognition_detail_payload = "{}"
            cursor = conn.execute(
                """
                UPDATE photo_review_faces
                SET decision = ?, person_id = ?, new_person_key = ?, new_person_name = ?,
                    new_person_metadata = ?, notes = ?, mentioned_person_ids = ?,
                    recognition_detail = ?, updated_at = ?
                WHERE review_id = ? AND face_id = ?
                """,
                (
                    normalized_decision, person_id, new_person_key,
                    _optional_text(new_person_name), metadata_payload, str(notes or "").strip(),
                    json.dumps(mention_ids, separators=(",", ":")),
                    recognition_detail_payload, utc_now(), review_id, face_id,
                ),
            )
            if not cursor.rowcount:
                raise KeyError(f"Unknown review face: {face_id}")
            return _photo_review_from_conn(conn, review_id)

    def get_photo_review(self, review_id: str) -> PhotoReview | None:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone() is None:
                return None
            return _photo_review_from_conn(conn, review_id)

    def cancel_photo_review(self, review_id: str) -> PhotoReview:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if row["status"] == "COMPLETED":
                raise ValueError("A completed review cannot be cancelled")
            conn.execute(
                "UPDATE photo_reviews SET status = 'CANCELLED' WHERE review_id = ?",
                (review_id,),
            )
            _remove_review_staging(conn, review_id)
            return _photo_review_from_conn(conn, review_id)

    def complete_photo_review(
        self,
        review_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        """Commit a complete review and all authoritative consequences atomically."""
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "review.complete",
            )
            if existing is not None:
                if existing.get("review_id") != review_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            review = conn.execute(
                "SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if review is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if review["status"] != "IN_PROGRESS":
                raise ValueError("Only an in-progress review can be completed")
            face_rows = conn.execute(
                "SELECT * FROM photo_review_faces WHERE review_id = ? ORDER BY face_id",
                (review_id,),
            ).fetchall()
            if not face_rows or any(row["decision"] is None for row in face_rows):
                raise ValueError("Every detected face requires a final decision before completion")
            _begin_journal_operation(
                conn,
                "review.complete",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or str(review["source"]),
                affected_entities=[
                    {"entity_type": "review", "entity_id": review_id},
                    {"entity_type": "media", "entity_id": review["media_id"]},
                ],
                details={"face_count": len(face_rows)},
            )
            assigned_by_face: dict[str, str] = {}
            created_by_key: dict[str, str] = {}
            created_person_ids: list[str] = []
            embedding_ids: list[str] = []
            embedding_by_face: dict[str, str] = {}
            note_ids: list[str] = []
            created_note_keys: set[tuple[str, str, tuple[str, ...]]] = set()
            staged_media_paths: set[str] = set()
            media_by_face: dict[str, str] = {}
            detail_inputs: list[tuple[str, str, str, dict, str]] = []
            for row in face_rows:
                decision = str(row["decision"])
                if decision in {"EXCLUDE", "SKIP"}:
                    continue
                staged = _staged_review_face_row(conn, row["staged_face_type"], row["staged_face_id"])
                staged_media_paths.add(str(staged["source_image"]))
                media_by_face[str(row["face_id"])] = str(staged["source_image"])
                if decision == "ACCEPT_EXISTING_PERSON":
                    person_id = _require_active_review_person(conn, row["person_id"])
                else:
                    key = str(row["new_person_key"] or row["face_id"])
                    person_id = created_by_key.get(key)
                    if person_id is None:
                        name = str(row["new_person_name"] or "").strip()
                        metadata = json.loads(row["new_person_metadata"] or "{}")
                        if not _has_meaningful_identity_context(name, metadata, str(row["notes"] or "")):
                            raise ValueError("A new person requires meaningful identity or context")
                        person_id = str(uuid.uuid4())
                        _insert_identified_person_record(
                            conn,
                            person_id=person_id,
                            name=name,
                            metadata=metadata,
                            enrollment_status="enrolled",
                        )
                        created_by_key[key] = person_id
                        created_person_ids.append(person_id)
                assigned_by_face[str(row["face_id"])] = person_id
                duplicate = conn.execute(
                    "SELECT embedding_id FROM embeddings WHERE person_id = ? AND vector = ? AND deleted_at IS NULL",
                    (person_id, staged["vector"]),
                ).fetchone()
                if duplicate is None:
                    embedding_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO embeddings(
                            embedding_id, person_id, vector, quality_score,
                            source_image, crop_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id, person_id, staged["vector"], staged["quality_score"],
                            staged["source_image"], staged["crop_path"], utc_now(),
                        ),
                    )
                    embedding_ids.append(embedding_id)
                else:
                    embedding_id = str(duplicate["embedding_id"])
                _mark_person_enrolled(conn, person_id)
                embedding_by_face[str(row["face_id"])] = embedding_id
                content = str(row["notes"] or "").strip()
                mention_ids = json.loads(row["mentioned_person_ids"] or "[]")
                note_key = (person_id, content, tuple(sorted(mention_ids)))
                if (content or mention_ids) and note_key not in created_note_keys:
                    note_ids.append(_create_review_person_note(
                        conn, person_id, content, mention_ids, operation_id, actor,
                        _optional_text(source) or str(review["source"]),
                    ))
                    created_note_keys.add(note_key)
                detail_payload = json.loads(row["recognition_detail"] or "{}")
                if detail_payload:
                    detail_inputs.append((
                        str(row["face_id"]), person_id, embedding_id,
                        detail_payload, content,
                    ))
            if not assigned_by_face:
                raise ValueError("A completed review requires at least one accepted person")
            canonical_participants: dict[str, str] = {}
            for face_id in sorted(assigned_by_face):
                raw_id = assigned_by_face[face_id]
                canonical_participants.setdefault(_resolve_canonical_person_id(conn, raw_id), raw_id)
            observation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface:review:{review_id}"))
            now = utc_now()
            conn.execute(
                """
                INSERT INTO observations(
                    observation_id, status, source, created_operation_id,
                    created_at, updated_at
                ) VALUES (?, 'DRAFT', ?, ?, ?, ?)
                """,
                (observation_id, str(review["source"]), operation_id, now, now),
            )
            _attach_observation_media(
                conn, observation_id, review["media_id"], review["media_path"],
                str(review["source"]), operation_id,
            )
            for face_id in sorted(assigned_by_face):
                assignment_id = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"sentriface:observation-face:{observation_id}:{face_id}",
                ))
                conn.execute(
                    """
                    INSERT INTO observation_face_assignments(
                        assignment_id, observation_id, review_id, face_id,
                        embedding_id, original_person_id, created_operation_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assignment_id, observation_id, review_id, face_id,
                        embedding_by_face[face_id], assigned_by_face[face_id],
                        operation_id, now,
                    ),
                )
            primary_path = str(review["media_path"] or "")
            for media_path in sorted(staged_media_paths):
                if media_path == primary_path:
                    continue
                _attach_observation_media(
                    conn, observation_id, media_path, media_path,
                    str(review["source"]), operation_id,
                )
            for canonical_id in sorted(canonical_participants):
                _add_observation_participant(
                    conn, observation_id, canonical_id, str(review["source"]), operation_id,
                )
            finalized_at = utc_now()
            conn.execute(
                """
                UPDATE observations SET status = 'FINALIZED', finalized_at = ?, updated_at = ?
                WHERE observation_id = ?
                """,
                (finalized_at, finalized_at, observation_id),
            )
            participant_ids = sorted(canonical_participants)
            detail_ids: list[str] = []
            for face_id, person_id, embedding_id, detail, detail_notes in detail_inputs:
                detail_id = str(uuid.uuid4())
                person_name = str(conn.execute(
                    "SELECT name FROM persons WHERE person_id = ?", (person_id,),
                ).fetchone()[0])
                conn.execute(
                    """
                    INSERT INTO recognition_details(
                        detail_id, embedding_id, person_id, image_id, image_path,
                        name, decision, seen_date, seen_time, place_seen,
                        individual_count, event_occasion, rank, country,
                        importance, added_by, notes, created_at, observation_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail_id, embedding_id, person_id,
                        str(detail.get("image_id") or f"{review['media_id']}#{face_id}"),
                        str(detail.get("image_path") or review["media_path"] or ""),
                        str(detail.get("name") or person_name),
                        str(detail.get("decision") or "accepted"),
                        str(detail.get("date") or detail.get("seen_date") or ""),
                        str(detail.get("time") or detail.get("seen_time") or ""),
                        str(detail.get("place_seen") or ""),
                        int(detail.get("individual_count") or len(participant_ids)),
                        str(detail.get("event_occasion") or ""),
                        _optional_text(detail.get("rank")),
                        _optional_text(detail.get("country")),
                        _optional_text(detail.get("importance")),
                        _optional_text(detail.get("added_by")),
                        detail_notes, utc_now(), observation_id,
                    ),
                )
                detail_ids.append(detail_id)
            evidence_ids: list[str] = []
            for index, first_id in enumerate(participant_ids):
                for second_id in participant_ids[index + 1:]:
                    evidence_ids.append(_insert_relationship_evidence(
                        conn,
                        evidence_type="CO_OBSERVED",
                        source_entity_type="OBSERVATION",
                        source_entity_id=observation_id,
                        source_person_id=first_id,
                        target_person_id=second_id,
                        relationship_type="ASSOCIATED_WITH",
                        directionality="UNDIRECTED",
                        source=_optional_text(source) or str(review["source"]),
                        created_operation_id=operation_id,
                        created_at=finalized_at,
                    ))
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            conn.execute(
                """
                UPDATE photo_reviews
                SET status = 'COMPLETED', observation_id = ?,
                    completed_operation_id = ?, completed_at = ?
                WHERE review_id = ? AND status = 'IN_PROGRESS'
                """,
                (observation_id, operation_id, finalized_at, review_id),
            )
            _remove_review_staging(conn, review_id)
            result = {
                "review_id": review_id,
                "media_id": str(review["media_id"]),
                "media_ids": [
                    item.media_id for item in _list_observation_media(conn, observation_id)
                ],
                "observation_id": observation_id,
                "accepted_existing_person_ids": sorted({
                    str(row["person_id"]) for row in face_rows
                    if row["decision"] == "ACCEPT_EXISTING_PERSON"
                }),
                "created_person_ids": created_person_ids,
                "created_people": [
                    {
                        "person_id": person_id,
                        "name": str(conn.execute(
                            "SELECT name FROM persons WHERE person_id = ?", (person_id,),
                        ).fetchone()[0]),
                    }
                    for person_id in created_person_ids
                ],
                "excluded_count": sum(
                    row["decision"] in {"EXCLUDE", "SKIP"} for row in face_rows
                ),
                "participant_ids": participant_ids,
                "embedding_ids": embedding_ids,
                "embedding_assignments": embedding_by_face,
                "face_media": media_by_face,
                "note_ids": note_ids,
                "recognition_detail_ids": detail_ids,
                "graph_evidence_ids": evidence_ids,
                "graph_evidence_count": len(evidence_ids),
                "face_assignments": assigned_by_face,
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def correct_observation_identity(
        self,
        observation_id: str,
        from_person_id: str,
        to_person_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.observation.correct",
            )
            if existing is not None:
                if existing.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            observation = _require_observation(conn, observation_id)
            if observation["status"] != "FINALIZED":
                raise ValueError("Only a finalized observation can be corrected")
            canonical_from_person_id = _resolve_canonical_person_id(conn, from_person_id)
            canonical_to_person_id = _resolve_canonical_person_id(conn, to_person_id)
            _require_active_review_person(conn, canonical_to_person_id)
            if canonical_from_person_id == canonical_to_person_id:
                raise ValueError("Correction source and target must be different")
            effective_before = _effective_observation_person_ids(conn, observation_id)
            if canonical_from_person_id not in effective_before:
                raise KeyError(
                    f"Person {canonical_from_person_id} is not an effective participant"
                )
            corrected_raw_before = _corrected_observation_person_ids(conn, observation_id)
            matching_raw_ids = {
                raw_person_id for raw_person_id in corrected_raw_before
                if _resolve_canonical_person_id(conn, raw_person_id)
                == canonical_from_person_id
            }
            assignments = _effective_face_assignments(conn, observation_id)
            matching = [
                item for item in assignments
                if _resolve_canonical_person_id(conn, item["current_person_id"])
                == canonical_from_person_id
            ]
            affected_entities = [
                {"entity_type": "observation", "entity_id": observation_id},
                {"entity_type": "person", "entity_id": canonical_from_person_id},
                {"entity_type": "person", "entity_id": canonical_to_person_id},
                *[
                    {"entity_type": "embedding", "entity_id": item["embedding_id"]}
                    for item in matching
                ],
            ]
            _begin_journal_operation(
                conn,
                "identity.observation.correct",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-correction-service",
                affected_entities=affected_entities,
                details={
                    "observation_id": observation_id,
                    "from_person_id": canonical_from_person_id,
                    "to_person_id": canonical_to_person_id,
                    "raw_from_person_ids": sorted(matching_raw_ids),
                },
            )
            correction_ids: list[str] = []
            for assignment in matching:
                correction_ids.append(_insert_identity_correction(
                    conn,
                    correction_type="FACE_ASSIGNMENT",
                    observation_id=observation_id,
                    face_assignment_id=assignment["assignment_id"],
                    embedding_id=assignment["embedding_id"],
                    from_person_id=str(assignment["current_person_id"]),
                    to_person_id=canonical_to_person_id,
                    operation_id=operation_id,
                ))
            assignment_current_ids = {
                str(item["current_person_id"]) for item in matching
            }
            for raw_from_person_id in sorted(matching_raw_ids - assignment_current_ids):
                correction_ids.append(_insert_identity_correction(
                    conn,
                    correction_type="OBSERVATION_IDENTITY",
                    observation_id=observation_id,
                    face_assignment_id=None,
                    embedding_id=None,
                    from_person_id=raw_from_person_id,
                    to_person_id=canonical_to_person_id,
                    operation_id=operation_id,
                ))
            effective_after, evidence_ids = _recalculate_observation_evidence(
                conn, observation_id, operation_id,
                _optional_text(source) or "identity-correction-service",
            )
            result = {
                "observation_id": observation_id,
                "from_person_id": canonical_from_person_id,
                "to_person_id": canonical_to_person_id,
                "raw_from_person_ids": sorted(matching_raw_ids),
                "previous_participant_ids": effective_before,
                "participant_ids": effective_after,
                "correction_ids": correction_ids,
                "graph_evidence_ids": evidence_ids,
                "graph_evidence_count": len(evidence_ids),
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def move_face(
        self,
        embedding_id: str,
        to_person_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.face.move",
            )
            if existing is not None:
                if existing.get("embedding_id") != embedding_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            target_person_id = _require_active_review_person(
                conn, _resolve_canonical_person_id(conn, to_person_id),
            )
            embedding = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.deleted_at
                FROM embeddings e
                WHERE e.embedding_id = ?
                  AND e.deleted_at IS NULL
                """,
                (embedding_id,),
            ).fetchone()
            if embedding is None:
                raise KeyError(f"Unknown active embedding: {embedding_id}")
            raw_from_person_id = _raw_embedding_owner_person_id(conn, embedding)
            from_person_id = _effective_embedding_owner_person_id(conn, embedding)
            if from_person_id == target_person_id:
                raise ValueError("Face already belongs to the selected person")
            source = conn.execute(
                "SELECT metadata FROM persons WHERE person_id = ?",
                (from_person_id,),
            ).fetchone()
            if source is None:
                raise KeyError(f"Unknown current embedding owner: {from_person_id}")
            assignments = conn.execute(
                """
                SELECT observation_id FROM observation_face_assignments
                WHERE embedding_id = ? ORDER BY observation_id
                """,
                (embedding_id,),
            ).fetchall()
            affected_observation_ids = sorted({str(row["observation_id"]) for row in assignments})
            _begin_journal_operation(
                conn,
                "identity.face.move",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-correction-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": from_person_id},
                    {"entity_type": "person", "entity_id": target_person_id},
                    *[
                        {"entity_type": "observation", "entity_id": item}
                        for item in affected_observation_ids
                    ],
                ],
                details={
                    "raw_owner_person_id": raw_from_person_id,
                    "from_person_id": from_person_id,
                    "to_person_id": target_person_id,
                },
            )
            correction_ids = [_insert_identity_correction(
                conn,
                correction_type="FACE_OWNERSHIP",
                observation_id=None,
                face_assignment_id=None,
                embedding_id=embedding_id,
                from_person_id=from_person_id,
                to_person_id=target_person_id,
                operation_id=operation_id,
            )]
            for observation_id in affected_observation_ids:
                for assignment in _effective_face_assignments(conn, observation_id):
                    if (
                        assignment["embedding_id"] == embedding_id
                        and _resolve_canonical_person_id(
                            conn, assignment["current_person_id"],
                        ) == from_person_id
                    ):
                        correction_ids.append(_insert_identity_correction(
                            conn,
                            correction_type="FACE_ASSIGNMENT",
                            observation_id=observation_id,
                            face_assignment_id=assignment["assignment_id"],
                            embedding_id=embedding_id,
                            from_person_id=assignment["current_person_id"],
                            to_person_id=target_person_id,
                            operation_id=operation_id,
                        ))
            source_metadata = json.loads(source["metadata"] or "{}")
            if source_metadata.get("representative_embedding_id") == embedding_id:
                source_metadata.pop("representative_embedding_id", None)
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(source_metadata, separators=(",", ":")), from_person_id),
                )
            remaining = any(
                _effective_embedding_owner_person_id(conn, item) == from_person_id
                for item in conn.execute(
                    "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
                ).fetchall()
            )
            if not remaining:
                conn.execute(
                    """
                    UPDATE persons
                    SET biometric_status = 'NO_FACE', enrollment_status = 'placeholder'
                    WHERE person_id = ?
                    """,
                    (from_person_id,),
                )
            _mark_person_enrolled(conn, target_person_id)
            graph_evidence_ids: list[str] = []
            participants_by_observation: dict[str, list[str]] = {}
            for observation_id in affected_observation_ids:
                participants, evidence_ids = _recalculate_observation_evidence(
                    conn, observation_id, operation_id,
                    _optional_text(source) or "identity-correction-service",
                )
                participants_by_observation[observation_id] = participants
                graph_evidence_ids.extend(evidence_ids)
            if not affected_observation_ids:
                _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "embedding_id": embedding_id,
                "raw_owner_person_id": raw_from_person_id,
                "source_person_id": from_person_id,
                "target_person_id": target_person_id,
                "moved": True,
                "changed": True,
                "affected_observation_ids": affected_observation_ids,
                "participants_by_observation": participants_by_observation,
                "correction_ids": correction_ids,
                "graph_evidence_ids": graph_evidence_ids,
                "graph_evidence_count": len(graph_evidence_ids),
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def add_face_to_person(
        self,
        review_id: str,
        person_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.face.add",
            )
            if existing is not None:
                if existing.get("review_id") != review_id or existing.get("person_id") != person_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            person_id = _require_active_review_person(
                conn, _resolve_canonical_person_id(conn, person_id),
            )
            review = conn.execute(
                "SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if review is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if review["status"] != "IN_PROGRESS":
                raise ValueError("Only an in-progress review can add a face")
            faces = conn.execute(
                "SELECT * FROM photo_review_faces WHERE review_id = ? ORDER BY face_id",
                (review_id,),
            ).fetchall()
            if not faces or any(row["decision"] is None for row in faces):
                raise ValueError("Every detected face requires a final decision before completion")
            accepted = [row for row in faces if row["decision"] == "ACCEPT_EXISTING_PERSON"]
            if not accepted:
                raise ValueError("Add Face requires at least one accepted face")
            if any(
                _resolve_canonical_person_id(conn, str(row["person_id"] or "")) != person_id
                for row in accepted
            ):
                raise ValueError("Every accepted face must target the selected existing person")
            if any(row["decision"] == "ACCEPT_NEW_PERSON" for row in faces):
                raise ValueError("Add Face cannot create another identity")
            _begin_journal_operation(
                conn,
                "identity.face.add",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-correction-service",
                affected_entities=[
                    {"entity_type": "review", "entity_id": review_id},
                    {"entity_type": "person", "entity_id": person_id},
                    *[
                        {"entity_type": "review_face", "entity_id": str(row["face_id"])}
                        for row in accepted
                    ],
                ],
                details={"person_id": person_id, "accepted_face_count": len(accepted)},
            )
            embedding_ids: list[str] = []
            created_embedding_ids: list[str] = []
            for row in accepted:
                staged = _staged_review_face_row(
                    conn, row["staged_face_type"], row["staged_face_id"],
                )
                duplicate = conn.execute(
                    """
                    SELECT embedding_id FROM embeddings
                    WHERE person_id = ? AND vector = ? AND deleted_at IS NULL
                    """,
                    (person_id, staged["vector"]),
                ).fetchone()
                if duplicate is None:
                    embedding_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO embeddings(
                            embedding_id, person_id, vector, quality_score,
                            source_image, crop_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id, person_id, staged["vector"], staged["quality_score"],
                            staged["source_image"], staged["crop_path"], utc_now(),
                        ),
                    )
                    created_embedding_ids.append(embedding_id)
                else:
                    embedding_id = str(duplicate["embedding_id"])
                embedding_ids.append(embedding_id)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO biometric_enrollment_history(
                        enrollment_id, embedding_id, person_id, review_id, operation_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface:enrollment:{operation_id}:{embedding_id}")),
                        embedding_id, person_id, review_id, operation_id, utc_now(),
                    ),
                )
            _mark_person_enrolled(conn, person_id)
            completed_at = utc_now()
            conn.execute(
                """
                UPDATE photo_reviews
                SET status = 'COMPLETED', completed_operation_id = ?, completed_at = ?
                WHERE review_id = ? AND status = 'IN_PROGRESS'
                """,
                (operation_id, completed_at, review_id),
            )
            _remove_review_staging(conn, review_id)
            result = {
                "review_id": review_id,
                "person_id": person_id,
                "embedding_ids": embedding_ids,
                "created_embedding_ids": created_embedding_ids,
                "created_person_ids": [],
                "observation_id": None,
                "graph_evidence_ids": [],
                "graph_evidence_count": 0,
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_corrections_for_observation(
        self, observation_id: str,
    ) -> list[IdentityCorrection]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM identity_corrections
                WHERE observation_id = ? ORDER BY created_at, correction_id
                """,
                (observation_id,),
            ).fetchall()
        return [_identity_correction_from_row(row) for row in rows]

    def list_corrections_for_embedding(
        self, embedding_id: str,
    ) -> list[IdentityCorrection]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM identity_corrections
                WHERE embedding_id = ? ORDER BY created_at, correction_id
                """,
                (embedding_id,),
            ).fetchall()
        return [_identity_correction_from_row(row) for row in rows]

    def get_observation(self, observation_id: str) -> Observation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
        return _observation_from_row(row) if row else None

    def update_observation(
        self,
        observation_id: str,
        operation_id: str,
        *,
        observed_at: str | None = None,
        location: str | None = None,
        context: dict | None = None,
        source: str | None = None,
        actor: dict | None = None,
    ) -> Observation:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.update",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _require_observation(conn, observation_id)
                return _observation_from_row(row)
            current = _require_draft_observation(conn, observation_id)
            if context is None:
                context_payload = current["context"]
            else:
                _, context_payload = _journal_json_object(context, "observation context")
            _begin_journal_operation(
                conn,
                "observation.update",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                ],
            )
            updated_at = utc_now()
            conn.execute(
                """
                UPDATE observations
                SET observed_at = ?, location = ?, context = ?, source = ?, updated_at = ?
                WHERE observation_id = ? AND status = 'DRAFT'
                """,
                (
                    current["observed_at"] if observed_at is None else _optional_text(observed_at),
                    current["location"] if location is None else _optional_text(location),
                    context_payload,
                    current["source"] if source is None else _optional_text(source),
                    updated_at,
                    observation_id,
                ),
            )
            result = {"observation_id": observation_id, "updated": True}
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            updated = conn.execute(
                "SELECT * FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            return _observation_from_row(updated)

    def attach_observation_media(
        self,
        observation_id: str,
        media_id: str,
        operation_id: str,
        *,
        media_path: str | None = None,
        source: str | None = None,
        actor: dict | None = None,
    ) -> ObservationMedia:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.media.attach",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = conn.execute(
                    """
                    SELECT observation_id, media_id, media_path, source, operation_id, created_at
                    FROM observation_media WHERE observation_id = ? AND media_id = ?
                    """,
                    (observation_id, existing_result.get("media_id")),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed media attachment is missing its membership")
                return _observation_media_from_row(row)
            _require_draft_observation(conn, observation_id)
            _begin_journal_operation(
                conn,
                "observation.media.attach",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    {"entity_type": "media", "entity_id": str(media_id).strip()},
                ],
            )
            item, changed = _attach_observation_media(
                conn, observation_id, media_id, media_path, source, operation_id,
            )
            _transition_journal_operation(
                conn,
                operation_id,
                "COMMITTED",
                {"observation_id": observation_id, "media_id": item.media_id, "changed": changed},
            )
            return item

    def add_observation_participant(
        self,
        observation_id: str,
        person_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> ObservationParticipant:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.participant.add",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                participants = _list_raw_observation_participants(conn, observation_id)
                for participant in participants:
                    if participant.person_id == existing_result.get("person_id"):
                        return participant
                raise RuntimeError("Committed participant addition is missing its participant")
            _require_draft_observation(conn, observation_id)
            raw_person_id = str(person_id).strip()
            if not raw_person_id:
                raise ValueError("Person ID is required")
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (raw_person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {raw_person_id}")
            _begin_journal_operation(
                conn,
                "observation.participant.add",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    {"entity_type": "person", "entity_id": raw_person_id},
                ],
            )
            participant, changed = _add_observation_participant(
                conn, observation_id, raw_person_id, source, operation_id,
            )
            _transition_journal_operation(
                conn,
                operation_id,
                "COMMITTED",
                {
                    "observation_id": observation_id,
                    "person_id": participant.person_id,
                    "canonical_person_id": participant.canonical_person_id,
                    "changed": changed,
                },
            )
            return participant

    def remove_observation_participant(
        self,
        observation_id: str,
        person_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.participant.remove",
            )
            if existing_result is not None:
                if (
                    existing_result.get("observation_id") != observation_id
                    or existing_result.get("person_id") != str(person_id).strip()
                ):
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing_result
            _require_draft_observation(conn, observation_id)
            raw_person_id = str(person_id).strip()
            if not raw_person_id:
                raise ValueError("Person ID is required")
            _begin_journal_operation(
                conn,
                "observation.participant.remove",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    {"entity_type": "person", "entity_id": raw_person_id},
                ],
            )
            cursor = conn.execute(
                "DELETE FROM observation_participants WHERE observation_id = ? AND person_id = ?",
                (observation_id, raw_person_id),
            )
            result = {
                "observation_id": observation_id,
                "person_id": raw_person_id,
                "removed": bool(cursor.rowcount),
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        return self.list_effective_observation_participants(observation_id)

    def list_raw_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        with self._connect() as conn:
            _require_observation(conn, observation_id)
            return _list_raw_observation_participants(conn, observation_id)

    def list_effective_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        with self._connect() as conn:
            _require_observation(conn, observation_id)
            return _list_observation_participants(conn, observation_id)

    def list_observation_media(self, observation_id: str) -> list[ObservationMedia]:
        with self._connect() as conn:
            _require_observation(conn, observation_id)
            return _list_observation_media(conn, observation_id)

    def _finalize_observation_without_graph_evidence(
        self,
        observation_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> Observation:
        """Low-level P3 primitive reserved for fixtures and future atomic P6 work."""
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.finalize",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _require_observation(conn, observation_id)
                return _observation_from_row(row)
            _require_draft_observation(conn, observation_id)
            participant_count = int(conn.execute(
                "SELECT COUNT(*) FROM observation_participants WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()[0])
            if participant_count < 1:
                raise ValueError("A finalized observation requires at least one participant")
            _begin_journal_operation(
                conn,
                "observation.finalize",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                ],
                details={"participant_count": participant_count},
            )
            finalized_at = utc_now()
            conn.execute(
                """
                UPDATE observations
                SET status = 'FINALIZED', finalized_at = ?, updated_at = ?
                WHERE observation_id = ? AND status = 'DRAFT'
                """,
                (finalized_at, finalized_at, observation_id),
            )
            # A finalized event is World-visible even when it has one participant and
            # therefore creates no relationship evidence/projection replacement.
            _advance_graph_revision(conn)
            result = {
                "observation_id": observation_id,
                "status": "FINALIZED",
                "participant_count": participant_count,
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            row = conn.execute(
                "SELECT * FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            return _observation_from_row(row)

    def list_observations_for_person(self, person_id: str) -> list[Observation]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = [
                row for row in conn.execute(
                    """
                    SELECT o.* FROM observations o
                    ORDER BY COALESCE(o.observed_at, o.created_at) DESC, o.observation_id
                    """
                ).fetchall()
                if canonical_person_id
                in _effective_observation_person_ids(conn, str(row["observation_id"]))
            ]
        return [_observation_from_row(row) for row in rows]

    def list_raw_observations_for_person(self, person_id: str) -> list[Observation]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {person_id}")
            rows = conn.execute(
                """
                SELECT o.* FROM observations o
                JOIN observation_participants p ON p.observation_id = o.observation_id
                WHERE p.person_id = ?
                ORDER BY COALESCE(o.observed_at, o.created_at) DESC, o.observation_id
                """,
                (person_id,),
            ).fetchall()
        return [_observation_from_row(row) for row in rows]

    def list_person_sightings(self, person_id: str) -> list[Sighting]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            return _list_person_sightings(conn, canonical_person_id)

    def get_person_intelligence(self, person_id: str) -> PersonIntelligence:
        with self._connect() as conn:
            requested = conn.execute(
                "SELECT * FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone()
            if requested is None:
                raise KeyError(f"Unknown person: {person_id}")
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            canonical = conn.execute(
                "SELECT * FROM persons WHERE person_id = ?", (canonical_person_id,),
            ).fetchone()
            if canonical is None:
                raise RuntimeError("Canonical person record is unavailable")
            sightings = _list_person_sightings(conn, canonical_person_id)
            presence = _presence_analytics(sightings)
            relationships = _person_relationship_analytics(conn, canonical_person_id)
            embedding_count = sum(
                _effective_embedding_owner_person_id(conn, row) == canonical_person_id
                for row in conn.execute(
                    "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
                ).fetchall()
            )
            activity = tuple(self._list_person_operations(
                conn, canonical_person_id, canonical_person_id=canonical_person_id,
            ))
            return PersonIntelligence(
                requested_person_id=person_id,
                canonical_person_id=canonical_person_id,
                lifecycle_status=str(requested["lifecycle_status"]),
                canonical_lifecycle_status=str(canonical["lifecycle_status"]),
                biometric_status=str(canonical["biometric_status"]),
                embedding_count=embedding_count,
                confidence_summary={
                    "score": None,
                    "basis": "operator-finalized observations and current biometric enrollment",
                    "accepted_observation_count": presence.observation_count,
                    "active_embedding_count": embedding_count,
                    "probabilistic_confidence_available": False,
                },
                presence=presence,
                relationships=relationships,
                activity=activity,
                provenance=(
                    "persons.lifecycle_status",
                    "persons.canonical_person_id",
                    "finalized observations and effective participants",
                    "active relationship_evidence",
                    "operation_journal",
                ),
            )

    def list_observations_for_media(self, media_id: str) -> list[Observation]:
        normalized_media_id = str(media_id).strip()
        if not normalized_media_id:
            raise ValueError("Media ID is required")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT o.*
                FROM observations o
                JOIN observation_media m ON m.observation_id = o.observation_id
                WHERE m.media_id = ?
                ORDER BY COALESCE(o.observed_at, o.created_at) DESC, o.observation_id
                """,
                (normalized_media_id,),
            ).fetchall()
        return [_observation_from_row(row) for row in rows]

    def record_observation_evidence(
        self,
        observation_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        normalized_observation_id = str(observation_id).strip()
        if not normalized_observation_id:
            raise ValueError("Observation ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "graph.observation-evidence.record",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != normalized_observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return _list_relationship_evidence_for_source(
                    conn, "CO_OBSERVED", normalized_observation_id,
                )
            observation = _require_observation(conn, normalized_observation_id)
            if observation["status"] != "FINALIZED":
                raise ValueError("Co-observation evidence requires a finalized observation")
            participants = conn.execute(
                """
                SELECT person_id
                FROM observation_participants
                WHERE observation_id = ?
                ORDER BY person_id
                """,
                (normalized_observation_id,),
            ).fetchall()
            raw_person_ids = [str(participant["person_id"]) for participant in participants]
            _begin_journal_operation(
                conn,
                "graph.observation-evidence.record",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "global-graph-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": normalized_observation_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id in raw_person_ids
                    ],
                ],
                details={"evidence_type": "CO_OBSERVED"},
            )
            created_at = utc_now()
            for index, first_person_id in enumerate(raw_person_ids):
                for second_person_id in raw_person_ids[index + 1:]:
                    _insert_relationship_evidence(
                        conn,
                        evidence_type="CO_OBSERVED",
                        source_entity_type="OBSERVATION",
                        source_entity_id=normalized_observation_id,
                        source_person_id=first_person_id,
                        target_person_id=second_person_id,
                        relationship_type="ASSOCIATED_WITH",
                        directionality="UNDIRECTED",
                        source=_optional_text(source),
                        created_operation_id=operation_id,
                        created_at=created_at,
                    )
            evidence = _list_relationship_evidence_for_source(
                conn, "CO_OBSERVED", normalized_observation_id,
            )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "observation_id": normalized_observation_id,
                "evidence_ids": [item.evidence_id for item in evidence],
                "evidence_count": len(evidence),
                "connection_count": validation["actual_connection_count"],
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return evidence

    def deactivate_relationship_evidence(
        self,
        evidence_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> RelationshipEvidence:
        normalized_evidence_id = str(evidence_id).strip()
        if not normalized_evidence_id:
            raise ValueError("Evidence ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "graph.evidence.deactivate",
            )
            if existing_result is not None:
                if existing_result.get("evidence_id") != normalized_evidence_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = conn.execute(
                    "SELECT * FROM relationship_evidence WHERE evidence_id = ?",
                    (normalized_evidence_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed evidence deactivation is missing its evidence")
                return _relationship_evidence_from_row(row)
            row = conn.execute(
                "SELECT * FROM relationship_evidence WHERE evidence_id = ?",
                (normalized_evidence_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown relationship evidence: {normalized_evidence_id}")
            _begin_journal_operation(
                conn,
                "graph.evidence.deactivate",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "global-graph-service",
                affected_entities=[
                    {"entity_type": "relationship_evidence", "entity_id": normalized_evidence_id},
                    {"entity_type": "person", "entity_id": row["source_person_id"]},
                    {"entity_type": "person", "entity_id": row["target_person_id"]},
                ],
            )
            changed = False
            if bool(row["active"]):
                deactivated_at = utc_now()
                conn.execute(
                    """
                    UPDATE relationship_evidence
                    SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
                    WHERE evidence_id = ? AND active = 1
                    """,
                    (operation_id, deactivated_at, normalized_evidence_id),
                )
                changed = True
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "evidence_id": normalized_evidence_id,
                "deactivated": True,
                "changed": changed,
                "connection_count": validation["actual_connection_count"],
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            updated = conn.execute(
                "SELECT * FROM relationship_evidence WHERE evidence_id = ?",
                (normalized_evidence_id,),
            ).fetchone()
            return _relationship_evidence_from_row(updated)

    def deactivate_relationship_evidence_for_source(
        self,
        evidence_type: str,
        source_entity_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        normalized_type = str(evidence_type).strip().upper()
        if normalized_type not in RELATIONSHIP_EVIDENCE_TYPES:
            raise ValueError(f"Unsupported relationship evidence type: {evidence_type}")
        normalized_source_entity_id = str(source_entity_id).strip()
        if not normalized_source_entity_id:
            raise ValueError("Evidence source entity ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "graph.source-evidence.deactivate",
            )
            if existing_result is not None:
                if (
                    existing_result.get("evidence_type") != normalized_type
                    or existing_result.get("source_entity_id") != normalized_source_entity_id
                ):
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return _list_relationship_evidence_for_source(
                    conn, normalized_type, normalized_source_entity_id,
                )
            rows = conn.execute(
                """
                SELECT * FROM relationship_evidence
                WHERE evidence_type = ? AND source_entity_id = ?
                ORDER BY evidence_id
                """,
                (normalized_type, normalized_source_entity_id),
            ).fetchall()
            if not rows:
                raise KeyError(
                    f"No {normalized_type} evidence exists for source {normalized_source_entity_id}"
                )
            _begin_journal_operation(
                conn,
                "graph.source-evidence.deactivate",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "global-graph-service",
                affected_entities=[
                    {
                        "entity_type": "relationship_evidence",
                        "entity_id": row["evidence_id"],
                    }
                    for row in rows
                ],
                details={
                    "evidence_type": normalized_type,
                    "source_entity_id": normalized_source_entity_id,
                },
            )
            deactivated_at = utc_now()
            cursor = conn.execute(
                """
                UPDATE relationship_evidence
                SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
                WHERE evidence_type = ? AND source_entity_id = ? AND active = 1
                """,
                (
                    operation_id,
                    deactivated_at,
                    normalized_type,
                    normalized_source_entity_id,
                ),
            )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "evidence_type": normalized_type,
                "source_entity_id": normalized_source_entity_id,
                "deactivated_count": int(cursor.rowcount),
                "connection_count": validation["actual_connection_count"],
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return _list_relationship_evidence_for_source(
                conn, normalized_type, normalized_source_entity_id,
            )

    def get_person_neighbors(self, person_id: str) -> list[GraphConnection]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT * FROM graph_connections
                WHERE source_person_id = ? OR target_person_id = ?
                ORDER BY last_evidence_at DESC, source_person_id, target_person_id,
                         relationship_type, directionality
                """,
                (canonical_person_id, canonical_person_id),
            ).fetchall()
        return [_graph_connection_from_row(row) for row in rows]

    def get_connection_evidence(
        self,
        source_person_id: str,
        target_person_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[RelationshipEvidence]:
        with self._connect() as conn:
            canonical_source = _resolve_canonical_person_id(conn, source_person_id)
            canonical_target = _resolve_canonical_person_id(conn, target_person_id)
            if canonical_source == canonical_target:
                return []
            rows = conn.execute(
                f"SELECT * FROM relationship_evidence "
                f"{' ' if include_inactive else 'WHERE active = 1 '}"
                "ORDER BY created_at, evidence_id"
            ).fetchall()
            evidence: list[RelationshipEvidence] = []
            for row in rows:
                resolved_source = _resolve_canonical_person_id(
                    conn, row["source_person_id"],
                )
                resolved_target = _resolve_canonical_person_id(
                    conn, row["target_person_id"],
                )
                if row["directionality"] == "UNDIRECTED":
                    matches = tuple(sorted((resolved_source, resolved_target))) == tuple(
                        sorted((canonical_source, canonical_target))
                    )
                else:
                    matches = (
                        resolved_source == canonical_source
                        and resolved_target == canonical_target
                    )
                if matches:
                    evidence.append(_relationship_evidence_from_row(row))
            return evidence

    def get_global_graph_projection(self) -> GlobalGraphProjection:
        with self._connect() as conn:
            person_rows = conn.execute(
                "SELECT person_id, name, lifecycle_status FROM persons ORDER BY person_id"
            ).fetchall()
            nodes = tuple(
                GraphNode(
                    person_id=row["person_id"],
                    canonical_person_id=_resolve_canonical_person_id(conn, row["person_id"]),
                    name=row["name"],
                    lifecycle_status=row["lifecycle_status"],
                )
                for row in person_rows
            )
            connection_rows = conn.execute(
                """
                SELECT * FROM graph_connections
                ORDER BY source_person_id, target_person_id, relationship_type, directionality
                """
            ).fetchall()
            connections = tuple(_graph_connection_from_row(row) for row in connection_rows)
            return GlobalGraphProjection(nodes=nodes, connections=connections)

    def get_graph_revision(self) -> str:
        with self._connect() as conn:
            return _graph_revision_token(conn)

    def get_person_graph_read(
        self, person_id: str, filters: GraphReadFilter | None = None,
    ) -> PersonGraphReadModel:
        normalized_person_id = str(person_id).strip()
        if not normalized_person_id:
            raise ValueError("Person ID is required")
        normalized_filters = _normalize_graph_filters(filters)
        with self._connect() as conn:
            requested = conn.execute(
                "SELECT lifecycle_status FROM persons WHERE person_id = ?",
                (normalized_person_id,),
            ).fetchone()
            if requested is None:
                raise KeyError(f"Unknown person: {normalized_person_id}")
            root_person_id = _resolve_canonical_person_id(conn, normalized_person_id)
            nodes_by_id, edges = _graph_read_components(
                conn, normalized_filters, always_include_person_id=root_person_id,
            )
            root = nodes_by_id.get(root_person_id)
            if root is None:
                root = _graph_read_node(conn, root_person_id)
            person_edges = tuple(
                GraphReadEdge(
                    **{
                        **item.__dict__,
                        "connected_person_id": (
                            item.target_person_id
                            if item.source_person_id == root_person_id
                            else item.source_person_id
                        ),
                    }
                )
                for item in edges
                if root_person_id in {item.source_person_id, item.target_person_id}
            )
            included_ids = {root_person_id}
            included_ids.update(
                item.connected_person_id for item in person_edges if item.connected_person_id
            )
            nodes = tuple(
                root if item_id == root_person_id else nodes_by_id[item_id]
                for item_id in sorted(included_ids, key=lambda value: (
                    value != root_person_id,
                    (root if value == root_person_id else nodes_by_id[value]).display_name.casefold(),
                    value,
                ))
            )
            return PersonGraphReadModel(
                graph_revision=_graph_revision_token(conn),
                generated_at=utc_now(),
                requested_person_id=normalized_person_id,
                root_person_id=root_person_id,
                root_requested_state=str(requested["lifecycle_status"]),
                filters=normalized_filters,
                nodes=nodes,
                edges=person_edges,
            )

    def get_world_graph_read(
        self, filters: GraphReadFilter | None = None,
    ) -> WorldGraphReadModel:
        normalized_filters = _normalize_graph_filters(filters)
        with self._connect() as conn:
            nodes_by_id, edges = _graph_read_components(conn, normalized_filters)
            return WorldGraphReadModel(
                graph_revision=_graph_revision_token(conn),
                generated_at=utc_now(),
                filters=normalized_filters,
                nodes=tuple(sorted(
                    nodes_by_id.values(),
                    key=lambda item: (item.display_name.casefold(), item.person_id),
                )),
                edges=edges,
            )

    def get_world_graph_v2_read(
        self, request: WorldGraphRequest | None = None,
    ) -> WorldGraphV2ReadModel:
        with self._connect() as conn:
            return _world_graph_v2_read(conn, request or WorldGraphRequest())

    def rebuild_graph_projection(
        self,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
        reason: str | None = None,
        context: dict | None = None,
    ) -> dict:
        """Explicit P11-B recovery command for the derived graph projection only."""
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Operation ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, normalized_operation_id, "graph.projection.rebuild",
            )
            if existing_result is not None:
                return existing_result

        # Import locally to keep the read-only P11-A module independent from store startup.
        from sentriface.integrity import ReadOnlyIntegrityChecker

        preflight = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        projection_findings = tuple(
            item for item in preflight.findings
            if item.invariant_id == "P11-GRAPH-001"
        )
        blocking_findings = tuple(
            item for item in preflight.findings
            if item.invariant_id != "P11-GRAPH-001"
            and item.severity.value in {"CRITICAL", "ERROR"}
        )
        preflight_status = (
            "BLOCKED"
            if blocking_findings or preflight.findings_truncated
            else "PROJECTION_DRIFT"
            if projection_findings
            else "PASS"
        )
        preflight_summary = {
            "status": preflight_status,
            "finding_count": len(preflight.findings),
            "projection_finding_count": len(projection_findings),
            "blocking_finding_count": len(blocking_findings),
            "blocking_invariant_ids": sorted({
                item.invariant_id for item in blocking_findings
            }),
            "findings_truncated": preflight.findings_truncated,
        }
        if preflight_status == "BLOCKED":
            self._record_graph_rebuild_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                context=context,
                details={
                    "reason": _optional_text(reason),
                    "preflight": preflight_summary,
                    "refused": True,
                    "transaction_rolled_back": True,
                },
            )
            raise GraphProjectionRebuildRefused(
                normalized_operation_id,
                preflight,
                "Graph projection rebuild refused because authoritative integrity "
                "findings prevent deterministic interpretation",
            )

        failure_details: dict = {
            "reason": _optional_text(reason),
            "preflight": preflight_summary,
            "transaction_rolled_back": True,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing_result = _existing_committed_operation_result(
                    conn, normalized_operation_id, "graph.projection.rebuild",
                )
                if existing_result is not None:
                    return existing_result
                revision_before = _graph_revision_token(conn)
                failure_details["revision_before"] = revision_before
                expected, authority_errors, active_evidence_count = (
                    _expected_graph_connections(conn)
                )
                if authority_errors:
                    failure_details.update({
                        "revision_before": revision_before,
                        "authority_error_count": len(authority_errors),
                        "authority_errors": authority_errors[:20],
                    })
                    raise RuntimeError(
                        "Authoritative relationship evidence became invalid after "
                        "preflight: " + "; ".join(authority_errors[:20])
                    )
                actual_rows = conn.execute(
                    """
                    SELECT * FROM graph_connections
                    ORDER BY source_person_id, target_person_id,
                             relationship_type, directionality
                    """
                ).fetchall()
                expected_signatures = {
                    _graph_connection_signature(item) for item in expected
                }
                actual_signatures = {
                    _graph_connection_row_signature(item) for item in actual_rows
                }
                changed = expected_signatures != actual_signatures
                added_count = len(expected_signatures - actual_signatures)
                removed_count = len(actual_signatures - expected_signatures)
                failure_details.update({
                    "active_evidence_count": active_evidence_count,
                    "expected_edge_count": len(expected),
                    "stored_edge_count_before": len(actual_rows),
                    "added_count": added_count,
                    "removed_count": removed_count,
                })
                operation = _begin_journal_operation(
                    conn,
                    "graph.projection.rebuild",
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=_optional_text(source) or "global-graph-service",
                    context=context,
                    affected_entities=[{
                        "entity_type": "graph_projection",
                        "entity_id": "graph_connections",
                    }],
                    details={
                        "reason": _optional_text(reason),
                        "preflight": preflight_summary,
                        "revision_before": revision_before,
                    },
                )
                if changed:
                    _write_graph_projection(conn, expected)
                validation = _validate_graph_projection(conn)
                if not validation["valid"]:
                    raise RuntimeError(
                        "Graph projection validation failed: "
                        + "; ".join(validation["errors"][:20])
                    )
                if changed:
                    _advance_graph_revision(conn)
                revision_after = _graph_revision_token(conn)
                result = {
                    "operation_id": normalized_operation_id,
                    "started_at": operation["created_at"],
                    "changed": changed,
                    "revision_before": revision_before,
                    "revision_after": revision_after,
                    "active_evidence_count": active_evidence_count,
                    "expected_edge_count": len(expected),
                    "stored_edge_count_before": len(actual_rows),
                    "stored_edge_count_after": validation["actual_connection_count"],
                    "added_count": added_count,
                    "removed_count": removed_count,
                    "preflight_status": preflight_status,
                    "postcheck_status": "PASS",
                }
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
        except Exception as exc:
            failure_details.update({
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            self._record_graph_rebuild_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                context=context,
                details=failure_details,
            )
            raise

        postcheck = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        if postcheck.status != "PASS":
            failed_result = {**result, "postcheck_status": postcheck.status}
            raise GraphProjectionPostcheckError(failed_result, postcheck)
        return result

    def _record_graph_rebuild_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict | None,
        source: str | None,
        context: dict | None,
        details: dict,
    ) -> dict:
        """Record failure only after a rebuild transaction has rolled back."""
        with self._connect() as conn:
            existing = _get_journal_operation(conn, operation_id)
            if existing is not None:
                if existing["operation_type"] != "graph.projection.rebuild":
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                if existing["status"] == "FAILED":
                    return existing
                if existing["status"] != "STARTED":
                    raise ValueError("Only a started graph rebuild can fail")
            else:
                _begin_journal_operation(
                    conn,
                    "graph.projection.rebuild",
                    operation_id=operation_id,
                    actor=actor,
                    source=_optional_text(source) or "global-graph-service",
                    context=context,
                    affected_entities=[{
                        "entity_type": "graph_projection",
                        "entity_id": "graph_connections",
                    }],
                    details={"transaction_rolled_back": True},
                )
            return _transition_journal_operation(
                conn, operation_id, "FAILED", details,
            )

    def validate_graph_projection(self) -> dict:
        with self._connect() as conn:
            return _validate_graph_projection(conn)

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
            if row is None:
                return None
            result = dict(row)
            result["raw_person_id"] = _raw_embedding_owner_person_id(conn, row)
            result["canonical_person_id"] = _effective_embedding_owner_person_id(conn, row)
            effective_person = conn.execute(
                "SELECT name, deleted_at FROM persons WHERE person_id = ?",
                (result["canonical_person_id"],),
            ).fetchone()
            if effective_person is not None:
                result["person_name"] = effective_person["name"]
                result["person_deleted_at"] = effective_person["deleted_at"]
            return result

    def get_person_lifecycle(self, person_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT person_id, lifecycle_status, canonical_person_id,
                       identity_status, biometric_status, deleted_at, lifecycle_changed_at
                FROM persons WHERE person_id = ?
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["resolved_canonical_person_id"] = _resolve_canonical_person_id(conn, person_id)
            return result

    def resolve_canonical_person_id(self, person_id: str) -> str:
        with self._connect() as conn:
            return _resolve_canonical_person_id(conn, person_id)

    def get_merge_operation(self, merge_operation_id: str) -> MergeOperation | None:
        with self._connect() as conn:
            return _get_merge_operation(conn, merge_operation_id)

    def preview_identity_merge(
        self, source_person_id: str, target_person_id: str,
    ) -> dict:
        with self._connect() as conn:
            return _preview_identity_merge(conn, source_person_id, target_person_id)

    def execute_identity_merge(
        self,
        source_person_id: str,
        target_person_id: str,
        operation_id: str,
        *,
        conflict_resolutions: list[dict] | dict[str, dict | str] | None = None,
        actor: dict | None = None,
        source: str | None = None,
        reason: str | None = None,
        context: dict | None = None,
        publish_index: Callable[[list[EmbeddingRecord]], None] | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> dict:
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Merge operation ID is required")
        normalized_source_id = str(source_person_id).strip()
        normalized_requested_target_id = str(target_person_id).strip()
        with self._connect() as conn:
            existing = _get_journal_operation(conn, normalized_operation_id)
            if existing is not None:
                if existing["operation_type"] != "identity.merge":
                    raise KeyError(f"Operation ID already exists: {normalized_operation_id}")
                prior = existing.get("details", {})
                if (
                    prior.get("source_person_id") != normalized_source_id
                    or prior.get("requested_target_person_id") != normalized_requested_target_id
                ):
                    raise ValueError("Merge operation ID belongs to a different request")
                if existing["status"] == "COMMITTED":
                    history = existing.get("status_history") or []
                    return dict(history[-1]["details"]) if history else {}
                if existing["status"] in {"FAILED", "ROLLED_BACK"}:
                    raise ValueError(
                        "A failed merge operation ID cannot be reused; retry with a new operation ID"
                    )
        preview = self.preview_identity_merge(source_person_id, target_person_id)
        requested = {
            "source_person_id": preview["source_person_id"],
            "requested_target_person_id": preview["requested_target_person_id"],
            "target_person_id": preview["target_person_id"],
        }
        with self._connect() as conn:
            existing = _get_journal_operation(conn, normalized_operation_id)
            if existing is not None:
                prior = existing.get("details", {})
                for key, value in requested.items():
                    if prior.get(key) != value:
                        raise ValueError("Merge operation ID belongs to a different request")
            else:
                _begin_journal_operation(
                    conn,
                    "identity.merge",
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=_optional_text(source) or "identity-merge-service",
                    context=context,
                    affected_entities=[
                        {"entity_type": "person", "entity_id": preview["source_person_id"]},
                        {"entity_type": "person", "entity_id": preview["target_person_id"]},
                    ],
                    details=requested,
                )
        try:
            with self._connect() as conn:
                current = _get_journal_operation(conn, normalized_operation_id)
                if current is None or current["status"] != "STARTED":
                    raise RuntimeError("Merge journal is not in STARTED state")
                preview = _preview_identity_merge(
                    conn, source_person_id, target_person_id,
                    exclude_operation_id=normalized_operation_id,
                )
                conflicts = _resolve_merge_conflicts(
                    preview["conflicts"], conflict_resolutions,
                )
                affected_items = _merge_inventory_with_profile_changes(
                    preview["affected_items"], conflicts,
                    preview["source_person_id"], preview["target_person_id"],
                )
                _insert_merge_manifest_in_transaction(
                    conn,
                    merge_operation_id=normalized_operation_id,
                    source_person_id=preview["source_person_id"],
                    target_person_id=preview["target_person_id"],
                    operation_journal_id=normalized_operation_id,
                    actor=actor,
                    reason=reason,
                    context={
                        **(context or {}),
                        "requested_target_person_id": preview["requested_target_person_id"],
                        "source_component_person_ids": preview["source_component_person_ids"],
                    },
                    affected_items=affected_items,
                    conflicts=conflicts,
                )
                _apply_merge_profile_resolutions(
                    conn,
                    preview["source_person_id"],
                    preview["target_person_id"],
                    conflicts,
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=_optional_text(source) or "identity-merge-service",
                )
                _set_canonical_person_id_in_transaction(
                    conn, preview["source_person_id"], preview["target_person_id"],
                )
                if failure_injector is not None:
                    failure_injector("after_canonical_update")
                _synchronize_survivor_biometric_state(conn, preview["target_person_id"])
                _replace_graph_projection(conn)
                if failure_injector is not None:
                    failure_injector("after_graph_rebuild")
                validation = _validate_merge_state(
                    conn, preview["source_person_id"], preview["target_person_id"],
                )
                if not validation["valid"]:
                    raise RuntimeError(
                        "Merge validation failed: " + "; ".join(validation["errors"])
                    )
                embeddings = _list_embeddings_in_transaction(conn)
                if publish_index is not None:
                    publish_index(embeddings)
                if failure_injector is not None:
                    failure_injector("after_index_publication")
                result = {
                    "merge_operation_id": normalized_operation_id,
                    "source_person_id": preview["source_person_id"],
                    "requested_target_person_id": preview["requested_target_person_id"],
                    "target_person_id": preview["target_person_id"],
                    "canonical_person_id": preview["target_person_id"],
                    "merged": True,
                    "affected_item_count": len(affected_items),
                    "conflict_count": len(conflicts),
                    "graph_validation": validation["graph"],
                    "undo_supported": False,
                }
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
                return result
        except Exception as exc:
            self.record_merge_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-merge-service",
                context=context,
                affected_entities=[
                    {"entity_type": "person", "entity_id": preview["source_person_id"]},
                    {"entity_type": "person", "entity_id": preview["target_person_id"]},
                ],
                details={
                    **requested,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

    def list_historical_persons(self) -> list[PersonSummary]:
        return self.list_persons(archived=True)

    def archive_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "archive-person")
            if existing:
                return existing
            row = conn.execute(
                "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown person: {person_id}")
            if row["lifecycle_status"] not in {"ACTIVE", "ARCHIVED"}:
                raise KeyError(f"Only active or archived people can be archived: {person_id}")
            _begin_journal_operation(
                conn,
                "identity.archive",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"previous_status": row["lifecycle_status"]},
            )
            archived_at = row["deleted_at"] or utc_now()
            cursor = conn.execute(
                """
                UPDATE persons
                SET lifecycle_status = 'ARCHIVED', deleted_at = ?, lifecycle_changed_at = ?
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE'
                """,
                (archived_at, archived_at, person_id),
            )
            result = {
                "person_id": person_id,
                "archived": True,
                "archived_at": archived_at,
                "lifecycle_status": "ARCHIVED",
                "changed": bool(cursor.rowcount),
            }
            _record_person_operation(conn, operation_id, "archive-person", result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def restore_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "restore-person")
            if existing:
                return existing
            row = conn.execute(
                "SELECT lifecycle_status, deleted_at, metadata FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown person: {person_id}")
            if row["lifecycle_status"] != "ARCHIVED":
                raise KeyError(f"Only archived people can be restored: {person_id}")
            _begin_journal_operation(
                conn,
                "identity.restore",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"previous_status": "ARCHIVED"},
            )
            cursor = _restore_archived_person_in_transaction(conn, person_id)
            result = {
                "person_id": person_id,
                "restored": True,
                "lifecycle_status": "ACTIVE",
                "changed": bool(cursor.rowcount),
            }
            _record_person_operation(conn, operation_id, "restore-person", result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def prepare_restore_archived_canonical_survivor(
        self, survivor_person_id: str,
    ) -> ArchivedCanonicalSurvivorRepairPrecondition:
        """Diagnose and bind the one authorized P11-C R01 mutation."""
        normalized_id = str(survivor_person_id).strip()
        if not normalized_id:
            raise ValueError("Survivor person ID is required")
        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        with self._connect() as conn:
            conn.execute("BEGIN")
            return _r01_precondition_from_report(conn, report, normalized_id)

    def execute_restore_archived_canonical_survivor(
        self,
        precondition: ArchivedCanonicalSurvivorRepairPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
    ) -> dict:
        """Execute P11C-R01 only; the caller performs the full P11-A post-check."""
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Operation ID is required")
        if not isinstance(actor, dict) or not actor:
            raise ValueError("Authenticated actor is required")
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Repair reason is required")
        if len(normalized_reason) > 500:
            raise ValueError("Repair reason must not exceed 500 characters")
        _validate_r01_request_shape(precondition)

        with self._connect() as conn:
            existing = _r01_existing_result(
                conn, normalized_operation_id, precondition,
            )
            if existing is not None:
                return existing

        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        failure_details = {
            "repair_id": precondition.repair_id,
            "repair_spec_version": precondition.repair_spec_version,
            "invariant_ids": list(precondition.invariant_ids),
            "finding_fingerprint_version": precondition.finding_fingerprint_version,
            "finding_fingerprint": precondition.finding_fingerprint,
            "survivor_person_id": precondition.survivor_person_id,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = _r01_existing_result(
                    conn, normalized_operation_id, precondition,
                )
                if existing is not None:
                    return existing
                current = _r01_precondition_from_report(
                    conn, report, precondition.survivor_person_id,
                )
                if current != precondition:
                    raise StructuredRepairRefused(
                        "R01 refused because the diagnosed authoritative state is stale",
                        report=report,
                    )
                connections_before = _r01_table_fingerprint(conn, "graph_connections")
                canonical_before = _r01_canonical_fingerprint(conn)
                merge_before = precondition.merge_state_fingerprint
                revision_before = _graph_revision_token(conn)
                _begin_journal_operation(
                    conn,
                    "integrity.repair.canonical-survivor.restore",
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=source or "structured-repair-service",
                    affected_entities=[
                        {"entity_type": "person", "entity_id": item}
                        for item in precondition.affected_entity_ids[:50]
                    ],
                    details={
                        **failure_details,
                        "reason": normalized_reason,
                        "affected_entity_count": len(precondition.affected_entity_ids),
                        "affected_entity_fingerprint": _r01_hash(
                            precondition.affected_entity_ids
                        ),
                        "before_state_fingerprint": _r01_hash({
                            "lifecycle": precondition.expected_lifecycle_status,
                            "deleted_at": precondition.expected_deleted_at,
                            "lifecycle_changed_at": precondition.expected_lifecycle_changed_at,
                            "canonical_person_id": precondition.expected_canonical_person_id,
                            "merge_state_fingerprint": merge_before,
                        }),
                    },
                )
                _restore_archived_person_in_transaction(
                    conn, precondition.survivor_person_id,
                )
                post = _validate_r01_postconditions(
                    conn,
                    precondition,
                    canonical_before=canonical_before,
                    connections_before=connections_before,
                    merge_before=merge_before,
                    revision_before=revision_before,
                )
                result = {
                    "repair_id": precondition.repair_id,
                    "repair_spec_version": precondition.repair_spec_version,
                    "invariant_ids": list(precondition.invariant_ids),
                    "finding_fingerprint_version": precondition.finding_fingerprint_version,
                    "finding_fingerprint": precondition.finding_fingerprint,
                    "survivor_person_id": precondition.survivor_person_id,
                    "merge_path_count": len(precondition.merge_paths),
                    "merge_path_fingerprint": _r01_hash(precondition.merge_paths),
                    "lifecycle_before": "ARCHIVED",
                    "lifecycle_after": "ACTIVE",
                    "graph_revision_before": revision_before,
                    "graph_revision_after": post["graph_revision_after"],
                    "changed": True,
                    "immediate_postcondition_status": "PASS",
                    "postcheck_status": "PENDING",
                }
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
                return result
        except StructuredRepairRefused:
            raise
        except Exception as exc:
            self._record_r01_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                details={
                    **failure_details,
                    "transaction_rolled_back": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
            )
            raise

    def _record_r01_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict,
        source: str | None,
        details: dict,
    ) -> None:
        with self._connect() as conn:
            if _get_journal_operation(conn, operation_id) is not None:
                return
            _begin_journal_operation(
                conn,
                "integrity.repair.canonical-survivor.restore",
                operation_id=operation_id,
                actor=actor,
                source=source or "structured-repair-service",
                affected_entities=[{
                    "entity_type": "person",
                    "entity_id": details["survivor_person_id"],
                }],
                details=details,
            )
            _transition_journal_operation(conn, operation_id, "FAILED", details)

    def prepare_note_reference_reconciliation(
        self, note_id: str, referenced_person_id: str,
    ) -> NoteReferenceReconciliationPrecondition:
        """Diagnose and bind one authorized P11-C R02 note/person scope."""
        normalized_note_id = str(note_id).strip()
        normalized_person_id = str(referenced_person_id).strip()
        if not normalized_note_id:
            raise ValueError("Note ID is required")
        if not normalized_person_id:
            raise ValueError("Referenced person ID is required")
        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        with self._connect() as conn:
            conn.execute("BEGIN")
            return _r02_precondition_from_report(
                conn, report, normalized_note_id, normalized_person_id,
            )

    def execute_note_reference_reconciliation(
        self,
        precondition: NoteReferenceReconciliationPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
    ) -> dict:
        """Execute only P11C-R02; the caller performs the full P11-A post-check."""
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Operation ID is required")
        if not isinstance(actor, dict) or not actor:
            raise ValueError("Authenticated actor is required")
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Repair reason is required")
        if len(normalized_reason) > 500:
            raise ValueError("Repair reason must not exceed 500 characters")
        _validate_r02_request_shape(precondition)

        with self._connect() as conn:
            existing = _r02_existing_result(
                conn, normalized_operation_id, precondition,
            )
            if existing is not None:
                return existing

        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        failure_details = {
            "repair_id": precondition.repair_id,
            "repair_spec_version": precondition.repair_spec_version,
            "invariant_ids": list(precondition.invariant_ids),
            "finding_fingerprint_version": precondition.finding_fingerprint_version,
            "finding_fingerprint": precondition.finding_fingerprint,
            "plan_type": precondition.plan.value,
            "note_id": precondition.note_id,
            "referenced_person_id": precondition.referenced_person_id,
            "authoritative_revision_id": precondition.latest_revision_id,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = _r02_existing_result(
                    conn, normalized_operation_id, precondition,
                )
                if existing is not None:
                    return existing
                current = _r02_precondition_from_report(
                    conn,
                    report,
                    precondition.note_id,
                    precondition.referenced_person_id,
                )
                if current != precondition:
                    raise StructuredRepairRefused(
                        "R02 refused because the diagnosed authoritative state is stale",
                        report=report,
                    )

                immutable_before = _r02_immutable_fingerprint(conn)
                unrelated_before = _r02_unrelated_fingerprint(
                    conn, precondition, normalized_operation_id,
                )
                historical_before = _r02_retired_history_fingerprint(conn, precondition)
                revision_before = _graph_revision_token(conn)
                connection_count_before = int(conn.execute(
                    "SELECT COUNT(*) FROM graph_connections"
                ).fetchone()[0])
                planned_occurrence_id, planned_evidence_id = _r02_planned_append_ids(
                    precondition, normalized_operation_id,
                )
                _begin_journal_operation(
                    conn,
                    _R02_OPERATION_TYPE,
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=source or "structured-repair-service",
                    affected_entities=_r02_affected_entities(
                        precondition,
                        planned_occurrence_id=planned_occurrence_id,
                        planned_evidence_id=planned_evidence_id,
                    ),
                    details={
                        **failure_details,
                        "reason": normalized_reason,
                        "affected_entity_count": len(precondition.affected_entity_ids),
                        "affected_entity_fingerprint": _r01_hash(
                            precondition.affected_entity_ids
                        ),
                        "before_state_fingerprint": _r01_hash({
                            "revision_history": precondition.revision_history_fingerprint,
                            "occurrence_group": precondition.occurrence_group_fingerprint,
                            "evidence_history": precondition.evidence_history_fingerprint,
                            "canonical_state": precondition.canonical_state_fingerprint,
                            "graph_projection": precondition.graph_projection_fingerprint,
                            "relevant_operations": precondition.relevant_operation_fingerprint,
                        }),
                    },
                )
                _r02_failure_checkpoint("after_journal_started")
                mutation = _apply_r02_plan(
                    conn,
                    precondition,
                    normalized_operation_id,
                    source=_optional_text(source),
                    planned_occurrence_id=planned_occurrence_id,
                )
                if mutation["active_evidence_changed"]:
                    _r02_maintain_affected_projection(conn, precondition)
                    _r02_failure_checkpoint("after_graph_projection")
                    _advance_graph_revision(conn)
                    _r02_failure_checkpoint("after_graph_revision_advance")
                post = _validate_r02_postconditions(
                    conn,
                    precondition,
                    operation_id=normalized_operation_id,
                    mutation=mutation,
                    immutable_before=immutable_before,
                    unrelated_before=unrelated_before,
                    historical_before=historical_before,
                    revision_before=revision_before,
                )
                _r02_failure_checkpoint("after_immediate_validation")
                result = {
                    **failure_details,
                    "occurrences_appended": mutation["occurrences_appended"],
                    "occurrences_retired": mutation["occurrences_retired"],
                    "evidence_appended": mutation["evidence_appended"],
                    "evidence_retired": mutation["evidence_retired"],
                    "graph_revision_before": revision_before,
                    "graph_revision_after": post["graph_revision_after"],
                    "connection_count_before": connection_count_before,
                    "connection_count_after": post["connection_count_after"],
                    "changed": True,
                    "immediate_validation_status": "PASS",
                    "postcheck_status": "PENDING",
                }
                _r02_failure_checkpoint("before_commit")
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
                return result
        except StructuredRepairRefused:
            raise
        except Exception as exc:
            self._record_r02_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                details={
                    **failure_details,
                    "transaction_rolled_back": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
            )
            raise

    def _record_r02_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict,
        source: str | None,
        details: dict,
    ) -> None:
        with self._connect() as conn:
            if _get_journal_operation(conn, operation_id) is not None:
                return
            _begin_journal_operation(
                conn,
                _R02_OPERATION_TYPE,
                operation_id=operation_id,
                actor=actor,
                source=source or "structured-repair-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": details["note_id"]},
                    {
                        "entity_type": "person",
                        "entity_id": details["referenced_person_id"],
                    },
                ],
                details=details,
            )
            _transition_journal_operation(conn, operation_id, "FAILED", details)

    def prepare_operation_revert(
        self, operation_id: str,
    ) -> OperationRevertPrecondition:
        """Prepare the one P11-D whitelist entry without mutating history."""
        normalized_id = str(operation_id).strip()
        if not normalized_id:
            raise ValueError("Operation ID is required")
        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        with self._connect() as conn:
            conn.execute("BEGIN")
            return _p11d_precondition_from_report(conn, report, normalized_id)

    def execute_operation_revert(
        self,
        precondition: OperationRevertPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> dict:
        """Execute a guarded safe-merge revert; no dynamic inversion is accepted."""
        normalized_revert_id = str(operation_id).strip()
        if not normalized_revert_id:
            raise ValueError("Revert operation ID is required")
        if not isinstance(actor, dict) or not actor:
            raise ValueError("Authenticated actor is required")
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Revert reason is required")
        if len(normalized_reason) > 500:
            raise ValueError("Revert reason must not exceed 500 characters")
        _validate_p11d_request_shape(precondition)

        with self._connect() as conn:
            existing = _p11d_existing_result(
                conn, normalized_revert_id, precondition,
            )
            if existing is not None:
                return existing

        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        failure_details = {
            "revert_spec_version": precondition.revert_spec_version,
            "fingerprint_version": precondition.fingerprint_version,
            "fingerprint": precondition.fingerprint,
            "reverted_operation_id": precondition.operation_id,
            "reverted_operation_type": precondition.operation_type,
            "source_person_id": precondition.source_person_id,
            "target_person_id": precondition.target_person_id,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = _p11d_existing_result(
                    conn, normalized_revert_id, precondition,
                )
                if existing is not None:
                    return existing
                current = _p11d_precondition_from_report(
                    conn, report, precondition.operation_id,
                )
                if current != precondition:
                    raise OperationRevertRefused(
                        "Revert refused because the prepared authoritative state is stale",
                        report=report,
                    )

                immutable_before = _p11d_immutable_fingerprint(
                    conn, precondition.operation_id,
                )
                target_before = _p11d_person_fingerprint(
                    conn, precondition.target_person_id,
                )
                source_stable_before = _p11d_person_stable_fingerprint(
                    conn, precondition.source_person_id,
                )
                revision_before = _graph_revision_token(conn)
                _begin_journal_operation(
                    conn,
                    _P11D_REVERT_OPERATION_TYPE,
                    operation_id=normalized_revert_id,
                    actor=actor,
                    source=source or "guarded-operation-revert-service",
                    affected_entities=[
                        {"entity_type": "operation", "entity_id": precondition.operation_id},
                        {"entity_type": "person", "entity_id": precondition.source_person_id},
                        {"entity_type": "person", "entity_id": precondition.target_person_id},
                    ],
                    details={
                        **failure_details,
                        "reason": normalized_reason,
                        "affected_entity_count": len(precondition.affected_entities),
                        "affected_entity_fingerprint": _r01_hash(
                            precondition.affected_entities
                        ),
                        "dependency_state_fingerprint": (
                            precondition.dependency_state_fingerprint
                        ),
                    },
                )
                _p11d_checkpoint(failure_injector, "after_journal_started")
                changed_at = utc_now()
                cursor = conn.execute(
                    """
                    UPDATE persons
                    SET lifecycle_status = 'ACTIVE', canonical_person_id = NULL,
                        deleted_at = NULL, lifecycle_changed_at = ?
                    WHERE person_id = ? AND lifecycle_status = 'MERGED'
                      AND canonical_person_id = ?
                      AND lifecycle_changed_at = ?
                    """,
                    (
                        changed_at,
                        precondition.source_person_id,
                        precondition.target_person_id,
                        precondition.expected_source_lifecycle_changed_at,
                    ),
                )
                if cursor.rowcount != 1:
                    raise OperationRevertRefused(
                        "Revert refused because the merge source changed"
                    )
                _p11d_checkpoint(failure_injector, "during_mutation")
                _replace_graph_projection(conn)
                _p11d_checkpoint(failure_injector, "during_graph_update")
                validation = _validate_p11d_postconditions(
                    conn,
                    precondition,
                    immutable_before=immutable_before,
                    target_before=target_before,
                    source_stable_before=source_stable_before,
                    revision_before=revision_before,
                )
                _p11d_checkpoint(failure_injector, "during_validation")
                _transition_journal_operation(
                    conn,
                    precondition.operation_id,
                    "REVERTED",
                    {
                        "reverted_by_operation_id": normalized_revert_id,
                        "revert_fingerprint": precondition.fingerprint,
                    },
                )
                result = {
                    **failure_details,
                    "revert_operation_id": normalized_revert_id,
                    "source_lifecycle_before": "MERGED",
                    "source_lifecycle_after": "ACTIVE",
                    "graph_revision_before": revision_before,
                    "graph_revision_after": validation["graph_revision_after"],
                    "changed": True,
                    "immediate_validation_status": "PASS",
                    "postcheck_status": "PENDING",
                }
                _transition_journal_operation(
                    conn, normalized_revert_id, "COMMITTED", result,
                )
                _p11d_checkpoint(failure_injector, "before_commit")
                return result
        except OperationRevertRefused:
            raise
        except Exception as exc:
            self._record_p11d_revert_attempt_failed(
                normalized_revert_id,
                actor=actor,
                source=source,
                details={
                    **failure_details,
                    "transaction_rolled_back": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
            )
            raise

    def _record_p11d_revert_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict,
        source: str | None,
        details: dict,
    ) -> None:
        with self._connect() as conn:
            if _get_journal_operation(conn, operation_id) is not None:
                return
            _begin_journal_operation(
                conn,
                _P11D_REVERT_OPERATION_TYPE,
                operation_id=operation_id,
                actor=actor,
                source=source or "guarded-operation-revert-service",
                affected_entities=[
                    {"entity_type": "operation", "entity_id": details["reverted_operation_id"]},
                    {"entity_type": "person", "entity_id": details["source_person_id"]},
                    {"entity_type": "person", "entity_id": details["target_person_id"]},
                ],
                details=details,
            )
            _transition_journal_operation(conn, operation_id, "FAILED", details)

    def soft_delete_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        return self._soft_delete_person(
            person_id, operation_id, "soft-delete-person", actor, source,
        )

    def permanently_delete_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        """Compatibility entry point for the former destructive UI action."""
        return self._soft_delete_person(person_id, operation_id, "purge-person", actor, source)

    def _soft_delete_person(
        self,
        person_id: str,
        operation_id: str,
        legacy_operation_type: str,
        actor: dict | None,
        source: str | None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, legacy_operation_type)
            if existing:
                return existing
            person = conn.execute(
                "SELECT name, lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if person is None:
                raise KeyError(f"Unknown person: {person_id}")
            if person["lifecycle_status"] == "MERGED":
                raise KeyError("Merged source identities cannot be deleted independently")
            _begin_journal_operation(
                conn,
                "identity.delete",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"previous_status": person["lifecycle_status"]},
            )
            deleted_at = person["deleted_at"] or utc_now()
            cursor = conn.execute(
                """
                UPDATE persons
                SET lifecycle_status = 'DELETED', deleted_at = ?, lifecycle_changed_at = ?
                WHERE person_id = ? AND lifecycle_status <> 'DELETED'
                """,
                (deleted_at, deleted_at, person_id),
            )
            counts = _person_historical_counts(conn, person_id)
            result = {
                "person_id": person_id,
                "person_name": person["name"],
                "deleted": True,
                "permanent": False,
                "tombstoned": True,
                "lifecycle_status": "DELETED",
                "deleted_at": deleted_at,
                "changed": bool(cursor.rowcount),
                **counts,
                "deleted_embeddings": 0,
                "deleted_sightings": 0,
                "deleted_profile_changes": 0,
                "deleted_queue_exclusions": 0,
                "deleted_associations": 0,
                "deleted_association_ids": [],
            }
            _record_person_operation(conn, operation_id, legacy_operation_type, result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def _set_canonical_person_id_for_merge(
        self,
        person_id: str,
        canonical_person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        """Compatibility harness; the connection-scoped helper is the P8 primitive."""
        with self._connect() as conn:
            _begin_journal_operation(
                conn,
                "identity.canonical-map",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[
                    {"entity_type": "person", "entity_id": person_id},
                    {"entity_type": "person", "entity_id": canonical_person_id},
                ],
                details={"requested_canonical_person_id": canonical_person_id},
            )
            result = _set_canonical_person_id_in_transaction(
                conn, person_id, canonical_person_id,
            )
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'graph_connections'"
            ).fetchone() is not None:
                _replace_graph_projection(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
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

    def physically_purge_person(self, person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "physical-purge-person")
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
            _record_person_operation(conn, operation_id, "physical-purge-person", result)
            return result

    def delete_embedding(
        self, embedding_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        """Soft-delete a face for 30 days while retaining its linked sightings."""
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "soft-delete-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.source_image, e.crop_path, e.deleted_at,
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
            raw_person_id = _raw_embedding_owner_person_id(conn, row)
            effective_person_id = _effective_embedding_owner_person_id(conn, row)
            effective_person = conn.execute(
                "SELECT metadata FROM persons WHERE person_id = ?",
                (effective_person_id,),
            ).fetchone()
            if effective_person is None:
                raise KeyError(f"Unknown effective person: {effective_person_id}")
            _begin_journal_operation(
                conn, "biometric.face.delete", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": effective_person_id},
                ],
            )
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
            metadata = json.loads(effective_person["metadata"])
            if metadata.get("representative_embedding_id") == embedding_id:
                metadata.pop("representative_embedding_id", None)
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(metadata, separators=(",", ":")), effective_person_id),
                )
            result = {
                "embedding_id": embedding_id,
                "person_id": effective_person_id,
                "raw_person_id": raw_person_id,
                "deleted": True,
                "permanent": False,
                "retained_sightings": detail_count,
                "deleted_at": deleted_at,
                "purge_after": purge_after,
                "source_image": row["source_image"],
                "crop_path": row["crop_path"],
            }
            _record_person_operation(conn, operation_id, "soft-delete-embedding", result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_deleted_embeddings(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.quality_score,
                       e.source_image, e.crop_path, e.created_at,
                       e.deleted_at, e.purge_after,
                       p.name, p.deleted_at AS person_deleted_at,
                       p.lifecycle_status AS person_lifecycle_status,
                       p.canonical_person_id AS canonical_person_id,
                       COUNT(d.detail_id) AS sighting_count
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                LEFT JOIN recognition_details d ON d.embedding_id = e.embedding_id
                WHERE e.deleted_at IS NOT NULL
                GROUP BY e.embedding_id
                ORDER BY e.deleted_at DESC
                """
            ).fetchall()
            result: list[dict] = []
            for row in rows:
                item = dict(row)
                raw_person_id = _raw_embedding_owner_person_id(conn, row)
                effective_person_id = _effective_embedding_owner_person_id(conn, row)
                effective_person = conn.execute(
                    "SELECT name, lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                    (effective_person_id,),
                ).fetchone()
                item["raw_person_id"] = raw_person_id
                item["person_id"] = effective_person_id
                item["canonical_person_id"] = effective_person_id
                if effective_person is not None:
                    item["name"] = effective_person["name"]
                    item["person_lifecycle_status"] = effective_person["lifecycle_status"]
                    item["person_deleted_at"] = effective_person["deleted_at"]
                result.append(item)
            return result

    def restore_deleted_embedding(
        self, embedding_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "restore-deleted-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.deleted_at, e.purge_after
                FROM embeddings e
                WHERE e.embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown deleted face: {embedding_id}")
            if row["deleted_at"] is None:
                raise KeyError("Face is not deleted")
            raw_person_id = _raw_embedding_owner_person_id(conn, row)
            effective_person_id = _effective_embedding_owner_person_id(conn, row)
            effective_person = conn.execute(
                "SELECT lifecycle_status, deleted_at, metadata FROM persons WHERE person_id = ?",
                (effective_person_id,),
            ).fetchone()
            if (
                effective_person is None
                or effective_person["lifecycle_status"] != "ACTIVE"
                or effective_person["deleted_at"] is not None
            ):
                raise KeyError("Only an active identity can receive a restored face")
            _begin_journal_operation(
                conn, "biometric.face.restore", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": effective_person_id},
                ],
            )
            conn.execute(
                """
                UPDATE embeddings
                SET deleted_at = NULL, purge_after = NULL
                WHERE embedding_id = ? AND deleted_at IS NOT NULL
                """,
                (embedding_id,),
            )
            metadata = json.loads(effective_person["metadata"])
            if not metadata.get("representative_embedding_id"):
                metadata["representative_embedding_id"] = embedding_id
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(metadata, separators=(",", ":")), effective_person_id),
                )
            result = {
                "embedding_id": embedding_id,
                "person_id": effective_person_id,
                "raw_person_id": raw_person_id,
                "restored": True,
                "previously_deleted_at": row["deleted_at"],
            }
            _record_person_operation(conn, operation_id, "restore-deleted-embedding", result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def permanently_delete_embedding(
        self, embedding_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
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
            _begin_journal_operation(
                conn, "biometric.face.purge", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": row["person_id"]},
                ],
            )
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
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
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
        actor: dict | None = None,
        source: str | None = None,
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
            _begin_journal_operation(
                conn, "biometric.face.purge-expired", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "retention-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id}
                    for embedding_id in unique_ids
                ],
            )
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
                _transition_journal_operation(conn, operation_id, "COMMITTED", result)
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
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def _legacy_move_embedding(self, embedding_id: str, person_id: str, operation_id: str) -> dict:
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

    def _legacy_merge_persons(
        self, source_person_id: str, target_person_id: str, operation_id: str,
    ) -> dict:
        """Retained only to read/test legacy merge history until normalized P8 merge."""
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

    def _legacy_undo_merge_persons(
        self, merge_operation_id: str, operation_id: str,
    ) -> dict:
        """Retained only to read/test legacy merge history until normalized P8 merge."""
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
        actor: dict | None = None,
        source: str | None = None,
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
            _begin_journal_operation(
                conn, "identity.preferences.update", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
            )
            metadata = json.loads(person["metadata"])
            changed_preferences = []
            if favorite is not None:
                metadata["favorite"] = bool(favorite)
                changed_preferences.append("favorite")
            if representative_embedding_id is not None:
                owned = conn.execute(
                    """
                    SELECT embedding_id, person_id FROM embeddings
                    WHERE embedding_id = ? AND deleted_at IS NULL
                    """,
                    (representative_embedding_id,),
                ).fetchone()
                if (
                    owned is None
                    or _effective_embedding_owner_person_id(conn, owned)
                    != _resolve_canonical_person_id(conn, person_id)
                ):
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
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
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
        """Internal legacy/import primitive; production review details use P6."""
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
            automatic_associations = _legacy_create_note_associations(
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
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT d.detail_id, d.embedding_id, d.person_id, d.image_id, d.image_path,
                       d.name, d.decision, d.seen_date, d.seen_time, d.place_seen,
                       d.individual_count, d.event_occasion, d.rank, d.country,
                       d.importance, d.added_by, d.notes, d.created_at
                FROM recognition_details d
                JOIN embeddings e ON e.embedding_id = d.embedding_id
                WHERE e.deleted_at IS NULL
                ORDER BY d.seen_date DESC, d.seen_time DESC, d.created_at DESC
                """
            ).fetchall()
            return [
                _recognition_detail_from_row(row) for row in rows
                if (
                    (embedding := conn.execute(
                        "SELECT embedding_id, person_id FROM embeddings WHERE embedding_id = ?",
                        (row["embedding_id"],),
                    ).fetchone()) is not None
                    and _effective_embedding_owner_person_id(conn, embedding)
                    == canonical_person_id
                )
            ]

    def list_raw_recognition_details_for_person(
        self, person_id: str,
    ) -> list[RecognitionDetail]:
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
        """Internal fixture/import primitive; production enrollment uses P6."""
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
                WHERE e.deleted_at IS NULL
                """
            ).fetchall()
            records: list[EmbeddingRecord] = []
            for row in rows:
                canonical_person_id = _effective_embedding_owner_person_id(conn, row)
                canonical = conn.execute(
                    "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                    (canonical_person_id,),
                ).fetchone()
                if (
                    canonical is not None
                    and canonical["lifecycle_status"] == "ACTIVE"
                    and canonical["deleted_at"] is None
                ):
                    records.append(_embedding_from_row(
                        row,
                        raw_person_id=_raw_embedding_owner_person_id(conn, row),
                        canonical_person_id=canonical_person_id,
                    ))
            return records

    def current_embedding_person_ids(self, embedding_ids: list[str]) -> dict[str, str]:
        normalized_ids = list(dict.fromkeys(
            str(embedding_id).strip() for embedding_id in embedding_ids
            if str(embedding_id).strip()
        ))
        if not normalized_ids:
            return {}
        placeholders = ", ".join("?" for _ in normalized_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT e.embedding_id, e.person_id
                FROM embeddings e
                WHERE e.embedding_id IN ({placeholders})
                  AND e.deleted_at IS NULL
                """,
                normalized_ids,
            ).fetchall()
            result: dict[str, str] = {}
            for row in rows:
                canonical_person_id = _effective_embedding_owner_person_id(conn, row)
                canonical = conn.execute(
                    "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                    (canonical_person_id,),
                ).fetchone()
                if (
                    canonical is not None
                    and canonical["lifecycle_status"] == "ACTIVE"
                    and canonical["deleted_at"] is None
                ):
                    result[str(row["embedding_id"])] = canonical_person_id
            return result

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

    def _legacy_confirm_pending_addition(
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
                automatic_associations = _legacy_create_note_associations(
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
                automatic_associations.extend(_legacy_create_note_associations(
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
            "SELECT * FROM persons WHERE person_id = ?",
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

    def _legacy_confirm_init_faces_atomic(
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
                automatic_associations = _legacy_create_note_associations(
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
                exclusions.setdefault(row["init_face_id"], set()).add(
                    _resolve_canonical_person_id(conn, row["person_id"]),
                )
            return exclusions

    @contextmanager
    def _connect(self):
        conn = connect_database(self.db_path, self.database_key, timeout=30, row_factory=True)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=FULL")
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
            _legacy_create_note_associations(conn, row["person_id"], row["notes"] or "", "SentriFace migration", [])
    if "notes" in detail_columns and "person_associations" in tables:
        for row in conn.execute(
            "SELECT person_id, notes FROM recognition_details WHERE notes LIKE '%@%'"
        ).fetchall():
            _legacy_create_note_associations(conn, row["person_id"], row["notes"] or "", "SentriFace migration", [])
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


def _migrate_17_to_18(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE persons ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'ACTIVE' "
        "CHECK(lifecycle_status IN ('ACTIVE', 'ARCHIVED', 'DELETED', 'MERGED'))"
    )
    conn.execute(
        "ALTER TABLE persons ADD COLUMN canonical_person_id TEXT REFERENCES persons(person_id) "
        "ON DELETE RESTRICT CHECK(canonical_person_id IS NULL OR canonical_person_id <> person_id)"
    )
    conn.execute(
        "ALTER TABLE persons ADD COLUMN identity_status TEXT NOT NULL DEFAULT 'IDENTIFIED' "
        "CHECK(identity_status IN ('IDENTIFIED', 'UNIDENTIFIED'))"
    )
    conn.execute(
        "ALTER TABLE persons ADD COLUMN biometric_status TEXT NOT NULL DEFAULT 'NO_FACE' "
        "CHECK(biometric_status IN ('NO_FACE', 'ENROLLED'))"
    )
    conn.execute("ALTER TABLE persons ADD COLUMN lifecycle_changed_at TEXT")

    rows = conn.execute(
        "SELECT person_id, metadata, deleted_at, enrollment_status "
        "FROM persons ORDER BY person_id"
    ).fetchall()
    has_embeddings_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'embeddings'"
    ).fetchone() is not None
    person_ids = {str(row["person_id"]) for row in rows}
    legacy_canonical_mappings: dict[str, str] = {}
    for row in rows:
        if not row["deleted_at"]:
            continue
        person_id = str(row["person_id"])
        metadata = json.loads(row["metadata"] or "{}")
        legacy_target = str(metadata.get("merged_into") or "").strip()
        if not legacy_target:
            continue
        if legacy_target == person_id:
            raise SchemaMigrationError(
                f"Invalid legacy canonical mapping for {person_id}: self-reference"
            )
        if legacy_target not in person_ids:
            raise SchemaMigrationError(
                f"Invalid legacy canonical mapping for {person_id}: "
                f"target {legacy_target} does not exist"
            )
        legacy_canonical_mappings[person_id] = legacy_target
    for source_person_id in sorted(legacy_canonical_mappings):
        visited: set[str] = set()
        current_person_id = source_person_id
        while current_person_id in legacy_canonical_mappings:
            if current_person_id in visited:
                raise SchemaMigrationError(
                    f"Invalid legacy canonical mapping for {source_person_id}: cycle detected"
                )
            visited.add(current_person_id)
            current_person_id = legacy_canonical_mappings[current_person_id]
    for row in rows:
        person_id = str(row["person_id"])
        legacy_target = legacy_canonical_mappings.get(person_id)
        if legacy_target is not None:
            lifecycle_status = "MERGED"
            canonical_person_id = legacy_target
        elif row["deleted_at"]:
            lifecycle_status = "ARCHIVED"
            canonical_person_id = None
        else:
            lifecycle_status = "ACTIVE"
            canonical_person_id = None
        if has_embeddings_table:
            has_embedding = conn.execute(
                "SELECT 1 FROM embeddings WHERE person_id = ? LIMIT 1",
                (person_id,),
            ).fetchone() is not None
        else:
            has_embedding = row["enrollment_status"] == "enrolled"
        biometric_status = "ENROLLED" if has_embedding else "NO_FACE"
        conn.execute(
            """
            UPDATE persons
            SET lifecycle_status = ?, canonical_person_id = ?, identity_status = 'IDENTIFIED',
                biometric_status = ?, lifecycle_changed_at = COALESCE(deleted_at, created_at)
            WHERE person_id = ?
            """,
            (lifecycle_status, canonical_person_id, biometric_status, person_id),
        )

    _execute_migration_script(
        conn,
        """
        CREATE INDEX idx_persons_lifecycle
        ON persons(lifecycle_status, name COLLATE NOCASE);

        CREATE INDEX idx_persons_canonical
        ON persons(canonical_person_id);

        CREATE TRIGGER persons_identity_biometric_insert
        BEFORE INSERT ON persons
        WHEN NEW.identity_status = 'UNIDENTIFIED'
         AND NEW.biometric_status = 'NO_FACE'
         AND trim(NEW.name) = ''
         AND trim(NEW.notes) = ''
         AND trim(NEW.metadata) IN ('', '{}')
        BEGIN
            SELECT RAISE(ABORT, 'an unidentified person without a face or context is invalid');
        END;

        CREATE TRIGGER persons_identity_biometric_update
        BEFORE UPDATE OF identity_status, biometric_status ON persons
        WHEN NEW.identity_status = 'UNIDENTIFIED'
         AND NEW.biometric_status = 'NO_FACE'
         AND trim(NEW.name) = ''
         AND trim(NEW.notes) = ''
         AND trim(NEW.metadata) IN ('', '{}')
        BEGIN
            SELECT RAISE(ABORT, 'an unidentified person without a face or context is invalid');
        END;

        CREATE TRIGGER persons_canonical_insert
        BEFORE INSERT ON persons
        WHEN NEW.canonical_person_id IS NOT NULL OR NEW.lifecycle_status = 'MERGED'
        BEGIN
            SELECT CASE
                WHEN NEW.lifecycle_status <> 'MERGED' OR NEW.canonical_person_id IS NULL
                THEN RAISE(ABORT, 'canonical mapping requires MERGED lifecycle status')
            END;
            SELECT CASE
                WHEN NEW.canonical_person_id = NEW.person_id
                THEN RAISE(ABORT, 'canonical identity cannot reference itself')
            END;
            SELECT CASE
                WHEN NOT EXISTS(SELECT 1 FROM persons WHERE person_id = NEW.canonical_person_id)
                THEN RAISE(ABORT, 'canonical identity target does not exist')
            END;
        END;

        CREATE TRIGGER persons_canonical_update
        BEFORE UPDATE OF canonical_person_id, lifecycle_status ON persons
        WHEN NEW.canonical_person_id IS NOT NULL OR NEW.lifecycle_status = 'MERGED'
        BEGIN
            SELECT CASE
                WHEN NEW.lifecycle_status <> 'MERGED' OR NEW.canonical_person_id IS NULL
                THEN RAISE(ABORT, 'canonical mapping requires MERGED lifecycle status')
            END;
            SELECT CASE
                WHEN NEW.canonical_person_id = NEW.person_id
                THEN RAISE(ABORT, 'canonical identity cannot reference itself')
            END;
            SELECT CASE
                WHEN NOT EXISTS(SELECT 1 FROM persons WHERE person_id = NEW.canonical_person_id)
                THEN RAISE(ABORT, 'canonical identity target does not exist')
            END;
            WITH RECURSIVE canonical_chain(person_id, canonical_person_id) AS (
                SELECT person_id, canonical_person_id
                FROM persons WHERE person_id = NEW.canonical_person_id
                UNION
                SELECT p.person_id, p.canonical_person_id
                FROM persons p
                JOIN canonical_chain c ON p.person_id = c.canonical_person_id
                WHERE c.canonical_person_id IS NOT NULL
            )
            SELECT CASE
                WHEN EXISTS(SELECT 1 FROM canonical_chain WHERE person_id = NEW.person_id)
                THEN RAISE(ABORT, 'canonical identity cycle detected')
            END;
        END;

        PRAGMA user_version = 18;
        """,
    )


def _migrate_18_to_19(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE observations (
            observation_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'DRAFT'
                CHECK(status IN ('DRAFT', 'FINALIZED')),
            observed_at TEXT,
            location TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            source TEXT,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finalized_at TEXT,
            FOREIGN KEY(created_operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            CHECK(
                (status = 'DRAFT' AND finalized_at IS NULL)
                OR (status = 'FINALIZED' AND finalized_at IS NOT NULL)
            )
        );

        CREATE INDEX idx_observations_status_time
        ON observations(status, observed_at, created_at);

        CREATE TABLE observation_media (
            observation_id TEXT NOT NULL,
            media_id TEXT NOT NULL,
            media_path TEXT,
            source TEXT,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(observation_id, media_id),
            FOREIGN KEY(observation_id)
                REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_observation_media_media
        ON observation_media(media_id, observation_id);

        CREATE TABLE observation_participants (
            observation_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            source TEXT,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(observation_id, person_id),
            FOREIGN KEY(observation_id)
                REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(person_id)
                REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_observation_participants_person
        ON observation_participants(person_id, observation_id);

        CREATE TRIGGER observations_no_delete
        BEFORE DELETE ON observations
        BEGIN
            SELECT RAISE(ABORT, 'observations cannot be deleted');
        END;

        CREATE TRIGGER observations_id_immutable
        BEFORE UPDATE OF observation_id ON observations
        BEGIN
            SELECT RAISE(ABORT, 'observation IDs are immutable');
        END;

        CREATE TRIGGER observations_finalized_immutable
        BEFORE UPDATE OF observed_at, location, context, source ON observations
        WHEN OLD.status = 'FINALIZED'
        BEGIN
            SELECT RAISE(ABORT, 'finalized observations are immutable');
        END;

        CREATE TRIGGER observations_status_transition
        BEFORE UPDATE OF status ON observations
        BEGIN
            SELECT CASE
                WHEN OLD.status <> 'DRAFT' OR NEW.status <> 'FINALIZED'
                THEN RAISE(ABORT, 'invalid observation status transition')
            END;
            SELECT CASE
                WHEN NOT EXISTS(
                    SELECT 1 FROM observation_participants p
                    WHERE p.observation_id = OLD.observation_id
                )
                THEN RAISE(ABORT, 'a finalized observation requires a participant')
            END;
        END;

        CREATE TRIGGER observation_media_draft_insert
        BEFORE INSERT ON observation_media
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = NEW.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation media can change only while draft');
        END;

        CREATE TRIGGER observation_media_draft_delete
        BEFORE DELETE ON observation_media
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = OLD.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation media can change only while draft');
        END;

        CREATE TRIGGER observation_participants_draft_insert
        BEFORE INSERT ON observation_participants
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = NEW.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation participants can change only while draft');
        END;

        CREATE TRIGGER observation_participants_draft_delete
        BEFORE DELETE ON observation_participants
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = OLD.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation participants can change only while draft');
        END;

        PRAGMA user_version = 19;
        """,
    )
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if "recognition_details" in tables:
        detail_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(recognition_details)")
        }
        if "observation_id" not in detail_columns:
            conn.execute(
                "ALTER TABLE recognition_details ADD COLUMN observation_id TEXT "
                "REFERENCES observations(observation_id) ON DELETE RESTRICT"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recognition_details_observation "
            "ON recognition_details(observation_id)"
        )


def _migrate_19_to_20(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE relationship_evidence (
            evidence_id TEXT PRIMARY KEY,
            evidence_type TEXT NOT NULL
                CHECK(evidence_type IN ('CO_OBSERVED', 'NOTE_REFERENCE', 'MANUAL_ASSOCIATION')),
            source_entity_type TEXT NOT NULL
                CHECK(source_entity_type IN ('OBSERVATION', 'NOTE', 'MANUAL_ASSERTION')),
            source_entity_id TEXT NOT NULL,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT 'ASSOCIATED_WITH',
            directionality TEXT NOT NULL DEFAULT 'UNDIRECTED'
                CHECK(directionality IN ('UNDIRECTED', 'DIRECTED')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            source TEXT,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deactivated_operation_id TEXT,
            deactivated_at TEXT,
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(deactivated_operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            UNIQUE(
                evidence_type, source_entity_type, source_entity_id,
                source_person_id, target_person_id, relationship_type, directionality
            ),
            CHECK(source_person_id <> target_person_id),
            CHECK(
                (active = 1 AND deactivated_operation_id IS NULL AND deactivated_at IS NULL)
                OR
                (active = 0 AND deactivated_operation_id IS NOT NULL AND deactivated_at IS NOT NULL)
            ),
            CHECK(
                (evidence_type = 'CO_OBSERVED' AND source_entity_type = 'OBSERVATION')
                OR (evidence_type = 'NOTE_REFERENCE' AND source_entity_type = 'NOTE')
                OR (evidence_type = 'MANUAL_ASSOCIATION' AND source_entity_type = 'MANUAL_ASSERTION')
            )
        );

        CREATE INDEX idx_relationship_evidence_source
        ON relationship_evidence(evidence_type, source_entity_id, active);

        CREATE INDEX idx_relationship_evidence_people
        ON relationship_evidence(source_person_id, target_person_id, active);

        CREATE TABLE graph_connections (
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            directionality TEXT NOT NULL
                CHECK(directionality IN ('UNDIRECTED', 'DIRECTED')),
            evidence_count INTEGER NOT NULL CHECK(evidence_count > 0),
            evidence_types TEXT NOT NULL,
            last_evidence_at TEXT NOT NULL,
            PRIMARY KEY(
                source_person_id, target_person_id, relationship_type, directionality
            ),
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            CHECK(source_person_id <> target_person_id),
            CHECK(directionality = 'DIRECTED' OR source_person_id < target_person_id)
        );

        CREATE INDEX idx_graph_connections_target
        ON graph_connections(target_person_id, source_person_id);

        CREATE TRIGGER relationship_evidence_no_delete
        BEFORE DELETE ON relationship_evidence
        BEGIN
            SELECT RAISE(ABORT, 'relationship evidence cannot be deleted');
        END;

        CREATE TRIGGER relationship_evidence_identity_immutable
        BEFORE UPDATE OF evidence_id, evidence_type, source_entity_type, source_entity_id,
                         source_person_id, target_person_id, relationship_type, directionality,
                         source, created_operation_id, created_at
        ON relationship_evidence
        BEGIN
            SELECT RAISE(ABORT, 'relationship evidence provenance is immutable');
        END;

        CREATE TRIGGER relationship_evidence_deactivation_only
        BEFORE UPDATE OF active, deactivated_operation_id, deactivated_at
        ON relationship_evidence
        WHEN OLD.active = 0 OR NEW.active <> 0
        BEGIN
            SELECT RAISE(ABORT, 'relationship evidence can only transition from active to inactive');
        END;

        PRAGMA user_version = 20;
        """,
    )


def _migrate_20_to_21(conn: sqlite3.Connection) -> None:
    invalid = conn.execute(
        """
        SELECT evidence_id
        FROM relationship_evidence
        WHERE directionality = 'UNDIRECTED'
          AND source_person_id >= target_person_id
        LIMIT 1
        """
    ).fetchone()
    if invalid is not None:
        raise SchemaMigrationError(
            "Cannot enforce undirected evidence ordering: "
            f"evidence {invalid['evidence_id']} has non-canonical raw endpoint order"
        )
    _execute_migration_script(
        conn,
        """
        CREATE TRIGGER relationship_evidence_undirected_order_insert
        BEFORE INSERT ON relationship_evidence
        WHEN NEW.directionality = 'UNDIRECTED'
         AND NEW.source_person_id >= NEW.target_person_id
        BEGIN
            SELECT RAISE(ABORT, 'undirected evidence endpoints must be ordered');
        END;

        PRAGMA user_version = 21;
        """,
    )


def _migrate_21_to_22(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE notes (
            note_id TEXT PRIMARY KEY,
            owner_person_id TEXT NOT NULL,
            subject_type TEXT NOT NULL CHECK(subject_type IN ('PERSON', 'RECOGNITION_DETAIL')),
            subject_id TEXT NOT NULL,
            is_profile_note INTEGER NOT NULL DEFAULT 0 CHECK(is_profile_note IN (0, 1)),
            status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'RETIRED')),
            created_operation_id TEXT,
            retired_operation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            retired_at TEXT,
            FOREIGN KEY(owner_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(retired_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            CHECK(
                (status = 'ACTIVE' AND retired_operation_id IS NULL AND retired_at IS NULL)
                OR
                (status = 'RETIRED' AND retired_operation_id IS NOT NULL AND retired_at IS NOT NULL)
            )
        );

        CREATE UNIQUE INDEX idx_notes_active_profile
        ON notes(owner_person_id)
        WHERE is_profile_note = 1 AND status = 'ACTIVE';

        CREATE INDEX idx_notes_subject
        ON notes(subject_type, subject_id, status);

        CREATE TABLE note_revisions (
            revision_id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL,
            revision_number INTEGER NOT NULL CHECK(revision_number > 0),
            content TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT '{}',
            author_name TEXT NOT NULL DEFAULT '',
            operation_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(note_id) REFERENCES notes(note_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            UNIQUE(note_id, revision_number)
        );

        CREATE INDEX idx_note_revisions_note
        ON note_revisions(note_id, revision_number);

        CREATE TABLE note_revision_mentions (
            revision_id TEXT NOT NULL,
            referenced_person_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(revision_id, referenced_person_id),
            FOREIGN KEY(revision_id) REFERENCES note_revisions(revision_id) ON DELETE RESTRICT,
            FOREIGN KEY(referenced_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT
        );

        CREATE TABLE note_mentions (
            mention_id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL,
            referenced_person_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            created_revision_id TEXT NOT NULL,
            retired_revision_id TEXT,
            created_operation_id TEXT NOT NULL,
            retired_operation_id TEXT,
            created_at TEXT NOT NULL,
            retired_at TEXT,
            FOREIGN KEY(note_id) REFERENCES notes(note_id) ON DELETE RESTRICT,
            FOREIGN KEY(referenced_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_revision_id) REFERENCES note_revisions(revision_id) ON DELETE RESTRICT,
            FOREIGN KEY(retired_revision_id) REFERENCES note_revisions(revision_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(retired_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            CHECK(
                (active = 1 AND retired_revision_id IS NULL
                 AND retired_operation_id IS NULL AND retired_at IS NULL)
                OR
                (active = 0 AND retired_operation_id IS NOT NULL AND retired_at IS NOT NULL)
            )
        );

        CREATE UNIQUE INDEX idx_note_mentions_active_target
        ON note_mentions(note_id, referenced_person_id)
        WHERE active = 1;

        CREATE TRIGGER notes_no_delete
        BEFORE DELETE ON notes
        BEGIN
            SELECT RAISE(ABORT, 'notes cannot be deleted');
        END;

        CREATE TRIGGER notes_identity_immutable
        BEFORE UPDATE OF note_id, owner_person_id, subject_type, subject_id,
                         is_profile_note, created_operation_id, created_at
        ON notes
        BEGIN
            SELECT RAISE(ABORT, 'note identity and provenance are immutable');
        END;

        CREATE TRIGGER notes_retirement_only
        BEFORE UPDATE OF status, retired_operation_id, retired_at ON notes
        WHEN OLD.status = 'RETIRED' OR NEW.status <> 'RETIRED'
        BEGIN
            SELECT RAISE(ABORT, 'notes can only transition from active to retired');
        END;

        CREATE TRIGGER note_revisions_no_update
        BEFORE UPDATE ON note_revisions
        BEGIN
            SELECT RAISE(ABORT, 'note revisions are immutable');
        END;

        CREATE TRIGGER note_revisions_no_delete
        BEFORE DELETE ON note_revisions
        BEGIN
            SELECT RAISE(ABORT, 'note revisions cannot be deleted');
        END;

        CREATE TRIGGER note_revision_mentions_no_update
        BEFORE UPDATE ON note_revision_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note revision mentions are immutable');
        END;

        CREATE TRIGGER note_revision_mentions_no_delete
        BEFORE DELETE ON note_revision_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note revision mentions cannot be deleted');
        END;

        CREATE TRIGGER note_mentions_no_delete
        BEFORE DELETE ON note_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note mentions cannot be deleted');
        END;

        CREATE TRIGGER note_mentions_identity_immutable
        BEFORE UPDATE OF mention_id, note_id, referenced_person_id,
                         created_revision_id, created_operation_id, created_at
        ON note_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note mention provenance is immutable');
        END;

        CREATE TRIGGER note_mentions_deactivation_only
        BEFORE UPDATE OF active, retired_revision_id, retired_operation_id, retired_at
        ON note_mentions
        WHEN OLD.active = 0 OR NEW.active <> 0
        BEGIN
            SELECT RAISE(ABORT, 'note mentions can only transition from active to inactive');
        END;
        """,
    )
    actor_payload = json.dumps(
        {"display_name": "Legacy migration", "roles": []}, separators=(",", ":"),
    )
    person_rows = conn.execute(
        """
        SELECT person_id, notes, created_at
        FROM persons
        WHERE trim(notes) <> ''
        ORDER BY person_id
        """
    ).fetchall()
    for row in person_rows:
        note_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface:person-note:{row['person_id']}"))
        revision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{note_id}:revision:1"))
        created_at = str(row["created_at"] or utc_now())
        conn.execute(
            """
            INSERT INTO notes(
                note_id, owner_person_id, subject_type, subject_id, is_profile_note,
                status, created_at, updated_at
            ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?)
            """,
            (note_id, row["person_id"], row["person_id"], created_at, created_at),
        )
        conn.execute(
            """
            INSERT INTO note_revisions(
                revision_id, note_id, revision_number, content, actor,
                author_name, operation_id, created_at
            ) VALUES (?, ?, 1, ?, ?, 'Legacy migration', NULL, ?)
            """,
            (revision_id, note_id, row["notes"], actor_payload, created_at),
        )
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if "recognition_details" in tables:
        detail_rows = conn.execute(
            """
            SELECT detail_id, person_id, notes, created_at
            FROM recognition_details
            WHERE trim(notes) <> ''
            ORDER BY detail_id
            """
        ).fetchall()
        for row in detail_rows:
            note_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"sentriface:recognition-note:{row['detail_id']}",
            ))
            revision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{note_id}:revision:1"))
            created_at = str(row["created_at"] or utc_now())
            conn.execute(
                """
                INSERT INTO notes(
                    note_id, owner_person_id, subject_type, subject_id,
                    is_profile_note, status, created_at, updated_at
                ) VALUES (?, ?, 'RECOGNITION_DETAIL', ?, 0, 'ACTIVE', ?, ?)
                """,
                (note_id, row["person_id"], row["detail_id"], created_at, created_at),
            )
            conn.execute(
                """
                INSERT INTO note_revisions(
                    revision_id, note_id, revision_number, content, actor,
                    author_name, operation_id, created_at
                ) VALUES (?, ?, 1, ?, ?, 'Legacy migration', NULL, ?)
                """,
                (revision_id, note_id, row["notes"], actor_payload, created_at),
            )
    conn.execute("PRAGMA user_version = 22")


def _migrate_22_to_23(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE photo_reviews (
            review_id TEXT PRIMARY KEY,
            media_id TEXT NOT NULL,
            media_path TEXT,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'IN_PROGRESS'
                CHECK(status IN ('IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
            observation_id TEXT,
            completed_operation_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(observation_id) REFERENCES observations(observation_id),
            FOREIGN KEY(completed_operation_id) REFERENCES operation_journal(operation_id)
        );

        CREATE TABLE photo_review_faces (
            review_id TEXT NOT NULL,
            face_id TEXT NOT NULL,
            staged_face_type TEXT NOT NULL
                CHECK(staged_face_type IN ('PENDING_ADDITION', 'INIT_FACE')),
            staged_face_id TEXT NOT NULL,
            decision TEXT
                CHECK(decision IS NULL OR decision IN (
                    'ACCEPT_EXISTING_PERSON', 'ACCEPT_NEW_PERSON', 'EXCLUDE', 'SKIP'
                )),
            person_id TEXT,
            new_person_key TEXT,
            new_person_name TEXT,
            new_person_metadata TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT '',
            mentioned_person_ids TEXT NOT NULL DEFAULT '[]',
            recognition_detail TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(review_id, face_id),
            UNIQUE(staged_face_type, staged_face_id),
            FOREIGN KEY(review_id) REFERENCES photo_reviews(review_id),
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX idx_photo_reviews_status_created
        ON photo_reviews(status, created_at);

        CREATE TRIGGER completed_photo_reviews_immutable
        BEFORE UPDATE ON photo_reviews
        WHEN OLD.status = 'COMPLETED'
        BEGIN
            SELECT RAISE(ABORT, 'completed reviews are immutable');
        END;

        CREATE TRIGGER completed_photo_review_faces_immutable
        BEFORE UPDATE ON photo_review_faces
        WHEN EXISTS (
            SELECT 1 FROM photo_reviews r
            WHERE r.review_id = OLD.review_id AND r.status = 'COMPLETED'
        )
        BEGIN
            SELECT RAISE(ABORT, 'completed review decisions are immutable');
        END;

        PRAGMA user_version = 23;
        """,
    )


def _migrate_23_to_24(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE observation_face_assignments (
            assignment_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            face_id TEXT NOT NULL,
            embedding_id TEXT NOT NULL,
            original_person_id TEXT NOT NULL,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(observation_id, face_id),
            FOREIGN KEY(observation_id) REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(review_id) REFERENCES photo_reviews(review_id) ON DELETE RESTRICT,
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id) ON DELETE RESTRICT,
            FOREIGN KEY(original_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_observation_face_assignments_embedding
        ON observation_face_assignments(embedding_id, observation_id);

        CREATE TABLE identity_corrections (
            correction_id TEXT PRIMARY KEY,
            correction_type TEXT NOT NULL CHECK(correction_type IN (
                'OBSERVATION_IDENTITY', 'FACE_ASSIGNMENT', 'FACE_OWNERSHIP'
            )),
            observation_id TEXT,
            face_assignment_id TEXT,
            embedding_id TEXT,
            from_person_id TEXT NOT NULL,
            to_person_id TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK(from_person_id <> to_person_id),
            FOREIGN KEY(observation_id) REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(face_assignment_id) REFERENCES observation_face_assignments(assignment_id) ON DELETE RESTRICT,
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id) ON DELETE RESTRICT,
            FOREIGN KEY(from_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(to_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_identity_corrections_observation
        ON identity_corrections(observation_id, created_at, correction_id);

        CREATE INDEX idx_identity_corrections_embedding
        ON identity_corrections(embedding_id, created_at, correction_id);

        CREATE TABLE biometric_enrollment_history (
            enrollment_id TEXT PRIMARY KEY,
            embedding_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(operation_id, embedding_id),
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id) ON DELETE RESTRICT,
            FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(review_id) REFERENCES photo_reviews(review_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE TRIGGER observation_face_assignments_no_update
        BEFORE UPDATE ON observation_face_assignments
        BEGIN
            SELECT RAISE(ABORT, 'observation face assignments are immutable');
        END;

        CREATE TRIGGER observation_face_assignments_no_delete
        BEFORE DELETE ON observation_face_assignments
        BEGIN
            SELECT RAISE(ABORT, 'observation face assignments cannot be deleted');
        END;

        CREATE TRIGGER identity_corrections_no_update
        BEFORE UPDATE ON identity_corrections
        BEGIN
            SELECT RAISE(ABORT, 'identity corrections are immutable');
        END;

        CREATE TRIGGER identity_corrections_no_delete
        BEFORE DELETE ON identity_corrections
        BEGIN
            SELECT RAISE(ABORT, 'identity corrections cannot be deleted');
        END;

        CREATE TRIGGER biometric_enrollment_history_no_update
        BEFORE UPDATE ON biometric_enrollment_history
        BEGIN
            SELECT RAISE(ABORT, 'biometric enrollment history is immutable');
        END;

        CREATE TRIGGER biometric_enrollment_history_no_delete
        BEFORE DELETE ON biometric_enrollment_history
        BEGIN
            SELECT RAISE(ABORT, 'biometric enrollment history cannot be deleted');
        END;
        """,
    )


    completed_reviews = conn.execute(
        """
        SELECT r.review_id, r.observation_id, r.completed_operation_id, h.details, r.completed_at
        FROM photo_reviews r
        JOIN operation_journal_status_history h
          ON h.operation_id = r.completed_operation_id AND h.to_status = 'COMMITTED'
        WHERE r.status = 'COMPLETED' AND r.observation_id IS NOT NULL
        ORDER BY r.review_id
        """
    ).fetchall()
    for review in completed_reviews:
        result = json.loads(review["details"] or "{}")
        face_assignments = result.get("face_assignments") or {}
        embedding_assignments = result.get("embedding_assignments") or {}
        for face_id in sorted(set(face_assignments) & set(embedding_assignments)):
            assignment_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"sentriface:observation-face:{review['observation_id']}:{face_id}",
            ))
            conn.execute(
                """
                INSERT OR IGNORE INTO observation_face_assignments(
                    assignment_id, observation_id, review_id, face_id, embedding_id,
                    original_person_id, created_operation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id, review["observation_id"], review["review_id"], face_id,
                    embedding_assignments[face_id], face_assignments[face_id],
                    review["completed_operation_id"], review["completed_at"] or utc_now(),
                ),
            )

    _execute_migration_script(
        conn,
        """
        DROP TRIGGER relationship_evidence_no_delete;
        DROP TRIGGER relationship_evidence_identity_immutable;
        DROP TRIGGER relationship_evidence_deactivation_only;
        DROP TRIGGER relationship_evidence_undirected_order_insert;
        DROP INDEX idx_relationship_evidence_source;
        DROP INDEX idx_relationship_evidence_people;
        ALTER TABLE relationship_evidence RENAME TO relationship_evidence_v23;

        CREATE TABLE relationship_evidence (
            evidence_id TEXT PRIMARY KEY,
            evidence_type TEXT NOT NULL CHECK(evidence_type IN ('CO_OBSERVED', 'NOTE_REFERENCE', 'MANUAL_ASSOCIATION')),
            source_entity_type TEXT NOT NULL CHECK(source_entity_type IN ('OBSERVATION', 'NOTE', 'MANUAL_ASSERTION')),
            source_entity_id TEXT NOT NULL,
            evidence_revision_id TEXT NOT NULL,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT 'ASSOCIATED_WITH',
            directionality TEXT NOT NULL DEFAULT 'UNDIRECTED' CHECK(directionality IN ('UNDIRECTED', 'DIRECTED')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            source TEXT,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deactivated_operation_id TEXT,
            deactivated_at TEXT,
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(deactivated_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            UNIQUE(evidence_type, source_entity_type, source_entity_id, evidence_revision_id,
                   source_person_id, target_person_id, relationship_type, directionality),
            CHECK(source_person_id <> target_person_id),
            CHECK((active = 1 AND deactivated_operation_id IS NULL AND deactivated_at IS NULL)
               OR (active = 0 AND deactivated_operation_id IS NOT NULL AND deactivated_at IS NOT NULL)),
            CHECK((evidence_type = 'CO_OBSERVED' AND source_entity_type = 'OBSERVATION')
               OR (evidence_type = 'NOTE_REFERENCE' AND source_entity_type = 'NOTE')
               OR (evidence_type = 'MANUAL_ASSOCIATION' AND source_entity_type = 'MANUAL_ASSERTION'))
        );

        INSERT INTO relationship_evidence(
            evidence_id, evidence_type, source_entity_type, source_entity_id,
            evidence_revision_id, source_person_id, target_person_id, relationship_type,
            directionality, active, source, created_operation_id, created_at,
            deactivated_operation_id, deactivated_at
        )
        SELECT evidence_id, evidence_type, source_entity_type, source_entity_id,
               source_entity_id, source_person_id, target_person_id, relationship_type,
               directionality, active, source, created_operation_id, created_at,
               deactivated_operation_id, deactivated_at
        FROM relationship_evidence_v23;
        DROP TABLE relationship_evidence_v23;

        CREATE INDEX idx_relationship_evidence_source
        ON relationship_evidence(evidence_type, source_entity_id, active);
        CREATE INDEX idx_relationship_evidence_people
        ON relationship_evidence(source_person_id, target_person_id, active);

        CREATE TRIGGER relationship_evidence_no_delete
        BEFORE DELETE ON relationship_evidence
        BEGIN SELECT RAISE(ABORT, 'relationship evidence cannot be deleted'); END;
        CREATE TRIGGER relationship_evidence_identity_immutable
        BEFORE UPDATE OF evidence_id, evidence_type, source_entity_type, source_entity_id,
                         evidence_revision_id, source_person_id, target_person_id,
                         relationship_type, directionality, source, created_operation_id, created_at
        ON relationship_evidence
        BEGIN SELECT RAISE(ABORT, 'relationship evidence provenance is immutable'); END;
        CREATE TRIGGER relationship_evidence_deactivation_only
        BEFORE UPDATE OF active, deactivated_operation_id, deactivated_at ON relationship_evidence
        WHEN OLD.active = 0 OR NEW.active <> 0
        BEGIN SELECT RAISE(ABORT, 'relationship evidence can only transition from active to inactive'); END;
        CREATE TRIGGER relationship_evidence_undirected_order_insert
        BEFORE INSERT ON relationship_evidence
        WHEN NEW.directionality = 'UNDIRECTED' AND NEW.source_person_id >= NEW.target_person_id
        BEGIN SELECT RAISE(ABORT, 'undirected evidence endpoints must be ordered'); END;

        PRAGMA user_version = 24;
        """,
    )


def _migrate_24_to_25(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE merge_operations (
            merge_operation_id TEXT PRIMARY KEY,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL,
            previous_source_lifecycle_status TEXT NOT NULL,
            previous_target_lifecycle_status TEXT NOT NULL,
            previous_source_canonical_person_id TEXT,
            previous_target_canonical_person_id TEXT,
            reason TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            operation_journal_id TEXT NOT NULL UNIQUE,
            CHECK(source_person_id <> target_person_id),
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(previous_source_canonical_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(previous_target_canonical_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_journal_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE TABLE merge_affected_items (
            merge_operation_id TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            previous_person_id TEXT,
            effective_person_id TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(merge_operation_id, item_type, item_id),
            FOREIGN KEY(merge_operation_id) REFERENCES merge_operations(merge_operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(previous_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(effective_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_merge_operations_people
        ON merge_operations(source_person_id, target_person_id, created_at);
        CREATE INDEX idx_merge_affected_items_lookup
        ON merge_affected_items(item_type, item_id);

        CREATE TRIGGER merge_operations_no_update
        BEFORE UPDATE ON merge_operations
        BEGIN SELECT RAISE(ABORT, 'merge operations are immutable'); END;
        CREATE TRIGGER merge_operations_no_delete
        BEFORE DELETE ON merge_operations
        BEGIN SELECT RAISE(ABORT, 'merge operations cannot be deleted'); END;
        CREATE TRIGGER merge_affected_items_no_update
        BEFORE UPDATE ON merge_affected_items
        BEGIN SELECT RAISE(ABORT, 'merge affected items are immutable'); END;
        CREATE TRIGGER merge_affected_items_no_delete
        BEFORE DELETE ON merge_affected_items
        BEGIN SELECT RAISE(ABORT, 'merge affected items cannot be deleted'); END;

        PRAGMA user_version = 25;
        """,
    )


def _migrate_25_to_26(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        DROP TRIGGER merge_affected_items_no_update;
        ALTER TABLE merge_affected_items ADD COLUMN raw_owner_person_id TEXT REFERENCES persons(person_id) ON DELETE RESTRICT;
        ALTER TABLE merge_affected_items ADD COLUMN effective_owner_person_id TEXT REFERENCES persons(person_id) ON DELETE RESTRICT;
        ALTER TABLE merge_affected_items ADD COLUMN action TEXT NOT NULL DEFAULT 'PRESERVE'
            CHECK(action IN ('PRESERVE', 'REINTERPRET_CANONICAL_OWNER', 'UNION_IN_CURRENT_VIEW', 'SELECT_VALUE'));
        ALTER TABLE merge_affected_items ADD COLUMN before_state TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE merge_affected_items ADD COLUMN after_state TEXT NOT NULL DEFAULT '{}';
        UPDATE merge_affected_items
        SET raw_owner_person_id = previous_person_id,
            effective_owner_person_id = effective_person_id;

        CREATE TRIGGER merge_affected_items_no_update
        BEFORE UPDATE ON merge_affected_items
        BEGIN SELECT RAISE(ABORT, 'merge affected items are immutable'); END;

        CREATE TABLE merge_conflict_resolutions (
            conflict_id TEXT PRIMARY KEY,
            merge_operation_id TEXT NOT NULL,
            category TEXT NOT NULL,
            field_name TEXT NOT NULL,
            source_value TEXT NOT NULL,
            target_value TEXT NOT NULL,
            strategy TEXT NOT NULL CHECK(strategy IN (
                'KEEP_SOURCE', 'KEEP_TARGET', 'COMBINE', 'USER_SELECTED'
            )),
            selected_value TEXT NOT NULL,
            inverse_data TEXT NOT NULL,
            UNIQUE(merge_operation_id, category, field_name),
            FOREIGN KEY(merge_operation_id) REFERENCES merge_operations(merge_operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_merge_conflicts_operation
        ON merge_conflict_resolutions(merge_operation_id, category, field_name);

        CREATE TRIGGER merge_conflicts_no_update
        BEFORE UPDATE ON merge_conflict_resolutions
        BEGIN SELECT RAISE(ABORT, 'merge conflict resolutions are immutable'); END;
        CREATE TRIGGER merge_conflicts_no_delete
        BEFORE DELETE ON merge_conflict_resolutions
        BEGIN SELECT RAISE(ABORT, 'merge conflict resolutions cannot be deleted'); END;

        CREATE TRIGGER merge_operations_require_terminal_survivor
        BEFORE INSERT ON merge_operations
        WHEN NOT EXISTS (
            SELECT 1 FROM persons p
            WHERE p.person_id = NEW.target_person_id
              AND p.lifecycle_status = 'ACTIVE'
              AND p.deleted_at IS NULL
              AND p.canonical_person_id IS NULL
        )
        BEGIN SELECT RAISE(ABORT, 'merge survivor must be the terminal active canonical identity'); END;

        CREATE TRIGGER merge_operations_require_journal_identity
        BEFORE INSERT ON merge_operations
        WHEN NEW.merge_operation_id <> NEW.operation_journal_id
          OR NOT EXISTS (
              SELECT 1 FROM operation_journal j
              WHERE j.operation_id = NEW.operation_journal_id
                AND j.operation_type = 'identity.merge'
                AND j.status = 'STARTED'
                AND j.actor = NEW.actor
          )
        BEGIN SELECT RAISE(ABORT, 'merge manifest must match its started journal identity and actor'); END;

        CREATE TRIGGER merge_affected_items_require_started_journal
        BEFORE INSERT ON merge_affected_items
        WHEN NOT EXISTS (
            SELECT 1 FROM merge_operations m
            JOIN operation_journal j ON j.operation_id = m.operation_journal_id
            WHERE m.merge_operation_id = NEW.merge_operation_id AND j.status = 'STARTED'
        )
        BEGIN SELECT RAISE(ABORT, 'merge manifest is closed'); END;

        CREATE TRIGGER merge_conflicts_require_started_journal
        BEFORE INSERT ON merge_conflict_resolutions
        WHEN NOT EXISTS (
            SELECT 1 FROM merge_operations m
            JOIN operation_journal j ON j.operation_id = m.operation_journal_id
            WHERE m.merge_operation_id = NEW.merge_operation_id AND j.status = 'STARTED'
        )
        BEGIN SELECT RAISE(ABORT, 'merge manifest is closed'); END;

        PRAGMA user_version = 26;
        """,
    )


def _migrate_26_to_27(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE graph_state (
            singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
            revision INTEGER NOT NULL CHECK(revision >= 1),
            updated_at TEXT NOT NULL
        );
        INSERT INTO graph_state(singleton_id, revision, updated_at)
        VALUES (1, 1, CURRENT_TIMESTAMP);

        CREATE INDEX idx_relationship_evidence_active_endpoints_time
        ON relationship_evidence(active, source_person_id, target_person_id, created_at);
        CREATE INDEX idx_observations_finalized_time_location
        ON observations(status, observed_at, location);

        CREATE TRIGGER graph_revision_person_insert
        AFTER INSERT ON persons
        BEGIN
            UPDATE graph_state
            SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1;
        END;
        CREATE TRIGGER graph_revision_person_read_fields
        AFTER UPDATE OF name, metadata, lifecycle_status, canonical_person_id,
                        identity_status, biometric_status ON persons
        BEGIN
            UPDATE graph_state
            SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1;
        END;

        PRAGMA user_version = 27;
        """,
    )
    # v27 introduced graph_state. Normalize a drifting pre-P11 projection once
    # inside the schema-upgrade transaction; do not churn an already-equal graph.
    expected, errors, _ = _expected_graph_connections(conn)
    if errors:
        raise RuntimeError(
            "Relationship evidence validation failed: " + "; ".join(errors)
        )
    actual_rows = conn.execute("SELECT * FROM graph_connections").fetchall()
    if (
        {_graph_connection_signature(item) for item in expected}
        != {_graph_connection_row_signature(item) for item in actual_rows}
    ):
        _write_graph_projection(conn, expected)
        _advance_graph_revision(conn)


def _migrate_27_to_28(conn: sqlite3.Connection) -> None:
    """Restrict the shared read revision to fields visible in graph/World contracts."""
    _execute_migration_script(
        conn,
        """
        DROP TRIGGER graph_revision_person_read_fields;
        CREATE TRIGGER graph_revision_person_read_fields
        AFTER UPDATE OF name, metadata, lifecycle_status, canonical_person_id,
                        identity_status, biometric_status ON persons
        WHEN OLD.name IS NOT NEW.name
          OR OLD.lifecycle_status IS NOT NEW.lifecycle_status
          OR OLD.canonical_person_id IS NOT NEW.canonical_person_id
          OR OLD.identity_status IS NOT NEW.identity_status
          OR OLD.biometric_status IS NOT NEW.biometric_status
          OR COALESCE(json_extract(OLD.metadata, '$.country'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.country'), '')
          OR COALESCE(json_extract(OLD.metadata, '$.rank'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.rank'), '')
          OR COALESCE(json_extract(OLD.metadata, '$.importance'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.importance'), '')
          OR COALESCE(json_extract(OLD.metadata, '$.representative_embedding_id'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.representative_embedding_id'), '')
        BEGIN
            UPDATE graph_state
            SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1;
        END;

        PRAGMA user_version = 28;
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
        SchemaMigration(17, 18, _migrate_17_to_18),
        SchemaMigration(18, 19, _migrate_18_to_19),
        SchemaMigration(19, 20, _migrate_19_to_20),
        SchemaMigration(20, 21, _migrate_20_to_21),
        SchemaMigration(21, 22, _migrate_21_to_22),
        SchemaMigration(22, 23, _migrate_22_to_23),
        SchemaMigration(23, 24, _migrate_23_to_24),
        SchemaMigration(24, 25, _migrate_24_to_25),
        SchemaMigration(25, 26, _migrate_25_to_26),
        SchemaMigration(26, 27, _migrate_26_to_27),
        SchemaMigration(27, 28, _migrate_27_to_28),
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


def migrate_staged_database(
    database_path: Path,
    *,
    database_key: bytes | None = None,
) -> tuple[int, int]:
    """Migrate and validate a disposable restore candidate in place.

    The caller owns the staged copy and its safety boundary. Unlike normal
    startup this deliberately creates no pre-migration backup and never opens
    or mutates the live configured database.
    """
    with closing(connect_database(database_path, database_key, row_factory=True)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        source_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        _require_supported_schema_version(source_version)
        _apply_schema_migrations(
            conn, source_version, allow_graph_projection_drift=True,
        )
        final_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if final_version == SCHEMA_VERSION and source_version == final_version:
            conn.execute("BEGIN IMMEDIATE")
            try:
                _validate_current_domain_state(
                    conn, allow_graph_projection_drift=True,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return source_version, final_version


def _apply_schema_migrations(
    conn: sqlite3.Connection,
    current_version: int,
    *,
    allow_graph_projection_drift: bool = False,
) -> None:
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
        _validate_current_domain_state(
            conn,
            allow_graph_projection_drift=allow_graph_projection_drift,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _validate_current_domain_state(
    conn: sqlite3.Connection,
    *,
    allow_graph_projection_drift: bool = False,
) -> None:
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    authoritative_foreign_key_errors = [
        row for row in foreign_key_errors if str(row[0]) != "graph_connections"
    ]
    if authoritative_foreign_key_errors:
        raise SchemaMigrationError(
            "Database domain validation failed: dangling foreign-key references"
        )

    lifecycle_errors: list[str] = []
    people = conn.execute(
        """
        SELECT person_id, lifecycle_status, canonical_person_id, deleted_at,
               identity_status, biometric_status, name, notes, metadata
        FROM persons ORDER BY person_id
        """
    ).fetchall()
    for person in people:
        person_id = str(person["person_id"])
        lifecycle_status = str(person["lifecycle_status"])
        canonical_person_id = person["canonical_person_id"]
        if lifecycle_status not in PERSON_LIFECYCLE_STATUSES:
            lifecycle_errors.append(f"Person {person_id} has invalid lifecycle {lifecycle_status}")
            continue
        if lifecycle_status == "ACTIVE" and person["deleted_at"] is not None:
            lifecycle_errors.append(f"Active person {person_id} has a deletion timestamp")
        if lifecycle_status != "ACTIVE" and person["deleted_at"] is None:
            lifecycle_errors.append(f"Historical person {person_id} lacks a lifecycle timestamp")
        if lifecycle_status == "MERGED" and canonical_person_id is None:
            lifecycle_errors.append(f"Merged person {person_id} has no canonical identity")
        if lifecycle_status != "MERGED" and canonical_person_id is not None:
            lifecycle_errors.append(f"Non-merged person {person_id} has a canonical mapping")
        if canonical_person_id is not None:
            try:
                _resolve_canonical_person_id(conn, person_id)
            except (KeyError, RuntimeError, ValueError) as exc:
                lifecycle_errors.append(f"Person {person_id} has invalid canonical mapping: {exc}")
        try:
            metadata = json.loads(person["metadata"] or "{}")
        except (TypeError, json.JSONDecodeError):
            lifecycle_errors.append(f"Person {person_id} has invalid metadata")
            metadata = {"invalid": True}
        if (
            person["identity_status"] == "UNIDENTIFIED"
            and person["biometric_status"] == "NO_FACE"
            and not str(person["name"] or "").strip()
            and not str(person["notes"] or "").strip()
            and not metadata
        ):
            lifecycle_errors.append(f"Person {person_id} is unidentified with no face or context")
    if lifecycle_errors:
        raise SchemaMigrationError(
            "Database domain validation failed: " + "; ".join(lifecycle_errors)
        )

    _, evidence_errors, _ = _expected_graph_connections(conn)
    if evidence_errors:
        raise SchemaMigrationError(
            "Database relationship evidence validation failed: "
            + "; ".join(evidence_errors)
        )
    validation = _validate_graph_projection(conn)
    if not validation["valid"] and not allow_graph_projection_drift:
        raise SchemaMigrationError(
            "Database graph projection validation failed; run the explicit P11-B "
            "graph projection rebuild after reviewing integrity findings: "
            + "; ".join(validation["errors"])
        )


def _insert_identified_person_record(
    conn: sqlite3.Connection,
    *,
    person_id: str,
    name: str,
    metadata: dict,
    enrollment_status: str,
) -> Person:
    normalized_name = str(name).strip()
    normalized_metadata = dict(metadata or {})
    if not _has_meaningful_identity_context(normalized_name, normalized_metadata, ""):
        raise ValueError("A person without a face requires meaningful identity or context")
    created_at = utc_now()
    person = Person(
        person_id=person_id,
        name=normalized_name,
        metadata=normalized_metadata,
        created_at=created_at,
        enrollment_status=enrollment_status,
        lifecycle_status="ACTIVE",
        identity_status="IDENTIFIED",
        biometric_status="NO_FACE",
    )
    conn.execute(
        """
        INSERT INTO persons(
            person_id, name, metadata, created_at, enrollment_status, notes,
            lifecycle_status, identity_status, biometric_status, lifecycle_changed_at
        ) VALUES (?, ?, ?, ?, ?, '', 'ACTIVE', 'IDENTIFIED', 'NO_FACE', ?)
        """,
        (
            person.person_id,
            person.name,
            json.dumps(person.metadata, separators=(",", ":")),
            person.created_at,
            person.enrollment_status,
            person.created_at,
        ),
    )
    return person


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
          AND lifecycle_status <> 'DELETED'
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
    _insert_unjournaled_profile_note(
        conn, person.person_id, person.notes, person.created_at,
    )
    return person


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _require_staged_review_face(
    conn: sqlite3.Connection, staged_type: str, staged_id: str,
) -> None:
    _staged_review_face_row(conn, staged_type, staged_id)


def _staged_review_face_row(
    conn: sqlite3.Connection, staged_type: str, staged_id: str,
) -> sqlite3.Row:
    normalized_type = str(staged_type).strip().upper()
    normalized_id = str(staged_id).strip()
    if normalized_type == "PENDING_ADDITION":
        row = conn.execute(
            """
            SELECT pending_id AS staged_face_id, vector, quality_score,
                   source_image, crop_path
            FROM pending_additions WHERE pending_id = ?
            """,
            (normalized_id,),
        ).fetchone()
    elif normalized_type == "INIT_FACE":
        row = conn.execute(
            """
            SELECT init_face_id AS staged_face_id, vector, quality_score,
                   source_image, crop_path
            FROM init_faces WHERE init_face_id = ?
            """,
            (normalized_id,),
        ).fetchone()
    else:
        raise ValueError(f"Unsupported staged face type: {staged_type}")
    if row is None:
        raise KeyError(f"Unknown staged review face: {normalized_id}")
    return row


def _require_active_review_person(
    conn: sqlite3.Connection, person_id: object | None,
) -> str:
    normalized_id = str(person_id or "").strip()
    row = conn.execute(
        """
        SELECT 1 FROM persons
        WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
        """,
        (normalized_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown active person: {normalized_id}")
    return normalized_id


def _photo_review_from_conn(conn: sqlite3.Connection, review_id: str) -> PhotoReview:
    row = conn.execute(
        "SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown photo review: {review_id}")
    face_rows = conn.execute(
        "SELECT * FROM photo_review_faces WHERE review_id = ? ORDER BY face_id",
        (review_id,),
    ).fetchall()
    faces = tuple(
        ReviewFaceDecision(
            review_id=str(item["review_id"]),
            face_id=str(item["face_id"]),
            staged_face_type=str(item["staged_face_type"]),
            staged_face_id=str(item["staged_face_id"]),
            decision=item["decision"],
            person_id=item["person_id"],
            new_person_key=item["new_person_key"],
            new_person_name=item["new_person_name"],
            new_person_metadata=json.loads(item["new_person_metadata"] or "{}"),
            notes=str(item["notes"] or ""),
            mentioned_person_ids=tuple(json.loads(item["mentioned_person_ids"] or "[]")),
            recognition_detail=json.loads(item["recognition_detail"] or "{}"),
        )
        for item in face_rows
    )
    return PhotoReview(
        review_id=str(row["review_id"]),
        media_id=str(row["media_id"]),
        media_path=row["media_path"],
        source=str(row["source"]),
        status=str(row["status"]),
        faces=faces,
        created_at=str(row["created_at"]),
        observation_id=row["observation_id"],
        completed_operation_id=row["completed_operation_id"],
        completed_at=row["completed_at"],
    )


def _remove_review_staging(conn: sqlite3.Connection, review_id: str) -> None:
    rows = conn.execute(
        "SELECT staged_face_type, staged_face_id FROM photo_review_faces WHERE review_id = ?",
        (review_id,),
    ).fetchall()
    conn.executemany(
        "DELETE FROM pending_additions WHERE pending_id = ?",
        [(row["staged_face_id"],) for row in rows if row["staged_face_type"] == "PENDING_ADDITION"],
    )
    conn.executemany(
        "DELETE FROM init_faces WHERE init_face_id = ?",
        [(row["staged_face_id"],) for row in rows if row["staged_face_type"] == "INIT_FACE"],
    )


def _create_review_person_note(
    conn: sqlite3.Connection,
    owner_person_id: str,
    content: str,
    mentioned_person_ids: list[str],
    operation_id: str,
    actor: dict | None,
    source: str,
) -> str:
    mentions = _normalize_note_mentions(conn, owner_person_id, mentioned_person_ids)
    note_id = str(uuid.uuid4())
    created_at = utc_now()
    conn.execute(
        """
        INSERT INTO notes(
            note_id, owner_person_id, subject_type, subject_id,
            is_profile_note, status, created_operation_id, created_at, updated_at
        ) VALUES (?, ?, 'PERSON', ?, 0, 'ACTIVE', ?, ?, ?)
        """,
        (note_id, owner_person_id, owner_person_id, operation_id, created_at, created_at),
    )
    revision_id = _insert_note_revision(
        conn,
        note_id=note_id,
        revision_number=1,
        content=content,
        mentions=mentions,
        actor=actor,
        author_name="",
        operation_id=operation_id,
        created_at=created_at,
    )
    _sync_note_reference_evidence(
        conn,
        note_id=note_id,
        owner_person_id=owner_person_id,
        revision_id=revision_id,
        mentions=mentions,
        operation_id=operation_id,
        source=source,
        created_at=created_at,
    )
    return note_id


def _normalize_note_mentions(
    conn: sqlite3.Connection,
    owner_person_id: str,
    mentioned_person_ids: list[str] | None,
    historical_person_ids: set[str] | None = None,
) -> list[tuple[str, str]]:
    normalized_ids = sorted({
        str(person_id).strip()
        for person_id in (mentioned_person_ids or [])
        if str(person_id).strip()
    })
    mentions: list[tuple[str, str]] = []
    for person_id in normalized_ids:
        row = conn.execute(
            """
            SELECT name, lifecycle_status, deleted_at
            FROM persons WHERE person_id = ?
            """,
            (person_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown mentioned person: {person_id}")
        if person_id != owner_person_id and person_id not in (historical_person_ids or set()) and (
            row["lifecycle_status"] != "ACTIVE" or row["deleted_at"] is not None
        ):
            raise KeyError(f"Mentioned person is not active: {person_id}")
        mentions.append((person_id, str(row["name"])))
    return mentions


def _note_row(conn: sqlite3.Connection, note_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT n.*, r.revision_id, r.revision_number, r.content,
               r.actor, r.author_name, r.operation_id AS revision_operation_id,
               r.created_at AS revision_created_at
        FROM notes n
        JOIN note_revisions r ON r.note_id = n.note_id
        WHERE n.note_id = ?
          AND r.revision_number = (
              SELECT MAX(latest.revision_number)
              FROM note_revisions latest WHERE latest.note_id = n.note_id
          )
        """,
        (note_id,),
    ).fetchone()


def _note_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> Note:
    mention_rows = conn.execute(
        """
        SELECT referenced_person_id
        FROM note_revision_mentions
        WHERE revision_id = ?
        ORDER BY referenced_person_id
        """,
        (row["revision_id"],),
    ).fetchall()
    raw_mentioned_person_ids = tuple(str(item[0]) for item in mention_rows)
    effective_mentioned_person_ids = tuple(sorted({
        _resolve_canonical_person_id(conn, person_id)
        for person_id in raw_mentioned_person_ids
    }))
    return Note(
        note_id=str(row["note_id"]),
        owner_person_id=str(row["owner_person_id"]),
        status=str(row["status"]),
        content=str(row["content"]),
        revision_number=int(row["revision_number"]),
        mentioned_person_ids=raw_mentioned_person_ids,
        subject_type=str(row["subject_type"]),
        subject_id=str(row["subject_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        retired_at=row["retired_at"],
        canonical_owner_person_id=_resolve_canonical_person_id(conn, row["owner_person_id"]),
        effective_mentioned_person_ids=effective_mentioned_person_ids,
    )


def _insert_note_revision(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    revision_number: int,
    content: str,
    mentions: list[tuple[str, str]],
    actor: dict | None,
    author_name: str,
    operation_id: str | None,
    created_at: str,
) -> str:
    actor_snapshot, actor_payload, _ = _operation_actor_snapshot(actor)
    resolved_author = (
        author_name.strip()
        or str(actor_snapshot.get("display_name") or actor_snapshot.get("username") or "")
        or "SentriFace"
    )
    revision_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO note_revisions(
            revision_id, note_id, revision_number, content, actor,
            author_name, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            revision_id,
            note_id,
            revision_number,
            content,
            actor_payload,
            resolved_author,
            operation_id,
            created_at,
        ),
    )
    conn.executemany(
        """
        INSERT INTO note_revision_mentions(
            revision_id, referenced_person_id, display_name, created_at
        ) VALUES (?, ?, ?, ?)
        """,
        [
            (revision_id, person_id, display_name, created_at)
            for person_id, display_name in mentions
        ],
    )
    return revision_id


def _sync_note_reference_evidence(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    owner_person_id: str,
    revision_id: str,
    mentions: list[tuple[str, str]],
    operation_id: str,
    source: str | None,
    created_at: str,
) -> None:
    desired_ids = {
        person_id for person_id, _ in mentions if person_id != owner_person_id
    }
    active_rows = conn.execute(
        """
        SELECT mention_id, referenced_person_id
        FROM note_mentions
        WHERE note_id = ? AND active = 1
        ORDER BY referenced_person_id
        """,
        (note_id,),
    ).fetchall()
    active_by_person = {
        str(row["referenced_person_id"]): str(row["mention_id"])
        for row in active_rows
    }
    removed_ids = sorted(set(active_by_person) - desired_ids)
    for person_id in removed_ids:
        mention_id = active_by_person[person_id]
        conn.execute(
            """
            UPDATE note_mentions
            SET active = 0, retired_revision_id = ?, retired_operation_id = ?,
                retired_at = ?
            WHERE mention_id = ? AND active = 1
            """,
            (revision_id, operation_id, created_at, mention_id),
        )
        conn.execute(
            """
            UPDATE relationship_evidence
            SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
            WHERE evidence_type = 'NOTE_REFERENCE'
              AND source_entity_type = 'NOTE'
              AND source_entity_id = ? AND active = 1
            """,
            (operation_id, created_at, mention_id),
        )
    for person_id in sorted(desired_ids - set(active_by_person)):
        mention_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO note_mentions(
                mention_id, note_id, referenced_person_id, active,
                created_revision_id, created_operation_id, created_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (
                mention_id,
                note_id,
                person_id,
                revision_id,
                operation_id,
                created_at,
            ),
        )
        _insert_relationship_evidence(
            conn,
            evidence_type="NOTE_REFERENCE",
            source_entity_type="NOTE",
            source_entity_id=mention_id,
            source_person_id=owner_person_id,
            target_person_id=person_id,
            relationship_type="REFERENCES",
            directionality="DIRECTED",
            source=source,
            created_operation_id=operation_id,
            created_at=created_at,
        )


def _insert_unjournaled_profile_note(
    conn: sqlite3.Connection,
    person_id: str,
    content: str,
    created_at: str,
) -> None:
    if not content or conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notes'"
    ).fetchone() is None:
        return
    note_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO notes(
            note_id, owner_person_id, subject_type, subject_id, is_profile_note,
            status, created_at, updated_at
        ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?)
        """,
        (note_id, person_id, person_id, created_at, created_at),
    )
    _insert_note_revision(
        conn,
        note_id=note_id,
        revision_number=1,
        content=content,
        mentions=[],
        actor={"display_name": "SentriFace", "roles": []},
        author_name="SentriFace",
        operation_id=None,
        created_at=created_at,
    )


def _normalize_evidence_endpoints(
    source_person_id: str,
    target_person_id: str,
    directionality: str,
) -> tuple[str, str]:
    source = str(source_person_id).strip()
    target = str(target_person_id).strip()
    if not source or not target:
        raise ValueError("Relationship evidence requires two person IDs")
    if source == target:
        raise ValueError("Relationship evidence cannot reference the same raw person twice")
    if directionality == "UNDIRECTED":
        return tuple(sorted((source, target)))
    if directionality == "DIRECTED":
        return source, target
    raise ValueError(f"Unsupported evidence directionality: {directionality}")


def _insert_relationship_evidence(
    conn: sqlite3.Connection,
    *,
    evidence_type: str,
    source_entity_type: str,
    source_entity_id: str,
    source_person_id: str,
    target_person_id: str,
    relationship_type: str,
    directionality: str,
    source: str | None,
    created_operation_id: str,
    created_at: str,
    evidence_revision_id: str | None = None,
) -> str:
    normalized_source, normalized_target = _normalize_evidence_endpoints(
        source_person_id, target_person_id, directionality,
    )
    evidence_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "|".join((
            "sentriface",
            evidence_type,
            source_entity_id,
            evidence_revision_id or source_entity_id,
            normalized_source,
            normalized_target,
            relationship_type,
            directionality,
        )),
    ))
    conn.execute(
        """
        INSERT OR IGNORE INTO relationship_evidence(
            evidence_id, evidence_type, source_entity_type, source_entity_id,
            evidence_revision_id, source_person_id, target_person_id, relationship_type,
            directionality, active, source, created_operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            evidence_id,
            evidence_type,
            source_entity_type,
            source_entity_id,
            evidence_revision_id or source_entity_id,
            normalized_source,
            normalized_target,
            relationship_type,
            directionality,
            source,
            created_operation_id,
            created_at,
        ),
    )
    return evidence_id


def _relationship_evidence_from_row(row: sqlite3.Row) -> RelationshipEvidence:
    return RelationshipEvidence(
        evidence_id=row["evidence_id"],
        evidence_type=row["evidence_type"],
        source_entity_type=row["source_entity_type"],
        source_entity_id=row["source_entity_id"],
        evidence_revision_id=row["evidence_revision_id"],
        source_person_id=row["source_person_id"],
        target_person_id=row["target_person_id"],
        relationship_type=row["relationship_type"],
        directionality=row["directionality"],
        active=bool(row["active"]),
        source=row["source"],
        created_operation_id=row["created_operation_id"],
        created_at=row["created_at"],
        deactivated_operation_id=row["deactivated_operation_id"],
        deactivated_at=row["deactivated_at"],
    )


def _graph_connection_from_row(row: sqlite3.Row) -> GraphConnection:
    return GraphConnection(
        source_person_id=row["source_person_id"],
        target_person_id=row["target_person_id"],
        relationship_type=row["relationship_type"],
        directionality=row["directionality"],
        evidence_count=int(row["evidence_count"]),
        evidence_types=tuple(json.loads(row["evidence_types"])),
        last_evidence_at=row["last_evidence_at"],
    )


def _list_relationship_evidence_for_source(
    conn: sqlite3.Connection,
    evidence_type: str,
    source_entity_id: str,
) -> list[RelationshipEvidence]:
    rows = conn.execute(
        """
        SELECT * FROM relationship_evidence
        WHERE evidence_type = ? AND source_entity_id = ?
        ORDER BY source_person_id, target_person_id, evidence_id
        """,
        (evidence_type, source_entity_id),
    ).fetchall()
    return [_relationship_evidence_from_row(row) for row in rows]


def _expected_graph_connections(
    conn: sqlite3.Connection,
) -> tuple[list[GraphConnection], list[str], int]:
    errors: list[str] = []
    aggregates: dict[tuple[str, str, str, str], dict] = {}
    resolve_canonical = _batch_canonical_resolver(conn)
    co_observation_ids = {
        str(row[0]) for row in conn.execute(
            """
            SELECT DISTINCT source_entity_id
            FROM relationship_evidence
            WHERE evidence_type = 'CO_OBSERVED'
            """
        )
    }
    observation_statuses = {
        str(row["observation_id"]): str(row["status"])
        for row in conn.execute(
            "SELECT observation_id, status FROM observations ORDER BY observation_id"
        )
        if str(row["observation_id"]) in co_observation_ids
    }
    raw_participants: dict[str, set[str]] = {
        observation_id: set() for observation_id in co_observation_ids
    }
    for row in conn.execute(
        """
        SELECT observation_id, person_id
        FROM observation_participants
        ORDER BY observation_id, person_id
        """
    ):
        observation_id = str(row["observation_id"])
        if observation_id in raw_participants:
            raw_participants[observation_id].add(str(row["person_id"]))
    effective_participants, participant_errors = (
        _batch_effective_observation_person_ids(
            conn, co_observation_ids, raw_participants, resolve_canonical,
        )
    )
    errors.extend(participant_errors)
    note_mentions = {
        str(row["mention_id"]): row
        for row in conn.execute(
            """
            SELECT m.mention_id, m.referenced_person_id, m.active,
                   n.owner_person_id, n.status
            FROM note_mentions m
            JOIN notes n ON n.note_id = m.note_id
            ORDER BY m.mention_id
            """
        )
    }
    note_reference_state: dict[str, dict[str, int]] = {
        mention_id: {"active": 0, "matching_active": 0}
        for mention_id in note_mentions
    }
    active_evidence_count = 0
    for row in conn.execute(
        "SELECT * FROM relationship_evidence ORDER BY created_at, evidence_id"
    ):
        evidence_id = str(row["evidence_id"])
        active_shape = (
            bool(row["active"])
            and row["deactivated_operation_id"] is None
            and row["deactivated_at"] is None
        )
        retired_shape = (
            not bool(row["active"])
            and row["deactivated_operation_id"] is not None
            and row["deactivated_at"] is not None
        )
        if not (active_shape or retired_shape):
            errors.append(
                f"Evidence {evidence_id} has invalid active/deactivation provenance"
            )
        if row["evidence_type"] == "CO_OBSERVED":
            observation_id = str(row["source_entity_id"])
            observation_status = observation_statuses.get(observation_id)
            if observation_status is None:
                errors.append(f"Evidence {evidence_id} has a missing observation source")
            elif observation_status != "FINALIZED":
                errors.append(f"Evidence {evidence_id} references a non-finalized observation")
            raw_participant_ids = raw_participants.get(observation_id, set())
            effective_participant_ids = effective_participants.get(observation_id, set())
            endpoints_valid = True
            for endpoint in (row["source_person_id"], row["target_person_id"]):
                endpoint_id = str(endpoint)
                if endpoint_id in raw_participant_ids:
                    continue
                try:
                    effective_endpoint = resolve_canonical(endpoint_id)
                except (KeyError, RuntimeError, ValueError):
                    endpoints_valid = False
                    break
                if effective_endpoint not in effective_participant_ids:
                    endpoints_valid = False
                    break
            if not endpoints_valid:
                errors.append(f"Evidence {evidence_id} endpoints are not observation participants")
        elif row["evidence_type"] == "NOTE_REFERENCE":
            mention_id = str(row["source_entity_id"])
            mention = note_mentions.get(mention_id)
            if mention is None:
                errors.append(f"Evidence {evidence_id} has a missing note mention source")
            else:
                state = note_reference_state[mention_id]
                if bool(row["active"]):
                    state["active"] = int(state["active"]) + 1
                if (
                    row["source_person_id"] != mention["owner_person_id"]
                    or row["target_person_id"] != mention["referenced_person_id"]
                ):
                    errors.append(f"Evidence {evidence_id} endpoints do not match its note mention")
                matching_shape = (
                    row["source_person_id"] == mention["owner_person_id"]
                    and row["target_person_id"] == mention["referenced_person_id"]
                    and row["relationship_type"] == "REFERENCES"
                    and row["directionality"] == "DIRECTED"
                )
                if bool(row["active"]) and matching_shape:
                    state["matching_active"] = int(state["matching_active"]) + 1
                if row["relationship_type"] != "REFERENCES":
                    errors.append(
                        f"Evidence {evidence_id} has an invalid NOTE_REFERENCE relationship type"
                    )
                if row["directionality"] != "DIRECTED":
                    errors.append(
                        f"Evidence {evidence_id} has invalid NOTE_REFERENCE directionality"
                    )
                if bool(row["active"]) and not (
                    bool(mention["active"])
                    and mention["status"] == "ACTIVE"
                ):
                    errors.append(
                        f"Evidence {evidence_id} has no current active note mention source"
                    )
        if not bool(row["active"]):
            continue
        active_evidence_count += 1
        try:
            source_person_id = resolve_canonical(str(row["source_person_id"]))
            target_person_id = resolve_canonical(str(row["target_person_id"]))
        except (KeyError, RuntimeError, ValueError) as exc:
            errors.append(f"Evidence {evidence_id} has invalid canonical endpoints: {exc}")
            continue
        if source_person_id == target_person_id:
            continue
        if row["directionality"] == "UNDIRECTED":
            source_person_id, target_person_id = sorted((source_person_id, target_person_id))
        key = (
            source_person_id,
            target_person_id,
            str(row["relationship_type"]),
            str(row["directionality"]),
        )
        aggregate = aggregates.setdefault(key, {
            "count": 0,
            "types": set(),
            "last": str(row["created_at"]),
        })
        aggregate["count"] += 1
        aggregate["types"].add(str(row["evidence_type"]))
        aggregate["last"] = max(aggregate["last"], str(row["created_at"]))
    for mention_id, mention in sorted(note_mentions.items()):
        state = note_reference_state[mention_id]
        expected_active = 1 if (
            bool(mention["active"])
            and mention["status"] == "ACTIVE"
            and mention["owner_person_id"] != mention["referenced_person_id"]
        ) else 0
        actual_active = int(state["active"])
        matching_active = int(state["matching_active"])
        if actual_active != expected_active or matching_active != expected_active:
            errors.append(
                "NOTE_REFERENCE current active cardinality disagrees for mention "
                f"{mention_id}: expected {expected_active}, matching {matching_active}, "
                f"all active {actual_active}"
            )
    connections = [
        GraphConnection(
            source_person_id=key[0],
            target_person_id=key[1],
            relationship_type=key[2],
            directionality=key[3],
            evidence_count=int(value["count"]),
            evidence_types=tuple(sorted(value["types"])),
            last_evidence_at=str(value["last"]),
        )
        for key, value in sorted(aggregates.items())
    ]
    return connections, errors, active_evidence_count


def _batch_canonical_resolver(conn: sqlite3.Connection) -> Callable[[str], str]:
    people = {
        str(row["person_id"]): (
            str(row["lifecycle_status"]),
            str(row["canonical_person_id"]) if row["canonical_person_id"] else None,
        )
        for row in conn.execute(
            """
            SELECT person_id, lifecycle_status, canonical_person_id
            FROM persons ORDER BY person_id
            """
        )
    }
    cache: dict[str, str] = {}

    def resolve(person_id: str) -> str:
        normalized_id = str(person_id).strip()
        if not normalized_id:
            raise ValueError("Person ID is required")
        cached = cache.get(normalized_id)
        if cached is not None:
            return cached
        current_id = normalized_id
        path: list[str] = []
        visited: set[str] = set()
        while True:
            if current_id in visited:
                raise RuntimeError("Canonical identity cycle detected")
            visited.add(current_id)
            path.append(current_id)
            person = people.get(current_id)
            if person is None:
                if len(path) == 1:
                    raise KeyError(f"Unknown person: {current_id}")
                raise RuntimeError(
                    f"Canonical identity target does not exist: {current_id}"
                )
            lifecycle_status, target_id = person
            if lifecycle_status != "MERGED":
                if target_id is not None:
                    raise RuntimeError(
                        "Non-merged identity has an invalid canonical mapping"
                    )
                for path_id in path:
                    cache[path_id] = current_id
                return current_id
            if target_id is None:
                raise RuntimeError("Merged identity has no canonical target")
            current_id = target_id

    return resolve


def _batch_effective_observation_person_ids(
    conn: sqlite3.Connection,
    observation_ids: set[str],
    raw_participants: dict[str, set[str]],
    resolve_canonical: Callable[[str], str],
) -> tuple[dict[str, set[str]], list[str]]:
    if not observation_ids:
        return {}, []
    assignment_current: dict[str, str] = {}
    assignment_originals: dict[str, set[str]] = {
        observation_id: set() for observation_id in observation_ids
    }
    assignment_observation: dict[str, str] = {}
    for row in conn.execute(
        """
        SELECT assignment_id, observation_id, original_person_id
        FROM observation_face_assignments
        ORDER BY observation_id, assignment_id
        """
    ):
        observation_id = str(row["observation_id"])
        if observation_id not in observation_ids:
            continue
        assignment_id = str(row["assignment_id"])
        original_person_id = str(row["original_person_id"])
        assignment_observation[assignment_id] = observation_id
        assignment_current[assignment_id] = original_person_id
        assignment_originals[observation_id].add(original_person_id)
    observation_corrections: dict[str, list[tuple[str, str]]] = {
        observation_id: [] for observation_id in observation_ids
    }
    for row in conn.execute(
        """
        SELECT correction_type, observation_id, face_assignment_id,
               from_person_id, to_person_id
        FROM identity_corrections
        ORDER BY created_at, rowid, correction_id
        """
    ):
        correction_type = str(row["correction_type"])
        if correction_type == "FACE_ASSIGNMENT" and row["face_assignment_id"]:
            assignment_id = str(row["face_assignment_id"])
            if assignment_id in assignment_current:
                assignment_current[assignment_id] = str(row["to_person_id"])
        elif correction_type == "OBSERVATION_IDENTITY" and row["observation_id"]:
            observation_id = str(row["observation_id"])
            if observation_id in observation_corrections:
                observation_corrections[observation_id].append((
                    str(row["from_person_id"]), str(row["to_person_id"]),
                ))
    assignment_effective: dict[str, set[str]] = {
        observation_id: set() for observation_id in observation_ids
    }
    for assignment_id, person_id in assignment_current.items():
        assignment_effective[assignment_observation[assignment_id]].add(person_id)
    result: dict[str, set[str]] = {}
    errors: list[str] = []
    for observation_id in sorted(observation_ids):
        current = (
            set(raw_participants.get(observation_id, set()))
            - assignment_originals[observation_id]
        )
        current.update(assignment_effective[observation_id])
        for from_person_id, to_person_id in observation_corrections[observation_id]:
            if from_person_id not in current:
                errors.append(
                    f"Observation {observation_id} correction source "
                    f"{from_person_id} is not a current participant"
                )
                continue
            current.remove(from_person_id)
            current.add(to_person_id)
        effective: set[str] = set()
        for person_id in sorted(current):
            try:
                effective.add(resolve_canonical(person_id))
            except (KeyError, RuntimeError, ValueError) as exc:
                errors.append(
                    f"Observation {observation_id} participant {person_id} "
                    f"cannot resolve: {exc}"
                )
        result[observation_id] = effective
    return result, errors


def _replace_graph_projection(conn: sqlite3.Connection) -> None:
    connections, errors, _ = _expected_graph_connections(conn)
    if errors:
        raise RuntimeError("Relationship evidence validation failed: " + "; ".join(errors))
    _write_graph_projection(conn, connections)
    _advance_graph_revision(conn)


def _graph_connection_signature(item: GraphConnection) -> tuple:
    return (
        item.source_person_id,
        item.target_person_id,
        item.relationship_type,
        item.directionality,
        item.evidence_count,
        tuple(sorted(item.evidence_types)),
        item.last_evidence_at,
    )


def _graph_connection_row_signature(row: sqlite3.Row) -> tuple:
    try:
        evidence_types_value = json.loads(row["evidence_types"])
        if not isinstance(evidence_types_value, list):
            raise ValueError("evidence_types must be a JSON list")
        evidence_types = tuple(sorted(str(item) for item in evidence_types_value))
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence_types = ("<invalid-json>", str(row["evidence_types"]))
    return (
        str(row["source_person_id"]),
        str(row["target_person_id"]),
        str(row["relationship_type"]),
        str(row["directionality"]),
        row["evidence_count"],
        evidence_types,
        str(row["last_evidence_at"]),
    )


def _write_graph_projection(
    conn: sqlite3.Connection, connections: list[GraphConnection],
) -> None:
    conn.execute("DELETE FROM graph_connections")
    _insert_graph_projection_rows(conn, connections)


def _insert_graph_projection_rows(
    conn: sqlite3.Connection, connections: list[GraphConnection],
) -> None:
    conn.executemany(
        """
        INSERT INTO graph_connections(
            source_person_id, target_person_id, relationship_type, directionality,
            evidence_count, evidence_types, last_evidence_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.source_person_id,
                item.target_person_id,
                item.relationship_type,
                item.directionality,
                item.evidence_count,
                json.dumps(item.evidence_types, separators=(",", ":")),
                item.last_evidence_at,
            )
            for item in connections
        ],
    )


def _graph_revision_token(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT revision FROM graph_state WHERE singleton_id = 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("Graph revision state is unavailable")
    return f"g{int(row['revision'])}"


def _advance_graph_revision(conn: sqlite3.Connection) -> None:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'graph_state'"
    ).fetchone()
    if table_exists is None:
        return
    cursor = conn.execute(
        """
        UPDATE graph_state
        SET revision = revision + 1, updated_at = ?
        WHERE singleton_id = 1
        """,
        (utc_now(),),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Graph revision state is unavailable")


def _normalize_graph_filters(filters: GraphReadFilter | None) -> GraphReadFilter:
    value = filters or GraphReadFilter()

    def choices(items: tuple[str, ...], *, upper: bool = False) -> tuple[str, ...]:
        normalized = {
            (str(item).strip().upper() if upper else str(item).strip())
            for item in items
            if str(item).strip()
        }
        return tuple(sorted(normalized, key=str.casefold))

    date_from = _optional_text(value.date_from)
    date_to = _optional_text(value.date_to)
    start = _graph_filter_datetime(date_from, end_of_day=False) if date_from else None
    end = _graph_filter_datetime(date_to, end_of_day=True) if date_to else None
    if start and end and start > end:
        raise ValueError("Graph date_from must be earlier than or equal to date_to")
    lifecycle = choices(value.lifecycle, upper=True)
    unsupported = set(lifecycle) - PERSON_LIFECYCLE_STATUSES
    if unsupported:
        raise ValueError(f"Unsupported graph lifecycle filter: {sorted(unsupported)[0]}")
    min_frequency = value.min_frequency
    if min_frequency is not None and float(min_frequency) < 0:
        raise ValueError("Graph minimum frequency cannot be negative")
    min_strength = value.min_relationship_strength
    if min_strength is not None and int(min_strength) < 1:
        raise ValueError("Graph minimum relationship strength must be at least 1")
    return GraphReadFilter(
        date_from=date_from,
        date_to=date_to,
        location=_optional_text(value.location),
        lifecycle=lifecycle,
        country=choices(value.country),
        rank=choices(value.rank),
        priority=choices(value.priority),
        min_frequency=float(min_frequency) if min_frequency is not None else None,
        min_relationship_strength=int(min_strength) if min_strength is not None else None,
    )


def _graph_filter_datetime(value: str, *, end_of_day: bool) -> datetime:
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid graph date/time: {value}") from exc
    if len(text) == 10 and end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _graph_occurrence_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _graph_read_components(
    conn: sqlite3.Connection,
    filters: GraphReadFilter,
    *,
    always_include_person_id: str | None = None,
) -> tuple[dict[str, GraphReadNode], tuple[GraphReadEdge, ...]]:
    canonical_ids: set[str] = set()
    aliases: dict[str, list[str]] = {}
    for row in conn.execute("SELECT person_id FROM persons ORDER BY person_id").fetchall():
        raw_id = str(row["person_id"])
        canonical_id = _resolve_canonical_person_id(conn, raw_id)
        canonical_ids.add(canonical_id)
        if raw_id != canonical_id:
            aliases.setdefault(canonical_id, []).append(raw_id)

    all_nodes = {
        person_id: _graph_read_node(
            conn, person_id, historical_person_ids=tuple(sorted(aliases.get(person_id, []))),
        )
        for person_id in sorted(canonical_ids)
    }
    nodes = {
        person_id: node
        for person_id, node in all_nodes.items()
        if person_id == always_include_person_id or _graph_node_matches(node, filters)
    }

    start = (
        _graph_filter_datetime(filters.date_from, end_of_day=False)
        if filters.date_from else None
    )
    end = (
        _graph_filter_datetime(filters.date_to, end_of_day=True)
        if filters.date_to else None
    )
    observations = {
        str(row["observation_id"]): row
        for row in conn.execute(
            "SELECT observation_id, status, observed_at, created_at, location FROM observations"
        ).fetchall()
    }
    scoped_people: set[str] = set()
    if start or end or filters.location:
        for observation_id, observation in observations.items():
            if observation["status"] != "FINALIZED":
                continue
            occurrence_at = str(observation["observed_at"] or observation["created_at"])
            if not _graph_time_matches(occurrence_at, start, end):
                continue
            if filters.location and str(observation["location"] or "").casefold() != filters.location.casefold():
                continue
            scoped_people.update(_effective_observation_person_ids(conn, observation_id))

    aggregates: dict[tuple[str, str], dict[str, object]] = {}
    evidence_rows = conn.execute(
        "SELECT * FROM relationship_evidence WHERE active = 1 ORDER BY created_at, evidence_id"
    ).fetchall()
    for row in evidence_rows:
        observation = (
            observations.get(str(row["source_entity_id"]))
            if row["evidence_type"] == "CO_OBSERVED"
            and row["source_entity_type"] == "OBSERVATION"
            else None
        )
        occurrence_at = str(
            (observation["observed_at"] or observation["created_at"])
            if observation is not None else row["created_at"]
        )
        if not _graph_time_matches(occurrence_at, start, end):
            continue
        if filters.location:
            if observation is None:
                continue
            if str(observation["location"] or "").casefold() != filters.location.casefold():
                continue
        source_id = _resolve_canonical_person_id(conn, str(row["source_person_id"]))
        target_id = _resolve_canonical_person_id(conn, str(row["target_person_id"]))
        if source_id == target_id:
            continue
        pair = tuple(sorted((source_id, target_id)))
        aggregate = aggregates.setdefault(pair, {
            "items": [], "types": {}, "relationships": {}, "sources": set(),
            "directions": {}, "first": occurrence_at, "last": occurrence_at,
        })
        aggregate["items"].append(row)
        evidence_type = str(row["evidence_type"])
        aggregate["types"][evidence_type] = aggregate["types"].get(evidence_type, 0) + 1
        relationship_type = str(row["relationship_type"])
        aggregate["relationships"][relationship_type] = (
            aggregate["relationships"].get(relationship_type, 0) + 1
        )
        aggregate["sources"].add((str(row["source_entity_type"]), str(row["source_entity_id"])))
        direction_key = (
            "UNDIRECTED" if row["directionality"] == "UNDIRECTED"
            else f"{source_id}->{target_id}"
        )
        aggregate["directions"][direction_key] = aggregate["directions"].get(direction_key, 0) + 1
        if _graph_occurrence_datetime(occurrence_at) < _graph_occurrence_datetime(str(aggregate["first"])):
            aggregate["first"] = occurrence_at
        if _graph_occurrence_datetime(occurrence_at) > _graph_occurrence_datetime(str(aggregate["last"])):
            aggregate["last"] = occurrence_at
        scoped_people.update((source_id, target_id))

    if start or end or filters.location:
        nodes = {
            person_id: node for person_id, node in nodes.items()
            if person_id == always_include_person_id or person_id in scoped_people
        }

    edges: list[GraphReadEdge] = []
    for pair, aggregate in sorted(aggregates.items()):
        if pair[0] not in nodes or pair[1] not in nodes:
            continue
        evidence_count = len(aggregate["items"])
        if (
            filters.min_relationship_strength is not None
            and evidence_count < filters.min_relationship_strength
        ):
            continue
        directions = aggregate["directions"]
        if set(directions) == {"UNDIRECTED"}:
            source_id, target_id = pair
            directionality = "UNDIRECTED"
        elif len(directions) == 1 and "UNDIRECTED" not in directions:
            source_id, target_id = next(iter(directions)).split("->", 1)
            directionality = "DIRECTED"
        else:
            source_id, target_id = pair
            directionality = "MIXED"
        evidence_types = tuple(sorted(aggregate["types"]))
        relationship_types = tuple(sorted(aggregate["relationships"]))
        edges.append(GraphReadEdge(
            source_person_id=source_id,
            target_person_id=target_id,
            connected_person_id=None,
            canonical_source_person_id=source_id,
            canonical_target_person_id=target_id,
            relationship_strength=evidence_count,
            evidence_count=evidence_count,
            evidence_types=evidence_types,
            first_occurrence_at=str(aggregate["first"]),
            last_occurrence_at=str(aggregate["last"]),
            directionality=directionality,
            relationship_types=relationship_types,
            relationship_type_summary=(
                relationship_types[0] if len(relationship_types) == 1 else "MULTIPLE"
            ),
            strength_basis="active_authoritative_evidence_count",
            provenance_summary={
                "evidence_type_counts": dict(sorted(aggregate["types"].items())),
                "relationship_type_counts": dict(sorted(aggregate["relationships"].items())),
                "source_record_count": len(aggregate["sources"]),
                "direction_counts": dict(sorted(directions.items())),
            },
        ))
    return nodes, tuple(edges)


def _graph_time_matches(
    value: str, start: datetime | None, end: datetime | None,
) -> bool:
    occurrence = _graph_occurrence_datetime(value)
    return not ((start and occurrence < start) or (end and occurrence > end))


def _graph_read_node(
    conn: sqlite3.Connection,
    person_id: str,
    *,
    historical_person_ids: tuple[str, ...] = (),
) -> GraphReadNode:
    row = conn.execute("SELECT * FROM persons WHERE person_id = ?", (person_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"Canonical graph person is unavailable: {person_id}")
    metadata = json.loads(row["metadata"] or "{}")
    sightings = _list_person_sightings(conn, person_id)
    presence = _presence_analytics(sightings)
    embedding_rows = conn.execute(
        "SELECT embedding_id, person_id, crop_path, source_image FROM embeddings WHERE deleted_at IS NULL"
    ).fetchall()
    effective_embeddings = [
        item for item in embedding_rows
        if _effective_embedding_owner_person_id(conn, item) == person_id
    ]
    representative_id = metadata.get("representative_embedding_id")
    representative = next((
        str(item["crop_path"] or item["source_image"])
        for item in effective_embeddings
        if item["embedding_id"] == representative_id and (item["crop_path"] or item["source_image"])
    ), None)
    if representative is None:
        representative = next((
            str(item["crop_path"] or item["source_image"])
            for item in effective_embeddings if item["crop_path"] or item["source_image"]
        ), None)
    lifecycle = str(row["lifecycle_status"])
    return GraphReadNode(
        person_id=person_id,
        canonical_person_id=person_id,
        display_name=str(row["name"]),
        lifecycle_status=lifecycle,
        biometric_status=str(row["biometric_status"]),
        representative_media_reference=representative,
        allowed_actions=_graph_allowed_actions(lifecycle),
        state_indicator="CURRENT" if lifecycle == "ACTIVE" else "HISTORICAL",
        historical_person_ids=historical_person_ids,
        summary_intelligence={
            "observation_count": presence.observation_count,
            "first_seen_at": presence.first_seen_at,
            "last_seen_at": presence.last_seen_at,
            "frequency_per_30_days": presence.frequency_per_30_days,
            "frequency_label": presence.frequency_label,
            "locations": [
                {"location": item.location, "count": item.count, "last_observed_at": item.last_observed_at}
                for item in presence.locations
            ],
            "country": metadata.get("country"),
            "rank": metadata.get("rank"),
            "priority": metadata.get("importance"),
        },
    )


def _graph_node_matches(node: GraphReadNode, filters: GraphReadFilter) -> bool:
    summary = node.summary_intelligence

    def matches(value: object, choices: tuple[str, ...]) -> bool:
        return not choices or str(value or "").casefold() in {item.casefold() for item in choices}

    return (
        (not filters.lifecycle or node.lifecycle_status in filters.lifecycle)
        and matches(summary.get("country"), filters.country)
        and matches(summary.get("rank"), filters.rank)
        and matches(summary.get("priority"), filters.priority)
        and (
            filters.min_frequency is None
            or float(summary.get("frequency_per_30_days") or 0) >= filters.min_frequency
        )
    )


def _graph_allowed_actions(lifecycle_status: str) -> tuple[str, ...]:
    return {
        "ACTIVE": (
            "OPEN", "EDIT", "EDIT_NOTES", "FAVORITE", "MANAGE_FACES",
            "ARCHIVE", "DELETE", "MERGE",
        ),
        "ARCHIVED": ("VIEW_HISTORY", "RESTORE", "DELETE"),
        "DELETED": ("VIEW_HISTORY",),
        "MERGED": ("VIEW_HISTORY", "OPEN_CANONICAL"),
    }.get(lifecycle_status, ("VIEW_HISTORY",))


_WORLD_FILTERS_VERSION = "world-filters-v1"
_WORLD_CLUSTER_VERSION = "connected-evidence-components-v1"
_WORLD_RANKING_VERSION = "descriptive-salience-v1"
_WORLD_CALCULATION_VERSION = "world-descriptive-v1"
_WORLD_RECENT_WINDOWS = {"LAST_7_DAYS": 7, "LAST_30_DAYS": 30, "LAST_90_DAYS": 90}
_WORLD_MAX_LIMITS = WorldReadLimits(
    people=100, clusters=50, events=100, evidence=100, media=100,
    relationships=200, patterns=25, provenance=200, facets=200,
)


def _world_graph_v2_read(
    conn: sqlite3.Connection, request: WorldGraphRequest,
) -> WorldGraphV2ReadModel:
    owns_snapshot = not conn.in_transaction
    if owns_snapshot:
        # The revision read is the first read in this deferred transaction. WAL
        # then keeps every later SELECT on the same snapshot while writers remain
        # free to commit on their own connections.
        conn.execute("BEGIN")
    try:
        result = _world_graph_v2_read_snapshot(conn, request)
    except Exception:
        if owns_snapshot:
            conn.rollback()
        raise
    if owns_snapshot:
        conn.commit()
    return result


def _world_graph_v2_read_snapshot(
    conn: sqlite3.Connection, request: WorldGraphRequest,
) -> WorldGraphV2ReadModel:
    revision = _graph_revision_token(conn)
    if request.revision is not None and request.revision != revision:
        raise ValueError("World revision is stale; request a new snapshot")
    cursor_as_of = _world_cursor_as_of(request.cursor)
    if request.as_of and cursor_as_of and _world_datetime(request.as_of, "as_of") != _world_datetime(cursor_as_of, "cursor as_of"):
        raise ValueError("World cursor does not match the requested as_of")
    as_of_dt = _world_datetime(request.as_of or cursor_as_of or utc_now(), "as_of")
    as_of = as_of_dt.isoformat()
    filters = _normalize_world_filters(request.filters, as_of_dt)
    limits = _normalize_world_limits(request.limits)
    level = WorldDetailLevel(request.detail_level)
    focus_type, focus_id = _normalize_world_focus(level, request.focus_type, request.focus_id)
    ranking = str(request.ranking or "SALIENCE").strip().upper()
    if ranking not in {"SALIENCE", "RECENT_ACTIVITY", "EVIDENCE_COUNT", "DISPLAY_NAME"}:
        raise ValueError(f"Unsupported World ranking intent: {ranking}")
    if ranking == "RECENT_ACTIVITY" and not (filters.recent_activity or filters.date_from or filters.date_to):
        raise ValueError("RECENT_ACTIVITY ranking requires an explicit recent or date scope")
    collection = _normalize_world_collection(level, request.collection)
    scope_fingerprint = _world_scope_fingerprint(filters, ranking, limits)
    offset = _world_decode_cursor(
        request.cursor, revision, level, focus_type, focus_id, collection,
        as_of, scope_fingerprint,
    )
    context = _WorldReadContext(
        request=request, revision=revision, as_of=as_of, filters=filters,
        limits=limits, level=level, focus_type=focus_type, focus_id=focus_id,
        collection=collection, ranking=ranking, scope_fingerprint=scope_fingerprint,
        offset=offset,
    )
    return {
        WorldDetailLevel.WORLD_SCOPE: _world_scope_read,
        WorldDetailLevel.CLUSTER: _world_cluster_read,
        WorldDetailLevel.PERSON: _world_person_read,
        WorldDetailLevel.EVENT: _world_event_read,
        WorldDetailLevel.EVIDENCE: _world_evidence_read,
    }[level](conn, context)


@dataclass(frozen=True)
class _WorldReadContext:
    request: WorldGraphRequest
    revision: str
    as_of: str
    filters: WorldReadFilter
    limits: WorldReadLimits
    level: WorldDetailLevel
    focus_type: str | None
    focus_id: str | None
    collection: WorldCollection
    ranking: str
    scope_fingerprint: str
    offset: int


def _normalize_world_collection(
    level: WorldDetailLevel, collection: WorldCollection | None,
) -> WorldCollection:
    defaults = {
        WorldDetailLevel.WORLD_SCOPE: WorldCollection.PEOPLE,
        WorldDetailLevel.CLUSTER: WorldCollection.MEMBERS,
        WorldDetailLevel.PERSON: WorldCollection.RELATIONSHIPS,
        WorldDetailLevel.EVENT: WorldCollection.PARTICIPANTS,
        WorldDetailLevel.EVIDENCE: WorldCollection.EVIDENCE,
    }
    allowed = {
        WorldDetailLevel.WORLD_SCOPE: {
            WorldCollection.PEOPLE, WorldCollection.CLUSTERS,
            WorldCollection.RELATIONSHIPS, WorldCollection.PATTERNS,
            WorldCollection.LOCATION_FACETS,
        },
        WorldDetailLevel.CLUSTER: {WorldCollection.MEMBERS, WorldCollection.RELATIONSHIPS},
        WorldDetailLevel.PERSON: {WorldCollection.RELATIONSHIPS, WorldCollection.EVENTS},
        WorldDetailLevel.EVENT: {
            WorldCollection.PARTICIPANTS, WorldCollection.PROVENANCE,
            WorldCollection.EVIDENCE, WorldCollection.MEDIA,
        },
        WorldDetailLevel.EVIDENCE: {WorldCollection.EVIDENCE, WorldCollection.MEDIA},
    }
    value = collection or defaults[level]
    if value not in allowed[level]:
        raise ValueError(f"Unsupported World collection {value.value} for {level.value}")
    return value


def _world_page_state(
    context: _WorldReadContext,
    collection: WorldCollection,
    total_count: int,
    returned_count: int,
    limit: int,
    *,
    offset: int | None = None,
) -> WorldPageState:
    page_offset = context.offset if offset is None else offset
    if collection != context.collection and returned_count == 0:
        return WorldPageState(
            collection=collection.value,
            total_count=total_count,
            returned_count=0,
            has_more=total_count > 0,
            next_cursor=None,
            truncated=total_count > 0,
            truncation_reason="collection_not_requested",
        )
    has_more = page_offset + returned_count < total_count
    truncation_reason = None
    if has_more:
        truncation_reason = f"backend_limit:{limit}"
    cursor = _world_token(
        "CURSOR", context.revision, context.level.value,
        context.focus_type, context.focus_id, page_offset + returned_count,
        collection=collection.value, as_of=context.as_of,
        scope=context.scope_fingerprint,
    ) if has_more else None
    return WorldPageState(
        collection=collection.value,
        total_count=total_count,
        returned_count=returned_count,
        has_more=has_more,
        next_cursor=cursor,
        truncated=has_more,
        truncation_reason=truncation_reason,
    )


def _world_result(
    context: _WorldReadContext,
    *,
    scope_totals: dict[str, int],
    pagination: dict[str, WorldPageState],
    available_facets: dict[str, object] | None = None,
    people: tuple[WorldPerson, ...] = (),
    clusters: tuple[WorldCluster, ...] = (),
    events: tuple[WorldEvent, ...] = (),
    evidence: tuple[WorldEvidence, ...] = (),
    relationships: tuple[WorldRelationship, ...] = (),
    patterns: tuple[WorldPattern, ...] = (),
    media: tuple[WorldMediaReference, ...] = (),
) -> WorldGraphV2ReadModel:
    primary = pagination.get(context.collection.value)
    returned_counts = {
        "people": len(people), "clusters": len(clusters), "events": len(events),
        "evidence": len(evidence), "relationships": len(relationships),
        "patterns": len(patterns), "media": len(media),
    }
    facets = {
        "filter_semantics_version": _WORLD_FILTERS_VERSION,
        "ranking_version": _WORLD_RANKING_VERSION,
        "clustering_version": _WORLD_CLUSTER_VERSION,
        "calculation_version": _WORLD_CALCULATION_VERSION,
        **(available_facets or {}),
    }
    return WorldGraphV2ReadModel(
        graph_revision=context.revision,
        as_of=context.as_of,
        generated_at=utc_now(),
        requested_detail_level=context.level,
        returned_detail_level=context.level,
        focus=(
            {"type": context.focus_type, "id": context.focus_id}
            if context.focus_type else None
        ),
        requested_filters=context.request.filters,
        effective_filters=context.filters,
        ranking=context.ranking,
        limits=context.limits,
        scope_totals=scope_totals,
        available_facets=facets,
        returned_counts=returned_counts,
        pagination=pagination,
        truncated=any(page.truncated for page in pagination.values()),
        has_more=primary.has_more if primary else False,
        next_cursor=primary.next_cursor if primary else None,
        expansion_tokens=(),
        people=people, clusters=clusters, events=events, evidence=evidence,
        relationships=relationships, patterns=patterns, media=media,
    )


def _world_scope_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    if context.collection == WorldCollection.LOCATION_FACETS:
        return _world_location_facets_read(conn, context)
    facet_offset = context.offset if context.collection == WorldCollection.LOCATION_FACETS else 0
    people_rows, aliases, canonical_map = _world_people_scope(conn, context.filters)
    relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
    )
    statistics = _world_event_statistics(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        location_offset=facet_offset, location_limit=context.limits.facets,
    )
    activity = statistics["activity"]
    if _world_has_event_scope(context.filters):
        related = {
            value for item in relationships
            for value in (item["source_person_id"], item["target_person_id"])
        }
        people_rows = {
            person_id: row for person_id, row in people_rows.items()
            if activity.get(person_id, 0) > 0 or person_id in related
        }
        relationships = [
            item for item in relationships
            if item["source_person_id"] in people_rows and item["target_person_id"] in people_rows
        ]
    if context.filters.activity:
        allowed = set(context.filters.activity)
        people_rows = {
            person_id: row for person_id, row in people_rows.items()
            if _world_activity_bucket(activity.get(person_id, 0)) in allowed
        }
        relationships = [
            item for item in relationships
            if item["source_person_id"] in people_rows and item["target_person_id"] in people_rows
        ]
        statistics = _world_event_statistics(
            conn, context.filters, set(people_rows), canonical_map=canonical_map,
            location_offset=facet_offset, location_limit=context.limits.facets,
        )
        activity = statistics["activity"]
    degree = _world_degree(people_rows, relationships)
    ordered_ids = _world_rank_people(people_rows, activity, degree, context.ranking)
    clusters_all = _world_clusters(
        context.revision, _world_filter_fingerprint(context.filters), relationships,
        people_rows, activity, min(context.limits.people, 10), context,
    )
    people: tuple[WorldPerson, ...] = ()
    clusters: tuple[WorldCluster, ...] = ()
    relationship_models: tuple[WorldRelationship, ...] = ()
    people_offset = context.offset if context.collection == WorldCollection.PEOPLE else 0
    cluster_offset = context.offset if context.collection == WorldCollection.CLUSTERS else 0
    if context.collection == WorldCollection.PEOPLE:
        page_ids = ordered_ids[people_offset:people_offset + context.limits.people]
        rank_positions = {person_id: index + 1 for index, person_id in enumerate(ordered_ids)}
        people = tuple(
            _world_person(
                person_id, people_rows[person_id], aliases.get(person_id, ()),
                activity.get(person_id, 0), degree.get(person_id, {}),
                context, rank_position=rank_positions[person_id],
            ) for person_id in page_ids
        )
    if context.collection == WorldCollection.CLUSTERS or (
        context.collection == WorldCollection.PEOPLE and context.offset == 0
    ):
        clusters = tuple(replace(item, member_ids=()) for item in clusters_all[
            cluster_offset:cluster_offset + context.limits.clusters
        ])
    relationship_offset = context.offset if context.collection == WorldCollection.RELATIONSHIPS else 0
    if context.collection == WorldCollection.RELATIONSHIPS:
        relationship_models = tuple(
            _world_relationship(item, context) for item in relationships[
                relationship_offset:relationship_offset + context.limits.relationships
            ]
        )
    pagination = {
        WorldCollection.PEOPLE.value: _world_page_state(
            context, WorldCollection.PEOPLE, len(ordered_ids), len(people),
            context.limits.people, offset=people_offset,
        ),
        WorldCollection.CLUSTERS.value: _world_page_state(
            context, WorldCollection.CLUSTERS, len(clusters_all), len(clusters),
            context.limits.clusters, offset=cluster_offset,
        ),
        WorldCollection.RELATIONSHIPS.value: _world_page_state(
            context, WorldCollection.RELATIONSHIPS, len(relationships),
            len(relationship_models), context.limits.relationships,
            offset=relationship_offset,
        ),
        WorldCollection.LOCATION_FACETS.value: _world_page_state(
            context, WorldCollection.LOCATION_FACETS,
            int(statistics["location_total_count"]),
            len(statistics["locations"]), context.limits.facets,
            offset=facet_offset,
        ),
    }
    eligible_ids = set(people_rows)
    event_count = int(statistics["total"])
    all_patterns = tuple(_world_patterns(
        conn, context.filters, len(people_rows), context.limits.patterns,
        eligible_person_ids=eligible_ids, context=context,
        measured_total=int(statistics["total"]),
        measured_missing=int(statistics["missing"]),
    ))
    patterns = all_patterns if context.offset == 0 else ()
    pattern_total = len(all_patterns)
    facets = _world_facets(
        conn, context.filters, people_rows, relationships, activity, eligible_ids,
        location_facets=statistics["locations"], pattern_count=pattern_total,
    )
    pagination[WorldCollection.PATTERNS.value] = _world_page_state(
        context, WorldCollection.PATTERNS, pattern_total, len(patterns),
        context.limits.patterns,
        offset=(context.offset if context.collection == WorldCollection.PATTERNS else 0),
    )
    return _world_result(
        context,
        scope_totals={
            "people": len(people_rows), "relationships": len(relationships),
            "clusters": len(clusters_all), "finalized_events": event_count,
        },
        pagination=pagination,
        available_facets=facets,
        people=people, clusters=clusters, patterns=patterns,
        relationships=relationship_models,
    )


def _world_location_facets_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    """Read the authoritative location collection without unrelated World models."""
    people_rows, _, canonical_map = _world_people_scope(conn, context.filters)
    eligible_ids = set(people_rows)
    if context.filters.activity:
        statistics = _world_event_statistics(
            conn, context.filters, eligible_ids, canonical_map=canonical_map,
            location_offset=context.offset, location_limit=context.limits.facets,
        )
        allowed = set(context.filters.activity)
        activity = statistics["activity"]
        eligible_ids = {
            person_id for person_id in eligible_ids
            if _world_activity_bucket(activity.get(person_id, 0)) in allowed
        }
        statistics = _world_event_statistics(
            conn, context.filters, eligible_ids, canonical_map=canonical_map,
            location_offset=context.offset, location_limit=context.limits.facets,
        )
    else:
        statistics = _world_location_facet_statistics(
            conn, context.filters, eligible_ids, canonical_map,
            context.offset, context.limits.facets,
        )
    pagination = {
        WorldCollection.LOCATION_FACETS.value: _world_page_state(
            context, WorldCollection.LOCATION_FACETS,
            int(statistics["location_total_count"]), len(statistics["locations"]),
            context.limits.facets, offset=context.offset,
        ),
    }
    return _world_result(
        context,
        scope_totals={"finalized_events": int(statistics["total"])},
        pagination=pagination,
        available_facets={"locations": statistics["locations"]},
    )


def _world_location_facet_statistics(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_ids: set[str],
    canonical_map: dict[str, str],
    offset: int,
    limit: int,
) -> dict[str, object]:
    """Page event-based locations without calculating unrelated activity models."""
    if not eligible_ids:
        return {"locations": [], "location_total_count": 0, "total": 0}
    if eligible_ids != set(canonical_map.values()):
        return _world_event_statistics(
            conn, filters, eligible_ids, canonical_map=canonical_map,
            location_offset=offset, location_limit=limit,
        )
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    rows = conn.execute(
        f"""WITH scoped_events AS (
                SELECT LOWER(TRIM(COALESCE(o.location, ''))) AS location_key,
                       TRIM(COALESCE(o.location, '')) AS display_location
                FROM observations o
                     INDEXED BY idx_observations_finalized_time_location
                WHERE {scope_sql}
                  AND EXISTS (
                      SELECT 1 FROM observation_participants p
                      WHERE p.observation_id = o.observation_id
                  )
            ), grouped AS (
                SELECT location_key,
                       CASE WHEN location_key = '' THEN 'MISSING'
                            ELSE MIN(display_location) END AS value,
                       COUNT(*) AS event_count
                FROM scoped_events
                GROUP BY location_key
            )
            SELECT value, event_count,
                   COUNT(*) OVER () AS facet_total_count,
                   SUM(event_count) OVER () AS event_total_count
            FROM grouped
            ORDER BY event_count DESC, LOWER(value)
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()
    if not rows:
        return {"locations": [], "location_total_count": 0, "total": 0}
    return {
        "locations": [
            {"value": str(row["value"]), "count": int(row["event_count"])}
            for row in rows
        ],
        "location_total_count": int(rows[0]["facet_total_count"]),
        "total": int(rows[0]["event_total_count"]),
    }


def _world_cluster_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    people_rows, aliases, canonical_map = _world_people_scope(conn, context.filters)
    relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
    )
    activity = _world_event_statistics(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        location_limit=1,
    )["activity"]
    clusters = _world_clusters(
        context.revision, _world_filter_fingerprint(context.filters), relationships,
        people_rows, activity, min(context.limits.people, 10), context,
    )
    cluster = next((item for item in clusters if item.cluster_id == context.focus_id), None)
    if cluster is None:
        raise KeyError("World cluster is unavailable in this revision and scope")
    members = tuple(cluster.member_ids)
    member_set = set(members)
    member_relationships = [
        item for item in relationships
        if item["source_person_id"] in member_set and item["target_person_id"] in member_set
    ]
    people: tuple[WorldPerson, ...] = ()
    relationship_models: tuple[WorldRelationship, ...] = ()
    if context.collection == WorldCollection.MEMBERS:
        ids = members[context.offset:context.offset + context.limits.people]
        degree = _world_degree(people_rows, member_relationships)
        people = tuple(
            _world_person(
                person_id, people_rows[person_id], aliases.get(person_id, ()),
                activity.get(person_id, 0), degree.get(person_id, {}), context,
                selected_by_focus=True,
            ) for person_id in ids
        )
        cluster_out = replace(
            cluster, member_ids=ids,
            member_preview=tuple({
                "canonical_person_id": person_id,
                "display_name": str(people_rows[person_id]["name"]),
            } for person_id in ids),
        )
    else:
        rows = member_relationships[
            context.offset:context.offset + context.limits.relationships
        ]
        relationship_models = tuple(_world_relationship(item, context) for item in rows)
        cluster_out = replace(cluster, member_ids=())
    pagination = {
        WorldCollection.MEMBERS.value: _world_page_state(
            context, WorldCollection.MEMBERS, len(members), len(people),
            context.limits.people,
            offset=(context.offset if context.collection == WorldCollection.MEMBERS else 0),
        ),
        WorldCollection.RELATIONSHIPS.value: _world_page_state(
            context, WorldCollection.RELATIONSHIPS, len(member_relationships),
            len(relationship_models), context.limits.relationships,
            offset=(context.offset if context.collection == WorldCollection.RELATIONSHIPS else 0),
        ),
    }
    return _world_result(
        context,
        scope_totals={
            "people": cluster.member_count,
            "relationships": len(member_relationships), "clusters": 1,
            "finalized_events": _world_scoped_event_count(
                conn, context.filters, member_set, canonical_map=canonical_map,
            ),
        },
        pagination=pagination,
        people=people, clusters=(cluster_out,), relationships=relationship_models,
    )


def _world_person_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    people_rows, aliases, canonical_map = _world_people_scope(conn, context.filters)
    canonical_id = canonical_map.get(str(context.focus_id))
    if canonical_id not in people_rows:
        raise KeyError("World person is unavailable in the effective scope")
    relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        focus_person_id=canonical_id,
    )
    all_relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
    )
    memberships = tuple({
        "cluster_id": cluster.cluster_id,
        "graph_revision": cluster.graph_revision,
        "member_count": cluster.member_count,
        "grouping_algorithm": cluster.grouping_algorithm,
        "algorithm_version": cluster.algorithm_version,
    } for cluster in _world_clusters(
        context.revision, _world_filter_fingerprint(context.filters),
        all_relationships, people_rows, {},
        min(context.limits.people, 10), context,
    ) if canonical_id in cluster.member_ids)
    event_total = _world_person_event_count(
        conn, canonical_id, context.filters, canonical_map=canonical_map,
    )
    activity = {canonical_id: event_total}
    degree = _world_degree({canonical_id: people_rows[canonical_id]}, relationships)
    root = replace(_world_person(
        canonical_id, people_rows[canonical_id], aliases.get(canonical_id, ()),
        activity.get(canonical_id, 0), degree.get(canonical_id, {}), context,
        selected_by_focus=True,
    ), cluster_memberships=memberships)
    relationship_models: tuple[WorldRelationship, ...] = ()
    events: tuple[WorldEvent, ...] = ()
    people = (root,)
    if context.collection == WorldCollection.RELATIONSHIPS:
        page_rows = relationships[
            context.offset:context.offset + context.limits.relationships
        ]
        relationship_models = tuple(_world_relationship(item, context) for item in page_rows)
        neighbor_ids = {
            item["target_person_id"] if item["source_person_id"] == canonical_id
            else item["source_person_id"] for item in page_rows
        }
        people += tuple(
            _world_person(
                person_id, people_rows[person_id], aliases.get(person_id, ()), None,
                None, context, selected_by_focus=True,
            ) for person_id in sorted(neighbor_ids) if person_id in people_rows
        )
    else:
        _, event_rows = _world_person_events(
            conn, canonical_id, context.filters, context.offset, context.limits.events,
            canonical_map=canonical_map, known_total=event_total,
        )
        batch = _world_event_batch_data(conn, event_rows, canonical_map)
        events = tuple(_world_event_from_row(
            conn, row, participant_offset=0,
            participant_limit=0, provenance_offset=0, provenance_limit=0,
            context=context,
            prepared=batch[str(row["observation_id"])],
        ) for row in event_rows)
    pagination = {
        WorldCollection.RELATIONSHIPS.value: _world_page_state(
            context, WorldCollection.RELATIONSHIPS, len(relationships),
            len(relationship_models), context.limits.relationships,
            offset=(context.offset if context.collection == WorldCollection.RELATIONSHIPS else 0),
        ),
        WorldCollection.EVENTS.value: _world_page_state(
            context, WorldCollection.EVENTS, event_total, len(events),
            context.limits.events,
            offset=(context.offset if context.collection == WorldCollection.EVENTS else 0),
        ),
    }
    return _world_result(
        context,
        scope_totals={
            "people": 1, "relationships": len(relationships),
            "clusters": 0, "finalized_events": event_total,
        },
        pagination=pagination, people=people, events=events,
        relationships=relationship_models,
    )


def _world_event_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    row = _world_event_row(conn, str(context.focus_id), context.filters)
    participant_mapping = _world_event_participant_mapping(conn, str(context.focus_id))
    participant_total = len(participant_mapping[0])
    provenance_total = len(participant_mapping[1])
    evidence_summary = _world_event_evidence_summary(conn, str(context.focus_id))
    evidence_total = _world_event_evidence_count(conn, str(context.focus_id), context.filters)
    media_total = _world_event_media_count(conn, str(context.focus_id))
    participant_offset = context.offset if context.collection == WorldCollection.PARTICIPANTS else 0
    provenance_offset = context.offset if context.collection == WorldCollection.PROVENANCE else 0
    event = _world_event_from_row(
        conn, row, participant_offset=participant_offset,
        participant_limit=(context.limits.people if context.collection == WorldCollection.PARTICIPANTS else 0),
        provenance_offset=provenance_offset,
        provenance_limit=(context.limits.provenance if context.collection == WorldCollection.PROVENANCE else 0),
        context=context,
        prepared=(participant_mapping, evidence_summary, media_total),
    )
    evidence: tuple[WorldEvidence, ...] = ()
    media: tuple[WorldMediaReference, ...] = ()
    if context.collection == WorldCollection.EVIDENCE:
        _, items = _world_evidence_page(
            conn, context.filters, "EVENT", context.focus_id,
            context.offset, context.limits.evidence,
        )
        evidence = tuple(items)
    elif context.collection == WorldCollection.MEDIA:
        _, media = _world_event_media_page(
            conn, str(context.focus_id), context.offset, context.limits.media,
        )
    pagination = {
        WorldCollection.PARTICIPANTS.value: _world_page_state(
            context, WorldCollection.PARTICIPANTS, participant_total,
            len(event.participants), context.limits.people,
            offset=participant_offset,
        ),
        WorldCollection.PROVENANCE.value: _world_page_state(
            context, WorldCollection.PROVENANCE, provenance_total,
            len(event.participant_provenance), context.limits.provenance,
            offset=provenance_offset,
        ),
        WorldCollection.EVIDENCE.value: _world_page_state(
            context, WorldCollection.EVIDENCE, evidence_total, len(evidence),
            context.limits.evidence,
            offset=(context.offset if context.collection == WorldCollection.EVIDENCE else 0),
        ),
        WorldCollection.MEDIA.value: _world_page_state(
            context, WorldCollection.MEDIA, media_total, len(media),
            context.limits.media,
            offset=(context.offset if context.collection == WorldCollection.MEDIA else 0),
        ),
    }
    return _world_result(
        context,
        scope_totals={
            "people": participant_total, "relationships": 0, "clusters": 0,
            "finalized_events": 1, "evidence": evidence_total, "media": media_total,
        },
        pagination=pagination, events=(event,), evidence=evidence, media=media,
    )


def _world_evidence_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    evidence: tuple[WorldEvidence, ...] = ()
    media: tuple[WorldMediaReference, ...] = ()
    if context.collection == WorldCollection.MEDIA:
        if context.focus_type != "EVIDENCE":
            raise ValueError("EVIDENCE media requires an EVIDENCE focus")
        evidence_total, detail = _world_evidence_page(
            conn, context.filters, "EVIDENCE", context.focus_id, 0, 1,
        )
        if evidence_total != 1 or not detail:
            raise KeyError("World evidence is unavailable in the effective scope")
        evidence = tuple(detail)
        item = detail[0]
        reference = item.supporting_references[0]
        if item.evidence_type == "CO_OBSERVED" and reference["source_entity_type"] == "OBSERVATION":
            media_total, media = _world_event_media_page(
                conn, str(reference["source_entity_id"]), context.offset,
                context.limits.media, supporting_evidence_id=item.evidence_id,
            )
        else:
            media_total = 0
        total = 1
    else:
        total, items = _world_evidence_page(
            conn, context.filters, context.focus_type, context.focus_id,
            context.offset, context.limits.evidence,
        )
        evidence = tuple(items)
        media_total = 0
    pagination = {
        WorldCollection.EVIDENCE.value: _world_page_state(
            context, WorldCollection.EVIDENCE, total, len(evidence),
            context.limits.evidence,
            offset=(context.offset if context.collection == WorldCollection.EVIDENCE else 0),
        ),
        WorldCollection.MEDIA.value: _world_page_state(
            context, WorldCollection.MEDIA, media_total, len(media),
            context.limits.media,
            offset=(context.offset if context.collection == WorldCollection.MEDIA else 0),
        ),
    }
    return _world_result(
        context, scope_totals={"evidence": total, "media": media_total},
        pagination=pagination, evidence=evidence, media=media,
    )


def _world_has_event_scope(filters: WorldReadFilter) -> bool:
    return bool(
        filters.date_from or filters.date_to or filters.locations
        or filters.missing_location != "INCLUDE"
    )


def _world_degree(
    people_rows: dict[str, sqlite3.Row], relationships: list[dict],
) -> dict[str, dict[str, int]]:
    degree = {
        person_id: {"relationships": 0, "evidence": 0} for person_id in people_rows
    }
    for item in relationships:
        for person_id in (item["source_person_id"], item["target_person_id"]):
            if person_id in degree:
                degree[person_id]["relationships"] += 1
                degree[person_id]["evidence"] += int(item["evidence_count"])
    return degree


def _world_explanation_scope(context: _WorldReadContext) -> dict[str, object]:
    return {
        "as_of": context.as_of,
        "date_from": context.filters.date_from,
        "date_to": context.filters.date_to,
        "recent_activity": context.filters.recent_activity,
        "locations": list(context.filters.locations),
        "missing_location": context.filters.missing_location,
        "filter_semantics_version": _WORLD_FILTERS_VERSION,
    }


def _normalize_world_limits(value: WorldReadLimits) -> WorldReadLimits:
    values = {}
    for name in WorldReadLimits.__dataclass_fields__:
        requested = int(getattr(value, name))
        if requested < 1:
            raise ValueError(f"World {name} limit must be at least 1")
        values[name] = min(requested, int(getattr(_WORLD_MAX_LIMITS, name)))
    return WorldReadLimits(**values)


def _world_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid World {label}: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_world_filters(value: WorldReadFilter, as_of: datetime) -> WorldReadFilter:
    def choices(items: tuple[str, ...], *, upper: bool = False) -> tuple[str, ...]:
        result = {(str(item).strip().upper() if upper else str(item).strip()) for item in items if str(item).strip()}
        return tuple(sorted(result, key=str.casefold))

    recent = _optional_text(value.recent_activity)
    if recent:
        recent = recent.upper()
        if recent not in _WORLD_RECENT_WINDOWS:
            raise ValueError(f"Unsupported recent activity preset: {recent}")
        if value.date_from or value.date_to:
            raise ValueError("Recent activity cannot be combined with absolute World dates")
        date_from = (as_of - timedelta(days=_WORLD_RECENT_WINDOWS[recent])).isoformat()
        date_to = as_of.isoformat()
    else:
        date_from, date_to = _optional_text(value.date_from), _optional_text(value.date_to)
        if date_from:
            start = _world_datetime(date_from, "date_from")
            date_from = start.isoformat()
        if date_to:
            end = _world_datetime(date_to, "date_to")
            if len(str(value.date_to).strip()) == 10:
                end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
            date_to = end.isoformat()
    if date_from and date_to and _world_datetime(date_from, "date_from") > _world_datetime(date_to, "date_to"):
        raise ValueError("World date_from must be earlier than or equal to date_to")
    missing = str(value.missing_location or "INCLUDE").strip().upper()
    if missing not in {"INCLUDE", "EXCLUDE", "ONLY"}:
        raise ValueError(f"Unsupported missing-location behavior: {missing}")
    lifecycle = choices(value.lifecycle, upper=True)
    identity = choices(value.identity_state, upper=True)
    biometric = choices(value.biometric_state, upper=True)
    evidence = choices(value.evidence_type, upper=True)
    unsupported = set(lifecycle) - PERSON_LIFECYCLE_STATUSES
    if unsupported:
        raise ValueError(f"Unsupported World lifecycle filter: {sorted(unsupported)[0]}")
    if set(identity) - PERSON_IDENTITY_STATUSES:
        raise ValueError("Unsupported World identity-state filter")
    if set(biometric) - PERSON_BIOMETRIC_STATUSES:
        raise ValueError("Unsupported World biometric-state filter")
    if set(evidence) - RELATIONSHIP_EVIDENCE_TYPES:
        raise ValueError("Unsupported World evidence-type filter")
    if value.min_relationship_strength is not None and int(value.min_relationship_strength) < 1:
        raise ValueError("World minimum relationship strength must be at least 1")
    activity = choices(value.activity, upper=True)
    if set(activity) - {"NONE", "LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Unsupported World activity filter")
    pattern_type = choices(value.pattern_type, upper=True)
    if set(pattern_type) - {"DATA_QUALITY"}:
        raise ValueError("Unsupported World pattern-type filter")
    return WorldReadFilter(
        date_from=date_from, date_to=date_to, recent_activity=recent,
        locations=choices(value.locations), missing_location=missing,
        lifecycle=lifecycle, identity_state=identity, biometric_state=biometric,
        country=choices(value.country), rank=choices(value.rank), priority=choices(value.priority),
        evidence_type=evidence, relationship_type=choices(value.relationship_type, upper=True),
        min_relationship_strength=(int(value.min_relationship_strength) if value.min_relationship_strength is not None else None),
        activity=activity, pattern_type=pattern_type,
    )


def _normalize_world_focus(
    level: WorldDetailLevel, focus_type: str | None, focus_id: str | None,
) -> tuple[str | None, str | None]:
    if level == WorldDetailLevel.WORLD_SCOPE:
        if focus_type or focus_id:
            raise ValueError("WORLD_SCOPE does not accept focus")
        return None, None
    expected = {
        WorldDetailLevel.CLUSTER: {"CLUSTER"},
        WorldDetailLevel.PERSON: {"PERSON"},
        WorldDetailLevel.EVENT: {"EVENT"},
        WorldDetailLevel.EVIDENCE: {"RELATIONSHIP", "EVENT", "PERSON", "EVIDENCE"},
    }[level]
    normalized_type = str(focus_type or "").strip().upper()
    normalized_id = str(focus_id or "").strip()
    if normalized_type not in expected or not normalized_id:
        raise ValueError(f"{level.value} requires a typed focus")
    return normalized_type, normalized_id


def _world_people_scope(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    canonical_map: dict[str, str] | None = None,
) -> tuple[
    dict[str, sqlite3.Row], dict[str, tuple[str, ...]], dict[str, str],
]:
    rows = conn.execute(
        """SELECT person_id, name, metadata, lifecycle_status,
                  canonical_person_id, identity_status, biometric_status
           FROM persons ORDER BY person_id"""
    ).fetchall()
    resolved = canonical_map or _world_canonical_map(conn, rows)
    aliases: dict[str, list[str]] = {}
    canonical_rows: dict[str, sqlite3.Row] = {}
    for row in rows:
        raw_id = str(row["person_id"])
        canonical_id = resolved[raw_id]
        if raw_id != canonical_id:
            aliases.setdefault(canonical_id, []).append(raw_id)
            continue
        metadata = json.loads(row["metadata"] or "{}")
        def match(field: str, choices: tuple[str, ...]) -> bool:
            return not choices or str(metadata.get(field) or "").casefold() in {item.casefold() for item in choices}
        if filters.lifecycle and str(row["lifecycle_status"]) not in filters.lifecycle:
            continue
        if filters.identity_state and str(row["identity_status"]) not in filters.identity_state:
            continue
        if filters.biometric_state and str(row["biometric_status"]) not in filters.biometric_state:
            continue
        if not (match("country", filters.country) and match("rank", filters.rank) and match("importance", filters.priority)):
            continue
        canonical_rows[canonical_id] = row
    return (
        canonical_rows,
        {key: tuple(sorted(value)) for key, value in aliases.items()},
        resolved,
    )


def _world_canonical_map(
    conn: sqlite3.Connection, rows: list[sqlite3.Row] | None = None,
) -> dict[str, str]:
    person_rows = rows or conn.execute(
        "SELECT person_id, canonical_person_id FROM persons ORDER BY person_id"
    ).fetchall()
    parent = {
        str(row["person_id"]): (
            str(row["canonical_person_id"]) if row["canonical_person_id"] else None
        ) for row in person_rows
    }
    resolved: dict[str, str] = {}
    for person_id in parent:
        chain: list[str] = []
        current = person_id
        while parent.get(current):
            if current in chain:
                raise RuntimeError(f"Canonical identity cycle detected: {person_id}")
            chain.append(current)
            current = str(parent[current])
        if current not in parent:
            raise RuntimeError(f"Canonical identity target is unavailable: {current}")
        resolved[person_id] = current
        for alias in chain:
            resolved[alias] = current
    return resolved


def _world_scope_sql(filters: WorldReadFilter, *, evidence: bool) -> tuple[str, list[object]]:
    clauses = ["o.status = 'FINALIZED'"]
    params: list[object] = []
    occurrence = "COALESCE(o.observed_at, o.created_at)"
    if filters.date_from:
        clauses.append(f"{occurrence} >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        clauses.append(f"{occurrence} <= ?")
        params.append(filters.date_to)
    if filters.locations:
        clauses.append("LOWER(TRIM(COALESCE(o.location, ''))) IN (%s)" % ",".join("?" for _ in filters.locations))
        params.extend(item.casefold() for item in filters.locations)
    if filters.missing_location == "EXCLUDE":
        clauses.append("TRIM(COALESCE(o.location, '')) <> ''")
    elif filters.missing_location == "ONLY":
        clauses.append("TRIM(COALESCE(o.location, '')) = ''")
    if evidence and filters.evidence_type:
        clauses.append("e.evidence_type IN (%s)" % ",".join("?" for _ in filters.evidence_type))
        params.extend(filters.evidence_type)
    if evidence and filters.relationship_type:
        clauses.append("e.relationship_type IN (%s)" % ",".join("?" for _ in filters.relationship_type))
        params.extend(filters.relationship_type)
    return " AND ".join(clauses), params


def _world_register_effective_evidence_function(
    conn: sqlite3.Connection,
    canonical_map: dict[str, str],
):
    """Register correction-before-canonical endpoint resolution for one read."""
    corrections = {
        (str(row["observation_id"]), str(row["from_person_id"])):
            str(row["to_person_id"])
        for row in conn.execute(
            """SELECT observation_id, from_person_id, to_person_id
               FROM identity_corrections
               WHERE correction_type = 'OBSERVATION_IDENTITY'
               ORDER BY created_at, correction_id"""
        ).fetchall()
    }

    def effective_person(
        evidence_type: object,
        source_entity_type: object,
        source_entity_id: object,
        raw_person_id: object,
    ) -> str:
        current = str(raw_person_id)
        if str(evidence_type) == "CO_OBSERVED" and str(source_entity_type) == "OBSERVATION":
            seen: set[str] = set()
            key = (str(source_entity_id), current)
            while key in corrections:
                if current in seen:
                    raise RuntimeError("Observation identity correction cycle detected")
                seen.add(current)
                current = corrections[key]
                key = (str(source_entity_id), current)
        return canonical_map[current]

    conn.create_function(
        "world_effective_evidence_person", 4, effective_person, deterministic=True,
    )
    return effective_person


def _world_relationship_scope(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_ids: set[str],
    *,
    canonical_map: dict[str, str] | None = None,
    focus_person_id: str | None = None,
) -> list[dict]:
    resolved = canonical_map or _world_canonical_map(conn)
    evidence_person = _world_register_effective_evidence_function(conn, resolved)
    scope_sql, scope_params = _world_scope_sql(filters, evidence=False)
    evidence_clauses: list[str] = []
    evidence_params: list[object] = []
    if filters.evidence_type:
        evidence_clauses.append("e.evidence_type IN (%s)" % ",".join("?" for _ in filters.evidence_type))
        evidence_params.extend(filters.evidence_type)
    if filters.relationship_type:
        evidence_clauses.append("e.relationship_type IN (%s)" % ",".join("?" for _ in filters.relationship_type))
        evidence_params.extend(filters.relationship_type)
    if focus_person_id:
        evidence_clauses.append(
            "(world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
            "e.source_entity_id, e.source_person_id) = ? OR "
            "world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
            "e.source_entity_id, e.target_person_id) = ?)"
        )
        evidence_params.extend([focus_person_id, focus_person_id])
    non_observation_clauses = ["e.evidence_type <> 'CO_OBSERVED'"]
    non_observation_params: list[object] = []
    if filters.date_from:
        non_observation_clauses.append("e.created_at >= ?")
        non_observation_params.append(filters.date_from)
    if filters.date_to:
        non_observation_clauses.append("e.created_at <= ?")
        non_observation_params.append(filters.date_to)
    non_observation_allowed = not filters.locations and filters.missing_location != "EXCLUDE"
    evidence_prefix = (" AND " + " AND ".join(evidence_clauses)) if evidence_clauses else ""
    rows = conn.execute(
        f"""
        SELECT e.source_person_id, e.target_person_id, e.evidence_type,
               e.source_entity_type, e.source_entity_id,
               e.relationship_type, e.directionality, COUNT(*) AS evidence_count,
               MIN(CASE WHEN e.evidence_type = 'CO_OBSERVED' THEN COALESCE(o.observed_at, o.created_at) ELSE e.created_at END) AS first_at,
               MAX(CASE WHEN e.evidence_type = 'CO_OBSERVED' THEN COALESCE(o.observed_at, o.created_at) ELSE e.created_at END) AS last_at
        FROM relationship_evidence e
        LEFT JOIN observations o ON e.evidence_type = 'CO_OBSERVED'
             AND e.source_entity_type = 'OBSERVATION' AND o.observation_id = e.source_entity_id
        WHERE e.active = 1{evidence_prefix} AND (
            (e.evidence_type = 'CO_OBSERVED' AND {scope_sql})
            OR ({' AND '.join(non_observation_clauses)} AND ? = 1)
        )
        GROUP BY e.source_person_id, e.target_person_id, e.evidence_type,
                 e.source_entity_type, e.source_entity_id,
                 e.relationship_type, e.directionality
        """,
        [*evidence_params, *scope_params, *non_observation_params, int(non_observation_allowed)],
    ).fetchall()
    aggregates: dict[tuple[str, str], dict] = {}
    for row in rows:
        source = evidence_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["source_person_id"],
        )
        target = evidence_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["target_person_id"],
        )
        if source == target or source not in eligible_ids or target not in eligible_ids:
            continue
        pair = tuple(sorted((source, target)))
        item = aggregates.setdefault(pair, {
            "relationship_id": f"relationship:{pair[0]}:{pair[1]}",
            "source_person_id": pair[0], "target_person_id": pair[1],
            "directionality": "UNDIRECTED", "directions": {}, "relationship_types": set(),
            "evidence_type_counts": {}, "evidence_count": 0,
            "first_occurrence_at": str(row["first_at"]), "last_occurrence_at": str(row["last_at"]),
        })
        count = int(row["evidence_count"])
        item["evidence_count"] += count
        item["evidence_type_counts"][str(row["evidence_type"])] = item["evidence_type_counts"].get(str(row["evidence_type"]), 0) + count
        item["relationship_types"].add(str(row["relationship_type"]))
        direction_key = (
            "UNDIRECTED" if str(row["directionality"]) == "UNDIRECTED"
            else f"{source}->{target}"
        )
        item["directions"][direction_key] = (
            item["directions"].get(direction_key, 0) + count
        )
        item["first_occurrence_at"] = min(item["first_occurrence_at"], str(row["first_at"]))
        item["last_occurrence_at"] = max(item["last_occurrence_at"], str(row["last_at"]))
    result = []
    for item in aggregates.values():
        if filters.min_relationship_strength and item["evidence_count"] < filters.min_relationship_strength:
            continue
        item["relationship_types"] = tuple(sorted(item["relationship_types"]))
        directions = item.pop("directions")
        if set(directions) == {"UNDIRECTED"}:
            item["directionality"] = "UNDIRECTED"
        elif "UNDIRECTED" not in directions and len(directions) == 1:
            item["source_person_id"], item["target_person_id"] = next(iter(directions)).split("->", 1)
            item["directionality"] = "DIRECTED"
        else:
            item["directionality"] = "MIXED"
        item["direction_counts"] = dict(sorted(directions.items()))
        result.append(item)
    return sorted(result, key=lambda item: (-item["evidence_count"], item["relationship_id"]))


def _world_scoped_event_people(conn: sqlite3.Connection, filters: WorldReadFilter) -> set[str]:
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    rows = conn.execute(
        f"""
        WITH RECURSIVE corrected(observation_id, person_id) AS (
            SELECT p.observation_id, p.person_id
            FROM observations o JOIN observation_participants p USING(observation_id)
            WHERE {scope_sql}
            UNION
            SELECT r.observation_id, c.to_person_id
            FROM corrected r JOIN identity_corrections c
              ON c.observation_id = r.observation_id
             AND c.correction_type = 'OBSERVATION_IDENTITY'
             AND c.from_person_id = r.person_id
        ), correction_terminal(observation_id, person_id) AS (
            SELECT r.observation_id, r.person_id FROM corrected r
            WHERE NOT EXISTS (
                SELECT 1 FROM identity_corrections c
                WHERE c.observation_id = r.observation_id
                  AND c.correction_type = 'OBSERVATION_IDENTITY'
                  AND c.from_person_id = r.person_id
            )
        ), canonical(observation_id, person_id) AS (
            SELECT observation_id, person_id FROM correction_terminal
            UNION
            SELECT c.observation_id, p.canonical_person_id
            FROM canonical c JOIN persons p ON p.person_id = c.person_id
            WHERE p.canonical_person_id IS NOT NULL
        )
        SELECT DISTINCT c.person_id FROM canonical c
        JOIN persons p ON p.person_id = c.person_id
        WHERE p.canonical_person_id IS NULL
        """, params,
    ).fetchall()
    return {str(row["person_id"]) for row in rows}


def _world_activity_counts(
    conn: sqlite3.Connection, eligible_ids: set[str], filters: WorldReadFilter,
) -> dict[str, int]:
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    rows = conn.execute(
        f"""
        WITH RECURSIVE corrected(observation_id, person_id) AS (
            SELECT p.observation_id, p.person_id
            FROM observations o JOIN observation_participants p USING(observation_id)
            WHERE {scope_sql}
            UNION
            SELECT r.observation_id, c.to_person_id
            FROM corrected r JOIN identity_corrections c
              ON c.observation_id = r.observation_id
             AND c.correction_type = 'OBSERVATION_IDENTITY'
             AND c.from_person_id = r.person_id
        ), correction_terminal(observation_id, person_id) AS (
            SELECT r.observation_id, r.person_id FROM corrected r
            WHERE NOT EXISTS (
                SELECT 1 FROM identity_corrections c
                WHERE c.observation_id = r.observation_id
                  AND c.correction_type = 'OBSERVATION_IDENTITY'
                  AND c.from_person_id = r.person_id
            )
        ), canonical(observation_id, person_id) AS (
            SELECT observation_id, person_id FROM correction_terminal
            UNION
            SELECT c.observation_id, p.canonical_person_id
            FROM canonical c JOIN persons p ON p.person_id = c.person_id
            WHERE p.canonical_person_id IS NOT NULL
        ), effective(observation_id, person_id) AS (
            SELECT DISTINCT c.observation_id, c.person_id FROM canonical c
            JOIN persons p ON p.person_id = c.person_id
            WHERE p.canonical_person_id IS NULL
        )
        SELECT person_id, COUNT(*) AS event_count
        FROM effective GROUP BY person_id
        """, params,
    ).fetchall()
    return {
        str(row["person_id"]): int(row["event_count"])
        for row in rows if str(row["person_id"]) in eligible_ids
    }


def _world_event_statistics(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_ids: set[str],
    *,
    canonical_map: dict[str, str] | None = None,
    location_offset: int = 0,
    location_limit: int = 100,
) -> dict[str, object]:
    """Calculate overview event metrics from one effective-participant projection."""
    if not eligible_ids:
        return {"activity": {}, "locations": [], "location_total_count": 0, "total": 0, "missing": 0}
    if canonical_map is not None and eligible_ids == set(canonical_map.values()):
        return _world_full_scope_event_statistics(
            conn, filters, canonical_map,
            location_offset=location_offset, location_limit=location_limit,
        )
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    cte = _world_effective_participant_cte(scope_sql)
    placeholders = ",".join("?" for _ in eligible_ids)
    rows = conn.execute(
        f"""{cte}, eligible AS (
                SELECT e.observation_id, e.person_id,
                       CASE WHEN TRIM(COALESCE(o.location, '')) = '' THEN 'MISSING'
                            ELSE TRIM(o.location) END AS location
                FROM effective e JOIN observations o USING(observation_id)
                WHERE e.person_id IN ({placeholders})
            ), event_set AS (
                SELECT DISTINCT observation_id, location FROM eligible
            )
            SELECT 'ACTIVITY' AS kind, person_id AS label,
                   COUNT(DISTINCT observation_id) AS value
            FROM eligible GROUP BY person_id
            UNION ALL
            SELECT 'LOCATION', location, COUNT(*) FROM event_set GROUP BY LOWER(location)
            UNION ALL
            SELECT 'TOTAL', '', COUNT(*) FROM event_set
            UNION ALL
            SELECT 'MISSING', '', COUNT(*) FROM event_set WHERE location = 'MISSING'""",
        [*params, *sorted(eligible_ids)],
    ).fetchall()
    activity: dict[str, int] = {}
    locations: list[dict[str, object]] = []
    total = missing = 0
    for row in rows:
        kind, label, value = str(row["kind"]), str(row["label"]), int(row["value"])
        if kind == "ACTIVITY":
            activity[label] = value
        elif kind == "LOCATION":
            locations.append({"value": label, "count": value})
        elif kind == "TOTAL":
            total = value
        elif kind == "MISSING":
            missing = value
    locations.sort(key=lambda item: (-int(item["count"]), str(item["value"]).casefold()))
    return {
        "activity": activity,
        "locations": locations[location_offset:location_offset + location_limit],
        "location_total_count": len(locations),
        "total": total, "missing": missing,
    }


def _world_full_scope_event_statistics(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    canonical_map: dict[str, str],
    *,
    location_offset: int = 0,
    location_limit: int = 100,
) -> dict[str, object]:
    """Fast exact aggregation when every terminal canonical identity is eligible."""
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    conn.create_aggregate(
        "world_overview_statistics", 3, _WorldOverviewStatisticsAggregate,
    )
    if not _world_use_participant_first_overview(conn, filters):
        aggregate_from = """observations o
                 INDEXED BY idx_observations_finalized_time_location
            CROSS JOIN observation_participants p"""
    else:
        aggregate_from = """observation_participants p
                 INDEXED BY sqlite_autoindex_observation_participants_1
            CROSS JOIN observations o"""
    row = conn.execute(
        f"""SELECT world_overview_statistics(
                       p.person_id, o.observation_id, o.location
                   ) AS payload
            FROM {aggregate_from}
            WHERE {scope_sql} AND p.observation_id = o.observation_id""",
        params,
    ).fetchone()
    payload = json.loads(str(row["payload"] or "{}"))
    activity: dict[str, int] = {}
    for raw_person_id, count in payload.get("activity", {}).items():
        canonical_id = canonical_map[str(raw_person_id)]
        activity[canonical_id] = (
            activity.get(canonical_id, 0) + int(count)
        )
    location_counts: dict[str, dict[str, object]] = {}
    for stored_location, event_count in payload.get("locations", {}).items():
        raw_location = str(stored_location or "").strip()
        location_key = raw_location.casefold()
        item = location_counts.setdefault(
            location_key,
            {"value": raw_location or "MISSING", "count": 0},
        )
        item["count"] = int(item["count"]) + int(event_count)
        if raw_location and raw_location < str(item["value"]):
            item["value"] = raw_location
    locations = sorted(
        location_counts.values(),
        key=lambda item: (-int(item["count"]), str(item["value"]).casefold()),
    )
    total = sum(int(item["count"]) for item in locations)
    missing = next(
        (int(item["count"]) for item in locations if item["value"] == "MISSING"), 0,
    )

    correction_sources = {
        str(row[0]) for row in conn.execute(
            """SELECT DISTINCT from_person_id FROM identity_corrections
               WHERE correction_type = 'OBSERVATION_IDENTITY'"""
        ).fetchall()
    }
    affected_ids = {
        raw_id for raw_id, canonical_id in canonical_map.items()
        if raw_id != canonical_id
    } | correction_sources
    if not affected_ids:
        return {
            "activity": activity,
            "locations": locations[location_offset:location_offset + location_limit],
            "location_total_count": len(locations),
            "total": total, "missing": missing,
        }

    candidates = _world_register_effective_person_function(conn, canonical_map)
    del candidates
    conn.create_function(
        "world_canonical_person", 1,
        lambda person_id: canonical_map[str(person_id)], deterministic=True,
    )
    placeholders = ",".join("?" for _ in affected_ids)
    adjustments = conn.execute(
        f"""WITH affected_events AS MATERIALIZED (
                SELECT DISTINCT p.observation_id
                FROM observation_participants p
                     INDEXED BY idx_observation_participants_person
                CROSS JOIN observations o
                WHERE p.person_id IN ({placeholders})
                  AND o.observation_id = p.observation_id
                  AND {scope_sql}
            )
            SELECT 'NAIVE' AS kind, world_canonical_person(p.person_id) AS person_id,
                   COUNT(*) AS count
            FROM observation_participants p JOIN affected_events a USING(observation_id)
            GROUP BY world_canonical_person(p.person_id)
            UNION ALL
            SELECT 'EFFECTIVE', world_effective_person(p.observation_id, p.person_id),
                   COUNT(DISTINCT p.observation_id)
            FROM observation_participants p JOIN affected_events a USING(observation_id)
            GROUP BY world_effective_person(p.observation_id, p.person_id)""",
        [*sorted(affected_ids), *params],
    ).fetchall()
    for row in adjustments:
        person_id, count = str(row["person_id"]), int(row["count"])
        activity[person_id] = activity.get(person_id, 0) + (
            count if str(row["kind"]) == "EFFECTIVE" else -count
        )
    return {
        "activity": activity,
        "locations": locations[location_offset:location_offset + location_limit],
        "location_total_count": len(locations),
        "total": total, "missing": missing,
    }


def _world_use_participant_first_overview(
    conn: sqlite3.Connection, filters: WorldReadFilter,
) -> bool:
    """Use the sequential participant scan only for an unrestricted sparse scope."""
    if _world_has_event_scope(filters):
        return False
    multi_participant = conn.execute(
        """SELECT 1
           FROM observation_participants
                INDEXED BY sqlite_autoindex_observation_participants_1
           GROUP BY observation_id
           HAVING COUNT(*) > 1
           LIMIT 1"""
    ).fetchone()
    return multi_participant is None


class _WorldOverviewStatisticsAggregate:
    """One-pass activity/location aggregation over observation-grouped input."""

    def __init__(self) -> None:
        self.activity: dict[str, int] = {}
        self.locations: dict[str, int] = {}
        self.last_observation_id: str | None = None

    def step(
        self, person_id: object, observation_id: object, location: object,
    ) -> None:
        raw_person_id = str(person_id)
        self.activity[raw_person_id] = self.activity.get(raw_person_id, 0) + 1
        current_observation_id = str(observation_id)
        # Both supported plans keep all participants for an observation
        # consecutive: observations are the outer loop for filtered scopes,
        # while the unfiltered plan scans the (observation_id, person_id)
        # participant primary-key index in order.
        if current_observation_id != self.last_observation_id:
            stored_location = "" if location is None else str(location)
            self.locations[stored_location] = self.locations.get(stored_location, 0) + 1
            self.last_observation_id = current_observation_id

    def finalize(self) -> str:
        return json.dumps(
            {"activity": self.activity, "locations": self.locations},
            sort_keys=True, separators=(",", ":"),
        )


def _world_activity_bucket(count: int) -> str:
    if count == 0:
        return "NONE"
    if count <= 2:
        return "LOW"
    if count <= 9:
        return "MEDIUM"
    return "HIGH"


def _world_rank_people(
    rows: dict[str, sqlite3.Row], activity: dict[str, int], degree: dict[str, dict[str, int]], ranking: str,
) -> list[str]:
    def priority_value(row: sqlite3.Row) -> int:
        metadata = json.loads(row["metadata"] or "{}")
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
            str(metadata.get("importance") or "").casefold(), 0,
        )
    def key(person_id: str):
        row = rows[person_id]
        if ranking == "DISPLAY_NAME":
            return (str(row["name"]).casefold(), person_id)
        if ranking == "RECENT_ACTIVITY":
            return (-activity.get(person_id, 0), str(row["name"]).casefold(), person_id)
        if ranking == "EVIDENCE_COUNT":
            return (-degree.get(person_id, {}).get("evidence", 0), str(row["name"]).casefold(), person_id)
        return (
            -priority_value(row), -activity.get(person_id, 0),
            -degree.get(person_id, {}).get("evidence", 0),
            str(row["name"]).casefold(), person_id,
        )
    return sorted(rows, key=key)


def _world_person(
    person_id: str,
    row: sqlite3.Row,
    aliases: tuple[str, ...],
    event_count: int | None,
    degree: dict[str, int] | None,
    context: _WorldReadContext,
    *,
    rank_position: int | None = None,
    selected_by_focus: bool = False,
) -> WorldPerson:
    metadata = json.loads(row["metadata"] or "{}")
    priority = metadata.get("importance")
    analytics_loaded = event_count is not None and degree is not None
    relationships = degree.get("relationships", 0) if degree is not None else None
    evidence_records = degree.get("evidence", 0) if degree is not None else None
    factors = (
        {"factor": "explicit_priority", "value": priority, "kind": "OPERATOR_ASSERTED"},
        {"factor": "finalized_event_count", "value": event_count, "kind": "MEASURED" if analytics_loaded else "NOT_LOADED"},
        {"factor": "relationship_count", "value": relationships, "kind": "MEASURED" if analytics_loaded else "NOT_LOADED"},
        {"factor": "evidence_count", "value": evidence_records, "kind": "MEASURED" if analytics_loaded else "NOT_LOADED"},
    )
    ranking_reasons = {
        "SALIENCE": "Ordered by operator priority, finalized events, evidence count, then display name.",
        "RECENT_ACTIVITY": "Ordered by finalized-event count in the explicit effective time window.",
        "EVIDENCE_COUNT": "Ordered by active authoritative relationship-evidence count in scope.",
        "DISPLAY_NAME": "Ordered by normalized display name.",
    }
    ranking_reason = (
        "Requested person focus; global ranking was not used to select this object."
        if selected_by_focus else ranking_reasons[context.ranking]
    )
    ranking_payload = {
        "applied": not selected_by_focus,
        "intent": context.ranking,
        "rank_position": rank_position,
        "ranking_reason": ranking_reason,
        "metrics": {
            "finalized_events": event_count,
            "relationships": relationships,
            "evidence_records": evidence_records,
            "operator_priority": priority,
        },
        "metrics_state": "LOADED" if analytics_loaded else "NOT_LOADED",
        "deterministic_tie_break": (
            ["operator_priority", "finalized_events", "evidence_records", "display_name", "canonical_person_id"]
            if context.ranking == "SALIENCE" else
            ["finalized_events", "display_name", "canonical_person_id"]
            if context.ranking == "RECENT_ACTIVITY" else
            ["evidence_records", "display_name", "canonical_person_id"]
            if context.ranking == "EVIDENCE_COUNT" else
            ["display_name", "canonical_person_id"]
        ),
        "value_semantics": "deterministic_ordering_not_confidence",
    }
    return WorldPerson(
        canonical_person_id=person_id,
        historical_person_ids=aliases,
        display_name=str(row["name"]),
        lifecycle_state=str(row["lifecycle_status"]),
        identity_state=str(row["identity_status"]),
        biometric_state=str(row["biometric_status"]),
        display={"country": metadata.get("country"), "rank": metadata.get("rank")},
        intelligence_summary={
            "relationship_count": relationships,
            "relationship_evidence_count": evidence_records,
            "activity_bucket": (_world_activity_bucket(event_count) if event_count is not None else None),
        },
        importance_indicators=factors,
        activity_summary={
            "finalized_event_count": event_count,
            "activity_bucket": (_world_activity_bucket(event_count) if event_count is not None else None),
            "state": "LOADED" if analytics_loaded else "NOT_LOADED",
        },
        ranking=ranking_payload,
        allowed_actions=_graph_allowed_actions(str(row["lifecycle_status"])),
        explanation=WorldExplanation(
            summary=ranking_reason,
            basis_type="PERSON_RANKING",
            factual_factors=factors,
            derived_factors=({"factor": "ranking_intent", "value": context.ranking},),
            calculation_version=_WORLD_RANKING_VERSION,
            evidence_count=(evidence_records if analytics_loaded else None),
            evidence_expansion_token=None,
            calculation_scope=_world_explanation_scope(context),
            strongest_factors=factors[:3],
            method="deterministic_lexicographic_ordering",
            limitations=("No probabilistic importance or identity confidence is calculated.",),
        ),
        analytics_state="LOADED" if analytics_loaded else "NOT_LOADED",
    )


def _world_clusters(
    revision: str,
    scope_fingerprint: str,
    relationships: list[dict],
    people_rows: dict[str, sqlite3.Row],
    activity: dict[str, int],
    preview_limit: int,
    context: _WorldReadContext,
) -> list[WorldCluster]:
    adjacency: dict[str, set[str]] = {}
    by_pair = {}
    for item in relationships:
        source, target = item["source_person_id"], item["target_person_id"]
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
        by_pair[tuple(sorted((source, target)))] = item
    components: list[set[str]] = []
    remaining = set(adjacency)
    while remaining:
        seed = min(remaining)
        component, frontier = set(), [seed]
        while frontier:
            current = frontier.pop()
            if current in component:
                continue
            component.add(current)
            frontier.extend(sorted(adjacency.get(current, set()) - component, reverse=True))
        remaining -= component
        if len(component) >= 2:
            components.append(component)
    result = []
    for members in components:
        ordered = tuple(sorted(members))
        member_edges = [item for pair, item in by_pair.items() if set(pair) <= members]
        evidence_count = sum(int(item["evidence_count"]) for item in member_edges)
        type_counts: dict[str, int] = {}
        for item in member_edges:
            for evidence_type, count in item["evidence_type_counts"].items():
                type_counts[evidence_type] = type_counts.get(evidence_type, 0) + int(count)
        digest = hashlib.sha256(
            json.dumps(
                [revision, scope_fingerprint, _WORLD_CLUSTER_VERSION, ordered],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:20]
        cluster_id = f"cluster:{digest}"
        preview_ids = sorted(
            ordered, key=lambda person_id: (-activity.get(person_id, 0), str(people_rows[person_id]["name"]).casefold(), person_id),
        )[:preview_limit]
        strongest = tuple({
            "relationship_id": item["relationship_id"],
            "source_person_id": item["source_person_id"],
            "target_person_id": item["target_person_id"],
            "evidence_count": item["evidence_count"],
            "evidence_types": sorted(item["evidence_type_counts"]),
        } for item in member_edges[:3])
        location_factor = {
            "factor": "location_context_role",
            "value": {
                "locations": list(context.filters.locations),
                "missing_location": context.filters.missing_location,
                "membership_basis": False,
            },
            "kind": "SCOPE_LIMITATION",
        }
        explanation = WorldExplanation(
            summary=f"{len(ordered)} people are connected by {evidence_count} scoped evidence records.",
            basis_type="EVIDENCE_CONNECTED_COMPONENT",
            factual_factors=(
                {"factor": "member_count", "value": len(ordered)},
                {"factor": "qualifying_relationship_count", "value": len(member_edges)},
                {"factor": "evidence_count", "value": evidence_count},
            ),
            derived_factors=(
                {"factor": "algorithm", "value": _WORLD_CLUSTER_VERSION},
                location_factor,
            ),
            calculation_version=_WORLD_CLUSTER_VERSION,
            evidence_types=tuple(sorted(type_counts)),
            evidence_count=evidence_count,
            first_occurrence_at=min((item["first_occurrence_at"] for item in member_edges), default=None),
            last_occurrence_at=max((item["last_occurrence_at"] for item in member_edges), default=None),
            evidence_expansion_token=None,
            calculation_scope=_world_explanation_scope(context),
            strongest_factors=strongest,
            method="connected_components_over_scoped_evidence_relationships",
            threshold={"minimum_members": 2, "minimum_relationship_strength": context.filters.min_relationship_strength or 1},
            sample={"member_count": len(ordered), "qualifying_relationship_count": len(member_edges)},
            limitations=(
                "Location and context restrict or describe scope but never create membership.",
                "A cluster is a revision-bound read object, not an organization or affiliation.",
            ),
        )
        result.append(WorldCluster(
            cluster_id=cluster_id, graph_revision=revision, member_ids=ordered,
            member_count=len(ordered),
            member_preview=tuple({"canonical_person_id": person_id, "display_name": str(people_rows[person_id]["name"])} for person_id in preview_ids),
            grouping_algorithm="EVIDENCE_CONNECTED_COMPONENT",
            algorithm_version=_WORLD_CLUSTER_VERSION,
            parameters={"minimum_members": 2, "qualifying_edge": "relationship_after_effective_filters"},
            evidence_basis={
                "relationship_count": len(member_edges),
                "evidence_count": evidence_count,
                "evidence_type_counts": dict(sorted(type_counts.items())),
                "strongest_relationships": list(strongest),
                "strongest_relationships_total_count": len(member_edges),
                "strongest_relationships_returned_count": len(strongest),
                "strongest_relationships_truncated": len(strongest) < len(member_edges),
                "location_context_role": "scope_only_not_membership",
            },
            explanation=explanation,
            activity_summary={
                "member_event_contributions": sum(activity.get(person_id, 0) for person_id in ordered),
                "active_member_count": sum(1 for person_id in ordered if activity.get(person_id, 0) > 0),
                "measurement": "deduplicated_person_event_contributions",
            },
            member_preview_state={
                "total_count": len(ordered),
                "returned_count": len(preview_ids),
                "has_more": len(preview_ids) < len(ordered),
                "truncated": len(preview_ids) < len(ordered),
                "truncation_reason": (
                    f"backend_preview_limit:{preview_limit}"
                    if len(preview_ids) < len(ordered) else None
                ),
            },
            expansion_token=None,
        ))
    ordered_result = sorted(
        result,
        key=lambda item: (
            -item.member_count,
            -int(item.evidence_basis["evidence_count"]),
            -int(item.activity_summary["member_event_contributions"]),
            item.cluster_id,
        ),
    )
    return [replace(item, ranking={
        "intent": "CLUSTER_SCOPE_SALIENCE",
        "rank_position": index + 1,
        "measurements": {
            "member_count": item.member_count,
            "evidence_count": item.evidence_basis["evidence_count"],
            "member_event_contributions": item.activity_summary["member_event_contributions"],
        },
        "deterministic_tie_break": [
            "member_count", "evidence_count", "member_event_contributions", "cluster_id",
        ],
        "reason": "Ordered by member count, evidence count, member event contributions, then cluster ID.",
        "value_semantics": "deterministic_ordering_not_confidence",
    }) for index, item in enumerate(ordered_result)]


def _world_relationship(
    item: dict, context: _WorldReadContext,
) -> WorldRelationship:
    explanation = WorldExplanation(
        summary=f"Supported by {item['evidence_count']} active authoritative evidence records in scope.",
        basis_type="EVIDENCE_COUNT_IN_SCOPE",
        factual_factors=(
            {"factor": "canonical_endpoints", "value": [item["source_person_id"], item["target_person_id"]]},
            {"factor": "evidence_type_counts", "value": dict(sorted(item["evidence_type_counts"].items()))},
            {"factor": "directionality", "value": item["directionality"]},
        ),
        calculation_version=_WORLD_CALCULATION_VERSION,
        evidence_types=tuple(sorted(item["evidence_type_counts"])), evidence_count=item["evidence_count"],
        first_occurrence_at=item["first_occurrence_at"], last_occurrence_at=item["last_occurrence_at"],
        evidence_expansion_token=None,
        calculation_scope=_world_explanation_scope(context),
        strongest_factors=(
            {"factor": "evidence_type_counts", "value": dict(sorted(item["evidence_type_counts"].items()))},
            {"factor": "occurrence_window", "value": {"first": item["first_occurrence_at"], "last": item["last_occurrence_at"]}},
        ),
        method="active_authoritative_evidence_count_after_scope",
        threshold={"minimum_evidence_count": context.filters.min_relationship_strength or 1},
        sample={"evidence_count": item["evidence_count"]},
        limitations=("Strength is a descriptive evidence count, not confidence or risk.",),
    )
    return WorldRelationship(
        relationship_id=item["relationship_id"], source_person_id=item["source_person_id"],
        target_person_id=item["target_person_id"], directionality=item["directionality"],
        relationship_types=item["relationship_types"], evidence_count=item["evidence_count"],
        evidence_type_counts=dict(sorted(item["evidence_type_counts"].items())),
        first_occurrence_at=item["first_occurrence_at"], last_occurrence_at=item["last_occurrence_at"],
        strength_basis="EVIDENCE_COUNT_IN_SCOPE", explanation=explanation,
        evidence_expansion_token=None,
    )


def _world_effective_participant_cte(scope_sql: str) -> str:
    return f"""
        WITH RECURSIVE identity_map(person_id, canonical_person_id) AS (
            SELECT person_id, person_id FROM persons WHERE canonical_person_id IS NULL
            UNION ALL
            SELECT p.person_id, m.canonical_person_id
            FROM persons p JOIN identity_map m ON p.canonical_person_id = m.person_id
        ), correction_chain(observation_id, raw_person_id, person_id) AS (
            SELECT observation_id, from_person_id, to_person_id
            FROM identity_corrections
            WHERE correction_type = 'OBSERVATION_IDENTITY'
            UNION ALL
            SELECT r.observation_id, r.raw_person_id, c.to_person_id
            FROM correction_chain r JOIN identity_corrections c
              ON c.observation_id = r.observation_id
             AND c.correction_type = 'OBSERVATION_IDENTITY'
             AND c.from_person_id = r.person_id
        ), correction_terminal(observation_id, raw_person_id, person_id) AS (
            SELECT r.observation_id, r.raw_person_id, r.person_id FROM correction_chain r
            WHERE NOT EXISTS (
                SELECT 1 FROM identity_corrections c
                WHERE c.observation_id = r.observation_id
                  AND c.correction_type = 'OBSERVATION_IDENTITY'
                  AND c.from_person_id = r.person_id
            )
        ), effective(observation_id, person_id) AS (
            SELECT DISTINCT p.observation_id, m.canonical_person_id
            FROM observations o JOIN observation_participants p USING(observation_id)
            LEFT JOIN correction_terminal c
              ON c.observation_id = p.observation_id AND c.raw_person_id = p.person_id
            JOIN identity_map m ON m.person_id = COALESCE(c.person_id, p.person_id)
            WHERE {scope_sql}
        )
    """


def _world_scoped_event_count(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_person_ids: set[str],
    *,
    canonical_map: dict[str, str] | None = None,
) -> int:
    if not eligible_person_ids:
        return 0
    resolved = canonical_map or _world_canonical_map(conn)
    candidates = _world_register_effective_person_function(
        conn, resolved, focus_person_ids=eligible_person_ids,
    )
    if not candidates:
        return 0
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    placeholders = ",".join("?" for _ in candidates)
    return int(conn.execute(
        f"""SELECT COUNT(DISTINCT p.observation_id)
            FROM observation_participants p
                 INDEXED BY idx_observation_participants_person
            CROSS JOIN observations o
            WHERE p.person_id IN ({placeholders})
              AND o.observation_id = p.observation_id
              AND {scope_sql}
              AND world_effective_person_in_scope(
                      p.observation_id, p.person_id
                  ) = 1""",
        [*sorted(candidates), *params],
    ).fetchone()[0])


def _world_person_event_count(
    conn: sqlite3.Connection,
    person_id: str,
    filters: WorldReadFilter,
    *,
    canonical_map: dict[str, str] | None = None,
) -> int:
    resolved = canonical_map or _world_canonical_map(conn)
    candidates = _world_register_effective_person_function(conn, resolved, person_id)
    if not candidates:
        return 0
    membership_sql, params = _world_person_event_membership_sql(
        filters, candidates, person_id,
    )
    return int(conn.execute(
        f"SELECT COUNT(DISTINCT p.observation_id) {membership_sql}", params,
    ).fetchone()[0])


def _world_person_events(
    conn: sqlite3.Connection,
    person_id: str,
    filters: WorldReadFilter,
    offset: int,
    limit: int,
    *,
    canonical_map: dict[str, str] | None = None,
    known_total: int | None = None,
) -> tuple[int, list[sqlite3.Row]]:
    resolved = canonical_map or _world_canonical_map(conn)
    candidates = _world_register_effective_person_function(conn, resolved, person_id)
    if not candidates:
        return 0, []
    membership_sql, params = _world_person_event_membership_sql(
        filters, candidates, person_id,
    )
    total = known_total if known_total is not None else _world_person_event_count(
        conn, person_id, filters, canonical_map=resolved,
    )
    rows = conn.execute(
        f"""SELECT DISTINCT o.* {membership_sql}
            ORDER BY COALESCE(o.observed_at, o.created_at) DESC, o.observation_id
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()
    return total, rows


def _world_person_event_membership_sql(
    filters: WorldReadFilter,
    candidates: set[str],
    person_id: str,
) -> tuple[str, list[object]]:
    """Return the shared participant-first focused-event membership predicate."""
    scope_sql, scope_params = _world_scope_sql(filters, evidence=False)
    placeholders = ",".join("?" for _ in candidates)
    return (
        f"""FROM observation_participants p
               INDEXED BY idx_observation_participants_person
            CROSS JOIN observations o
            WHERE p.person_id IN ({placeholders})
              AND o.observation_id = p.observation_id
              AND {scope_sql}
              AND world_effective_person(p.observation_id, p.person_id) = ?""",
        [*sorted(candidates), *scope_params, person_id],
    )


def _world_register_effective_person_function(
    conn: sqlite3.Connection,
    canonical_map: dict[str, str],
    focus_person_id: str | None = None,
    *,
    focus_person_ids: set[str] | None = None,
) -> set[str]:
    corrections = {
        (str(row["observation_id"]), str(row["from_person_id"])):
            str(row["to_person_id"])
        for row in conn.execute(
            """SELECT observation_id, from_person_id, to_person_id
               FROM identity_corrections
               WHERE correction_type = 'OBSERVATION_IDENTITY'
               ORDER BY created_at, correction_id"""
        ).fetchall()
    }

    def effective_person(observation_id: object, raw_person_id: object) -> str:
        current = str(raw_person_id)
        seen: set[str] = set()
        while (str(observation_id), current) in corrections:
            if current in seen:
                raise RuntimeError("Observation identity correction cycle detected")
            seen.add(current)
            current = corrections[(str(observation_id), current)]
        return canonical_map[current]

    conn.create_function("world_effective_person", 2, effective_person, deterministic=True)
    if focus_person_id is not None and focus_person_ids is not None:
        raise ValueError("World effective-person focus must be singular or a set")
    target_ids = (
        set(focus_person_ids) if focus_person_ids is not None
        else {focus_person_id} if focus_person_id is not None
        else None
    )
    if target_ids is None:
        return set(canonical_map)
    candidates = {
        raw_id for raw_id, canonical_id in canonical_map.items()
        if canonical_id in target_ids
    }
    changed = True
    while changed:
        changed = False
        for (_, source), target in corrections.items():
            if target in candidates and source not in candidates:
                candidates.add(source)
                changed = True
    if focus_person_ids is not None:
        conn.create_function(
            "world_effective_person_in_scope", 2,
            lambda observation_id, raw_person_id: int(
                effective_person(observation_id, raw_person_id) in target_ids
            ),
            deterministic=True,
        )
    return candidates


def _world_event_row(
    conn: sqlite3.Connection, event_id: str, filters: WorldReadFilter,
) -> sqlite3.Row:
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    row = conn.execute(
        f"SELECT o.* FROM observations o WHERE {scope_sql} AND o.observation_id = ?",
        [*params, event_id],
    ).fetchone()
    if row is None:
        raise KeyError("World event is unavailable in the effective scope")
    return row


def _world_event_participant_mapping(
    conn: sqlite3.Connection, event_id: str,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    raw_rows = conn.execute(
        "SELECT person_id FROM observation_participants WHERE observation_id = ? ORDER BY person_id",
        (event_id,),
    ).fetchall()
    corrections = conn.execute(
        """SELECT from_person_id, to_person_id, operation_id
           FROM identity_corrections
           WHERE observation_id = ? AND correction_type = 'OBSERVATION_IDENTITY'
           ORDER BY created_at, correction_id""",
        (event_id,),
    ).fetchall()
    canonical_map = _world_canonical_map(conn)
    return _world_participant_mapping(
        [str(row["person_id"]) for row in raw_rows], corrections, canonical_map,
    )


def _world_participant_mapping(
    raw_ids: list[str],
    corrections: list[sqlite3.Row],
    canonical_map: dict[str, str],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    effective_ids: set[str] = set()
    provenance: list[dict[str, object]] = []
    for raw_id in sorted(raw_ids):
        current = raw_id
        correction_ids: list[str] = []
        changed = True
        while changed:
            changed = False
            for correction in corrections:
                if str(correction["from_person_id"]) == current:
                    current = str(correction["to_person_id"])
                    correction_ids.append(str(correction["operation_id"]))
                    changed = True
                    break
        effective_id = canonical_map[current]
        effective_ids.add(effective_id)
        relationship = (
            "CORRECTED_PARTICIPANT" if correction_ids else
            "MERGED_SOURCE" if raw_id != effective_id else
            "ORIGINAL_IDENTITY"
        )
        provenance.append({
            "raw_person_id": raw_id,
            "effective_person_id": effective_id,
            "relationship_to_effective_identity": relationship,
            "correction_operation_ids": correction_ids,
        })
    participants = tuple({"person_id": person_id} for person_id in sorted(effective_ids))
    return participants, tuple(provenance)


def _world_event_batch_data(
    conn: sqlite3.Connection,
    event_rows: list[sqlite3.Row],
    canonical_map: dict[str, str],
) -> dict[str, tuple[
    tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]],
    dict[str, object],
    int,
]]:
    event_ids = [str(row["observation_id"]) for row in event_rows]
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    raw_by_event: dict[str, list[str]] = {event_id: [] for event_id in event_ids}
    for row in conn.execute(
        f"""SELECT observation_id, person_id FROM observation_participants
            WHERE observation_id IN ({placeholders}) ORDER BY observation_id, person_id""",
        event_ids,
    ).fetchall():
        raw_by_event[str(row["observation_id"])].append(str(row["person_id"]))
    corrections_by_event: dict[str, list[sqlite3.Row]] = {
        event_id: [] for event_id in event_ids
    }
    for row in conn.execute(
        f"""SELECT observation_id, from_person_id, to_person_id, operation_id
            FROM identity_corrections
            WHERE correction_type = 'OBSERVATION_IDENTITY'
              AND observation_id IN ({placeholders})
            ORDER BY observation_id, created_at, correction_id""",
        event_ids,
    ).fetchall():
        corrections_by_event[str(row["observation_id"])].append(row)
    evidence_by_event: dict[str, dict[str, int]] = {event_id: {} for event_id in event_ids}
    for row in conn.execute(
        f"""SELECT source_entity_id, evidence_type, COUNT(*) AS count
            FROM relationship_evidence
            WHERE active = 1 AND source_entity_type = 'OBSERVATION'
              AND source_entity_id IN ({placeholders})
            GROUP BY source_entity_id, evidence_type""",
        event_ids,
    ).fetchall():
        evidence_by_event[str(row["source_entity_id"])][str(row["evidence_type"])] = int(row["count"])
    media_by_event = {event_id: 0 for event_id in event_ids}
    for row in conn.execute(
        f"""SELECT observation_id, COUNT(*) AS count FROM observation_media
            WHERE observation_id IN ({placeholders}) GROUP BY observation_id""",
        event_ids,
    ).fetchall():
        media_by_event[str(row["observation_id"])] = int(row["count"])
    return {
        event_id: (
            _world_participant_mapping(
                raw_by_event[event_id], corrections_by_event[event_id], canonical_map,
            ),
            {
                "total_count": sum(evidence_by_event[event_id].values()),
                "evidence_type_counts": dict(sorted(evidence_by_event[event_id].items())),
            },
            media_by_event[event_id],
        )
        for event_id in event_ids
    }


def _world_context_summary(payload: str) -> dict[str, object]:
    context = json.loads(payload or "{}")
    allowed = ("occasion", "event_type", "description")
    values = {
        key: str(context[key]) for key in allowed
        if context.get(key) is not None and str(context[key]).strip()
    }
    return {"available": bool(values), **values}


def _world_event_evidence_summary(
    conn: sqlite3.Connection, event_id: str,
) -> dict[str, object]:
    rows = conn.execute(
        """SELECT evidence_type, COUNT(*) AS count
           FROM relationship_evidence
           WHERE active = 1 AND source_entity_type = 'OBSERVATION'
             AND source_entity_id = ?
           GROUP BY evidence_type ORDER BY evidence_type""",
        (event_id,),
    ).fetchall()
    counts = {str(row["evidence_type"]): int(row["count"]) for row in rows}
    return {"total_count": sum(counts.values()), "evidence_type_counts": counts}


def _world_event_evidence_count(
    conn: sqlite3.Connection, event_id: str, filters: WorldReadFilter,
) -> int:
    total, _ = _world_evidence_page(conn, filters, "EVENT", event_id, 0, 1)
    return total


def _world_event_media_count(conn: sqlite3.Connection, event_id: str) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM observation_media WHERE observation_id = ?", (event_id,),
    ).fetchone()[0])


def _world_event_media_page(
    conn: sqlite3.Connection, event_id: str, offset: int, limit: int,
    *, supporting_evidence_id: str | None = None,
) -> tuple[int, tuple[WorldMediaReference, ...]]:
    total = _world_event_media_count(conn, event_id)
    event = conn.execute(
        "SELECT COALESCE(observed_at, created_at) AS occurred_at FROM observations WHERE observation_id = ? AND status = 'FINALIZED'",
        (event_id,),
    ).fetchone()
    if event is None:
        raise KeyError("World event is unavailable")
    rows = conn.execute(
        """SELECT media_id, media_path, source FROM observation_media
           WHERE observation_id = ? ORDER BY created_at, media_id LIMIT ? OFFSET ?""",
        (event_id, limit, offset),
    ).fetchall()
    return total, tuple(WorldMediaReference(
        media_id=str(row["media_id"]),
        media_reference=_optional_text(row["media_path"]),
        source=_optional_text(row["source"]),
        occurred_at=str(event["occurred_at"]),
        supporting_event_id=event_id,
        supporting_evidence_id=supporting_evidence_id,
    ) for row in rows)


def _world_event_from_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    participant_offset: int,
    participant_limit: int,
    provenance_offset: int,
    provenance_limit: int,
    context: _WorldReadContext,
    prepared: tuple[
        tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]],
        dict[str, object],
        int,
    ] | None = None,
) -> WorldEvent:
    event_id = str(row["observation_id"])
    if prepared is None:
        all_participants, provenance = _world_event_participant_mapping(conn, event_id)
        evidence_summary = _world_event_evidence_summary(conn, event_id)
        media_count = _world_event_media_count(conn, event_id)
    else:
        (all_participants, provenance), evidence_summary, media_count = prepared
    participants = all_participants[
        participant_offset:participant_offset + participant_limit
    ]
    page_provenance = provenance[
        provenance_offset:provenance_offset + provenance_limit
    ]
    occurred_at = str(row["observed_at"] or row["created_at"])
    return WorldEvent(
        event_id=event_id,
        finalized_at=str(row["finalized_at"]),
        occurred_at=occurred_at,
        location=_optional_text(row["location"]),
        context_summary=_world_context_summary(str(row["context"] or "{}")),
        source=_optional_text(row["source"]),
        participants=participants,
        participant_provenance=page_provenance,
        participant_summary={
            "total_count": len(all_participants), "returned_count": len(participants),
            "has_more": participant_offset + len(participants) < len(all_participants),
            "provenance_total_count": len(provenance),
            "provenance_returned_count": len(page_provenance),
            "participants_state": "LOADED" if participant_limit else "NOT_REQUESTED",
            "provenance_state": "LOADED" if provenance_limit else "NOT_REQUESTED",
        },
        evidence_summary=evidence_summary,
        media_summary={"total_count": media_count, "retrieval": "EVENT_MEDIA_COLLECTION"},
        explanation=WorldExplanation(
            summary=f"Finalized event with {len(all_participants)} effective canonical participants.",
            basis_type="FINALIZED_OBSERVATION",
            factual_factors=(
                {"factor": "finalization_state", "value": "FINALIZED"},
                {"factor": "participant_count", "value": len(all_participants)},
                {"factor": "evidence_count", "value": evidence_summary["total_count"]},
                {"factor": "media_count", "value": media_count},
                {"factor": "location", "value": _optional_text(row["location"])},
            ),
            calculation_version=_WORLD_CALCULATION_VERSION,
            evidence_types=tuple(sorted(evidence_summary["evidence_type_counts"])),
            evidence_count=int(evidence_summary["total_count"]),
            first_occurrence_at=occurred_at,
            last_occurrence_at=occurred_at,
            calculation_scope=_world_explanation_scope(context),
            strongest_factors=(
                {"factor": "participant_count", "value": len(all_participants)},
                {"factor": "evidence_count", "value": evidence_summary["total_count"]},
            ),
            method="finalized_observation_summary",
            sample={"participant_count": len(all_participants)},
            limitations=("Media and evidence details are retrieved through separate bounded collections.",),
        ),
    )


def _world_evidence_page(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    focus_type: str | None,
    focus_id: str | None,
    offset: int,
    limit: int,
) -> tuple[int, list[WorldEvidence]]:
    canonical_map = _world_canonical_map(conn)
    effective_person = _world_register_effective_evidence_function(conn, canonical_map)
    effective_source = (
        "world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
        "e.source_entity_id, e.source_person_id)"
    )
    effective_target = (
        "world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
        "e.source_entity_id, e.target_person_id)"
    )
    clauses = [
        "e.active = 1",
        "(e.evidence_type <> 'CO_OBSERVED' OR o.status = 'FINALIZED')",
    ]
    params: list[object] = []
    if focus_type == "RELATIONSHIP":
        parts = str(focus_id).split(":")
        if len(parts) != 3 or parts[0] != "relationship":
            raise ValueError("Invalid World relationship focus")
        first, second = sorted(parts[1:])
        if first == second or first not in canonical_map.values() or second not in canonical_map.values():
            raise ValueError("Invalid World relationship focus")
        clauses.append(
            f"(({effective_source} = ? AND {effective_target} = ?) OR "
            f"({effective_source} = ? AND {effective_target} = ?))"
        )
        params.extend([first, second, second, first])
    elif focus_type == "EVENT":
        clauses.append("e.source_entity_type = 'OBSERVATION' AND e.source_entity_id = ?")
        params.append(focus_id)
    elif focus_type == "PERSON":
        canonical_id = canonical_map.get(str(focus_id))
        if canonical_id is None:
            raise KeyError("World person is unavailable")
        clauses.append(f"({effective_source} = ? OR {effective_target} = ?)")
        params.extend([canonical_id, canonical_id])
    elif focus_type == "EVIDENCE":
        clauses.append("e.evidence_id = ?")
        params.append(focus_id)
    if filters.evidence_type:
        clauses.append("e.evidence_type IN (%s)" % ",".join("?" for _ in filters.evidence_type))
        params.extend(filters.evidence_type)
    if filters.relationship_type:
        clauses.append("e.relationship_type IN (%s)" % ",".join("?" for _ in filters.relationship_type))
        params.extend(filters.relationship_type)
    occurrence = "CASE WHEN e.evidence_type = 'CO_OBSERVED' THEN COALESCE(o.observed_at, o.created_at) ELSE e.created_at END"
    if filters.date_from:
        clauses.append(f"{occurrence} >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        clauses.append(f"{occurrence} <= ?")
        params.append(filters.date_to)
    if filters.locations:
        clauses.append("e.evidence_type = 'CO_OBSERVED'")
        clauses.append("LOWER(TRIM(COALESCE(o.location, ''))) IN (%s)" % ",".join("?" for _ in filters.locations))
        params.extend(item.casefold() for item in filters.locations)
    if filters.missing_location == "EXCLUDE":
        clauses.append("e.evidence_type = 'CO_OBSERVED' AND TRIM(COALESCE(o.location, '')) <> ''")
    elif filters.missing_location == "ONLY":
        clauses.append("(e.evidence_type <> 'CO_OBSERVED' OR TRIM(COALESCE(o.location, '')) = '')")
    where = " AND ".join(clauses)
    joined = "relationship_evidence e LEFT JOIN observations o ON e.evidence_type = 'CO_OBSERVED' AND o.observation_id = e.source_entity_id"
    total = int(conn.execute(f"SELECT COUNT(*) FROM {joined} WHERE {where}", params).fetchone()[0])
    rows = conn.execute(
        f"SELECT e.*, {occurrence} AS effective_occurred_at FROM {joined} "
        f"WHERE {where} ORDER BY {occurrence} DESC, e.evidence_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    observation_ids = sorted({
        str(row["source_entity_id"]) for row in rows
        if str(row["evidence_type"]) == "CO_OBSERVED"
        and str(row["source_entity_type"]) == "OBSERVATION"
    })
    media_counts: dict[str, int] = {}
    if observation_ids:
        placeholders = ",".join("?" for _ in observation_ids)
        media_counts = {
            str(row["observation_id"]): int(row["count"])
            for row in conn.execute(
                f"""SELECT observation_id, COUNT(*) AS count FROM observation_media
                    WHERE observation_id IN ({placeholders}) GROUP BY observation_id""",
                observation_ids,
            ).fetchall()
        }
    result = []
    for row in rows:
        source = effective_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["source_person_id"],
        )
        target = effective_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["target_person_id"],
        )
        occurred_at = str(row["effective_occurred_at"])
        supporting = ({
            "source_entity_type": str(row["source_entity_type"]),
            "source_entity_id": str(row["source_entity_id"]),
            "evidence_revision_id": str(row["evidence_revision_id"]),
        },)
        raw_endpoints = (str(row["source_person_id"]), str(row["target_person_id"]))
        effective_endpoints = (source, target)
        is_observation = (
            str(row["evidence_type"]) == "CO_OBSERVED"
            and str(row["source_entity_type"]) == "OBSERVATION"
        )
        media_count = media_counts.get(str(row["source_entity_id"]), 0) if is_observation else 0
        directionality = str(row["directionality"])
        explanation = WorldExplanation(
            summary=(
                f"{row['evidence_type']} evidence records an authoritative "
                f"{directionality.lower()} relationship fact from {row['source_entity_type']}."
            ),
            basis_type="AUTHORITATIVE_EVIDENCE_PROVENANCE",
            factual_factors=(
                {"factor": "raw_endpoints", "value": list(raw_endpoints)},
                {"factor": "effective_endpoints", "value": list(effective_endpoints)},
                {"factor": "directionality", "value": directionality},
                {"factor": "authoritative_source", "value": {
                    "type": str(row["source_entity_type"]),
                    "id": str(row["source_entity_id"]),
                }},
            ),
            calculation_version=_WORLD_CALCULATION_VERSION,
            evidence_types=(str(row["evidence_type"]),), evidence_count=1,
            first_occurrence_at=occurred_at, last_occurrence_at=occurred_at,
            method="correction_before_terminal_canonical_resolution",
            sample={"evidence_items": 1},
            limitations=(
                "This evidence is descriptive provenance, not confidence, risk, or inferred intent.",
            ),
        )
        result.append(WorldEvidence(
            evidence_id=str(row["evidence_id"]),
            provenance={
                "created_operation_id": str(row["created_operation_id"]),
                "source": row["source"],
                "canonical_endpoints": [source, target],
                "raw_endpoints": list(raw_endpoints),
            },
            evidence_type=str(row["evidence_type"]), supporting_references=supporting,
            occurred_at=occurred_at,
            explanation_links=(
                (f"relationship:{min(source, target)}:{max(source, target)}",)
                if source != target else ()
            ),
            active=bool(row["active"]),
            directionality=directionality,
            effective_endpoints=effective_endpoints, raw_endpoints=raw_endpoints,
            occurrence_bounds={"first": occurred_at, "last": occurred_at},
            explanation=explanation,
            media_summary={
                "total_count": media_count,
                "availability": "AVAILABLE" if is_observation else "UNAVAILABLE",
                "retrieval": "EVIDENCE_MEDIA_COLLECTION",
                "reason": None if is_observation else "evidence_source_has_no_authoritative_media",
            },
        ))
    return total, result


def _world_patterns(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    people_count: int,
    limit: int,
    *,
    eligible_person_ids: set[str],
    context: _WorldReadContext,
    measured_total: int | None = None,
    measured_missing: int | None = None,
) -> list[WorldPattern]:
    if not eligible_person_ids:
        return []
    if measured_total is None or measured_missing is None:
        statistics = _world_event_statistics(conn, filters, eligible_person_ids)
        total, missing = int(statistics["total"]), int(statistics["missing"])
    else:
        total, missing = measured_total, measured_missing
    if not total or not missing or limit < 1:
        return []
    explanation = WorldExplanation(
        summary=f"{missing} of {total} finalized events in scope have no location metadata.",
        basis_type="DATA_QUALITY_MEASUREMENT",
        factual_factors=(
            {"factor": "finalized_event_count", "value": total},
            {"factor": "missing_location_count", "value": missing},
            {"factor": "scoped_people_count", "value": people_count},
        ),
        calculation_version=_WORLD_CALCULATION_VERSION,
        calculation_scope=_world_explanation_scope(context),
        strongest_factors=(
            {"factor": "missing_location_count", "value": missing},
            {"factor": "finalized_event_count", "value": total},
        ),
        method="count_finalized_events_with_missing_location",
        threshold={"emit_when_missing_location_count_at_least": 1},
        sample={"finalized_event_count": total, "scoped_people_count": people_count},
        limitations=(
            "This is a data-quality measurement, not an anomaly, risk, or prediction.",
            "Free-text locations are not normalized place identities.",
        ),
    )
    return [WorldPattern(
        pattern_id=f"pattern:data-quality:missing-location:{hashlib.sha256(str([total, missing]).encode()).hexdigest()[:12]}",
        pattern_type="DATA_QUALITY", status="MEASURED", subject_ids=("WORLD_SCOPE",),
        metrics={"missing_location_count": missing, "finalized_event_count": total, "unit": "events"},
        calculation_version=_WORLD_CALCULATION_VERSION, explanation=explanation,
    )]


def _world_facets(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    people_rows: dict[str, sqlite3.Row],
    relationships: list[dict],
    activity: dict[str, int],
    eligible_person_ids: set[str],
    *,
    location_facets: list[dict[str, object]] | None = None,
    pattern_count: int = 0,
) -> dict[str, object]:
    def facet(values: list[str]) -> list[dict[str, object]]:
        counts: dict[str, int] = {}
        for value in values:
            normalized = value.strip() or "MISSING"
            counts[normalized] = counts.get(normalized, 0) + 1
        return [
            {"value": value, "count": count}
            for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
        ]

    metadata = {
        person_id: json.loads(row["metadata"] or "{}")
        for person_id, row in people_rows.items()
    }
    evidence_counts: dict[str, int] = {}
    for relationship in relationships:
        for evidence_type, count in relationship["evidence_type_counts"].items():
            evidence_counts[evidence_type] = evidence_counts.get(evidence_type, 0) + int(count)
    return {
        "locations": (
            location_facets if location_facets is not None
            else _world_location_facets_effective(conn, filters, eligible_person_ids)
        ),
        "lifecycle": facet([str(row["lifecycle_status"]) for row in people_rows.values()]),
        "identity_state": facet([str(row["identity_status"]) for row in people_rows.values()]),
        "biometric_state": facet([str(row["biometric_status"]) for row in people_rows.values()]),
        "country": facet([str(value.get("country") or "") for value in metadata.values()]),
        "rank": facet([str(value.get("rank") or "") for value in metadata.values()]),
        "priority": facet([str(value.get("importance") or "") for value in metadata.values()]),
        "activity": facet([_world_activity_bucket(activity.get(person_id, 0)) for person_id in people_rows]),
        "evidence_type": [
            {"value": value, "count": count}
            for value, count in sorted(evidence_counts.items())
        ],
        "pattern_type": (
            [{"value": "DATA_QUALITY", "count": pattern_count}]
            if pattern_count else []
        ),
    }


def _world_location_facets_effective(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_person_ids: set[str],
) -> list[dict]:
    if not eligible_person_ids:
        return []
    location_filters = WorldReadFilter(
        date_from=filters.date_from, date_to=filters.date_to,
        recent_activity=filters.recent_activity, missing_location="INCLUDE",
    )
    scope_sql, params = _world_scope_sql(location_filters, evidence=False)
    cte = _world_effective_participant_cte(scope_sql)
    placeholders = ",".join("?" for _ in eligible_person_ids)
    rows = conn.execute(
        f"""{cte}, eligible_events AS (
                SELECT DISTINCT observation_id FROM effective
                WHERE person_id IN ({placeholders})
            )
            SELECT CASE WHEN TRIM(COALESCE(o.location, '')) = '' THEN 'MISSING'
                         ELSE TRIM(o.location) END AS value, COUNT(*) AS count
            FROM eligible_events e JOIN observations o USING(observation_id)
            GROUP BY LOWER(TRIM(COALESCE(o.location, '')))
            ORDER BY count DESC, value LIMIT 100""",
        [*params, *sorted(eligible_person_ids)],
    ).fetchall()
    return [{"value": str(row["value"]), "count": int(row["count"])} for row in rows]


def _world_token(
    kind: str, revision: str, level: str, focus_type: str | None, focus_id: str | None, offset: int,
    *, collection: str | None = None, as_of: str | None = None, scope: str | None = None,
) -> str:
    payload = json.dumps({
        "kind": kind, "revision": revision, "level": level,
        "focus_type": focus_type, "focus_id": focus_id, "offset": offset,
        "collection": collection, "as_of": as_of, "scope": scope,
    }, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _world_decode_cursor(
    token: str | None, revision: str, level: WorldDetailLevel,
    focus_type: str | None, focus_id: str | None, collection: WorldCollection,
    as_of: str, scope: str,
) -> int:
    if not token:
        return 0
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid World cursor") from exc
    expected = {
        "kind": "CURSOR", "revision": revision, "level": level.value,
        "focus_type": focus_type, "focus_id": focus_id,
        "collection": collection.value, "as_of": as_of, "scope": scope,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("World cursor does not match the current revision, level, focus, collection, as_of, or scope")
    offset = payload.get("offset")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("Invalid World cursor offset")
    return offset


def _world_cursor_as_of(token: str | None) -> str | None:
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid World cursor") from exc
    if payload.get("kind") != "CURSOR":
        raise ValueError("Invalid World cursor")
    return _optional_text(payload.get("as_of"))


def _world_scope_fingerprint(
    filters: WorldReadFilter, ranking: str, limits: WorldReadLimits,
) -> str:
    payload = json.dumps(
        {"filters": asdict(filters), "ranking": ranking, "limits": asdict(limits)},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _world_filter_fingerprint(filters: WorldReadFilter) -> str:
    payload = json.dumps(asdict(filters), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _validate_graph_projection(conn: sqlite3.Connection) -> dict:
    expected, errors, active_evidence_count = _expected_graph_connections(conn)
    actual_rows = conn.execute(
        """
        SELECT * FROM graph_connections
        ORDER BY source_person_id, target_person_id, relationship_type, directionality
        """
    ).fetchall()
    actual: list[GraphConnection] = []
    for row in actual_rows:
        try:
            actual.append(_graph_connection_from_row(row))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(
                "Invalid projected connection payload for "
                f"{row['source_person_id']} -> {row['target_person_id']}: {exc}"
            )
    expected_map = {
        (
            item.source_person_id,
            item.target_person_id,
            item.relationship_type,
            item.directionality,
        ): item
        for item in expected
    }
    actual_map = {
        (
            item.source_person_id,
            item.target_person_id,
            item.relationship_type,
            item.directionality,
        ): item
        for item in actual
    }
    for key in sorted(expected_map.keys() - actual_map.keys()):
        errors.append(f"Missing projected connection: {key}")
    for key in sorted(actual_map.keys() - expected_map.keys()):
        errors.append(f"Unexpected projected connection: {key}")
    for key in sorted(expected_map.keys() & actual_map.keys()):
        if expected_map[key] != actual_map[key]:
            errors.append(f"Projected connection does not match evidence: {key}")
    dangling = conn.execute(
        """
        SELECT g.source_person_id, g.target_person_id
        FROM graph_connections g
        LEFT JOIN persons source ON source.person_id = g.source_person_id
        LEFT JOIN persons target ON target.person_id = g.target_person_id
        WHERE source.person_id IS NULL OR target.person_id IS NULL
        """
    ).fetchall()
    for row in dangling:
        errors.append(
            f"Dangling projected connection: {row['source_person_id']} -> {row['target_person_id']}"
        )
    self_edges = conn.execute(
        "SELECT source_person_id FROM graph_connections WHERE source_person_id = target_person_id"
    ).fetchall()
    for row in self_edges:
        errors.append(f"Illegal projected self-edge: {row['source_person_id']}")
    return {
        "valid": not errors,
        "errors": errors,
        "active_evidence_count": active_evidence_count,
        "expected_connection_count": len(expected),
        "actual_connection_count": len(actual),
    }


def _require_observation(conn: sqlite3.Connection, observation_id: str) -> sqlite3.Row:
    normalized_id = str(observation_id).strip()
    if not normalized_id:
        raise ValueError("Observation ID is required")
    row = conn.execute(
        "SELECT * FROM observations WHERE observation_id = ?", (normalized_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown observation: {normalized_id}")
    return row


def _require_draft_observation(conn: sqlite3.Connection, observation_id: str) -> sqlite3.Row:
    row = _require_observation(conn, observation_id)
    if row["status"] != "DRAFT":
        raise ValueError("Finalized observations cannot be changed")
    return row


def _require_existing_media(
    conn: sqlite3.Connection,
    media_id: str,
    media_path: str | None,
) -> None:
    candidates = {media_id}
    if media_path:
        candidates.add(media_path)
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    references = (
        ("recognition_details", "image_id"),
        ("recognition_details", "image_path"),
        ("embeddings", "source_image"),
        ("embeddings", "crop_path"),
        ("pending_additions", "source_image"),
        ("init_faces", "source_image"),
        ("init_faces", "crop_path"),
    )
    for table, column in references:
        if table not in tables:
            continue
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            continue
        for value in candidates:
            if conn.execute(
                f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (value,),
            ).fetchone() is not None:
                return
    raise KeyError(f"Unknown existing media: {media_id}")


def _attach_observation_media(
    conn: sqlite3.Connection,
    observation_id: str,
    media_id: str,
    media_path: str | None,
    source: str | None,
    operation_id: str,
) -> tuple[ObservationMedia, bool]:
    normalized_media_id = str(media_id).strip()
    if not normalized_media_id:
        raise ValueError("Media ID is required")
    normalized_media_path = _optional_text(media_path)
    existing = conn.execute(
        """
        SELECT observation_id, media_id, media_path, source, operation_id, created_at
        FROM observation_media WHERE observation_id = ? AND media_id = ?
        """,
        (observation_id, normalized_media_id),
    ).fetchone()
    if existing is not None:
        return _observation_media_from_row(existing), False
    _require_existing_media(conn, normalized_media_id, normalized_media_path)
    created_at = utc_now()
    conn.execute(
        """
        INSERT INTO observation_media(
            observation_id, media_id, media_path, source, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            normalized_media_id,
            normalized_media_path,
            _optional_text(source),
            operation_id,
            created_at,
        ),
    )
    row = conn.execute(
        """
        SELECT observation_id, media_id, media_path, source, operation_id, created_at
        FROM observation_media WHERE observation_id = ? AND media_id = ?
        """,
        (observation_id, normalized_media_id),
    ).fetchone()
    return _observation_media_from_row(row), True


def _add_observation_participant(
    conn: sqlite3.Connection,
    observation_id: str,
    person_id: str,
    source: str | None,
    operation_id: str,
) -> tuple[ObservationParticipant, bool]:
    normalized_person_id = str(person_id).strip()
    if not normalized_person_id:
        raise ValueError("Person ID is required")
    if conn.execute(
        "SELECT 1 FROM persons WHERE person_id = ?", (normalized_person_id,),
    ).fetchone() is None:
        raise KeyError(f"Unknown person: {normalized_person_id}")
    canonical_person_id = _resolve_canonical_person_id(conn, normalized_person_id)
    existing_rows = conn.execute(
        """
        SELECT p.observation_id, p.person_id, p.source, p.operation_id, p.created_at,
               person.lifecycle_status
        FROM observation_participants p
        JOIN persons person ON person.person_id = p.person_id
        WHERE p.observation_id = ?
        ORDER BY p.created_at, p.person_id
        """,
        (observation_id,),
    ).fetchall()
    for row in existing_rows:
        existing = _observation_participant_from_row(conn, row)
        if existing.person_id == normalized_person_id:
            return existing, False
        if existing.canonical_person_id == canonical_person_id:
            return existing, False
    created_at = utc_now()
    conn.execute(
        """
        INSERT INTO observation_participants(
            observation_id, person_id, source, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            normalized_person_id,
            _optional_text(source),
            operation_id,
            created_at,
        ),
    )
    row = conn.execute(
        """
        SELECT p.observation_id, p.person_id, p.source, p.operation_id, p.created_at,
               person.lifecycle_status
        FROM observation_participants p
        JOIN persons person ON person.person_id = p.person_id
        WHERE p.observation_id = ? AND p.person_id = ?
        """,
        (observation_id, normalized_person_id),
    ).fetchone()
    return _observation_participant_from_row(conn, row), True


def _list_observation_media(
    conn: sqlite3.Connection, observation_id: str,
) -> list[ObservationMedia]:
    rows = conn.execute(
        """
        SELECT observation_id, media_id, media_path, source, operation_id, created_at
        FROM observation_media
        WHERE observation_id = ?
        ORDER BY created_at, media_id
        """,
        (observation_id,),
    ).fetchall()
    return [_observation_media_from_row(row) for row in rows]


def _insert_identity_correction(
    conn: sqlite3.Connection,
    *,
    correction_type: str,
    observation_id: str | None,
    face_assignment_id: str | None,
    embedding_id: str | None,
    from_person_id: str,
    to_person_id: str,
    operation_id: str,
) -> str:
    correction_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "|".join((
            "sentriface-correction", operation_id, correction_type,
            observation_id or "", face_assignment_id or "", embedding_id or "",
            from_person_id, to_person_id,
        )),
    ))
    conn.execute(
        """
        INSERT INTO identity_corrections(
            correction_id, correction_type, observation_id, face_assignment_id,
            embedding_id, from_person_id, to_person_id, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            correction_id, correction_type, observation_id, face_assignment_id,
            embedding_id, from_person_id, to_person_id, operation_id, utc_now(),
        ),
    )
    return correction_id


def _identity_correction_from_row(row: sqlite3.Row) -> IdentityCorrection:
    return IdentityCorrection(
        correction_id=str(row["correction_id"]),
        correction_type=str(row["correction_type"]),
        observation_id=row["observation_id"],
        face_assignment_id=row["face_assignment_id"],
        embedding_id=row["embedding_id"],
        from_person_id=str(row["from_person_id"]),
        to_person_id=str(row["to_person_id"]),
        operation_id=str(row["operation_id"]),
        created_at=str(row["created_at"]),
    )


def _effective_face_assignments(
    conn: sqlite3.Connection, observation_id: str,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT assignment_id, observation_id, face_id, embedding_id, original_person_id
        FROM observation_face_assignments
        WHERE observation_id = ? ORDER BY face_id, assignment_id
        """,
        (observation_id,),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        correction = conn.execute(
            """
            SELECT to_person_id FROM identity_corrections
            WHERE face_assignment_id = ? AND correction_type = 'FACE_ASSIGNMENT'
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (row["assignment_id"],),
        ).fetchone()
        result.append({
            "assignment_id": str(row["assignment_id"]),
            "observation_id": str(row["observation_id"]),
            "face_id": str(row["face_id"]),
            "embedding_id": str(row["embedding_id"]),
            "original_person_id": str(row["original_person_id"]),
            "current_person_id": str(
                correction["to_person_id"] if correction else row["original_person_id"]
            ),
        })
    return result


def _corrected_observation_person_ids(
    conn: sqlite3.Connection, observation_id: str,
) -> list[str]:
    base_ids = {
        str(row["person_id"])
        for row in conn.execute(
            "SELECT person_id FROM observation_participants WHERE observation_id = ?",
            (observation_id,),
        ).fetchall()
    }
    assignments = _effective_face_assignments(conn, observation_id)
    represented_original_ids = {item["original_person_id"] for item in assignments}
    effective_ids = base_ids - represented_original_ids
    effective_ids.update(item["current_person_id"] for item in assignments)
    participant_corrections = conn.execute(
        """
        SELECT from_person_id, to_person_id
        FROM identity_corrections
        WHERE observation_id = ? AND correction_type = 'OBSERVATION_IDENTITY'
        ORDER BY created_at, rowid
        """,
        (observation_id,),
    ).fetchall()
    for correction in participant_corrections:
        from_person_id = str(correction["from_person_id"])
        if from_person_id in effective_ids:
            effective_ids.remove(from_person_id)
            effective_ids.add(str(correction["to_person_id"]))
    return sorted(effective_ids)


def _effective_observation_person_ids(
    conn: sqlite3.Connection, observation_id: str,
) -> list[str]:
    corrected_ids = _corrected_observation_person_ids(conn, observation_id)
    return sorted({
        _resolve_canonical_person_id(conn, raw_person_id)
        for raw_person_id in corrected_ids
    })


def _list_person_sightings(
    conn: sqlite3.Connection, canonical_person_id: str,
) -> list[Sighting]:
    sightings: list[Sighting] = []
    rows = conn.execute(
        """
        SELECT * FROM observations
        WHERE status = 'FINALIZED'
        ORDER BY COALESCE(observed_at, created_at) DESC, observation_id
        """
    ).fetchall()
    for row in rows:
        observation_id = str(row["observation_id"])
        effective_ids = tuple(_effective_observation_person_ids(conn, observation_id))
        if canonical_person_id not in effective_ids:
            continue
        raw_ids = tuple(sorted({
            str(item["person_id"])
            for item in conn.execute(
                "SELECT person_id FROM observation_participants WHERE observation_id = ?",
                (observation_id,),
            ).fetchall()
        }))
        correction_ids = tuple(
            str(item["operation_id"])
            for item in conn.execute(
                """
                SELECT DISTINCT operation_id FROM identity_corrections
                WHERE observation_id = ?
                ORDER BY created_at, operation_id
                """,
                (observation_id,),
            ).fetchall()
        )
        sightings.append(Sighting(
            sighting_id=f"{observation_id}:{canonical_person_id}",
            observation_id=observation_id,
            canonical_person_id=canonical_person_id,
            observed_at=str(row["observed_at"] or row["created_at"]),
            location=_optional_text(row["location"]),
            context=json.loads(row["context"] or "{}"),
            source=_optional_text(row["source"]),
            finalized_at=_optional_text(row["finalized_at"]),
            media=tuple(_list_observation_media(conn, observation_id)),
            raw_participant_person_ids=raw_ids,
            effective_participant_person_ids=effective_ids,
            correction_operation_ids=correction_ids,
        ))
    return sightings


def _presence_analytics(sightings: list[Sighting]) -> PresenceAnalytics:
    if not sightings:
        return PresenceAnalytics(
            observation_count=0,
            first_seen_at=None,
            last_seen_at=None,
            frequency_per_30_days=0.0,
            frequency_label="Never Seen",
            provenance=(
                "observations.status=FINALIZED",
                "effective corrected/canonical observation participants",
            ),
        )
    ordered = sorted(sightings, key=lambda item: (item.observed_at, item.observation_id))
    first_seen_at = ordered[0].observed_at
    last_seen_at = ordered[-1].observed_at
    try:
        first = datetime.fromisoformat(first_seen_at.replace("Z", "+00:00"))
        last = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
        active_days = max(1.0, (last - first).total_seconds() / 86_400 + 1)
    except (TypeError, ValueError):
        active_days = 30.0
    frequency = round(len(ordered) / max(1.0, active_days / 30.0), 3)
    if frequency >= 8:
        frequency_label = "Very Frequent"
    elif frequency >= 3:
        frequency_label = "Frequent"
    elif frequency >= 1:
        frequency_label = "Occasional"
    else:
        frequency_label = "Rare"
    periods: dict[str, int] = {}
    locations: dict[str, dict[str, object]] = {}
    for sighting in ordered:
        period = sighting.observed_at[:7]
        periods[period] = periods.get(period, 0) + 1
        if sighting.location:
            item = locations.setdefault(sighting.location, {
                "count": 0, "last_observed_at": sighting.observed_at,
            })
            item["count"] = int(item["count"]) + 1
            item["last_observed_at"] = max(
                str(item["last_observed_at"]), sighting.observed_at,
            )
    return PresenceAnalytics(
        observation_count=len(ordered),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        frequency_per_30_days=frequency,
        frequency_label=frequency_label,
        timeline=tuple(TemporalCount(period=period, count=count)
                       for period, count in sorted(periods.items())),
        locations=tuple(sorted((
            LocationCount(
                location=location,
                count=int(values["count"]),
                last_observed_at=str(values["last_observed_at"]),
            )
            for location, values in locations.items()
        ), key=lambda item: (-item.count, item.location.casefold()))),
        provenance=(
            "observations.status=FINALIZED",
            "observations.observed_at (created_at fallback)",
            "effective corrected/canonical observation participants",
        ),
    )


def _person_relationship_analytics(
    conn: sqlite3.Connection, canonical_person_id: str,
) -> tuple[RelationshipAnalytics, ...]:
    aggregates: dict[tuple[str, str, str, str], list[RelationshipEvidence]] = {}
    rows = conn.execute(
        "SELECT * FROM relationship_evidence WHERE active = 1 ORDER BY created_at, evidence_id"
    ).fetchall()
    for row in rows:
        source_id = _resolve_canonical_person_id(conn, str(row["source_person_id"]))
        target_id = _resolve_canonical_person_id(conn, str(row["target_person_id"]))
        if source_id == target_id:
            continue
        if row["directionality"] == "UNDIRECTED":
            source_id, target_id = sorted((source_id, target_id))
        if canonical_person_id not in {source_id, target_id}:
            continue
        other_id = target_id if source_id == canonical_person_id else source_id
        key = (
            other_id,
            source_id,
            target_id,
            f"{row['relationship_type']}|{row['directionality']}",
        )
        aggregates.setdefault(key, []).append(_relationship_evidence_from_row(row))
    results: list[RelationshipAnalytics] = []
    for (other_id, source_id, target_id, relationship_key), evidence in aggregates.items():
        relationship_type, directionality = relationship_key.split("|", 1)
        type_counts: dict[str, int] = {}
        for item in evidence:
            type_counts[item.evidence_type] = type_counts.get(item.evidence_type, 0) + 1
        results.append(RelationshipAnalytics(
            person_id=other_id,
            source_person_id=source_id,
            target_person_id=target_id,
            relationship_type=relationship_type,
            directionality=directionality,
            evidence_count=len(evidence),
            evidence_type_counts=dict(sorted(type_counts.items())),
            first_evidence_at=min(item.created_at for item in evidence),
            last_evidence_at=max(item.created_at for item in evidence),
            co_observation_count=type_counts.get("CO_OBSERVED", 0),
            evidence=tuple(evidence),
        ))
    results.sort(key=lambda item: (item.last_evidence_at, item.person_id), reverse=True)
    results.sort(key=lambda item: item.evidence_count, reverse=True)
    return tuple(results)


def _recalculate_observation_evidence(
    conn: sqlite3.Connection,
    observation_id: str,
    operation_id: str,
    source: str,
) -> tuple[list[str], list[str]]:
    deactivated_at = utc_now()
    conn.execute(
        """
        UPDATE relationship_evidence
        SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
        WHERE evidence_type = 'CO_OBSERVED'
          AND source_entity_type = 'OBSERVATION'
          AND source_entity_id = ? AND active = 1
        """,
        (operation_id, deactivated_at, observation_id),
    )
    participant_ids = _effective_observation_person_ids(conn, observation_id)
    evidence_ids: list[str] = []
    created_at = utc_now()
    for index, first_person_id in enumerate(participant_ids):
        for second_person_id in participant_ids[index + 1:]:
            evidence_ids.append(_insert_relationship_evidence(
                conn,
                evidence_type="CO_OBSERVED",
                source_entity_type="OBSERVATION",
                source_entity_id=observation_id,
                evidence_revision_id=operation_id,
                source_person_id=first_person_id,
                target_person_id=second_person_id,
                relationship_type="ASSOCIATED_WITH",
                directionality="UNDIRECTED",
                source=source,
                created_operation_id=operation_id,
                created_at=created_at,
            ))
    _replace_graph_projection(conn)
    validation = _validate_graph_projection(conn)
    if not validation["valid"]:
        raise RuntimeError(
            "Graph projection validation failed: " + "; ".join(validation["errors"])
        )
    return participant_ids, evidence_ids


def _list_observation_participants(
    conn: sqlite3.Connection, observation_id: str,
) -> list[ObservationParticipant]:
    correction = conn.execute(
        """
        SELECT operation_id, created_at FROM identity_corrections
        WHERE observation_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
        """,
        (observation_id,),
    ).fetchone()
    participants: list[ObservationParticipant] = []
    for person_id in _effective_observation_person_ids(conn, observation_id):
        person = conn.execute(
            "SELECT lifecycle_status FROM persons WHERE person_id = ?", (person_id,),
        ).fetchone()
        participants.append(ObservationParticipant(
            observation_id=observation_id,
            person_id=person_id,
            canonical_person_id=person_id,
            person_lifecycle_status=str(person["lifecycle_status"]),
            source="identity-correction" if correction is not None else "canonical-resolution",
            operation_id=str(correction["operation_id"]) if correction is not None else "",
            created_at=str(correction["created_at"]) if correction is not None else "",
        ))
    return participants


def _list_raw_observation_participants(
    conn: sqlite3.Connection, observation_id: str,
) -> list[ObservationParticipant]:
    rows = conn.execute(
        """
        SELECT p.observation_id, p.person_id, p.source, p.operation_id, p.created_at,
               person.lifecycle_status
        FROM observation_participants p
        JOIN persons person ON person.person_id = p.person_id
        WHERE p.observation_id = ?
        ORDER BY p.created_at, p.person_id
        """,
        (observation_id,),
    ).fetchall()
    return [_observation_participant_from_row(conn, row) for row in rows]


def _observation_from_row(row: sqlite3.Row) -> Observation:
    return Observation(
        observation_id=row["observation_id"],
        status=row["status"],
        observed_at=row["observed_at"],
        location=row["location"],
        context=json.loads(row["context"]),
        source=row["source"],
        created_operation_id=row["created_operation_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finalized_at=row["finalized_at"],
    )


def _observation_media_from_row(row: sqlite3.Row) -> ObservationMedia:
    return ObservationMedia(
        observation_id=row["observation_id"],
        media_id=row["media_id"],
        media_path=row["media_path"],
        source=row["source"],
        operation_id=row["operation_id"],
        created_at=row["created_at"],
    )


def _observation_participant_from_row(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> ObservationParticipant:
    return ObservationParticipant(
        observation_id=row["observation_id"],
        person_id=row["person_id"],
        canonical_person_id=_resolve_canonical_person_id(conn, row["person_id"]),
        person_lifecycle_status=row["lifecycle_status"],
        source=row["source"],
        operation_id=row["operation_id"],
        created_at=row["created_at"],
    )


def _has_meaningful_identity_context(name: str, metadata: dict, notes: str) -> bool:
    if name.strip() or notes.strip():
        return True
    return any(value not in (None, "", [], {}, ()) for value in metadata.values())


def _profile_note_snapshot(conn: sqlite3.Connection, person_id: str) -> dict:
    row = conn.execute(
        """
        SELECT note_id FROM notes
        WHERE owner_person_id = ? AND is_profile_note = 1 AND status = 'ACTIVE'
        ORDER BY updated_at DESC, note_id LIMIT 1
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        return {"note_id": None, "content": "", "revision_number": 0, "mentions": ()}
    note = _note_from_row(conn, _note_row(conn, str(row["note_id"])))
    return {
        "note_id": note.note_id,
        "content": note.content,
        "revision_number": note.revision_number,
        "mentions": note.mentioned_person_ids,
    }


def _write_merge_profile_note_revision(
    conn: sqlite3.Connection,
    source_person_id: str,
    target_person_id: str,
    content: str,
    strategy: str,
    *,
    operation_id: str,
    actor: dict | None,
    source: str | None,
) -> None:
    source_note = _profile_note_snapshot(conn, source_person_id)
    target_note = _profile_note_snapshot(conn, target_person_id)
    if strategy == MergeConflictStrategy.KEEP_SOURCE.value:
        mention_ids = source_note["mentions"]
    elif strategy == MergeConflictStrategy.COMBINE.value:
        mention_ids = tuple(dict.fromkeys([
            *target_note["mentions"], *source_note["mentions"],
        ]))
    else:
        # USER_SELECTED content has no reliable parsed mention provenance.
        mention_ids = target_note["mentions"]
    mentions = _normalize_note_mentions(
        conn,
        target_person_id,
        list(mention_ids),
        historical_person_ids=set(mention_ids),
    )
    created_at = utc_now()
    note_id = target_note["note_id"] or str(uuid.uuid4())
    if target_note["note_id"] is None:
        conn.execute(
            """
            INSERT INTO notes(
                note_id, owner_person_id, subject_type, subject_id,
                is_profile_note, status, created_operation_id, created_at, updated_at
            ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?, ?)
            """,
            (note_id, target_person_id, target_person_id, operation_id, created_at, created_at),
        )
    revision_number = int(target_note["revision_number"]) + 1
    revision_id = _insert_note_revision(
        conn,
        note_id=note_id,
        revision_number=revision_number,
        content=content,
        mentions=mentions,
        actor=actor,
        author_name=str((actor or {}).get("display_name") or ""),
        operation_id=operation_id,
        created_at=created_at,
    )
    _sync_note_reference_evidence(
        conn,
        note_id=note_id,
        owner_person_id=target_person_id,
        revision_id=revision_id,
        mentions=mentions,
        operation_id=operation_id,
        source=source,
        created_at=created_at,
    )
    conn.execute("UPDATE notes SET updated_at = ? WHERE note_id = ?", (created_at, note_id))
    # Compatibility mirror is deliberately last: normalized revision is current truth.
    conn.execute("UPDATE persons SET notes = ? WHERE person_id = ?", (content, target_person_id))


def _preview_identity_merge(
    conn: sqlite3.Connection,
    source_person_id: str,
    target_person_id: str,
    *,
    exclude_operation_id: str | None = None,
) -> dict:
    source_id = str(source_person_id).strip()
    requested_target_id = str(target_person_id).strip()
    if not source_id or not requested_target_id:
        raise ValueError("Merge source and target IDs are required")
    source_row = conn.execute(
        "SELECT * FROM persons WHERE person_id = ?", (source_id,),
    ).fetchone()
    if source_row is None:
        raise KeyError(f"Unknown source person: {source_id}")
    if source_row["lifecycle_status"] not in {"ACTIVE", "ARCHIVED"}:
        raise KeyError("Merge source must be an active or archived identity")
    if source_row["deleted_at"] is not None and source_row["lifecycle_status"] != "ARCHIVED":
        raise KeyError("Deleted identities cannot be merged")
    try:
        terminal_target_id = _resolve_canonical_person_id(conn, requested_target_id)
    except KeyError as exc:
        raise KeyError(f"Unknown target person: {requested_target_id}") from exc
    if terminal_target_id == source_id:
        raise ValueError("Merge source and survivor must be different; cycle/self merge rejected")
    target_row = conn.execute(
        "SELECT * FROM persons WHERE person_id = ?", (terminal_target_id,),
    ).fetchone()
    if (
        target_row is None
        or target_row["lifecycle_status"] != "ACTIVE"
        or target_row["deleted_at"] is not None
        or target_row["canonical_person_id"] is not None
    ):
        raise KeyError("Merge target must resolve to a terminal active canonical survivor")
    component_ids = sorted(
        str(row["person_id"])
        for row in conn.execute("SELECT person_id FROM persons ORDER BY person_id").fetchall()
        if _resolve_canonical_person_id(conn, str(row["person_id"])) == source_id
    )
    if source_id not in component_ids:
        component_ids.append(source_id)
        component_ids.sort()
    conflicts = _proposed_merge_conflicts(conn, source_row, target_row)
    affected_items = _discover_merge_affected_items(
        conn, component_ids, source_id, terminal_target_id,
        exclude_operation_id=exclude_operation_id,
    )
    return {
        "source_person_id": source_id,
        "requested_target_person_id": requested_target_id,
        "target_person_id": terminal_target_id,
        "canonical_person_id": terminal_target_id,
        "source_lifecycle_status": str(source_row["lifecycle_status"]),
        "target_lifecycle_status": str(target_row["lifecycle_status"]),
        "source_component_person_ids": component_ids,
        "conflicts": conflicts,
        "proposed_conflict_resolutions": conflicts,
        "affected_items": affected_items,
        "affected_item_count": len(affected_items),
        "will_mutate": False,
    }


def _proposed_merge_conflicts(
    conn: sqlite3.Connection, source_row: sqlite3.Row, target_row: sqlite3.Row,
) -> list[dict]:
    source_metadata = json.loads(source_row["metadata"] or "{}")
    target_metadata = json.loads(target_row["metadata"] or "{}")
    ignored_metadata = {"merged_into", "merged_at"}
    source_note = _profile_note_snapshot(conn, str(source_row["person_id"]))
    target_note = _profile_note_snapshot(conn, str(target_row["person_id"]))
    fields: dict[str, tuple[object, object]] = {
        "name": (str(source_row["name"]), str(target_row["name"])),
        "notes": (source_note["content"], target_note["content"]),
    }
    for key in sorted((set(source_metadata) | set(target_metadata)) - ignored_metadata):
        fields[key] = (source_metadata.get(key), target_metadata.get(key))
    conflicts: list[dict] = []
    for field_name, (source_value, target_value) in fields.items():
        if source_value == target_value:
            continue
        combine_valid = field_name in {"tags", "favorite", "notes"}
        if field_name == "tags":
            strategy = MergeConflictStrategy.COMBINE.value
            selected_value = _normalize_tags([
                *(target_value or []), *(source_value or []),
            ])
        elif field_name == "favorite":
            strategy = MergeConflictStrategy.COMBINE.value
            selected_value = bool(source_value or target_value)
        elif field_name == "notes" and source_value and target_value:
            strategy = MergeConflictStrategy.COMBINE.value
            selected_value = (
                target_value if source_value == target_value
                else f"{target_value}\n\n{source_value}"
            )
        elif target_value in (None, "", [], {}):
            strategy = MergeConflictStrategy.KEEP_SOURCE.value
            selected_value = source_value
        else:
            strategy = MergeConflictStrategy.KEEP_TARGET.value
            selected_value = target_value
        conflicts.append({
            "conflict_id": str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"sentriface:merge-preview:{source_row['person_id']}:{target_row['person_id']}:{field_name}",
            )),
            "category": "PROFILE",
            "field_name": field_name,
            "source_value": source_value,
            "target_value": target_value,
            "strategy": strategy,
            "selected_value": selected_value,
            "combine_valid": combine_valid,
            "inverse_data": {
                "source_value": source_value,
                "target_value": target_value,
                "target_field_existed": (
                    field_name in {"name", "notes"} or field_name in target_metadata
                ),
            },
        })
    return conflicts


def _discover_merge_affected_items(
    conn: sqlite3.Connection,
    source_component_ids: list[str],
    source_person_id: str,
    target_person_id: str,
    *,
    exclude_operation_id: str | None = None,
) -> list[dict]:
    component = set(source_component_ids)
    items: dict[tuple[str, str], dict] = {}

    def add(
        item_type: str,
        item_id: object,
        raw_owner: str | None = None,
        *,
        action: str = MergeAffectedAction.UNION_IN_CURRENT_VIEW.value,
        before: dict | None = None,
        after: dict | None = None,
        context: dict | None = None,
    ) -> None:
        normalized_id = str(item_id)
        key = (item_type, normalized_id)
        items[key] = {
            "item_type": item_type,
            "item_id": normalized_id,
            "raw_owner_person_id": raw_owner,
            "effective_owner_person_id": target_person_id,
            "action": action,
            "before_state": before or ({"raw_owner_person_id": raw_owner} if raw_owner else {}),
            "after_state": after or {"canonical_person_id": target_person_id},
            "context": {"raw_provenance_retained": True, **(context or {})},
        }

    source = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (source_person_id,),
    ).fetchone()
    add(
        "PERSON", source_person_id, source_person_id,
        action=MergeAffectedAction.REINTERPRET_CANONICAL_OWNER.value,
        before={
            "lifecycle_status": source["lifecycle_status"],
            "canonical_person_id": source["canonical_person_id"],
        },
        after={"lifecycle_status": "MERGED", "canonical_person_id": target_person_id},
    )
    placeholders = ",".join("?" for _ in source_component_ids)
    args = tuple(source_component_ids)

    for row in conn.execute(
        f"SELECT * FROM embeddings WHERE person_id IN ({placeholders}) ORDER BY embedding_id", args,
    ).fetchall():
        owner = _raw_embedding_owner_person_id(conn, row)
        add("EMBEDDING", row["embedding_id"], owner, context={"deleted_at": row["deleted_at"]})
        for path_kind in ("source_image", "crop_path"):
            if row[path_kind]:
                add(
                    "PHOTO", f"{row['embedding_id']}:{path_kind}", owner,
                    context={"path_kind": path_kind, "path": row[path_kind]},
                )
    target_state = conn.execute(
        "SELECT biometric_status, enrollment_status FROM persons WHERE person_id = ?",
        (target_person_id,),
    ).fetchone()
    component_has_active_embedding = conn.execute(
        f"SELECT 1 FROM embeddings WHERE person_id IN ({placeholders}) AND deleted_at IS NULL LIMIT 1",
        args,
    ).fetchone() is not None
    if component_has_active_embedding and target_state["biometric_status"] != "ENROLLED":
        add(
            "CURRENT_STATE", "survivor-biometric-status", target_person_id,
            action=MergeAffectedAction.SELECT_VALUE.value,
            before={
                "biometric_status": target_state["biometric_status"],
                "enrollment_status": target_state["enrollment_status"],
            },
            after={"biometric_status": "ENROLLED", "enrollment_status": "enrolled"},
            context={"derived_from_preserved_embeddings": True},
        )
    for row in conn.execute(
        f"SELECT * FROM init_face_person_exclusions WHERE person_id IN ({placeholders}) ORDER BY session_id, init_face_id, person_id",
        args,
    ).fetchall():
        add(
            "RECOGNITION_EXCLUSION",
            f"{row['session_id']}:{row['init_face_id']}:{row['person_id']}",
            str(row["person_id"]), action=MergeAffectedAction.REINTERPRET_CANONICAL_OWNER.value,
        )
    for row in conn.execute(
        f"SELECT * FROM recognition_details WHERE person_id IN ({placeholders}) ORDER BY detail_id", args,
    ).fetchall():
        add("RECOGNITION_HISTORY", row["detail_id"], str(row["person_id"]))
    for row in conn.execute(
        f"SELECT * FROM person_change_history WHERE person_id IN ({placeholders}) ORDER BY change_id", args,
    ).fetchall():
        add("PROFILE_HISTORY", row["change_id"], str(row["person_id"]), action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute(
        f"SELECT * FROM biometric_enrollment_history WHERE person_id IN ({placeholders}) ORDER BY enrollment_id", args,
    ).fetchall():
        add("ENROLLMENT_HISTORY", row["enrollment_id"], str(row["person_id"]), action=MergeAffectedAction.PRESERVE.value)
    affected_observation_ids: set[str] = set()
    for row in conn.execute("SELECT * FROM observations ORDER BY observation_id").fetchall():
        corrected = _corrected_observation_person_ids(conn, str(row["observation_id"]))
        if any(person_id in component for person_id in corrected):
            affected_observation_ids.add(str(row["observation_id"]))
            add("OBSERVATION", row["observation_id"], context={"corrected_person_ids": corrected})
    for row in conn.execute("SELECT * FROM observation_media ORDER BY observation_id, media_id").fetchall():
        if str(row["observation_id"]) in affected_observation_ids:
            add(
                "OBSERVATION_MEDIA", f"{row['observation_id']}:{row['media_id']}",
                action=MergeAffectedAction.PRESERVE.value,
            )
    for row in conn.execute(
        f"SELECT * FROM observation_participants WHERE person_id IN ({placeholders}) ORDER BY observation_id, person_id",
        args,
    ).fetchall():
        add(
            "OBSERVATION_PARTICIPANT",
            f"{row['observation_id']}:{row['person_id']}",
            str(row["person_id"]),
            context={"observation_id": row["observation_id"]},
        )
    for row in conn.execute("SELECT * FROM identity_corrections ORDER BY correction_id").fetchall():
        if str(row["from_person_id"]) in component or str(row["to_person_id"]) in component:
            add("CORRECTION", row["correction_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM observation_face_assignments ORDER BY assignment_id").fetchall():
        if str(row["original_person_id"]) in component:
            add(
                "OBSERVATION_FACE_ASSIGNMENT", row["assignment_id"],
                str(row["original_person_id"]), action=MergeAffectedAction.PRESERVE.value,
            )
    for row in conn.execute("SELECT * FROM photo_review_faces ORDER BY review_id, face_id").fetchall():
        if row["person_id"] is not None and str(row["person_id"]) in component:
            add(
                "PHOTO_REVIEW_DECISION", f"{row['review_id']}:{row['face_id']}",
                str(row["person_id"]), action=MergeAffectedAction.PRESERVE.value,
            )
    note_ids: set[str] = set()
    for row in conn.execute("SELECT * FROM notes ORDER BY note_id").fetchall():
        owner = str(row["owner_person_id"])
        if owner in component or (row["subject_type"] == "PERSON" and str(row["subject_id"]) in component):
            note_ids.add(str(row["note_id"]))
            add("NOTE", row["note_id"], owner)
    for row in conn.execute("SELECT * FROM note_mentions ORDER BY mention_id").fetchall():
        if str(row["referenced_person_id"]) in component or str(row["note_id"]) in note_ids:
            note_id = str(row["note_id"])
            if note_id not in note_ids:
                note = conn.execute(
                    "SELECT owner_person_id FROM notes WHERE note_id = ?", (note_id,),
                ).fetchone()
                if note is not None:
                    note_ids.add(note_id)
                    add("NOTE", note_id, str(note["owner_person_id"]))
            add("NOTE_MENTION", row["mention_id"], str(row["referenced_person_id"]))
    if note_ids:
        note_placeholders = ",".join("?" for _ in note_ids)
        for row in conn.execute(
            f"SELECT * FROM note_revisions WHERE note_id IN ({note_placeholders}) ORDER BY revision_id",
            tuple(sorted(note_ids)),
        ).fetchall():
            add("NOTE_REVISION", row["revision_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM note_revision_mentions ORDER BY revision_id, referenced_person_id").fetchall():
        if str(row["referenced_person_id"]) in component:
            add(
                "NOTE_REVISION_MENTION",
                f"{row['revision_id']}:{row['referenced_person_id']}",
                str(row["referenced_person_id"]), action=MergeAffectedAction.PRESERVE.value,
            )
    affected_graph_people = component | {target_person_id}
    for row in conn.execute("SELECT * FROM relationship_evidence ORDER BY evidence_id").fetchall():
        if str(row["source_person_id"]) in affected_graph_people or str(row["target_person_id"]) in affected_graph_people:
            add("GRAPH_EVIDENCE", row["evidence_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM person_associations ORDER BY association_id").fetchall():
        if str(row["source_person_id"]) in component or str(row["target_person_id"]) in component:
            add("MANUAL_ASSOCIATION", row["association_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM merge_operations ORDER BY merge_operation_id").fetchall():
        if str(row["source_person_id"]) in component or str(row["target_person_id"]) in component:
            add("MERGE_HISTORY", row["merge_operation_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT operation_id, affected_entities FROM operation_journal ORDER BY operation_id").fetchall():
        if str(row["operation_id"]) == exclude_operation_id:
            continue
        entities = json.loads(row["affected_entities"] or "[]")
        if any(str(item.get("entity_id")) in component for item in entities if isinstance(item, dict)):
            add("OPERATION_HISTORY", row["operation_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT operation_id, result FROM person_operations ORDER BY operation_id").fetchall():
        payload = json.loads(row["result"] or "{}")
        if any(
            value in component
            for key, value in payload.items()
            if key.endswith("person_id") and isinstance(value, str)
        ):
            add("LEGACY_OPERATION_HISTORY", row["operation_id"], action=MergeAffectedAction.PRESERVE.value)
    return [items[key] for key in sorted(items)]


def _resolve_merge_conflicts(
    proposed: list[dict],
    requested: list[dict] | dict[str, dict | str] | None,
) -> list[dict]:
    overrides: dict[str, dict] = {}
    if isinstance(requested, dict):
        for field_name, value in requested.items():
            overrides[str(field_name)] = (
                dict(value) if isinstance(value, dict) else {"strategy": str(value)}
            )
    elif requested is not None:
        if not isinstance(requested, list):
            raise ValueError("Conflict resolutions must be a list or field mapping")
        for item in requested:
            if not isinstance(item, dict) or not str(item.get("field_name") or "").strip():
                raise ValueError("Each conflict resolution requires field_name")
            overrides[str(item["field_name"])] = dict(item)
    result: list[dict] = []
    known_fields = {str(item["field_name"]) for item in proposed}
    unknown_fields = set(overrides) - known_fields
    if unknown_fields:
        raise ValueError("Unknown merge conflict fields: " + ", ".join(sorted(unknown_fields)))
    for conflict in proposed:
        resolved = dict(conflict)
        override = overrides.get(str(conflict["field_name"]), {})
        strategy = str(override.get("strategy") or resolved["strategy"]).strip().upper()
        try:
            typed_strategy = MergeConflictStrategy(strategy)
        except ValueError as exc:
            raise ValueError(f"Unsupported merge conflict strategy: {strategy}") from exc
        if typed_strategy is MergeConflictStrategy.KEEP_SOURCE:
            selected = conflict["source_value"]
        elif typed_strategy is MergeConflictStrategy.KEEP_TARGET:
            selected = conflict["target_value"]
        elif typed_strategy is MergeConflictStrategy.COMBINE:
            if not conflict.get("combine_valid"):
                raise ValueError(f"COMBINE is not valid for profile field {conflict['field_name']}")
            selected = _combine_merge_value(
                str(conflict["field_name"]), conflict["source_value"], conflict["target_value"],
            )
        else:
            if "selected_value" not in override:
                raise ValueError(
                    f"USER_SELECTED requires selected_value for {conflict['field_name']}"
                )
            selected = override["selected_value"]
        resolved["strategy"] = typed_strategy.value
        resolved["selected_value"] = selected
        resolved.pop("combine_valid", None)
        result.append(resolved)
    return result


def _combine_merge_value(field_name: str, source_value, target_value):
    if field_name == "tags":
        return _normalize_tags([*(target_value or []), *(source_value or [])])
    if field_name == "favorite":
        return bool(source_value or target_value)
    if field_name == "notes":
        parts = [str(value).strip() for value in (target_value, source_value) if str(value or "").strip()]
        return "\n\n".join(dict.fromkeys(parts))
    raise ValueError(f"COMBINE is not valid for profile field {field_name}")


def _merge_inventory_with_profile_changes(
    inventory: list[dict], conflicts: list[dict], source_person_id: str, target_person_id: str,
) -> list[dict]:
    result = [dict(item) for item in inventory]
    for conflict in conflicts:
        result.append({
            "item_type": "PROFILE_FIELD",
            "item_id": str(conflict["field_name"]),
            "raw_owner_person_id": source_person_id,
            "effective_owner_person_id": target_person_id,
            "action": MergeAffectedAction.SELECT_VALUE.value,
            "before_state": {
                "source_value": conflict["source_value"],
                "target_value": conflict["target_value"],
            },
            "after_state": {"resulting_value": conflict["selected_value"]},
            "context": {"strategy": conflict["strategy"], "raw_provenance_retained": True},
        })
    return sorted(result, key=lambda item: (item["item_type"], item["item_id"]))


def _apply_merge_profile_resolutions(
    conn: sqlite3.Connection,
    source_person_id: str,
    target_person_id: str,
    conflicts: list[dict],
    *,
    operation_id: str,
    actor: dict | None,
    source: str | None,
) -> None:
    row = conn.execute(
        "SELECT name, notes, metadata FROM persons WHERE person_id = ?", (target_person_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown merge survivor: {target_person_id}")
    name = str(row["name"])
    metadata = json.loads(row["metadata"] or "{}")
    selected_notes: str | None = None
    note_strategy: str | None = None
    for conflict in conflicts:
        field_name = str(conflict["field_name"])
        selected = conflict["selected_value"]
        if field_name == "name":
            name = str(selected or "").strip()
            if not name:
                raise ValueError("Merge survivor name cannot be empty")
        elif field_name == "notes":
            selected_notes = str(selected or "").strip()
            note_strategy = str(conflict["strategy"])
        else:
            if selected is None and not conflict["inverse_data"].get("target_field_existed"):
                metadata.pop(field_name, None)
            else:
                metadata[field_name] = selected
    conn.execute(
        "UPDATE persons SET name = ?, metadata = ? WHERE person_id = ?",
        (name, json.dumps(metadata, separators=(",", ":"), sort_keys=True), target_person_id),
    )
    if selected_notes is not None and note_strategy is not None:
        _write_merge_profile_note_revision(
            conn,
            source_person_id,
            target_person_id,
            selected_notes,
            note_strategy,
            operation_id=operation_id,
            actor=actor,
            source=source,
        )


def _synchronize_survivor_biometric_state(
    conn: sqlite3.Connection, target_person_id: str,
) -> None:
    has_embedding = any(
        _effective_embedding_owner_person_id(conn, row) == target_person_id
        for row in conn.execute(
            "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
        ).fetchall()
    )
    if has_embedding:
        conn.execute(
            "UPDATE persons SET biometric_status = 'ENROLLED', enrollment_status = 'enrolled' WHERE person_id = ?",
            (target_person_id,),
        )


def _list_embeddings_in_transaction(conn: sqlite3.Connection) -> list[EmbeddingRecord]:
    records: list[EmbeddingRecord] = []
    for row in conn.execute(
        """
        SELECT embedding_id, person_id, vector, quality_score,
               source_image, crop_path, created_at
        FROM embeddings WHERE deleted_at IS NULL ORDER BY embedding_id
        """
    ).fetchall():
        canonical_person_id = _effective_embedding_owner_person_id(conn, row)
        canonical = conn.execute(
            "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
            (canonical_person_id,),
        ).fetchone()
        if canonical and canonical["lifecycle_status"] == "ACTIVE" and canonical["deleted_at"] is None:
            records.append(_embedding_from_row(
                row,
                raw_person_id=_raw_embedding_owner_person_id(conn, row),
                canonical_person_id=canonical_person_id,
            ))
    return records


def _validate_merge_state(
    conn: sqlite3.Connection, source_person_id: str, target_person_id: str,
) -> dict:
    errors: list[str] = []
    source = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (source_person_id,),
    ).fetchone()
    target = conn.execute(
        "SELECT lifecycle_status, canonical_person_id, deleted_at FROM persons WHERE person_id = ?",
        (target_person_id,),
    ).fetchone()
    if source is None or source["lifecycle_status"] != "MERGED" or source["canonical_person_id"] != target_person_id:
        errors.append("Source is not mapped to the requested survivor")
    if target is None or target["lifecycle_status"] != "ACTIVE" or target["canonical_person_id"] is not None or target["deleted_at"] is not None:
        errors.append("Survivor is not terminal and active")
    try:
        if _resolve_canonical_person_id(conn, source_person_id) != target_person_id:
            errors.append("Canonical resolution does not reach the survivor")
    except (KeyError, RuntimeError, ValueError) as exc:
        errors.append(str(exc))
    graph = _validate_graph_projection(conn)
    errors.extend(graph["errors"])
    foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_keys:
        errors.append("Foreign key validation failed")
    return {"valid": not errors, "errors": errors, "graph": graph}


def _set_canonical_person_id_in_transaction(
    conn: sqlite3.Connection,
    person_id: str,
    canonical_person_id: str,
) -> dict:
    """Update canonical state on the caller's connection without journaling or committing."""
    normalized_person_id = str(person_id).strip()
    normalized_target_id = str(canonical_person_id).strip()
    if not normalized_person_id or not normalized_target_id:
        raise ValueError("Source and canonical person IDs are required")
    source_row = conn.execute(
        "SELECT lifecycle_status FROM persons WHERE person_id = ?",
        (normalized_person_id,),
    ).fetchone()
    if source_row is None:
        raise KeyError(f"Unknown person: {normalized_person_id}")
    if source_row["lifecycle_status"] not in {"ACTIVE", "ARCHIVED"}:
        raise KeyError("Only active or archived identities can receive a canonical mapping")
    resolved_target = _resolve_canonical_person_id(conn, normalized_target_id)
    if resolved_target == normalized_person_id:
        raise ValueError("Canonical identity cannot reference itself or create a cycle")
    target_row = conn.execute(
        "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
        (resolved_target,),
    ).fetchone()
    if target_row is None:
        raise KeyError(f"Unknown canonical person: {normalized_target_id}")
    if target_row["lifecycle_status"] != "ACTIVE" or target_row["deleted_at"] is not None:
        raise KeyError("Canonical identity must resolve to an active person")
    changed_at = utc_now()
    try:
        conn.execute(
            """
            UPDATE persons
            SET lifecycle_status = 'MERGED', canonical_person_id = ?,
                deleted_at = COALESCE(deleted_at, ?), lifecycle_changed_at = ?
            WHERE person_id = ?
            """,
            (resolved_target, changed_at, changed_at, normalized_person_id),
        )
    except sqlite3.IntegrityError as exc:
        if "cycle" in str(exc).lower() or "check constraint" in str(exc).lower():
            raise ValueError(
                "Canonical identity cannot reference itself or create a cycle"
            ) from exc
        raise
    return {
        "person_id": normalized_person_id,
        "canonical_person_id": resolved_target,
        "lifecycle_status": "MERGED",
        "mapped": True,
    }


def _insert_merge_manifest_in_transaction(
    conn: sqlite3.Connection,
    *,
    merge_operation_id: str,
    source_person_id: str,
    target_person_id: str,
    operation_journal_id: str,
    actor: dict | None = None,
    reason: str | None = None,
    context: dict | None = None,
    affected_items: list[dict] | None = None,
    conflicts: list[dict] | None = None,
    created_at: str | None = None,
) -> MergeOperation:
    """Persist immutable merge provenance on the caller-owned transaction."""
    normalized_merge_id = str(merge_operation_id).strip()
    normalized_source_id = str(source_person_id).strip()
    normalized_target_id = str(target_person_id).strip()
    normalized_journal_id = str(operation_journal_id).strip()
    if not all((normalized_merge_id, normalized_source_id, normalized_target_id,
                normalized_journal_id)):
        raise ValueError("Merge, source, target, and journal IDs are required")
    if normalized_merge_id != normalized_journal_id:
        raise ValueError("Merge operation ID must match its journal operation ID")
    terminal_target_id = _resolve_canonical_person_id(conn, normalized_target_id)
    if normalized_source_id == terminal_target_id:
        raise ValueError("Merge source and survivor must be different")
    source_row = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (normalized_source_id,),
    ).fetchone()
    target_row = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (terminal_target_id,),
    ).fetchone()
    if source_row is None or target_row is None:
        raise KeyError("Merge source and target must both exist")
    journal = conn.execute(
        "SELECT operation_type, status, actor FROM operation_journal WHERE operation_id = ?",
        (normalized_journal_id,),
    ).fetchone()
    if journal is None:
        raise KeyError(f"Unknown operation journal entry: {normalized_journal_id}")
    if journal["status"] != "STARTED":
        raise ValueError("Merge manifest must be recorded while its journal is STARTED")
    if journal["operation_type"] != "identity.merge":
        raise ValueError("Merge manifest requires an identity.merge journal operation")
    _, actor_payload, _ = _operation_actor_snapshot(actor)
    if actor_payload != journal["actor"]:
        raise ValueError("Merge manifest actor must match its operation journal actor")
    if target_row["lifecycle_status"] != "ACTIVE" or target_row["canonical_person_id"] is not None:
        raise ValueError("Merge survivor must be the terminal active canonical identity")
    target_deleted = conn.execute(
        "SELECT deleted_at FROM persons WHERE person_id = ?", (terminal_target_id,),
    ).fetchone()[0]
    if target_deleted is not None:
        raise ValueError("Merge survivor must be the terminal active canonical identity")
    _, context_payload = _journal_json_object(context, "merge context")
    timestamp = created_at or utc_now()
    conn.execute(
        """
        INSERT INTO merge_operations(
            merge_operation_id, source_person_id, target_person_id, actor, created_at,
            previous_source_lifecycle_status, previous_target_lifecycle_status,
            previous_source_canonical_person_id, previous_target_canonical_person_id,
            reason, context, operation_journal_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_merge_id, normalized_source_id, terminal_target_id,
            actor_payload, timestamp, source_row["lifecycle_status"],
            target_row["lifecycle_status"], source_row["canonical_person_id"],
            target_row["canonical_person_id"], _optional_text(reason),
            context_payload, normalized_journal_id,
        ),
    )
    for item in affected_items or []:
        item_type = str(item.get("item_type") or "").strip().upper()
        item_id = str(item.get("item_id") or "").strip()
        if not item_type or not item_id:
            raise ValueError("Affected merge items require item_type and item_id")
        raw_owner_person_id = _optional_text(
            item.get("raw_owner_person_id", item.get("previous_person_id")),
        )
        effective_owner_person_id = _optional_text(
            item.get("effective_owner_person_id", item.get("effective_person_id")),
        )
        default_action = (
            MergeAffectedAction.UNION_IN_CURRENT_VIEW.value
            if item_type in MERGE_COLLECTION_ITEM_TYPES
            else MergeAffectedAction.REINTERPRET_CANONICAL_OWNER.value
        )
        action = str(item.get("action") or default_action).strip().upper()
        try:
            MergeAffectedAction(action)
        except ValueError as exc:
            raise ValueError(f"Unsupported merge affected-item action: {action}") from exc
        _, item_context = _journal_json_object(item.get("context"), "affected item context")
        _, before_state = _journal_json_object(item.get("before_state"), "affected item before state")
        _, after_state = _journal_json_object(item.get("after_state"), "affected item after state")
        conn.execute(
            """
            INSERT INTO merge_affected_items(
                merge_operation_id, item_type, item_id, previous_person_id,
                effective_person_id, context, raw_owner_person_id,
                effective_owner_person_id, action, before_state, after_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_merge_id, item_type, item_id,
                raw_owner_person_id, effective_owner_person_id, item_context,
                raw_owner_person_id, effective_owner_person_id, action,
                before_state, after_state,
            ),
        )
    for conflict in conflicts or []:
        category = str(conflict.get("category") or "").strip().upper()
        field_name = str(conflict.get("field_name") or conflict.get("field") or "").strip()
        if not category or not field_name:
            raise ValueError("Merge conflicts require category and field_name")
        strategy_value = str(conflict.get("strategy") or "").strip().upper()
        try:
            strategy = MergeConflictStrategy(strategy_value)
        except ValueError as exc:
            raise ValueError(f"Unsupported merge conflict strategy: {strategy_value}") from exc
        source_value = conflict.get("source_value")
        target_value = conflict.get("target_value")
        selected_value = conflict.get("selected_value")
        if strategy is MergeConflictStrategy.KEEP_SOURCE and selected_value != source_value:
            raise ValueError("KEEP_SOURCE must select the source value")
        if strategy is MergeConflictStrategy.KEEP_TARGET and selected_value != target_value:
            raise ValueError("KEEP_TARGET must select the target value")
        inverse_data = conflict.get("inverse_data")
        if inverse_data is None:
            inverse_data = {
                "source_value": source_value,
                "target_value": target_value,
            }
        _, inverse_payload = _journal_json_object(inverse_data, "merge conflict inverse data")
        conn.execute(
            """
            INSERT INTO merge_conflict_resolutions(
                conflict_id, merge_operation_id, category, field_name,
                source_value, target_value, strategy, selected_value, inverse_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(conflict.get("conflict_id") or uuid.uuid4()), normalized_merge_id,
                category, field_name, _json_value_payload(source_value, "source value"),
                _json_value_payload(target_value, "target value"), strategy.value,
                _json_value_payload(selected_value, "selected value"), inverse_payload,
            ),
        )
    operation = _get_merge_operation(conn, normalized_merge_id)
    if operation is None:
        raise RuntimeError("Stored merge manifest could not be read")
    return operation


def _get_merge_operation(
    conn: sqlite3.Connection, merge_operation_id: str,
) -> MergeOperation | None:
    row = conn.execute(
        "SELECT * FROM merge_operations WHERE merge_operation_id = ?",
        (str(merge_operation_id).strip(),),
    ).fetchone()
    if row is None:
        return None
    item_rows = conn.execute(
        """
        SELECT * FROM merge_affected_items
        WHERE merge_operation_id = ? ORDER BY item_type, item_id
        """,
        (row["merge_operation_id"],),
    ).fetchall()
    conflict_rows = conn.execute(
        """
        SELECT * FROM merge_conflict_resolutions
        WHERE merge_operation_id = ? ORDER BY category, field_name, conflict_id
        """,
        (row["merge_operation_id"],),
    ).fetchall()
    return MergeOperation(
        merge_operation_id=str(row["merge_operation_id"]),
        source_person_id=str(row["source_person_id"]),
        target_person_id=str(row["target_person_id"]),
        actor=json.loads(row["actor"]),
        created_at=str(row["created_at"]),
        previous_source_lifecycle_status=str(row["previous_source_lifecycle_status"]),
        previous_target_lifecycle_status=str(row["previous_target_lifecycle_status"]),
        previous_source_canonical_person_id=row["previous_source_canonical_person_id"],
        previous_target_canonical_person_id=row["previous_target_canonical_person_id"],
        reason=row["reason"],
        context=json.loads(row["context"]),
        operation_journal_id=str(row["operation_journal_id"]),
        affected_items=tuple(MergeAffectedItem(
            item_type=str(item["item_type"]),
            item_id=str(item["item_id"]),
            raw_owner_person_id=item["raw_owner_person_id"],
            effective_owner_person_id=item["effective_owner_person_id"],
            action=MergeAffectedAction(str(item["action"])),
            before_state=json.loads(item["before_state"]),
            after_state=json.loads(item["after_state"]),
            context=json.loads(item["context"]),
        ) for item in item_rows),
        conflicts=tuple(MergeConflictResolution(
            conflict_id=str(item["conflict_id"]),
            category=str(item["category"]),
            field_name=str(item["field_name"]),
            source_value=json.loads(item["source_value"]),
            target_value=json.loads(item["target_value"]),
            strategy=MergeConflictStrategy(str(item["strategy"])),
            selected_value=json.loads(item["selected_value"]),
            inverse_data=json.loads(item["inverse_data"]),
        ) for item in conflict_rows),
    )


def _resolve_canonical_person_id(conn: sqlite3.Connection, person_id: str) -> str:
    current_id = str(person_id).strip()
    if not current_id:
        raise ValueError("Person ID is required")
    visited: set[str] = set()
    while True:
        if current_id in visited:
            raise RuntimeError("Canonical identity cycle detected")
        visited.add(current_id)
        row = conn.execute(
            "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
            (current_id,),
        ).fetchone()
        if row is None:
            if len(visited) == 1:
                raise KeyError(f"Unknown person: {current_id}")
            raise RuntimeError(f"Canonical identity target does not exist: {current_id}")
        canonical_person_id = row["canonical_person_id"]
        if row["lifecycle_status"] != "MERGED":
            if canonical_person_id is not None:
                raise RuntimeError("Non-merged identity has an invalid canonical mapping")
            return current_id
        if not canonical_person_id:
            raise RuntimeError("Merged identity has no canonical target")
        current_id = str(canonical_person_id)


def _person_historical_counts(conn: sqlite3.Connection, person_id: str) -> dict:
    return {
        "retained_embeddings": int(conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE person_id = ?", (person_id,),
        ).fetchone()[0]),
        "retained_sightings": int(conn.execute(
            "SELECT COUNT(*) FROM recognition_details WHERE person_id = ?", (person_id,),
        ).fetchone()[0]),
        "retained_profile_changes": int(conn.execute(
            "SELECT COUNT(*) FROM person_change_history WHERE person_id = ?", (person_id,),
        ).fetchone()[0]),
        "retained_associations": int(conn.execute(
            """
            SELECT COUNT(*) FROM person_associations
            WHERE source_person_id = ? OR target_person_id = ?
            """,
            (person_id, person_id),
        ).fetchone()[0]),
    }


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
            """
            SELECT 1 FROM persons
            WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
            """,
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


def _legacy_create_note_associations(
    conn: sqlite3.Connection,
    owner_person_id: str,
    notes: str,
    actor_name: str,
    explicit_person_ids: list[str],
) -> list[PersonAssociation]:
    if not explicit_person_ids:
        return []
    active_rows = conn.execute(
        """
        SELECT person_id, name FROM persons
        WHERE lifecycle_status = 'ACTIVE' AND deleted_at IS NULL AND person_id <> ?
        """,
        (owner_person_id,),
    ).fetchall()
    rows_by_id = {row["person_id"]: row for row in active_rows}
    mentioned_ids = {
        str(person_id)
        for person_id in explicit_person_ids
        if str(person_id) in rows_by_id
    }
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
        lifecycle_status=row["lifecycle_status"] if "lifecycle_status" in row.keys() else (
            "ARCHIVED" if row["deleted_at"] else "ACTIVE"
        ),
        canonical_person_id=(
            row["canonical_person_id"] if "canonical_person_id" in row.keys() else None
        ),
        identity_status=(row["identity_status"] if "identity_status" in row.keys() else "IDENTIFIED"),
        biometric_status=(row["biometric_status"] if "biometric_status" in row.keys() else "NO_FACE"),
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
        FROM persons
        WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown person: {person_id}")
    conn.execute(
        "UPDATE persons SET biometric_status = 'ENROLLED' WHERE person_id = ?",
        (person_id,),
    )
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


def _json_value_payload(value, label: str) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Merge {label} must be JSON-compatible") from exc


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


def _existing_committed_operation_result(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != operation_type:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    if operation["status"] != "COMMITTED":
        raise RuntimeError(
            f"Operation {operation_id} is {operation['status']} and cannot be retried"
        )
    history = operation["status_history"]
    return dict(history[-1]["details"]) if history else {}


_R01_REPAIR_ID = "P11C-R01-RESTORE-ARCHIVED-CANONICAL-SURVIVOR"
_R01_SPEC_VERSION = 1
_R01_INVARIANT_ID = "P11-IDENTITY-003"
_R01_FINGERPRINT_VERSION = "p11-a-schema28-repair-fingerprint-v1"
_R01_OPERATION_TYPE = "integrity.repair.canonical-survivor.restore"


def _r01_hash(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _r01_table_fingerprint(conn: sqlite3.Connection, table: str) -> str:
    allowed = {
        "graph_connections", "merge_operations", "merge_affected_items",
        "merge_conflict_resolutions",
    }
    if table not in allowed:
        raise ValueError("Unsupported R01 fingerprint table")
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    return _r01_hash([dict(row) for row in rows])


def _r01_canonical_fingerprint(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT person_id, canonical_person_id FROM persons ORDER BY person_id"
    ).fetchall()
    return _r01_hash([tuple(row) for row in rows])


def _r01_resolve_paths(
    conn: sqlite3.Connection, survivor_person_id: str,
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    people = {
        str(row["person_id"]): (str(row["lifecycle_status"]), row["canonical_person_id"])
        for row in conn.execute(
            "SELECT person_id, lifecycle_status, canonical_person_id FROM persons"
        )
    }
    paths: list[tuple[str, ...]] = []
    sources: list[str] = []
    for source_id, (lifecycle, target) in sorted(people.items()):
        if lifecycle != "MERGED":
            continue
        if not target:
            raise StructuredRepairRefused("R01 refused because a merged identity has no target")
        current = source_id
        path: list[str] = []
        seen: set[str] = set()
        while True:
            if current in seen:
                raise StructuredRepairRefused("R01 refused because a canonical cycle exists")
            seen.add(current)
            path.append(current)
            state = people.get(current)
            if state is None:
                raise StructuredRepairRefused("R01 refused because a canonical target is dangling")
            current_lifecycle, current_target = state
            if current_lifecycle != "MERGED":
                if current_target is not None:
                    raise StructuredRepairRefused(
                        "R01 refused because a non-merged identity has a canonical target"
                    )
                break
            if not current_target:
                raise StructuredRepairRefused("R01 refused because a canonical path is malformed")
            current = str(current_target)
        if current == survivor_person_id:
            sources.append(source_id)
            paths.append(tuple(path))
    return tuple(sources), tuple(paths)


def _r01_merge_snapshot(
    conn: sqlite3.Connection,
    sources: tuple[str, ...],
) -> tuple[tuple[str, ...], str]:
    operation_ids: list[str] = []
    for source_id in sources:
        direct_target = conn.execute(
            "SELECT canonical_person_id FROM persons WHERE person_id = ?",
            (source_id,),
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT m.*, j.operation_type, j.status, j.actor AS journal_actor
            FROM merge_operations m
            JOIN operation_journal j ON j.operation_id = m.operation_journal_id
            WHERE m.source_person_id = ? AND m.target_person_id = ?
            ORDER BY m.created_at, m.merge_operation_id
            """,
            (source_id, direct_target),
        ).fetchall()
        if len(rows) != 1:
            raise StructuredRepairRefused(
                "R01 refused because merge history does not uniquely support the path"
            )
        row = rows[0]
        if (
            row["operation_type"] != "identity.merge"
            or row["status"] != "COMMITTED"
            or row["actor"] != row["journal_actor"]
            or row["operation_journal_id"] != row["merge_operation_id"]
        ):
            raise StructuredRepairRefused(
                "R01 refused because merge manifest and journal history disagree"
            )
        operation_ids.append(str(row["merge_operation_id"]))
    ids = tuple(sorted(operation_ids))
    if not ids:
        raise StructuredRepairRefused("R01 requires at least one preserved merge manifest")
    placeholders = ",".join("?" for _ in ids)
    snapshot = {
        "operations": [dict(row) for row in conn.execute(
            f"SELECT * FROM merge_operations WHERE merge_operation_id IN ({placeholders}) ORDER BY merge_operation_id",
            ids,
        )],
        "items": [dict(row) for row in conn.execute(
            f"SELECT * FROM merge_affected_items WHERE merge_operation_id IN ({placeholders}) ORDER BY merge_operation_id, item_type, item_id",
            ids,
        )],
        "conflicts": [dict(row) for row in conn.execute(
            f"SELECT * FROM merge_conflict_resolutions WHERE merge_operation_id IN ({placeholders}) ORDER BY merge_operation_id, conflict_id",
            ids,
        )],
    }
    return ids, _r01_hash(snapshot)


def _r01_relevant_operation_fingerprint(
    conn: sqlite3.Connection, entity_ids: tuple[str, ...],
) -> str:
    selected: list[dict] = []
    wanted = set(entity_ids)
    for row in conn.execute(
        "SELECT operation_id, operation_type, status, affected_entities, created_at, completed_at FROM operation_journal ORDER BY rowid"
    ):
        try:
            affected = json.loads(row["affected_entities"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise StructuredRepairRefused("R01 refused because journal metadata is malformed") from exc
        if any(
            isinstance(item, dict) and str(item.get("entity_id")) in wanted
            for item in affected
        ):
            selected.append(dict(row))
    return _r01_hash(selected)


def _r01_precondition_from_report(
    conn: sqlite3.Connection,
    report: object,
    survivor_person_id: str,
) -> ArchivedCanonicalSurvivorRepairPrecondition:
    if report.schema_version != SCHEMA_VERSION or SCHEMA_VERSION != 28:
        raise StructuredRepairRefused("R01 requires schema version 28", report=report)
    if report.findings_truncated:
        raise StructuredRepairRefused("R01 requires an untruncated P11-A report", report=report)
    blocking = [
        item for item in report.findings
        if item.severity.value in {"CRITICAL", "ERROR"}
    ]
    selected = []
    for item in blocking:
        entities = dict(item.entity_ids)
        if (
            item.invariant_id != _R01_INVARIANT_ID
            or entities.get("terminal_person_id") != survivor_person_id
        ):
            raise StructuredRepairRefused(
                "R01 refused because another critical/error finding makes identity interpretation ambiguous",
                report=report,
            )
        selected.append(item)
    if not selected:
        raise StructuredRepairRefused(
            "R01 refused because the selected P11-IDENTITY-003 finding is absent",
            report=report,
        )
    graph_revision = _graph_revision_token(conn)
    if graph_revision != report.graph_revision:
        raise StructuredRepairRefused(
            "R01 refused because the graph revision changed after diagnosis", report=report,
        )
    row = conn.execute(
        """
        SELECT lifecycle_status, deleted_at, lifecycle_changed_at, canonical_person_id
        FROM persons WHERE person_id = ?
        """,
        (survivor_person_id,),
    ).fetchone()
    if row is None:
        raise StructuredRepairRefused("R01 survivor no longer exists", report=report)
    if (
        row["lifecycle_status"] != "ARCHIVED"
        or row["deleted_at"] is None
        or row["lifecycle_changed_at"] is None
        or row["canonical_person_id"] is not None
    ):
        raise StructuredRepairRefused(
            "R01 survivor is not the exact supported archived terminal state", report=report,
        )
    sources, paths = _r01_resolve_paths(conn, survivor_person_id)
    selected_sources = tuple(sorted(dict(item.entity_ids)["person_id"] for item in selected))
    if sources != selected_sources:
        raise StructuredRepairRefused(
            "R01 finding set does not cover every canonical path to the survivor", report=report,
        )
    merge_ids, merge_fingerprint = _r01_merge_snapshot(conn, sources)
    affected = tuple(sorted({survivor_person_id, *sources}))
    relevant_fingerprint = _r01_relevant_operation_fingerprint(conn, affected)
    finding_payload = [
        {
            "invariant_id": item.invariant_id,
            "message": item.message,
            "entity_ids": list(item.entity_ids),
            "evidence": list(item.evidence),
        }
        for item in sorted(selected, key=lambda value: value.entity_ids)
    ]
    state = {
        "survivor_person_id": survivor_person_id,
        "lifecycle_status": row["lifecycle_status"],
        "deleted_at": row["deleted_at"],
        "lifecycle_changed_at": row["lifecycle_changed_at"],
        "canonical_person_id": row["canonical_person_id"],
        "merge_sources": sources,
        "merge_paths": paths,
        "merge_operation_ids": merge_ids,
        "merge_state_fingerprint": merge_fingerprint,
        "relevant_operation_fingerprint": relevant_fingerprint,
    }
    fingerprint = _r01_hash({
        "checker_contract": _R01_FINGERPRINT_VERSION,
        "repair_id": _R01_REPAIR_ID,
        "repair_spec_version": _R01_SPEC_VERSION,
        "findings": finding_payload,
        "schema_version": report.schema_version,
        "graph_revision": graph_revision,
        "state": state,
    })
    return ArchivedCanonicalSurvivorRepairPrecondition(
        repair_id=_R01_REPAIR_ID,
        repair_spec_version=_R01_SPEC_VERSION,
        invariant_ids=(_R01_INVARIANT_ID,),
        affected_entity_ids=affected,
        survivor_person_id=survivor_person_id,
        finding_fingerprint_version=_R01_FINGERPRINT_VERSION,
        finding_fingerprint=fingerprint,
        schema_version=SCHEMA_VERSION,
        graph_revision=graph_revision,
        expected_lifecycle_status=str(row["lifecycle_status"]),
        expected_deleted_at=str(row["deleted_at"]),
        expected_lifecycle_changed_at=str(row["lifecycle_changed_at"]),
        expected_canonical_person_id=row["canonical_person_id"],
        merge_source_person_ids=sources,
        merge_paths=paths,
        merge_operation_ids=merge_ids,
        merge_state_fingerprint=merge_fingerprint,
        relevant_operation_fingerprint=relevant_fingerprint,
    )


def _validate_r01_request_shape(
    precondition: ArchivedCanonicalSurvivorRepairPrecondition,
) -> None:
    if not isinstance(precondition, ArchivedCanonicalSurvivorRepairPrecondition):
        raise ValueError("R01 requires its typed finding precondition")
    if (
        precondition.repair_id != _R01_REPAIR_ID
        or precondition.repair_spec_version != _R01_SPEC_VERSION
        or precondition.invariant_ids != (_R01_INVARIANT_ID,)
        or precondition.finding_fingerprint_version != _R01_FINGERPRINT_VERSION
        or precondition.schema_version != SCHEMA_VERSION
    ):
        raise StructuredRepairRefused("R01 request does not match the frozen repair specification")


def _r01_existing_result(
    conn: sqlite3.Connection,
    operation_id: str,
    precondition: ArchivedCanonicalSurvivorRepairPrecondition,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != _R01_OPERATION_TYPE:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    details = operation["details"]
    if (
        details.get("finding_fingerprint") != precondition.finding_fingerprint
        or details.get("repair_id") != precondition.repair_id
        or details.get("survivor_person_id") != precondition.survivor_person_id
    ):
        raise KeyError("Operation ID was already used for a different R01 diagnosis")
    if operation["status"] != "COMMITTED":
        raise RuntimeError(
            f"Operation {operation_id} is {operation['status']} and cannot be retried"
        )
    return dict(operation["status_history"][-1]["details"])


def _restore_archived_person_in_transaction(
    conn: sqlite3.Connection, person_id: str,
) -> sqlite3.Cursor:
    row = conn.execute(
        "SELECT lifecycle_status FROM persons WHERE person_id = ?", (person_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown person: {person_id}")
    if row["lifecycle_status"] != "ARCHIVED":
        raise KeyError(f"Only archived people can be restored: {person_id}")
    try:
        cursor = conn.execute(
            """
            UPDATE persons
            SET lifecycle_status = 'ACTIVE', deleted_at = NULL, lifecycle_changed_at = ?
            WHERE person_id = ? AND lifecycle_status = 'ARCHIVED'
            """,
            (utc_now(), person_id),
        )
    except sqlite3.IntegrityError as exc:
        raise _placeholder_name_conflict(exc) from exc
    if cursor.rowcount != 1:
        raise RuntimeError("Archived person lifecycle changed concurrently")
    return cursor


def _validate_r01_postconditions(
    conn: sqlite3.Connection,
    precondition: ArchivedCanonicalSurvivorRepairPrecondition,
    *,
    canonical_before: str,
    connections_before: str,
    merge_before: str,
    revision_before: str,
) -> dict:
    row = conn.execute(
        "SELECT lifecycle_status, deleted_at, canonical_person_id FROM persons WHERE person_id = ?",
        (precondition.survivor_person_id,),
    ).fetchone()
    if row is None or tuple(row) != ("ACTIVE", None, None):
        raise RuntimeError("R01 immediate lifecycle postcondition failed")
    sources, paths = _r01_resolve_paths(conn, precondition.survivor_person_id)
    merge_ids, merge_after = _r01_merge_snapshot(conn, sources)
    if (
        sources != precondition.merge_source_person_ids
        or paths != precondition.merge_paths
        or merge_ids != precondition.merge_operation_ids
        or merge_after != merge_before
        or _r01_canonical_fingerprint(conn) != canonical_before
    ):
        raise RuntimeError("R01 changed canonical or merge history")
    if _r01_table_fingerprint(conn, "graph_connections") != connections_before:
        raise RuntimeError("R01 unexpectedly changed the graph projection")
    projection = _validate_graph_projection(conn)
    if not projection["valid"]:
        raise RuntimeError("R01 graph validation failed: " + "; ".join(projection["errors"][:10]))
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("R01 foreign-key postcondition failed")
    before_number = int(revision_before[1:])
    revision_after = _graph_revision_token(conn)
    if revision_after != f"g{before_number + 1}":
        raise RuntimeError("R01 must advance graph revision exactly once")
    return {"graph_revision_after": revision_after, "projection": projection}


_R02_REPAIR_ID = "P11C-R02-RECONCILE-NOTE-REFERENCE-STATE"
_R02_SPEC_VERSION = 1
_R02_FINGERPRINT_VERSION = "p11-a-schema28-repair-fingerprint-v1"
_R02_OPERATION_TYPE = "integrity.repair.note-reference.reconcile"
_R02_ALLOWED_INVARIANTS = {
    "P11-NOTE-002", "P11-NOTE-003", "P11-EVIDENCE-001", "P11-GRAPH-001",
}
_R02_STALE_EVIDENCE_MESSAGE = (
    "active evidence has no current active note mention source"
)


def _r02_failure_checkpoint(_phase: str) -> None:
    """Patchable transaction checkpoint used only by focused rollback tests."""


def _r02_rows_fingerprint(rows: list[sqlite3.Row]) -> str:
    return _r01_hash([dict(row) for row in rows])


def _r02_revision_snapshot(
    conn: sqlite3.Connection, note_id: str,
) -> tuple[sqlite3.Row, tuple[str, ...], str]:
    note = conn.execute(
        "SELECT * FROM notes WHERE note_id = ?", (note_id,),
    ).fetchone()
    if note is None:
        raise StructuredRepairRefused("R02 refused because the selected note does not exist")
    revisions = conn.execute(
        "SELECT * FROM note_revisions WHERE note_id = ? ORDER BY revision_number",
        (note_id,),
    ).fetchall()
    if not revisions or tuple(int(row["revision_number"]) for row in revisions) != tuple(
        range(1, len(revisions) + 1)
    ):
        raise StructuredRepairRefused(
            "R02 refused because immutable note revision history is malformed"
        )
    latest = revisions[-1]
    mentions = tuple(str(row["referenced_person_id"]) for row in conn.execute(
        """
        SELECT referenced_person_id FROM note_revision_mentions
        WHERE revision_id = ? ORDER BY referenced_person_id
        """,
        (latest["revision_id"],),
    ))
    all_mentions = conn.execute(
        """
        SELECT rm.* FROM note_revision_mentions rm
        JOIN note_revisions r ON r.revision_id = rm.revision_id
        WHERE r.note_id = ? ORDER BY r.revision_number, rm.referenced_person_id
        """,
        (note_id,),
    ).fetchall()
    fingerprint = _r01_hash({
        "note": dict(note),
        "revisions": [dict(row) for row in revisions],
        "mentions": [dict(row) for row in all_mentions],
    })
    return latest, mentions, fingerprint


def _r02_group_rows(
    conn: sqlite3.Connection, note_id: str, referenced_person_id: str,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    occurrences = conn.execute(
        """
        SELECT m.*, created.note_id AS created_note_id,
               created.revision_number AS created_revision_number,
               retired.note_id AS retired_note_id,
               retired.revision_number AS retired_revision_number
        FROM note_mentions m
        LEFT JOIN note_revisions created ON created.revision_id=m.created_revision_id
        LEFT JOIN note_revisions retired ON retired.revision_id=m.retired_revision_id
        WHERE m.note_id=? AND m.referenced_person_id=?
        ORDER BY m.created_at, m.mention_id
        """,
        (note_id, referenced_person_id),
    ).fetchall()
    if not occurrences:
        raise StructuredRepairRefused(
            "R02 refused because a wholly missing occurrence group is outside P11-A coverage"
        )
    occurrence_ids = tuple(str(row["mention_id"]) for row in occurrences)
    placeholders = ",".join("?" for _ in occurrence_ids)
    evidence = conn.execute(
        f"""
        SELECT * FROM relationship_evidence
        WHERE evidence_type='NOTE_REFERENCE'
          AND source_entity_id IN ({placeholders})
        ORDER BY created_at, evidence_id
        """,
        occurrence_ids,
    ).fetchall()
    return occurrences, evidence


def _r02_validate_history(
    conn: sqlite3.Connection,
    note: sqlite3.Row,
    occurrences: list[sqlite3.Row],
    evidence: list[sqlite3.Row],
    *,
    allowed_started_operation_id: str | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    operation_ids: set[str] = set()
    note_active_shape = (
        note["status"] == "ACTIVE"
        and note["retired_operation_id"] is None
        and note["retired_at"] is None
    )
    note_retired_shape = (
        note["status"] == "RETIRED"
        and note["retired_operation_id"] is not None
        and note["retired_at"] is not None
    )
    if not (note_active_shape or note_retired_shape):
        raise StructuredRepairRefused(
            "R02 refused because note retirement provenance is malformed"
        )
    if note["created_operation_id"]:
        operation_ids.add(str(note["created_operation_id"]))
    if note["retired_operation_id"]:
        operation_ids.add(str(note["retired_operation_id"]))
    operation_ids.update(
        str(row["operation_id"])
        for row in conn.execute(
            """
            SELECT operation_id FROM note_revisions
            WHERE note_id=? AND operation_id IS NOT NULL
            """,
            (note["note_id"],),
        )
    )
    for row in occurrences:
        active_shape = (
            bool(row["active"])
            and row["retired_revision_id"] is None
            and row["retired_operation_id"] is None
            and row["retired_at"] is None
        )
        retired_shape = (
            not bool(row["active"])
            and row["retired_revision_id"] is not None
            and row["retired_operation_id"] is not None
            and row["retired_at"] is not None
            and row["created_note_id"] == row["note_id"]
            and row["retired_note_id"] == row["note_id"]
            and int(row["retired_revision_number"] or 0)
                >= int(row["created_revision_number"] or 0)
        )
        if not (active_shape or retired_shape):
            raise StructuredRepairRefused(
                "R02 refused because occurrence retirement provenance is malformed"
            )
        operation_ids.add(str(row["created_operation_id"]))
        if row["retired_operation_id"]:
            operation_ids.add(str(row["retired_operation_id"]))
    occurrence_by_id = {
        str(row["mention_id"]): row for row in occurrences
    }
    for row in evidence:
        source_occurrence = occurrence_by_id.get(str(row["source_entity_id"]))
        active_shape = (
            bool(row["active"])
            and row["deactivated_operation_id"] is None
            and row["deactivated_at"] is None
        )
        retired_shape = (
            not bool(row["active"])
            and row["deactivated_operation_id"] is not None
            and row["deactivated_at"] is not None
        )
        coherent = (
            source_occurrence is not None
            and row["evidence_type"] == "NOTE_REFERENCE"
            and row["source_entity_type"] == "NOTE"
            and row["source_person_id"] == note["owner_person_id"]
            and row["target_person_id"] == source_occurrence["referenced_person_id"]
            and row["relationship_type"] == "REFERENCES"
            and row["directionality"] == "DIRECTED"
            and row["source_person_id"] != row["target_person_id"]
        )
        if not coherent:
            raise StructuredRepairRefused(
                "R02 refused because NOTE_REFERENCE provenance, endpoints, or direction are malformed"
            )
        if not (active_shape or retired_shape):
            raise StructuredRepairRefused(
                "R02 refused because evidence retirement provenance is malformed"
            )
        operation_ids.add(str(row["created_operation_id"]))
        if row["deactivated_operation_id"]:
            operation_ids.add(str(row["deactivated_operation_id"]))
    linked_operation_ids = set(operation_ids)
    relevant_entity_ids = {
        str(note["note_id"]),
        str(note["owner_person_id"]),
        *[str(row["referenced_person_id"]) for row in occurrences],
        *[str(row["mention_id"]) for row in occurrences],
        *[str(row["evidence_id"]) for row in evidence],
    }
    for row in conn.execute(
        "SELECT operation_id, affected_entities FROM operation_journal ORDER BY rowid"
    ):
        try:
            affected_entities = json.loads(row["affected_entities"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise StructuredRepairRefused(
                "R02 refused because relevant journal metadata is malformed"
            ) from exc
        if any(
            isinstance(item, dict)
            and str(item.get("entity_id")) in relevant_entity_ids
            for item in affected_entities
        ):
            operation_ids.add(str(row["operation_id"]))
    operation_snapshot: list[dict] = []
    for operation_id in sorted(operation_ids):
        operation = _get_journal_operation(conn, operation_id)
        allowed_statuses = (
            {"COMMITTED", "REVERTED"}
            if operation_id in linked_operation_ids
            else {"COMMITTED", "REVERTED", "FAILED", "ROLLED_BACK"}
        )
        if operation_id == allowed_started_operation_id:
            allowed_statuses.add("STARTED")
        if operation is None or operation["status"] not in allowed_statuses:
            raise StructuredRepairRefused(
                "R02 refused because occurrence/evidence operation history is incomplete"
            )
        operation_snapshot.append(operation)
    retirement = {
        "occurrences": [
            {
                key: row[key] for key in (
                    "mention_id", "active", "retired_revision_id",
                    "retired_operation_id", "retired_at",
                )
            }
            for row in occurrences
        ],
        "evidence": [
            {
                key: row[key] for key in (
                    "evidence_id", "active", "deactivated_operation_id",
                    "deactivated_at",
                )
            }
            for row in evidence
        ],
    }
    return (
        _r01_hash(retirement),
        _r01_hash(operation_snapshot),
        tuple(sorted(operation_ids)),
    )


def _r02_canonical_snapshot(
    conn: sqlite3.Connection, person_ids: tuple[str, ...],
) -> tuple[str, dict[str, str]]:
    people = {
        str(row["person_id"]): {
            "lifecycle_status": str(row["lifecycle_status"]),
            "deleted_at": row["deleted_at"],
            "canonical_person_id": (
                str(row["canonical_person_id"])
                if row["canonical_person_id"] is not None else None
            ),
        }
        for row in conn.execute(
            """
            SELECT person_id, lifecycle_status, deleted_at, canonical_person_id
            FROM persons ORDER BY person_id
            """
        )
    }
    paths: dict[str, tuple[str, ...]] = {}
    terminals: dict[str, str] = {}
    relevant: set[str] = set()
    for person_id in person_ids:
        current = person_id
        path: list[str] = []
        seen: set[str] = set()
        while True:
            if current in seen:
                raise StructuredRepairRefused(
                    "R02 refused because a canonical cycle exists"
                )
            seen.add(current)
            path.append(current)
            relevant.add(current)
            row = people.get(current)
            if row is None:
                raise StructuredRepairRefused(
                    "R02 refused because a canonical target is dangling"
                )
            target = row["canonical_person_id"]
            if row["lifecycle_status"] != "MERGED":
                if target is not None:
                    raise StructuredRepairRefused(
                        "R02 refused because a correction/canonical chain is invalid"
                    )
                terminals[person_id] = current
                paths[person_id] = tuple(path)
                break
            if target is None:
                raise StructuredRepairRefused(
                    "R02 refused because a merged canonical chain is incomplete"
                )
            current = str(target)
    snapshot = {
        "paths": paths,
        "people": {person_id: people[person_id] for person_id in sorted(relevant)},
    }
    return _r01_hash(snapshot), terminals


def _r02_plan_for_state(
    *,
    note: sqlite3.Row,
    latest_mentions: tuple[str, ...],
    referenced_person_id: str,
    occurrences: list[sqlite3.Row],
    evidence: list[sqlite3.Row],
) -> NoteReferenceRepairPlan:
    expected_occurrence = (
        note["status"] == "ACTIVE"
        and referenced_person_id in latest_mentions
        and referenced_person_id != note["owner_person_id"]
    )
    active_occurrences = [row for row in occurrences if bool(row["active"])]
    if len(active_occurrences) > 1:
        raise StructuredRepairRefused(
            "R02 refused because duplicate active occurrences make the plan ambiguous"
        )
    active_evidence = [row for row in evidence if bool(row["active"])]
    active_occurrence_ids = {
        str(row["mention_id"]) for row in active_occurrences
    }
    active_on_current = [
        row for row in active_evidence
        if str(row["source_entity_id"]) in active_occurrence_ids
    ]
    active_on_inactive = [
        row for row in active_evidence
        if str(row["source_entity_id"]) not in active_occurrence_ids
    ]
    if expected_occurrence:
        if not active_occurrences:
            if active_evidence:
                raise StructuredRepairRefused(
                    "R02 refused because occurrence append and stale-evidence retirement are both required"
                )
            return NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE
        if active_on_inactive:
            raise StructuredRepairRefused(
                "R02 refused because more than one repair plan applies"
            )
        if not active_on_current:
            return NoteReferenceRepairPlan.APPEND_EVIDENCE
        if len(active_on_current) > 1:
            return NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE
        raise StructuredRepairRefused(
            "R02 refused because the selected occurrence/evidence state is already healthy"
        )
    if active_occurrences:
        if active_on_inactive:
            raise StructuredRepairRefused(
                "R02 refused because occurrence and unrelated stale-evidence plans conflict"
            )
        return NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE
    if active_evidence:
        return NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE
    raise StructuredRepairRefused(
        "R02 refused because the selected occurrence/evidence state is already healthy"
    )


def _r02_graph_key(
    terminals: dict[str, str], owner_person_id: str, referenced_person_id: str,
) -> tuple[str, str, str, str] | None:
    source = terminals[owner_person_id]
    target = terminals[referenced_person_id]
    if source == target:
        return None
    return (source, target, "REFERENCES", "DIRECTED")


def _r02_classify_findings(
    report: object,
    *,
    note_id: str,
    referenced_person_id: str,
    occurrence_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    plan: NoteReferenceRepairPlan,
    graph_key: tuple[str, str, str, str] | None,
    active_evidence_changes: bool,
) -> tuple[object, ...]:
    selected: list[object] = []
    saw_note002 = False
    saw_note003 = False
    saw_stale_evidence = False
    for item in report.findings:
        if item.severity.value not in {"CRITICAL", "ERROR"}:
            continue
        entities = dict(item.entity_ids)
        if item.invariant_id not in _R02_ALLOWED_INVARIANTS:
            raise StructuredRepairRefused(
                "R02 refused because an unrelated critical/error finding blocks deterministic repair",
                report=report,
            )
        if item.invariant_id == "P11-NOTE-002":
            if (
                item.message
                != "Current note mention occurrence cardinality disagrees with the latest authoritative revision"
                or entities.get("note_id") != note_id
                or entities.get("person_id") != referenced_person_id
            ):
                raise StructuredRepairRefused(
                    "R02 refused because P11-NOTE-002 is not the admitted current-cardinality shape",
                    report=report,
                )
            saw_note002 = True
        elif item.invariant_id == "P11-NOTE-003":
            if (
                item.message
                != "NOTE_REFERENCE active evidence does not match authoritative mention state"
                or entities.get("note_id") != note_id
                or entities.get("person_id") != referenced_person_id
                or entities.get("mention_id") not in occurrence_ids
            ):
                raise StructuredRepairRefused(
                    "R02 refused because P11-NOTE-003 is outside the selected occurrence group",
                    report=report,
                )
            saw_note003 = True
        elif item.invariant_id == "P11-EVIDENCE-001":
            if (
                item.message != _R02_STALE_EVIDENCE_MESSAGE
                or entities.get("evidence_id") not in evidence_ids
            ):
                raise StructuredRepairRefused(
                    "R02 refused because P11-EVIDENCE-001 is not the exact admitted stale-active-source shape",
                    report=report,
                )
            saw_stale_evidence = True
        else:
            evidence = dict(item.evidence)
            finding_key = (
                entities.get("source_person_id"),
                entities.get("target_person_id"),
                evidence.get("relationship_type"),
                evidence.get("directionality"),
            )
            if not active_evidence_changes or graph_key is None or finding_key != graph_key:
                raise StructuredRepairRefused(
                    "R02 refused because graph drift is not caused by the selected note-reference scope",
                    report=report,
                )
        selected.append(item)
    if plan in {
        NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE,
        NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE,
    } and not saw_note002:
        raise StructuredRepairRefused(
            "R02 refused because the required P11-NOTE-002 finding is absent",
            report=report,
        )
    if plan in {
        NoteReferenceRepairPlan.APPEND_EVIDENCE,
        NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE,
    } and not saw_note003:
        raise StructuredRepairRefused(
            "R02 refused because the required P11-NOTE-003 finding is absent",
            report=report,
        )
    if plan is NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE and not (
        saw_note003 and saw_stale_evidence
    ):
        raise StructuredRepairRefused(
            "R02 refused because the exact stale active evidence findings are absent",
            report=report,
        )
    return tuple(selected)


def _r02_precondition_from_report(
    conn: sqlite3.Connection,
    report: object,
    note_id: str,
    referenced_person_id: str,
) -> NoteReferenceReconciliationPrecondition:
    if report.schema_version != SCHEMA_VERSION or SCHEMA_VERSION != 28:
        raise StructuredRepairRefused("R02 requires schema version 28", report=report)
    if report.findings_truncated:
        raise StructuredRepairRefused("R02 requires an untruncated P11-A report", report=report)
    graph_revision = _graph_revision_token(conn)
    if graph_revision != report.graph_revision:
        raise StructuredRepairRefused(
            "R02 refused because graph authority changed after diagnosis", report=report,
        )
    note = conn.execute(
        "SELECT * FROM notes WHERE note_id=?", (note_id,),
    ).fetchone()
    if note is None:
        raise StructuredRepairRefused("R02 selected note no longer exists", report=report)
    latest, latest_mentions, revision_fingerprint = _r02_revision_snapshot(conn, note_id)
    occurrences, evidence = _r02_group_rows(conn, note_id, referenced_person_id)
    retirement_fingerprint, operation_fingerprint, _operation_ids = _r02_validate_history(
        conn, note, occurrences, evidence,
    )
    canonical_fingerprint, terminals = _r02_canonical_snapshot(
        conn, (str(note["owner_person_id"]), referenced_person_id),
    )
    plan = _r02_plan_for_state(
        note=note,
        latest_mentions=latest_mentions,
        referenced_person_id=referenced_person_id,
        occurrences=occurrences,
        evidence=evidence,
    )
    active_evidence_changes = (
        plan is not NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE
        or any(bool(row["active"]) for row in evidence)
    )
    occurrence_ids = tuple(str(row["mention_id"]) for row in occurrences)
    evidence_ids = tuple(str(row["evidence_id"]) for row in evidence)
    selected = _r02_classify_findings(
        report,
        note_id=note_id,
        referenced_person_id=referenced_person_id,
        occurrence_ids=occurrence_ids,
        evidence_ids=evidence_ids,
        plan=plan,
        graph_key=_r02_graph_key(
            terminals, str(note["owner_person_id"]), referenced_person_id,
        ),
        active_evidence_changes=active_evidence_changes,
    )
    finding_payload = [
        {
            "invariant_id": item.invariant_id,
            "message": item.message,
            "entity_ids": list(item.entity_ids),
            "evidence": list(item.evidence),
        }
        for item in sorted(
            selected,
            key=lambda item: (item.invariant_id, item.entity_ids, item.message),
        )
    ]
    occurrence_fingerprint = _r02_rows_fingerprint(occurrences)
    evidence_fingerprint = _r02_rows_fingerprint(evidence)
    graph_projection_fingerprint = _r01_hash([
        dict(row) for row in conn.execute(
            "SELECT * FROM graph_connections ORDER BY rowid"
        )
    ])
    active_occurrence_ids = tuple(
        str(row["mention_id"]) for row in occurrences if bool(row["active"])
    )
    active_evidence_ids = tuple(
        str(row["evidence_id"]) for row in evidence if bool(row["active"])
    )
    affected = tuple(sorted({
        note_id,
        str(note["owner_person_id"]),
        referenced_person_id,
        *occurrence_ids,
        *evidence_ids,
    }))
    state = {
        "plan": plan.value,
        "note_id": note_id,
        "referenced_person_id": referenced_person_id,
        "owner_person_id": note["owner_person_id"],
        "note_status": note["status"],
        "latest_revision_id": latest["revision_id"],
        "latest_revision_number": latest["revision_number"],
        "latest_revision_mentions": latest_mentions,
        "revision_history_fingerprint": revision_fingerprint,
        "occurrence_group_fingerprint": occurrence_fingerprint,
        "evidence_history_fingerprint": evidence_fingerprint,
        "retirement_provenance_fingerprint": retirement_fingerprint,
        "canonical_state_fingerprint": canonical_fingerprint,
        "graph_projection_fingerprint": graph_projection_fingerprint,
        "relevant_operation_fingerprint": operation_fingerprint,
    }
    fingerprint = _r01_hash({
        "checker_contract": _R02_FINGERPRINT_VERSION,
        "repair_id": _R02_REPAIR_ID,
        "repair_spec_version": _R02_SPEC_VERSION,
        "findings": finding_payload,
        "schema_version": report.schema_version,
        "graph_revision": graph_revision,
        "state": state,
    })
    return NoteReferenceReconciliationPrecondition(
        repair_id=_R02_REPAIR_ID,
        repair_spec_version=_R02_SPEC_VERSION,
        invariant_ids=tuple(sorted({item.invariant_id for item in selected})),
        affected_entity_ids=affected,
        finding_entity_ids=tuple(sorted({
            value for item in selected for _key, value in item.entity_ids
        })),
        plan=plan,
        finding_fingerprint_version=_R02_FINGERPRINT_VERSION,
        finding_fingerprint=fingerprint,
        schema_version=SCHEMA_VERSION,
        graph_revision=graph_revision,
        note_id=note_id,
        referenced_person_id=referenced_person_id,
        owner_person_id=str(note["owner_person_id"]),
        note_status=str(note["status"]),
        latest_revision_id=str(latest["revision_id"]),
        latest_revision_number=int(latest["revision_number"]),
        latest_revision_mentions=latest_mentions,
        revision_history_fingerprint=revision_fingerprint,
        occurrence_ids=occurrence_ids,
        active_occurrence_ids=active_occurrence_ids,
        occurrence_group_fingerprint=occurrence_fingerprint,
        evidence_ids=evidence_ids,
        active_evidence_ids=active_evidence_ids,
        evidence_history_fingerprint=evidence_fingerprint,
        retirement_provenance_fingerprint=retirement_fingerprint,
        canonical_state_fingerprint=canonical_fingerprint,
        graph_projection_fingerprint=graph_projection_fingerprint,
        relevant_operation_fingerprint=operation_fingerprint,
    )


def _validate_r02_request_shape(
    precondition: NoteReferenceReconciliationPrecondition,
) -> None:
    if not isinstance(precondition, NoteReferenceReconciliationPrecondition):
        raise ValueError("R02 requires its typed finding precondition")
    if (
        precondition.repair_id != _R02_REPAIR_ID
        or precondition.repair_spec_version != _R02_SPEC_VERSION
        or precondition.finding_fingerprint_version != _R02_FINGERPRINT_VERSION
        or precondition.schema_version != SCHEMA_VERSION
        or not isinstance(precondition.plan, NoteReferenceRepairPlan)
        or not precondition.invariant_ids
        or not set(precondition.invariant_ids).issubset(_R02_ALLOWED_INVARIANTS)
    ):
        raise StructuredRepairRefused(
            "R02 request does not match the frozen repair specification"
        )


def _r02_existing_result(
    conn: sqlite3.Connection,
    operation_id: str,
    precondition: NoteReferenceReconciliationPrecondition,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != _R02_OPERATION_TYPE:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    details = operation["details"]
    if (
        details.get("finding_fingerprint") != precondition.finding_fingerprint
        or details.get("repair_id") != precondition.repair_id
        or details.get("note_id") != precondition.note_id
        or details.get("referenced_person_id") != precondition.referenced_person_id
        or details.get("plan_type") != precondition.plan.value
    ):
        raise KeyError("Operation ID was already used for a different R02 diagnosis")
    if operation["status"] != "COMMITTED":
        raise RuntimeError(
            f"Operation {operation_id} is {operation['status']} and cannot be retried"
        )
    return dict(operation["status_history"][-1]["details"])


def _r02_affected_entities(
    precondition: NoteReferenceReconciliationPrecondition,
    *,
    planned_occurrence_id: str | None,
    planned_evidence_id: str | None,
) -> list[dict]:
    entities = [
        {"entity_type": "note", "entity_id": precondition.note_id},
        {"entity_type": "person", "entity_id": precondition.owner_person_id},
        {"entity_type": "person", "entity_id": precondition.referenced_person_id},
    ]
    if planned_occurrence_id is not None:
        entities.append({
            "entity_type": "note_mention", "entity_id": planned_occurrence_id,
        })
    if planned_evidence_id is not None:
        entities.append({
            "entity_type": "relationship_evidence", "entity_id": planned_evidence_id,
        })
    entities.extend(
        {"entity_type": "note_mention", "entity_id": item}
        for item in precondition.occurrence_ids[:24]
    )
    entities.extend(
        {"entity_type": "relationship_evidence", "entity_id": item}
        for item in precondition.evidence_ids[:23]
    )
    return entities[:50]


def _r02_planned_append_ids(
    precondition: NoteReferenceReconciliationPrecondition,
    operation_id: str,
) -> tuple[str | None, str | None]:
    occurrence_id: str | None = None
    if precondition.plan is NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE:
        occurrence_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join((
                "sentriface", _R02_REPAIR_ID, operation_id, "note-mention",
                precondition.note_id, precondition.referenced_person_id,
            )),
        ))
    source_occurrence_id = occurrence_id
    if precondition.plan in {
        NoteReferenceRepairPlan.APPEND_EVIDENCE,
        NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE,
    }:
        source_occurrence_id = precondition.active_occurrence_ids[0]
    evidence_id: str | None = None
    if source_occurrence_id is not None:
        normalized_source, normalized_target = _normalize_evidence_endpoints(
            precondition.owner_person_id,
            precondition.referenced_person_id,
            "DIRECTED",
        )
        evidence_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join((
                "sentriface", "NOTE_REFERENCE", source_occurrence_id, operation_id,
                normalized_source, normalized_target, "REFERENCES", "DIRECTED",
            )),
        ))
    return occurrence_id, evidence_id


def _r02_append_evidence(
    conn: sqlite3.Connection,
    *,
    mention_id: str,
    owner_person_id: str,
    referenced_person_id: str,
    operation_id: str,
    source: str | None,
    created_at: str,
) -> str:
    evidence_id = _insert_relationship_evidence(
        conn,
        evidence_type="NOTE_REFERENCE",
        source_entity_type="NOTE",
        source_entity_id=mention_id,
        evidence_revision_id=operation_id,
        source_person_id=owner_person_id,
        target_person_id=referenced_person_id,
        relationship_type="REFERENCES",
        directionality="DIRECTED",
        source=source,
        created_operation_id=operation_id,
        created_at=created_at,
    )
    row = conn.execute(
        """
        SELECT active, created_operation_id FROM relationship_evidence
        WHERE evidence_id=?
        """,
        (evidence_id,),
    ).fetchone()
    if row is None or not bool(row["active"]) or row["created_operation_id"] != operation_id:
        raise RuntimeError("R02 failed to append a repair-owned evidence revision")
    return evidence_id


def _apply_r02_plan(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
    operation_id: str,
    *,
    source: str | None,
    planned_occurrence_id: str | None,
) -> dict:
    created_at = utc_now()
    mutation = {
        "occurrences_appended": 0,
        "occurrences_retired": 0,
        "evidence_appended": 0,
        "evidence_retired": 0,
        "active_evidence_changed": False,
        "appended_occurrence_ids": [],
        "appended_evidence_ids": [],
        "retired_occurrence_ids": [],
        "retired_evidence_ids": [],
    }
    active_occurrence_id = (
        precondition.active_occurrence_ids[0]
        if precondition.active_occurrence_ids else None
    )
    if precondition.plan is NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE:
        if planned_occurrence_id is None:
            raise RuntimeError("R02 occurrence append is missing its planned identity")
        mention_id = planned_occurrence_id
        conn.execute(
            """
            INSERT INTO note_mentions(
                mention_id, note_id, referenced_person_id, active,
                created_revision_id, created_operation_id, created_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (
                mention_id,
                precondition.note_id,
                precondition.referenced_person_id,
                precondition.latest_revision_id,
                operation_id,
                created_at,
            ),
        )
        mutation["occurrences_appended"] = 1
        mutation["appended_occurrence_ids"].append(mention_id)
        _r02_failure_checkpoint("after_occurrence_append")
        evidence_id = _r02_append_evidence(
            conn,
            mention_id=mention_id,
            owner_person_id=precondition.owner_person_id,
            referenced_person_id=precondition.referenced_person_id,
            operation_id=operation_id,
            source=source,
            created_at=created_at,
        )
        mutation["evidence_appended"] = 1
        mutation["appended_evidence_ids"].append(evidence_id)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_evidence_append")
    elif precondition.plan is NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE:
        if active_occurrence_id is None:
            raise RuntimeError("R02 retirement plan lost its active occurrence")
        cursor = conn.execute(
            """
            UPDATE note_mentions
            SET active=0, retired_revision_id=?, retired_operation_id=?, retired_at=?
            WHERE mention_id=? AND active=1
            """,
            (
                precondition.latest_revision_id,
                operation_id,
                created_at,
                active_occurrence_id,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("R02 failed to retire the selected occurrence")
        mutation["occurrences_retired"] = 1
        mutation["retired_occurrence_ids"].append(active_occurrence_id)
        _r02_failure_checkpoint("after_occurrence_retirement")
        rows = conn.execute(
            """
            SELECT evidence_id FROM relationship_evidence
            WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
            ORDER BY evidence_id
            """,
            (active_occurrence_id,),
        ).fetchall()
        if rows:
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id=?, deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (operation_id, created_at, active_occurrence_id),
            )
            mutation["evidence_retired"] = len(rows)
            mutation["retired_evidence_ids"].extend(str(row[0]) for row in rows)
            mutation["active_evidence_changed"] = True
            _r02_failure_checkpoint("after_evidence_retirement")
    elif precondition.plan is NoteReferenceRepairPlan.APPEND_EVIDENCE:
        if active_occurrence_id is None:
            raise RuntimeError("R02 evidence append plan lost its active occurrence")
        evidence_id = _r02_append_evidence(
            conn,
            mention_id=active_occurrence_id,
            owner_person_id=precondition.owner_person_id,
            referenced_person_id=precondition.referenced_person_id,
            operation_id=operation_id,
            source=source,
            created_at=created_at,
        )
        mutation["evidence_appended"] = 1
        mutation["appended_evidence_ids"].append(evidence_id)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_evidence_append")
    elif precondition.plan is NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE:
        if active_occurrence_id is None:
            raise RuntimeError("R02 duplicate replacement lost its active occurrence")
        rows = conn.execute(
            """
            SELECT evidence_id FROM relationship_evidence
            WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
            ORDER BY evidence_id
            """,
            (active_occurrence_id,),
        ).fetchall()
        if len(rows) < 2:
            raise RuntimeError("R02 duplicate evidence plan no longer has duplicates")
        conn.execute(
            """
            UPDATE relationship_evidence
            SET active=0, deactivated_operation_id=?, deactivated_at=?
            WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
            """,
            (operation_id, created_at, active_occurrence_id),
        )
        mutation["evidence_retired"] = len(rows)
        mutation["retired_evidence_ids"].extend(str(row[0]) for row in rows)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_duplicate_evidence_retire_phase")
        evidence_id = _r02_append_evidence(
            conn,
            mention_id=active_occurrence_id,
            owner_person_id=precondition.owner_person_id,
            referenced_person_id=precondition.referenced_person_id,
            operation_id=operation_id,
            source=source,
            created_at=created_at,
        )
        mutation["evidence_appended"] = 1
        mutation["appended_evidence_ids"].append(evidence_id)
        _r02_failure_checkpoint("after_replacement_evidence_append")
    elif precondition.plan is NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE:
        placeholders = ",".join("?" for _ in precondition.occurrence_ids)
        rows = conn.execute(
            f"""
            SELECT evidence_id FROM relationship_evidence
            WHERE evidence_type='NOTE_REFERENCE' AND active=1
              AND source_entity_id IN ({placeholders})
            ORDER BY evidence_id
            """,
            precondition.occurrence_ids,
        ).fetchall()
        if not rows:
            raise RuntimeError("R02 stale evidence plan no longer has active evidence")
        conn.execute(
            f"""
            UPDATE relationship_evidence
            SET active=0, deactivated_operation_id=?, deactivated_at=?
            WHERE evidence_type='NOTE_REFERENCE' AND active=1
              AND source_entity_id IN ({placeholders})
            """,
            (operation_id, created_at, *precondition.occurrence_ids),
        )
        mutation["evidence_retired"] = len(rows)
        mutation["retired_evidence_ids"].extend(str(row[0]) for row in rows)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_evidence_retirement")
    else:  # pragma: no cover - the typed enum and request guard make this unreachable.
        raise RuntimeError("Unsupported R02 plan")
    return mutation


def _r02_maintain_affected_projection(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
) -> None:
    """Replace only the one effective directed relationship aggregate R02 can affect."""
    connections, errors, _ = _expected_graph_connections(conn)
    if errors:
        raise RuntimeError(
            "R02 relationship evidence validation failed: " + "; ".join(errors[:10])
        )
    resolve = _batch_canonical_resolver(conn)
    source_person_id = resolve(precondition.owner_person_id)
    target_person_id = resolve(precondition.referenced_person_id)
    if source_person_id == target_person_id:
        return
    key = (
        source_person_id, target_person_id, "REFERENCES", "DIRECTED",
    )
    expected = [
        item for item in connections
        if _graph_connection_signature(item)[:4] == key
    ]
    if len(expected) > 1:
        raise RuntimeError("R02 shared graph authority returned duplicate affected keys")
    conn.execute(
        """
        DELETE FROM graph_connections
        WHERE source_person_id=? AND target_person_id=?
          AND relationship_type='REFERENCES' AND directionality='DIRECTED'
        """,
        (source_person_id, target_person_id),
    )
    _insert_graph_projection_rows(conn, expected)


def _r02_immutable_fingerprint(conn: sqlite3.Connection) -> str:
    tables = ("notes", "note_revisions", "note_revision_mentions")
    return _r01_hash({
        table: [dict(row) for row in conn.execute(
            f"SELECT * FROM {table} ORDER BY rowid"
        )]
        for table in tables
    })


def _r02_unrelated_fingerprint(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
    operation_id: str,
) -> str:
    tables = (
        "persons", "embeddings", "biometric_enrollment_history", "observations",
        "observation_media", "observation_participants", "observation_face_assignments",
        "identity_corrections", "merge_operations", "merge_affected_items",
        "merge_conflict_resolutions",
    )
    snapshot: dict[str, object] = {
        table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in tables
    }
    snapshot["unrelated_occurrences"] = [dict(row) for row in conn.execute(
        """
        SELECT * FROM note_mentions
        WHERE NOT (note_id=? AND referenced_person_id=?) ORDER BY rowid
        """,
        (precondition.note_id, precondition.referenced_person_id),
    )]
    snapshot["unrelated_evidence"] = [dict(row) for row in conn.execute(
        """
        SELECT e.* FROM relationship_evidence e
        WHERE NOT (
          e.evidence_type='NOTE_REFERENCE' AND EXISTS (
            SELECT 1 FROM note_mentions m
            WHERE m.mention_id=e.source_entity_id
              AND m.note_id=? AND m.referenced_person_id=?
          )
        )
        ORDER BY e.rowid
        """,
        (precondition.note_id, precondition.referenced_person_id),
    )]
    snapshot["prior_journal"] = [dict(row) for row in conn.execute(
        "SELECT * FROM operation_journal WHERE operation_id<>? ORDER BY rowid",
        (operation_id,),
    )]
    snapshot["prior_journal_history"] = [dict(row) for row in conn.execute(
        """
        SELECT * FROM operation_journal_status_history
        WHERE operation_id<>? ORDER BY rowid
        """,
        (operation_id,),
    )]
    return _r01_hash(snapshot)


def _r02_retired_history_fingerprint(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
) -> str:
    retired_occurrence_ids = tuple(
        item for item in precondition.occurrence_ids
        if item not in precondition.active_occurrence_ids
    )
    retired_evidence_ids = tuple(
        item for item in precondition.evidence_ids
        if item not in precondition.active_evidence_ids
    )

    def selected(table: str, column: str, ids: tuple[str, ...]) -> list[dict]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        return [dict(row) for row in conn.execute(
            f"SELECT * FROM {table} WHERE {column} IN ({placeholders}) ORDER BY rowid",
            ids,
        )]

    return _r01_hash({
        "occurrences": selected("note_mentions", "mention_id", retired_occurrence_ids),
        "evidence": selected("relationship_evidence", "evidence_id", retired_evidence_ids),
    })


def _validate_r02_postconditions(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
    *,
    operation_id: str,
    mutation: dict,
    immutable_before: str,
    unrelated_before: str,
    historical_before: str,
    revision_before: str,
) -> dict:
    if _r02_immutable_fingerprint(conn) != immutable_before:
        raise RuntimeError("R02 changed immutable note revision authority")
    if _r02_unrelated_fingerprint(conn, precondition, operation_id) != unrelated_before:
        raise RuntimeError("R02 changed unrelated authoritative state")
    if _r02_retired_history_fingerprint(conn, precondition) != historical_before:
        raise RuntimeError("R02 rewrote pre-existing retired history")
    latest, latest_mentions, revision_fingerprint = _r02_revision_snapshot(
        conn, precondition.note_id,
    )
    if (
        str(latest["revision_id"]) != precondition.latest_revision_id
        or int(latest["revision_number"]) != precondition.latest_revision_number
        or latest_mentions != precondition.latest_revision_mentions
        or revision_fingerprint != precondition.revision_history_fingerprint
    ):
        raise RuntimeError("R02 latest revision authority changed")
    occurrences, evidence = _r02_group_rows(
        conn, precondition.note_id, precondition.referenced_person_id,
    )
    _r02_validate_history(
        conn,
        conn.execute("SELECT * FROM notes WHERE note_id=?", (precondition.note_id,)).fetchone(),
        occurrences,
        evidence,
        allowed_started_operation_id=operation_id,
    )
    expected_occurrence = (
        precondition.note_status == "ACTIVE"
        and precondition.referenced_person_id in precondition.latest_revision_mentions
        and precondition.referenced_person_id != precondition.owner_person_id
    )
    active_occurrences = [row for row in occurrences if bool(row["active"])]
    if len(active_occurrences) != (1 if expected_occurrence else 0):
        raise RuntimeError("R02 immediate NOTE-002 cardinality postcondition failed")
    active_occurrence_ids = {
        str(row["mention_id"]) for row in active_occurrences
    }
    active_evidence = [row for row in evidence if bool(row["active"])]
    expected_evidence = 1 if expected_occurrence else 0
    matching_active = [
        row for row in active_evidence
        if str(row["source_entity_id"]) in active_occurrence_ids
        and row["source_person_id"] == precondition.owner_person_id
        and row["target_person_id"] == precondition.referenced_person_id
        and row["relationship_type"] == "REFERENCES"
        and row["directionality"] == "DIRECTED"
    ]
    if len(active_evidence) != expected_evidence or len(matching_active) != expected_evidence:
        raise RuntimeError("R02 immediate NOTE-003 cardinality postcondition failed")
    projection = _validate_graph_projection(conn)
    if not projection["valid"]:
        raise RuntimeError(
            "R02 graph/evidence postcondition failed: "
            + "; ".join(projection["errors"][:10])
        )
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("R02 foreign-key postcondition failed")
    journal = _get_journal_operation(conn, operation_id)
    if (
        journal is None
        or journal["operation_type"] != _R02_OPERATION_TYPE
        or journal["status"] != "STARTED"
        or tuple(item["to_status"] for item in journal["status_history"]) != ("STARTED",)
    ):
        raise RuntimeError("R02 transaction-local journal postcondition failed")
    before_number = int(revision_before[1:])
    revision_after = _graph_revision_token(conn)
    expected_revision = (
        f"g{before_number + 1}"
        if mutation["active_evidence_changed"] else revision_before
    )
    if revision_after != expected_revision:
        raise RuntimeError("R02 graph revision did not follow the frozen rule")
    return {
        "graph_revision_after": revision_after,
        "connection_count_after": projection["actual_connection_count"],
    }


_P11D_REVERT_SPEC_VERSION = 1
_P11D_FINGERPRINT_VERSION = "p11-d-schema28-merge-revert-v1"
_P11D_REVERT_OPERATION_TYPE = "identity.merge.revert"


def _p11d_checkpoint(
    failure_injector: Callable[[str], None] | None, seam: str,
) -> None:
    if failure_injector is not None:
        failure_injector(seam)


def _p11d_person_fingerprint(conn: sqlite3.Connection, person_id: str) -> str:
    row = conn.execute(
        "SELECT * FROM persons WHERE person_id=?", (person_id,),
    ).fetchone()
    if row is None:
        raise OperationRevertRefused(f"Affected person is missing: {person_id}")
    return _r01_hash(dict(row))


def _p11d_person_stable_fingerprint(conn: sqlite3.Connection, person_id: str) -> str:
    row = conn.execute(
        "SELECT * FROM persons WHERE person_id=?", (person_id,),
    ).fetchone()
    if row is None:
        raise OperationRevertRefused(f"Affected person is missing: {person_id}")
    value = dict(row)
    for field in (
        "lifecycle_status", "canonical_person_id", "deleted_at",
        "lifecycle_changed_at",
    ):
        value.pop(field, None)
    return _r01_hash(value)


def _p11d_merge_state_fingerprint(
    conn: sqlite3.Connection, merge_operation_id: str,
) -> str:
    return _r01_hash({
        "operation": [dict(row) for row in conn.execute(
            "SELECT * FROM merge_operations WHERE merge_operation_id=?",
            (merge_operation_id,),
        )],
        "items": [dict(row) for row in conn.execute(
            """
            SELECT * FROM merge_affected_items
            WHERE merge_operation_id=? ORDER BY item_type, item_id
            """,
            (merge_operation_id,),
        )],
        "conflicts": [dict(row) for row in conn.execute(
            """
            SELECT * FROM merge_conflict_resolutions
            WHERE merge_operation_id=? ORDER BY category, field_name, conflict_id
            """,
            (merge_operation_id,),
        )],
    })


def _p11d_immutable_fingerprint(
    conn: sqlite3.Connection, merge_operation_id: str,
) -> str:
    return _p11d_merge_state_fingerprint(conn, merge_operation_id)


def _p11d_affected_entities(
    operation: dict, manifest: MergeOperation,
) -> tuple[tuple[str, str], ...]:
    entities: set[tuple[str, str]] = {
        ("person", manifest.source_person_id),
        ("person", manifest.target_person_id),
        ("operation", manifest.merge_operation_id),
    }
    for item in operation.get("affected_entities") or []:
        if isinstance(item, dict) and str(item.get("entity_id") or "").strip():
            entities.add((
                str(item.get("entity_type") or "entity").strip().lower(),
                str(item["entity_id"]),
            ))
    for item in manifest.affected_items:
        entities.add((item.item_type.lower(), item.item_id))
    return tuple(sorted(entities))


def _p11d_later_dependencies(
    conn: sqlite3.Connection,
    operation_id: str,
    affected_entities: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    original = conn.execute(
        "SELECT rowid FROM operation_journal WHERE operation_id=?", (operation_id,),
    ).fetchone()
    if original is None:
        raise OperationRevertRefused("Operation history is incomplete")
    affected_ids = {entity_id for _, entity_id in affected_entities}
    dependencies: list[str] = []
    rows = conn.execute(
        """
        SELECT operation_id, operation_type, status, affected_entities
        FROM operation_journal
        WHERE rowid>? AND status IN ('STARTED','COMMITTED','REVERTED')
        ORDER BY rowid
        """,
        (original["rowid"],),
    ).fetchall()
    for row in rows:
        if row["operation_type"] == "graph.projection.rebuild":
            continue
        try:
            entities = json.loads(row["affected_entities"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OperationRevertRefused("Later operation history is malformed") from exc
        later_ids = {
            str(item.get("entity_id"))
            for item in entities if isinstance(item, dict) and item.get("entity_id") is not None
        }
        if affected_ids & later_ids:
            dependencies.append(str(row["operation_id"]))
    return tuple(dependencies)


def _p11d_precondition_from_report(
    conn: sqlite3.Connection,
    report: object,
    operation_id: str,
) -> OperationRevertPrecondition:
    if getattr(report, "schema_version", None) != SCHEMA_VERSION:
        raise OperationRevertRefused("Revert requires the current schema")
    if getattr(report, "findings_truncated", True):
        raise OperationRevertRefused("Revert requires an untruncated P11-A report", report=report)
    blocking = tuple(
        finding for finding in getattr(report, "findings", ())
        if finding.severity.value in {"CRITICAL", "ERROR"}
    )
    if blocking:
        raise OperationRevertRefused(
            "Revert requires a clean authoritative P11-A preflight", report=report,
        )
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        raise OperationRevertRefused("Operation history is incomplete")
    if operation["operation_type"] != "identity.merge":
        raise OperationRevertRefused(
            f"Operation type is not in the revert whitelist: {operation['operation_type']}"
        )
    if operation["status"] == "REVERTED":
        raise OperationRevertRefused("Operation has already been reverted")
    if operation["status"] != "COMMITTED":
        raise OperationRevertRefused("Only a committed operation can be reverted")
    statuses = tuple(item["to_status"] for item in operation["status_history"])
    if statuses != ("STARTED", "COMMITTED"):
        raise OperationRevertRefused("Operation journal history is incomplete or ambiguous")
    manifest = _get_merge_operation(conn, operation_id)
    if manifest is None or manifest.operation_journal_id != operation_id:
        raise OperationRevertRefused("Merge manifest history is incomplete")
    if (
        manifest.previous_source_lifecycle_status != "ACTIVE"
        or manifest.previous_source_canonical_person_id is not None
        or manifest.previous_target_lifecycle_status != "ACTIVE"
        or manifest.previous_target_canonical_person_id is not None
    ):
        raise OperationRevertRefused(
            "Merge previous lifecycle/canonical state is not safely reversible"
        )
    if manifest.conflicts:
        raise OperationRevertRefused(
            "Merge changed survivor profile or note state and is not safely reversible"
        )
    if any(
        item.item_type in {"CURRENT_STATE", "PROFILE_FIELD"}
        for item in manifest.affected_items
    ):
        raise OperationRevertRefused(
            "Merge changed survivor current state and is not safely reversible"
        )
    person_items = tuple(
        item for item in manifest.affected_items
        if item.item_type == "PERSON" and item.item_id == manifest.source_person_id
    )
    if len(person_items) != 1 or person_items[0].before_state != {
        "lifecycle_status": "ACTIVE", "canonical_person_id": None,
    } or person_items[0].after_state != {
        "lifecycle_status": "MERGED", "canonical_person_id": manifest.target_person_id,
    }:
        raise OperationRevertRefused("Merge inverse manifest is incomplete or ambiguous")
    source_row = conn.execute(
        """
        SELECT lifecycle_status, canonical_person_id, deleted_at, lifecycle_changed_at
        FROM persons WHERE person_id=?
        """,
        (manifest.source_person_id,),
    ).fetchone()
    target_row = conn.execute(
        """
        SELECT lifecycle_status, canonical_person_id, deleted_at, lifecycle_changed_at
        FROM persons WHERE person_id=?
        """,
        (manifest.target_person_id,),
    ).fetchone()
    if (
        source_row is None
        or source_row["lifecycle_status"] != "MERGED"
        or source_row["canonical_person_id"] != manifest.target_person_id
        or source_row["deleted_at"] is None
        or not source_row["lifecycle_changed_at"]
    ):
        raise OperationRevertRefused("Current merge source state differs from the expected result")
    if (
        target_row is None
        or target_row["lifecycle_status"] != "ACTIVE"
        or target_row["canonical_person_id"] is not None
        or target_row["deleted_at"] is not None
    ):
        raise OperationRevertRefused("Merge survivor is no longer terminal and active")
    affected_entities = _p11d_affected_entities(operation, manifest)
    dependencies = _p11d_later_dependencies(conn, operation_id, affected_entities)
    dependency_state_fingerprint = _r01_hash({
        "operation_id": operation_id,
        "affected_entities": affected_entities,
        "later_dependency_operation_ids": dependencies,
    })
    if dependencies:
        raise OperationRevertRefused(
            "Later dependent operations prevent safe revert: " + ", ".join(dependencies)
        )
    graph_revision = _graph_revision_token(conn)
    if getattr(report, "graph_revision", None) != graph_revision:
        raise OperationRevertRefused("P11-A preflight is stale")
    journal_history_fingerprint = _r01_hash(operation)
    merge_state_fingerprint = _p11d_merge_state_fingerprint(conn, operation_id)
    graph_projection_fingerprint = _r01_table_fingerprint(conn, "graph_connections")
    target_state_fingerprint = _p11d_person_fingerprint(conn, manifest.target_person_id)
    relevant_revisions = (
        ("graph_revision", graph_revision),
        ("source_lifecycle_changed_at", str(source_row["lifecycle_changed_at"])),
        ("target_lifecycle_changed_at", str(target_row["lifecycle_changed_at"] or "")),
        ("operation_completed_at", str(operation["completed_at"] or "")),
    )
    payload = {
        "revert_spec_version": _P11D_REVERT_SPEC_VERSION,
        "fingerprint_version": _P11D_FINGERPRINT_VERSION,
        "operation_id": operation_id,
        "operation_type": operation["operation_type"],
        "journal_state": operation["status"],
        "journal_history_fingerprint": journal_history_fingerprint,
        "affected_entities": affected_entities,
        "relevant_revisions": relevant_revisions,
        "graph_revision": graph_revision,
        "graph_projection_fingerprint": graph_projection_fingerprint,
        "dependency_operation_ids": dependencies,
        "dependency_state_fingerprint": dependency_state_fingerprint,
        "merge_state_fingerprint": merge_state_fingerprint,
        "source_person_id": manifest.source_person_id,
        "target_person_id": manifest.target_person_id,
        "expected_source_lifecycle_status": "MERGED",
        "expected_source_canonical_person_id": manifest.target_person_id,
        "expected_source_lifecycle_changed_at": str(source_row["lifecycle_changed_at"]),
        "expected_target_state_fingerprint": target_state_fingerprint,
    }
    return OperationRevertPrecondition(
        **payload,
        fingerprint=_r01_hash(payload),
    )


def _validate_p11d_request_shape(precondition: OperationRevertPrecondition) -> None:
    if not isinstance(precondition, OperationRevertPrecondition):
        raise OperationRevertRefused("A typed P11-D revert precondition is required")
    if (
        precondition.revert_spec_version != _P11D_REVERT_SPEC_VERSION
        or precondition.fingerprint_version != _P11D_FINGERPRINT_VERSION
        or precondition.operation_type != "identity.merge"
        or precondition.journal_state != "COMMITTED"
        or precondition.dependency_operation_ids
    ):
        raise OperationRevertRefused("Unsupported or unsafe revert precondition")
    payload = asdict(precondition)
    fingerprint = payload.pop("fingerprint")
    if _r01_hash(payload) != fingerprint:
        raise OperationRevertRefused("Revert precondition fingerprint is invalid")


def _p11d_existing_result(
    conn: sqlite3.Connection,
    operation_id: str,
    precondition: OperationRevertPrecondition,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != _P11D_REVERT_OPERATION_TYPE:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    if operation.get("details", {}).get("fingerprint") != precondition.fingerprint:
        raise ValueError("Revert operation ID belongs to a different request")
    if operation["status"] != "COMMITTED":
        raise ValueError(
            "A failed or incomplete revert operation ID cannot be reused"
        )
    history = operation.get("status_history") or []
    return dict(history[-1]["details"]) if history else {}


def _validate_p11d_postconditions(
    conn: sqlite3.Connection,
    precondition: OperationRevertPrecondition,
    *,
    immutable_before: str,
    target_before: str,
    source_stable_before: str,
    revision_before: str,
) -> dict:
    source = conn.execute(
        """
        SELECT lifecycle_status, canonical_person_id, deleted_at
        FROM persons WHERE person_id=?
        """,
        (precondition.source_person_id,),
    ).fetchone()
    if (
        source is None
        or source["lifecycle_status"] != "ACTIVE"
        or source["canonical_person_id"] is not None
        or source["deleted_at"] is not None
    ):
        raise RuntimeError("P11-D source lifecycle/canonical postcondition failed")
    if _p11d_person_fingerprint(conn, precondition.target_person_id) != target_before:
        raise RuntimeError("P11-D changed the merge survivor")
    if (
        _p11d_person_stable_fingerprint(conn, precondition.source_person_id)
        != source_stable_before
    ):
        raise RuntimeError("P11-D changed non-lifecycle source state")
    if _p11d_immutable_fingerprint(conn, precondition.operation_id) != immutable_before:
        raise RuntimeError("P11-D changed immutable merge history")
    projection = _validate_graph_projection(conn)
    if not projection["valid"]:
        raise RuntimeError(
            "P11-D graph postcondition failed: " + "; ".join(projection["errors"][:10])
        )
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("P11-D foreign-key postcondition failed")
    journal = _get_journal_operation(conn, precondition.operation_id)
    if journal is None or journal["status"] != "COMMITTED":
        raise RuntimeError("P11-D changed the original journal before validation")
    revision_after = _graph_revision_token(conn)
    expected_revision = f"g{int(revision_before[1:]) + 2}"
    if revision_after != expected_revision:
        raise RuntimeError("P11-D graph revision did not follow existing merge rules")
    return {
        "graph_revision_after": revision_after,
        "connection_count_after": projection["actual_connection_count"],
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


def _embedding_from_row(
    row: sqlite3.Row, *, raw_person_id: str | None = None,
    canonical_person_id: str | None = None,
) -> EmbeddingRecord:
    return EmbeddingRecord(
        embedding_id=row["embedding_id"],
        person_id=raw_person_id or row["person_id"],
        vector=_unpack_embedding(row["vector"]),
        quality_score=row["quality_score"],
        source_image=row["source_image"],
        crop_path=row["crop_path"],
        created_at=row["created_at"],
        canonical_person_id=canonical_person_id,
    )


def _raw_embedding_owner_person_id(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> str:
    """Return immutable enrollment ownership, including pre-P8-C moved faces."""
    embedding_id = str(row["embedding_id"])
    latest = conn.execute(
        """
        SELECT to_person_id FROM identity_corrections
        WHERE embedding_id = ? AND correction_type = 'FACE_OWNERSHIP'
        ORDER BY created_at DESC, correction_id DESC LIMIT 1
        """,
        (embedding_id,),
    ).fetchone()
    stored_owner = str(row["person_id"])
    if latest is None or stored_owner != str(latest["to_person_id"]):
        return stored_owner
    correction = conn.execute(
        """
        SELECT from_person_id FROM identity_corrections
        WHERE embedding_id = ? AND correction_type = 'FACE_OWNERSHIP'
        ORDER BY created_at ASC, correction_id ASC LIMIT 1
        """,
        (embedding_id,),
    ).fetchone()
    return str(correction["from_person_id"] if correction is not None else stored_owner)


def _current_embedding_owner_person_id(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> str:
    """Return the latest corrected owner without rewriting raw ownership."""
    embedding_id = str(row["embedding_id"])
    correction = conn.execute(
        """
        SELECT to_person_id FROM identity_corrections
        WHERE embedding_id = ? AND correction_type = 'FACE_OWNERSHIP'
        ORDER BY created_at DESC, correction_id DESC LIMIT 1
        """,
        (embedding_id,),
    ).fetchone()
    return str(correction["to_person_id"] if correction is not None else row["person_id"])


def _effective_embedding_owner_person_id(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> str:
    return _resolve_canonical_person_id(
        conn, _current_embedding_owner_person_id(conn, row),
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
