from __future__ import annotations

import json
import sqlite3
import struct
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path

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
    PersonChange,
    PersonMatch,
    PersonSummary,
    QualityReport,
    QualityStatus,
    RecognitionDetail,
    utc_now,
)

from sentriface.secure_storage import connect_database, ensure_encrypted_database

SCHEMA_VERSION = 12
DELETED_FACE_RETENTION_DAYS = 30


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
        version = self._schema_version()
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than this app supports "
                f"({SCHEMA_VERSION}). Please update SentriFace."
            )
        if 0 < version < SCHEMA_VERSION:
            self._create_pre_migration_backup(version)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than this app supports "
                    f"({SCHEMA_VERSION}). Please update SentriFace."
                )
            if version == 0:
                _migrate_0_to_1(conn)
                version = 1
            if version == 1:
                _migrate_1_to_2(conn)
                version = 2
            if version == 2:
                _migrate_2_to_3(conn)
                version = 3
            if version == 3:
                _migrate_3_to_4(conn)
                version = 4
            if version == 4:
                _migrate_4_to_5(conn)
                version = 5
            if version == 5:
                _migrate_5_to_6(conn)
                version = 6
            if version == 6:
                _migrate_6_to_7(conn)
                version = 7
            if version == 7:
                _migrate_7_to_8(conn)
                version = 8
            if version == 8:
                _migrate_8_to_9(conn)
                version = 9
            if version == 9:
                _migrate_9_to_10(conn)
                version = 10
            if version == 10:
                _migrate_10_to_11(conn)
                version = 11
            if version == 11:
                _migrate_11_to_12(conn)
                version = 12
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported database schema version: {version}")

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

    def create_person(self, name: str, metadata: dict | None = None) -> Person:
        person = Person(
            person_id=str(uuid.uuid4()),
            name=name,
            metadata=metadata or {},
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO persons(person_id, name, metadata, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    person.person_id,
                    person.name,
                    json.dumps(person.metadata, separators=(",", ":")),
                    person.created_at,
                ),
            )
        return person

    def get_person(self, person_id: str, include_archived: bool = False) -> Person | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT person_id, name, metadata, created_at, deleted_at
                FROM persons
                WHERE person_id = ? {" " if include_archived else "AND deleted_at IS NULL"}
                """,
                (person_id,),
            ).fetchone()
        if row is None:
            return None
        return Person(
            person_id=row["person_id"],
            name=row["name"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )

    def list_persons(self, archived: bool = False) -> list[PersonSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.person_id, p.name, p.metadata, p.created_at, p.deleted_at,
                       COUNT(CASE WHEN e.deleted_at IS NULL THEN e.embedding_id END) AS embedding_count
                FROM persons p
                LEFT JOIN embeddings e ON e.person_id = p.person_id
                WHERE p.deleted_at IS {"NOT NULL" if archived else "NULL"}
                GROUP BY p.person_id
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
                ),
                embedding_count=row["embedding_count"],
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
            cursor = conn.execute(
                "UPDATE persons SET name = ? WHERE person_id = ? AND deleted_at IS NULL",
                (name, person_id),
            )
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
                               previous_importance, new_importance, editor_name, created_at
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
                SELECT person_id, name, metadata
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
                editor_name=editor_name,
                created_at=utc_now(),
            )
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
            conn.execute(
                """
                INSERT INTO person_change_history(
                    change_id, person_id, previous_name, new_name,
                    previous_rank, new_rank, previous_country, new_country,
                    previous_importance, new_importance, editor_name, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    change.editor_name,
                    change.created_at,
                ),
            )
            if operation_id:
                _record_person_operation(
                    conn,
                    operation_id,
                    "update-profile",
                    {"change_id": change.change_id, "person_id": person_id},
                )
        return change

    def list_person_changes(self, person_id: str) -> list[PersonChange]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT change_id, person_id, previous_name, new_name,
                       previous_rank, new_rank, previous_country, new_country,
                       previous_importance, new_importance, editor_name, created_at
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

    def get_person_operation(self, operation_id: str, operation_type: str) -> dict | None:
        with self._connect() as conn:
            return _existing_person_operation(conn, operation_id, operation_type)

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
            cursor = conn.execute(
                "UPDATE persons SET deleted_at = NULL WHERE person_id = ? AND deleted_at IS NOT NULL",
                (person_id,),
            )
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
            conn.execute("DELETE FROM recognition_details WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM init_face_person_exclusions WHERE person_id = ?", (person_id,))
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
                "SELECT name, metadata, deleted_at FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (source_person_id,),
            ).fetchone()
            target = conn.execute(
                "SELECT name, metadata, deleted_at FROM persons WHERE person_id = ? AND deleted_at IS NULL",
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
                "UPDATE persons SET metadata = ?, deleted_at = NULL WHERE person_id = ?",
                (json.dumps(snapshot["source_metadata"], separators=(",", ":")), source_person_id),
            )
            conn.execute(
                "UPDATE persons SET metadata = ? WHERE person_id = ?",
                (json.dumps(snapshot["target_metadata"], separators=(",", ":")), target_person_id),
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
                    importance, added_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            if operation_id:
                _record_person_operation(
                    conn,
                    operation_id,
                    "recognition-followup",
                    {"detail_id": detail.detail_id},
                )
        return detail

    def list_recognition_details_for_embedding(self, embedding_id: str) -> list[RecognitionDetail]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT detail_id, embedding_id, person_id, image_id, image_path,
                       name, decision, seen_date, seen_time, place_seen,
                       individual_count, event_occasion, rank, country,
                       importance, added_by, created_at
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
                       d.importance, d.added_by, d.created_at
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
    ) -> tuple[Person, EmbeddingRecord]:
        operation_type = "confirm-pending-existing" if person_id else "confirm-pending-new"
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
                    "INSERT INTO persons(person_id, name, metadata, created_at) VALUES (?, ?, ?, ?)",
                    (
                        person_id,
                        name.strip(),
                        json.dumps(metadata or {}, separators=(",", ":")),
                        utc_now(),
                    ),
                )
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
            conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))
            _record_person_operation(
                conn,
                operation_id,
                operation_type,
                {"person_id": person_id, "embedding_id": embedding_id},
            )
            return self._confirmed_records(conn, person_id, embedding_id)

    @staticmethod
    def _confirmed_records(
        conn: sqlite3.Connection,
        person_id: str,
        embedding_id: str,
    ) -> tuple[Person, EmbeddingRecord]:
        person_row = conn.execute(
            "SELECT person_id, name, metadata, created_at, deleted_at FROM persons WHERE person_id = ?",
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
        person = Person(
            person_id=person_row["person_id"],
            name=person_row["name"],
            metadata=json.loads(person_row["metadata"]),
            created_at=person_row["created_at"],
            deleted_at=person_row["deleted_at"],
        )
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
    ) -> dict:
        operation_type = "confirm-init-existing" if person_id else "confirm-init-new"
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
                    "INSERT INTO persons(person_id, name, metadata, created_at) VALUES (?, ?, '{}', ?)",
                    (person_id, name.strip(), utc_now()),
                )
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
            result = {"person_id": person_id, "accepted": accepted}
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


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    conn.executescript(
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
    conn.executescript(
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
    conn.executescript(
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
    conn.executescript(
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
    conn.executescript(
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
    conn.executescript(
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
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_embeddings_deleted
        ON embeddings(deleted_at, purge_after);

        PRAGMA user_version = 10;
        """
    )


def _migrate_10_to_11(conn: sqlite3.Connection) -> None:
    conn.executescript(
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
    conn.executescript(
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
